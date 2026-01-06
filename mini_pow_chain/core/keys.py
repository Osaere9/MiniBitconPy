"""
ECDSA key management and signing using secp256k1.

This module provides:
- PrivateKey: Generate, load, and use private keys for signing
- PublicKey: Derive from private key, verify signatures
- Wallet: High-level interface for key management

Address format:
- address = hex(HASH160(compressed_pubkey))
- HASH160 = RIPEMD160(SHA256(data))
"""

import os
import secrets
from dataclasses import dataclass
from typing import Optional

try:
    import coincurve

    USING_COINCURVE = True
except ImportError:
    # Fallback to ecdsa library if coincurve not available
    import ecdsa

    USING_COINCURVE = False

from mini_pow_chain.core.hashing import double_sha256, hash160


@dataclass
class PublicKey:
    """
    An ECDSA public key on the secp256k1 curve.

    Attributes:
        key_bytes: 33-byte compressed public key
    """

    key_bytes: bytes

    @classmethod
    def from_hex(cls, hex_string: str) -> "PublicKey":
        """Create PublicKey from hex string."""
        return cls(key_bytes=bytes.fromhex(hex_string))

    def to_hex(self) -> str:
        """Return hex representation of the public key."""
        return self.key_bytes.hex()

    def to_hash160(self) -> bytes:
        """Compute HASH160 of the public key."""
        return hash160(self.key_bytes)

    def to_address(self) -> str:
        """
        Derive address from public key.

        Address = hex(HASH160(compressed_pubkey))
        """
        return self.to_hash160().hex()

    def verify(self, message_hash: bytes, signature: bytes) -> bool:
        """
        Verify an ECDSA signature.

        Args:
            message_hash: 32-byte hash that was signed
            signature: DER-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        if USING_COINCURVE:
            try:
                pubkey = coincurve.PublicKey(self.key_bytes)
                return pubkey.verify(signature, message_hash, hasher=None)
            except Exception:
                return False
        else:
            try:
                vk = ecdsa.VerifyingKey.from_string(
                    self.key_bytes, curve=ecdsa.SECP256k1
                )
                return vk.verify(signature, message_hash, hashfunc=lambda x: x)
            except Exception:
                return False


@dataclass
class PrivateKey:
    """
    An ECDSA private key on the secp256k1 curve.

    Attributes:
        key_bytes: 32-byte private key scalar
    """

    key_bytes: bytes

    @classmethod
    def generate(cls) -> "PrivateKey":
        """Generate a new random private key."""
        if USING_COINCURVE:
            # coincurve validates the key is in valid range
            key = coincurve.PrivateKey()
            return cls(key_bytes=key.secret)
        else:
            # Generate random 32 bytes and ensure it's valid for secp256k1
            while True:
                key_bytes = secrets.token_bytes(32)
                try:
                    ecdsa.SigningKey.from_string(key_bytes, curve=ecdsa.SECP256k1)
                    return cls(key_bytes=key_bytes)
                except Exception:
                    continue

    @classmethod
    def from_hex(cls, hex_string: str) -> "PrivateKey":
        """Create PrivateKey from hex string."""
        return cls(key_bytes=bytes.fromhex(hex_string))

    def to_hex(self) -> str:
        """Return hex representation of the private key."""
        return self.key_bytes.hex()

    def get_public_key(self) -> PublicKey:
        """Derive the corresponding public key."""
        if USING_COINCURVE:
            privkey = coincurve.PrivateKey(self.key_bytes)
            # Get compressed public key (33 bytes)
            pubkey_bytes = privkey.public_key.format(compressed=True)
            return PublicKey(key_bytes=pubkey_bytes)
        else:
            sk = ecdsa.SigningKey.from_string(self.key_bytes, curve=ecdsa.SECP256k1)
            vk = sk.get_verifying_key()
            # Manually compress the public key
            point = vk.pubkey.point
            prefix = b"\x02" if point.y() % 2 == 0 else b"\x03"
            pubkey_bytes = prefix + point.x().to_bytes(32, byteorder="big")
            return PublicKey(key_bytes=pubkey_bytes)

    def sign(self, message_hash: bytes) -> bytes:
        """
        Sign a 32-byte message hash.

        Args:
            message_hash: 32-byte hash to sign

        Returns:
            DER-encoded signature
        """
        if USING_COINCURVE:
            privkey = coincurve.PrivateKey(self.key_bytes)
            # Sign and return DER-encoded signature
            return privkey.sign(message_hash, hasher=None)
        else:
            sk = ecdsa.SigningKey.from_string(self.key_bytes, curve=ecdsa.SECP256k1)
            sig = sk.sign(message_hash, hashfunc=lambda x: x, sigencode=ecdsa.util.sigencode_der)
            return sig


@dataclass
class Wallet:
    """
    High-level wallet interface.

    A wallet holds a private key and provides convenient methods for
    address generation and transaction signing.
    """

    private_key: PrivateKey
    _public_key: Optional[PublicKey] = None
    _address: Optional[str] = None

    @classmethod
    def generate(cls) -> "Wallet":
        """Generate a new random wallet."""
        return cls(private_key=PrivateKey.generate())

    @classmethod
    def from_private_key_hex(cls, hex_string: str) -> "Wallet":
        """Create wallet from private key hex string."""
        return cls(private_key=PrivateKey.from_hex(hex_string))

    @property
    def public_key(self) -> PublicKey:
        """Get the public key (cached)."""
        if self._public_key is None:
            self._public_key = self.private_key.get_public_key()
        return self._public_key

    @property
    def address(self) -> str:
        """Get the address (cached)."""
        if self._address is None:
            self._address = self.public_key.to_address()
        return self._address

    @property
    def pubkey_hash(self) -> str:
        """Get the pubkey hash in hex (same as address in our simple format)."""
        return self.address

    def sign(self, message_hash: bytes) -> bytes:
        """Sign a message hash."""
        return self.private_key.sign(message_hash)

    def to_dict(self) -> dict:
        """Export wallet info as dictionary (for CLI display)."""
        return {
            "private_key": self.private_key.to_hex(),
            "public_key": self.public_key.to_hex(),
            "address": self.address,
        }


def verify_signature(
    message_hash: bytes,
    signature: bytes,
    pubkey_hex: str,
    expected_pubkey_hash: str,
) -> bool:
    """
    Verify a signature and check that the pubkey matches expected hash.

    This is the main verification function used during transaction validation.

    Args:
        message_hash: 32-byte hash that was signed
        signature: DER-encoded signature bytes
        pubkey_hex: Hex-encoded compressed public key
        expected_pubkey_hash: Expected HASH160 of the pubkey (hex)

    Returns:
        True if signature is valid AND pubkey hashes to expected value
    """
    try:
        pubkey = PublicKey.from_hex(pubkey_hex)

        # First verify that pubkey matches expected hash
        actual_hash = pubkey.to_address()
        if actual_hash != expected_pubkey_hash:
            return False

        # Then verify the signature
        return pubkey.verify(message_hash, signature)
    except Exception:
        return False
