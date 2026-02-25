"""
配额重置定时任务单元测试
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import uuid

from shared.models.application import Application, AppSubscriptionPlan
from shared.models.subscription import SubscriptionPlan
from shared.models.quota import AppQuotaOverride, QuotaUsage


class FakeRedis:
    """Fake Redis client for testing"""
    def __init__(self, data=None):
        self._data = data or {}
        self._deleted = []
        self._pipeline_ops = []

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value, ex=None):
        self._data[key] = str(value)

    def delete(self, *keys):
        for key in keys:
            self._data.pop(key, None)
            self._deleted.append(key)

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis_instance):
        self._redis = redis_instance
        self._ops = []

    def set(self, key, value, ex=None):
        self._ops.append(('set', key, value, ex))
        return self

    def delete(self, key):
        self._ops.append(('delete', key))
        return self

    def execute(self):
        for op in self._ops:
            if op[0] == 'set':
                self._redis._data[op[1]] = str(op[2])
            elif op[0] == 'delete':
                self._redis._data.pop(op[1], None)
                self._redis._deleted.append(op[1])
        return [True] * len(self._ops)


def _make_app(app_id="test-app-001"):
    """Create a fake Application object"""
    app = MagicMock(spec=Application)
    app.id = uuid.uuid4()
    app.app_id = app_id
    app.status = "active"
    return app


def _make_plan(request_quota=1000, token_quota=50000, quota_period_days=30):
    """Create a fake SubscriptionPlan object"""
    plan = MagicMock(spec=SubscriptionPlan)
    plan.id = uuid.uuid4()
    plan.request_quota = request_quota
    plan.token_quota = token_quota
    plan.quota_period_days = quota_period_days
    return plan


def _make_binding(app, plan):
    """Create a fake AppSubscriptionPlan object"""
    binding = MagicMock(spec=AppSubscriptionPlan)
    binding.application_id = app.id
    binding.plan_id = plan.id
    return binding


class TestProcessQuotaResets:
    """Tests for process_quota_resets function"""

    @patch('services.subscription.main.create_audit_log')
    @patch('services.subscription.main.get_redis')
    def test_resets_expired_cycle(self, mock_get_redis, mock_audit_log):
        """When a billing cycle has ended, counters should be reset and usage persisted"""
        app = _make_app("app-expired")
        plan = _make_plan(request_quota=1000, token_quota=50000, quota_period_days=30)
        binding = _make_binding(app, plan)

        # Cycle started 31 days ago (expired)
        cycle_start = (datetime.utcnow() - timedelta(days=31)).isoformat()
        fake_redis = FakeRedis({
            "quota:app-expired:requests": "150",
            "quota:app-expired:tokens": "3500",
            "quota:app-expired:cycle_start": cycle_start,
        })
        mock_get_redis.return_value = fake_redis

        db = MagicMock()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
            (app, binding, plan)
        ]
        # No override
        db.query.return_value.filter.return_value.first.return_value = None

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["processed"] == 1
        assert result["reset"] == 1
        assert result["errors"] == 0

        # Verify Redis counters were reset
        assert fake_redis._data["quota:app-expired:requests"] == "0"
        assert fake_redis._data["quota:app-expired:tokens"] == "0"

        # Verify warning flags were cleared
        assert "quota:app-expired:warning_sent:80" in fake_redis._deleted
        assert "quota:app-expired:warning_sent:100" in fake_redis._deleted

        # Verify QuotaUsage was added to db
        db.add.assert_called()
        added_obj = db.add.call_args[0][0]
        assert isinstance(added_obj, QuotaUsage)
        assert added_obj.request_quota_used == 150
        assert added_obj.token_quota_used == 3500
        assert added_obj.reset_type == "auto"
        assert added_obj.request_quota_limit == 1000
        assert added_obj.token_quota_limit == 50000

        # Verify audit log was called
        mock_audit_log.assert_called_once()
        audit_call = mock_audit_log.call_args
        assert audit_call.kwargs["action"] == "quota_reset"
        assert audit_call.kwargs["details"]["reset_type"] == "auto"

    @patch('services.subscription.main.create_audit_log')
    @patch('services.subscription.main.get_redis')
    def test_skips_active_cycle(self, mock_get_redis, mock_audit_log):
        """When a billing cycle has NOT ended, no reset should occur"""
        app = _make_app("app-active")
        plan = _make_plan(quota_period_days=30)
        binding = _make_binding(app, plan)

        # Cycle started 10 days ago (still active)
        cycle_start = (datetime.utcnow() - timedelta(days=10)).isoformat()
        fake_redis = FakeRedis({
            "quota:app-active:requests": "50",
            "quota:app-active:tokens": "1000",
            "quota:app-active:cycle_start": cycle_start,
        })
        mock_get_redis.return_value = fake_redis

        db = MagicMock()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
            (app, binding, plan)
        ]

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["processed"] == 1
        assert result["reset"] == 0
        assert result["errors"] == 0
        mock_audit_log.assert_not_called()

    @patch('services.subscription.main.create_audit_log')
    @patch('services.subscription.main.get_redis')
    def test_skips_no_cycle_start(self, mock_get_redis, mock_audit_log):
        """When no cycle_start exists in Redis, the app should be skipped"""
        app = _make_app("app-no-cycle")
        plan = _make_plan()
        binding = _make_binding(app, plan)

        fake_redis = FakeRedis({})  # No cycle_start key
        mock_get_redis.return_value = fake_redis

        db = MagicMock()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
            (app, binding, plan)
        ]

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["processed"] == 1
        assert result["reset"] == 0
        mock_audit_log.assert_not_called()

    @patch('services.subscription.main.create_audit_log')
    @patch('services.subscription.main.get_redis')
    def test_uses_override_quota(self, mock_get_redis, mock_audit_log):
        """When AppQuotaOverride exists, it should be used instead of plan defaults"""
        app = _make_app("app-override")
        plan = _make_plan(request_quota=1000, token_quota=50000, quota_period_days=30)
        binding = _make_binding(app, plan)

        cycle_start = (datetime.utcnow() - timedelta(days=31)).isoformat()
        fake_redis = FakeRedis({
            "quota:app-override:requests": "200",
            "quota:app-override:tokens": "8000",
            "quota:app-override:cycle_start": cycle_start,
        })
        mock_get_redis.return_value = fake_redis

        override = MagicMock(spec=AppQuotaOverride)
        override.request_quota = 2000
        override.token_quota = 100000

        db = MagicMock()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
            (app, binding, plan)
        ]
        db.query.return_value.filter.return_value.first.return_value = override

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["reset"] == 1
        added_obj = db.add.call_args[0][0]
        assert added_obj.request_quota_limit == 2000
        assert added_obj.token_quota_limit == 100000

    @patch('services.subscription.main.get_redis')
    def test_redis_connection_failure(self, mock_get_redis):
        """When Redis is unavailable, should return error gracefully"""
        mock_get_redis.side_effect = Exception("Connection refused")

        db = MagicMock()

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["processed"] == 0
        assert result["errors"] == 1
        assert "Redis" in result.get("error_message", "")

    @patch('services.subscription.main.create_audit_log')
    @patch('services.subscription.main.get_redis')
    def test_no_active_apps(self, mock_get_redis, mock_audit_log):
        """When there are no active apps with subscriptions, should return zero counts"""
        fake_redis = FakeRedis({})
        mock_get_redis.return_value = fake_redis

        db = MagicMock()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["processed"] == 0
        assert result["reset"] == 0
        assert result["errors"] == 0

    @patch('services.subscription.main.create_audit_log')
    @patch('services.subscription.main.get_redis')
    def test_multiple_apps_mixed(self, mock_get_redis, mock_audit_log):
        """Multiple apps: one expired, one active - only expired should be reset"""
        app1 = _make_app("app-expired-multi")
        app2 = _make_app("app-active-multi")
        plan = _make_plan(quota_period_days=30)
        binding1 = _make_binding(app1, plan)
        binding2 = _make_binding(app2, plan)

        expired_start = (datetime.utcnow() - timedelta(days=31)).isoformat()
        active_start = (datetime.utcnow() - timedelta(days=5)).isoformat()

        fake_redis = FakeRedis({
            "quota:app-expired-multi:requests": "100",
            "quota:app-expired-multi:tokens": "2000",
            "quota:app-expired-multi:cycle_start": expired_start,
            "quota:app-active-multi:requests": "50",
            "quota:app-active-multi:tokens": "1000",
            "quota:app-active-multi:cycle_start": active_start,
        })
        mock_get_redis.return_value = fake_redis

        db = MagicMock()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
            (app1, binding1, plan),
            (app2, binding2, plan),
        ]
        db.query.return_value.filter.return_value.first.return_value = None

        from services.subscription.main import process_quota_resets
        result = process_quota_resets(db)

        assert result["processed"] == 2
        assert result["reset"] == 1
        assert result["errors"] == 0


class TestTriggerQuotaResetEndpoint:
    """Tests for the trigger_quota_reset_processing endpoint"""

    @patch('services.subscription.main.process_quota_resets')
    def test_trigger_endpoint(self, mock_process):
        """The trigger endpoint should call process_quota_resets and return its result"""
        from fastapi.testclient import TestClient
        from services.subscription.main import app

        mock_process.return_value = {
            "processed": 5,
            "reset": 2,
            "errors": 0,
            "timestamp": "2024-01-01T00:00:00"
        }

        client = TestClient(app)
        response = client.post("/api/v1/admin/subscriptions/process-quota-resets")

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == 5
        assert data["reset"] == 2
        assert data["errors"] == 0
        mock_process.assert_called_once()
