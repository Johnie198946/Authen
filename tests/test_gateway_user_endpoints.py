"""
网关用户管理类 API 端点单元测试

测试 4 个用户管理端点的完整流水线：
  - GET /api/v1/gateway/users/{user_id}
  - GET /api/v1/gateway/users/{user_id}/roles
  - POST /api/v1/gateway/users/{user_id}/permissions/check
  - POST /api/v1/gateway/auth/change-password

每个端点测试覆盖：Bearer Token 鉴权 → Scope 检查 → 限流 → AppUser 绑定检查 → 路由

需求: 7.1, 7.2, 7.3, 7.4, 7.5, 4.3, 4.4, 4.5
"""
import sys
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.utils.jwt import create_access_token
from services.gateway.main import app


# ---------------------------------------------------------------------------
# Fixtures & Constants
# ---------------------------------------------------------------------------

TEST_USER_ID = str(uuid.uuid4())
TEST_APP_ID = "test-app-id"

APP_DATA = {
    "id": str(uuid.uuid4()),
    "name": "Test App",
    "app_id": TEST_APP_ID,
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


def _make_valid_token(user_id=None, app_id=None):
    """Create a valid JWT token with app_id for testing."""
    payload = {
        "sub": user_id or TEST_USER_ID,
        "app_id": app_id or TEST_APP_ID,
    }
    return create_access_token(payload)


def _bearer_headers(token=None):
    """Create Authorization: Bearer headers."""
    if token is None:
        token = _make_valid_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: patch the Bearer pipeline dependencies
# ---------------------------------------------------------------------------

class BearerPipelineCtx:
    """Context manager that patches all Bearer pipeline dependencies."""

    def __init__(
        self,
        router_result=None,
        app_data=None,
        scopes=None,
        rate_limit_result=None,
        app_user_exists=True,
    ):
        self.router_result = router_result or {"status_code": 200, "body": {"success": True}}
        self.app_data = app_data or APP_DATA
        self.scopes = scopes or {"user:read", "user:write", "role:read"}
        self.rate_limit_result = rate_limit_result or RATE_LIMIT_OK
        self.app_user_exists = app_user_exists
        self.patches = {}
        self.mocks = {}

    def __enter__(self):
        # Patch get_app_from_cache_or_db (used in _run_bearer_pipeline)
        self.patches["app_cache"] = patch(
            "services.gateway.main.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=self.app_data,
        )

        # Patch check_scope
        self.patches["check_scope"] = patch(
            "services.gateway.main.check_scope",
            new_callable=AsyncMock,
            return_value="user:read",
        )

        # Patch check_rate_limit
        self.patches["rate_limit"] = patch(
            "services.gateway.main.check_rate_limit",
            new_callable=AsyncMock,
            return_value=self.rate_limit_result,
        )

        # Patch _check_app_user_binding
        if self.app_user_exists:
            self.patches["binding_check"] = patch(
                "services.gateway.main._check_app_user_binding",
                return_value=None,
            )
        else:
            from fastapi import HTTPException
            self.patches["binding_check"] = patch(
                "services.gateway.main._check_app_user_binding",
                side_effect=HTTPException(
                    status_code=403,
                    detail={"error_code": "user_not_bound", "message": "用户不属于该应用"},
                ),
            )

        # Patch get_service_router
        self.patches["router"] = patch("services.gateway.main.get_service_router")

        for name, p in self.patches.items():
            self.mocks[name] = p.start()

        # Configure router mock
        mock_router_instance = MagicMock()
        mock_router_instance.forward = AsyncMock(return_value=self.router_result)
        self.mocks["router"].return_value = mock_router_instance
        self.router_instance = mock_router_instance

        return self

    def __exit__(self, *args):
        for p in self.patches.values():
            p.stop()


# ===========================================================================
# GET /api/v1/gateway/users/{user_id}
# ===========================================================================

class TestGetUser:
    """用户查询端点测试"""

    def test_success(self, client):
        """成功查询用户信息 (需求 7.1)"""
        user_info = {
            "id": TEST_USER_ID,
            "username": "testuser",
            "email": "test@example.com",
            "phone": "13800138000",
            "status": "active",
        }
        result = {"status_code": 200, "body": user_info}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result) as ctx:
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}",
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testuser"
        assert "request_id" in data

    def test_routes_to_user_service(self, client):
        """请求被路由到 User Service (需求 7.1)"""
        result = {"status_code": 200, "body": {"id": TEST_USER_ID}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result) as ctx:
            client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}",
                headers=_bearer_headers(token),
            )
            ctx.router_instance.forward.assert_called_once_with(
                "user", "GET", f"/api/v1/users/{TEST_USER_ID}"
            )

    def test_missing_bearer_token(self, client):
        """缺少 Bearer Token 返回 401 (需求 4.5)"""
        resp = client.get(f"/api/v1/gateway/users/{TEST_USER_ID}")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "invalid_token"

    def test_invalid_token(self, client):
        """无效 Token 返回 401 + invalid_token (需求 4.5)"""
        resp = client.get(
            f"/api/v1/gateway/users/{TEST_USER_ID}",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "invalid_token"

    def test_expired_token(self, client):
        """过期 Token 返回 401 + token_expired (需求 4.4)"""
        from datetime import datetime, timedelta
        from jose import jwt as jose_jwt
        from shared.config import settings

        expired_payload = {
            "sub": TEST_USER_ID,
            "app_id": TEST_APP_ID,
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iat": datetime.utcnow() - timedelta(hours=2),
        }
        expired_token = jose_jwt.encode(
            expired_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )
        resp = client.get(
            f"/api/v1/gateway/users/{TEST_USER_ID}",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "token_expired"

    def test_user_not_bound(self, client):
        """用户不属于该应用返回 403 + user_not_bound (需求 7.5)"""
        token = _make_valid_token()
        with BearerPipelineCtx(app_user_exists=False):
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}",
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "user_not_bound"

    def test_rate_limit_headers(self, client):
        """响应包含限流头 (需求 6.4)"""
        result = {"status_code": 200, "body": {"id": TEST_USER_ID}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}",
                headers=_bearer_headers(token),
            )
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    def test_x_request_id_in_response(self, client):
        """响应包含 X-Request-Id (需求 9.3)"""
        result = {"status_code": 200, "body": {"id": TEST_USER_ID}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}",
                headers=_bearer_headers(token),
            )
        assert "X-Request-Id" in resp.headers
        uuid.UUID(resp.headers["X-Request-Id"])

    def test_upstream_error_unified_format(self, client):
        """下游错误返回统一格式 (需求 9.1)"""
        result = {"status_code": 404, "body": {"error_code": "not_found", "message": "用户不存在"}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}",
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error_code"] == "not_found"
        assert "request_id" in data


