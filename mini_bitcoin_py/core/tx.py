"""
Transaction structures for the UTXO model.

Transaction Structure:
- version: int32
- inputs: list[TxIn]
- outputs: list[TxOut]
- locktime: uint32 (default 0)

TxIn Structure:
- prev_txid: 32-byte hex (points to previous transaction)
- prev_index: uint32 (index of output in previous transaction)
- signature: hex (DER-encoded ECDSA signature)
- pubkey: hex (33-byte compressed public key)

TxOut Structure:
- amount: int64 (satoshi-like units, must be >= 0)
- pubkey_hash: 20-byte hex (HASH160 of recipient's pubkey)

Coinbase Transaction:
- First transaction in every block
- Input: prev_txid = "00"*32, prev_index = 0xFFFFFFFF (-1 as uint32), no signature
- Contains block reward + fees

TXID Computation:
- txid = double_sha256(serialize(tx_without_signatures))
- Signatures are excluded from txid to avoid circular dependency

Sighash Preimage (simplified):
For each input being signed:
  - version (4 bytes)
  - For each input: prev_txid + prev_index + (pubkey_hash of referenced UTXO if signing this input)
  - For each output: amount + pubkey_hash
  - locktime (4 bytes)
Signature = ECDSA_sign(double_sha256(preimage))
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from mini_bitcoin_py.core.encoding import (
    encode_int32,
    encode_uint32,
    encode_int64,
    encode_varint,
    encode_fixed_bytes,
    encode_hex_bytes,
)
from mini_bitcoin_py.core.hashing import double_sha256


# Coinbase constants
COINBASE_TXID = "00" * 32
COINBASE_INDEX = 0xFFFFFFFF  # -1 as uint32


@dataclass
class TxOut:
    """
    Transaction output.

    Attributes:
        amount: Value in satoshi-like units (must be >= 0)
        pubkey_hash: HASH160 of recipient's public key (20 bytes as hex)
    """

    amount: int
    pubkey_hash: str  # 40 hex chars = 20 bytes

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("TxOut amount cannot be negative")
        if len(self.pubkey_hash) != 40:
            raise ValueError(f"pubkey_hash must be 40 hex chars, got {len(self.pubkey_hash)}")

    def serialize(self) -> bytes:
        """Serialize output for txid computation and signing."""
        return (
            encode_int64(self.amount)
            + encode_fixed_bytes(self.pubkey_hash, 20)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "amount": self.amount,
            "pubkey_hash": self.pubkey_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TxOut":
        """Create from dictionary."""
        return cls(
            amount=data["amount"],
            pubkey_hash=data["pubkey_hash"],
        )


@dataclass
class TxIn:
    """
    Transaction input.

    Attributes:
        prev_txid: Transaction ID being spent (32 bytes as hex)
        prev_index: Output index in the previous transaction
        signature: DER-encoded ECDSA signature (hex)
        pubkey: Compressed public key used to sign (hex, 33 bytes)
    """

    prev_txid: str  # 64 hex chars = 32 bytes
    prev_index: int
    signature: str = ""  # Hex encoded DER signature
    pubkey: str = ""  # Hex encoded compressed pubkey (66 hex chars = 33 bytes)

    def __post_init__(self):
        if len(self.prev_txid) != 64:
            raise ValueError(f"prev_txid must be 64 hex chars, got {len(self.prev_txid)}")

    def is_coinbase(self) -> bool:
        """Check if this is a coinbase input."""
        return self.prev_txid == COINBASE_TXID and self.prev_index == COINBASE_INDEX

    def serialize_for_txid(self) -> bytes:
        """
        Serialize input for txid computation (without signature/pubkey).

        For txid, we only include prev_txid and prev_index.
        """
        return (
            encode_fixed_bytes(self.prev_txid, 32)
            + encode_uint32(self.prev_index)
        )

    def serialize_for_signing(self, pubkey_hash_to_include: Optional[str] = None) -> bytes:
        """
        Serialize input for signing preimage.

        Args:
            pubkey_hash_to_include: If this is the input being signed, include
                                    the pubkey_hash of the UTXO being spent
        """
        result = encode_fixed_bytes(self.prev_txid, 32) + encode_uint32(self.prev_index)
        if pubkey_hash_to_include:
            result += encode_fixed_bytes(pubkey_hash_to_include, 20)
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "prev_txid": self.prev_txid,
            "prev_index": self.prev_index,
            "signature": self.signature,
            "pubkey": self.pubkey,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TxIn":
        """Create from dictionary."""
        return cls(
            prev_txid=data["prev_txid"],
            prev_index=data["prev_index"],
            signature=data.get("signature", ""),
            pubkey=data.get("pubkey", ""),
        )

    @classmethod
    def coinbase(cls) -> "TxIn":
        """Create a coinbase input."""
        return cls(
            prev_txid=COINBASE_TXID,
            prev_index=COINBASE_INDEX,
            signature="",
            pubkey="",
        )


@dataclass
class Transaction:
    """
    A blockchain transaction.

    Attributes:
        version: Transaction version (default 1)
        inputs: List of transaction inputs
        outputs: List of transaction outputs
        locktime: Block height or timestamp for time-locked tx (default 0)
    """

    version: int = 1
    inputs: List[TxIn] = field(default_factory=list)
    outputs: List[TxOut] = field(default_factory=list)
    locktime: int = 0
    _txid_cache: Optional[str] = field(default=None, repr=False, compare=False)

    def serialize_for_txid(self) -> bytes:
        """
        Serialize transaction for txid computation.

        Excludes signatures to avoid circular dependency.
        """
        result = encode_int32(self.version)

        # Serialize inputs (without signatures)
        result += encode_varint(len(self.inputs))
        for inp in self.inputs:
            result += inp.serialize_for_txid()

        # Serialize outputs
        result += encode_varint(len(self.outputs))
        for out in self.outputs:
            result += out.serialize()

        result += encode_uint32(self.locktime)
        return result

    def compute_txid(self) -> str:
        """
        Compute the transaction ID.

        txid = hex(double_sha256(serialize_for_txid()))
        """
        if self._txid_cache is not None:
            return self._txid_cache
        serialized = self.serialize_for_txid()
        hash_bytes = double_sha256(serialized)
        self._txid_cache = hash_bytes.hex()
        return self._txid_cache

    @property
    def txid(self) -> str:
        """Get the transaction ID."""
        return self.compute_txid()

    def invalidate_txid_cache(self):
        """Invalidate the txid cache (call after modifying tx structure)."""
        self._txid_cache = None

    def create_sighash_preimage(
        self,
        input_index: int,
        utxo_pubkey_hash: str,
    ) -> bytes:
        """
        Create the preimage for signing a specific input.

        The preimage includes:
        - version
        - All inputs (with utxo_pubkey_hash only for the input being signed)
        - All outputs
        - locktime

        Args:
            input_index: Index of the input being signed
            utxo_pubkey_hash: pubkey_hash of the UTXO being spent by this input

        Returns:
            Preimage bytes (will be double_sha256'd before signing)
        """
        result = encode_int32(self.version)

        # Serialize inputs
        result += encode_varint(len(self.inputs))
        for i, inp in enumerate(self.inputs):
            if i == input_index:
                result += inp.serialize_for_signing(utxo_pubkey_hash)
            else:
                result += inp.serialize_for_signing(None)

        # Serialize outputs
        result += encode_varint(len(self.outputs))
        for out in self.outputs:
            result += out.serialize()

        result += encode_uint32(self.locktime)
        return result

    def compute_sighash(self, input_index: int, utxo_pubkey_hash: str) -> bytes:
        """
        Compute the hash to be signed for a specific input.

        Returns:
            32-byte double_sha256 hash of the preimage
        """
        preimage = self.create_sighash_preimage(input_index, utxo_pubkey_hash)
        return double_sha256(preimage)

    def is_coinbase(self) -> bool:
        """Check if this is a coinbase transaction."""
        return (
            len(self.inputs) == 1
            and self.inputs[0].is_coinbase()
        )

    def total_output_amount(self) -> int:
        """Sum of all output amounts."""
        return sum(out.amount for out in self.outputs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "txid": self.txid,
            "version": self.version,
            "inputs": [inp.to_dict() for inp in self.inputs],
            "outputs": [out.to_dict() for out in self.outputs],
            "locktime": self.locktime,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        """Create from dictionary."""
        tx = cls(
            version=data.get("version", 1),
            inputs=[TxIn.from_dict(i) for i in data.get("inputs", [])],
            outputs=[TxOut.from_dict(o) for o in data.get("outputs", [])],
            locktime=data.get("locktime", 0),
        )
        return tx

    @classmethod
    def create_coinbase(
        cls,
        miner_address: str,
        reward: int,
        fees: int = 0,
    ) -> "Transaction":
        """
        Create a coinbase transaction.

        Args:
            miner_address: pubkey_hash (address) of the miner
            reward: Block reward amount
            fees: Total fees from block transactions

        Returns:
            Coinbase transaction
        """
        return cls(
            version=1,
            inputs=[TxIn.coinbase()],
            outputs=[TxOut(amount=reward + fees, pubkey_hash=miner_address)],
            locktime=0,
        )
