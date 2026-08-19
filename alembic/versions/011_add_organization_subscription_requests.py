"""add organization subscription approval requests

Revision ID: 011
Revises: 010
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_subscription_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=160), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column(
            "requested_entitlements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_plan_id"], ["subscription_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_org_subscription_request_id"),
    )
    op.create_index("ix_org_sub_req_org", "organization_subscription_requests", ["organization_id"])
    op.create_index("ix_org_sub_req_app", "organization_subscription_requests", ["application_id"])
    op.create_index("ix_org_sub_req_plan", "organization_subscription_requests", ["target_plan_id"])
    op.create_index("ix_org_sub_req_status", "organization_subscription_requests", ["status"])
    op.create_index(
        "uq_org_app_pending_subscription_request",
        "organization_subscription_requests",
        ["organization_id", "application_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_org_app_pending_subscription_request",
        table_name="organization_subscription_requests",
    )
    op.drop_index("ix_org_sub_req_status", table_name="organization_subscription_requests")
    op.drop_index("ix_org_sub_req_plan", table_name="organization_subscription_requests")
    op.drop_index("ix_org_sub_req_app", table_name="organization_subscription_requests")
    op.drop_index("ix_org_sub_req_org", table_name="organization_subscription_requests")
    op.drop_table("organization_subscription_requests")
