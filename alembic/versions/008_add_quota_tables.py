"""add quota columns to subscription_plans and create quota tables

Revision ID: 008
Revises: 007
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 为 subscription_plans 表添加配额相关列
    op.add_column('subscription_plans', sa.Column('request_quota', sa.Integer(), nullable=False, server_default=sa.text('-1')))
    op.add_column('subscription_plans', sa.Column('token_quota', sa.BigInteger(), nullable=False, server_default=sa.text('-1')))
    op.add_column('subscription_plans', sa.Column('quota_period_days', sa.Integer(), nullable=False, server_default=sa.text('30')))

    # 创建 app_quota_overrides 表
    op.create_table(
        'app_quota_overrides',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('application_id', UUID(as_uuid=True), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('request_quota', sa.Integer(), nullable=True),
        sa.Column('token_quota', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # 创建 quota_usages 表
    op.create_table(
        'quota_usages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('application_id', UUID(as_uuid=True), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('billing_cycle_start', sa.DateTime(), nullable=False),
        sa.Column('billing_cycle_end', sa.DateTime(), nullable=False),
        sa.Column('request_quota_limit', sa.Integer(), nullable=False),
        sa.Column('request_quota_used', sa.Integer(), nullable=False),
        sa.Column('token_quota_limit', sa.BigInteger(), nullable=False),
        sa.Column('token_quota_used', sa.BigInteger(), nullable=False),
        sa.Column('reset_type', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f('ix_quota_usages_application_id'), 'quota_usages', ['application_id'], unique=False)


def downgrade() -> None:
    # 删除 quota_usages 表及其索引
    op.drop_index(op.f('ix_quota_usages_application_id'), table_name='quota_usages')
    op.drop_table('quota_usages')

    # 删除 app_quota_overrides 表
    op.drop_table('app_quota_overrides')

    # 移除 subscription_plans 表的配额列
    op.drop_column('subscription_plans', 'quota_period_days')
    op.drop_column('subscription_plans', 'token_quota')
    op.drop_column('subscription_plans', 'request_quota')
