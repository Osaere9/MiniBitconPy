"""
Node configuration using Pydantic Settings.

Configuration is loaded from environment variables with sensible defaults.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/minibitcoinpy"

    # Node
    node_host: str = "0.0.0.0"
    node_port: int = 8000
    node_name: str = "node1"

    # Mining
    default_target: int = int(
        "00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16
    )
    block_reward: int = 5000000000  # 50 "coins" with 8 decimal places
    max_block_txs: int = 100

    # P2P
    bootstrap_peers: List[str] = []
    max_peers: int = 50
    sync_interval: int = 30  # seconds

    # Logging
    log_level: str = "INFO"

    @field_validator("default_target", mode="before")
    @classmethod
    def parse_target(cls, v):
        """Parse target from hex string if needed."""
        if isinstance(v, str):
            return int(v, 16)
        return v

    @field_validator("bootstrap_peers", mode="before")
    @classmethod
    def parse_peers(cls, v):
        """Parse peers from comma-separated string."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [p.strip() for p in v.split(",") if p.strip()]
        return v or []

    @property
    def node_url(self) -> str:
        """Get the node's URL."""
        return f"http://{self.node_host}:{self.node_port}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
