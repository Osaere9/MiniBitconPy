"""
Blockchain storage operations.

Provides high-level storage operations for:
- Blocks: Store, retrieve, query
- Chain state: Manage tip and state
- Peers: Manage peer list
- Mempool: Optional persistence

UTXO Set Rebuild:
The UTXO set is rebuilt from blocks on startup. This is acceptable for
a demo-scale blockchain and ensures consistency.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session

from mini_pow_chain.core.block import Block
from mini_pow_chain.core.tx import Transaction
from mini_pow_chain.core.utxo import UTXOSet
from mini_pow_chain.core.consensus import compute_work
from mini_pow_chain.node.models import (
    BlockModel,
    ChainStateModel,
    PeerModel,
    MempoolTxModel,
)

logger = logging.getLogger(__name__)


class BlockStorage:
    """Storage operations for blocks."""

    def __init__(self, session: Session):
        self.session = session

    def store_block(self, block: Block, height: int) -> BlockModel:
        """
        Store a block in the database.

        Args:
            block: Block to store
            height: Block height in the chain

        Returns:
            Created BlockModel
        """
        model = BlockModel(
            block_hash=block.block_hash,
            height=height,
            version=block.header.version,
            prev_hash=block.prev_hash,
            merkle_root=block.header.merkle_root,
            timestamp=block.timestamp,
            target=hex(block.target),
            nonce=block.nonce,
            block_data=block.to_dict(),
        )
        self.session.add(model)
        self.session.flush()
        logger.info(f"Stored block {block.block_hash[:16]}... at height {height}")
        return model

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """Get a block by its hash."""
        stmt = select(BlockModel).where(BlockModel.block_hash == block_hash)
        model = self.session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return Block.from_dict(model.block_data)

    def get_block_by_height(self, height: int) -> Optional[Block]:
        """Get a block by its height."""
        stmt = select(BlockModel).where(BlockModel.height == height)
        model = self.session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return Block.from_dict(model.block_data)

    def get_block_model_by_hash(self, block_hash: str) -> Optional[BlockModel]:
        """Get block model by hash."""
        stmt = select(BlockModel).where(BlockModel.block_hash == block_hash)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_blocks_from_height(self, start_height: int, limit: int = 100) -> List[Block]:
        """Get blocks starting from a height."""
        stmt = (
            select(BlockModel)
            .where(BlockModel.height >= start_height)
            .order_by(BlockModel.height)
            .limit(limit)
        )
        models = self.session.execute(stmt).scalars().all()
        return [Block.from_dict(m.block_data) for m in models]

    def get_all_blocks_ordered(self) -> List[Block]:
        """Get all blocks ordered by height."""
        stmt = select(BlockModel).order_by(BlockModel.height)
        models = self.session.execute(stmt).scalars().all()
        return [Block.from_dict(m.block_data) for m in models]

    def get_latest_block(self) -> Optional[Block]:
        """Get the latest (highest) block."""
        stmt = select(BlockModel).order_by(BlockModel.height.desc()).limit(1)
        model = self.session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return Block.from_dict(model.block_data)

    def get_block_count(self) -> int:
        """Get the total number of blocks."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(BlockModel)
        return self.session.execute(stmt).scalar() or 0

    def block_exists(self, block_hash: str) -> bool:
        """Check if a block exists."""
        stmt = select(BlockModel.id).where(BlockModel.block_hash == block_hash)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def delete_blocks_above_height(self, height: int) -> int:
        """Delete blocks above a given height (for reorg)."""
        stmt = delete(BlockModel).where(BlockModel.height > height)
        result = self.session.execute(stmt)
        return result.rowcount


class ChainStateStorage:
    """Storage operations for chain state."""

    def __init__(self, session: Session):
        self.session = session

    def get_state(self) -> Optional[ChainStateModel]:
        """Get the chain state (singleton)."""
        stmt = select(ChainStateModel).where(ChainStateModel.id == 1)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_or_create_state(self, default_target: int) -> ChainStateModel:
        """Get or create the chain state."""
        state = self.get_state()
        if state is None:
            state = ChainStateModel(
                id=1,
                tip_hash=None,
                tip_height=-1,
                current_target=hex(default_target),
                cumulative_work="0",
            )
            self.session.add(state)
            self.session.flush()
        return state

    def update_tip(
        self,
        tip_hash: str,
        tip_height: int,
        target: int,
        cumulative_work: int,
    ):
        """Update the chain tip."""
        stmt = (
            update(ChainStateModel)
            .where(ChainStateModel.id == 1)
            .values(
                tip_hash=tip_hash,
                tip_height=tip_height,
                current_target=hex(target),
                cumulative_work=hex(cumulative_work),
                updated_at=datetime.utcnow(),
            )
        )
        self.session.execute(stmt)

    def update_last_sync(self):
        """Update the last sync timestamp."""
        stmt = (
            update(ChainStateModel)
            .where(ChainStateModel.id == 1)
            .values(last_sync=datetime.utcnow())
        )
        self.session.execute(stmt)


