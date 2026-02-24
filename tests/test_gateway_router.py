"""
内部服务路由器单元测试

测试 services/gateway/router.py 中的 ServiceRouter 类：
- forward: 转发请求到下游服务
- 超时处理: 10 秒超时返回 503
- 下游不可用: 连接失败返回 503
- 非预期错误格式: 返回 502 upstream_error
- 成功响应透传
- 错误响应格式转换
"""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.router import ServiceRouter, get_service_router, DEFAULT_TIMEOUT


# ==================== Fixtures ====================

@pytest.fixture
def router():
    """创建测试用 ServiceRouter 实例"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    return ServiceRouter(client=mock_client)


@pytest.fixture
def mock_response():
    """创建 mock httpx.Response 的工厂函数"""
    def _make(status_code=200, json_data=None, text="", is_json=True):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.text = text
        if is_json and json_data is not None:
            resp.json.return_value = json_data
        elif not is_json:
            resp.json.side_effect = ValueError("No JSON")
        else:
            resp.json.return_value = json_data or {}
        return resp
    return _make


# ==================== ServiceRouter.__init__ ====================

class TestServiceRouterInit:
    """ServiceRouter 初始化测试"""

    def test_default_services(self):
        """默认服务映射应包含 auth/sso/user/permission"""
        router = ServiceRouter()
        assert "auth" in router.services
        assert "sso" in router.services
        assert "user" in router.services
        assert "permission" in router.services
        assert router.services["auth"] == "http://localhost:8001"

    def test_custom_services(self):
        """支持自定义服务映射"""
        custom = {"auth": "http://custom:9001"}
        router = ServiceRouter(services=custom)
        assert router.services == custom

    def test_default_timeout(self):
        """默认超时应为 10 秒"""
        assert DEFAULT_TIMEOUT == 10.0

    def test_custom_client(self):
        """支持注入自定义 httpx 客户端"""
        mock_client = AsyncMock()
        router = ServiceRouter(client=mock_client)
        assert router.client is mock_client


# ==================== ServiceRouter.forward ====================

class TestForwardSuccess:
    """forward 成功场景测试"""

    @pytest.mark.asyncio
    async def test_forward_success_json(self, router, mock_response):
        """成功的 JSON 响应应被透传"""
        resp = mock_response(200, {"user_id": "123", "token": "abc"})
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/login", json={"id": "test"})

        assert result["status_code"] == 200
        assert result["body"]["user_id"] == "123"
        router.client.request.assert_called_once_with(
            "POST", "http://localhost:8001/api/v1/auth/login", json={"id": "test"}
        )

    @pytest.mark.asyncio
    async def test_forward_passes_kwargs(self, router, mock_response):
        """额外参数应被传递给 httpx"""
        resp = mock_response(200, {"ok": True})
        router.client.request = AsyncMock(return_value=resp)

        headers = {"Authorization": "Bearer token123"}
        await router.forward("user", "GET", "/api/v1/users/1", headers=headers)

        router.client.request.assert_called_once_with(
            "GET", "http://localhost:8003/api/v1/users/1", headers=headers
        )


class TestForwardDownstreamUnavailable:
    """下游服务不可用测试 (需求 8.2)"""

    @pytest.mark.asyncio
    async def test_connect_error_returns_503(self, router):
        """连接失败应返回 503 service_unavailable"""
        router.client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        assert result["status_code"] == 503
        assert result["body"]["error_code"] == "service_unavailable"

    @pytest.mark.asyncio
    async def test_connect_timeout_returns_503(self, router):
        """连接超时应返回 503 service_unavailable"""
        router.client.request = AsyncMock(side_effect=httpx.ConnectTimeout("Timed out"))

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        assert result["status_code"] == 503
        assert result["body"]["error_code"] == "service_unavailable"

    @pytest.mark.asyncio
    async def test_read_timeout_returns_503(self, router):
        """读取超时应返回 503 service_unavailable"""
        router.client.request = AsyncMock(side_effect=httpx.ReadTimeout("Read timed out"))

        result = await router.forward("auth", "GET", "/api/v1/auth/status")

        assert result["status_code"] == 503
        assert result["body"]["error_code"] == "service_unavailable"

    @pytest.mark.asyncio
    async def test_generic_http_error_returns_502(self, router):
        """其他 HTTP 传输错误应返回 502 upstream_error"""
        router.client.request = AsyncMock(side_effect=httpx.HTTPError("Unknown error"))

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        assert result["status_code"] == 502
        assert result["body"]["error_code"] == "upstream_error"


class TestForwardUnknownService:
    """未知服务测试"""

    @pytest.mark.asyncio
    async def test_unknown_service_returns_502(self, router):
        """未知服务名应返回 502"""
        result = await router.forward("nonexistent", "GET", "/api/v1/test")

        assert result["status_code"] == 502
        assert result["body"]["error_code"] == "upstream_error"


class TestForwardErrorResponses:
    """下游错误响应处理测试 (需求 9.2, 9.4)"""

    @pytest.mark.asyncio
    async def test_fastapi_error_format_converted(self, router, mock_response):
        """FastAPI 标准错误格式应被转换为统一格式"""
        resp = mock_response(422, {"detail": "Validation error", "error_code": "validation_error"})
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        assert result["status_code"] == 422
        assert result["body"]["error_code"] == "validation_error"
        assert result["body"]["message"] == "Validation error"

    @pytest.mark.asyncio
    async def test_unified_error_format_passthrough(self, router, mock_response):
        """已经是统一格式的错误应直接透传"""
        resp = mock_response(401, {"error_code": "token_expired", "message": "Token 已过期"})
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/refresh")

        assert result["status_code"] == 401
        assert result["body"]["error_code"] == "token_expired"
        assert result["body"]["message"] == "Token 已过期"

    @pytest.mark.asyncio
    async def test_unexpected_error_format_returns_502(self, router, mock_response):
        """非预期的错误格式应返回 502 upstream_error (需求 9.4)"""
        resp = mock_response(500, {"unexpected_field": "some value"})
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        assert result["status_code"] == 502
        assert result["body"]["error_code"] == "upstream_error"
        assert "非预期" in result["body"]["message"]

    @pytest.mark.asyncio
    async def test_non_json_error_returns_502(self, router, mock_response):
        """非 JSON 错误响应应返回 502 upstream_error"""
        resp = mock_response(500, None, text="Internal Server Error", is_json=False)
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        assert result["status_code"] == 502
        assert result["body"]["error_code"] == "upstream_error"

    @pytest.mark.asyncio
    async def test_error_response_hides_internal_details(self, router, mock_response):
        """错误响应不应泄露内部微服务实现细节 (需求 9.2)"""
        resp = mock_response(500, {
            "detail": "SQLAlchemy error: connection to postgres failed",
            "traceback": "File /app/services/auth/main.py line 42..."
        })
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/login")

        body = result["body"]
        # 5xx 错误不应包含 traceback 等内部信息
        assert "traceback" not in body
        assert "SQLAlchemy" not in body.get("message", "")
        assert body["error_code"] == "upstream_error"

    @pytest.mark.asyncio
    async def test_4xx_error_preserves_business_detail(self, router, mock_response):
        """4xx 错误应保留业务相关的 detail 信息"""
        resp = mock_response(400, {"detail": "邮箱格式不正确"})
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "POST", "/api/v1/auth/register/email")

        assert result["status_code"] == 400
        assert result["body"]["message"] == "邮箱格式不正确"


class TestForwardNonJsonSuccess:
    """非 JSON 成功响应测试"""

    @pytest.mark.asyncio
    async def test_non_json_success_returns_text(self, router, mock_response):
        """非 JSON 的成功响应应返回 text"""
        resp = mock_response(200, None, text="OK", is_json=False)
        router.client.request = AsyncMock(return_value=resp)

        result = await router.forward("auth", "GET", "/health")

        assert result["status_code"] == 200
        assert result["body"]["data"] == "OK"


# ==================== get_service_router ====================

class TestGetServiceRouter:
    """get_service_router 单例测试"""

    def test_returns_service_router_instance(self):
        """应返回 ServiceRouter 实例"""
        import services.gateway.router as router_module
        # Reset singleton
        router_module._router_instance = None

        instance = get_service_router()
        assert isinstance(instance, ServiceRouter)

    def test_returns_same_instance(self):
        """多次调用应返回同一实例"""
        import services.gateway.router as router_module
        router_module._router_instance = None

        instance1 = get_service_router()
        instance2 = get_service_router()
        assert instance1 is instance2


# ==================== ServiceRouter.close ====================

class TestClose:
    """close 方法测试"""

    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, router):
        """close 应调用 client.aclose"""
        await router.close()
        router.client.aclose.assert_called_once()
