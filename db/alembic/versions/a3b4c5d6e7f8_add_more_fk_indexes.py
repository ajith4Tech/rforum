"""Add indexes on more FK columns confirmed to be used in query/filter/join paths.

SessionAsset.user_id/session_id/event_id/slide_id, PresentationTimelineItem.timeline_id,
PresentationPage.presentation_id, and Session.event_id are all filtered or joined on by
existing queries (asset listing/storage totals, timeline item lookups/reorders, the
lazy page-render hot path, and event-scoped session/analytics queries) but were never
indexed. SessionAsset.presentation_id is deliberately NOT indexed here — it's set on
insert but never filtered/joined on by any query. Purely additive; no data or API changes.

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
    op.create_index("ix_session_assets_user_id", "session_assets", ["user_id"])
    op.create_index("ix_session_assets_session_id", "session_assets", ["session_id"])
    op.create_index("ix_session_assets_event_id", "session_assets", ["event_id"])
    op.create_index("ix_session_assets_slide_id", "session_assets", ["slide_id"])
    op.create_index(
        "ix_presentation_timeline_items_timeline_id", "presentation_timeline_items", ["timeline_id"]
    )
    op.create_index("ix_presentation_pages_presentation_id", "presentation_pages", ["presentation_id"])
    op.create_index("ix_sessions_event_id", "sessions", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_event_id", table_name="sessions")
    op.drop_index("ix_presentation_pages_presentation_id", table_name="presentation_pages")
    op.drop_index("ix_presentation_timeline_items_timeline_id", table_name="presentation_timeline_items")
    op.drop_index("ix_session_assets_slide_id", table_name="session_assets")
    op.drop_index("ix_session_assets_event_id", table_name="session_assets")
    op.drop_index("ix_session_assets_session_id", table_name="session_assets")
    op.drop_index("ix_session_assets_user_id", table_name="session_assets")
