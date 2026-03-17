"""Add moderator and speaker fields to sessions

Revision ID: 9c1d2e3f4a5b
Revises: a5b6c7d8e9f0
Create Date: 2026-03-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c1d2e3f4a5b"
down_revision: Union[str, None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("moderator_name", sa.String(length=255), nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "speaker_names",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "speaker_names")
    op.drop_column("sessions", "moderator_name")
