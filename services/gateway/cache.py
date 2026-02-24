"""
Redis 缓存管理模块

管理应用配置的 Redis 缓存读写，包括登录方式、权限范围和 OAuth 配置。
缓存 TTL 300 秒，配置变更时删除对应 key 使缓存失效。

Key 模式:
  - app:{app_id}           Hash   应用基本信息
  - app:{app_id}:methods   Set    已启用的登录方式
  - app:{app_id}:scopes    Set    已授权的 Scope
  - app:{app_id}:oauth:{provider}  Hash  加密的 OAuth 配置

需求: 2.4, 5.3
"""
import json
from typing import Optional, Set

from shared.database import SessionLocal
from shared.models.application import AppLoginMethod, AppScope
from shared.redis_client import get_redis

# 缓存常量（与 dependencies.py 保持一致）
APP_CACHE_PREFIX = "app:"
APP_CACHE_TTL = 300  # 5 分钟


def _get_db():
    """创建数据库会话"""
    return SessionLocal()


# ---------------------------------------------------------------------------
# 登录方式缓存
# ---------------------------------------------------------------------------

async def get_app_methods(app_id: str) -> Set[str]:
    """
    获取应用已启用的登录方式集合。

    优先从 Redis 缓存读取，缓存未命中时查询数据库并写入缓存。

    Args:
        app_id: 应用的 app_id

    Returns:
        已启用的登录方式名称集合，如 {"email", "phone"}
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}:methods"

    # 尝试从缓存读取
    cached = redis.smembers(cache_key)
    if cached:
        return cached

    # 缓存未命中，查询数据库
    db = _get_db()
    try:
        from shared.models.application import Application

        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app:
            return set()

        methods = (
            db.query(AppLoginMethod)
            .filter(
                AppLoginMethod.application_id == app.id,
                AppLoginMethod.is_enabled.is_(True),
            )
            .all()
        )

        enabled_methods = {m.method for m in methods}

        # 写入缓存（仅当有数据时）
        if enabled_methods:
            redis.sadd(cache_key, *enabled_methods)
            redis.expire(cache_key, APP_CACHE_TTL)

        return enabled_methods
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 权限范围缓存
# ---------------------------------------------------------------------------

async def get_app_scopes(app_id: str) -> Set[str]:
    """
    获取应用已授权的权限范围集合。

    优先从 Redis 缓存读取，缓存未命中时查询数据库并写入缓存。

    Args:
        app_id: 应用的 app_id

    Returns:
        已授权的 Scope 名称集合，如 {"user:read", "auth:login"}
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}:scopes"

    # 尝试从缓存读取
    cached = redis.smembers(cache_key)
    if cached:
        return cached

    # 缓存未命中，查询数据库
    db = _get_db()
    try:
        from shared.models.application import Application

        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app:
            return set()

        scopes = (
            db.query(AppScope)
            .filter(AppScope.application_id == app.id)
            .all()
        )

        scope_names = {s.scope for s in scopes}

        # 写入缓存（仅当有数据时）
        if scope_names:
            redis.sadd(cache_key, *scope_names)
            redis.expire(cache_key, APP_CACHE_TTL)

        return scope_names
    finally:
        db.close()


# ---------------------------------------------------------------------------
# OAuth 配置缓存
# ---------------------------------------------------------------------------

async def get_app_oauth_config(app_id: str, provider: str) -> Optional[dict]:
    """
    获取应用的 OAuth 提供商配置。

    优先从 Redis 缓存读取，缓存未命中时查询数据库并写入缓存。
    OAuth 配置在数据库中以加密形式存储，缓存中同样保持加密状态。

    Args:
        app_id: 应用的 app_id
        provider: OAuth 提供商名称（wechat/alipay/google/apple）

    Returns:
        解密后的 OAuth 配置字典 {"client_id": ..., "client_secret": ...}，
        如果未配置则返回 None。
    """
    from shared.utils.crypto import decrypt_config

    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}:oauth:{provider}"

    # 尝试从缓存读取
    cached = redis.hgetall(cache_key)
    if cached and "encrypted_config" in cached:
        try:
            return decrypt_config(cached["encrypted_config"])
        except (ValueError, Exception):
            # 缓存数据损坏，删除并回退到数据库
            redis.delete(cache_key)

    # 缓存未命中，查询数据库
    db = _get_db()
    try:
        from shared.models.application import Application

        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app:
            return None

        login_method = (
            db.query(AppLoginMethod)
            .filter(
                AppLoginMethod.application_id == app.id,
                AppLoginMethod.method == provider,
                AppLoginMethod.is_enabled.is_(True),
            )
            .first()
        )

        if not login_method or not login_method.oauth_config:
            return None

        # 写入缓存（保持加密状态）
        redis.hset(cache_key, "encrypted_config", login_method.oauth_config)
        redis.expire(cache_key, APP_CACHE_TTL)

        # 返回解密后的配置
        return decrypt_config(login_method.oauth_config)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 缓存失效
# ---------------------------------------------------------------------------

def invalidate_app_cache(app_id: str) -> int:
    """
    删除应用的所有 Redis 缓存 key。

    用于应用删除或需要完全刷新缓存的场景。
    使用 SCAN 匹配 app:{app_id}* 模式的所有 key 并删除。

    Args:
        app_id: 应用的 app_id

    Returns:
        删除的 key 数量
    """
    redis = get_redis()
    pattern = f"{APP_CACHE_PREFIX}{app_id}*"
    deleted = 0

    # 使用 SCAN 避免阻塞 Redis（比 KEYS 更安全）
    cursor = 0
    while True:
        cursor, keys = redis.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            deleted += redis.delete(*keys)
        if cursor == 0:
            break

    return deleted


def invalidate_app_methods_cache(app_id: str) -> bool:
    """
    删除应用的登录方式缓存。

    用于登录方式配置变更后使缓存失效。

    Args:
        app_id: 应用的 app_id

    Returns:
        是否成功删除（key 存在时为 True）
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}:methods"
    return redis.delete(cache_key) > 0


def invalidate_app_scopes_cache(app_id: str) -> bool:
    """
    删除应用的权限范围缓存。

    用于 Scope 配置变更后使缓存失效。

    Args:
        app_id: 应用的 app_id

    Returns:
        是否成功删除（key 存在时为 True）
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}:scopes"
    return redis.delete(cache_key) > 0


def invalidate_app_oauth_cache(app_id: str, provider: str) -> bool:
    """
    删除应用的指定 OAuth 提供商配置缓存。

    用于 OAuth 配置变更后使缓存失效。

    Args:
        app_id: 应用的 app_id
        provider: OAuth 提供商名称

    Returns:
        是否成功删除（key 存在时为 True）
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}:oauth:{provider}"
    return redis.delete(cache_key) > 0


def invalidate_app_config_cache(app_id: str) -> int:
    """
    删除应用的基本信息缓存。

    用于应用基本信息（名称、状态、限流阈值等）变更后使缓存失效。

    Args:
        app_id: 应用的 app_id

    Returns:
        删除的 key 数量
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}"
    return redis.delete(cache_key)
