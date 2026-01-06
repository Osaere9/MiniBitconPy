"""
UTXO (Unspent Transaction Output) Set management.

The UTXO set tracks all spendable outputs in the blockchain.
Key: (txid, output_index) -> Value: TxOut

Rules:
- An output can only be spent once
- Spending requires valid signature from the pubkey that hashes to pubkey_hash
- Input amounts must be >= output amounts (difference is fee)
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional, Set
import copy

from mini_bitcoin_py.core.tx import Transaction, TxOut


# Type alias for UTXO key
UTXOKey = Tuple[str, int]  # (txid, output_index)


@dataclass
class UTXOSet:
    """
    Maintains the set of unspent transaction outputs.

    This is the core data structure for validating transactions.
    Each UTXO is identified by (txid, output_index) and contains the TxOut data.
    """

    # Map from (txid, vout_index) to TxOut
    utxos: Dict[UTXOKey, TxOut] = field(default_factory=dict)

    def get(self, txid: str, index: int) -> Optional[TxOut]:
        """
        Get a UTXO by its key.

        Args:
            txid: Transaction ID containing the output
            index: Output index within the transaction

        Returns:
            TxOut if exists, None otherwise
        """
        return self.utxos.get((txid, index))

    def exists(self, txid: str, index: int) -> bool:
        """Check if a UTXO exists."""
        return (txid, index) in self.utxos

    def add(self, txid: str, index: int, output: TxOut):
        """Add a new UTXO to the set."""
        key = (txid, index)
        if key in self.utxos:
            raise ValueError(f"UTXO already exists: {txid}:{index}")
        self.utxos[key] = output

    def remove(self, txid: str, index: int) -> TxOut:
        """
        Remove and return a UTXO from the set.

        Raises:
            KeyError: If UTXO doesn't exist
        """
        key = (txid, index)
        if key not in self.utxos:
            raise KeyError(f"UTXO not found: {txid}:{index}")
        return self.utxos.pop(key)

    def apply_transaction(self, tx: Transaction) -> int:
        """
        Apply a transaction to the UTXO set.

        This removes spent UTXOs and adds new ones.
        Should only be called AFTER validation.

        Args:
            tx: The transaction to apply

        Returns:
            Fee amount (input_sum - output_sum), or 0 for coinbase
        """
        input_sum = 0
        txid = tx.txid

        # Remove spent UTXOs (skip for coinbase)
        if not tx.is_coinbase():
            for inp in tx.inputs:
                utxo = self.remove(inp.prev_txid, inp.prev_index)
                input_sum += utxo.amount

        # Add new UTXOs
        for idx, out in enumerate(tx.outputs):
            self.add(txid, idx, out)

        output_sum = tx.total_output_amount()

        # For coinbase, no fee calculation
        if tx.is_coinbase():
            return 0

        return input_sum - output_sum

    def unapply_transaction(self, tx: Transaction, spent_utxos: Dict[UTXOKey, TxOut]):
        """
        Reverse a transaction from the UTXO set (for reorg).

        Args:
            tx: The transaction to reverse
            spent_utxos: Map of UTXOs that were spent by this tx (to restore them)
        """
        txid = tx.txid

        # Remove the outputs created by this transaction
        for idx in range(len(tx.outputs)):
            key = (txid, idx)
            if key in self.utxos:
                del self.utxos[key]

        # Restore spent UTXOs (skip for coinbase)
        if not tx.is_coinbase():
            for inp in tx.inputs:
                key = (inp.prev_txid, inp.prev_index)
                if key in spent_utxos:
                    self.utxos[key] = spent_utxos[key]

    def get_balance(self, address: str) -> int:
        """
        Calculate balance for an address.

        Args:
            address: pubkey_hash (address) to check

        Returns:
            Total balance in satoshi-like units
        """
        balance = 0
        for utxo in self.utxos.values():
            if utxo.pubkey_hash == address:
                balance += utxo.amount
        return balance

    def get_utxos_for_address(self, address: str) -> Dict[UTXOKey, TxOut]:
        """
        Get all UTXOs for a specific address.

        Args:
            address: pubkey_hash to filter by

        Returns:
            Dict of UTXOs owned by this address
        """
        return {
            key: utxo
            for key, utxo in self.utxos.items()
            if utxo.pubkey_hash == address
        }

    def select_utxos_for_amount(
        self,
        address: str,
        target_amount: int,
    ) -> Tuple[Dict[UTXOKey, TxOut], int]:
        """
        Select UTXOs to cover a target amount (simple greedy algorithm).

        Args:
            address: pubkey_hash to select from
            target_amount: Amount needed

        Returns:
            Tuple of (selected UTXOs, total value of selected UTXOs)

        Raises:
            ValueError: If insufficient funds
        """
        available = self.get_utxos_for_address(address)
        selected: Dict[UTXOKey, TxOut] = {}
        total = 0

        # Sort by amount (largest first for fewer inputs)
        sorted_utxos = sorted(
            available.items(),
            key=lambda x: x[1].amount,
            reverse=True,
        )

        for key, utxo in sorted_utxos:
            if total >= target_amount:
                break
            selected[key] = utxo
            total += utxo.amount

        if total < target_amount:
            raise ValueError(
                f"Insufficient funds: have {total}, need {target_amount}"
            )

        return selected, total

    def copy(self) -> "UTXOSet":
        """Create a deep copy of the UTXO set."""
        return UTXOSet(utxos=copy.deepcopy(self.utxos))

    def __len__(self) -> int:
        """Return the number of UTXOs in the set."""
        return len(self.utxos)

    def clear(self):
        """Clear all UTXOs."""
        self.utxos.clear()


@dataclass
class MempoolUTXOTracker:
    """
    Tracks UTXO changes from mempool transactions.

    This allows checking for double-spends within the mempool
    without modifying the confirmed UTXO set.
    """

    # UTXOs spent by mempool transactions
    spent: Set[UTXOKey] = field(default_factory=set)

    # New UTXOs created by mempool transactions
    created: Dict[UTXOKey, TxOut] = field(default_factory=dict)

    def is_spent_in_mempool(self, txid: str, index: int) -> bool:
        """Check if a UTXO is already spent by a mempool transaction."""
        return (txid, index) in self.spent

    def add_transaction(self, tx: Transaction):
        """Track a mempool transaction's UTXO changes."""
        txid = tx.txid

        # Track spent UTXOs
        if not tx.is_coinbase():
            for inp in tx.inputs:
                self.spent.add((inp.prev_txid, inp.prev_index))

        # Track created UTXOs
        for idx, out in enumerate(tx.outputs):
            self.created[(txid, idx)] = out

    def remove_transaction(self, tx: Transaction):
        """Remove a transaction from tracking (e.g., when mined)."""
        txid = tx.txid

        # Remove spent tracking
        if not tx.is_coinbase():
            for inp in tx.inputs:
                self.spent.discard((inp.prev_txid, inp.prev_index))

        # Remove created tracking
        for idx in range(len(tx.outputs)):
            self.created.pop((txid, idx), None)

    def clear(self):
        """Clear all tracked changes."""
        self.spent.clear()
        self.created.clear()
