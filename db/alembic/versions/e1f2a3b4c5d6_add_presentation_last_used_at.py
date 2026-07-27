"""Add last_used_at to presentations: refreshed on upload, dedup-reuse,
replace, and attach, surfaced in the Presentation Details panel. Purely
additive/nullable — no backfill needed, existing rows simply read as
"never used since creation" until next touched.

Revision ID: e1f2a3b4c5d6
Revises: c9a1f2e3b4d5
Create Date: 2026-07-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "c9a1f2e3b4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "presentations", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("presentations", "last_used_at")
