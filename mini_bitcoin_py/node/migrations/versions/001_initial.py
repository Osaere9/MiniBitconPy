"""Initial migration - create blockchain tables

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create blocks table
    op.create_table(
        'blocks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('block_hash', sa.String(64), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('prev_hash', sa.String(64), nullable=False),
        sa.Column('merkle_root', sa.String(64), nullable=False),
        sa.Column('timestamp', sa.BigInteger(), nullable=False),
        sa.Column('target', sa.String(66), nullable=False),
        sa.Column('nonce', sa.BigInteger(), nullable=False),
        sa.Column('block_data', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('block_hash'),
    )
    op.create_index('ix_blocks_block_hash', 'blocks', ['block_hash'])
    op.create_index('ix_blocks_height', 'blocks', ['height'])
    op.create_index('ix_blocks_prev_hash', 'blocks', ['prev_hash'])
    op.create_index('ix_blocks_height_hash', 'blocks', ['height', 'block_hash'])

    # Create chain_state table
    op.create_table(
        'chain_state',
        sa.Column('id', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('tip_hash', sa.String(64), nullable=True),
        sa.Column('tip_height', sa.Integer(), nullable=False, server_default='-1'),
        sa.Column('current_target', sa.String(66), nullable=False),
        sa.Column('cumulative_work', sa.Text(), nullable=False, server_default='0'),
        sa.Column('last_sync', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create peers table
    op.create_table(
        'peers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('url', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url'),
    )
    op.create_index('ix_peers_url', 'peers', ['url'])

    # Create mempool_txs table
    op.create_table(
        'mempool_txs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('txid', sa.String(64), nullable=False),
        sa.Column('tx_data', postgresql.JSONB(), nullable=False),
        sa.Column('fee', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('txid'),
    )
    op.create_index('ix_mempool_txs_txid', 'mempool_txs', ['txid'])


def downgrade() -> None:
    op.drop_table('mempool_txs')
    op.drop_table('peers')
    op.drop_table('chain_state')
    op.drop_table('blocks')
