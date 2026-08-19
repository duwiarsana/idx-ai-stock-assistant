"""Add crypto scanner tables (crypto_scans, crypto_alerts)

Revision ID: 2c9f1a3b5d7e
Revises: bb8cba7d6407
Create Date: 2026-08-16 00:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c9f1a3b5d7e'
down_revision: Union[str, None] = 'bb8cba7d6407'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crypto_scans',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('display', sa.String(length=50), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('market_metrics', sa.JSON(), nullable=True),
        sa.Column('indicator_summary', sa.JSON(), nullable=True),
        sa.Column('score_breakdown', sa.JSON(), nullable=True),
        sa.Column('ai_verdict', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crypto_scans_symbol', 'crypto_scans', ['symbol'])
    op.create_index('ix_crypto_scans_symbol_time', 'crypto_scans', ['symbol', 'created_at'])

    op.create_table(
        'crypto_alerts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('display', sa.String(length=50), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('ai_confidence', sa.Integer(), nullable=True),
        sa.Column('risk', sa.String(length=10), nullable=True),
        sa.Column('reason', sa.JSON(), nullable=True),
        sa.Column('delivery_status', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crypto_alerts_symbol', 'crypto_alerts', ['symbol'])
    op.create_index('ix_crypto_alerts_symbol_time', 'crypto_alerts', ['symbol', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_crypto_alerts_symbol_time', table_name='crypto_alerts')
    op.drop_index('ix_crypto_alerts_symbol', table_name='crypto_alerts')
    op.drop_table('crypto_alerts')
    op.drop_index('ix_crypto_scans_symbol_time', table_name='crypto_scans')
    op.drop_index('ix_crypto_scans_symbol', table_name='crypto_scans')
    op.drop_table('crypto_scans')
