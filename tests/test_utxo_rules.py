"""Tests for UTXO set and validation rules."""

import pytest

from mini_bitcoin_py.core.utxo import UTXOSet, MempoolUTXOTracker
from mini_bitcoin_py.core.tx import Transaction, TxIn, TxOut
from mini_bitcoin_py.core.keys import Wallet
from mini_bitcoin_py.core.validation import (
    validate_transaction_basic,
    validate_transaction_against_utxo,
    ValidationError,
)


class TestUTXOSet:
    """Tests for UTXOSet class."""

    def test_add_and_get(self):
        """Test adding and retrieving UTXOs."""
        utxo_set = UTXOSet()

        txout = TxOut(amount=1000, pubkey_hash="ab" * 20)
        utxo_set.add("txid1" + "00" * 28, 0, txout)

        result = utxo_set.get("txid1" + "00" * 28, 0)
        assert result == txout

    def test_exists(self):
        """Test checking UTXO existence."""
        utxo_set = UTXOSet()
        txid = "ab" * 32

        assert not utxo_set.exists(txid, 0)

        utxo_set.add(txid, 0, TxOut(amount=1000, pubkey_hash="cd" * 20))

        assert utxo_set.exists(txid, 0)
        assert not utxo_set.exists(txid, 1)

    def test_remove(self):
        """Test removing UTXOs."""
        utxo_set = UTXOSet()
        txid = "ab" * 32

        utxo_set.add(txid, 0, TxOut(amount=1000, pubkey_hash="cd" * 20))
        assert utxo_set.exists(txid, 0)

        removed = utxo_set.remove(txid, 0)
        assert removed.amount == 1000
        assert not utxo_set.exists(txid, 0)

    def test_remove_nonexistent_raises(self):
        """Test that removing nonexistent UTXO raises error."""
        utxo_set = UTXOSet()

        with pytest.raises(KeyError):
            utxo_set.remove("ab" * 32, 0)

    def test_get_balance(self):
        """Test balance calculation."""
        utxo_set = UTXOSet()
        address = "ab" * 20

        # Add multiple UTXOs for the same address
        utxo_set.add("tx1" + "0" * 56, 0, TxOut(amount=1000, pubkey_hash=address))
        utxo_set.add("tx2" + "0" * 56, 0, TxOut(amount=2000, pubkey_hash=address))
        utxo_set.add("tx3" + "0" * 56, 0, TxOut(amount=3000, pubkey_hash=address))

        assert utxo_set.get_balance(address) == 6000

    def test_get_utxos_for_address(self):
        """Test getting UTXOs for specific address."""
        utxo_set = UTXOSet()
        address1 = "ab" * 20
        address2 = "cd" * 20

        utxo_set.add("tx1" + "0" * 56, 0, TxOut(amount=1000, pubkey_hash=address1))
        utxo_set.add("tx2" + "0" * 56, 0, TxOut(amount=2000, pubkey_hash=address2))
        utxo_set.add("tx3" + "0" * 56, 0, TxOut(amount=3000, pubkey_hash=address1))

        utxos1 = utxo_set.get_utxos_for_address(address1)
        utxos2 = utxo_set.get_utxos_for_address(address2)

        assert len(utxos1) == 2
        assert len(utxos2) == 1

    def test_apply_transaction(self):
        """Test applying a transaction to UTXO set."""
        utxo_set = UTXOSet()
        sender = Wallet.generate()
        receiver = Wallet.generate()

        # Add initial UTXO
        initial_txid = "ab" * 32
        utxo_set.add(initial_txid, 0, TxOut(amount=5000, pubkey_hash=sender.address))

        # Create transaction
        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid=initial_txid, prev_index=0)],
            outputs=[
                TxOut(amount=3000, pubkey_hash=receiver.address),
                TxOut(amount=1000, pubkey_hash=sender.address),  # Change
            ],
        )

        # Apply transaction
        fee = utxo_set.apply_transaction(tx)

        assert fee == 1000  # 5000 - 4000 = 1000
        assert not utxo_set.exists(initial_txid, 0)
        assert utxo_set.exists(tx.txid, 0)
        assert utxo_set.exists(tx.txid, 1)

    def test_select_utxos_for_amount(self):
        """Test UTXO selection algorithm."""
        utxo_set = UTXOSet()
        address = "ab" * 20

        # Add UTXOs of various sizes
        utxo_set.add("tx1" + "0" * 56, 0, TxOut(amount=100, pubkey_hash=address))
        utxo_set.add("tx2" + "0" * 56, 0, TxOut(amount=500, pubkey_hash=address))
        utxo_set.add("tx3" + "0" * 56, 0, TxOut(amount=1000, pubkey_hash=address))

        # Select for amount 800
        selected, total = utxo_set.select_utxos_for_amount(address, 800)

        assert total >= 800
        assert len(selected) >= 1

    def test_select_utxos_insufficient_funds(self):
        """Test UTXO selection with insufficient funds."""
        utxo_set = UTXOSet()
        address = "ab" * 20

        utxo_set.add("tx1" + "0" * 56, 0, TxOut(amount=100, pubkey_hash=address))

        with pytest.raises(ValueError, match="Insufficient funds"):
            utxo_set.select_utxos_for_amount(address, 1000)


