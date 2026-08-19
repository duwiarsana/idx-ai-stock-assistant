"""Add crypto paper trading tables (accounts, positions, trades)

Revision ID: 3d9a2f6b8c1e
Revises: 2c9f1a3b5d7e
Create Date: 2026-08-16 00:30:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d9a2f6b8c1e'
down_revision: Union[str, None] = '2c9f1a3b5d7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'crypto_paper_accounts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('quote_asset', sa.String(length=10), nullable=False),
        sa.Column('initial_balance', sa.Float(), nullable=False),
        sa.Column('cash_balance', sa.Float(), nullable=False),
        sa.Column('realized_pnl', sa.Float(), nullable=False),
        sa.Column('total_trades', sa.Integer(), nullable=False),
        sa.Column('winning_trades', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('quote_asset'),
    )

    op.create_table(
        'crypto_paper_positions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('base', sa.String(length=20), nullable=True),
        sa.Column('quote', sa.String(length=10), nullable=False),
        sa.Column('display', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=True),
        sa.Column('invested', sa.Float(), nullable=True),
        sa.Column('take_profit_1', sa.Float(), nullable=True),
        sa.Column('take_profit_2', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('entry_score', sa.Float(), nullable=True),
        sa.Column('entry_reason', sa.String(length=255), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('exit_reason', sa.String(length=50), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_paper_positions_status', 'crypto_paper_positions', ['status'])
    op.create_index('ix_paper_positions_symbol_status', 'crypto_paper_positions', ['symbol', 'status'])

    op.create_table(
        'crypto_paper_trades',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('position_id', sa.Uuid(), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('side', sa.String(length=20), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=True),
        sa.Column('quote_amount', sa.Float(), nullable=True),
        sa.Column('realized_pnl', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_paper_trades_position', 'crypto_paper_trades', ['position_id'])


def downgrade() -> None:
    op.drop_index('ix_paper_trades_position', table_name='crypto_paper_trades')
    op.drop_table('crypto_paper_trades')
    op.drop_index('ix_paper_positions_symbol_status', table_name='crypto_paper_positions')
    op.drop_index('ix_paper_positions_status', table_name='crypto_paper_positions')
    op.drop_table('crypto_paper_positions')
    op.drop_table('crypto_paper_accounts')