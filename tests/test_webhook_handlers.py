"""
Webhook 事件处理器单元测试

测试六种事件类型的处理函数：
- handle_subscription_created: 创建活跃订阅
- handle_subscription_renewed: 更新到期日期
- handle_subscription_upgraded: 升级订阅计划
- handle_subscription_downgraded: 降级订阅计划
- handle_subscription_cancelled: 取消订阅
- handle_subscription_expired: 订阅到期

每个处理函数校验 user_id 的 AppUser 绑定关系和 plan_id 有效性。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi import HTTPException

from services.subscription.webhook_handlers import (
    handle_subscription_created,
    handle_subscription_renewed,
    handle_subscription_upgraded,
    handle_subscription_downgraded,
    handle_subscription_cancelled,
    handle_subscription_expired,
    _validate_app_user,
    _validate_plan,
)


# --- Fake model objects ---

class FakeApplication:
    def __init__(self, app_id="test-app", id_val=None):
        self.id = id_val or uuid.uuid4()
        self.app_id = app_id
        self.status = "active"


class FakeAppUser:
    def __init__(self, application_id, user_id):
        self.id = uuid.uuid4()
        self.application_id = application_id
        self.user_id = user_id


class FakePlan:
    def __init__(self, plan_id=None, is_active=True, duration_days=30):
        self.id = plan_id or uuid.uuid4()
        self.is_active = is_active
        self.duration_days = duration_days


class FakeSubscription:
    def __init__(self, user_id, plan_id, status="active"):
        self.id = uuid.uuid4()
        self.user_id = user_id
        self.plan_id = plan_id
        self.status = status
        self.start_date = datetime.utcnow()
        self.end_date = datetime.utcnow() + timedelta(days=30)
        self.updated_at = datetime.utcnow()


# --- Mock DB helper ---

def _build_mock_db(query_map=None):
    """
    Build a mock db session that supports multiple model queries.

    query_map: dict mapping model class -> list of (filter_result, method) tuples
    For simplicity, we use a side_effect approach based on the model queried.
    """
    mock_db = MagicMock()

    # Store call counts per model to support sequential queries
    call_counts = {}

    def query_side_effect(model):
        mock_query = MagicMock()

        if query_map and model in query_map:
            results = query_map[model]
            key = model.__name__
            if key not in call_counts:
                call_counts[key] = 0
            idx = min(call_counts[key], len(results) - 1)
            call_counts[key] += 1
            result = results[idx]

            mock_filter = MagicMock()
            mock_filter.first.return_value = result
            mock_query.filter.return_value = mock_filter
        else:
            mock_filter = MagicMock()
            mock_filter.first.return_value = None
            mock_query.filter.return_value = mock_filter

        return mock_query

    mock_db.query.side_effect = query_side_effect
    return mock_db


# --- Fixtures ---

@pytest.fixture
def app_id():
    return "test-app-001"


@pytest.fixture
def user_id():
    return str(uuid.uuid4())


@pytest.fixture
def plan_id():
    return str(uuid.uuid4())


@pytest.fixture
def base_data(user_id, plan_id):
    return {
        "user_id": user_id,
        "plan_id": plan_id,
        "effective_date": "2024-01-01T00:00:00",
        "expiry_date": "2024-12-31T23:59:59",
    }


def run_async(coro):
    """Helper to run async functions in tests."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ============================================================
# Tests for validation helpers
# ============================================================

