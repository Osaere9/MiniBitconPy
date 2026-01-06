"""
Transaction and Block validation rules.

Transaction Validation:
1. Non-empty inputs and outputs
2. All input amounts positive, output amounts non-negative
3. Sum of inputs >= sum of outputs
4. No double-spends (each input references unspent UTXO)
5. Valid signatures (signature matches pubkey, pubkey hashes to UTXO's pubkey_hash)
6. Coinbase transactions: exactly one input with prev_txid=00*32, prev_index=0xFFFFFFFF

Block Validation:
1. Previous block exists (or genesis)
2. Timestamp not too far in future (allow MAX_FUTURE_TIME drift)
3. Merkle root matches computed value
4. PoW is valid (block_hash <= target)
5. Coinbase is first transaction, exactly one coinbase per block
6. All transactions valid
7. Coinbase output <= block_reward + fees
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Tuple, Dict
import time

from mini_pow_chain.core.tx import Transaction, COINBASE_TXID, COINBASE_INDEX
from mini_pow_chain.core.block import Block, GENESIS_PREV_HASH
from mini_pow_chain.core.utxo import UTXOSet, MempoolUTXOTracker, UTXOKey
from mini_pow_chain.core.keys import verify_signature
from mini_pow_chain.core.hashing import double_sha256


# Maximum time in the future a block timestamp can be (2 hours)
MAX_FUTURE_TIME = 2 * 60 * 60


class ValidationError(Enum):
    """Types of validation errors."""

    # Transaction errors
    TX_EMPTY_INPUTS = "Transaction has no inputs"
    TX_EMPTY_OUTPUTS = "Transaction has no outputs"
    TX_NEGATIVE_OUTPUT = "Transaction output has negative amount"
    TX_INSUFFICIENT_INPUT = "Input sum is less than output sum"
    TX_MISSING_UTXO = "Referenced UTXO does not exist"
    TX_DOUBLE_SPEND = "UTXO already spent"
    TX_INVALID_SIGNATURE = "Invalid signature"
    TX_PUBKEY_MISMATCH = "Public key does not match UTXO pubkey_hash"
    TX_COINBASE_NOT_ALLOWED = "Coinbase transaction not allowed in mempool"
    TX_INVALID_COINBASE = "Invalid coinbase transaction structure"
    TX_DUPLICATE_INPUT = "Duplicate input in transaction"

    # Block errors
    BLOCK_PREV_NOT_FOUND = "Previous block not found"
    BLOCK_TIMESTAMP_FUTURE = "Block timestamp too far in future"
    BLOCK_INVALID_MERKLE = "Merkle root does not match"
    BLOCK_INVALID_POW = "Proof of work is invalid"
    BLOCK_NO_COINBASE = "Block has no coinbase transaction"
    BLOCK_MULTIPLE_COINBASE = "Block has multiple coinbase transactions"
    BLOCK_COINBASE_NOT_FIRST = "Coinbase must be first transaction"
    BLOCK_INVALID_TX = "Block contains invalid transaction"
    BLOCK_COINBASE_TOO_LARGE = "Coinbase output exceeds allowed amount"
    BLOCK_DOUBLE_SPEND = "Double spend within block"


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    valid: bool
    error: Optional[ValidationError] = None
    message: Optional[str] = None
    fee: int = 0  # Total fee for valid transactions

    @classmethod
    def success(cls, fee: int = 0) -> "ValidationResult":
        return cls(valid=True, fee=fee)

    @classmethod
    def failure(cls, error: ValidationError, message: str = "") -> "ValidationResult":
        return cls(valid=False, error=error, message=message)


def validate_transaction_basic(tx: Transaction) -> ValidationResult:
    """
    Basic transaction validation (structure only, no UTXO checks).

    Checks:
    - Has inputs and outputs
    - Output amounts are non-negative
    - No duplicate inputs
    """
    # Check for empty inputs/outputs
    if not tx.inputs:
        return ValidationResult.failure(ValidationError.TX_EMPTY_INPUTS)
    if not tx.outputs:
        return ValidationResult.failure(ValidationError.TX_EMPTY_OUTPUTS)

    # Check output amounts
    for i, out in enumerate(tx.outputs):
        if out.amount < 0:
            return ValidationResult.failure(
                ValidationError.TX_NEGATIVE_OUTPUT,
                f"Output {i} has negative amount: {out.amount}",
            )

    # Check for duplicate inputs
    seen_inputs = set()
    for inp in tx.inputs:
        key = (inp.prev_txid, inp.prev_index)
        if key in seen_inputs:
            return ValidationResult.failure(
                ValidationError.TX_DUPLICATE_INPUT,
                f"Duplicate input: {inp.prev_txid}:{inp.prev_index}",
            )
        seen_inputs.add(key)

    return ValidationResult.success()


def validate_coinbase(tx: Transaction, block_reward: int, max_fees: int = 0) -> ValidationResult:
    """
    Validate a coinbase transaction.

    Args:
        tx: The coinbase transaction
        block_reward: Expected block reward
        max_fees: Maximum allowed fees (from other block transactions)
    """
    if not tx.is_coinbase():
        return ValidationResult.failure(
            ValidationError.TX_INVALID_COINBASE,
            "Transaction is not a coinbase",
        )

    # Coinbase must have exactly one input
    if len(tx.inputs) != 1:
        return ValidationResult.failure(
            ValidationError.TX_INVALID_COINBASE,
            f"Coinbase must have 1 input, has {len(tx.inputs)}",
        )

    inp = tx.inputs[0]
    if inp.prev_txid != COINBASE_TXID or inp.prev_index != COINBASE_INDEX:
        return ValidationResult.failure(
            ValidationError.TX_INVALID_COINBASE,
            "Coinbase input not properly formatted",
        )

    # Check total output doesn't exceed reward + fees
    total_output = tx.total_output_amount()
    max_allowed = block_reward + max_fees
    if total_output > max_allowed:
        return ValidationResult.failure(
            ValidationError.BLOCK_COINBASE_TOO_LARGE,
            f"Coinbase output {total_output} exceeds max {max_allowed}",
        )

    return ValidationResult.success()


def validate_transaction_against_utxo(
    tx: Transaction,
    utxo_set: UTXOSet,
    mempool_tracker: Optional[MempoolUTXOTracker] = None,
    allow_coinbase: bool = False,
) -> ValidationResult:
    """
    Full transaction validation against UTXO set.

    Args:
        tx: Transaction to validate
        utxo_set: Current UTXO set
        mempool_tracker: Optional tracker for mempool double-spend detection
        allow_coinbase: Whether to allow coinbase transactions

    Returns:
        ValidationResult with validity and fee
    """
    # Basic validation first
    basic = validate_transaction_basic(tx)
    if not basic.valid:
        return basic

    # Reject coinbase if not allowed
    if tx.is_coinbase():
        if not allow_coinbase:
            return ValidationResult.failure(ValidationError.TX_COINBASE_NOT_ALLOWED)
        return ValidationResult.success()  # Coinbase validated separately

    input_sum = 0

    # Validate each input
    for idx, inp in enumerate(tx.inputs):
        # Check for mempool double-spend
        if mempool_tracker and mempool_tracker.is_spent_in_mempool(
            inp.prev_txid, inp.prev_index
        ):
            return ValidationResult.failure(
                ValidationError.TX_DOUBLE_SPEND,
                f"Input {idx}: UTXO already spent in mempool",
            )

        # Check UTXO exists
        utxo = utxo_set.get(inp.prev_txid, inp.prev_index)
        if utxo is None:
            # Check if it's a mempool-created UTXO
            if mempool_tracker:
                utxo = mempool_tracker.created.get((inp.prev_txid, inp.prev_index))
            if utxo is None:
                return ValidationResult.failure(
                    ValidationError.TX_MISSING_UTXO,
                    f"Input {idx}: UTXO not found {inp.prev_txid}:{inp.prev_index}",
                )

        input_sum += utxo.amount

        # Compute sighash for this input
        sighash = tx.compute_sighash(idx, utxo.pubkey_hash)

        # Verify signature
        try:
            sig_bytes = bytes.fromhex(inp.signature)
        except ValueError:
            return ValidationResult.failure(
                ValidationError.TX_INVALID_SIGNATURE,
                f"Input {idx}: Invalid signature hex",
            )

        if not verify_signature(sighash, sig_bytes, inp.pubkey, utxo.pubkey_hash):
            return ValidationResult.failure(
                ValidationError.TX_INVALID_SIGNATURE,
                f"Input {idx}: Signature verification failed",
            )

    # Check input sum >= output sum
    output_sum = tx.total_output_amount()
    if input_sum < output_sum:
        return ValidationResult.failure(
            ValidationError.TX_INSUFFICIENT_INPUT,
            f"Input sum {input_sum} < output sum {output_sum}",
        )

    fee = input_sum - output_sum
    return ValidationResult.success(fee=fee)


def validate_block_header(
    block: Block,
    prev_block: Optional[Block],
    current_time: Optional[int] = None,
) -> ValidationResult:
    """
    Validate block header (without transaction validation).

    Args:
        block: Block to validate
        prev_block: Previous block (None for genesis)
        current_time: Current time for timestamp check (defaults to now)
    """
    if current_time is None:
        current_time = int(time.time())

    # Check previous block
    if block.prev_hash == GENESIS_PREV_HASH:
        # Genesis block - prev_block should be None
        if prev_block is not None:
            return ValidationResult.failure(
                ValidationError.BLOCK_PREV_NOT_FOUND,
                "Genesis block should not have a previous block",
            )
    else:
        # Non-genesis - must have previous block
        if prev_block is None:
            return ValidationResult.failure(
                ValidationError.BLOCK_PREV_NOT_FOUND,
                f"Previous block not found: {block.prev_hash}",
            )
        if prev_block.block_hash != block.prev_hash:
            return ValidationResult.failure(
                ValidationError.BLOCK_PREV_NOT_FOUND,
                f"Previous block hash mismatch",
            )

    # Check timestamp not too far in future
    if block.timestamp > current_time + MAX_FUTURE_TIME:
        return ValidationResult.failure(
            ValidationError.BLOCK_TIMESTAMP_FUTURE,
            f"Timestamp {block.timestamp} too far in future (now: {current_time})",
        )

    # Check merkle root
    if not block.verify_merkle_root():
        return ValidationResult.failure(
            ValidationError.BLOCK_INVALID_MERKLE,
            f"Merkle root mismatch",
        )

    # Check PoW
    if not block.is_valid_pow():
        return ValidationResult.failure(
            ValidationError.BLOCK_INVALID_POW,
            f"PoW invalid: hash {block.block_hash} > target {hex(block.target)}",
        )

    return ValidationResult.success()


def validate_block_transactions(
    block: Block,
    utxo_set: UTXOSet,
    block_reward: int,
) -> ValidationResult:
    """
    Validate all transactions in a block.

    Args:
        block: Block to validate
        utxo_set: UTXO set (state before this block)
        block_reward: Expected block reward
    """
    if not block.transactions:
        return ValidationResult.failure(
            ValidationError.BLOCK_NO_COINBASE,
            "Block has no transactions",
        )

    # First transaction must be coinbase
    coinbase = block.transactions[0]
    if not coinbase.is_coinbase():
        return ValidationResult.failure(
            ValidationError.BLOCK_COINBASE_NOT_FIRST,
            "First transaction is not coinbase",
        )

    # No other transaction can be coinbase
    for i, tx in enumerate(block.transactions[1:], 1):
        if tx.is_coinbase():
            return ValidationResult.failure(
                ValidationError.BLOCK_MULTIPLE_COINBASE,
                f"Transaction {i} is coinbase",
            )

    # Track spent UTXOs within this block
    spent_in_block: set[UTXOKey] = set()
    total_fees = 0

    # Create a temporary UTXO tracker for block transactions
    temp_utxo = utxo_set.copy()

    # Validate non-coinbase transactions
    for i, tx in enumerate(block.transactions[1:], 1):
        # Check for double-spend within block
        for inp in tx.inputs:
            key = (inp.prev_txid, inp.prev_index)
            if key in spent_in_block:
                return ValidationResult.failure(
                    ValidationError.BLOCK_DOUBLE_SPEND,
                    f"Transaction {i} double-spends within block",
                )

        # Validate transaction
        result = validate_transaction_against_utxo(tx, temp_utxo, allow_coinbase=False)
        if not result.valid:
            return ValidationResult.failure(
                ValidationError.BLOCK_INVALID_TX,
                f"Transaction {i} ({tx.txid[:16]}...): {result.error.value if result.error else ''} - {result.message}",
            )

        total_fees += result.fee

        # Mark inputs as spent
        for inp in tx.inputs:
            spent_in_block.add((inp.prev_txid, inp.prev_index))

        # Apply transaction to temp UTXO
        temp_utxo.apply_transaction(tx)

    # Validate coinbase amount
    coinbase_result = validate_coinbase(coinbase, block_reward, total_fees)
    if not coinbase_result.valid:
        return coinbase_result

    return ValidationResult.success(fee=total_fees)


def validate_block_full(
    block: Block,
    prev_block: Optional[Block],
    utxo_set: UTXOSet,
    block_reward: int,
    current_time: Optional[int] = None,
) -> ValidationResult:
    """
    Full block validation.

    Args:
        block: Block to validate
        prev_block: Previous block (None for genesis)
        utxo_set: UTXO set (state before this block)
        block_reward: Expected block reward
        current_time: Current time for timestamp check
    """
    # Header validation
    header_result = validate_block_header(block, prev_block, current_time)
    if not header_result.valid:
        return header_result

    # Transaction validation
    tx_result = validate_block_transactions(block, utxo_set, block_reward)
    if not tx_result.valid:
        return tx_result

    return ValidationResult.success(fee=tx_result.fee)
