"""Add system_settings table

Revision ID: e1f2a3b4c5d6
Revises: 9c1d2e3f4a5b
Create Date: 2026-06-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "9c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_name", sa.String(255), nullable=False,
            server_default="Tech4Good Community"
        ),
        sa.Column(
            "org_logo_url", sa.String(500), nullable=False,
            server_default="/logo-mascot.webp"
        ),
        sa.Column(
            "invite_code", sa.String(50), nullable=False,
            server_default="RFORUM01"
        ),
        sa.Column(
            "invite_code_enabled", sa.Boolean(), nullable=False,
            server_default="true"
        ),
        sa.Column(
            "onboarding_locked", sa.Boolean(), nullable=False,
            server_default="false"
        ),
    )
    # Seed the single settings row.
    op.execute(
        "INSERT INTO system_settings "
        "(id, org_name, org_logo_url, invite_code, invite_code_enabled, onboarding_locked) "
        "VALUES (1, 'Tech4Good Community', '/logo-mascot.webp', 'RFORUM01', true, false)"
    )


def downgrade() -> None:
    op.drop_table("system_settings")
