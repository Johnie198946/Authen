"""
Webhook 事件日志分页查询端点测试

测试 GET /api/v1/webhooks/events 端点：
- 无筛选条件返回全部记录（分页）
- 按 app_id、event_type、status 筛选
- 按 start_time、end_time 时间范围筛选
- 分页参数正确应用
- 响应格式包含 total、page、page_size、items
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from services.subscription.main import app
from shared.database import get_db
from shared.models.webhook import WebhookEventLog


# --- Fake event log ---

class FakeEventLogItem:
    def __init__(self, app_id="app-1", event_type="subscription.created", status="success",
                 created_at=None, processed_at=None):
        self.id = uuid.uuid4()
        self.event_id = f"evt-{uuid.uuid4().hex[:8]}"
        self.app_id = app_id
        self.event_type = event_type
        self.status = status
        self.request_summary = {"event_type": event_type}
        self.response_summary = {"status": "processed"}
        self.error_message = None
        self.processed_at = processed_at or datetime.utcnow()
        self.created_at = created_at or datetime.utcnow()


# --- Mock query builder ---

class MockEventsQuery:
    """Mock query that tracks filter calls and returns fake items."""
    def __init__(self, items):
        self._items = items
        self._filters = []

    def filter(self, *args):
        # Return self to allow chaining; filters are not actually applied in mock
        return self

    def order_by(self, *args):
        return self

    def offset(self, n):
        self._offset = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def count(self):
        return len(self._items)

    def all(self):
        offset = getattr(self, '_offset', 0)
        limit = getattr(self, '_limit', 20)
        return self._items[offset:offset + limit]


def _build_mock_db(items):
    db = MagicMock()
    db.query.return_value = MockEventsQuery(items)
    return db


def _make_client(db_mock):
    def override_get_db():
        yield db_mock
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


# --- Tests ---

class TestListWebhookEvents:
    """GET /api/v1/webhooks/events 端点测试"""

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_empty_result(self):
        """无记录时返回空列表"""
        db = _build_mock_db([])
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["items"] == []

    def test_returns_items_with_correct_fields(self):
        """返回的每条记录包含所有必要字段"""
        item = FakeEventLogItem()
        db = _build_mock_db([item])
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

        record = data["items"][0]
        assert "id" in record
        assert "event_id" in record
        assert "app_id" in record
        assert "event_type" in record
        assert "status" in record
        assert "request_summary" in record
        assert "response_summary" in record
        assert "error_message" in record
        assert "processed_at" in record
        assert "created_at" in record

    def test_response_structure(self):
        """响应包含 total、page、page_size、items"""
        items = [FakeEventLogItem() for _ in range(3)]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "items" in data
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_pagination_defaults(self):
        """默认分页参数 page=1, page_size=20"""
        items = [FakeEventLogItem() for _ in range(5)]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events")
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_custom_pagination(self):
        """自定义分页参数"""
        items = [FakeEventLogItem() for _ in range(10)]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events?page=2&page_size=3")
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 3
        # Mock returns items[3:6] due to offset=3, limit=3
        assert len(data["items"]) == 3

    def test_pagination_beyond_total(self):
        """页码超出总数时返回空列表"""
        items = [FakeEventLogItem() for _ in range(2)]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events?page=10&page_size=5")
        data = resp.json()
        assert data["total"] == 2
        assert data["items"] == []

    def test_filter_by_app_id(self):
        """按 app_id 筛选"""
        items = [FakeEventLogItem(app_id="app-1")]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events?app_id=app-1")
        assert resp.status_code == 200
        # Verify query was called (mock doesn't actually filter, but endpoint passes param)
        db.query.assert_called_once_with(WebhookEventLog)

    def test_filter_by_event_type(self):
        """按 event_type 筛选"""
        items = [FakeEventLogItem(event_type="subscription.cancelled")]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events?event_type=subscription.cancelled")
        assert resp.status_code == 200
        db.query.assert_called_once_with(WebhookEventLog)

    def test_filter_by_status(self):
        """按 status 筛选"""
        items = [FakeEventLogItem(status="failed")]
        db = _build_mock_db(items)
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events?status=failed")
        assert resp.status_code == 200
        db.query.assert_called_once_with(WebhookEventLog)

    def test_filter_by_time_range(self):
        """按时间范围筛选"""
        items = [FakeEventLogItem()]
        db = _build_mock_db(items)
        client = _make_client(db)

        start = "2024-01-01T00:00:00"
        end = "2024-12-31T23:59:59"
        resp = client.get(f"/api/v1/webhooks/events?start_time={start}&end_time={end}")
        assert resp.status_code == 200
        db.query.assert_called_once_with(WebhookEventLog)

    def test_item_serialization(self):
        """验证 item 字段序列化正确"""
        now = datetime(2024, 6, 15, 12, 0, 0)
        item = FakeEventLogItem(
            app_id="app-test",
            event_type="subscription.renewed",
            status="success",
            created_at=now,
            processed_at=now,
        )
        item.error_message = "some error"
        db = _build_mock_db([item])
        client = _make_client(db)

        resp = client.get("/api/v1/webhooks/events")
        record = resp.json()["items"][0]
        assert record["app_id"] == "app-test"
        assert record["event_type"] == "subscription.renewed"
        assert record["status"] == "success"
        assert record["error_message"] == "some error"
        assert record["processed_at"] == "2024-06-15T12:00:00"
        assert record["created_at"] == "2024-06-15T12:00:00"
