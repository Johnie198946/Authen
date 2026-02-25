"""
Admin Service Webhook 事件日志代理接口测试

测试 Task 6.2: 管理服务代理调用订阅服务的事件日志查询接口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from services.admin.main import app


client = TestClient(app)


MOCK_EVENTS_RESPONSE = {
    "total": 2,
    "page": 1,
    "page_size": 20,
    "items": [
        {
            "id": "aaa-bbb",
            "event_id": "evt_001",
            "app_id": "app_123",
            "event_type": "subscription.created",
            "status": "success",
            "request_summary": {"user_id": "u1"},
            "response_summary": None,
            "error_message": None,
            "processed_at": "2024-01-01T00:00:00",
            "created_at": "2024-01-01T00:00:00",
        },
        {
            "id": "ccc-ddd",
            "event_id": "evt_002",
            "app_id": "app_123",
            "event_type": "subscription.cancelled",
            "status": "failed",
            "request_summary": None,
            "response_summary": None,
            "error_message": "plan not found",
            "processed_at": None,
            "created_at": "2024-01-02T00:00:00",
        },
    ],
}


def _make_mock_client(response_data=None, side_effect=None):
    """Create a mock httpx.AsyncClient with proper async context manager support."""
    mock_client = AsyncMock()

    if side_effect:
        mock_client.get.side_effect = side_effect
    else:
        # httpx.Response.json() and .raise_for_status() are sync methods
        mock_resp = MagicMock()
        mock_resp.json.return_value = response_data
        mock_resp.raise_for_status.return_value = None
        mock_client.get.return_value = mock_resp

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestAdminWebhookEventsProxy:
    """Tests for GET /api/v1/admin/webhook-events proxy endpoint."""

    @patch("services.admin.main.httpx.AsyncClient")
    def test_proxy_forwards_all_params(self, mock_client_cls):
        """All query parameters are forwarded to the subscription service."""
        mock_client = _make_mock_client(MOCK_EVENTS_RESPONSE)
        mock_client_cls.return_value = mock_client

        resp = client.get(
            "/api/v1/admin/webhook-events",
            params={
                "app_id": "app_123",
                "event_type": "subscription.created",
                "status": "success",
                "start_time": "2024-01-01T00:00:00",
                "end_time": "2024-12-31T23:59:59",
                "page": 2,
                "page_size": 10,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Verify the call was made with correct URL and params
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "http://localhost:8006/api/v1/webhooks/events"
        params = call_args[1]["params"]
        assert params["app_id"] == "app_123"
        assert params["event_type"] == "subscription.created"
        assert params["status"] == "success"
        assert params["start_time"] == "2024-01-01T00:00:00"
        assert params["end_time"] == "2024-12-31T23:59:59"
        assert params["page"] == 2
        assert params["page_size"] == 10

    @patch("services.admin.main.httpx.AsyncClient")
    def test_proxy_no_optional_params(self, mock_client_cls):
        """When no optional filters are provided, only page/page_size are forwarded."""
        mock_client = _make_mock_client({"total": 0, "page": 1, "page_size": 20, "items": []})
        mock_client_cls.return_value = mock_client

        resp = client.get("/api/v1/admin/webhook-events")

        assert resp.status_code == 200
        params = mock_client.get.call_args[1]["params"]
        assert "app_id" not in params
        assert "event_type" not in params
        assert "status" not in params
        assert "start_time" not in params
        assert "end_time" not in params
        assert params["page"] == 1
        assert params["page_size"] == 20

    @patch("services.admin.main.httpx.AsyncClient")
    def test_proxy_timeout_returns_502(self, mock_client_cls):
        """Timeout from subscription service returns 502."""
        mock_client = _make_mock_client(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        resp = client.get("/api/v1/admin/webhook-events")

        assert resp.status_code == 502
        assert "超时" in resp.json()["detail"]

    @patch("services.admin.main.httpx.AsyncClient")
    def test_proxy_connection_error_returns_502(self, mock_client_cls):
        """Connection error to subscription service returns 502."""
        mock_client = _make_mock_client(side_effect=httpx.ConnectError("connection refused"))
        mock_client_cls.return_value = mock_client

        resp = client.get("/api/v1/admin/webhook-events")

        assert resp.status_code == 502
        assert "无法连接" in resp.json()["detail"]

    @patch("services.admin.main.httpx.AsyncClient")
    def test_proxy_upstream_error_forwarded(self, mock_client_cls):
        """HTTP errors from subscription service are forwarded."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_request = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=mock_request, response=mock_resp
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        resp = client.get("/api/v1/admin/webhook-events")

        assert resp.status_code == 500
