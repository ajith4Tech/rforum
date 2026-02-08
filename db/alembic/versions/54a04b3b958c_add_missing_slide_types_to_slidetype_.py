"""add missing slide types to slidetype enum

Revision ID: 54a04b3b958c
Revises: 75ab51c2e678
Create Date: 2026-02-06 23:17:31.293090
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = '54a04b3b958c'
down_revision: Union[str, None] = '75ab51c2e678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