class TestValidateAppUser:
    """Tests for _validate_app_user"""

    def test_valid_binding(self, app_id, user_id):
        """Valid AppUser binding should return user UUID."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, uuid.UUID(user_id))

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
        })

        result = _validate_app_user(app_id, user_id, db)
        assert result == uuid.UUID(user_id)

    def test_app_not_found(self, app_id, user_id):
        """Missing application should raise 422."""
        from shared.models.application import Application, AppUser

        db = _build_mock_db({
            Application: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            _validate_app_user(app_id, user_id, db)
        assert exc_info.value.status_code == 422
        assert "用户不属于该应用" in exc_info.value.detail

    def test_no_binding(self, app_id, user_id):
        """User not bound to app should raise 422."""
        from shared.models.application import Application, AppUser

        fake_app = FakeApplication(app_id)
        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            _validate_app_user(app_id, user_id, db)
        assert exc_info.value.status_code == 422

    def test_invalid_user_id_format(self, app_id):
        """Invalid UUID format for user_id should raise 422."""
        from shared.models.application import Application
        db = _build_mock_db({Application: [FakeApplication(app_id)]})

        with pytest.raises(HTTPException) as exc_info:
            _validate_app_user(app_id, "not-a-uuid", db)
        assert exc_info.value.status_code == 422


class TestValidatePlan:
    """Tests for _validate_plan"""

    def test_valid_active_plan(self, plan_id):
        """Active plan should return plan UUID."""
        from shared.models.subscription import SubscriptionPlan

        fake_plan = FakePlan(uuid.UUID(plan_id), is_active=True)
        db = _build_mock_db({SubscriptionPlan: [fake_plan]})

        result = _validate_plan(plan_id, db)
        assert result == uuid.UUID(plan_id)

    def test_plan_not_found(self, plan_id):
        """Missing plan should raise 422."""
        from shared.models.subscription import SubscriptionPlan

        db = _build_mock_db({SubscriptionPlan: [None]})

        with pytest.raises(HTTPException) as exc_info:
            _validate_plan(plan_id, db)
        assert exc_info.value.status_code == 422
        assert "订阅计划无效" in exc_info.value.detail

    def test_inactive_plan(self, plan_id):
        """Inactive plan should raise 422."""
        from shared.models.subscription import SubscriptionPlan

        fake_plan = FakePlan(uuid.UUID(plan_id), is_active=False)
        db = _build_mock_db({SubscriptionPlan: [fake_plan]})

        with pytest.raises(HTTPException) as exc_info:
            _validate_plan(plan_id, db)
        assert exc_info.value.status_code == 422

    def test_invalid_plan_id_format(self):
        """Invalid UUID format for plan_id should raise 422."""
        from shared.models.subscription import SubscriptionPlan
        db = _build_mock_db({SubscriptionPlan: [None]})

        with pytest.raises(HTTPException) as exc_info:
            _validate_plan("not-a-uuid", db)
        assert exc_info.value.status_code == 422


# ============================================================
# Tests for event handlers
# ============================================================

class TestHandleSubscriptionCreated:
    """Tests for handle_subscription_created"""

    def test_creates_active_subscription(self, app_id, base_data):
        """Should create an active subscription record."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True, duration_days=365)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan, fake_plan],  # called twice: validate + end_date calc
        })

        # Mock the add/commit/refresh cycle
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)
        db.refresh.side_effect = lambda obj: setattr(obj, 'id', uuid.uuid4())

        result = run_async(handle_subscription_created(app_id, base_data, db))

        assert result["action"] == "created"
        assert result["status"] == "active"
        assert result["user_id"] == str(user_uuid)
        assert result["plan_id"] == str(plan_uuid)
        assert len(added_objects) == 1
        assert added_objects[0].status == "active"
        db.commit.assert_called_once()

    def test_invalid_user_raises_422(self, app_id, base_data):
        """Should raise 422 when user is not bound to app."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan

        fake_app = FakeApplication(app_id)
        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            run_async(handle_subscription_created(app_id, base_data, db))
        assert exc_info.value.status_code == 422

    def test_invalid_plan_raises_422(self, app_id, base_data):
        """Should raise 422 when plan is invalid."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan

        user_uuid = uuid.UUID(base_data["user_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            run_async(handle_subscription_created(app_id, base_data, db))
        assert exc_info.value.status_code == 422


class TestHandleSubscriptionRenewed:
    """Tests for handle_subscription_renewed"""

    def test_updates_end_date(self, app_id, base_data):
        """Should update subscription end_date."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)
        fake_sub = FakeSubscription(user_uuid, plan_uuid)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [fake_sub],
        })

        result = run_async(handle_subscription_renewed(app_id, base_data, db))

        assert result["action"] == "renewed"
        assert result["user_id"] == str(user_uuid)
        assert "new_end_date" in result
        db.commit.assert_called_once()

    def test_no_active_subscription_raises_422(self, app_id, base_data):
        """Should raise 422 when no active subscription found."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            run_async(handle_subscription_renewed(app_id, base_data, db))
        assert exc_info.value.status_code == 422
        assert "未找到活跃订阅" in exc_info.value.detail


class TestHandleSubscriptionUpgraded:
    """Tests for handle_subscription_upgraded"""

    def test_updates_plan(self, app_id, base_data):
        """Should update subscription plan_id."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        old_plan_id = uuid.uuid4()
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)
        fake_sub = FakeSubscription(user_uuid, old_plan_id)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [fake_sub],
        })

        result = run_async(handle_subscription_upgraded(app_id, base_data, db))

        assert result["action"] == "upgraded"
        assert result["new_plan_id"] == str(plan_uuid)
        assert result["old_plan_id"] == str(old_plan_id)
        assert fake_sub.plan_id == plan_uuid
        db.commit.assert_called_once()


class TestHandleSubscriptionDowngraded:
    """Tests for handle_subscription_downgraded"""

    def test_updates_plan(self, app_id, base_data):
        """Should update subscription plan_id on downgrade."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        old_plan_id = uuid.uuid4()
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)
        fake_sub = FakeSubscription(user_uuid, old_plan_id)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [fake_sub],
        })

        result = run_async(handle_subscription_downgraded(app_id, base_data, db))

        assert result["action"] == "downgraded"
        assert result["new_plan_id"] == str(plan_uuid)
        assert fake_sub.plan_id == plan_uuid
        db.commit.assert_called_once()


