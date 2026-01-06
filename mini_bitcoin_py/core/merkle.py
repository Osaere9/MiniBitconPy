"""
Merkle tree implementation for block transaction validation.

The merkle root is computed from transaction IDs (txids) using double SHA-256.
If the number of transactions is odd, the last hash is duplicated.

This provides:
- Efficient proof that a transaction is included in a block
- Tamper detection for block contents
"""

from typing import List

from mini_bitcoin_py.core.hashing import double_sha256


def compute_merkle_root(txids: List[str]) -> str:
    """
    Compute the merkle root from a list of transaction IDs.

    Args:
        txids: List of transaction IDs (64-char hex strings)

    Returns:
        Merkle root as 64-char hex string

    Raises:
        ValueError: If txids list is empty
    """
    if not txids:
        raise ValueError("Cannot compute merkle root of empty list")

    # Convert txids to bytes
    hashes = [bytes.fromhex(txid) for txid in txids]

    # Build tree bottom-up
    while len(hashes) > 1:
        # If odd number, duplicate last hash
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        # Combine pairs
        new_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i + 1]
            new_level.append(double_sha256(combined))
        hashes = new_level

    return hashes[0].hex()


def compute_merkle_proof(txids: List[str], target_index: int) -> List[dict]:
    """
    Compute a merkle proof for a specific transaction.

    Args:
        txids: List of transaction IDs
        target_index: Index of the transaction to prove

    Returns:
        List of proof elements, each containing:
        - 'hash': The sibling hash (hex)
        - 'position': 'left' or 'right' (position of sibling)
    """
    if not txids:
        raise ValueError("Cannot compute proof of empty list")
    if target_index < 0 or target_index >= len(txids):
        raise ValueError(f"Invalid target index: {target_index}")

    proof = []
    hashes = [bytes.fromhex(txid) for txid in txids]
    index = target_index

    while len(hashes) > 1:
        # If odd number, duplicate last hash
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])

        new_level = []
        for i in range(0, len(hashes), 2):
            # Check if our target is in this pair
            if i == index or i + 1 == index:
                # Add sibling to proof
                if i == index:
                    proof.append({
                        "hash": hashes[i + 1].hex(),
                        "position": "right",
                    })
                else:
                    proof.append({
                        "hash": hashes[i].hex(),
                        "position": "left",
                    })

            combined = hashes[i] + hashes[i + 1]
            new_level.append(double_sha256(combined))

        hashes = new_level
        index = index // 2  # Update index for next level

    return proof


def verify_merkle_proof(
    txid: str,
    merkle_root: str,
    proof: List[dict],
) -> bool:
    """
    Verify a merkle proof.

    Args:
        txid: The transaction ID being verified
        merkle_root: Expected merkle root
        proof: List of proof elements

    Returns:
        True if proof is valid
    """
    current = bytes.fromhex(txid)

    for element in proof:
        sibling = bytes.fromhex(element["hash"])
        if element["position"] == "right":
            combined = current + sibling
        else:
            combined = sibling + current
        current = double_sha256(combined)

    return current.hex() == merkle_root
