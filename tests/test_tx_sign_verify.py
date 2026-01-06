"""Tests for transaction signing and verification."""

import pytest

from mini_pow_chain.core.keys import (
    PrivateKey,
    PublicKey,
    Wallet,
    verify_signature,
)
from mini_pow_chain.core.tx import Transaction, TxIn, TxOut, COINBASE_TXID, COINBASE_INDEX
from mini_pow_chain.core.hashing import double_sha256


class TestPrivateKey:
    """Tests for PrivateKey class."""

    def test_generate(self):
        """Test private key generation."""
        key = PrivateKey.generate()
        assert len(key.key_bytes) == 32

    def test_from_hex(self):
        """Test private key from hex."""
        hex_key = "0" * 63 + "1"  # Valid 32-byte key
        key = PrivateKey.from_hex(hex_key)
        assert key.to_hex() == hex_key

    def test_get_public_key(self):
        """Test deriving public key."""
        key = PrivateKey.generate()
        pubkey = key.get_public_key()

        # Compressed public key is 33 bytes
        assert len(pubkey.key_bytes) == 33
        # Starts with 02 or 03
        assert pubkey.key_bytes[0] in (0x02, 0x03)

    def test_sign(self):
        """Test signing a message."""
        key = PrivateKey.generate()
        message_hash = double_sha256(b"test message")

        signature = key.sign(message_hash)

        # DER signature should be reasonable length
        assert len(signature) >= 68
        assert len(signature) <= 72


class TestPublicKey:
    """Tests for PublicKey class."""

    def test_from_hex(self):
        """Test public key from hex."""
        # Generate a key pair first
        privkey = PrivateKey.generate()
        pubkey = privkey.get_public_key()

        # Convert to hex and back
        hex_key = pubkey.to_hex()
        restored = PublicKey.from_hex(hex_key)

        assert restored.key_bytes == pubkey.key_bytes

    def test_to_address(self):
        """Test address derivation."""
        privkey = PrivateKey.generate()
        pubkey = privkey.get_public_key()

        address = pubkey.to_address()

        # Address is hex-encoded HASH160 (20 bytes = 40 hex chars)
        assert len(address) == 40
        # Should be valid hex
        bytes.fromhex(address)

    def test_verify_valid_signature(self):
        """Test verifying a valid signature."""
        privkey = PrivateKey.generate()
        pubkey = privkey.get_public_key()

        message_hash = double_sha256(b"test message")
        signature = privkey.sign(message_hash)

        assert pubkey.verify(message_hash, signature) is True

    def test_verify_invalid_signature(self):
        """Test verifying an invalid signature."""
        privkey = PrivateKey.generate()
        pubkey = privkey.get_public_key()

        message_hash = double_sha256(b"test message")
        wrong_hash = double_sha256(b"different message")
        signature = privkey.sign(message_hash)

        # Signature doesn't match the message
        assert pubkey.verify(wrong_hash, signature) is False

    def test_verify_wrong_pubkey(self):
        """Test verifying with wrong public key."""
        privkey1 = PrivateKey.generate()
        privkey2 = PrivateKey.generate()
        pubkey2 = privkey2.get_public_key()

        message_hash = double_sha256(b"test message")
        signature = privkey1.sign(message_hash)

        # Signature from privkey1 shouldn't verify with pubkey2
        assert pubkey2.verify(message_hash, signature) is False


class TestWallet:
    """Tests for Wallet class."""

    def test_generate(self):
        """Test wallet generation."""
        wallet = Wallet.generate()

        assert wallet.private_key is not None
        assert len(wallet.address) == 40

    def test_from_private_key_hex(self):
        """Test wallet from private key hex."""
        privkey = PrivateKey.generate()
        wallet = Wallet.from_private_key_hex(privkey.to_hex())

        assert wallet.address == privkey.get_public_key().to_address()

    def test_to_dict(self):
        """Test wallet serialization."""
        wallet = Wallet.generate()
        info = wallet.to_dict()

        assert "private_key" in info
        assert "public_key" in info
        assert "address" in info
        assert len(info["private_key"]) == 64
        assert len(info["public_key"]) == 66
        assert len(info["address"]) == 40

    def test_sign(self):
        """Test wallet signing."""
        wallet = Wallet.generate()
        message_hash = double_sha256(b"test")

        signature = wallet.sign(message_hash)

        # Verify with wallet's public key
        assert wallet.public_key.verify(message_hash, signature)


