"""
网关认证类 API 端点单元测试

测试 5 个认证端点的完整流水线：
  - POST /api/v1/gateway/auth/register/email
  - POST /api/v1/gateway/auth/register/phone
  - POST /api/v1/gateway/auth/login
  - POST /api/v1/gateway/auth/oauth/{provider}
  - POST /api/v1/gateway/auth/refresh

每个端点测试覆盖：凭证验证 → 登录方式检查 → Scope 检查 → 限流 → 路由 → 审计日志

需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 3.8, 4.6
"""
import sys
import os
import uuid
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

RATE_LIMIT_EXCEEDED = MagicMock(
    allowed=False,
    limit=60,
    remaining=0,
    reset=9999999999,
    retry_after=30,
    headers={
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "9999999999",
        "Retry-After": "30",
    },
)

HEADERS = {"X-App-Id": "test-app-id", "X-App-Secret": "test-secret"}


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: patch the full pipeline at the main.py import level
# ---------------------------------------------------------------------------

def _make_pipeline_patches(
    enabled_methods=None,
    scopes=None,
    rate_limit_result=None,
    router_result=None,
    oauth_config=None,
    credential_side_effect=None,
):
    """
    Patch all dependencies at the services.gateway.main module level
    so that the endpoint functions see the mocked versions.
    """
    if enabled_methods is None:
        enabled_methods = {"email", "phone", "wechat", "google"}
    if scopes is None:
        scopes = {"auth:register", "auth:login", "user:read", "user:write"}
    if rate_limit_result is None:
        rate_limit_result = RATE_LIMIT_OK
    if router_result is None:
        router_result = {"status_code": 200, "body": {"success": True}}

    # Mock get_app_credential_from_request to return APP_DATA and set request.state
    async def mock_get_credential(request):
        request.state.app = APP_DATA
        if credential_side_effect:
            raise credential_side_effect
        return APP_DATA

    patches = {
        "credential": patch(
            "services.gateway.main.get_app_credential_from_request",
            side_effect=mock_get_credential,
        ),
        "methods": patch(
            "services.gateway.main.get_app_methods",
            new_callable=AsyncMock,
            return_value=enabled_methods,
        ),
        "check_scope": patch(
            "services.gateway.main.check_scope",
            new_callable=AsyncMock,
            return_value="auth:register",
        ),
        "rate_limit": patch(
            "services.gateway.main.check_rate_limit",
            new_callable=AsyncMock,
            return_value=rate_limit_result,
        ),
        "router": patch("services.gateway.main.get_service_router"),
        "binding": patch("services.gateway.main._create_app_user_binding"),
    }

    if oauth_config is not None:
        patches["oauth_config"] = patch(
            "services.gateway.main.get_app_oauth_config",
            new_callable=AsyncMock,
            return_value=oauth_config,
        )

    return patches, router_result


class PipelineCtx:
    """Context manager that starts all patches and configures the router mock."""

    def __init__(self, router_result=None, **kwargs):
        self.patches_dict, self.router_result = _make_pipeline_patches(
            router_result=router_result, **kwargs
        )
        self.mocks = {}

    def __enter__(self):
        for name, p in self.patches_dict.items():
            self.mocks[name] = p.start()
        # Configure router mock
        mock_router_instance = MagicMock()
        mock_router_instance.forward = AsyncMock(return_value=self.router_result)
        self.mocks["router"].return_value = mock_router_instance
        self.router_instance = mock_router_instance
        return self

    def __exit__(self, *args):
        for p in self.patches_dict.values():
            p.stop()


# ===========================================================================
# POST /api/v1/gateway/auth/register/email
# ===========================================================================

