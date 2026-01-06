"""
Cryptographic hashing functions for the blockchain.

This module provides:
- sha256: Single SHA-256 hash
- double_sha256: SHA-256(SHA-256(data)) - used for block hashes and txids
- hash160: RIPEMD160(SHA256(data)) - used for address generation
"""

import hashlib
from typing import Union


def sha256(data: Union[bytes, str]) -> bytes:
    """
    Compute SHA-256 hash of data.

    Args:
        data: Input data as bytes or hex string

    Returns:
        32-byte hash as bytes
    """
    if isinstance(data, str):
        data = bytes.fromhex(data)
    return hashlib.sha256(data).digest()


def double_sha256(data: Union[bytes, str]) -> bytes:
    """
    Compute double SHA-256 hash (SHA256(SHA256(data))).

    This is the standard hash function used in Bitcoin for:
    - Block header hashing
    - Transaction ID computation
    - Merkle tree construction

    Args:
        data: Input data as bytes or hex string

    Returns:
        32-byte hash as bytes
    """
    if isinstance(data, str):
        data = bytes.fromhex(data)
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash160(data: Union[bytes, str]) -> bytes:
    """
    Compute HASH160: RIPEMD160(SHA256(data)).

    This is used to derive the pubkey_hash (address) from a public key.

    Args:
        data: Input data as bytes or hex string (typically a compressed public key)

    Returns:
        20-byte hash as bytes
    """
    if isinstance(data, str):
        data = bytes.fromhex(data)
    sha256_hash = hashlib.sha256(data).digest()
    # Use hashlib.new for RIPEMD160 (available in OpenSSL)
    ripemd160 = hashlib.new("ripemd160")
    ripemd160.update(sha256_hash)
    return ripemd160.digest()


def hash_to_hex(hash_bytes: bytes) -> str:
    """Convert hash bytes to lowercase hex string."""
    return hash_bytes.hex()


def hex_to_hash(hex_string: str) -> bytes:
    """Convert lowercase hex string to hash bytes."""
    return bytes.fromhex(hex_string)
