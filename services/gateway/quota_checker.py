"""
配额检查模块

负责大模型 API 的配额检查、扣减和响应头注入。
使用 Redis 原子计数器保证高并发性能，PostgreSQL 存储配额配置。

Redis Key 设计:
  - quota:{app_id}:requests          当前周期请求次数计数器 (String, INCRBY)
  - quota:{app_id}:tokens            当前周期 Token 消耗量计数器 (String, INCRBYFLOAT)
  - quota:{app_id}:cycle_start       当前计费周期开始时间 (String, ISO format)
  - quota:{app_id}:config            配额配置缓存 (Hash)
  - quota:{app_id}:warning_sent:80   80% 预警已发送标记
  - quota:{app_id}:warning_sent:100  100% 耗尽已发送标记

降级策略: Redis 不可用时放行请求并记录 WARNING 日志。

需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5,
      5.1, 5.2, 5.3, 5.5, 5.6, 9.1, 9.2, 9.3
"""
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

from shared.database import SessionLocal
from shared.redis_client import get_redis

logger = logging.getLogger("gateway.quota_checker")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
QUOTA_KEY_PREFIX = "quota:"
QUOTA_CONFIG_CACHE_TTL = 300  # 配额配置缓存 5 分钟
SAFETY_MARGIN_SECONDS = 86400  # TTL 安全余量 1 天


# ---------------------------------------------------------------------------
# QuotaCheckResult 数据类
# ---------------------------------------------------------------------------

