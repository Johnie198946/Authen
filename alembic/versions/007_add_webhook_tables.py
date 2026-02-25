"""add webhook_event_logs table and webhook_secret column

Revision ID: 007
Revises: 006
Create Date: 2026-03-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 webhook_event_logs 表
    op.create_table(
        'webhook_event_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('event_id', sa.String(255), nullable=False),
        sa.Column('app_id', sa.String(64), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('request_summary', sa.JSON(), nullable=True),
        sa.Column('response_summary', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_webhook_event_logs_event_id'), 'webhook_event_logs', ['event_id'], unique=True)
    op.create_index(op.f('ix_webhook_event_logs_app_id'), 'webhook_event_logs', ['app_id'], unique=False)
    op.create_index(op.f('ix_webhook_event_logs_event_type'), 'webhook_event_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_webhook_event_logs_status'), 'webhook_event_logs', ['status'], unique=False)

    # 为 applications 表添加 webhook_secret 列
    op.add_column('applications', sa.Column('webhook_secret', sa.String(255), nullable=True))


def downgrade() -> None:
    # 移除 applications 表的 webhook_secret 列
    op.drop_column('applications', 'webhook_secret')

    # 删除 webhook_event_logs 表及其索引
    op.drop_index(op.f('ix_webhook_event_logs_status'), table_name='webhook_event_logs')
    op.drop_index(op.f('ix_webhook_event_logs_event_type'), table_name='webhook_event_logs')
    op.drop_index(op.f('ix_webhook_event_logs_app_id'), table_name='webhook_event_logs')
    op.drop_index(op.f('ix_webhook_event_logs_event_id'), table_name='webhook_event_logs')
    op.drop_table('webhook_event_logs')
