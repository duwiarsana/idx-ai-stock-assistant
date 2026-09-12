"""add tp1_partial_done to crypto_paper_positions

Revision ID: 6a1b2c3d4e5f
Revises: 5f6a7b8c9d0e
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = '6a1b2c3d4e5f'
down_revision = '5f6a7b8c9d0e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'crypto_paper_positions',
        sa.Column('tp1_partial_done', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('crypto_paper_positions', 'tp1_partial_done')