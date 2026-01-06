"""
Peer-to-peer networking using HTTP.

This module handles:
- Broadcasting transactions to peers
- Broadcasting blocks to peers
- Requesting chain data from peers
- Managing peer connections

All P2P communication is done via HTTP POST/GET requests.
"""

import asyncio
import logging
from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass, field

import httpx

from mini_bitcoin_py.core.tx import Transaction
from mini_bitcoin_py.core.block import Block

logger = logging.getLogger(__name__)

# Default timeout for P2P requests
DEFAULT_TIMEOUT = 10.0


@dataclass
class P2PManager:
    """
    Manages peer-to-peer communication.

    Uses httpx for async HTTP requests to peer nodes.
    """

    # Known peer URLs
    peers: Set[str] = field(default_factory=set)

    # Seen transaction hashes (for loop prevention)
    seen_txs: Set[str] = field(default_factory=set)

    # Seen block hashes (for loop prevention)
    seen_blocks: Set[str] = field(default_factory=set)

    # Maximum seen cache size
    max_seen_size: int = 10000

    # HTTP client (created lazily)
    _client: Optional[httpx.AsyncClient] = field(default=None, repr=False)

    def __post_init__(self):
        # Limit seen cache size
        self._trim_seen()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _trim_seen(self):
        """Trim seen caches to max size."""
        if len(self.seen_txs) > self.max_seen_size:
            # Remove oldest half
            to_remove = list(self.seen_txs)[: self.max_seen_size // 2]
            self.seen_txs -= set(to_remove)
        if len(self.seen_blocks) > self.max_seen_size:
            to_remove = list(self.seen_blocks)[: self.max_seen_size // 2]
            self.seen_blocks -= set(to_remove)

    def add_peer(self, url: str) -> bool:
        """Add a peer URL."""
        url = url.rstrip("/")
        if url not in self.peers:
            self.peers.add(url)
            logger.info(f"Added peer: {url}")
            return True
        return False

    def remove_peer(self, url: str) -> bool:
        """Remove a peer URL."""
        url = url.rstrip("/")
        if url in self.peers:
            self.peers.discard(url)
            logger.info(f"Removed peer: {url}")
            return True
        return False

    def mark_tx_seen(self, txid: str):
        """Mark a transaction as seen."""
        self.seen_txs.add(txid)
        self._trim_seen()

    def mark_block_seen(self, block_hash: str):
        """Mark a block as seen."""
        self.seen_blocks.add(block_hash)
        self._trim_seen()

    def is_tx_seen(self, txid: str) -> bool:
        """Check if a transaction has been seen."""
        return txid in self.seen_txs

    def is_block_seen(self, block_hash: str) -> bool:
        """Check if a block has been seen."""
        return block_hash in self.seen_blocks

    async def broadcast_transaction(
        self,
        tx: Transaction,
        exclude_peers: Optional[Set[str]] = None,
    ) -> Dict[str, bool]:
        """
        Broadcast a transaction to all peers.

        Args:
            tx: Transaction to broadcast
            exclude_peers: Peers to skip (e.g., the one that sent it to us)

        Returns:
            Dict mapping peer URL to success status
        """
        txid = tx.txid
        self.mark_tx_seen(txid)

        exclude = exclude_peers or set()
        results = {}

        async def send_to_peer(peer_url: str) -> tuple[str, bool]:
            try:
                response = await self.client.post(
                    f"{peer_url}/tx",
                    json=tx.to_dict(),
                    timeout=DEFAULT_TIMEOUT,
                )
                success = response.status_code in (200, 201, 409)  # 409 = already exists
                return peer_url, success
            except Exception as e:
                logger.warning(f"Failed to send tx to {peer_url}: {e}")
                return peer_url, False

        # Send to all peers concurrently
        tasks = [
            send_to_peer(peer)
            for peer in self.peers
            if peer not in exclude
        ]

        if tasks:
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            for result in completed:
                if isinstance(result, tuple):
                    results[result[0]] = result[1]

        logger.debug(f"Broadcast tx {txid[:16]}... to {len(results)} peers")
        return results

    async def broadcast_block(
        self,
        block: Block,
        exclude_peers: Optional[Set[str]] = None,
    ) -> Dict[str, bool]:
        """
        Broadcast a block to all peers.

        Args:
            block: Block to broadcast
            exclude_peers: Peers to skip

        Returns:
            Dict mapping peer URL to success status
        """
        block_hash = block.block_hash
        self.mark_block_seen(block_hash)

        exclude = exclude_peers or set()
        results = {}

        async def send_to_peer(peer_url: str) -> tuple[str, bool]:
            try:
                response = await self.client.post(
                    f"{peer_url}/block",
                    json=block.to_dict(),
                    timeout=DEFAULT_TIMEOUT,
                )
                success = response.status_code in (200, 201, 409)
                return peer_url, success
            except Exception as e:
                logger.warning(f"Failed to send block to {peer_url}: {e}")
                return peer_url, False

        tasks = [
            send_to_peer(peer)
            for peer in self.peers
            if peer not in exclude
        ]

        if tasks:
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            for result in completed:
                if isinstance(result, tuple):
                    results[result[0]] = result[1]

        logger.debug(f"Broadcast block {block_hash[:16]}... to {len(results)} peers")
        return results

    async def get_peer_chain(self, peer_url: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get the full chain from a peer.

        Args:
            peer_url: URL of the peer

        Returns:
            List of block dicts, or None on failure
        """
        try:
            response = await self.client.get(
                f"{peer_url}/chain",
                timeout=30.0,  # Longer timeout for chain sync
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.warning(f"Failed to get chain from {peer_url}: {e}")
            return None

    async def get_peer_status(self, peer_url: str) -> Optional[Dict[str, Any]]:
        """
        Get status/health from a peer.

        Args:
            peer_url: URL of the peer

        Returns:
            Status dict, or None on failure
        """
        try:
            response = await self.client.get(
                f"{peer_url}/health",
                timeout=DEFAULT_TIMEOUT,
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.debug(f"Failed to get status from {peer_url}: {e}")
            return None

    async def discover_peers(self, peer_url: str) -> List[str]:
        """
        Discover new peers from an existing peer.

        Args:
            peer_url: URL of the peer to ask

        Returns:
            List of discovered peer URLs
        """
        try:
            response = await self.client.get(
                f"{peer_url}/peers",
                timeout=DEFAULT_TIMEOUT,
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("peers", [])
            return []
        except Exception as e:
            logger.debug(f"Failed to discover peers from {peer_url}: {e}")
            return []
