"""
网关依赖注入模块 - 应用凭证验证

提供 verify_app_credential 函数，用于验证三方系统的 app_id + app_secret 凭证。
从 Redis 缓存优先加载应用配置，缓存未命中时回退到数据库查询。

需求: 3.6, 1.4, 4.1, 4.2
"""
import json
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from shared.database import SessionLocal
from shared.models.application import Application
from shared.redis_client import get_redis
from shared.utils.crypto import verify_password


# Redis 缓存 key 前缀和 TTL
APP_CACHE_PREFIX = "app:"
APP_CACHE_TTL = 300  # 5 分钟


def _get_db() -> Session:
    """创建数据库会话（非生成器版本，用于手动管理生命周期）"""
    return SessionLocal()


async def get_app_from_cache_or_db(app_id: str) -> Optional[dict]:
    """
    从 Redis 缓存或数据库加载应用配置。

    缓存命中时直接返回；未命中时查询数据库并写入缓存（TTL 300s）。

    Args:
        app_id: 应用的 app_id

    Returns:
        应用配置字典，包含 id, name, app_id, app_secret_hash, status, rate_limit；
        如果应用不存在则返回 None。
    """
    redis = get_redis()
    cache_key = f"{APP_CACHE_PREFIX}{app_id}"

    # 尝试从 Redis 缓存读取
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 缓存未命中，查询数据库
    db = _get_db()
    try:
        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app:
            return None

        app_data = {
            "id": str(app.id),
            "name": app.name,
            "app_id": app.app_id,
            "app_secret_hash": app.app_secret_hash,
            "status": app.status,
            "rate_limit": app.rate_limit,
        }

        # 写入 Redis 缓存
        redis.setex(cache_key, APP_CACHE_TTL, json.dumps(app_data))

        return app_data
    finally:
        db.close()


async def verify_app_credential(app_id: str, app_secret: str) -> dict:
    """
    验证应用凭证。

    行为：
    - app_id 不存在 → 401 "凭证无效"（不区分具体原因）
    - app_secret 不匹配 → 401 "凭证无效"
    - 应用状态为 disabled → 403 "应用已被禁用"
    - 验证通过 → 返回应用配置字典

    Args:
        app_id: 应用 ID
        app_secret: 应用密钥（明文）

    Returns:
        应用配置字典

    Raises:
        HTTPException: 401 凭证无效 / 403 应用已被禁用
    """
    app_data = await get_app_from_cache_or_db(app_id)

    # app_id 不存在 → 统一返回 401
    if not app_data:
        raise HTTPException(status_code=401, detail="凭证无效")

    # 先验证密钥，再检查状态（防止通过不同错误码探测应用是否存在）
    if not verify_password(app_secret, app_data["app_secret_hash"]):
        raise HTTPException(status_code=401, detail="凭证无效")

    # 应用被禁用 → 403
    if app_data["status"] != "active":
        raise HTTPException(status_code=403, detail="应用已被禁用")

    return app_data


async def get_app_credential_from_request(request: Request) -> dict:
    """
    从请求头中提取并验证应用凭证。

    从 X-App-Id 和 X-App-Secret 请求头提取凭证，
    验证通过后将 Application 配置注入请求 state。

    Args:
        request: FastAPI Request 对象

    Returns:
        应用配置字典

    Raises:
        HTTPException: 401 缺少凭证 / 凭证无效 / 403 应用已被禁用
    """
    app_id = request.headers.get("X-App-Id")
    app_secret = request.headers.get("X-App-Secret")

    if not app_id or not app_secret:
        raise HTTPException(status_code=401, detail="凭证无效")

    app_data = await verify_app_credential(app_id, app_secret)

    # 注入到请求上下文，供后续中间件和端点使用
    request.state.app = app_data

    return app_data