@dataclass
class QuotaCheckResult:
    """配额检查结果"""

    allowed: bool
    request_limit: int
    request_used: int
    request_remaining: int
    token_limit: int
    token_used: int
    token_remaining: int
    reset_timestamp: int  # Unix 时间戳
    error_code: Optional[str] = None
    warning: Optional[str] = None

    @property
    def headers(self) -> Dict[str, str]:
        """生成 X-Quota-* 响应头"""
        h: Dict[str, str] = {
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


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _get_db():
    """创建数据库会话"""
    return SessionLocal()


def _quota_key(app_id: str, suffix: str) -> str:
    """构造 Redis key"""
    return f"{QUOTA_KEY_PREFIX}{app_id}:{suffix}"


def _compute_cycle_ttl(cycle_start: datetime, period_days: int) -> int:
    """计算当前周期剩余秒数 + 安全余量"""
    cycle_end = cycle_start + timedelta(days=period_days)
    remaining = (cycle_end - datetime.utcnow()).total_seconds()
    return max(int(remaining) + SAFETY_MARGIN_SECONDS, SAFETY_MARGIN_SECONDS)


def _compute_remaining(limit: int, used: int) -> int:
    """计算剩余配额。-1 表示无限制，remaining 始终返回 -1"""
    if limit == -1:
        return -1
    return max(0, limit - used)


def _compute_reset_timestamp(cycle_start: datetime, period_days: int) -> int:
    """计算周期重置的 Unix 时间戳"""
    cycle_end = cycle_start + timedelta(days=period_days)
    return int(cycle_end.timestamp())


def _determine_warning(
    request_limit: int,
    request_used: int,
    token_limit: int,
    token_used: int,
) -> Optional[str]:
    """
    根据使用率判断预警级别。

    返回 'exhausted' 如果任一配额达到 100%，
    返回 'approaching_limit' 如果任一配额超过 80%，
    否则返回 None。
    """
    levels = []
    for limit, used in [(request_limit, request_used), (token_limit, token_used)]:
        if limit <= 0:
            # -1 无限制，0 不应出现但安全处理
            continue
        ratio = used / limit
        if ratio >= 1.0:
            return "exhausted"
        if ratio >= 0.8:
            levels.append("approaching_limit")
    return "approaching_limit" if levels else None


async def _load_quota_config(app_id: str) -> Optional[dict]:
    """
    从 Redis 缓存或 PostgreSQL 加载配额配置。

    返回 dict 包含:
      - request_quota: int
      - token_quota: int
      - quota_period_days: int
      - cycle_start: datetime

    如果应用未绑定订阅计划，返回 None。
    """
    redis = get_redis()
    config_key = _quota_key(app_id, "config")

    # 尝试从 Redis Hash 缓存读取
    cached = redis.hgetall(config_key)
    if cached and "request_quota" in cached:
        cycle_start_key = _quota_key(app_id, "cycle_start")
        cycle_start_str = redis.get(cycle_start_key)
        cycle_start = (
            datetime.fromisoformat(cycle_start_str)
            if cycle_start_str
            else datetime.utcnow()
        )
        return {
            "request_quota": int(cached["request_quota"]),
            "token_quota": int(cached["token_quota"]),
            "quota_period_days": int(cached["quota_period_days"]),
            "cycle_start": cycle_start,
        }

    # 缓存未命中，查询数据库
    return await _load_quota_config_from_db(app_id)


async def _load_quota_config_from_db(app_id: str) -> Optional[dict]:
    """从 PostgreSQL 加载配额配置并写入 Redis 缓存"""
    from shared.models.application import Application, AppSubscriptionPlan
    from shared.models.subscription import SubscriptionPlan
    from shared.models.quota import AppQuotaOverride

    db = _get_db()
    try:
        # 查找应用
        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app:
            return None

        # 查找应用绑定的订阅计划
        binding = (
            db.query(AppSubscriptionPlan)
            .filter(AppSubscriptionPlan.application_id == app.id)
            .first()
        )
        if not binding:
            return None

        plan = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.id == binding.plan_id)
            .first()
        )
        if not plan:
            return None

        # 查找手动覆盖
        override = (
            db.query(AppQuotaOverride)
            .filter(AppQuotaOverride.application_id == app.id)
            .first()
        )

        # 计算有效配额（覆盖优先）
        effective_request_quota = plan.request_quota
        effective_token_quota = plan.token_quota
        if override:
            if override.request_quota is not None:
                effective_request_quota = override.request_quota
            if override.token_quota is not None:
                effective_token_quota = override.token_quota

        period_days = plan.quota_period_days

        # 确定周期开始时间
        redis = get_redis()
        cycle_start_key = _quota_key(app_id, "cycle_start")
        cycle_start_str = redis.get(cycle_start_key)
        if cycle_start_str:
            cycle_start = datetime.fromisoformat(cycle_start_str)
        else:
            cycle_start = datetime.utcnow()
            ttl = _compute_cycle_ttl(cycle_start, period_days)
            redis.setex(cycle_start_key, ttl, cycle_start.isoformat())

        # 检查周期是否已过期，如果过期则重置
        cycle_end = cycle_start + timedelta(days=period_days)
        if datetime.utcnow() >= cycle_end:
            cycle_start = datetime.utcnow()
            ttl = _compute_cycle_ttl(cycle_start, period_days)
            redis.setex(cycle_start_key, ttl, cycle_start.isoformat())
            # 重置计数器
            req_key = _quota_key(app_id, "requests")
            tok_key = _quota_key(app_id, "tokens")
            redis.delete(req_key, tok_key)

        # 写入配置缓存
        config_key = _quota_key(app_id, "config")
        redis.hset(config_key, mapping={
            "request_quota": str(effective_request_quota),
            "token_quota": str(effective_token_quota),
            "quota_period_days": str(period_days),
        })
        redis.expire(config_key, QUOTA_CONFIG_CACHE_TTL)

        return {
            "request_quota": effective_request_quota,
            "token_quota": effective_token_quota,
            "quota_period_days": period_days,
            "cycle_start": cycle_start,
        }
    finally:
        db.close()


