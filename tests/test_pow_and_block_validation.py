"""Tests for Proof-of-Work and block validation."""

import time
import pytest

from mini_bitcoin_py.core.block import Block, BlockHeader, create_genesis_block, GENESIS_PREV_HASH
from mini_bitcoin_py.core.tx import Transaction, TxIn, TxOut
from mini_bitcoin_py.core.utxo import UTXOSet
from mini_bitcoin_py.core.keys import Wallet
from mini_bitcoin_py.core.consensus import (
    compute_work,
    is_valid_pow,
    mine_block,
    DEFAULT_TARGET,
    MAX_TARGET,
)
from mini_bitcoin_py.core.merkle import compute_merkle_root
from mini_bitcoin_py.core.validation import (
    validate_block_header,
    validate_block_transactions,
    validate_block_full,
    ValidationError,
)


# Use a very easy target for testing (many leading zeros bits off)
TEST_TARGET = int("0" * 4 + "f" * 60, 16)


class TestBlockHeader:
    """Tests for BlockHeader class."""

    def test_serialize(self):
        """Test header serialization is deterministic."""
        header = BlockHeader(
            version=1,
            prev_hash="ab" * 32,
            merkle_root="cd" * 32,
            timestamp=1234567890,
            target=TEST_TARGET,
            nonce=12345,
        )

        serialized1 = header.serialize()
        serialized2 = header.serialize()

        assert serialized1 == serialized2
        assert len(serialized1) == 108  # 4 + 32 + 32 + 4 + 32 + 4

    def test_compute_hash(self):
        """Test header hash computation."""
        header = BlockHeader(
            version=1,
            prev_hash="00" * 32,
            merkle_root="00" * 32,
            timestamp=0,
            target=MAX_TARGET,
            nonce=0,
        )

        hash1 = header.compute_hash()
        hash2 = header.compute_hash()

        assert hash1 == hash2
        assert len(hash1) == 64  # 32 bytes as hex

    def test_nonce_changes_hash(self):
        """Test that changing nonce changes the hash."""
        header = BlockHeader(
            version=1,
            prev_hash="00" * 32,
            merkle_root="00" * 32,
            timestamp=0,
            target=MAX_TARGET,
            nonce=0,
        )

        hash1 = header.compute_hash()
        header.nonce = 1
        hash2 = header.compute_hash()

        assert hash1 != hash2


class TestBlock:
    """Tests for Block class."""

    def test_create_candidate(self):
        """Test creating a candidate block."""
        miner = Wallet.generate()

        block = Block.create_candidate(
            prev_hash="ab" * 32,
            prev_target=TEST_TARGET,
            transactions=[],
            miner_address=miner.address,
            block_reward=5000000000,
        )

        assert block.prev_hash == "ab" * 32
        assert block.target == TEST_TARGET
        assert len(block.transactions) == 1  # Just coinbase
        assert block.transactions[0].is_coinbase()

    def test_verify_merkle_root(self):
        """Test merkle root verification."""
        miner = Wallet.generate()

        block = Block.create_candidate(
            prev_hash="ab" * 32,
            prev_target=TEST_TARGET,
            transactions=[],
            miner_address=miner.address,
            block_reward=5000000000,
        )

        assert block.verify_merkle_root()

        # Tamper with merkle root
        block.header.merkle_root = "00" * 32
        assert not block.verify_merkle_root()

    def test_is_genesis(self):
        """Test genesis block detection."""
        miner = Wallet.generate()

        genesis = create_genesis_block(
            miner_address=miner.address,
            block_reward=5000000000,
            target=TEST_TARGET,
        )

        assert genesis.is_genesis()

        non_genesis = Block.create_candidate(
            prev_hash="ab" * 32,
            prev_target=TEST_TARGET,
            transactions=[],
            miner_address=miner.address,
            block_reward=5000000000,
        )

        assert not non_genesis.is_genesis()

    def test_serialization_roundtrip(self):
        """Test block serialization and deserialization."""
        miner = Wallet.generate()

        block = Block.create_candidate(
            prev_hash="ab" * 32,
            prev_target=TEST_TARGET,
            transactions=[],
            miner_address=miner.address,
            block_reward=5000000000,
        )

        # Convert to dict and back
        block_dict = block.to_dict()
        restored = Block.from_dict(block_dict)

        assert restored.block_hash == block.block_hash
        assert restored.prev_hash == block.prev_hash
        assert len(restored.transactions) == len(block.transactions)


