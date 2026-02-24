"""Add application tables

Revision ID: 004
Revises: 003
Create Date: 2024-01-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 applications 表
    op.create_table(
        'applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('app_id', sa.String(64), nullable=False),
        sa.Column('app_secret_hash', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('rate_limit', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_applications_app_id'), 'applications', ['app_id'], unique=True)
    op.create_index(op.f('ix_applications_status'), 'applications', ['status'], unique=False)

    # 创建 app_login_methods 表
    op.create_table(
        'app_login_methods',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('application_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('method', sa.String(20), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('oauth_config', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'method', name='uq_app_login_method'),
    )
    op.create_index(op.f('ix_app_login_methods_application_id'), 'app_login_methods', ['application_id'], unique=False)

    # 创建 app_scopes 表
    op.create_table(
        'app_scopes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('application_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scope', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'scope', name='uq_app_scope'),
    )
    op.create_index(op.f('ix_app_scopes_application_id'), 'app_scopes', ['application_id'], unique=False)

    # 创建 app_users 表
    op.create_table(
        'app_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=uuid.uuid4),
        sa.Column('application_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'user_id', name='uq_app_user'),
    )
    op.create_index(op.f('ix_app_users_application_id'), 'app_users', ['application_id'], unique=False)
    op.create_index(op.f('ix_app_users_user_id'), 'app_users', ['user_id'], unique=False)


def downgrade() -> None:
    # 按依赖关系逆序删除
    op.drop_index(op.f('ix_app_users_user_id'), table_name='app_users')
    op.drop_index(op.f('ix_app_users_application_id'), table_name='app_users')
    op.drop_table('app_users')

    op.drop_index(op.f('ix_app_scopes_application_id'), table_name='app_scopes')
    op.drop_table('app_scopes')

    op.drop_index(op.f('ix_app_login_methods_application_id'), table_name='app_login_methods')
    op.drop_table('app_login_methods')

    op.drop_index(op.f('ix_applications_status'), table_name='applications')
    op.drop_index(op.f('ix_applications_app_id'), table_name='applications')
    op.drop_table('applications')