async def _get_app_webhook_config(app_id: str) -> Optional[dict]:
    """
    查询应用的 Webhook 配置（webhook_url 和 webhook_secret）。

    返回 dict 包含 webhook_url 和 webhook_secret，如果应用未配置回调地址则返回 None。
    """
    from shared.models.application import Application

    db = _get_db()
    try:
        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app or not app.webhook_url:
            return None
        return {
            "webhook_url": app.webhook_url,
            "webhook_secret": app.webhook_secret,
        }
    finally:
        db.close()


async def _check_and_send_warning(
    app_id: str,
    request_limit: int,
    request_used: int,
    token_limit: int,
    token_used: int,
    ttl: int,
    reset_timestamp: int = 0,
) -> None:
    """
    检查配额使用率并触发预警事件（防重复）。

    80% → quota.warning 事件
    100% → quota.exhausted 事件
    通过 Redis 标记位 quota:{app_id}:warning_sent:{level} 防止同一周期重复触发。
    如果应用配置了 webhook_url，同时通过 Webhook 推送事件（需求 9.4）。
    """
    redis = get_redis()
    webhook_config = None  # 延迟加载

    for limit, used, resource in [
        (request_limit, request_used, "request"),
        (token_limit, token_used, "token"),
    ]:
        if limit <= 0:
            continue
        ratio = used / limit

        # 100% 耗尽检查
        if ratio >= 1.0:
            warning_key = _quota_key(app_id, "warning_sent:100")
            if not redis.exists(warning_key):
                redis.setex(warning_key, ttl, "1")
                logger.info(
                    "quota.exhausted | app_id=%s resource=%s used=%s limit=%s",
                    app_id, resource, used, limit,
                )
                # Webhook 推送
                webhook_config = await _maybe_push_webhook(
                    app_id, "quota.exhausted", resource, used, limit,
                    reset_timestamp, webhook_config,
                )

        # 80% 预警检查
        if ratio >= 0.8:
            warning_key = _quota_key(app_id, "warning_sent:80")
            if not redis.exists(warning_key):
                redis.setex(warning_key, ttl, "1")
                logger.info(
                    "quota.warning | app_id=%s resource=%s used=%s limit=%s",
                    app_id, resource, used, limit,
                )
                # Webhook 推送
                webhook_config = await _maybe_push_webhook(
                    app_id, "quota.warning", resource, used, limit,
                    reset_timestamp, webhook_config,
                )


async def _maybe_push_webhook(
    app_id: str,
    event_type: str,
    resource: str,
    used: int,
    limit: int,
    reset_timestamp: int,
    cached_config: Optional[dict],
) -> Optional[dict]:
    """
    如果应用配置了 webhook_url，推送配额事件。

    返回 webhook_config（用于缓存，避免重复查询数据库）。
    """
    from services.subscription.webhook_push import push_quota_webhook

    if cached_config is None:
        cached_config = await _get_app_webhook_config(app_id)

    if cached_config and cached_config.get("webhook_url"):
        try:
            await push_quota_webhook(
                app_id=app_id,
                webhook_url=cached_config["webhook_url"],
                webhook_secret=cached_config.get("webhook_secret"),
                event_type=event_type,
                resource=resource,
                current_used=used,
                limit=limit,
                reset_timestamp=reset_timestamp,
            )
        except Exception as e:
            logger.warning(
                "Webhook push error (non-blocking) | app_id=%s event=%s error=%s",
                app_id, event_type, str(e),
            )

    return cached_config


def _build_degraded_result() -> QuotaCheckResult:
    """构建 Redis 降级时的放行结果"""
    return QuotaCheckResult(
        allowed=True,
        request_limit=-1,
        request_used=0,
        request_remaining=-1,
        token_limit=-1,
        token_used=0,
        token_remaining=-1,
        reset_timestamp=0,
        error_code=None,
        warning=None,
    )


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

