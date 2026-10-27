"""Add is_hidden to responses

Lets a moderator hide an individual audience response (offensive Q&A, word
cloud or feedback text) without deleting it: hidden rows are filtered out of
everything guests and the projector receive, and the moderator can unhide
them. Additive with a server default, so existing responses stay visible.

Revision ID: c4d5e6f7a8b9
Revises: f3a6d7e8c9b1
Create Date: 2026-10-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "f3a6d7e8c9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "responses",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("responses", "is_hidden")
