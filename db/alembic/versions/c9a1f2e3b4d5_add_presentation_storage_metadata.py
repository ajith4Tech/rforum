"""Add storage-related metadata to presentations: checksum (dedup), page
dimensions, persisted conversion warnings, and orphaned_since (reference
lifecycle tracking for cleanup). Purely additive — every new column is
nullable or has a server_default, so all existing Presentation rows are
unaffected and keep working through app/storage's backward-compatible key
resolution without any data migration.

Revision ID: c9a1f2e3b4d5
Revises: b7f3c1a9d4e2
Create Date: 2026-07-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c9a1f2e3b4d5"
down_revision: Union[str, None] = "b7f3c1a9d4e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("presentations", sa.Column("checksum", sa.String(length=64), nullable=True))
    op.add_column("presentations", sa.Column("page_width", sa.Float(), nullable=True))
    op.add_column("presentations", sa.Column("page_height", sa.Float(), nullable=True))
    op.add_column(
        "presentations",
        sa.Column(
            "conversion_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
    )
    op.add_column(
        "presentations", sa.Column("orphaned_since", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_presentations_owner_checksum", "presentations", ["owner_id", "checksum"]
    )


def downgrade() -> None:
    op.drop_index("ix_presentations_owner_checksum", table_name="presentations")
    op.drop_column("presentations", "orphaned_since")
    op.drop_column("presentations", "conversion_warnings")
    op.drop_column("presentations", "page_height")
    op.drop_column("presentations", "page_width")
    op.drop_column("presentations", "checksum")