async def check_quota(app_id: str) -> QuotaCheckResult:
    """
    检查应用配额（请求前调用）。

    流程:
      1. 从 Redis/PostgreSQL 加载配额配置
      2. 从 Redis 读取当前计数器
      3. 计算剩余配额
      4. 判断是否放行

    降级策略: Redis ConnectionError/TimeoutError 时返回 allowed=True。
    """
    import redis as redis_lib

    try:
        # 加载配额配置
        config = await _load_quota_config(app_id)
        if config is None:
            return QuotaCheckResult(
                allowed=False,
                request_limit=0,
                request_used=0,
                request_remaining=0,
                token_limit=0,
                token_used=0,
                token_remaining=0,
                reset_timestamp=0,
                error_code="quota_not_configured",
                warning=None,
            )

        request_limit = config["request_quota"]
        token_limit = config["token_quota"]
        period_days = config["quota_period_days"]
        cycle_start = config["cycle_start"]

        reset_ts = _compute_reset_timestamp(cycle_start, period_days)

        # 从 Redis 读取当前计数器
        redis = get_redis()
        req_key = _quota_key(app_id, "requests")
        tok_key = _quota_key(app_id, "tokens")

        pipe = redis.pipeline(transaction=False)
        pipe.get(req_key)
        pipe.get(tok_key)
        results = pipe.execute()

        request_used = int(results[0] or 0)
        token_used = int(float(results[1] or 0))

        request_remaining = _compute_remaining(request_limit, request_used)
        token_remaining = _compute_remaining(token_limit, token_used)

        # 判断是否放行
        allowed = True
        error_code = None

        if request_limit != -1 and request_remaining <= 0:
            allowed = False
            error_code = "request_quota_exceeded"
        elif token_limit != -1 and token_remaining <= 0:
            allowed = False
            error_code = "token_quota_exceeded"

        # 计算预警
        warning = _determine_warning(request_limit, request_used, token_limit, token_used)

        # 异步检查并发送预警事件（防重复）
        ttl = _compute_cycle_ttl(cycle_start, period_days)
        await _check_and_send_warning(
            app_id, request_limit, request_used, token_limit, token_used, ttl,
            reset_timestamp=reset_ts,
        )

        return QuotaCheckResult(
            allowed=allowed,
            request_limit=request_limit,
            request_used=request_used,
            request_remaining=request_remaining,
            token_limit=token_limit,
            token_used=token_used,
            token_remaining=token_remaining,
            reset_timestamp=reset_ts,
            error_code=error_code,
            warning=warning,
        )

    except (redis_lib.ConnectionError, redis_lib.TimeoutError) as e:
        logger.warning("Redis 不可用，配额检查降级放行: %s", str(e))
        return _build_degraded_result()


async def deduct_request_quota(app_id: str) -> None:
    """
    扣减请求次数配额（请求成功后调用）。

    使用 Redis INCRBY 原子递增请求计数器。
    """
    import redis as redis_lib

    try:
        redis = get_redis()
        req_key = _quota_key(app_id, "requests")
        redis.incrby(req_key, 1)

        # 确保 key 有 TTL（首次创建时设置）
        if redis.ttl(req_key) == -1:
            config = await _load_quota_config(app_id)
            if config:
                ttl = _compute_cycle_ttl(config["cycle_start"], config["quota_period_days"])
                redis.expire(req_key, ttl)

    except (redis_lib.ConnectionError, redis_lib.TimeoutError) as e:
        logger.warning("Redis 不可用，请求配额扣减跳过: %s", str(e))


