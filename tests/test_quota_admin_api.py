"""
Admin Service 配额管理 API 单元测试

测试 Task 5.1 中实现的配额管理端点和订阅计划配额字段扩展。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi import Query
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import uuid

from shared.database import get_db
from shared.models.application import Application, AppSubscriptionPlan
from shared.models.subscription import SubscriptionPlan
from shared.models.quota import AppQuotaOverride, QuotaUsage
from services.admin.main import app, require_super_admin


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

class Store:
    def __init__(self):
        self.applications = {}
        self.plans = {}
        self.overrides = {}
        self.usages = []
        self.bindings = {}
        self.audit_logs = []

    def reset(self):
        self.applications.clear()
        self.plans.clear()
        self.overrides.clear()
        self.usages.clear()
        self.bindings.clear()
        self.audit_logs.clear()


store = Store()


# Fake Redis for testing
class FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, *args, **kwargs):
        self.data[key] = str(value)

    def hgetall(self, key):
        val = self.data.get(key)
        if isinstance(val, dict):
            return val
        return {}

    def hset(self, key, mapping=None, **kwargs):
        if key not in self.data or not isinstance(self.data[key], dict):
            self.data[key] = {}
        if mapping:
            self.data[key].update(mapping)

    def delete(self, *keys):
        for k in keys:
            self.data.pop(k, None)

    def reset(self):
        self.data.clear()


fake_redis = FakeRedis()


class FakeQuery:
    """Mimics SQLAlchemy query chain for multiple model types."""

    def __init__(self, model, store_ref):
        self._model = model
        self._store = store_ref
        self._filters = {}
        self._order = None
        self._offset_val = 0
        self._limit_val = 100

    def filter(self, *args):
        for arg in args:
            try:
                col_name = arg.left.key
                value = arg.right.effective_value
                self._filters[col_name] = value
            except Exception:
                pass
        return self

    def order_by(self, *args):
        return self

    def offset(self, n):
        self._offset_val = n
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def count(self):
        return len(self._get_results())

    def first(self):
        results = self._get_results()
        return results[0] if results else None

    def all(self):
        results = self._get_results()
        return results[self._offset_val:self._offset_val + self._limit_val]

    def delete(self, synchronize_session=None):
        pass

    def _get_results(self):
        if self._model == Application:
            items = list(self._store.applications.values())
            if "app_id" in self._filters:
                items = [a for a in items if a.app_id == self._filters["app_id"]]
            if "status" in self._filters:
                items = [a for a in items if a.status == self._filters["status"]]
            return items
        elif self._model == SubscriptionPlan:
            items = list(self._store.plans.values())
            if "id" in self._filters:
                items = [p for p in items if p.id == self._filters["id"]]
            return items
        elif self._model == AppQuotaOverride:
            items = list(self._store.overrides.values())
            if "application_id" in self._filters:
                items = [o for o in items if o.application_id == self._filters["application_id"]]
            return items
        elif self._model == AppSubscriptionPlan:
            items = list(self._store.bindings.values())
            if "application_id" in self._filters:
                items = [b for b in items if b.application_id == self._filters["application_id"]]
            return items
        elif self._model == QuotaUsage:
            items = list(self._store.usages)
            if "application_id" in self._filters:
                items = [u for u in items if u.application_id == self._filters["application_id"]]
            return items
        return []


class FakeSession:
    def __init__(self, store_ref):
        self._store = store_ref

    def query(self, model):
        return FakeQuery(model, self._store)

    def add(self, obj):
        if isinstance(obj, AppQuotaOverride):
            self._store.overrides[obj.application_id] = obj
        elif isinstance(obj, QuotaUsage):
            self._store.usages.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def close(self):
        pass


def override_get_db():
    session = FakeSession(store)
    try:
        yield session
    finally:
        session.close()


def override_require_super_admin(user_id: str = Query("admin1")):
    return user_id


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[require_super_admin] = override_require_super_admin

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(app_id="test_app_001", name="TestApp"):
    a = Application()
    a.id = uuid.uuid4()
    a.app_id = app_id
    a.name = name
    a.status = "active"
    a.created_at = datetime.utcnow()
    a.updated_at = datetime.utcnow()
    return a


def _make_plan(request_quota=1000, token_quota=50000, quota_period_days=30):
    p = SubscriptionPlan()
    p.id = uuid.uuid4()
    p.name = "Basic Plan"
    p.description = "Test plan"
    p.duration_days = 30
    p.price = 9.99
    p.is_active = True
    p.request_quota = request_quota
    p.token_quota = token_quota
    p.quota_period_days = quota_period_days
    p.created_at = datetime.utcnow()
    p.updated_at = datetime.utcnow()
    return p


def _bind_plan(app_obj, plan_obj):
    b = AppSubscriptionPlan()
    b.id = uuid.uuid4()
    b.application_id = app_obj.id
    b.plan_id = plan_obj.id
    b.created_at = datetime.utcnow()
    store.bindings[app_obj.id] = b


def _setup_redis(app_id, requests=100, tokens=5000, cycle_start=None):
    if cycle_start is None:
        cycle_start = datetime.utcnow().isoformat()
    fake_redis.set(f"quota:{app_id}:requests", requests)
    fake_redis.set(f"quota:{app_id}:tokens", tokens)
    fake_redis.set(f"quota:{app_id}:cycle_start", cycle_start)


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    fake_redis.reset()
    yield
    store.reset()
    fake_redis.reset()


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/admin/quota/overview
# ---------------------------------------------------------------------------

@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_overview_empty(mock_redis):
    """No active apps → empty overview"""
    resp = client.get("/api/v1/admin/quota/overview?user_id=admin1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_overview_with_apps(mock_redis):
    """Overview returns data for active apps"""
    app_obj = _make_app()
    plan = _make_plan()
    store.applications[app_obj.app_id] = app_obj
    store.plans[plan.id] = plan
    _bind_plan(app_obj, plan)
    _setup_redis(app_obj.app_id, requests=500, tokens=25000)

    resp = client.get("/api/v1/admin/quota/overview?user_id=admin1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["app_id"] == app_obj.app_id
    assert item["request_quota_used"] == 500
    assert item["token_quota_used"] == 25000
    assert item["request_usage_rate"] == pytest.approx(0.5, abs=0.01)


@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_overview_sort_by_request_usage(mock_redis):
    """Overview supports sorting by request_usage_rate"""
    app1 = _make_app("app_low", "LowUsage")
    app2 = _make_app("app_high", "HighUsage")
    plan = _make_plan(request_quota=1000)
    store.applications[app1.app_id] = app1
    store.applications[app2.app_id] = app2
    store.plans[plan.id] = plan
    _bind_plan(app1, plan)
    _bind_plan(app2, plan)
    _setup_redis("app_low", requests=100)
    _setup_redis("app_high", requests=900)

    resp = client.get("/api/v1/admin/quota/overview?sort_by=request_usage_rate&user_id=admin1")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["app_id"] == "app_high"
    assert items[1]["app_id"] == "app_low"


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/admin/quota/{app_id}
# ---------------------------------------------------------------------------

@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_detail_not_found(mock_redis):
    resp = client.get("/api/v1/admin/quota/nonexistent?user_id=admin1")
    assert resp.status_code == 404


@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_detail_success(mock_redis):
    app_obj = _make_app()
    plan = _make_plan(request_quota=2000, token_quota=100000)
    store.applications[app_obj.app_id] = app_obj
    store.plans[plan.id] = plan
    _bind_plan(app_obj, plan)
    _setup_redis(app_obj.app_id, requests=300, tokens=15000)

    resp = client.get(f"/api/v1/admin/quota/{app_obj.app_id}?user_id=admin1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_id"] == app_obj.app_id
    assert data["request_quota_limit"] == 2000
    assert data["request_quota_used"] == 300
    assert data["token_quota_limit"] == 100000
    assert data["plan_name"] == "Basic Plan"
    assert data["has_override"] is False


# ---------------------------------------------------------------------------
# Tests: PUT /api/v1/admin/quota/{app_id}/override
# ---------------------------------------------------------------------------

@patch("shared.redis_client.get_redis", return_value=fake_redis)
@patch("shared.utils.audit_log.create_audit_log")
def test_quota_override_not_found(mock_audit, mock_redis):
    resp = client.put(
        "/api/v1/admin/quota/nonexistent/override?user_id=admin1",
        json={"request_quota": 5000},
    )
    assert resp.status_code == 404


@patch("shared.redis_client.get_redis", return_value=fake_redis)
@patch("shared.utils.audit_log.create_audit_log")
def test_quota_override_invalid_value(mock_audit, mock_redis):
    app_obj = _make_app()
    store.applications[app_obj.app_id] = app_obj

    resp = client.put(
        f"/api/v1/admin/quota/{app_obj.app_id}/override?user_id=admin1",
        json={"request_quota": -5},
    )
    assert resp.status_code == 400


@patch("shared.redis_client.get_redis", return_value=fake_redis)
@patch("shared.utils.audit_log.create_audit_log")
def test_quota_override_success(mock_audit, mock_redis):
    app_obj = _make_app()
    store.applications[app_obj.app_id] = app_obj

    resp = client.put(
        f"/api/v1/admin/quota/{app_obj.app_id}/override?user_id=admin1",
        json={"request_quota": 5000, "token_quota": 200000},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["new_values"]["request_quota"] == 5000
    assert data["new_values"]["token_quota"] == 200000
    # Verify override stored
    assert app_obj.id in store.overrides


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/admin/quota/{app_id}/reset
# ---------------------------------------------------------------------------

@patch("shared.redis_client.get_redis", return_value=fake_redis)
@patch("shared.utils.audit_log.create_audit_log")
def test_quota_reset_not_found(mock_audit, mock_redis):
    resp = client.post("/api/v1/admin/quota/nonexistent/reset?user_id=admin1")
    assert resp.status_code == 404


@patch("shared.redis_client.get_redis", return_value=fake_redis)
@patch("shared.utils.audit_log.create_audit_log")
def test_quota_reset_success(mock_audit, mock_redis):
    app_obj = _make_app()
    plan = _make_plan()
    store.applications[app_obj.app_id] = app_obj
    store.plans[plan.id] = plan
    _bind_plan(app_obj, plan)
    _setup_redis(app_obj.app_id, requests=800, tokens=40000)

    resp = client.post(f"/api/v1/admin/quota/{app_obj.app_id}/reset?user_id=admin1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["previous_usage"]["request_used"] == 800
    assert data["previous_usage"]["token_used"] == 40000
    # Verify Redis counters reset
    assert fake_redis.get(f"quota:{app_obj.app_id}:requests") == "0"
    assert fake_redis.get(f"quota:{app_obj.app_id}:tokens") == "0"
    # Verify usage record persisted
    assert len(store.usages) == 1
    assert store.usages[0].reset_type == "manual"
    assert store.usages[0].request_quota_used == 800


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/admin/quota/{app_id}/history
# ---------------------------------------------------------------------------

@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_history_not_found(mock_redis):
    resp = client.get("/api/v1/admin/quota/nonexistent/history?user_id=admin1")
    assert resp.status_code == 404


@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_history_empty(mock_redis):
    app_obj = _make_app()
    store.applications[app_obj.app_id] = app_obj

    resp = client.get(f"/api/v1/admin/quota/{app_obj.app_id}/history?user_id=admin1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@patch("shared.redis_client.get_redis", return_value=fake_redis)
def test_quota_history_with_records(mock_redis):
    app_obj = _make_app()
    store.applications[app_obj.app_id] = app_obj

    now = datetime.utcnow()
    usage = QuotaUsage()
    usage.id = uuid.uuid4()
    usage.application_id = app_obj.id
    usage.billing_cycle_start = now - timedelta(days=30)
    usage.billing_cycle_end = now
    usage.request_quota_limit = 1000
    usage.request_quota_used = 750
    usage.token_quota_limit = 50000
    usage.token_quota_used = 35000
    usage.reset_type = "auto"
    usage.created_at = now
    store.usages.append(usage)

    resp = client.get(f"/api/v1/admin/quota/{app_obj.app_id}/history?user_id=admin1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["request_quota_used"] == 750
    assert item["reset_type"] == "auto"


# ---------------------------------------------------------------------------
# Tests: Subscription Plan CRUD quota field extension
# ---------------------------------------------------------------------------

def test_subscription_plan_create_with_quota():
    """Test creating a plan with quota fields via subscription service"""
    from services.subscription.main import app as sub_app, PlanCreate, PlanResponse
    from fastapi.testclient import TestClient as TC

    # Use a separate mock for subscription service
    mock_db = MagicMock()
    plan_id = uuid.uuid4()

    created_plan = MagicMock()
    created_plan.id = plan_id
    created_plan.name = "Pro Plan"
    created_plan.description = "Pro"
    created_plan.duration_days = 30
    created_plan.price = 29.99
    created_plan.is_active = True
    created_plan.request_quota = 5000
    created_plan.token_quota = 200000
    created_plan.quota_period_days = 30

    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock(side_effect=lambda obj: setattr(obj, 'id', plan_id) or
                                setattr(obj, 'is_active', True) or
                                setattr(obj, 'request_quota', 5000) or
                                setattr(obj, 'token_quota', 200000) or
                                setattr(obj, 'quota_period_days', 30))

    def override_db():
        yield mock_db

    from shared.database import get_db as gdb
    sub_app.dependency_overrides[gdb] = override_db
    sub_client = TC(sub_app)

    resp = sub_client.post("/api/v1/subscriptions/plans", json={
        "name": "Pro Plan",
        "description": "Pro",
        "duration_days": 30,
        "price": 29.99,
        "request_quota": 5000,
        "token_quota": 200000,
        "quota_period_days": 30,
    })
    assert resp.status_code == 200
    # Verify the plan was created with add()
    mock_db.add.assert_called_once()
    created_obj = mock_db.add.call_args[0][0]
    assert created_obj.request_quota == 5000
    assert created_obj.token_quota == 200000
    assert created_obj.quota_period_days == 30

    sub_app.dependency_overrides.clear()


def test_subscription_plan_create_rejects_invalid_quota():
    """Test that creating a plan with invalid quota values is rejected"""
    from services.subscription.main import app as sub_app
    from fastapi.testclient import TestClient as TC

    mock_db = MagicMock()

    def override_db():
        yield mock_db

    from shared.database import get_db as gdb
    sub_app.dependency_overrides[gdb] = override_db
    sub_client = TC(sub_app)

    resp = sub_client.post("/api/v1/subscriptions/plans", json={
        "name": "Bad Plan",
        "duration_days": 30,
        "price": 9.99,
        "request_quota": -5,
    })
    assert resp.status_code == 400

    resp2 = sub_client.post("/api/v1/subscriptions/plans", json={
        "name": "Bad Plan",
        "duration_days": 30,
        "price": 9.99,
        "token_quota": -10,
    })
    assert resp2.status_code == 400

    sub_app.dependency_overrides.clear()