class TestRegisterEmail:
    """邮箱注册端点测试"""

    def test_success(self, client):
        """成功注册返回 user_id 和 request_id"""
        result = {"status_code": 200, "body": {"success": True, "user_id": "u123", "message": "注册成功"}}
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/register/email",
                json={"email": "test@example.com", "password": "pass123", "username": "tester"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "u123"
        assert "request_id" in data

    def test_creates_app_user_binding(self, client):
        """注册成功后创建 AppUser 绑定 (需求 3.8)"""
        result = {"status_code": 200, "body": {"success": True, "user_id": "u123", "message": "注册成功"}}
        with PipelineCtx(router_result=result) as ctx:
            client.post(
                "/api/v1/gateway/auth/register/email",
                json={"email": "test@example.com", "password": "pass123", "username": "tester"},
                headers=HEADERS,
            )
            ctx.mocks["binding"].assert_called_once_with(APP_DATA, "u123")

    def test_login_method_disabled(self, client):
        """email 登录方式未启用返回 400 + login_method_disabled (需求 3.7)"""
        with PipelineCtx(enabled_methods={"phone"}):
            resp = client.post(
                "/api/v1/gateway/auth/register/email",
                json={"email": "test@example.com", "password": "pass123", "username": "tester"},
                headers=HEADERS,
            )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "login_method_disabled"

    def test_rate_limit_headers(self, client):
        """响应包含限流头 (需求 6.4)"""
        result = {"status_code": 200, "body": {"success": True, "user_id": "u1", "message": "ok"}}
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/register/email",
                json={"email": "test@example.com", "password": "pass123", "username": "tester"},
                headers=HEADERS,
            )
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_missing_credentials(self, client):
        """缺少凭证返回 401 (需求 3.6)"""
        resp = client.post(
            "/api/v1/gateway/auth/register/email",
            json={"email": "test@example.com", "password": "pass123", "username": "tester"},
        )
        assert resp.status_code == 401

    def test_upstream_error_unified_format(self, client):
        """下游错误返回统一格式 (需求 9.1)"""
        result = {"status_code": 400, "body": {"error_code": "email_exists", "message": "邮箱已注册"}}
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/register/email",
                json={"email": "test@example.com", "password": "pass123", "username": "tester"},
                headers=HEADERS,
            )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "email_exists"
        assert "request_id" in data


# ===========================================================================
# POST /api/v1/gateway/auth/register/phone
# ===========================================================================

class TestRegisterPhone:
    """手机注册端点测试"""

    def test_success(self, client):
        """成功注册返回 user_id (需求 3.2)"""
        result = {"status_code": 200, "body": {"success": True, "user_id": "u456", "message": "注册成功"}}
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/register/phone",
                json={"phone": "13800138000", "password": "pass123", "username": "tester", "verification_code": "1234"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "u456"

    def test_phone_method_disabled(self, client):
        """phone 登录方式未启用返回 400 (需求 3.7)"""
        with PipelineCtx(enabled_methods={"email"}):
            resp = client.post(
                "/api/v1/gateway/auth/register/phone",
                json={"phone": "13800138000", "password": "pass123", "username": "tester", "verification_code": "1234"},
                headers=HEADERS,
            )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "login_method_disabled"

    def test_creates_app_user_binding(self, client):
        """注册成功后创建 AppUser 绑定 (需求 3.8)"""
        result = {"status_code": 200, "body": {"success": True, "user_id": "u456", "message": "ok"}}
        with PipelineCtx(router_result=result) as ctx:
            client.post(
                "/api/v1/gateway/auth/register/phone",
                json={"phone": "13800138000", "password": "pass123", "username": "tester", "verification_code": "1234"},
                headers=HEADERS,
            )
            ctx.mocks["binding"].assert_called_once_with(APP_DATA, "u456")


# ===========================================================================
# POST /api/v1/gateway/auth/login
# ===========================================================================

class TestLogin:
    """登录端点测试"""

    def test_success_with_token_injection(self, client):
        """登录成功返回 Token 且 payload 包含 app_id (需求 3.3, 4.6)"""
        from shared.utils.jwt import create_access_token, create_refresh_token
        at = create_access_token({"sub": "user1"})
        rt = create_refresh_token({"sub": "user1"})
        result = {
            "status_code": 200,
            "body": {
                "access_token": at,
                "refresh_token": rt,
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": {"id": "user1", "username": "tester"},
            },
        }
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/login",
                json={"identifier": "test@example.com", "password": "pass123"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        # Verify app_id was injected
        from shared.utils.jwt import decode_token
        payload = decode_token(data["access_token"])
        assert payload is not None
        assert payload.get("app_id") == "test-app-id"

    def test_login_does_not_check_specific_method(self, client):
        """登录不检查具体的 login_method"""
        result = {"status_code": 200, "body": {"access_token": "tok", "token_type": "Bearer", "expires_in": 3600, "user": {}}}
        with PipelineCtx(enabled_methods=set(), router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/login",
                json={"identifier": "test@example.com", "password": "pass123"},
                headers=HEADERS,
            )
        assert resp.status_code == 200

    def test_rate_limited(self, client):
        """超过限流返回 429 (需求 6.3)"""
        with PipelineCtx(rate_limit_result=RATE_LIMIT_EXCEEDED):
            resp = client.post(
                "/api/v1/gateway/auth/login",
                json={"identifier": "test@example.com", "password": "pass123"},
                headers=HEADERS,
            )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error_code"] == "rate_limit_exceeded"

    def test_insufficient_scope(self, client):
        """缺少 auth:login scope 返回 403 (需求 5.2)"""
        from fastapi import HTTPException

        async def mock_check_scope(app_id, endpoint):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "insufficient_scope", "message": "应用未被授予所需的权限范围: auth:login"},
            )

        with PipelineCtx() as ctx:
            ctx.mocks["check_scope"].side_effect = mock_check_scope
            resp = client.post(
                "/api/v1/gateway/auth/login",
                json={"identifier": "test@example.com", "password": "pass123"},
                headers=HEADERS,
            )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "insufficient_scope"


