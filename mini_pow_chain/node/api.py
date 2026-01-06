"""
FastAPI node API.

Provides HTTP endpoints for:
- Health check
- Chain queries
- Transaction submission
- Block mining and submission
- Peer management
- Chain sync
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mini_pow_chain.core.block import Block, create_genesis_block
from mini_pow_chain.core.tx import Transaction, TxIn, TxOut
from mini_pow_chain.core.utxo import UTXOSet, MempoolUTXOTracker
from mini_pow_chain.core.consensus import mine_block, DEFAULT_TARGET
from mini_pow_chain.core.validation import (
    validate_transaction_against_utxo,
    validate_block_full,
)
from mini_pow_chain.core.keys import Wallet
from mini_pow_chain.node.config import Settings, get_settings
from mini_pow_chain.node.db import get_db, get_db_session, init_db
from mini_pow_chain.node.storage import (
    BlockStorage,
    ChainStateStorage,
    PeerStorage,
    MempoolStorage,
    rebuild_utxo_set,
)
from mini_pow_chain.node.p2p import P2PManager
from mini_pow_chain.node.sync import ChainSynchronizer

logger = logging.getLogger(__name__)


# === Pydantic Models for API ===


class TxInRequest(BaseModel):
    """Transaction input for API requests."""

    prev_txid: str = Field(..., min_length=64, max_length=64)
    prev_index: int = Field(..., ge=0)
    signature: str = ""
    pubkey: str = ""


class TxOutRequest(BaseModel):
    """Transaction output for API requests."""

    amount: int = Field(..., ge=0)
    pubkey_hash: str = Field(..., min_length=40, max_length=40)


class TransactionRequest(BaseModel):
    """Transaction submission request."""

    version: int = 1
    inputs: List[TxInRequest]
    outputs: List[TxOutRequest]
    locktime: int = 0


class MineRequest(BaseModel):
    """Mining request."""

    miner_address: str = Field(..., min_length=40, max_length=40)


class PeerAddRequest(BaseModel):
    """Add peer request."""

    url: str


class SyncRequest(BaseModel):
    """Sync from peer request."""

    peer_url: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    node_name: str
    chain_height: int
    tip_hash: Optional[str]
    utxo_count: int
    mempool_size: int
    peer_count: int


class BalanceResponse(BaseModel):
    """Balance query response."""

    address: str
    balance: int
    utxo_count: int


class ChainResponse(BaseModel):
    """Chain query response."""

    height: int
    tip_hash: Optional[str]
    blocks: List[Dict[str, Any]]


# === Application State ===


@dataclass
class NodeState:
    """Mutable node state."""

    utxo_set: UTXOSet = field(default_factory=UTXOSet)
    mempool: Dict[str, Transaction] = field(default_factory=dict)
    mempool_tracker: MempoolUTXOTracker = field(default_factory=MempoolUTXOTracker)
    p2p: P2PManager = field(default_factory=P2PManager)
    settings: Optional[Settings] = None
    mining_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# Global state (initialized in lifespan)
_node_state: Optional[NodeState] = None


def get_state() -> NodeState:
    """Get the node state."""
    if _node_state is None:
        raise RuntimeError("Node state not initialized")
    return _node_state


# === Lifespan Management ===


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _node_state

    settings = get_settings()

    logger.info(f"Starting node: {settings.node_name}")
    logger.info(f"Database: {settings.database_url}")

    # Initialize database
    init_db()

    # Initialize node state
    _node_state = NodeState(settings=settings)

    # Load state from database
    with get_db_session() as session:
        # Rebuild UTXO set
        _node_state.utxo_set = rebuild_utxo_set(session)

        # Initialize chain state if needed
        state_storage = ChainStateStorage(session)
        state_storage.get_or_create_state(settings.default_target)

        # Load peers
        peer_storage = PeerStorage(session)
        for peer_url in peer_storage.get_active_peers():
            _node_state.p2p.add_peer(peer_url)

        # Load mempool
        mempool_storage = MempoolStorage(session)
        for tx in mempool_storage.get_all_txs():
            _node_state.mempool[tx.txid] = tx
            _node_state.mempool_tracker.add_transaction(tx)

    # Add bootstrap peers
    for peer in settings.bootstrap_peers:
        _node_state.p2p.add_peer(peer)

    logger.info(f"Node started: {len(_node_state.utxo_set)} UTXOs, {len(_node_state.mempool)} mempool txs")

    yield

    # Shutdown
    logger.info("Shutting down node...")
    await _node_state.p2p.close()
    _node_state = None


# === FastAPI App ===


app = FastAPI(
    title="Mini PoW Chain Node",
    description="A minimal Bitcoin-like Proof-of-Work blockchain node",
    version="0.1.0",
    lifespan=lifespan,
)


# === Endpoints ===


@app.get("/health", response_model=HealthResponse)
async def health(db: Session = Depends(get_db)):
    """Health check endpoint."""
    state = get_state()
    state_storage = ChainStateStorage(db)
    chain_state = state_storage.get_state()

    return HealthResponse(
        status="healthy",
        node_name=state.settings.node_name if state.settings else "unknown",
        chain_height=chain_state.tip_height if chain_state else -1,
        tip_hash=chain_state.tip_hash if chain_state else None,
        utxo_count=len(state.utxo_set),
        mempool_size=len(state.mempool),
        peer_count=len(state.p2p.peers),
    )


@app.get("/chain")
async def get_chain(db: Session = Depends(get_db)):
    """Get the full chain."""
    state_storage = ChainStateStorage(db)
    block_storage = BlockStorage(db)

    chain_state = state_storage.get_state()
    blocks = block_storage.get_all_blocks_ordered()

    return {
        "height": chain_state.tip_height if chain_state else -1,
        "tip_hash": chain_state.tip_hash if chain_state else None,
        "blocks": [b.to_dict() for b in blocks],
    }


@app.get("/block/{block_hash}")
async def get_block(block_hash: str, db: Session = Depends(get_db)):
    """Get a block by hash."""
    block_storage = BlockStorage(db)
    block = block_storage.get_block_by_hash(block_hash)

    if block is None:
        raise HTTPException(status_code=404, detail="Block not found")

    # Get height from model
    model = block_storage.get_block_model_by_hash(block_hash)

    return {
        "height": model.height if model else None,
        **block.to_dict(),
    }


@app.get("/balance/{address}", response_model=BalanceResponse)
async def get_balance(address: str):
    """Get balance for an address."""
    state = get_state()

    if len(address) != 40:
        raise HTTPException(status_code=400, detail="Invalid address format")

    balance = state.utxo_set.get_balance(address)
    utxos = state.utxo_set.get_utxos_for_address(address)

    return BalanceResponse(
        address=address,
        balance=balance,
        utxo_count=len(utxos),
    )


@app.get("/utxos/{address}")
async def get_utxos(address: str):
    """Get UTXOs for an address."""
    state = get_state()

    if len(address) != 40:
        raise HTTPException(status_code=400, detail="Invalid address format")

    utxos = state.utxo_set.get_utxos_for_address(address)

    return {
        "address": address,
        "utxos": [
            {
                "txid": key[0],
                "vout": key[1],
                "amount": utxo.amount,
                "pubkey_hash": utxo.pubkey_hash,
            }
            for key, utxo in utxos.items()
        ],
    }


@app.get("/mempool")
async def get_mempool():
    """Get mempool transactions."""
    state = get_state()

    return {
        "size": len(state.mempool),
        "transactions": [tx.to_dict() for tx in state.mempool.values()],
    }


@app.post("/tx")
async def submit_transaction(
    request: TransactionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Submit a transaction to the mempool."""
    state = get_state()

    # Build transaction
    tx = Transaction(
        version=request.version,
        inputs=[
            TxIn(
                prev_txid=inp.prev_txid,
                prev_index=inp.prev_index,
                signature=inp.signature,
                pubkey=inp.pubkey,
            )
            for inp in request.inputs
        ],
        outputs=[
            TxOut(amount=out.amount, pubkey_hash=out.pubkey_hash)
            for out in request.outputs
        ],
        locktime=request.locktime,
    )

    txid = tx.txid

    # Check if already in mempool
    if txid in state.mempool:
        raise HTTPException(status_code=409, detail="Transaction already in mempool")

    # Check if already seen (loop prevention)
    if state.p2p.is_tx_seen(txid):
        raise HTTPException(status_code=409, detail="Transaction already processed")

    # Validate transaction
    result = validate_transaction_against_utxo(
        tx,
        state.utxo_set,
        state.mempool_tracker,
        allow_coinbase=False,
    )

    if not result.valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transaction: {result.error.value if result.error else ''} - {result.message}",
        )

    # Add to mempool
    state.mempool[txid] = tx
    state.mempool_tracker.add_transaction(tx)

    # Persist to database
    mempool_storage = MempoolStorage(db)
    mempool_storage.store_tx(tx, fee=result.fee)
    db.commit()

    logger.info(f"Added tx {txid[:16]}... to mempool (fee={result.fee})")

    # Broadcast to peers
    background_tasks.add_task(state.p2p.broadcast_transaction, tx)

    return {"txid": txid, "fee": result.fee}