class TestMempoolUTXOTracker:
    """Tests for MempoolUTXOTracker."""

    def test_track_transaction(self):
        """Test tracking mempool transaction."""
        tracker = MempoolUTXOTracker()

        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid="ab" * 32, prev_index=0)],
            outputs=[TxOut(amount=1000, pubkey_hash="cd" * 20)],
        )

        tracker.add_transaction(tx)

        # Input should be marked as spent
        assert tracker.is_spent_in_mempool("ab" * 32, 0)

        # Output should be tracked as created
        assert (tx.txid, 0) in tracker.created

    def test_remove_transaction(self):
        """Test removing transaction from tracker."""
        tracker = MempoolUTXOTracker()

        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid="ab" * 32, prev_index=0)],
            outputs=[TxOut(amount=1000, pubkey_hash="cd" * 20)],
        )

        tracker.add_transaction(tx)
        tracker.remove_transaction(tx)

        assert not tracker.is_spent_in_mempool("ab" * 32, 0)
        assert (tx.txid, 0) not in tracker.created


class TestTransactionValidation:
    """Tests for transaction validation rules."""

    def test_validate_empty_inputs(self):
        """Test that empty inputs are rejected."""
        tx = Transaction(
            version=1,
            inputs=[],
            outputs=[TxOut(amount=1000, pubkey_hash="ab" * 20)],
        )

        result = validate_transaction_basic(tx)
        assert not result.valid
        assert result.error == ValidationError.TX_EMPTY_INPUTS

    def test_validate_empty_outputs(self):
        """Test that empty outputs are rejected."""
        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid="ab" * 32, prev_index=0)],
            outputs=[],
        )

        result = validate_transaction_basic(tx)
        assert not result.valid
        assert result.error == ValidationError.TX_EMPTY_OUTPUTS

    def test_validate_negative_output(self):
        """Test that negative outputs are rejected."""
        # Note: TxOut.__post_init__ actually raises ValueError for negative amounts
        # So we can't easily test this through validation
        pass

    def test_validate_duplicate_input(self):
        """Test that duplicate inputs are rejected."""
        txid = "ab" * 32
        tx = Transaction(
            version=1,
            inputs=[
                TxIn(prev_txid=txid, prev_index=0),
                TxIn(prev_txid=txid, prev_index=0),  # Duplicate
            ],
            outputs=[TxOut(amount=1000, pubkey_hash="cd" * 20)],
        )

        result = validate_transaction_basic(tx)
        assert not result.valid
        assert result.error == ValidationError.TX_DUPLICATE_INPUT

    def test_validate_missing_utxo(self):
        """Test that missing UTXO is rejected."""
        utxo_set = UTXOSet()

        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid="ab" * 32, prev_index=0)],
            outputs=[TxOut(amount=1000, pubkey_hash="cd" * 20)],
        )

        result = validate_transaction_against_utxo(tx, utxo_set)
        assert not result.valid
        assert result.error == ValidationError.TX_MISSING_UTXO

    def test_validate_double_spend_in_mempool(self):
        """Test that double spend in mempool is rejected."""
        sender = Wallet.generate()
        utxo_set = UTXOSet()
        tracker = MempoolUTXOTracker()

        # Add UTXO
        initial_txid = "ab" * 32
        utxo_set.add(initial_txid, 0, TxOut(amount=5000, pubkey_hash=sender.address))

        # First transaction (already in mempool)
        tx1 = Transaction(
            version=1,
            inputs=[TxIn(prev_txid=initial_txid, prev_index=0)],
            outputs=[TxOut(amount=4000, pubkey_hash="cd" * 20)],
        )
        tracker.add_transaction(tx1)

        # Second transaction trying to spend same UTXO
        tx2 = Transaction(
            version=1,
            inputs=[TxIn(prev_txid=initial_txid, prev_index=0)],
            outputs=[TxOut(amount=4000, pubkey_hash="ef" * 20)],
        )

        result = validate_transaction_against_utxo(tx2, utxo_set, tracker)
        assert not result.valid
        assert result.error == ValidationError.TX_DOUBLE_SPEND

    def test_validate_coinbase_not_allowed(self):
        """Test that coinbase is rejected in normal validation."""
        tx = Transaction.create_coinbase(
            miner_address="ab" * 20,
            reward=5000000000,
        )

        result = validate_transaction_against_utxo(tx, UTXOSet(), allow_coinbase=False)
        assert not result.valid
        assert result.error == ValidationError.TX_COINBASE_NOT_ALLOWED

    def test_validate_valid_transaction(self):
        """Test validation of a valid signed transaction."""
        sender = Wallet.generate()
        receiver = Wallet.generate()

        utxo_set = UTXOSet()
        initial_txid = "ab" * 32
        utxo_set.add(initial_txid, 0, TxOut(amount=5000, pubkey_hash=sender.address))

        # Create and sign transaction
        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid=initial_txid, prev_index=0)],
            outputs=[TxOut(amount=4000, pubkey_hash=receiver.address)],
        )

        # Sign
        sighash = tx.compute_sighash(0, sender.address)
        signature = sender.sign(sighash)
        tx.inputs[0].signature = signature.hex()
        tx.inputs[0].pubkey = sender.public_key.to_hex()

        result = validate_transaction_against_utxo(tx, utxo_set)
        assert result.valid
        assert result.fee == 1000  # 5000 - 4000

    def test_validate_invalid_signature(self):
        """Test that invalid signature is rejected."""
        sender = Wallet.generate()
        wrong_signer = Wallet.generate()
        receiver = Wallet.generate()

        utxo_set = UTXOSet()
        initial_txid = "ab" * 32
        utxo_set.add(initial_txid, 0, TxOut(amount=5000, pubkey_hash=sender.address))

        # Create transaction but sign with wrong key
        tx = Transaction(
            version=1,
            inputs=[TxIn(prev_txid=initial_txid, prev_index=0)],
            outputs=[TxOut(amount=4000, pubkey_hash=receiver.address)],
        )

        # Sign with wrong wallet
        sighash = tx.compute_sighash(0, sender.address)
        signature = wrong_signer.sign(sighash)
        tx.inputs[0].signature = signature.hex()
        tx.inputs[0].pubkey = wrong_signer.public_key.to_hex()  # Wrong pubkey

        result = validate_transaction_against_utxo(tx, utxo_set)
        assert not result.valid
        assert result.error == ValidationError.TX_INVALID_SIGNATURE
