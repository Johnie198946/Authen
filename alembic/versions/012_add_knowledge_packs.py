"""add governed knowledge packs and organization grants

Revision ID: 012
Revises: 011
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_subscription_requests",
        sa.Column("requested_pack_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "organization_subscription_requests",
        sa.Column("approved_pack_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    op.create_table(
        "knowledge_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entitlement_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("is_selectable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minimum_document_count", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("approved_document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("freshness_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_label", sa.String(80), nullable=False, server_default="黄色受限知识"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("application_id", "entitlement_key", name="uq_knowledge_pack_app_key"),
    )
    op.create_index("ix_knowledge_pack_app", "knowledge_packs", ["application_id"])
    op.create_index("ix_knowledge_pack_status", "knowledge_packs", ["status"])

    op.create_table(
        "plan_knowledge_pack_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("max_pack_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selectable_pack_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("custom_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("plan_id", "application_id", name="uq_plan_pack_policy_app"),
    )
    op.create_index("ix_plan_pack_policy_plan", "plan_knowledge_pack_policies", ["plan_id"])
    op.create_index("ix_plan_pack_policy_app", "plan_knowledge_pack_policies", ["application_id"])

    op.create_table(
        "organization_knowledge_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("effective_until", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_request_id", sa.String(160), nullable=False, server_default=""),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_subscription_id"], ["organization_subscriptions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["knowledge_pack_id"], ["knowledge_packs.id"]),
        sa.UniqueConstraint(
            "organization_subscription_id", "knowledge_pack_id", name="uq_org_subscription_pack_grant"
        ),
    )
    op.create_index("ix_org_grant_subscription", "organization_knowledge_grants", ["organization_subscription_id"])
    op.create_index("ix_org_grant_pack", "organization_knowledge_grants", ["knowledge_pack_id"])
    op.create_index("ix_org_grant_status", "organization_knowledge_grants", ["status"])
    op.create_index("ix_org_grant_expiry", "organization_knowledge_grants", ["effective_until"])

    op.get_bind().exec_driver_sql("""
    INSERT INTO subscription_plans
      (id, name, description, duration_days, price, features, is_active,
       request_quota, token_quota, quota_period_days, created_at, updated_at)
    VALUES
      ('d1100000-0000-4000-8000-000000000001', '团队知识基础版',
       '绿色公共知识、知识钱包与基础组织协作。', 365, 0,
       '{"highlights":["绿色公共知识","知识钱包","组织审批"],"commercial_mode":"approval"}'::jsonb,
       true, 10000, 10000000, 30, now(), now()),
      ('d1100000-0000-4000-8000-000000000002', '团队知识专业版',
       '团队共享检索、Agent与工作流调用，可申请2个治理完成的黄色知识包。', 365, 0,
       '{"highlights":["2个自选知识包","Agent与工作流","来源追溯"],"commercial_mode":"approval"}'::jsonb,
       true, 50000, 50000000, 30, now(), now()),
      ('d1100000-0000-4000-8000-000000000003', '企业知识治理版',
       '企业权益管理、使用审计与治理状态，可申请5个治理完成的黄色知识包。', 365, 0,
       '{"highlights":["5个自选知识包","权益审计","治理状态"],"commercial_mode":"approval"}'::jsonb,
       true, 200000, 200000000, 30, now(), now()),
      ('d1100000-0000-4000-8000-000000000004', '企业知识专属版',
       '按合同配置专属租户隔离、私有知识治理、审计与运维服务。', 365, 0,
       '{"highlights":["专属隔离","私有治理服务","定制配额"],"commercial_mode":"contact_admin","custom_only":true}'::jsonb,
       true, -1, -1, 30, now(), now())
    ON CONFLICT (id) DO UPDATE SET
      name=EXCLUDED.name, description=EXCLUDED.description, features=EXCLUDED.features,
      is_active=EXCLUDED.is_active, request_quota=EXCLUDED.request_quota,
      token_quota=EXCLUDED.token_quota, quota_period_days=EXCLUDED.quota_period_days,
      updated_at=now();

    INSERT INTO app_subscription_plans (id, application_id, plan_id, created_at)
    SELECT gen_random_uuid(), a.id, p.id, now()
    FROM applications a
    CROSS JOIN subscription_plans p
    WHERE a.app_id='ai-lab-platform'
      AND p.id IN (
        'd1100000-0000-4000-8000-000000000001',
        'd1100000-0000-4000-8000-000000000002',
        'd1100000-0000-4000-8000-000000000003',
        'd1100000-0000-4000-8000-000000000004'
      )
    ON CONFLICT (application_id, plan_id) DO NOTHING;
    """)

    op.get_bind().exec_driver_sql("""
    INSERT INTO knowledge_packs
      (id, application_id, entitlement_key, name, description, status, is_selectable,
       sort_order, minimum_document_count, approved_document_count, freshness_percent, risk_label)
    SELECT v.id::uuid, a.id, v.entitlement_key, v.name, v.description, v.status, false,
           v.sort_order, 5, 0, 0, v.risk_label
    FROM applications a
    CROSS JOIN (VALUES
      ('e1100000-0000-4000-8000-000000000001','kb.agent-knowledge-governance','Agent与知识治理','Agent安全、知识治理、多租户、DSL、记忆与权限方法论','draft',10,'黄色受限知识'),
      ('e1100000-0000-4000-8000-000000000002','kb.ai-infra-tokenops','AI Infra与TokenOps','Token工程、推理基础设施、模型路由、成本与可观测性','draft',20,'黄色受限知识'),
      ('e1100000-0000-4000-8000-000000000003','kb.enterprise-ai-delivery','企业AI落地方法','场景评估、AI中台、IPD、供应链与方案交付方法','draft',30,'黄色受限知识'),
      ('e1100000-0000-4000-8000-000000000004','kb.manufacturing-physical-ai','制造与Physical AI','智能制造、工业Agent、知识图谱、物理AI与工厂方案','draft',40,'黄色受限知识'),
      ('e1100000-0000-4000-8000-000000000005','kb.competitive-strategy','竞品与战略情报','企业、模型、算力和产业趋势；逐条排除内部战略与客户材料','draft',50,'受限情报·逐条治理'),
      ('e1100000-0000-4000-8000-000000000006','kb.quantum-platform-product','Quantum平台产品与实施','已批准的产品能力、实施规范、平台架构和客户启用材料','draft',60,'黄色受限知识'),
      ('e1100000-0000-4000-8000-000000000007','kb.audit-compliance','审计与合规','审计、合规与风险控制专项知识','incubating',70,'建设中'),
      ('e1100000-0000-4000-8000-000000000008','kb.finance','金融行业','金融行业场景、监管与实施知识','incubating',80,'建设中'),
      ('e1100000-0000-4000-8000-000000000009','kb.healthcare','医疗行业','医疗行业场景、合规与实施知识','incubating',90,'建设中'),
      ('e1100000-0000-4000-8000-000000000010','kb.education','教育行业','教育行业场景与实施知识','incubating',100,'建设中')
    ) AS v(id, entitlement_key, name, description, status, sort_order, risk_label)
    WHERE a.app_id='ai-lab-platform'
    ON CONFLICT (application_id, entitlement_key) DO NOTHING;
    """)

    op.get_bind().exec_driver_sql("""
    INSERT INTO plan_knowledge_pack_policies
      (id, plan_id, application_id, max_pack_count, selectable_pack_ids, custom_only)
    SELECT gen_random_uuid(), p.plan_id::uuid, a.id, p.max_count,
           CASE WHEN p.max_count=0 THEN '[]'::jsonb ELSE
             (SELECT jsonb_agg(id::text ORDER BY sort_order) FROM knowledge_packs
              WHERE application_id=a.id AND status='draft') END,
           p.custom_only
    FROM applications a
    CROSS JOIN (VALUES
      ('d1100000-0000-4000-8000-000000000001',0,false),
      ('d1100000-0000-4000-8000-000000000002',2,false),
      ('d1100000-0000-4000-8000-000000000003',5,false),
      ('d1100000-0000-4000-8000-000000000004',-1,true)
    ) AS p(plan_id,max_count,custom_only)
    WHERE a.app_id='ai-lab-platform'
    ON CONFLICT (plan_id, application_id) DO UPDATE SET
      max_pack_count=EXCLUDED.max_pack_count,
      selectable_pack_ids=EXCLUDED.selectable_pack_ids,
      custom_only=EXCLUDED.custom_only,
      updated_at=now();
    """)


def downgrade() -> None:
    op.drop_table("organization_knowledge_grants")
    op.drop_table("plan_knowledge_pack_policies")
    op.drop_table("knowledge_packs")
    op.drop_column("organization_subscription_requests", "approved_pack_ids")
    op.drop_column("organization_subscription_requests", "requested_pack_ids")
