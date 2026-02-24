"""
限流器模块单元测试

测试 services/gateway/rate_limiter.py 中的核心逻辑：
- check_rate_limit: 滑动窗口限流检查
- RateLimitResult: 结果对象和响应头生成
"""
import math
import time
import uuid
import pytest
from unittest.mock import patch, MagicMock, call

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.rate_limiter import (
    check_rate_limit,
    RateLimitResult,
    RATE_LIMIT_PREFIX,
    WINDOW_SIZE_SECONDS,
    DEFAULT_RATE_LIMIT,
)


# ==================== RateLimitResult ====================

class TestRateLimitResult:
    """RateLimitResult 数据类测试"""

    def test_allowed_result_headers(self):
        """允许请求时响应头包含 Limit、Remaining、Reset"""
        result = RateLimitResult(
            allowed=True,
            limit=60,
            remaining=59,
            reset=1700000060,
        )
        headers = result.headers
        assert headers["X-RateLimit-Limit"] == "60"
        assert headers["X-RateLimit-Remaining"] == "59"
        assert headers["X-RateLimit-Reset"] == "1700000060"
        assert "Retry-After" not in headers

    def test_denied_result_headers_include_retry_after(self):
        """超限时响应头额外包含 Retry-After"""
        result = RateLimitResult(
            allowed=False,
            limit=60,
            remaining=0,
            reset=1700000060,
            retry_after=30,
        )
        headers = result.headers
        assert headers["X-RateLimit-Limit"] == "60"
        assert headers["X-RateLimit-Remaining"] == "0"
        assert headers["X-RateLimit-Reset"] == "1700000060"
        assert headers["Retry-After"] == "30"

    def test_remaining_never_negative_in_headers(self):
        """remaining 为 0 时 header 值为 "0" """
        result = RateLimitResult(allowed=False, limit=10, remaining=0, reset=100)
        assert result.headers["X-RateLimit-Remaining"] == "0"

    def test_custom_limit_reflected_in_headers(self):
        """自定义限流阈值应正确反映在响应头中"""
        result = RateLimitResult(allowed=True, limit=1000, remaining=999, reset=200)
        assert result.headers["X-RateLimit-Limit"] == "1000"


# ==================== check_rate_limit ====================