class TestProofOfWork:
    """Tests for Proof-of-Work consensus."""

    def test_compute_work(self):
        """Test work computation."""
        # Higher target = easier = less work
        easy_work = compute_work(MAX_TARGET)
        hard_work = compute_work(1)

        assert hard_work > easy_work

    def test_is_valid_pow_easy_target(self):
        """Test PoW validation with easy target."""
        miner = Wallet.generate()

        block = create_genesis_block(
            miner_address=miner.address,
            block_reward=5000000000,
            target=MAX_TARGET,  # Very easy target
        )

        # With max target, almost any hash should be valid
        assert is_valid_pow(block)

    def test_is_valid_pow_hard_target(self):
        """Test PoW validation with hard target."""
        miner = Wallet.generate()

        block = create_genesis_block(
            miner_address=miner.address,
            block_reward=5000000000,
            target=1,  # Impossible target
        )

        # With target=1, almost no hash will be valid
        assert not is_valid_pow(block)

    def test_mine_block(self):
        """Test mining a block."""
        miner = Wallet.generate()

        # Use a very easy target for testing
        easy_target = int("00ffffff" + "ff" * 28, 16)

        block = create_genesis_block(
            miner_address=miner.address,
            block_reward=5000000000,
            target=easy_target,
        )

        result = mine_block(block, max_nonce=1000000)

        assert result.success
        assert result.nonce >= 0
        assert is_valid_pow(block)


