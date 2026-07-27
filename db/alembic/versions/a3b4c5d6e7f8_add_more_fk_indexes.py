"""Add index on the one FK column confirmed to be used in a query/filter/join path
that no earlier migration already indexed.

SessionAsset.event_id is filtered/joined on by existing queries (asset listing/storage
totals) but was never indexed. Purely additive; no data or API changes.

This migration originally also (re)created ix_session_assets_user_id/_session_id/_slide_id
(already created by a5b6c7d8e9f0/add_session_asset alongside the table itself),
ix_presentation_timeline_items_timeline_id and ix_presentation_pages_presentation_id
(already created by b7f3c1a9d4e2/add_presentation_timeline_models), and
ix_sessions_event_id (already created by c2d9a0a1b2c3/add_events_and_session_event_id) —
all ancestors of this revision in the same linear history. Recreating them raised
DuplicateTableError against a database migrated from scratch; it went unnoticed because
every environment this had actually run against was already past all four of those
migrations with the indexes already in place. Removed here; only the genuinely new
SessionAsset.event_id index remains. SessionAsset.presentation_id is deliberately NOT
indexed — it's set on insert but never filtered/joined on by any query.

Revision ID: a3b4c5d6e7f8
Revises: f7a8b9c0d1e2
Create Date: 2026-07-20 00:00:00.000001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_session_assets_event_id", "session_assets", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_session_assets_event_id", table_name="session_assets")
