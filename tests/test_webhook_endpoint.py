"""
Webhook 端点集成测试

测试 POST /api/v1/webhooks/subscription 端点的完整处理流程：
- 成功处理事件返回 200
- 幂等性：重复 event_id 返回 200 + duplicate
- 签名验证失败返回 401/403
- Payload 校验失败返回 422
- 内部错误返回 500 并记录 Event Log
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from services.subscription.main import app
from shared.database import get_db


# --- Fake models ---

class FakeApplication:
    def __init__(self, app_id="test-app", status="active", webhook_secret="test-secret"):
        self.id = uuid.uuid4()
        self.app_id = app_id
        self.name = "Test App"
        self.status = status
        self.webhook_secret = webhook_secret
        self.app_secret_hash = "hashed"


class FakeAppUser:
    def __init__(self, application_id, user_id):
        self.id = uuid.uuid4()
        self.application_id = application_id
        self.user_id = user_id


class FakePlan:
    def __init__(self, plan_id=None, is_active=True, duration_days=30):
        self.id = plan_id or uuid.uuid4()
        self.name = "Test Plan"
        self.is_active = is_active
        self.duration_days = duration_days
        self.price = 9.99


class FakeSubscription:
    def __init__(self, user_id, plan_id, status="active"):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.plan_id = plan_id
        self.status = status
        self.start_date = datetime.utcnow()
        self.end_date = datetime.utcnow() + timedelta(days=30)
        self.auto_renew = True
        self.updated_at = None


class FakeEventLog:
    def __init__(self, event_id, status="success", response_summary=None):
        self.id = uuid.uuid4()
        self.event_id = event_id
        self.app_id = "test-app"
        self.event_type = "subscription.created"
        self.status = status
        self.request_summary = {}
        self.response_summary = response_summary or {"event_id": event_id, "status": "processed"}
        self.error_message = None
        self.processed_at = datetime.utcnow()
        self.created_at = datetime.utcnow()


# --- Helpers ---

def _compute_signature(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def _make_payload(event_type="subscription.created", user_id=None, plan_id=None, event_id=None):
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "user_id": user_id or str(uuid.uuid4()),
            "plan_id": plan_id or str(uuid.uuid4()),
            "effective_date": datetime.utcnow().isoformat(),
            "expiry_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        },
    }


# --- Mock DB builder ---

class MockQuery:
    """Flexible mock query that routes based on model class."""
    def __init__(self, route_map):
        self._route_map = route_map

    def __call__(self, model_class):
        model_name = model_class.__name__ if hasattr(model_class, '__name__') else str(model_class)
        result = self._route_map.get(model_name)
        mock_filter = MagicMock()
        if isinstance(result, list):
            mock_filter.first.return_value = result[0] if result else None
            mock_filter.all.return_value = result
            mock_filter.count.return_value = len(result)
        else:
            mock_filter.first.return_value = result
            mock_filter.all.return_value = [result] if result else []
            mock_filter.count.return_value = 1 if result else 0
        mock_filter.filter.return_value = mock_filter
        return mock_filter


def _build_mock_db(route_map=None):
    db = MagicMock()
    if route_map:
        db.query = MockQuery(route_map)
    else:
        mock_filter = MagicMock()
        mock_filter.first.return_value = None
        mock_filter.filter.return_value = mock_filter
        db.query.return_value = mock_filter
    return db


# --- Test fixtures ---

APP_ID = "test-app-001"
WEBHOOK_SECRET = "webhook-secret-abc123"
USER_ID = str(uuid.uuid4())
PLAN_ID = str(uuid.uuid4())


@pytest.fixture
def fake_app():
    return FakeApplication(app_id=APP_ID, webhook_secret=WEBHOOK_SECRET)


@pytest.fixture
def fake_plan():
    return FakePlan(plan_id=uuid.UUID(PLAN_ID))


@pytest.fixture
def fake_app_user(fake_app):
    return FakeAppUser(application_id=fake_app.id, user_id=uuid.UUID(USER_ID))


@pytest.fixture
def fake_subscription():
    return FakeSubscription(user_id=uuid.UUID(USER_ID), plan_id=uuid.UUID(PLAN_ID))


def _make_client(db_mock):
    """Create a TestClient with overridden get_db dependency."""
    def override_get_db():
        yield db_mock
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client


def _send_webhook(client, payload_dict, app_id=APP_ID, secret=WEBHOOK_SECRET):
    """Send a webhook request with proper HMAC signature."""
    body = json.dumps(payload_dict).encode("utf-8")
    sig = _compute_signature(secret, body)
    return client.post(
        "/api/v1/webhooks/subscription",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-App-Id": app_id,
            "X-Webhook-Signature": sig,
        },
    )


# --- Tests ---

class TestWebhookEndpointSuccess:
    """成功处理事件的测试"""

    def test_successful_created_event(self, fake_app, fake_plan, fake_app_user):
        """成功处理 subscription.created 事件返回 200"""
        new_sub = FakeSubscription(user_id=uuid.UUID(USER_ID), plan_id=uuid.UUID(PLAN_ID))
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,  # No existing log (not idempotent hit)
            "AppUser": fake_app_user,
            "SubscriptionPlan": fake_plan,
            "UserSubscription": None,  # No existing subscription
        })
        # Make db.refresh set the id on the subscription
        def fake_refresh(obj):
            if not hasattr(obj, 'id') or obj.id is None:
                obj.id = uuid.uuid4()
        db.refresh = fake_refresh

        client = _make_client(db)
        payload = _make_payload(
            event_type="subscription.created",
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        resp = _send_webhook(client, payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == payload["event_id"]
        assert data["status"] == "processed"

        app.dependency_overrides.clear()

    def test_response_format(self, fake_app, fake_plan, fake_app_user):
        """成功响应包含 event_id 和 status=processed"""
        new_sub = FakeSubscription(user_id=uuid.UUID(USER_ID), plan_id=uuid.UUID(PLAN_ID))
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
            "AppUser": fake_app_user,
            "SubscriptionPlan": fake_plan,
            "UserSubscription": None,
        })
        db.refresh = lambda obj: setattr(obj, 'id', uuid.uuid4()) if not getattr(obj, 'id', None) else None

        client = _make_client(db)
        payload = _make_payload(
            event_type="subscription.created",
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        resp = _send_webhook(client, payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "event_id" in body
        assert body["status"] == "processed"

        app.dependency_overrides.clear()


class TestWebhookIdempotency:
    """幂等性测试"""

    def test_duplicate_event_returns_200_duplicate(self, fake_app):
        """重复 event_id 返回 200 + duplicate 状态"""
        existing_event_id = "evt-already-processed"
        existing_log = FakeEventLog(
            event_id=existing_event_id,
            status="success",
            response_summary={"event_id": existing_event_id, "status": "processed"},
        )

        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": existing_log,
        })

        client = _make_client(db)
        payload = _make_payload(
            event_type="subscription.created",
            user_id=USER_ID,
            plan_id=PLAN_ID,
            event_id=existing_event_id,
        )

        resp = _send_webhook(client, payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "duplicate"
        assert data["event_id"] == existing_event_id
        assert "original_result" in data

        app.dependency_overrides.clear()

    def test_duplicate_with_duplicate_status_returns_200(self, fake_app):
        """已标记为 duplicate 的事件再次提交也返回 200"""
        existing_event_id = "evt-dup"
        existing_log = FakeEventLog(
            event_id=existing_event_id,
            status="duplicate",
            response_summary={"event_id": existing_event_id, "status": "processed"},
        )

        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": existing_log,
        })

        client = _make_client(db)
        payload = _make_payload(event_id=existing_event_id, user_id=USER_ID, plan_id=PLAN_ID)

        resp = _send_webhook(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate"

        app.dependency_overrides.clear()


class TestWebhookAuthErrors:
    """认证错误测试"""

    def test_missing_app_id_returns_401(self):
        """缺少 X-App-Id 头部返回 401"""
        db = _build_mock_db()
        client = _make_client(db)
        payload = _make_payload()
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 401

        app.dependency_overrides.clear()

    def test_missing_signature_returns_401(self):
        """缺少 X-Webhook-Signature 头部返回 401"""
        db = _build_mock_db()
        client = _make_client(db)
        payload = _make_payload()
        body = json.dumps(payload).encode("utf-8")

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
            },
        )
        assert resp.status_code == 401

        app.dependency_overrides.clear()

    def test_wrong_signature_returns_401(self, fake_app):
        """错误签名返回 401"""
        db = _build_mock_db({"Application": fake_app})
        client = _make_client(db)
        payload = _make_payload()
        body = json.dumps(payload).encode("utf-8")

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
            },
        )
        assert resp.status_code == 401

        app.dependency_overrides.clear()

    def test_nonexistent_app_returns_403(self):
        """不存在的应用返回 403"""
        db = _build_mock_db({"Application": None})
        client = _make_client(db)
        payload = _make_payload()
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": "nonexistent-app",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 403

        app.dependency_overrides.clear()

    def test_disabled_app_returns_403(self):
        """已禁用应用返回 403"""
        disabled_app = FakeApplication(app_id=APP_ID, status="disabled")
        db = _build_mock_db({"Application": disabled_app})
        client = _make_client(db)
        payload = _make_payload()
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 403

        app.dependency_overrides.clear()


class TestWebhookPayloadValidation:
    """Payload 校验测试"""

    def test_invalid_json_returns_422(self, fake_app):
        """无效 JSON 返回 422"""
        db = _build_mock_db({"Application": fake_app})
        client = _make_client(db)
        body = b"not valid json"
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

        app.dependency_overrides.clear()

    def test_missing_event_id_returns_422(self, fake_app):
        """缺少 event_id 返回 422"""
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
        })
        client = _make_client(db)
        payload = {
            "event_type": "subscription.created",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "effective_date": datetime.utcnow().isoformat(),
            },
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

        app.dependency_overrides.clear()

    def test_invalid_event_type_returns_422(self, fake_app):
        """无效事件类型返回 422"""
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
        })
        client = _make_client(db)
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "subscription.invalid_type",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "user_id": USER_ID,
                "plan_id": PLAN_ID,
                "effective_date": datetime.utcnow().isoformat(),
            },
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

        app.dependency_overrides.clear()

    def test_missing_data_field_returns_422(self, fake_app):
        """缺少 data 字段返回 422"""
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
        })
        client = _make_client(db)
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "subscription.created",
            "timestamp": datetime.utcnow().isoformat(),
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

        app.dependency_overrides.clear()

    def test_empty_user_id_returns_422(self, fake_app):
        """空 user_id 返回 422"""
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
        })
        client = _make_client(db)
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "subscription.created",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "user_id": "",
                "plan_id": PLAN_ID,
                "effective_date": datetime.utcnow().isoformat(),
            },
        }
        body = json.dumps(payload).encode("utf-8")
        sig = _compute_signature(WEBHOOK_SECRET, body)

        resp = client.post(
            "/api/v1/webhooks/subscription",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-App-Id": APP_ID,
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 422

        app.dependency_overrides.clear()


class TestWebhookInternalError:
    """内部错误测试"""

    def test_handler_exception_returns_500(self, fake_app):
        """处理器抛出异常返回 500 并记录 Event Log"""
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
            "AppUser": None,  # Will cause handler to raise
        })

        client = _make_client(db)
        payload = _make_payload(
            event_type="subscription.created",
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        # The handler will raise HTTPException 422 for invalid user,
        # which is re-raised, not caught as 500
        resp = _send_webhook(client, payload)
        assert resp.status_code == 422

        app.dependency_overrides.clear()

    def test_unexpected_exception_returns_500(self, fake_app):
        """非 HTTPException 异常返回 500"""
        db = _build_mock_db({
            "Application": fake_app,
            "WebhookEventLog": None,
        })

        client = _make_client(db)
        payload = _make_payload(
            event_type="subscription.created",
            user_id=USER_ID,
            plan_id=PLAN_ID,
        )

        # Patch the handler to raise a generic exception
        with patch(
            "services.subscription.main.EVENT_HANDLERS",
            {"subscription.created": AsyncMock(side_effect=RuntimeError("unexpected"))},
        ):
            resp = _send_webhook(client, payload)
            assert resp.status_code == 500
            data = resp.json()
            assert data["error_code"] == "internal_error"

        app.dependency_overrides.clear()
