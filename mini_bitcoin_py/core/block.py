"""
Block and BlockHeader structures.

BlockHeader:
- version: int32 (default 1)
- prev_hash: 32-byte hex (hash of previous block, "00"*32 for genesis)
- merkle_root: 32-byte hex (merkle root of transactions)
- timestamp: uint32 (unix timestamp)
- target: 256-bit integer (PoW target, block_hash must be <= target)
- nonce: uint32 (PoW solution)

Block:
- header: BlockHeader
- transactions: list[Transaction]
- block_hash: computed as double_sha256(serialize(header))

Block Hash Computation:
The block hash is computed from the serialized header only.
Header serialization is deterministic and includes all fields.

PoW Validity:
int(block_hash, 16) <= target
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import time

from mini_bitcoin_py.core.encoding import (
    encode_int32,
    encode_uint32,
    encode_fixed_bytes,
    encode_target,
)
from mini_bitcoin_py.core.hashing import double_sha256
from mini_bitcoin_py.core.tx import Transaction
from mini_bitcoin_py.core.merkle import compute_merkle_root


# Genesis block previous hash
GENESIS_PREV_HASH = "00" * 32


@dataclass
class BlockHeader:
    """
    Block header containing metadata and PoW fields.

    Attributes:
        version: Block version (default 1)
        prev_hash: Hash of the previous block header
        merkle_root: Merkle root of block transactions
        timestamp: Unix timestamp when block was created
        target: PoW target (block hash must be <= this value)
        nonce: PoW solution nonce
    """

    version: int
    prev_hash: str  # 64 hex chars = 32 bytes
    merkle_root: str  # 64 hex chars = 32 bytes
    timestamp: int
    target: int  # 256-bit integer
    nonce: int = 0

    def serialize(self) -> bytes:
        """
        Serialize header for hashing.

        Format:
        - version: 4 bytes (int32, little-endian)
        - prev_hash: 32 bytes
        - merkle_root: 32 bytes
        - timestamp: 4 bytes (uint32, little-endian)
        - target: 32 bytes (big-endian for comparison)
        - nonce: 4 bytes (uint32, little-endian)

        Total: 108 bytes
        """
        return (
            encode_int32(self.version)
            + encode_fixed_bytes(self.prev_hash, 32)
            + encode_fixed_bytes(self.merkle_root, 32)
            + encode_uint32(self.timestamp)
            + encode_target(self.target)
            + encode_uint32(self.nonce)
        )

    def compute_hash(self) -> str:
        """
        Compute block header hash.

        Returns:
            Block hash as 64-char hex string
        """
        serialized = self.serialize()
        hash_bytes = double_sha256(serialized)
        return hash_bytes.hex()

    def is_valid_pow(self) -> bool:
        """
        Check if the proof-of-work is valid.

        Returns:
            True if int(block_hash, 16) <= target
        """
        block_hash = self.compute_hash()
        hash_int = int(block_hash, 16)
        return hash_int <= self.target

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "prev_hash": self.prev_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "target": hex(self.target),
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlockHeader":
        """Create from dictionary."""
        target = data["target"]
        if isinstance(target, str):
            target = int(target, 16)
        return cls(
            version=data.get("version", 1),
            prev_hash=data["prev_hash"],
            merkle_root=data["merkle_root"],
            timestamp=data["timestamp"],
            target=target,
            nonce=data.get("nonce", 0),
        )


@dataclass
class Block:
    """
    A complete block containing header and transactions.

    Attributes:
        header: Block header
        transactions: List of transactions (coinbase first)
    """

    header: BlockHeader
    transactions: List[Transaction] = field(default_factory=list)
    _hash_cache: Optional[str] = field(default=None, repr=False, compare=False)

    @property
    def block_hash(self) -> str:
        """Get the block hash (cached)."""
        if self._hash_cache is None:
            self._hash_cache = self.header.compute_hash()
        return self._hash_cache

    @property
    def prev_hash(self) -> str:
        """Get the previous block hash."""
        return self.header.prev_hash

    @property
    def timestamp(self) -> int:
        """Get the block timestamp."""
        return self.header.timestamp

    @property
    def target(self) -> int:
        """Get the PoW target."""
        return self.header.target

    @property
    def nonce(self) -> int:
        """Get the nonce."""
        return self.header.nonce

    @nonce.setter
    def nonce(self, value: int):
        """Set the nonce and invalidate hash cache."""
        self.header.nonce = value
        self._hash_cache = None

    def invalidate_hash_cache(self):
        """Invalidate the hash cache."""
        self._hash_cache = None

    def is_genesis(self) -> bool:
        """Check if this is the genesis block."""
        return self.header.prev_hash == GENESIS_PREV_HASH

    def compute_merkle_root(self) -> str:
        """Compute merkle root from transactions."""
        txids = [tx.txid for tx in self.transactions]
        return compute_merkle_root(txids)

    def verify_merkle_root(self) -> bool:
        """Verify that header merkle_root matches computed value."""
        return self.header.merkle_root == self.compute_merkle_root()

    def is_valid_pow(self) -> bool:
        """Check if PoW is valid."""
        return self.header.is_valid_pow()

    def get_coinbase(self) -> Optional[Transaction]:
        """Get the coinbase transaction (first tx)."""
        if self.transactions:
            return self.transactions[0]
        return None

    def get_fees(self) -> int:
        """
        Calculate total fees from non-coinbase transactions.

        Note: This requires access to UTXO set to know input amounts.
        Returns 0 as fees must be calculated during validation.
        """
        return 0  # Fees are calculated during validation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "block_hash": self.block_hash,
            "header": self.header.to_dict(),
            "transactions": [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Block":
        """Create from dictionary."""
        return cls(
            header=BlockHeader.from_dict(data["header"]),
            transactions=[
                Transaction.from_dict(tx) for tx in data.get("transactions", [])
            ],
        )

    @classmethod
    def create_candidate(
        cls,
        prev_hash: str,
        prev_target: int,
        transactions: List[Transaction],
        miner_address: str,
        block_reward: int,
        version: int = 1,
    ) -> "Block":
        """
        Create a candidate block for mining.

        This creates a block with:
        - Coinbase transaction (first)
        - Provided transactions
        - Computed merkle root
        - Current timestamp

        Args:
            prev_hash: Hash of the previous block
            prev_target: Target to use (may be adjusted)
            transactions: Transactions to include (excluding coinbase)
            miner_address: Address to receive block reward
            block_reward: Base block reward amount
            version: Block version

        Returns:
            Block ready for mining (nonce = 0)
        """
        # Calculate fees from transactions
        # Note: In real usage, fees would be validated first
        fees = 0  # Will be calculated during mining if needed

        # Create coinbase as first transaction
        coinbase = Transaction.create_coinbase(
            miner_address=miner_address,
            reward=block_reward,
            fees=fees,
        )

        # All transactions: coinbase first, then others
        all_txs = [coinbase] + list(transactions)

        # Compute merkle root
        txids = [tx.txid for tx in all_txs]
        merkle_root = compute_merkle_root(txids)

        # Create header
        header = BlockHeader(
            version=version,
            prev_hash=prev_hash,
            merkle_root=merkle_root,
            timestamp=int(time.time()),
            target=prev_target,
            nonce=0,
        )

        return cls(header=header, transactions=all_txs)


def create_genesis_block(
    miner_address: str,
    block_reward: int,
    target: int,
    timestamp: Optional[int] = None,
) -> Block:
    """
    Create the genesis block.

    Args:
        miner_address: Address to receive genesis reward
        block_reward: Genesis block reward
        target: Initial PoW target
        timestamp: Optional specific timestamp

    Returns:
        Genesis block (not mined yet, nonce=0)
    """
    if timestamp is None:
        timestamp = int(time.time())

    # Create coinbase transaction
    coinbase = Transaction.create_coinbase(
        miner_address=miner_address,
        reward=block_reward,
        fees=0,
    )

    # Compute merkle root
    merkle_root = compute_merkle_root([coinbase.txid])

    # Create header with genesis prev_hash
    header = BlockHeader(
        version=1,
        prev_hash=GENESIS_PREV_HASH,
        merkle_root=merkle_root,
        timestamp=timestamp,
        target=target,
        nonce=0,
    )

    return Block(header=header, transactions=[coinbase])