# ===========================================================================
# POST /api/v1/gateway/auth/oauth/{provider}
# ===========================================================================

class TestOAuth:
    """OAuth 登录端点测试"""

    def test_success_with_app_level_config(self, client):
        """OAuth 成功使用应用级配置 (需求 3.4)"""
        from shared.utils.jwt import create_access_token, create_refresh_token
        at = create_access_token({"sub": "oauthuser"})
        rt = create_refresh_token({"sub": "oauthuser"})
        result = {
            "status_code": 200,
            "body": {
                "access_token": at,
                "refresh_token": rt,
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": {"id": "oauthuser", "username": "oauth_tester"},
                "is_new_user": False,
            },
        }
        oauth_cfg = {"client_id": "app-client-id", "client_secret": "app-client-secret"}
        with PipelineCtx(router_result=result, oauth_config=oauth_cfg) as ctx:
            resp = client.post(
                "/api/v1/gateway/auth/oauth/google",
                json={"code": "auth-code", "redirect_uri": "https://example.com/callback"},
                headers=HEADERS,
            )
            # Verify the router was called with app-level OAuth config injected
            call_args = ctx.router_instance.forward.call_args
            sent_json = call_args.kwargs.get("json", {})
            assert sent_json.get("client_id") == "app-client-id"
            assert sent_json.get("client_secret") == "app-client-secret"

        assert resp.status_code == 200
        data = resp.json()
        from shared.utils.jwt import decode_token
        payload = decode_token(data["access_token"])
        assert payload.get("app_id") == "test-app-id"

    def test_provider_method_disabled(self, client):
        """OAuth provider 未启用返回 400 (需求 3.7)"""
        with PipelineCtx(enabled_methods={"email", "phone"}):
            resp = client.post(
                "/api/v1/gateway/auth/oauth/wechat",
                json={"code": "auth-code", "redirect_uri": "https://example.com/callback"},
                headers=HEADERS,
            )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "login_method_disabled"

    def test_new_user_creates_binding(self, client):
        """OAuth 新用户创建 AppUser 绑定 (需求 3.8)"""
        result = {
            "status_code": 200,
            "body": {
                "access_token": "tok",
                "refresh_token": "rtok",
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": {"id": "new-user-id", "username": "new_user"},
                "is_new_user": True,
            },
        }
        oauth_cfg = {"client_id": "cid", "client_secret": "csec"}
        with PipelineCtx(router_result=result, oauth_config=oauth_cfg) as ctx:
            client.post(
                "/api/v1/gateway/auth/oauth/google",
                json={"code": "auth-code", "redirect_uri": "https://example.com/callback"},
                headers=HEADERS,
            )
            ctx.mocks["binding"].assert_called_once_with(APP_DATA, "new-user-id")


# ===========================================================================
# POST /api/v1/gateway/auth/refresh
# ===========================================================================

class TestRefresh:
    """Token 刷新端点测试"""

    def test_success_with_token_injection(self, client):
        """刷新成功返回新 Token 且 payload 包含 app_id (需求 3.5, 4.6)"""
        from shared.utils.jwt import create_access_token
        at = create_access_token({"sub": "user1"})
        result = {
            "status_code": 200,
            "body": {"access_token": at, "token_type": "Bearer", "expires_in": 3600},
        }
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/refresh",
                json={"refresh_token": "old-refresh-token"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        from shared.utils.jwt import decode_token
        payload = decode_token(data["access_token"])
        assert payload is not None
        assert payload.get("app_id") == "test-app-id"

    def test_upstream_error(self, client):
        """下游返回错误时使用统一格式 (需求 9.1)"""
        result = {"status_code": 401, "body": {"error_code": "invalid_token", "message": "Token 无效"}}
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/refresh",
                json={"refresh_token": "bad-token"},
                headers=HEADERS,
            )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "invalid_token"
        assert "request_id" in data

    def test_x_request_id_in_response(self, client):
        """所有响应包含 X-Request-Id (需求 9.3)"""
        result = {"status_code": 200, "body": {"access_token": "tok", "token_type": "Bearer", "expires_in": 3600}}
        with PipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/refresh",
                json={"refresh_token": "rt"},
                headers=HEADERS,
            )
        assert "X-Request-Id" in resp.headers
        uuid.UUID(resp.headers["X-Request-Id"])