# ===========================================================================
# GET /api/v1/gateway/users/{user_id}/roles
# ===========================================================================

class TestGetUserRoles:
    """用户角色查询端点测试"""

    def test_success(self, client):
        """成功查询用户角色 (需求 7.2)"""
        roles = {"roles": [{"id": "r1", "name": "admin"}, {"id": "r2", "name": "editor"}]}
        result = {"status_code": 200, "body": roles}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}/roles",
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["roles"]) == 2
        assert "request_id" in data

    def test_routes_to_permission_service(self, client):
        """请求被路由到 Permission Service (需求 7.2)"""
        result = {"status_code": 200, "body": {"roles": []}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result) as ctx:
            client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}/roles",
                headers=_bearer_headers(token),
            )
            ctx.router_instance.forward.assert_called_once_with(
                "permission", "GET", f"/api/v1/permissions/users/{TEST_USER_ID}/roles"
            )

    def test_user_not_bound(self, client):
        """用户不属于该应用返回 403 (需求 7.5)"""
        token = _make_valid_token()
        with BearerPipelineCtx(app_user_exists=False):
            resp = client.get(
                f"/api/v1/gateway/users/{TEST_USER_ID}/roles",
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "user_not_bound"


# ===========================================================================
# POST /api/v1/gateway/users/{user_id}/permissions/check
# ===========================================================================

class TestCheckUserPermission:
    """用户权限检查端点测试"""

    def test_success(self, client):
        """成功检查用户权限 (需求 7.3)"""
        result = {"status_code": 200, "body": {"has_permission": True}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.post(
                f"/api/v1/gateway/users/{TEST_USER_ID}/permissions/check",
                json={"permission_name": "manage_users"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_permission"] is True
        assert "request_id" in data

    def test_routes_to_permission_service(self, client):
        """请求被路由到 Permission Service (需求 7.3)"""
        result = {"status_code": 200, "body": {"has_permission": False}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result) as ctx:
            client.post(
                f"/api/v1/gateway/users/{TEST_USER_ID}/permissions/check",
                json={"permission_name": "manage_users"},
                headers=_bearer_headers(token),
            )
            ctx.router_instance.forward.assert_called_once()
            call_args = ctx.router_instance.forward.call_args
            assert call_args[0][0] == "permission"
            assert call_args[0][1] == "POST"

    def test_user_not_bound(self, client):
        """用户不属于该应用返回 403 (需求 7.5)"""
        token = _make_valid_token()
        with BearerPipelineCtx(app_user_exists=False):
            resp = client.post(
                f"/api/v1/gateway/users/{TEST_USER_ID}/permissions/check",
                json={"permission_name": "manage_users"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "user_not_bound"


# ===========================================================================
# POST /api/v1/gateway/auth/change-password
# ===========================================================================

class TestChangePassword:
    """修改密码端点测试"""

    def test_success(self, client):
        """成功修改密码 (需求 7.4)"""
        result = {"status_code": 200, "body": {"message": "密码修改成功"}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/change-password",
                json={"old_password": "old123", "new_password": "new456"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "密码修改成功"
        assert "request_id" in data

    def test_routes_to_auth_service(self, client):
        """请求被路由到 Auth Service (需求 7.4)"""
        result = {"status_code": 200, "body": {"message": "ok"}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result) as ctx:
            client.post(
                "/api/v1/gateway/auth/change-password",
                json={"old_password": "old123", "new_password": "new456"},
                headers=_bearer_headers(token),
            )
            ctx.router_instance.forward.assert_called_once_with(
                "auth", "POST", "/api/v1/auth/change-password",
                json={"old_password": "old123", "new_password": "new456"},
            )

    def test_user_not_bound(self, client):
        """用户不属于该应用返回 403 (需求 7.5)"""
        token = _make_valid_token()
        with BearerPipelineCtx(app_user_exists=False):
            resp = client.post(
                "/api/v1/gateway/auth/change-password",
                json={"old_password": "old123", "new_password": "new456"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "user_not_bound"

    def test_upstream_error(self, client):
        """下游返回错误时使用统一格式 (需求 9.1)"""
        result = {"status_code": 400, "body": {"error_code": "wrong_password", "message": "旧密码错误"}}
        token = _make_valid_token()
        with BearerPipelineCtx(router_result=result):
            resp = client.post(
                "/api/v1/gateway/auth/change-password",
                json={"old_password": "wrong", "new_password": "new456"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error_code"] == "wrong_password"
        assert "request_id" in data

    def test_token_without_app_id(self, client):
        """Token 中缺少 app_id 返回 401 (需求 4.3)"""
        # Create a token without app_id
        token = create_access_token({"sub": TEST_USER_ID})
        resp = client.post(
            "/api/v1/gateway/auth/change-password",
            json={"old_password": "old123", "new_password": "new456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error_code"] == "invalid_token"

    def test_disabled_app(self, client):
        """应用被禁用返回 403 (需求 1.4)"""
        disabled_app = {**APP_DATA, "status": "disabled"}
        token = _make_valid_token()
        with BearerPipelineCtx(app_data=disabled_app):
            resp = client.post(
                "/api/v1/gateway/auth/change-password",
                json={"old_password": "old123", "new_password": "new456"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error_code"] == "app_disabled"

    def test_rate_limited(self, client):
        """超过限流返回 429 (需求 6.3)"""
        token = _make_valid_token()
        with BearerPipelineCtx(rate_limit_result=RATE_LIMIT_EXCEEDED):
            resp = client.post(
                "/api/v1/gateway/auth/change-password",
                json={"old_password": "old123", "new_password": "new456"},
                headers=_bearer_headers(token),
            )
        assert resp.status_code == 429
        data = resp.json()
        assert data["error_code"] == "rate_limit_exceeded"
