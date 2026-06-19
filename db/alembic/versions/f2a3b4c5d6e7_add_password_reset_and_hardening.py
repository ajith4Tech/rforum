"""Add password_reset_tokens and DB hardening constraints

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── password_reset_tokens ─────────────────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "used", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_prt_user_id", "password_reset_tokens", ["user_id"])
    op.create_index(
        "ix_prt_token_hash", "password_reset_tokens", ["token_hash"], unique=True
    )
    op.create_index("ix_prt_expires_at", "password_reset_tokens", ["expires_at"])

    # ── Partial unique index: at most one SUPER_ADMIN ─────────────────────────
    op.create_index(
        "uq_one_super_admin",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'SUPER_ADMIN'"),
    )


def downgrade() -> None:
    op.drop_index("uq_one_super_admin", table_name="users")
    op.drop_index("ix_prt_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_prt_token_hash", table_name="password_reset_tokens")
    op.drop_index("ix_prt_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
