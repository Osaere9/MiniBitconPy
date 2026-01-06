"""
SQLAlchemy database models for blockchain persistence.

Tables:
- blocks: Store all blocks with header data and transactions (JSONB)
- chain_state: Current chain tip and state
- peers: Known peer URLs
- mempool: Pending transactions (optional, can be in-memory)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class BlockModel(Base):
    """
    Stored block with header and transactions.

    The block is stored with denormalized header fields for efficient querying,
    plus the full block data in JSONB for complete reconstruction.
    """

    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Block identification
    block_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    height: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Header fields (denormalized for querying)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target: Mapped[str] = mapped_column(String(66), nullable=False)  # Hex string
    nonce: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Full block data (header + transactions)
    block_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Indexes
    __table_args__ = (
        Index("ix_blocks_height_hash", "height", "block_hash"),
    )

    def __repr__(self) -> str:
        return f"<Block(hash={self.block_hash[:16]}..., height={self.height})>"


class ChainStateModel(Base):
    """
    Current chain state (singleton row).

    Stores the current best chain tip and related state.
    """

    __tablename__ = "chain_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Best chain tip
    tip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tip_height: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)

    # Current target for next block
    current_target: Mapped[str] = mapped_column(String(66), nullable=False)

    # Cumulative work (stored as hex string due to size)
    cumulative_work: Mapped[str] = mapped_column(Text, nullable=False, default="0")

    # Last sync time
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Update timestamp
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<ChainState(tip={self.tip_hash[:16] if self.tip_hash else 'None'}..., height={self.tip_height})>"


class PeerModel(Base):
    """
    Known peer node.
    """

    __tablename__ = "peers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Peer URL (e.g., "http://localhost:8001")
    url: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Peer(url={self.url}, active={self.is_active})>"


class MempoolTxModel(Base):
    """
    Mempool transaction (optional persistence).

    Can be used to persist mempool across restarts.
    """

    __tablename__ = "mempool_txs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Transaction ID
    txid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Full transaction data
    tx_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Fee for prioritization
    fee: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<MempoolTx(txid={self.txid[:16]}..., fee={self.fee})>"
