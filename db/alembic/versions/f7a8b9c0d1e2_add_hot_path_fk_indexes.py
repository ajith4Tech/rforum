"""Add indexes on hot-path FK columns with no existing index.

Session.owner_id, Session.presentation_id, Slide.session_id, and
Response.slide_id are filtered/joined on by nearly every authenticated
request (ownership checks, timeline/slide lookups, analytics aggregates) but
were never indexed — Postgres does not auto-index plain foreign-key
columns, only primary/unique ones. Purely additive; no data or API changes.

Revision ID: f7a8b9c0d1e2
Revises: e1f2a3b4c5d6
Create Date: 2026-07-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_sessions_owner_id", "sessions", ["owner_id"])
    op.create_index("ix_sessions_presentation_id", "sessions", ["presentation_id"])
    op.create_index("ix_slides_session_id", "slides", ["session_id"])
    op.create_index("ix_responses_slide_id", "responses", ["slide_id"])


def downgrade() -> None:
    op.drop_index("ix_responses_slide_id", table_name="responses")
    op.drop_index("ix_slides_session_id", table_name="slides")
    op.drop_index("ix_sessions_presentation_id", table_name="sessions")
    op.drop_index("ix_sessions_owner_id", table_name="sessions")
