"""Add password_changed field to users table

Revision ID: 002
Revises: 001
Create Date: 2024-01-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 添加password_changed字段到users表
    op.add_column('users', sa.Column('password_changed', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # 删除password_changed字段
    op.drop_column('users', 'password_changed')
