"""
Scope 权限检查模块单元测试

测试 services/gateway/scope_checker.py 中的核心逻辑：
- _match_endpoint: 端点路径到 Scope 的通配符匹配
- check_scope: 从缓存加载 Scope 并验证权限
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.scope_checker import (
    _match_endpoint,
    check_scope,
    ENDPOINT_SCOPE_MAP,
)


# ==================== _match_endpoint ====================

class TestMatchEndpoint:
    """_match_endpoint 函数测试"""

    def test_exact_match_auth_login(self):
        """auth/login 精确匹配 → auth:login"""
        assert _match_endpoint("auth/login") == "auth:login"

    def test_exact_match_auth_refresh(self):
        """auth/refresh 精确匹配 → auth:login"""
        assert _match_endpoint("auth/refresh") == "auth:login"

    def test_exact_match_auth_change_password(self):
        """auth/change-password 精确匹配 → user:write"""
        assert _match_endpoint("auth/change-password") == "user:write"

    def test_wildcard_match_auth_register_email(self):
        """auth/register/email 通配符匹配 → auth:register"""
        assert _match_endpoint("auth/register/email") == "auth:register"

    def test_wildcard_match_auth_register_phone(self):
        """auth/register/phone 通配符匹配 → auth:register"""
        assert _match_endpoint("auth/register/phone") == "auth:register"

    def test_wildcard_match_auth_oauth_google(self):
        """auth/oauth/google 通配符匹配 → auth:login"""
        assert _match_endpoint("auth/oauth/google") == "auth:login"

    def test_wildcard_match_auth_oauth_wechat(self):
        """auth/oauth/wechat 通配符匹配 → auth:login"""
        assert _match_endpoint("auth/oauth/wechat") == "auth:login"

    def test_wildcard_match_users_roles(self):
        """users/{id}/roles 通配符匹配 → role:read"""
        assert _match_endpoint("users/abc-123/roles") == "role:read"

    def test_wildcard_match_users_permissions_check(self):
        """users/{id}/permissions/check 通配符匹配 → role:read"""
        assert _match_endpoint("users/abc-123/permissions/check") == "role:read"

    def test_wildcard_match_users_by_id(self):
        """users/{id} 通配符匹配 → user:read"""
        assert _match_endpoint("users/abc-123") == "user:read"

    def test_unmatched_endpoint_returns_none(self):
        """未在映射表中的端点返回 None"""
        assert _match_endpoint("unknown/path") is None

    def test_strips_leading_trailing_slashes(self):
        """首尾斜杠应被去除后正常匹配"""
        assert _match_endpoint("/auth/login/") == "auth:login"

    def test_empty_endpoint_returns_none(self):
        """空端点返回 None"""
        assert _match_endpoint("") is None


# ==================== check_scope ====================

class TestCheckScope:
    """check_scope 函数测试"""

    @pytest.mark.asyncio
    async def test_authorized_scope_passes(self):
        """应用拥有所需 Scope 时应正常返回"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
            return_value={"auth:login", "user:read"},
        ):
            result = await check_scope("test-app-id", "auth/login")
            assert result == "auth:login"

    @pytest.mark.asyncio
    async def test_missing_scope_raises_403(self):
        """应用缺少所需 Scope 时应返回 403 + insufficient_scope"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
            return_value={"user:read"},
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_scope("test-app-id", "auth/login")
            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail
            assert detail["error_code"] == "insufficient_scope"

    @pytest.mark.asyncio
    async def test_empty_scopes_raises_403(self):
        """应用没有任何 Scope 时应返回 403"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
            return_value=set(),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_scope("test-app-id", "auth/login")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unmapped_endpoint_skips_check(self):
        """未在映射表中的端点不需要 Scope 检查"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
        ) as mock_get_scopes:
            result = await check_scope("test-app-id", "health")
            assert result == ""
            mock_get_scopes.assert_not_called()

    @pytest.mark.asyncio
    async def test_wildcard_endpoint_scope_check(self):
        """通配符端点也应正确检查 Scope"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
            return_value={"auth:register"},
        ):
            result = await check_scope("test-app-id", "auth/register/email")
            assert result == "auth:register"

    @pytest.mark.asyncio
    async def test_users_roles_requires_role_read(self):
        """users/*/roles 端点需要 role:read Scope"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
            return_value={"role:read"},
        ):
            result = await check_scope("test-app-id", "users/user-123/roles")
            assert result == "role:read"

    @pytest.mark.asyncio
    async def test_insufficient_scope_error_message_contains_scope(self):
        """403 错误消息应包含缺少的 Scope 名称"""
        with patch(
            "services.gateway.scope_checker.get_app_scopes",
            new_callable=AsyncMock,
            return_value=set(),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_scope("test-app-id", "auth/login")
            detail = exc_info.value.detail
            assert "auth:login" in detail["message"]