@app.post("/block")
async def receive_block(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Receive a block from a peer."""
    state = get_state()
    settings = state.settings

    data = await request.json()

    try:
        block = Block.from_dict(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid block format: {e}")

    block_hash = block.block_hash

    # Check if already seen
    if state.p2p.is_block_seen(block_hash):
        raise HTTPException(status_code=409, detail="Block already processed")

    # Mark as seen
    state.p2p.mark_block_seen(block_hash)

    # Check if already stored
    block_storage = BlockStorage(db)
    if block_storage.block_exists(block_hash):
        raise HTTPException(status_code=409, detail="Block already exists")

    # Add block through synchronizer
    synchronizer = ChainSynchronizer(
        db, state.utxo_set, settings.block_reward if settings else 5000000000
    )
    success, message = synchronizer.add_block(block)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Remove mined transactions from mempool
    for tx in block.transactions[1:]:  # Skip coinbase
        if tx.txid in state.mempool:
            del state.mempool[tx.txid]
            state.mempool_tracker.remove_transaction(tx)

    # Clean up mempool in DB
    mempool_storage = MempoolStorage(db)
    mempool_storage.remove_txs([tx.txid for tx in block.transactions[1:]])
    db.commit()

    # Broadcast to peers
    background_tasks.add_task(state.p2p.broadcast_block, block)

    logger.info(f"Received and stored block {block_hash[:16]}...")

    return {"block_hash": block_hash, "message": message}


@app.post("/mine")
async def mine(request: MineRequest, db: Session = Depends(get_db)):
    """Mine a new block."""
    state = get_state()
    settings = state.settings

    if not settings:
        raise HTTPException(status_code=500, detail="Node not configured")

    # Acquire mining lock
    async with state.mining_lock:
        state_storage = ChainStateStorage(db)
        block_storage = BlockStorage(db)

        chain_state = state_storage.get_state()

        # Get previous block info
        if chain_state and chain_state.tip_hash:
            prev_hash = chain_state.tip_hash
            prev_block = block_storage.get_block_by_hash(prev_hash)
            prev_target = int(chain_state.current_target, 16)
        else:
            # Genesis block
            prev_hash = "00" * 32
            prev_block = None
            prev_target = settings.default_target

        # Select transactions from mempool
        mempool_txs = list(state.mempool.values())[: settings.max_block_txs]

        # Calculate fees
        total_fees = 0
        for tx in mempool_txs:
            result = validate_transaction_against_utxo(tx, state.utxo_set)
            if result.valid:
                total_fees += result.fee

        # Create candidate block
        block = Block.create_candidate(
            prev_hash=prev_hash,
            prev_target=prev_target,
            transactions=mempool_txs,
            miner_address=request.miner_address,
            block_reward=settings.block_reward + total_fees,
        )

        logger.info(f"Mining block with {len(mempool_txs)} txs, reward={settings.block_reward + total_fees}")

        # Mine the block (this blocks the event loop - acceptable for demo)
        result = mine_block(block)

        if not result.success:
            raise HTTPException(status_code=500, detail="Mining failed")

        logger.info(
            f"Mined block {block.block_hash[:16]}... in {result.elapsed_seconds:.2f}s "
            f"(nonce={result.nonce}, hashes={result.hash_count})"
        )

        # Add block through synchronizer
        synchronizer = ChainSynchronizer(db, state.utxo_set, settings.block_reward)
        success, message = synchronizer.add_block(block)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to add mined block: {message}")

        # Remove mined transactions from mempool
        for tx in mempool_txs:
            if tx.txid in state.mempool:
                del state.mempool[tx.txid]
                state.mempool_tracker.remove_transaction(tx)

        # Clean up mempool in DB
        mempool_storage = MempoolStorage(db)
        mempool_storage.remove_txs([tx.txid for tx in mempool_txs])
        db.commit()

        # Broadcast block
        await state.p2p.broadcast_block(block)

        return {
            "block_hash": block.block_hash,
            "height": chain_state.tip_height + 1 if chain_state else 0,
            "nonce": result.nonce,
            "elapsed_seconds": result.elapsed_seconds,
            "transactions": len(block.transactions),
        }


@app.get("/peers")
async def get_peers(db: Session = Depends(get_db)):
    """Get list of peers."""
    state = get_state()
    peer_storage = PeerStorage(db)

    return {
        "peers": list(state.p2p.peers),
        "stored_peers": [
            {"url": p.url, "is_active": p.is_active, "failures": p.failures}
            for p in peer_storage.get_all_peers()
        ],
    }


@app.post("/peers/add")
async def add_peer(request: PeerAddRequest, db: Session = Depends(get_db)):
    """Add a peer."""
    state = get_state()

    url = request.url.rstrip("/")

    # Add to P2P manager
    state.p2p.add_peer(url)

    # Persist to database
    peer_storage = PeerStorage(db)
    peer_storage.add_peer(url)
    db.commit()

    return {"message": f"Added peer: {url}"}


@app.post("/sync")
async def sync_from_peer(request: SyncRequest, db: Session = Depends(get_db)):
    """Sync chain from a peer."""
    state = get_state()
    settings = state.settings

    if not settings:
        raise HTTPException(status_code=500, detail="Node not configured")

    peer_url = request.peer_url.rstrip("/")

    logger.info(f"Syncing from peer: {peer_url}")

    # Get chain from peer
    chain_data = await state.p2p.get_peer_chain(peer_url)

    if chain_data is None:
        raise HTTPException(status_code=502, detail="Failed to get chain from peer")

    if not chain_data.get("blocks"):
        return {"message": "Peer has empty chain", "synced": False}

    # Sync from peer chain
    synchronizer = ChainSynchronizer(db, state.utxo_set, settings.block_reward)
    success, message, new_height = synchronizer.sync_from_peer_chain(chain_data["blocks"])

    if success:
        # Clear mempool (might conflict with new chain)
        state.mempool.clear()
        state.mempool_tracker.clear()
        mempool_storage = MempoolStorage(db)
        mempool_storage.clear()
        db.commit()

    return {
        "synced": success,
        "message": message,
        "new_height": new_height,
    }


# === Error Handlers ===


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
