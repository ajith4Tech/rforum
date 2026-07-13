"""Add Presentation-first architecture: Presentation, PresentationPage,
PresentationTimeline, PresentationTimelineItem, plus optional links from
Session and SessionAsset. Purely additive — no existing table/column is
altered or dropped; every new column is nullable and every new table starts
empty, so all legacy sessions/slides/assets are unaffected.

Revision ID: b7f3c1a9d4e2
Revises: 9c1d2e3f4a5b
Create Date: 2026-07-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7f3c1a9d4e2"
down_revision: Union[str, None] = "9c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    presentation_source_format = sa.Enum(
        "PDF", "PPT", "PPTX", name="presentationsourceformat"
    )
    presentation_status = sa.Enum(
        "PENDING", "PROCESSING", "READY", "FAILED", name="presentationstatus"
    )
    timeline_item_type = sa.Enum(
        "PAGE", "POLL", "QNA", "WORD_CLOUD", "FEEDBACK", "RATING", name="timelineitemtype"
    )

    op.create_table(
        "presentations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_file_name", sa.String(length=500), nullable=False),
        sa.Column("original_file_url", sa.String(length=1000), nullable=False),
        sa.Column("original_file_type", sa.String(length=255), nullable=False),
        sa.Column("original_file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source_format", presentation_source_format, nullable=False),
        sa.Column(
            "status", presentation_status, nullable=False, server_default="PENDING"
        ),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replaces_presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaces_presentation_id"], ["presentations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_presentations_owner_id", "presentations", ["owner_id"])

    op.create_table(
        "presentation_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_presentation_pages_presentation_id", "presentation_pages", ["presentation_id"]
    )

    # active_timeline_item_id's FK is added after presentation_timeline_items exists
    # (circular reference between the two tables), matching the model's use_alter=True.
    op.create_table(
        "presentation_timelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_timeline_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["presentation_id"], ["presentations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )

    op.create_table(
        "presentation_timeline_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timeline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("item_type", timeline_item_type, nullable=False),
        sa.Column("presentation_page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slide_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["timeline_id"], ["presentation_timelines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["presentation_page_id"], ["presentation_pages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_presentation_timeline_items_timeline_id",
        "presentation_timeline_items",
        ["timeline_id"],
    )

    op.create_foreign_key(
        "fk_timeline_active_item",
        "presentation_timelines",
        "presentation_timeline_items",
        ["active_timeline_item_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "sessions",
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_presentation_id",
        "sessions",
        "presentations",
        ["presentation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "session_assets",
        sa.Column("presentation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_session_assets_presentation_id",
        "session_assets",
        "presentations",
        ["presentation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_session_assets_presentation_id", "session_assets", ["presentation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_assets_presentation_id", table_name="session_assets")
    op.drop_constraint(
        "fk_session_assets_presentation_id", "session_assets", type_="foreignkey"
    )
    op.drop_column("session_assets", "presentation_id")

    op.drop_constraint("fk_sessions_presentation_id", "sessions", type_="foreignkey")
    op.drop_column("sessions", "presentation_id")

    op.drop_constraint(
        "fk_timeline_active_item", "presentation_timelines", type_="foreignkey"
    )

    op.drop_index(
        "ix_presentation_timeline_items_timeline_id",
        table_name="presentation_timeline_items",
    )
    op.drop_table("presentation_timeline_items")

    op.drop_table("presentation_timelines")

    op.drop_index("ix_presentation_pages_presentation_id", table_name="presentation_pages")
    op.drop_table("presentation_pages")

    op.drop_index("ix_presentations_owner_id", table_name="presentations")
    op.drop_table("presentations")

    sa.Enum(name="timelineitemtype").drop(op.get_bind())
    sa.Enum(name="presentationstatus").drop(op.get_bind())
    sa.Enum(name="presentationsourceformat").drop(op.get_bind())
