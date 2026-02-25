"""
Gateway 配额端点集成测试

测试 2 个配额相关端点：
  - POST /api/v1/gateway/llm/{path:path}  (大模型 API 代理)
  - GET /api/v1/quota/usage  (配额查询)

覆盖：认证流水线 → 配额检查 → 扣减 → 转发 → 响应头注入

需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 9.3, 12.1, 12.2, 12.6
"""
import sys
import os
import uuid
from dataclasses import dataclass
from typing import Optional, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.main import app


# ---------------------------------------------------------------------------
# Fixtures & Constants
# ---------------------------------------------------------------------------

APP_DATA = {
    "id": str(uuid.uuid4()),
    "name": "Test App",
    "app_id": "test-app-id",
    "app_secret_hash": "fakehash",
    "status": "active",
    "rate_limit": 60,
}

RATE_LIMIT_OK = MagicMock(
    allowed=True,
    limit=60,
    remaining=59,
    reset=9999999999,
    headers={
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Remaining": "59",
        "X-RateLimit-Reset": "9999999999",
    },
)

HEADERS = {"X-App-Id": "test-app-id", "X-App-Secret": "test-secret"}


@dataclass
class FakeQuotaCheckResult:
    """Fake QuotaCheckResult for testing"""
    allowed: bool
    request_limit: int
    request_used: int
    request_remaining: int
    token_limit: int
    token_used: int
    token_remaining: int
    reset_timestamp: int
    error_code: Optional[str] = None
    warning: Optional[str] = None

    @property
    def headers(self) -> Dict[str, str]:
        h = {
            "X-Quota-Request-Limit": str(self.request_limit),
            "X-Quota-Request-Remaining": str(self.request_remaining),
            "X-Quota-Request-Reset": str(self.reset_timestamp),
            "X-Quota-Token-Limit": str(self.token_limit),
            "X-Quota-Token-Remaining": str(self.token_remaining),
            "X-Quota-Token-Reset": str(self.reset_timestamp),
        }
        if self.warning:
            h["X-Quota-Warning"] = self.warning
        return h


QUOTA_OK = FakeQuotaCheckResult(
    allowed=True,
    request_limit=1000,
    request_used=10,
    request_remaining=990,
    token_limit=100000,
    token_used=500,
    token_remaining=99500,
    reset_timestamp=9999999999,
)

QUOTA_AFTER_DEDUCT = FakeQuotaCheckResult(
    allowed=True,
    request_limit=1000,
    request_used=11,
    request_remaining=989,
    token_limit=100000,
    token_used=600,
    token_remaining=99400,
    reset_timestamp=9999999999,
)

QUOTA_REQUEST_EXCEEDED = FakeQuotaCheckResult(
    allowed=False,
    request_limit=1000,
    request_used=1000,
    request_remaining=0,
    token_limit=100000,
    token_used=500,
    token_remaining=99500,
    reset_timestamp=9999999999,
    error_code="request_quota_exceeded",
)

QUOTA_TOKEN_EXCEEDED = FakeQuotaCheckResult(
    allowed=False,
    request_limit=1000,
    request_used=10,
    request_remaining=990,
    token_limit=100000,
    token_used=100000,
    token_remaining=0,
    reset_timestamp=9999999999,
    error_code="token_quota_exceeded",
)

QUOTA_NOT_CONFIGURED = FakeQuotaCheckResult(
    allowed=False,
    request_limit=0,
    request_used=0,
    request_remaining=0,
    token_limit=0,
    token_used=0,
    token_remaining=0,
    reset_timestamp=0,
    error_code="quota_not_configured",
)

QUOTA_WITH_WARNING = FakeQuotaCheckResult(
    allowed=True,
    request_limit=1000,
    request_used=850,
    request_remaining=150,
    token_limit=100000,
    token_used=85000,
    token_remaining=15000,
    reset_timestamp=9999999999,
    warning="approaching_limit",
)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: patch the full pipeline for LLM proxy endpoint
# ---------------------------------------------------------------------------

