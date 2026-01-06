"""
Chain synchronization module.

Handles:
- Initial sync from peers on startup
- Adopting better chains (reorg if necessary)
- Periodic sync with peers

Chain Selection:
- Best chain = highest cumulative work
- On receiving a better chain, validate and adopt it
- Rebuild UTXO set from genesis when switching chains
"""

import logging
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy.orm import Session

from mini_pow_chain.core.block import Block
from mini_pow_chain.core.utxo import UTXOSet
from mini_pow_chain.core.consensus import compute_work, compute_cumulative_work
from mini_pow_chain.core.validation import validate_block_full
from mini_pow_chain.node.storage import (
    BlockStorage,
    ChainStateStorage,
    rebuild_utxo_set,
)
from mini_pow_chain.node.config import get_settings

logger = logging.getLogger(__name__)


class ChainSynchronizer:
    """
    Handles chain synchronization and reorg logic.
    """

    def __init__(
        self,
        session: Session,
        utxo_set: UTXOSet,
        block_reward: int,
    ):
        self.session = session
        self.utxo_set = utxo_set
        self.block_reward = block_reward
        self.block_storage = BlockStorage(session)
        self.state_storage = ChainStateStorage(session)

    def get_current_height(self) -> int:
        """Get current chain height."""
        state = self.state_storage.get_state()
        return state.tip_height if state else -1

    def get_current_tip(self) -> Optional[str]:
        """Get current chain tip hash."""
        state = self.state_storage.get_state()
        return state.tip_hash if state else None

    def get_cumulative_work(self) -> int:
        """Get current cumulative work."""
        state = self.state_storage.get_state()
        if state:
            return int(state.cumulative_work, 16)
        return 0

    def validate_and_import_chain(
        self,
        blocks: List[Block],
    ) -> Tuple[bool, str, int]:
        """
        Validate and potentially import a chain.

        Args:
            blocks: List of blocks (should start from genesis or connect to existing chain)

        Returns:
            Tuple of (success, message, new_height)
        """
        if not blocks:
            return False, "Empty block list", -1

        # Check if this is a better chain
        new_work = sum(compute_work(b.target) for b in blocks)
        current_work = self.get_cumulative_work()

        if new_work <= current_work:
            return False, f"Chain work {new_work} not better than current {current_work}", -1

        logger.info(f"Validating chain with {len(blocks)} blocks, work={new_work}")

        # Build temporary UTXO set and validate all blocks
        temp_utxo = UTXOSet()
        prev_block = None

        for i, block in enumerate(blocks):
            # Validate block
            result = validate_block_full(
                block=block,
                prev_block=prev_block,
                utxo_set=temp_utxo,
                block_reward=self.block_reward,
            )

            if not result.valid:
                return False, f"Block {i} ({block.block_hash[:16]}...) invalid: {result.message}", -1

            # Apply transactions to temp UTXO
            for tx in block.transactions:
                temp_utxo.apply_transaction(tx)

            prev_block = block

        # All blocks valid - import the chain
        logger.info("Chain validated successfully, importing...")

        # Clear existing blocks (full reorg)
        self.block_storage.delete_blocks_above_height(-1)

        # Store all blocks
        for height, block in enumerate(blocks):
            self.block_storage.store_block(block, height)

        # Update chain state
        final_block = blocks[-1]
        self.state_storage.update_tip(
            tip_hash=final_block.block_hash,
            tip_height=len(blocks) - 1,
            target=final_block.target,
            cumulative_work=new_work,
        )

        # Replace UTXO set
        self.utxo_set.utxos = temp_utxo.utxos

        self.session.commit()

        logger.info(f"Imported chain: height={len(blocks)-1}, tip={final_block.block_hash[:16]}...")
        return True, "Chain imported successfully", len(blocks) - 1

    def sync_from_peer_chain(
        self,
        peer_blocks: List[Dict[str, Any]],
    ) -> Tuple[bool, str, int]:
        """
        Sync from a peer's chain data.

        Args:
            peer_blocks: List of block dicts from peer's /chain endpoint

        Returns:
            Tuple of (success, message, new_height)
        """
        if not peer_blocks:
            return False, "No blocks from peer", -1

        # Parse blocks
        try:
            blocks = [Block.from_dict(b) for b in peer_blocks]
        except Exception as e:
            return False, f"Failed to parse blocks: {e}", -1

        return self.validate_and_import_chain(blocks)

    def add_block(
        self,
        block: Block,
    ) -> Tuple[bool, str]:
        """
        Add a single block to the chain.

        Args:
            block: Block to add

        Returns:
            Tuple of (success, message)
        """
        # Check if block already exists
        if self.block_storage.block_exists(block.block_hash):
            return False, "Block already exists"

        # Get current tip
        current_tip = self.get_current_tip()
        current_height = self.get_current_height()

        # Check if block extends current chain
        if block.prev_hash != current_tip and current_tip is not None:
            return False, f"Block does not extend current chain (prev={block.prev_hash[:16]}..., tip={current_tip[:16]}...)"

        # Get previous block for validation
        prev_block = None
        if current_tip:
            prev_block = self.block_storage.get_block_by_hash(current_tip)

        # Validate block
        result = validate_block_full(
            block=block,
            prev_block=prev_block,
            utxo_set=self.utxo_set,
            block_reward=self.block_reward,
        )

        if not result.valid:
            return False, f"Block invalid: {result.error.value if result.error else ''} - {result.message}"

        # Apply transactions to UTXO set
        for tx in block.transactions:
            self.utxo_set.apply_transaction(tx)

        # Store block
        new_height = current_height + 1
        self.block_storage.store_block(block, new_height)

        # Update chain state
        new_work = self.get_cumulative_work() + compute_work(block.target)
        self.state_storage.update_tip(
            tip_hash=block.block_hash,
            tip_height=new_height,
            target=block.target,
            cumulative_work=new_work,
        )

        self.session.commit()

        logger.info(f"Added block {block.block_hash[:16]}... at height {new_height}")
        return True, f"Block added at height {new_height}"


def initial_sync(
    session: Session,
    peer_chains: List[List[Dict[str, Any]]],
    utxo_set: UTXOSet,
    block_reward: int,
) -> Tuple[bool, int]:
    """
    Perform initial sync from multiple peer chains.

    Selects the chain with highest cumulative work.

    Args:
        session: Database session
        peer_chains: List of chain data from peers
        utxo_set: UTXO set to update
        block_reward: Block reward for validation

    Returns:
        Tuple of (synced, new_height)
    """
    if not peer_chains:
        return False, -1

    # Parse and calculate work for each chain
    best_chain = None
    best_work = 0

    for chain_data in peer_chains:
        try:
            blocks = [Block.from_dict(b) for b in chain_data]
            work = sum(compute_work(b.target) for b in blocks)
            if work > best_work:
                best_work = work
                best_chain = blocks
        except Exception as e:
            logger.warning(f"Failed to parse peer chain: {e}")
            continue

    if not best_chain:
        return False, -1

    # Sync from best chain
    synchronizer = ChainSynchronizer(session, utxo_set, block_reward)
    success, _, height = synchronizer.validate_and_import_chain(best_chain)

    return success, height
