"""
Gateway Service 主应用测试

测试 /health、/api/v1/gateway/info 端点和中间件注册。

需求: 8.1, 8.3, 8.4
"""
import sys
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from services.gateway.main import (
    app,
    GATEWAY_VERSION,
    SUPPORTED_API_VERSIONS,
    AVAILABLE_LOGIN_METHODS,
    DOWNSTREAM_SERVICES,
)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /api/v1/gateway/info 端点
# ---------------------------------------------------------------------------

class TestGatewayInfo:
    """测试 /api/v1/gateway/info 端点 (需求 8.4)"""

    def test_info_returns_version(self, client):
        resp = client.get("/api/v1/gateway/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == GATEWAY_VERSION

    def test_info_returns_supported_api_versions(self, client):
        resp = client.get("/api/v1/gateway/info")
        data = resp.json()
        assert data["supported_api_versions"] == SUPPORTED_API_VERSIONS
        assert "v1" in data["supported_api_versions"]

    def test_info_returns_available_login_methods(self, client):
        resp = client.get("/api/v1/gateway/info")
        data = resp.json()
        assert data["available_login_methods"] == AVAILABLE_LOGIN_METHODS
        assert "email" in data["available_login_methods"]
        assert "phone" in data["available_login_methods"]
        assert "wechat" in data["available_login_methods"]
        assert "alipay" in data["available_login_methods"]
        assert "google" in data["available_login_methods"]
        assert "apple" in data["available_login_methods"]

    def test_info_response_structure(self, client):
        resp = client.get("/api/v1/gateway/info")
        data = resp.json()
        assert set(data.keys()) == {"version", "supported_api_versions", "available_login_methods"}


# ---------------------------------------------------------------------------
# RequestId 中间件
# ---------------------------------------------------------------------------

class TestRequestIdMiddleware:
    """测试 RequestIdMiddleware 为每个请求生成唯一 request_id (需求 9.3)"""

    def test_response_has_x_request_id_header(self, client):
        resp = client.get("/api/v1/gateway/info")
        assert "X-Request-Id" in resp.headers

    def test_request_id_is_valid_uuid(self, client):
        import uuid
        resp = client.get("/api/v1/gateway/info")
        request_id = resp.headers["X-Request-Id"]
        # Should not raise
        uuid.UUID(request_id)

    def test_different_requests_get_different_ids(self, client):
        resp1 = client.get("/api/v1/gateway/info")
        resp2 = client.get("/api/v1/gateway/info")
        assert resp1.headers["X-Request-Id"] != resp2.headers["X-Request-Id"]


# ---------------------------------------------------------------------------
# /health 端点
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """测试 /health 端点 (需求 8.1)"""

    @patch("services.gateway.main.check_overall_health")
    @patch("services.gateway.main.httpx.AsyncClient")
    def test_health_returns_downstream_services(self, mock_client_cls, mock_health, client):
        """健康检查应包含所有下游微服务状态"""
        mock_health.return_value = {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy", "message": "OK"},
                "redis": {"status": "healthy", "message": "OK"},
            },
        }

        # Mock httpx client to simulate downstream services
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()

        assert "status" in data
        assert "components" in data
        # Should have downstream service entries
        components = data["components"]
        for service_key in DOWNSTREAM_SERVICES:
            assert f"downstream_{service_key}" in components

    @patch("services.gateway.main.check_overall_health")
    @patch("services.gateway.main.httpx.AsyncClient")
    def test_health_marks_unavailable_service_as_unhealthy(self, mock_client_cls, mock_health, client):
        """不可用的下游服务应标记为 unhealthy"""
        mock_health.return_value = {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy", "message": "OK"},
                "redis": {"status": "healthy", "message": "OK"},
            },
        }

        # Simulate connection failure
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = client.get("/health")
        data = resp.json()

        # All downstream services should be unhealthy
        for service_key in DOWNSTREAM_SERVICES:
            assert data["components"][f"downstream_{service_key}"]["status"] == "unhealthy"

    @patch("services.gateway.main.check_overall_health")
    @patch("services.gateway.main.httpx.AsyncClient")
    def test_health_degraded_when_some_services_down(self, mock_client_cls, mock_health, client):
        """部分服务不可用时应返回 degraded 状态"""
        mock_health.return_value = {
            "status": "healthy",
            "components": {
                "database": {"status": "healthy", "message": "OK"},
                "redis": {"status": "healthy", "message": "OK"},
            },
        }

        # Simulate mixed availability
        call_count = 0

        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                resp = MagicMock()
                resp.status_code = 200
                return resp
            raise Exception("Connection refused")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = client.get("/health")
        data = resp.json()

        assert data["status"] == "degraded"
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 根路径
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    def test_root_returns_service_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "统一 API 网关"
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# 异常处理器
# ---------------------------------------------------------------------------

class TestExceptionHandlers:
    """测试统一错误处理器注册 (需求 9.1)"""

    def test_404_returns_unified_error_format(self, client):
        resp = client.get("/nonexistent-path")
        assert resp.status_code == 404
        data = resp.json()
        assert "error_code" in data
        assert "message" in data
        assert "request_id" in data

    def test_error_response_has_request_id_header(self, client):
        resp = client.get("/nonexistent-path")
        assert "X-Request-Id" in resp.headers