class LLMPipelineCtx:
    """Context manager that patches auth pipeline + quota functions + router."""

    def __init__(
        self,
        quota_check_result=None,
        quota_deduct_token_result=None,
        router_result=None,
    ):
        self.quota_check_result = quota_check_result or QUOTA_OK
        self.quota_deduct_token_result = quota_deduct_token_result or QUOTA_AFTER_DEDUCT
        self.router_result = router_result or {
            "status_code": 200,
            "body": {"result": "hello", "token_usage": 100},
        }

    def __enter__(self):
        async def mock_get_credential(request):
            request.state.app = APP_DATA
            return APP_DATA

        self.patches = [
            patch(
                "services.gateway.main.get_app_credential_from_request",
                side_effect=mock_get_credential,
            ),
            patch(
                "services.gateway.main.get_app_methods",
                new_callable=AsyncMock,
                return_value={"email", "phone"},
            ),
            patch(
                "services.gateway.main.check_scope",
                new_callable=AsyncMock,
            ),
            patch(
                "services.gateway.main.check_rate_limit",
                new_callable=AsyncMock,
                return_value=RATE_LIMIT_OK,
            ),
            patch(
                "services.gateway.main.check_quota",
                new_callable=AsyncMock,
                return_value=self.quota_check_result,
            ),
            patch(
                "services.gateway.main.deduct_request_quota",
                new_callable=AsyncMock,
            ),
            patch(
                "services.gateway.main.deduct_token_quota",
                new_callable=AsyncMock,
                return_value=self.quota_deduct_token_result,
            ),
            patch("services.gateway.main.get_service_router"),
        ]

        self.mocks = [p.start() for p in self.patches]

        # Configure router mock
        mock_router = MagicMock()
        mock_router.forward = AsyncMock(return_value=self.router_result)
        self.mocks[-1].return_value = mock_router  # get_service_router returns mock_router
        self.router_mock = mock_router

        # Named references
        self.check_quota_mock = self.mocks[4]
        self.deduct_request_mock = self.mocks[5]
        self.deduct_token_mock = self.mocks[6]

        return self

    def __exit__(self, *args):
        for p in self.patches:
            p.stop()


class QuotaUsagePipelineCtx:
    """Context manager that patches auth pipeline + get_quota_usage."""

    def __init__(self, usage_result=None):
        self.usage_result = usage_result or {
            "request_quota_limit": 1000,
            "request_quota_used": 50,
            "request_quota_remaining": 950,
            "token_quota_limit": 100000,
            "token_quota_used": 2000,
            "token_quota_remaining": 98000,
            "billing_cycle_start": "2024-01-01T00:00:00",
            "billing_cycle_end": "2024-01-31T00:00:00",
            "billing_cycle_reset": 1706659200,
        }

    def __enter__(self):
        async def mock_get_credential(request):
            request.state.app = APP_DATA
            return APP_DATA

        self.patches = [
            patch(
                "services.gateway.main.get_app_credential_from_request",
                side_effect=mock_get_credential,
            ),
            patch(
                "services.gateway.main.get_app_methods",
                new_callable=AsyncMock,
                return_value={"email", "phone"},
            ),
            patch(
                "services.gateway.main.check_scope",
                new_callable=AsyncMock,
            ),
            patch(
                "services.gateway.main.check_rate_limit",
                new_callable=AsyncMock,
                return_value=RATE_LIMIT_OK,
            ),
            patch(
                "services.gateway.main.get_quota_usage",
                new_callable=AsyncMock,
                return_value=self.usage_result,
            ),
        ]

        self.mocks = [p.start() for p in self.patches]
        self.get_quota_usage_mock = self.mocks[4]
        return self

    def __exit__(self, *args):
        for p in self.patches:
            p.stop()


# ===========================================================================
# POST /api/v1/gateway/llm/{path:path}
# ===========================================================================

