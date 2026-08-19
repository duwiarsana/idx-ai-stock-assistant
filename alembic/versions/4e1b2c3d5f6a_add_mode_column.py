"""Add mode column to crypto_paper_positions (PAPER vs REAL)

Revision ID: 4e1b2c3d5f6a
Revises: 3d9a2f6b8c1e
Create Date: 2026-08-17 05:30:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e1b2c3d5f6a'
down_revision: Union[str, None] = '3d9a2f6b8c1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crypto_paper_positions', sa.Column('mode', sa.String(length=10), nullable=True))
    op.execute("UPDATE crypto_paper_positions SET mode = 'PAPER' WHERE mode IS NULL")
    op.alter_column('crypto_paper_positions', 'mode', nullable=False)
    op.create_index('ix_paper_positions_mode', 'crypto_paper_positions', ['mode'])


def downgrade() -> None:
    op.drop_index('ix_paper_positions_mode', table_name='crypto_paper_positions')
    op.drop_column('crypto_paper_positions', 'mode')