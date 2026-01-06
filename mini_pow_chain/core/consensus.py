"""
Consensus rules and Proof-of-Work mining.

PoW Validity:
- block_hash (as integer) must be <= target
- Target is a 256-bit integer

Work Calculation:
- work = 2^256 / (target + 1)
- Cumulative work = sum of work for all blocks in chain
- Best chain = chain with highest cumulative work

Target Adjustment (optional):
- Adjust every ADJUSTMENT_INTERVAL blocks
- Based on actual vs expected time for the interval
- Clamped to max 4x adjustment per interval
"""

import time
from dataclasses import dataclass
from typing import Optional, Callable

from mini_pow_chain.core.block import Block


# Maximum possible target (256 bits all 1s)
MAX_TARGET = (1 << 256) - 1

# Default easy target for quick mining (about 16 leading zero bits)
DEFAULT_TARGET = int("00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16)

# Target adjustment parameters
ADJUSTMENT_INTERVAL = 10  # Adjust every N blocks
TARGET_BLOCK_TIME = 10  # Target seconds per block
MAX_ADJUSTMENT_FACTOR = 4  # Max 4x adjustment per interval


def compute_work(target: int) -> int:
    """
    Compute the work value for a given target.

    Work = 2^256 / (target + 1)

    Higher target (easier) = less work
    Lower target (harder) = more work

    Args:
        target: The PoW target

    Returns:
        Work value as integer
    """
    if target < 0:
        raise ValueError("Target cannot be negative")
    if target >= MAX_TARGET:
        return 1  # Minimum work
    return (1 << 256) // (target + 1)


def compute_cumulative_work(blocks: list[Block]) -> int:
    """
    Compute cumulative work for a chain of blocks.

    Args:
        blocks: List of blocks (in order from genesis)

    Returns:
        Total cumulative work
    """
    return sum(compute_work(block.target) for block in blocks)


def is_valid_pow(block: Block) -> bool:
    """
    Check if a block's proof-of-work is valid.

    Args:
        block: Block to validate

    Returns:
        True if int(block_hash, 16) <= target
    """
    hash_int = int(block.block_hash, 16)
    return hash_int <= block.target


def adjust_target(
    current_target: int,
    actual_time: int,
    expected_time: int,
) -> int:
    """
    Adjust target based on actual vs expected block time.

    If blocks are too fast: lower target (harder)
    If blocks are too slow: raise target (easier)

    Args:
        current_target: Current target value
        actual_time: Actual time taken for interval (seconds)
        expected_time: Expected time for interval (seconds)

    Returns:
        New target value (clamped)
    """
    if actual_time <= 0:
        actual_time = 1

    # Calculate adjustment ratio
    ratio = actual_time / expected_time

    # Clamp ratio to prevent extreme adjustments
    ratio = max(1 / MAX_ADJUSTMENT_FACTOR, min(MAX_ADJUSTMENT_FACTOR, ratio))

    # Calculate new target
    new_target = int(current_target * ratio)

    # Ensure target doesn't exceed maximum
    new_target = min(new_target, MAX_TARGET)

    # Ensure target is at least 1
    new_target = max(new_target, 1)

    return new_target


def calculate_next_target(
    current_height: int,
    current_target: int,
    block_timestamps: list[int],
) -> int:
    """
    Calculate target for the next block.

    Args:
        current_height: Height of the latest block
        current_target: Target of the latest block
        block_timestamps: Timestamps of recent blocks (for adjustment)

    Returns:
        Target for the next block
    """
    next_height = current_height + 1

    # Check if adjustment is needed
    if next_height % ADJUSTMENT_INTERVAL != 0:
        return current_target

    # Need at least ADJUSTMENT_INTERVAL timestamps
    if len(block_timestamps) < ADJUSTMENT_INTERVAL:
        return current_target

    # Get timestamps for the adjustment interval
    recent = block_timestamps[-ADJUSTMENT_INTERVAL:]
    actual_time = recent[-1] - recent[0]
    expected_time = (ADJUSTMENT_INTERVAL - 1) * TARGET_BLOCK_TIME

    return adjust_target(current_target, actual_time, expected_time)


@dataclass
class MiningResult:
    """Result of a mining attempt."""

    success: bool
    block: Optional[Block] = None
    nonce: int = 0
    hash_count: int = 0
    elapsed_seconds: float = 0.0


def mine_block(
    block: Block,
    max_nonce: int = 0xFFFFFFFF,
    callback: Optional[Callable[[int], bool]] = None,
) -> MiningResult:
    """
    Mine a block by finding a valid nonce.

    Args:
        block: Block to mine (nonce will be modified)
        max_nonce: Maximum nonce value to try
        callback: Optional callback(nonce) -> bool, return False to stop

    Returns:
        MiningResult with success status and statistics
    """
    start_time = time.time()
    target = block.target

    for nonce in range(max_nonce + 1):
        block.nonce = nonce

        # Get hash and check PoW
        block_hash = block.block_hash
        hash_int = int(block_hash, 16)

        if hash_int <= target:
            elapsed = time.time() - start_time
            return MiningResult(
                success=True,
                block=block,
                nonce=nonce,
                hash_count=nonce + 1,
                elapsed_seconds=elapsed,
            )

        # Call callback periodically
        if callback and nonce % 10000 == 0:
            if not callback(nonce):
                elapsed = time.time() - start_time
                return MiningResult(
                    success=False,
                    nonce=nonce,
                    hash_count=nonce + 1,
                    elapsed_seconds=elapsed,
                )

    elapsed = time.time() - start_time
    return MiningResult(
        success=False,
        nonce=max_nonce,
        hash_count=max_nonce + 1,
        elapsed_seconds=elapsed,
    )


def mine_block_async_friendly(
    block: Block,
    batch_size: int = 10000,
) -> tuple[bool, int]:
    """
    Mine a batch of nonces (for async-friendly mining).

    This function tries batch_size nonces and returns.
    Call repeatedly with increasing start nonces until success.

    Args:
        block: Block to mine
        batch_size: Number of nonces to try

    Returns:
        Tuple of (found_valid, nonces_tried)
    """
    target = block.target
    start_nonce = block.nonce

    for i in range(batch_size):
        nonce = start_nonce + i
        if nonce > 0xFFFFFFFF:
            break

        block.nonce = nonce
        block.invalidate_hash_cache()

        hash_int = int(block.block_hash, 16)
        if hash_int <= target:
            return True, i + 1

    # Update block to last tried nonce + 1 for next batch
    block.nonce = min(start_nonce + batch_size, 0xFFFFFFFF)
    block.invalidate_hash_cache()

    return False, batch_size
