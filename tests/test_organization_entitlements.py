from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import uuid

import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.compiler import compiles


@compiles(UUID, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kw):
    return "CHAR(36)"

from services.subscription.main import app
from shared.config import settings
from shared.database import Base, get_db
from shared.models.application import Application, AppSubscriptionPlan
from shared.models.organization import Organization
from shared.models.subscription import OrganizationSubscription, SubscriptionPlan


@pytest.fixture
def entitlement_client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'entitlements.db'}", connect_args={"check_same_thread": False}
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    old_admin = settings.SUBSCRIPTION_ADMIN_TOKEN
    old_service = settings.AI_PLATFORM_SERVICE_TOKEN
    settings.SUBSCRIPTION_ADMIN_TOKEN = "admin-test"
    settings.AI_PLATFORM_SERVICE_TOKEN = "platform-test"
    app.dependency_overrides[get_db] = override_db

    db = session_factory()
    org = Organization(id=uuid.uuid4(), name="Tenant A", path="/tenant-a", level=0)
    application = Application(
        id=uuid.uuid4(), name="AI Lab", app_id="ai-lab-platform",
        app_secret_hash="hash", status="active",
    )
    plan = SubscriptionPlan(
        id=uuid.uuid4(), name="Research Pro", duration_days=30, price=Decimal("99.00"),
        features={"knowledge_entitlements": ["premium_research"]}, request_quota=1000,
        token_quota=100000, quota_period_days=30,
    )
    db.add_all([org, application, plan])
    db.flush()
    db.add(AppSubscriptionPlan(application_id=application.id, plan_id=plan.id))
    db.add(OrganizationSubscription(
        organization_id=org.id, application_id=application.id, plan_id=plan.id,
        status="active", start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30), entitlement_version=3,
    ))
    db.commit()
    ids = {"org": str(org.id), "plan": str(plan.id)}
    db.close()
    yield httpx.ASGITransport(app=app), ids
    app.dependency_overrides.pop(get_db, None)
    settings.SUBSCRIPTION_ADMIN_TOKEN = old_admin
    settings.AI_PLATFORM_SERVICE_TOKEN = old_service
    Base.metadata.drop_all(engine)


@pytest.mark.asyncio
async def test_internal_entitlements_require_service_identity(entitlement_client):
    transport, ids = entitlement_client
    path = f"/api/v1/internal/organizations/{ids['org']}/entitlements?app_id=ai-lab-platform"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(path)).status_code == 403
        response = await client.get(path, headers={"Authorization": "Bearer platform-test"})
    assert response.status_code == 200
    assert response.json()["knowledge_entitlements"] == ["premium_research"]
    assert response.json()["entitlement_version"] == 3


@pytest.mark.asyncio
async def test_plan_mutation_requires_admin_and_rejects_wildcards(entitlement_client):
    transport, _ = entitlement_client
    body = {
        "name": "Unsafe", "duration_days": 30, "price": 1,
        "features": {"knowledge_entitlements": ["premium_*"]},
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/v1/subscriptions/plans", json=body)).status_code == 403
        response = await client.post(
            "/api/v1/subscriptions/plans", json=body,
            headers={"Authorization": "Bearer admin-test"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_plan_response_includes_features(entitlement_client):
    transport, _ = entitlement_client
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/subscriptions/plans")
    assert response.status_code == 200
    assert response.json()[0]["features"]["knowledge_entitlements"] == ["premium_research"]