class TestLLMProxy:
    """大模型 API 代理端点测试"""

    def test_success_with_quota_headers(self, client):
        """成功请求返回下游响应 + X-Quota-* 响应头 (需求 3.3, 3.4)"""
        with LLMPipelineCtx() as ctx:
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "hello"
        assert "X-Quota-Request-Limit" in resp.headers
        assert "X-Quota-Request-Remaining" in resp.headers
        assert "X-Quota-Request-Reset" in resp.headers
        assert "X-Quota-Token-Limit" in resp.headers
        assert "X-Quota-Token-Remaining" in resp.headers
        assert "X-Quota-Token-Reset" in resp.headers

    def test_request_quota_exceeded_returns_429(self, client):
        """请求配额耗尽返回 429 + error_code (需求 3.2, 4.1)"""
        with LLMPipelineCtx(quota_check_result=QUOTA_REQUEST_EXCEEDED):
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error_code"] == "request_quota_exceeded"
        assert "reset_at" in data

    def test_token_quota_exceeded_returns_429(self, client):
        """Token 配额耗尽返回 429 + error_code (需求 4.2)"""
        with LLMPipelineCtx(quota_check_result=QUOTA_TOKEN_EXCEEDED):
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error_code"] == "token_quota_exceeded"
        assert "reset_at" in data

    def test_quota_not_configured_returns_429(self, client):
        """未配置配额返回 429 (需求 2.4)"""
        with LLMPipelineCtx(quota_check_result=QUOTA_NOT_CONFIGURED):
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error_code"] == "quota_not_configured"

    def test_deduct_request_quota_called(self, client):
        """成功请求后调用 deduct_request_quota (需求 3.5)"""
        with LLMPipelineCtx() as ctx:
            client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
            ctx.deduct_request_mock.assert_called_once_with("test-app-id")

    def test_deduct_token_quota_with_usage(self, client):
        """从下游响应提取 token_usage 并扣减 (需求 3.6, 4.3)"""
        router_result = {
            "status_code": 200,
            "body": {"result": "ok", "token_usage": 250},
        }
        with LLMPipelineCtx(router_result=router_result) as ctx:
            client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
            ctx.deduct_token_mock.assert_called_once_with("test-app-id", 250)

    def test_deduct_token_quota_default_zero(self, client):
        """下游响应无 token_usage 时默认扣减 0 (需求 4.4)"""
        router_result = {
            "status_code": 200,
            "body": {"result": "ok"},
        }
        with LLMPipelineCtx(router_result=router_result) as ctx:
            client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
            ctx.deduct_token_mock.assert_called_once_with("test-app-id", 0)

    def test_quota_warning_header(self, client):
        """配额预警时注入 X-Quota-Warning 响应头 (需求 9.3)"""
        warning_after_deduct = FakeQuotaCheckResult(
            allowed=True,
            request_limit=1000,
            request_used=851,
            request_remaining=149,
            token_limit=100000,
            token_used=85100,
            token_remaining=14900,
            reset_timestamp=9999999999,
            warning="approaching_limit",
        )
        with LLMPipelineCtx(
            quota_check_result=QUOTA_WITH_WARNING,
            quota_deduct_token_result=warning_after_deduct,
        ):
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.headers.get("X-Quota-Warning") == "approaching_limit"

    def test_rate_limit_headers_present(self, client):
        """响应包含限流头"""
        with LLMPipelineCtx():
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert "X-RateLimit-Limit" in resp.headers

    def test_request_id_in_response(self, client):
        """响应包含 X-Request-Id"""
        with LLMPipelineCtx():
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert "X-Request-Id" in resp.headers

    def test_upstream_error_forwarded(self, client):
        """下游错误返回统一格式"""
        router_result = {
            "status_code": 500,
            "body": {"error_code": "upstream_error", "message": "LLM 服务内部错误"},
        }
        with LLMPipelineCtx(router_result=router_result):
            resp = client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
        assert resp.status_code == 500
        data = resp.json()
        assert data["error_code"] == "upstream_error"

    def test_path_forwarded_correctly(self, client):
        """路径正确转发到下游 LLM 服务"""
        with LLMPipelineCtx() as ctx:
            client.post(
                "/api/v1/gateway/llm/v1/chat/completions",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
            ctx.router_mock.forward.assert_called_once()
            call_args = ctx.router_mock.forward.call_args
            assert call_args[0][0] == "llm"  # service
            assert call_args[0][1] == "POST"  # method
            assert call_args[0][2] == "/api/v1/llm/v1/chat/completions"  # path

    def test_no_deduction_when_quota_exceeded(self, client):
        """配额耗尽时不调用扣减和转发"""
        with LLMPipelineCtx(quota_check_result=QUOTA_REQUEST_EXCEEDED) as ctx:
            client.post(
                "/api/v1/gateway/llm/chat",
                json={"prompt": "hello"},
                headers=HEADERS,
            )
            ctx.deduct_request_mock.assert_not_called()
            ctx.deduct_token_mock.assert_not_called()
            ctx.router_mock.forward.assert_not_called()

    def test_missing_credentials(self, client):
        """缺少凭证返回 401"""
        resp = client.post(
            "/api/v1/gateway/llm/chat",
            json={"prompt": "hello"},
        )
        assert resp.status_code == 401


# ===========================================================================
# GET /api/v1/quota/usage
# ===========================================================================

class TestQuotaUsage:
    """配额查询端点测试"""

    def test_success(self, client):
        """成功返回配额使用数据 (需求 12.1, 12.6)"""
        with QuotaUsagePipelineCtx():
            resp = client.get("/api/v1/quota/usage", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["request_quota_limit"] == 1000
        assert data["request_quota_used"] == 50
        assert data["request_quota_remaining"] == 950
        assert data["token_quota_limit"] == 100000
        assert data["token_quota_used"] == 2000
        assert data["token_quota_remaining"] == 98000
        assert "billing_cycle_start" in data
        assert "billing_cycle_end" in data
        assert "billing_cycle_reset" in data

    def test_quota_not_configured(self, client):
        """未配置配额返回 403 (需求 12.2)"""
        usage = {
            "error_code": "quota_not_configured",
            "message": "应用未配置配额计划",
        }
        with QuotaUsagePipelineCtx(usage_result=usage):
            resp = client.get("/api/v1/quota/usage", headers=HEADERS)
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "quota_not_configured"

    def test_service_degraded(self, client):
        """Redis 不可用返回 503"""
        usage = {
            "error_code": "service_degraded",
            "message": "配额服务暂时不可用，请稍后重试",
        }
        with QuotaUsagePipelineCtx(usage_result=usage):
            resp = client.get("/api/v1/quota/usage", headers=HEADERS)
        assert resp.status_code == 503
        data = resp.json()
        assert data["error_code"] == "service_degraded"

    def test_request_id_in_response(self, client):
        """响应包含 request_id"""
        with QuotaUsagePipelineCtx():
            resp = client.get("/api/v1/quota/usage", headers=HEADERS)
        data = resp.json()
        assert "request_id" in data

    def test_rate_limit_headers_present(self, client):
        """响应包含限流头"""
        with QuotaUsagePipelineCtx():
            resp = client.get("/api/v1/quota/usage", headers=HEADERS)
        assert "X-RateLimit-Limit" in resp.headers

    def test_missing_credentials(self, client):
        """缺少凭证返回 401"""
        resp = client.get("/api/v1/quota/usage")
        assert resp.status_code == 401

    def test_calls_get_quota_usage_with_app_id(self, client):
        """调用 get_quota_usage 时传入正确的 app_id"""
        with QuotaUsagePipelineCtx() as ctx:
            client.get("/api/v1/quota/usage", headers=HEADERS)
            ctx.get_quota_usage_mock.assert_called_once_with("test-app-id")
