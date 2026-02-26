"""Add events and link sessions

Revision ID: c2d9a0a1b2c3
Revises: f1a2b3c4d5e6
Create Date: 2026-02-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c2d9a0a1b2c3"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_owner_date", "events", ["owner_id", "event_date"])

    op.add_column("sessions", sa.Column("event_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_sessions_event_id",
        "sessions",
        "events",
        ["event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sessions_event_id", "sessions", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_sessions_event_id", table_name="sessions")
    op.drop_constraint("fk_sessions_event_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "event_id")

    op.drop_index("ix_events_owner_date", table_name="events")
    op.drop_table("events")
