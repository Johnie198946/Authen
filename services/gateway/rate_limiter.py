"""
限流器模块

基于 Redis ZSET 实现滑动窗口算法，按 app_id 维度限流。
默认限制为每分钟 60 次请求，可通过 Application.rate_limit 字段配置。

响应头:
  - X-RateLimit-Limit: 每分钟允许的最大请求数
  - X-RateLimit-Remaining: 当前窗口剩余请求数
  - X-RateLimit-Reset: 窗口重置的 Unix 时间戳

超限返回 HTTP 429 + Retry-After 头（距离窗口重置的秒数）。

需求: 6.1, 6.2, 6.3, 6.4
"""
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict

from shared.redis_client import get_redis

# 常量
RATE_LIMIT_PREFIX = "rate_limit:"
WINDOW_SIZE_SECONDS = 60  # 滑动窗口大小：60 秒
DEFAULT_RATE_LIMIT = 60   # 默认每分钟请求限制


@dataclass
class RateLimitResult:
    """限流检查结果"""

    allowed: bool
    limit: int
    remaining: int
    reset: int  # Unix 时间戳（秒）
    retry_after: int = 0  # 距离窗口重置的秒数（仅超限时有值）

    @property
    def headers(self) -> Dict[str, str]:
        """生成限流相关的响应头"""
        h: Dict[str, str] = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset),
        }
        if not self.allowed:
            h["Retry-After"] = str(self.retry_after)
        return h


async def check_rate_limit(app_id: str, limit: int = DEFAULT_RATE_LIMIT) -> RateLimitResult:
    """
    使用 Redis ZSET 实现滑动窗口限流。

    算法:
      1. 获取当前时间戳（毫秒）
      2. 计算窗口起始时间 = 当前时间 - 60s
      3. 移除 ZSET 中窗口之前的过期成员
      4. 统计当前窗口内的请求数
      5. 如果未超限，添加新成员（score=当前时间戳, member=唯一请求ID）
      6. 设置 key 过期时间为窗口大小（自动清理）

    Args:
        app_id: 应用的 app_id
        limit: 每分钟允许的最大请求数

    Returns:
        RateLimitResult 包含是否允许、限流头信息和 retry_after
    """
    redis = get_redis()
    key = f"{RATE_LIMIT_PREFIX}{app_id}"

    now_ms = time.time() * 1000  # 当前时间戳（毫秒）
    window_start_ms = now_ms - (WINDOW_SIZE_SECONDS * 1000)

    # 窗口重置时间 = 当前时间 + 窗口大小
    now_s = time.time()
    reset_timestamp = int(math.ceil(now_s)) + WINDOW_SIZE_SECONDS

    # 使用 pipeline 减少 Redis 往返
    pipe = redis.pipeline(transaction=True)

    # 1. 移除窗口之前的过期成员
    pipe.zremrangebyscore(key, 0, window_start_ms)

    # 2. 统计当前窗口内的请求数
    pipe.zcard(key)

    results = pipe.execute()
    current_count = results[1]

    if current_count >= limit:
        # 超限：计算 retry_after
        # 获取窗口内最早的请求时间戳，据此计算何时有配额释放
        earliest = redis.zrange(key, 0, 0, withscores=True)
        if earliest:
            earliest_ms = earliest[0][1]
            retry_after = max(1, int(math.ceil((earliest_ms + WINDOW_SIZE_SECONDS * 1000 - now_ms) / 1000)))
        else:
            retry_after = WINDOW_SIZE_SECONDS

        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            reset=reset_timestamp,
            retry_after=retry_after,
        )

    # 未超限：添加新请求记录
    request_id = str(uuid.uuid4())
    pipe2 = redis.pipeline(transaction=True)
    pipe2.zadd(key, {request_id: now_ms})
    pipe2.expire(key, WINDOW_SIZE_SECONDS + 1)  # +1s 余量，确保 key 不会提前过期
    pipe2.execute()

    remaining = max(0, limit - current_count - 1)

    return RateLimitResult(
        allowed=True,
        limit=limit,
        remaining=remaining,
        reset=reset_timestamp,
    )
