"""Add user role column

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum type
    userrole = sa.Enum("USER", "SUPER_ADMIN", name="userrole")
    userrole.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum("USER", "SUPER_ADMIN", name="userrole", create_type=False),
            nullable=False,
            server_default="USER",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
