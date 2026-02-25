"""add auto_provision_configs table

Revision ID: 006
Revises: 005
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'auto_provision_configs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('application_id', UUID(as_uuid=True), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role_ids', JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column('permission_ids', JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column('organization_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('subscription_plan_id', UUID(as_uuid=True), sa.ForeignKey('subscription_plans.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_enabled', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('application_id', name='uq_auto_provision_config_application'),
    )


def downgrade() -> None:
    op.drop_table('auto_provision_configs')