class TestCheckRateLimit:
    """check_rate_limit 函数测试"""

    @pytest.fixture
    def app_id(self):
        return str(uuid.uuid4())

    @pytest.fixture
    def mock_redis(self):
        redis = MagicMock()
        # pipeline mock
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]  # zremrangebyscore result, zcard result
        redis.pipeline.return_value = pipe
        return redis

    @pytest.mark.asyncio
    async def test_first_request_allowed(self, app_id, mock_redis):
        """第一个请求应被允许，remaining = limit - 1"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]  # 窗口内 0 个请求
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.allowed is True
            assert result.limit == 60
            assert result.remaining == 59
            assert result.reset > int(time.time())

    @pytest.mark.asyncio
    async def test_request_within_limit_allowed(self, app_id, mock_redis):
        """窗口内请求数未达上限时应被允许"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 30]  # 窗口内 30 个请求
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.allowed is True
            assert result.remaining == 29  # 60 - 30 - 1

    @pytest.mark.asyncio
    async def test_request_at_limit_denied(self, app_id, mock_redis):
        """窗口内请求数达到上限时应被拒绝"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 60]  # 窗口内已有 60 个请求

        mock_redis.pipeline.return_value = pipe
        # 模拟获取最早请求时间戳
        earliest_ts = time.time() * 1000 - 30000  # 30 秒前
        mock_redis.zrange.return_value = [("req-id", earliest_ts)]

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.allowed is False
            assert result.remaining == 0
            assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_request_over_limit_denied(self, app_id, mock_redis):
        """窗口内请求数超过上限时应被拒绝"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 100]  # 窗口内已有 100 个请求

        mock_redis.pipeline.return_value = pipe
        earliest_ts = time.time() * 1000 - 10000  # 10 秒前
        mock_redis.zrange.return_value = [("req-id", earliest_ts)]

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.allowed is False
            assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_denied_result_has_retry_after(self, app_id, mock_redis):
        """超限时 retry_after 应为正整数"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 60]

        mock_redis.pipeline.return_value = pipe
        earliest_ts = time.time() * 1000 - 20000  # 20 秒前
        mock_redis.zrange.return_value = [("req-id", earliest_ts)]

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.retry_after >= 1
            assert isinstance(result.retry_after, int)

    @pytest.mark.asyncio
    async def test_denied_no_earliest_uses_window_size(self, app_id, mock_redis):
        """超限但无最早请求时 retry_after 使用窗口大小"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 60]

        mock_redis.pipeline.return_value = pipe
        mock_redis.zrange.return_value = []

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.retry_after == WINDOW_SIZE_SECONDS

    @pytest.mark.asyncio
    async def test_custom_limit(self, app_id, mock_redis):
        """自定义限流阈值应正确生效"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 5]  # 窗口内 5 个请求
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=100)

            assert result.allowed is True
            assert result.limit == 100
            assert result.remaining == 94  # 100 - 5 - 1

    @pytest.mark.asyncio
    async def test_default_limit_is_60(self, app_id, mock_redis):
        """默认限流阈值为 60"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id)

            assert result.limit == DEFAULT_RATE_LIMIT
            assert result.limit == 60

    @pytest.mark.asyncio
    async def test_redis_key_uses_correct_prefix(self, app_id, mock_redis):
        """Redis key 应使用 rate_limit:{app_id} 格式"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        expected_key = f"{RATE_LIMIT_PREFIX}{app_id}"

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            await check_rate_limit(app_id)

            # 验证 zremrangebyscore 使用了正确的 key
            pipe.zremrangebyscore.assert_called_once()
            actual_key = pipe.zremrangebyscore.call_args[0][0]
            assert actual_key == expected_key

    @pytest.mark.asyncio
    async def test_expired_entries_removed(self, app_id, mock_redis):
        """应移除窗口之前的过期成员"""
        pipe = MagicMock()
        pipe.execute.return_value = [3, 10]  # 移除了 3 个过期成员，剩余 10 个
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=60)

            assert result.allowed is True
            assert result.remaining == 49  # 60 - 10 - 1
            pipe.zremrangebyscore.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_timestamp_in_future(self, app_id, mock_redis):
        """reset 时间戳应在当前时间之后"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id)

            now = int(time.time())
            assert result.reset > now
            assert result.reset <= now + WINDOW_SIZE_SECONDS + 1

    @pytest.mark.asyncio
    async def test_key_expiry_set_on_allowed(self, app_id, mock_redis):
        """允许请求时应设置 key 过期时间"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            await check_rate_limit(app_id)

            # 第二个 pipeline 应调用 expire
            pipe2.expire.assert_called_once()
            expire_args = pipe2.expire.call_args[0]
            assert expire_args[1] == WINDOW_SIZE_SECONDS + 1

    @pytest.mark.asyncio
    async def test_limit_of_one(self, app_id, mock_redis):
        """限流阈值为 1 时，第一个请求允许，第二个拒绝"""
        # 第一个请求：窗口内 0 个
        pipe = MagicMock()
        pipe.execute.return_value = [0, 0]
        pipe2 = MagicMock()
        pipe2.execute.return_value = [True, True]

        call_count = [0]

        def pipeline_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe
            return pipe2

        mock_redis.pipeline.side_effect = pipeline_side_effect

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=1)
            assert result.allowed is True
            assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_limit_of_one_second_request_denied(self, app_id, mock_redis):
        """限流阈值为 1 时，窗口内已有 1 个请求则拒绝"""
        pipe = MagicMock()
        pipe.execute.return_value = [0, 1]  # 窗口内已有 1 个请求

        mock_redis.pipeline.return_value = pipe
        earliest_ts = time.time() * 1000 - 5000
        mock_redis.zrange.return_value = [("req-id", earliest_ts)]

        with patch("services.gateway.rate_limiter.get_redis", return_value=mock_redis):
            result = await check_rate_limit(app_id, limit=1)
            assert result.allowed is False
            assert result.remaining == 0
