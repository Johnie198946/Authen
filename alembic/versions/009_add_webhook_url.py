"""add webhook_url column to applications table

Revision ID: 009
Revises: 008
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('webhook_url', sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'webhook_url')