async def deduct_token_quota(app_id: str, token_usage: int) -> QuotaCheckResult:
    """
    扣减 Token 配额并返回更新后的状态（下游响应后调用）。

    使用 Redis INCRBYFLOAT 原子递增 Token 计数器。
    Token 超额允许当次完成（不回滚），但后续检查会拒绝。
    """
    import redis as redis_lib

    try:
        redis = get_redis()
        tok_key = _quota_key(app_id, "tokens")

        # 原子递增
        new_token_used = float(redis.incrbyfloat(tok_key, token_usage))

        # 确保 key 有 TTL
        if redis.ttl(tok_key) == -1:
            config = await _load_quota_config(app_id)
            if config:
                ttl = _compute_cycle_ttl(config["cycle_start"], config["quota_period_days"])
                redis.expire(tok_key, ttl)

        # 加载配置以构建完整结果
        config = await _load_quota_config(app_id)
        if config is None:
            return _build_degraded_result()

        request_limit = config["request_quota"]
        token_limit = config["token_quota"]
        period_days = config["quota_period_days"]
        cycle_start = config["cycle_start"]
        reset_ts = _compute_reset_timestamp(cycle_start, period_days)

        # 读取请求计数器
        req_key = _quota_key(app_id, "requests")
        request_used = int(redis.get(req_key) or 0)
        token_used = int(new_token_used)

        request_remaining = _compute_remaining(request_limit, request_used)
        token_remaining = _compute_remaining(token_limit, token_used)

        warning = _determine_warning(request_limit, request_used, token_limit, token_used)

        # 检查并发送预警事件
        ttl = _compute_cycle_ttl(cycle_start, period_days)
        await _check_and_send_warning(
            app_id, request_limit, request_used, token_limit, token_used, ttl,
            reset_timestamp=reset_ts,
        )

        # 判断错误码（Token 超额允许当次完成，但标记状态）
        error_code = None
        allowed = True
        if request_limit != -1 and request_remaining <= 0:
            error_code = "request_quota_exceeded"
            allowed = False
        elif token_limit != -1 and token_remaining <= 0:
            error_code = "token_quota_exceeded"
            allowed = False

        return QuotaCheckResult(
            allowed=allowed,
            request_limit=request_limit,
            request_used=request_used,
            request_remaining=request_remaining,
            token_limit=token_limit,
            token_used=token_used,
            token_remaining=token_remaining,
            reset_timestamp=reset_ts,
            error_code=error_code,
            warning=warning,
        )

    except (redis_lib.ConnectionError, redis_lib.TimeoutError) as e:
        logger.warning("Redis 不可用，Token 配额扣减跳过: %s", str(e))
        return _build_degraded_result()


async def get_quota_usage(app_id: str) -> dict:
    """
    获取应用当前配额使用情况（供 /api/v1/quota/usage 端点使用）。

    从 Redis 读取实时计数器数据。
    """
    import redis as redis_lib

    try:
        config = await _load_quota_config(app_id)
        if config is None:
            return {
                "error_code": "quota_not_configured",
                "message": "应用未配置配额计划",
            }

        request_limit = config["request_quota"]
        token_limit = config["token_quota"]
        period_days = config["quota_period_days"]
        cycle_start = config["cycle_start"]
        cycle_end = cycle_start + timedelta(days=period_days)
        reset_ts = int(cycle_end.timestamp())

        # 从 Redis 读取计数器
        redis = get_redis()
        req_key = _quota_key(app_id, "requests")
        tok_key = _quota_key(app_id, "tokens")

        pipe = redis.pipeline(transaction=False)
        pipe.get(req_key)
        pipe.get(tok_key)
        results = pipe.execute()

        request_used = int(results[0] or 0)
        token_used = int(float(results[1] or 0))

        request_remaining = _compute_remaining(request_limit, request_used)
        token_remaining = _compute_remaining(token_limit, token_used)

        return {
            "request_quota_limit": request_limit,
            "request_quota_used": request_used,
            "request_quota_remaining": request_remaining,
            "token_quota_limit": token_limit,
            "token_quota_used": token_used,
            "token_quota_remaining": token_remaining,
            "billing_cycle_start": cycle_start.isoformat(),
            "billing_cycle_end": cycle_end.isoformat(),
            "billing_cycle_reset": reset_ts,
        }

    except (redis_lib.ConnectionError, redis_lib.TimeoutError) as e:
        logger.warning("Redis 不可用，配额查询降级: %s", str(e))
        return {
            "error_code": "service_degraded",
            "message": "配额服务暂时不可用，请稍后重试",
        }