class TestVerifySignature:
    """Tests for the verify_signature function."""

    def test_verify_valid(self):
        """Test verifying a valid signature with correct pubkey hash."""
        wallet = Wallet.generate()
        message_hash = double_sha256(b"test message")
        signature = wallet.sign(message_hash)

        result = verify_signature(
            message_hash=message_hash,
            signature=signature,
            pubkey_hex=wallet.public_key.to_hex(),
            expected_pubkey_hash=wallet.address,
        )

        assert result is True

    def test_verify_wrong_pubkey_hash(self):
        """Test that verification fails with wrong pubkey hash."""
        wallet = Wallet.generate()
        other_wallet = Wallet.generate()

        message_hash = double_sha256(b"test message")
        signature = wallet.sign(message_hash)

        result = verify_signature(
            message_hash=message_hash,
            signature=signature,
            pubkey_hex=wallet.public_key.to_hex(),
            expected_pubkey_hash=other_wallet.address,  # Wrong hash
        )

        assert result is False

    def test_verify_wrong_signature(self):
        """Test that verification fails with wrong signature."""
        wallet = Wallet.generate()
        message_hash = double_sha256(b"test message")
        wrong_hash = double_sha256(b"wrong message")
        signature = wallet.sign(wrong_hash)

        result = verify_signature(
            message_hash=message_hash,
            signature=signature,
            pubkey_hex=wallet.public_key.to_hex(),
            expected_pubkey_hash=wallet.address,
        )

        assert result is False


class TestTransactionSigning:
    """Tests for transaction signing."""

    def test_sighash_computation(self):
        """Test sighash preimage computation."""
        wallet = Wallet.generate()

        tx = Transaction(
            version=1,
            inputs=[
                TxIn(
                    prev_txid="00" * 32,
                    prev_index=0,
                )
            ],
            outputs=[
                TxOut(
                    amount=1000,
                    pubkey_hash=wallet.address,
                )
            ],
        )

        # Compute sighash
        sighash = tx.compute_sighash(0, wallet.address)

        assert len(sighash) == 32
        # Should be deterministic
        assert sighash == tx.compute_sighash(0, wallet.address)

    def test_sign_and_verify_transaction(self):
        """Test signing and verifying a complete transaction."""
        sender = Wallet.generate()
        receiver = Wallet.generate()

        # Create a transaction spending from sender to receiver
        tx = Transaction(
            version=1,
            inputs=[
                TxIn(
                    prev_txid="ab" * 32,  # Fake previous txid
                    prev_index=0,
                )
            ],
            outputs=[
                TxOut(
                    amount=1000,
                    pubkey_hash=receiver.address,
                )
            ],
        )

        # Sign the input
        sighash = tx.compute_sighash(0, sender.address)
        signature = sender.sign(sighash)

        # Update input with signature and pubkey
        tx.inputs[0].signature = signature.hex()
        tx.inputs[0].pubkey = sender.public_key.to_hex()

        # Verify
        result = verify_signature(
            message_hash=sighash,
            signature=signature,
            pubkey_hex=tx.inputs[0].pubkey,
            expected_pubkey_hash=sender.address,
        )

        assert result is True

    def test_txid_excludes_signature(self):
        """Test that txid doesn't include signature."""
        wallet = Wallet.generate()

        tx = Transaction(
            version=1,
            inputs=[
                TxIn(
                    prev_txid="ab" * 32,
                    prev_index=0,
                )
            ],
            outputs=[
                TxOut(
                    amount=1000,
                    pubkey_hash=wallet.address,
                )
            ],
        )

        # Get txid before signing
        txid_before = tx.txid

        # Sign
        sighash = tx.compute_sighash(0, wallet.address)
        signature = wallet.sign(sighash)
        tx.inputs[0].signature = signature.hex()
        tx.inputs[0].pubkey = wallet.public_key.to_hex()

        # txid should be the same (signatures excluded)
        tx.invalidate_txid_cache()
        txid_after = tx.txid

        assert txid_before == txid_after

    def test_coinbase_transaction(self):
        """Test coinbase transaction creation."""
        miner = Wallet.generate()

        tx = Transaction.create_coinbase(
            miner_address=miner.address,
            reward=5000000000,
            fees=1000,
        )

        assert tx.is_coinbase()
        assert len(tx.inputs) == 1
        assert tx.inputs[0].prev_txid == COINBASE_TXID
        assert tx.inputs[0].prev_index == COINBASE_INDEX
        assert tx.outputs[0].amount == 5000001000
        assert tx.outputs[0].pubkey_hash == miner.address
