"""add word_cloud slide type

Revision ID: f1a2b3c4d5e6
Revises: e8d384600296
Create Date: 2026-02-24 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e8d384600296'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE slidetype ADD VALUE IF NOT EXISTS 'WORD_CLOUD'")


def downgrade() -> None:
    pass