class TestHandleSubscriptionCancelled:
    """Tests for handle_subscription_cancelled"""

    def test_sets_status_cancelled(self, app_id, base_data):
        """Should set subscription status to cancelled."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)
        fake_sub = FakeSubscription(user_uuid, plan_uuid)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [fake_sub],
        })

        result = run_async(handle_subscription_cancelled(app_id, base_data, db))

        assert result["action"] == "cancelled"
        assert result["status"] == "cancelled"
        assert fake_sub.status == "cancelled"
        db.commit.assert_called_once()

    def test_no_active_subscription_raises_422(self, app_id, base_data):
        """Should raise 422 when no active subscription found."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            run_async(handle_subscription_cancelled(app_id, base_data, db))
        assert exc_info.value.status_code == 422


class TestHandleSubscriptionExpired:
    """Tests for handle_subscription_expired"""

    def test_sets_status_expired(self, app_id, base_data):
        """Should set subscription status to expired."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)
        fake_sub = FakeSubscription(user_uuid, plan_uuid)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [fake_sub],
        })

        result = run_async(handle_subscription_expired(app_id, base_data, db))

        assert result["action"] == "expired"
        assert result["status"] == "expired"
        assert fake_sub.status == "expired"
        db.commit.assert_called_once()

    def test_no_active_subscription_raises_422(self, app_id, base_data):
        """Should raise 422 when no active subscription found."""
        from shared.models.application import Application, AppUser
        from shared.models.subscription import SubscriptionPlan, UserSubscription

        user_uuid = uuid.UUID(base_data["user_id"])
        plan_uuid = uuid.UUID(base_data["plan_id"])
        fake_app = FakeApplication(app_id)
        fake_binding = FakeAppUser(fake_app.id, user_uuid)
        fake_plan = FakePlan(plan_uuid, is_active=True)

        db = _build_mock_db({
            Application: [fake_app],
            AppUser: [fake_binding],
            SubscriptionPlan: [fake_plan],
            UserSubscription: [None],
        })

        with pytest.raises(HTTPException) as exc_info:
            run_async(handle_subscription_expired(app_id, base_data, db))
        assert exc_info.value.status_code == 422
