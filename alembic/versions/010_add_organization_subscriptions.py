"""add organization subscriptions

Revision ID: 010
Revises: 009
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_app_subscription_plan", "app_subscription_plans", type_="unique")
    op.create_unique_constraint(
        "uq_app_subscription_plan", "app_subscription_plans", ["application_id", "plan_id"]
    )
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
        sa.Column("entitlement_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "application_id", name="uq_org_subscription_app"),
    )
    op.create_index("ix_org_sub_org", "organization_subscriptions", ["organization_id"])
    op.create_index("ix_org_sub_app", "organization_subscriptions", ["application_id"])
    op.create_index("ix_org_sub_status", "organization_subscriptions", ["status"])
    op.create_index("ix_org_sub_end", "organization_subscriptions", ["end_date"])


def downgrade() -> None:
    op.drop_index("ix_org_sub_end", table_name="organization_subscriptions")
    op.drop_index("ix_org_sub_status", table_name="organization_subscriptions")
    op.drop_index("ix_org_sub_app", table_name="organization_subscriptions")
    op.drop_index("ix_org_sub_org", table_name="organization_subscriptions")
    op.drop_table("organization_subscriptions")
    op.drop_constraint("uq_app_subscription_plan", "app_subscription_plans", type_="unique")
    op.create_unique_constraint("uq_app_subscription_plan", "app_subscription_plans", ["application_id"])
