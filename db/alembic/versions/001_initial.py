"""Initial tables

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Sessions
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("unique_code", sa.String(9), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("is_live", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_unique_code", "sessions", ["unique_code"])

    # Slides
    slide_type = sa.Enum("poll", "qna", "feedback", "content", name="slidetype")
    op.create_table(
        "slides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", slide_type, nullable=False),
        sa.Column("order", sa.Integer, nullable=False, default=0),
        sa.Column("content_json", JSON, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, default=False),
    )
    op.create_index("ix_slides_session_order", "slides", ["session_id", "order"])

    # Responses
    op.create_table(
        "responses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slide_id", UUID(as_uuid=True), sa.ForeignKey("slides.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("guest_identifier", sa.String(255), nullable=False),
        sa.Column("upvotes", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_responses_slide_id", "responses", ["slide_id"])


def downgrade() -> None:
    op.drop_table("responses")
    op.drop_table("slides")
    op.drop_table("sessions")
    op.drop_table("users")
    sa.Enum(name="slidetype").drop(op.get_bind())