class PeerStorage:
    """Storage operations for peers."""

    def __init__(self, session: Session):
        self.session = session

    def add_peer(self, url: str) -> bool:
        """
        Add a peer if it doesn't exist.

        Returns:
            True if peer was added, False if already exists
        """
        # Check if exists
        stmt = select(PeerModel).where(PeerModel.url == url)
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return False

        peer = PeerModel(url=url)
        self.session.add(peer)
        self.session.flush()
        logger.info(f"Added peer: {url}")
        return True

    def get_active_peers(self) -> List[str]:
        """Get all active peer URLs."""
        stmt = select(PeerModel.url).where(PeerModel.is_active == True)
        result = self.session.execute(stmt).scalars().all()
        return list(result)

    def get_all_peers(self) -> List[PeerModel]:
        """Get all peers."""
        stmt = select(PeerModel)
        return list(self.session.execute(stmt).scalars().all())

    def update_peer_seen(self, url: str):
        """Update last seen time for a peer."""
        stmt = (
            update(PeerModel)
            .where(PeerModel.url == url)
            .values(last_seen=datetime.utcnow(), failures=0, is_active=True)
        )
        self.session.execute(stmt)

    def record_peer_failure(self, url: str, max_failures: int = 5):
        """Record a failure for a peer."""
        stmt = select(PeerModel).where(PeerModel.url == url)
        peer = self.session.execute(stmt).scalar_one_or_none()
        if peer:
            peer.failures += 1
            if peer.failures >= max_failures:
                peer.is_active = False
                logger.warning(f"Deactivated peer {url} after {peer.failures} failures")

    def remove_peer(self, url: str) -> bool:
        """Remove a peer."""
        stmt = delete(PeerModel).where(PeerModel.url == url)
        result = self.session.execute(stmt)
        return result.rowcount > 0


class MempoolStorage:
    """Storage operations for mempool (optional persistence)."""

    def __init__(self, session: Session):
        self.session = session

    def store_tx(self, tx: Transaction, fee: int = 0):
        """Store a transaction in the mempool."""
        model = MempoolTxModel(
            txid=tx.txid,
            tx_data=tx.to_dict(),
            fee=fee,
        )
        self.session.add(model)
        self.session.flush()

    def get_tx(self, txid: str) -> Optional[Transaction]:
        """Get a transaction by txid."""
        stmt = select(MempoolTxModel).where(MempoolTxModel.txid == txid)
        model = self.session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return Transaction.from_dict(model.tx_data)

    def get_all_txs(self) -> List[Transaction]:
        """Get all mempool transactions ordered by fee (highest first)."""
        stmt = select(MempoolTxModel).order_by(MempoolTxModel.fee.desc())
        models = self.session.execute(stmt).scalars().all()
        return [Transaction.from_dict(m.tx_data) for m in models]

    def remove_tx(self, txid: str) -> bool:
        """Remove a transaction from mempool."""
        stmt = delete(MempoolTxModel).where(MempoolTxModel.txid == txid)
        result = self.session.execute(stmt)
        return result.rowcount > 0

    def remove_txs(self, txids: List[str]):
        """Remove multiple transactions."""
        if txids:
            stmt = delete(MempoolTxModel).where(MempoolTxModel.txid.in_(txids))
            self.session.execute(stmt)

    def clear(self):
        """Clear all mempool transactions."""
        stmt = delete(MempoolTxModel)
        self.session.execute(stmt)

    def tx_exists(self, txid: str) -> bool:
        """Check if a transaction exists in mempool."""
        stmt = select(MempoolTxModel.id).where(MempoolTxModel.txid == txid)
        return self.session.execute(stmt).scalar_one_or_none() is not None


def rebuild_utxo_set(session: Session) -> UTXOSet:
    """
    Rebuild the UTXO set from stored blocks.

    This is called on node startup to reconstruct the UTXO state.

    Args:
        session: Database session

    Returns:
        Rebuilt UTXOSet
    """
    logger.info("Rebuilding UTXO set from blocks...")
    utxo_set = UTXOSet()

    block_storage = BlockStorage(session)
    blocks = block_storage.get_all_blocks_ordered()

    for block in blocks:
        for tx in block.transactions:
            utxo_set.apply_transaction(tx)

    logger.info(f"UTXO set rebuilt: {len(utxo_set)} UTXOs")
    return utxo_set


def calculate_cumulative_work(session: Session) -> int:
    """Calculate cumulative work from all blocks."""
    block_storage = BlockStorage(session)
    blocks = block_storage.get_all_blocks_ordered()
    return sum(compute_work(block.target) for block in blocks)
