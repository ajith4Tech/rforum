"""Add org_settings singleton table backing the Organization Settings /
Branding admin feature. One Rforum instance = one organization (see
deploy/helm/rforum's one-instance-per-org deployment model), so this table
is seeded with exactly one row (id=1) and a CHECK constraint enforces it
never grows past that — not just an application-level convention.

Revision ID: b4f1c2d3e4f5
Revises: a3b4c5d6e7f8
Create Date: 2026-07-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b4f1c2d3e4f5'
down_revision: Union[str, None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'org_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=False, server_default='Your Organization'),
        sa.Column('logo_key', sa.String(length=500), nullable=True),
        sa.Column('logo_content_type', sa.String(length=100), nullable=True),
        sa.Column('favicon_key', sa.String(length=500), nullable=True),
        sa.Column('favicon_content_type', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='org_settings_singleton'),
    )
    op.execute("INSERT INTO org_settings (id, display_name) VALUES (1, 'Your Organization')")


def downgrade() -> None:
    op.drop_table('org_settings')
