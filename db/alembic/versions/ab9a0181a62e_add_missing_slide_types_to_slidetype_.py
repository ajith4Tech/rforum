"""add missing slide types to slidetype enum

Revision ID: ab9a0181a62e
Revises: 54a04b3b958c
Create Date: 2026-02-06 23:20:48.278913
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'ab9a0181a62e'
down_revision: Union[str, None] = '54a04b3b958c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE slidetype ADD VALUE IF NOT EXISTS 'POLL'")
    op.execute("ALTER TYPE slidetype ADD VALUE IF NOT EXISTS 'QNA'")
    op.execute("ALTER TYPE slidetype ADD VALUE IF NOT EXISTS 'FEEDBACK'")
    op.execute("ALTER TYPE slidetype ADD VALUE IF NOT EXISTS 'CONTENT'")



def downgrade() -> None:
    pass
