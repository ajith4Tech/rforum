"""Add session_asset model for centralised file tracking

Revision ID: a5b6c7d8e9f0
Revises: e8d384600296
Create Date: 2026-03-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a5b6c7d8e9f0'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'session_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('slide_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('file_name', sa.String(length=500), nullable=False),
        sa.Column('file_url', sa.String(length=1000), nullable=False),
        sa.Column('file_type', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('file_size', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['slide_id'], ['slides.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_session_assets_user_id', 'session_assets', ['user_id'])
    op.create_index('ix_session_assets_session_id', 'session_assets', ['session_id'])
    op.create_index('ix_session_assets_slide_id', 'session_assets', ['slide_id'])


def downgrade() -> None:
    op.drop_index('ix_session_assets_slide_id', table_name='session_assets')
    op.drop_index('ix_session_assets_session_id', table_name='session_assets')
    op.drop_index('ix_session_assets_user_id', table_name='session_assets')
    op.drop_table('session_assets')
