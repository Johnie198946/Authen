from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import uuid

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import shared.models  # noqa: F401
from services.subscription.main import app
from shared.config import settings
from shared.database import Base, get_db
from shared.models.application import Application, AppSubscriptionPlan
from shared.models.organization import Organization
from shared.models.subscription import (
    KnowledgePack,
    OrganizationKnowledgeGrant,
    PlanKnowledgePackPolicy,
    SubscriptionPlan,
)


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kw):
    return "CHAR(36)"


@pytest.fixture
def pack_context():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)

    def override_db():
        with factory() as db:
            yield db

    old_service = settings.AI_PLATFORM_SERVICE_TOKEN
    old_url = settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_URL
    old_secret = settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_SECRET
    settings.AI_PLATFORM_SERVICE_TOKEN = "platform-test"
    settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_URL = ""
    settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_SECRET = ""
    app.dependency_overrides[get_db] = override_db

    with factory() as db:
        org = Organization(id=uuid.uuid4(), name="Tenant A", path="/tenant-a", level=0)
        application = Application(
            id=uuid.uuid4(), name="AI Lab", app_id="ai-lab-platform",
            app_secret_hash="hash", status="active",
        )
        basic = SubscriptionPlan(
            id=uuid.uuid4(), name="团队知识基础版", duration_days=365,
            price=Decimal("0"), features={}, request_quota=10000,
            token_quota=10000000, quota_period_days=30,
        )
        pro = SubscriptionPlan(
            id=uuid.uuid4(), name="团队知识专业版", duration_days=365,
            price=Decimal("0"), features={}, request_quota=50000,
            token_quota=50000000, quota_period_days=30,
        )
        packs = [
            KnowledgePack(
                id=uuid.uuid4(), application_id=application.id,
                entitlement_key=f"kb.pack-{index}", name=f"Pack {index}",
                description="Published", status="published", is_selectable=True,
                sort_order=index, approved_document_count=5, minimum_document_count=5,
                freshness_percent=100,
            )
            for index in range(1, 4)
        ]
        draft = KnowledgePack(
            id=uuid.uuid4(), application_id=application.id,
            entitlement_key="kb.draft", name="Draft", description="Draft",
            status="draft", is_selectable=False, approved_document_count=0,
            minimum_document_count=5, freshness_percent=0,
        )
        db.add_all([org, application, basic, pro, *packs, draft])
        db.flush()
        db.add_all([
            AppSubscriptionPlan(application_id=application.id, plan_id=basic.id),
            AppSubscriptionPlan(application_id=application.id, plan_id=pro.id),
            PlanKnowledgePackPolicy(
                plan_id=basic.id, application_id=application.id,
                max_pack_count=0, selectable_pack_ids=[],
            ),
            PlanKnowledgePackPolicy(
                plan_id=pro.id, application_id=application.id,
                max_pack_count=2, selectable_pack_ids=[str(pack.id) for pack in packs] + [str(draft.id)],
            ),
        ])
        db.commit()
        ids = {
            "org": str(org.id), "basic": str(basic.id), "pro": str(pro.id),
            "packs": [str(pack.id) for pack in packs], "draft": str(draft.id),
        }

    yield httpx.ASGITransport(app=app), ids, factory

    app.dependency_overrides.pop(get_db, None)
    settings.AI_PLATFORM_SERVICE_TOKEN = old_service
    settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_URL = old_url
    settings.AI_PLATFORM_ENTITLEMENT_WEBHOOK_SECRET = old_secret
    Base.metadata.drop_all(engine)


@pytest.mark.asyncio
async def test_plan_pack_limit_governance_and_atomic_grants(pack_context):
    transport, ids, factory = pack_context
    headers = {"Authorization": "Bearer platform-test"}
    path = f"/api/v1/internal/organizations/{ids['org']}/subscription-requests"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        too_many = await client.post(
            path, params={"app_id": "ai-lab-platform"}, headers=headers,
            json={
                "request_id": "request-too-many", "plan_id": ids["pro"],
                "requested_by": "member", "requested_pack_ids": ids["packs"],
            },
        )
        assert too_many.status_code == 422

        draft = await client.post(
            path, params={"app_id": "ai-lab-platform"}, headers=headers,
            json={
                "request_id": "request-draft-pack", "plan_id": ids["pro"],
                "requested_by": "member", "requested_pack_ids": [ids["draft"]],
            },
        )
        assert draft.status_code == 422

        body = {
            "request_id": "request-professional-0001", "plan_id": ids["pro"],
            "requested_by": "member", "requested_pack_ids": ids["packs"][:2],
        }
        created = await client.post(path, params={"app_id": "ai-lab-platform"}, headers=headers, json=body)
        repeated = await client.post(path, params={"app_id": "ai-lab-platform"}, headers=headers, json=body)
        assert created.status_code == 200, created.text
        assert repeated.json()["id"] == created.json()["id"]

        approved = await client.post(
            f"/api/v1/internal/admin/subscription-requests/{created.json()['id']}/approve",
            params={"app_id": "ai-lab-platform"}, headers=headers,
            json={
                "reviewed_by": "admin", "review_note": "partial approval",
                "approved_pack_ids": [ids["packs"][0]],
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["approved_pack_ids"] == [ids["packs"][0]]

        entitlements = await client.get(
            f"/api/v1/internal/organizations/{ids['org']}/entitlements",
            params={"app_id": "ai-lab-platform"}, headers=headers,
        )
        assert entitlements.status_code == 200
        assert entitlements.json()["knowledge_entitlements"] == ["kb.pack-1"]
        assert entitlements.json()["pack_allowance"] == 2

        downgrade = await client.post(
            path, params={"app_id": "ai-lab-platform"}, headers=headers,
            json={
                "request_id": "request-downgrade-0001", "plan_id": ids["basic"],
                "requested_by": "member", "requested_pack_ids": [],
            },
        )
        assert downgrade.status_code == 200, downgrade.text
        downgraded = await client.post(
            f"/api/v1/internal/admin/subscription-requests/{downgrade.json()['id']}/approve",
            params={"app_id": "ai-lab-platform"}, headers=headers,
            json={"reviewed_by": "admin", "review_note": "downgraded"},
        )
        assert downgraded.status_code == 200
        after = await client.get(
            f"/api/v1/internal/organizations/{ids['org']}/entitlements",
            params={"app_id": "ai-lab-platform"}, headers=headers,
        )
        assert after.json()["knowledge_entitlements"] == []
        assert after.json()["entitlement_version"] == 2

    with factory() as db:
        grant = db.query(OrganizationKnowledgeGrant).one()
        assert grant.status == "revoked"
        assert grant.revoked_at is not None
