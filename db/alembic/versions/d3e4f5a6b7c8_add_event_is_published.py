"""Add is_published to events

Revision ID: d3e4f5a6b7c8
Revises: c2d9a0a1b2c3
Create Date: 2026-02-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d9a0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("events", "is_published")
