"""Tests for hashing functions."""

import pytest

from mini_pow_chain.core.hashing import sha256, double_sha256, hash160


class TestSHA256:
    """Tests for SHA256 function."""

    def test_sha256_empty(self):
        """Test SHA256 of empty string."""
        result = sha256(b"")
        expected = bytes.fromhex(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        assert result == expected

    def test_sha256_hello(self):
        """Test SHA256 of 'hello'."""
        result = sha256(b"hello")
        expected = bytes.fromhex(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )
        assert result == expected

    def test_sha256_from_hex_string(self):
        """Test SHA256 with hex string input."""
        # 'hello' in hex
        result = sha256("68656c6c6f")
        expected = bytes.fromhex(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )
        assert result == expected

    def test_sha256_deterministic(self):
        """Test that SHA256 is deterministic."""
        data = b"test data for hashing"
        assert sha256(data) == sha256(data)


class TestDoubleSHA256:
    """Tests for double SHA256 function."""

    def test_double_sha256_empty(self):
        """Test double SHA256 of empty string."""
        # SHA256(SHA256(""))
        result = double_sha256(b"")
        first_hash = sha256(b"")
        expected = sha256(first_hash)
        assert result == expected

    def test_double_sha256_hello(self):
        """Test double SHA256 of 'hello'."""
        result = double_sha256(b"hello")
        first_hash = sha256(b"hello")
        expected = sha256(first_hash)
        assert result == expected

    def test_double_sha256_bitcoin_genesis(self):
        """Test double SHA256 produces 32 bytes."""
        result = double_sha256(b"The Times 03/Jan/2009 Chancellor on brink of second bailout for banks")
        assert len(result) == 32

    def test_double_sha256_deterministic(self):
        """Test that double SHA256 is deterministic."""
        data = b"blockchain data"
        assert double_sha256(data) == double_sha256(data)


class TestHash160:
    """Tests for HASH160 (RIPEMD160(SHA256)) function."""

    def test_hash160_empty(self):
        """Test HASH160 of empty string."""
        result = hash160(b"")
        assert len(result) == 20  # RIPEMD160 produces 20 bytes

    def test_hash160_pubkey_like(self):
        """Test HASH160 with pubkey-like input."""
        # 33-byte compressed pubkey format
        fake_pubkey = b"\x02" + b"\x00" * 32
        result = hash160(fake_pubkey)
        assert len(result) == 20

    def test_hash160_from_hex(self):
        """Test HASH160 with hex string input."""
        # Same input as bytes vs hex should produce same result
        data = b"\x02" + b"\xab" * 32
        hex_data = data.hex()

        result_bytes = hash160(data)
        result_hex = hash160(hex_data)

        assert result_bytes == result_hex

    def test_hash160_deterministic(self):
        """Test that HASH160 is deterministic."""
        data = b"public key data"
        assert hash160(data) == hash160(data)


class TestHashingIntegration:
    """Integration tests for hashing functions."""

    def test_hash_chain(self):
        """Test chaining hash functions."""
        data = b"test"

        # hash160 is RIPEMD160(SHA256(data))
        h160 = hash160(data)
        assert len(h160) == 20

        # double_sha256 is SHA256(SHA256(data))
        ds256 = double_sha256(data)
        assert len(ds256) == 32

        # They should be different
        assert h160 != ds256[:20]

    def test_hash_uniqueness(self):
        """Test that different inputs produce different hashes."""
        inputs = [b"a", b"b", b"ab", b"ba", b""]

        hashes = [sha256(i) for i in inputs]
        assert len(set(hashes)) == len(inputs)

        double_hashes = [double_sha256(i) for i in inputs]
        assert len(set(double_hashes)) == len(inputs)