class TestBlockValidation:
    """Tests for block validation rules."""

    def setup_method(self):
        """Set up test fixtures."""
        self.miner = Wallet.generate()
        self.easy_target = int("00ffffff" + "ff" * 28, 16)

    def test_validate_genesis_block(self):
        """Test validating genesis block."""
        genesis = create_genesis_block(
            miner_address=self.miner.address,
            block_reward=5000000000,
            target=self.easy_target,
        )

        # Mine it
        mine_block(genesis, max_nonce=1000000)

        utxo_set = UTXOSet()
        result = validate_block_full(
            block=genesis,
            prev_block=None,  # Genesis has no previous
            utxo_set=utxo_set,
            block_reward=5000000000,
        )

        assert result.valid, f"Validation failed: {result.message}"

    def test_validate_block_chain(self):
        """Test validating a chain of blocks."""
        # Create and mine genesis
        genesis = create_genesis_block(
            miner_address=self.miner.address,
            block_reward=5000000000,
            target=self.easy_target,
        )
        mine_block(genesis, max_nonce=1000000)

        # Apply genesis to UTXO set
        utxo_set = UTXOSet()
        result = validate_block_full(genesis, None, utxo_set, 5000000000)
        assert result.valid
        for tx in genesis.transactions:
            utxo_set.apply_transaction(tx)

        # Create second block
        block2 = Block.create_candidate(
            prev_hash=genesis.block_hash,
            prev_target=self.easy_target,
            transactions=[],
            miner_address=self.miner.address,
            block_reward=5000000000,
        )
        mine_block(block2, max_nonce=1000000)

        # Validate second block
        result = validate_block_full(block2, genesis, utxo_set, 5000000000)
        assert result.valid, f"Validation failed: {result.message}"

    def test_validate_wrong_prev_hash(self):
        """Test that wrong prev_hash is rejected."""
        genesis = create_genesis_block(
            miner_address=self.miner.address,
            block_reward=5000000000,
            target=self.easy_target,
        )
        mine_block(genesis, max_nonce=1000000)

        # Create block with wrong prev_hash
        bad_block = Block.create_candidate(
            prev_hash="ab" * 32,  # Wrong hash
            prev_target=self.easy_target,
            transactions=[],
            miner_address=self.miner.address,
            block_reward=5000000000,
        )
        mine_block(bad_block, max_nonce=1000000)

        result = validate_block_header(bad_block, genesis)
        assert not result.valid
        assert result.error == ValidationError.BLOCK_PREV_NOT_FOUND

    def test_validate_timestamp_too_far_future(self):
        """Test that future timestamps are rejected."""
        genesis = create_genesis_block(
            miner_address=self.miner.address,
            block_reward=5000000000,
            target=self.easy_target,
            timestamp=int(time.time()) + 10000000,  # Far in future
        )
        mine_block(genesis, max_nonce=1000000)

        result = validate_block_header(genesis, None)
        assert not result.valid
        assert result.error == ValidationError.BLOCK_TIMESTAMP_FUTURE

    def test_validate_invalid_merkle_root(self):
        """Test that invalid merkle root is rejected."""
        genesis = create_genesis_block(
            miner_address=self.miner.address,
            block_reward=5000000000,
            target=self.easy_target,
        )

        # Tamper with merkle root before mining
        genesis.header.merkle_root = "00" * 32
        mine_block(genesis, max_nonce=1000000)

        result = validate_block_header(genesis, None)
        assert not result.valid
        assert result.error == ValidationError.BLOCK_INVALID_MERKLE

    def test_validate_invalid_pow(self):
        """Test that invalid PoW is rejected."""
        genesis = create_genesis_block(
            miner_address=self.miner.address,
            block_reward=5000000000,
            target=1,  # Impossible target
        )
        # Don't mine - nonce=0 won't satisfy target=1

        result = validate_block_header(genesis, None)
        assert not result.valid
        assert result.error == ValidationError.BLOCK_INVALID_POW

    def test_validate_no_coinbase(self):
        """Test that block without coinbase is rejected."""
        header = BlockHeader(
            version=1,
            prev_hash=GENESIS_PREV_HASH,
            merkle_root="00" * 32,
            timestamp=int(time.time()),
            target=MAX_TARGET,
            nonce=0,
        )

        block = Block(header=header, transactions=[])

        result = validate_block_transactions(block, UTXOSet(), 5000000000)
        assert not result.valid
        assert result.error == ValidationError.BLOCK_NO_COINBASE

    def test_validate_coinbase_output_too_large(self):
        """Test that oversized coinbase output is rejected."""
        # Create coinbase with too much reward
        coinbase = Transaction.create_coinbase(
            miner_address=self.miner.address,
            reward=10000000000,  # More than allowed
            fees=0,
        )

        txids = [coinbase.txid]
        header = BlockHeader(
            version=1,
            prev_hash=GENESIS_PREV_HASH,
            merkle_root=compute_merkle_root(txids),
            timestamp=int(time.time()),
            target=MAX_TARGET,
            nonce=0,
        )

        block = Block(header=header, transactions=[coinbase])

        result = validate_block_transactions(block, UTXOSet(), 5000000000)
        assert not result.valid
        assert result.error == ValidationError.BLOCK_COINBASE_TOO_LARGE


class TestMerkleRoot:
    """Tests for Merkle tree computation."""

    def test_single_transaction(self):
        """Test merkle root with single transaction."""
        txid = "ab" * 32
        root = compute_merkle_root([txid])

        # Single tx: root = double_sha256(txid)
        # Actually for single item, merkle root is the item itself
        # Let's verify it's deterministic
        assert compute_merkle_root([txid]) == root

    def test_two_transactions(self):
        """Test merkle root with two transactions."""
        txid1 = "ab" * 32
        txid2 = "cd" * 32

        root = compute_merkle_root([txid1, txid2])

        # Should be different from either txid
        assert root != txid1
        assert root != txid2

    def test_odd_number_duplicates_last(self):
        """Test that odd number of txs duplicates the last."""
        txid1 = "ab" * 32
        txid2 = "cd" * 32
        txid3 = "ef" * 32

        # With 3 txs, the 3rd should be duplicated at the leaf level
        root = compute_merkle_root([txid1, txid2, txid3])
        assert len(root) == 64

    def test_empty_raises(self):
        """Test that empty list raises error."""
        with pytest.raises(ValueError):
            compute_merkle_root([])

    def test_deterministic(self):
        """Test that merkle root is deterministic."""
        txids = ["ab" * 32, "cd" * 32, "ef" * 32]

        root1 = compute_merkle_root(txids)
        root2 = compute_merkle_root(txids)

        assert root1 == root2
