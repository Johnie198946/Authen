"""
Scope 权限检查模块

每个 API 端点映射到一个 Scope，请求时检查应用是否拥有该 Scope。
缺少 Scope 返回 403 + error_code "insufficient_scope"。

需求: 5.2, 5.4
"""
from fnmatch import fnmatch
from typing import Optional

from fastapi import HTTPException

from services.gateway.cache import get_app_scopes


# API 端点路径到 Scope 的映射（使用 fnmatch 通配符）
# 路径为去掉 /api/v1/gateway/ 前缀后的相对路径
ENDPOINT_SCOPE_MAP = {
    "auth/register/*": "auth:register",
    "auth/login": "auth:login",
    "auth/oauth/*": "auth:login",
    "auth/refresh": "auth:login",
    "auth/change-password": "user:write",
    "users/*/roles/assign": "role:write",
    "users/*/roles/*/remove": "role:write",
    "users/*/permissions": "role:read",
    "users/*/permissions/check": "role:read",
    "users/*/roles": "role:read",
    "users/*": "user:read",
}


def _match_endpoint(endpoint: str) -> Optional[str]:
    """
    将请求端点路径匹配到所需的 Scope。

    使用 fnmatch 进行通配符匹配，按映射表顺序逐一匹配。
    更具体的模式（如 users/*/roles）应排在更通用的模式（如 users/*）之前。

    Args:
        endpoint: 去掉网关前缀后的相对路径，如 "auth/login" 或 "users/123/roles"

    Returns:
        匹配到的 Scope 名称，未匹配返回 None
    """
    # 去除首尾斜杠以统一格式
    endpoint = endpoint.strip("/")

    for pattern, scope in ENDPOINT_SCOPE_MAP.items():
        if fnmatch(endpoint, pattern):
            return scope

    return None


async def check_scope(app_id: str, endpoint: str) -> str:
    """
    检查应用是否拥有访问指定端点所需的 Scope。

    从缓存加载应用的 Scope 列表，匹配端点所需的 Scope，
    如果应用未被授予该 Scope 则抛出 403 异常。

    Args:
        app_id: 应用的 app_id
        endpoint: 去掉网关前缀后的相对路径

    Returns:
        匹配到的 Scope 名称

    Raises:
        HTTPException: 403 insufficient_scope（应用缺少所需权限）
    """
    required_scope = _match_endpoint(endpoint)

    # 端点未在映射表中 → 无需 Scope 检查（如 /health、/info）
    if required_scope is None:
        return ""

    app_scopes = await get_app_scopes(app_id)

    if required_scope not in app_scopes:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "insufficient_scope",
                "message": f"应用未被授予所需的权限范围: {required_scope}",
            },
        )

    return required_scope
