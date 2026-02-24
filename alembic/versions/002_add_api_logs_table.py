"""add api_logs table

Revision ID: 002
Revises: 001
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    添加API日志表
    
    需求：9.8 - API网关应记录所有API调用日志
    """
    # 创建api_logs表
    op.create_table(
        'api_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('path', sa.String(500), nullable=False),
        sa.Column('query_params', postgresql.JSONB, nullable=True),
        sa.Column('request_body', postgresql.JSONB, nullable=True),
        sa.Column('status_code', sa.String(3), nullable=False),
        sa.Column('response_time', sa.String(20), nullable=True),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'))
    )
    
    # 创建索引
    op.create_index('idx_api_logs_user_id', 'api_logs', ['user_id'])
    op.create_index('idx_api_logs_path', 'api_logs', ['path'])
    op.create_index('idx_api_logs_status_code', 'api_logs', ['status_code'])
    op.create_index('idx_api_logs_created_at', 'api_logs', ['created_at'])


def downgrade() -> None:
    """删除API日志表"""
    op.drop_index('idx_api_logs_created_at', 'api_logs')
    op.drop_index('idx_api_logs_status_code', 'api_logs')
    op.drop_index('idx_api_logs_path', 'api_logs')
    op.drop_index('idx_api_logs_user_id', 'api_logs')
    op.drop_table('api_logs')
