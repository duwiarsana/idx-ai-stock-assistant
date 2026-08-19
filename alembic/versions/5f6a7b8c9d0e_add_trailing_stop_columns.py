"""add trailing stop columns to crypto_paper_positions

Revision ID: 5f6a7b8c9d0e
Revises: 4e1b2c3d5f6a
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = '5f6a7b8c9d0e'
down_revision = '4e1b2c3d5f6a'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('crypto_paper_positions', sa.Column('highest_price', sa.Float(), nullable=True))
    op.add_column('crypto_paper_positions', sa.Column('atr_value', sa.Float(), nullable=True))

def downgrade() -> None:
    op.drop_column('crypto_paper_positions', 'atr_value')
    op.drop_column('crypto_paper_positions', 'highest_price')
