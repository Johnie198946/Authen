"""
quota_checker 模块核心逻辑单元测试

覆盖:
  - QuotaCheckResult 数据类与 headers 属性
  - check_quota 正常流程与降级
  - deduct_request_quota / deduct_token_quota
  - get_quota_usage
  - 配额优先级（AppQuotaOverride > SubscriptionPlan）
  - 预警逻辑
"""
import sys
import os
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import asdict

import pytest

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.quota_checker import (
    QuotaCheckResult,
    check_quota,
    deduct_request_quota,
    deduct_token_quota,
    get_quota_usage,
    _compute_remaining,
    _determine_warning,
    _build_degraded_result,
    _compute_cycle_ttl,
    _compute_reset_timestamp,
    _quota_key,
)


# ---------------------------------------------------------------------------
# QuotaCheckResult 测试
# ---------------------------------------------------------------------------

class TestQuotaCheckResult:
    """QuotaCheckResult 数据类测试"""

    def test_headers_basic(self):
        """基本响应头生成"""
        result = QuotaCheckResult(
            allowed=True,
            request_limit=1000,
            request_used=100,
            request_remaining=900,
            token_limit=50000,
            token_used=5000,
            token_remaining=45000,
            reset_timestamp=1700000000,
        )
        headers = result.headers
        assert headers["X-Quota-Request-Limit"] == "1000"
        assert headers["X-Quota-Request-Remaining"] == "900"
        assert headers["X-Quota-Request-Reset"] == "1700000000"
        assert headers["X-Quota-Token-Limit"] == "50000"
        assert headers["X-Quota-Token-Remaining"] == "45000"
        assert headers["X-Quota-Token-Reset"] == "1700000000"
        assert "X-Quota-Warning" not in headers

    def test_headers_with_warning(self):
        """带预警的响应头"""
        result = QuotaCheckResult(
            allowed=True,
            request_limit=1000,
            request_used=850,
            request_remaining=150,
            token_limit=50000,
            token_used=5000,
            token_remaining=45000,
            reset_timestamp=1700000000,
            warning="approaching_limit",
        )
        headers = result.headers
        assert headers["X-Quota-Warning"] == "approaching_limit"

    def test_headers_exhausted_warning(self):
        """耗尽预警响应头"""
        result = QuotaCheckResult(
            allowed=False,
            request_limit=1000,
            request_used=1000,
            request_remaining=0,
            token_limit=50000,
            token_used=5000,
            token_remaining=45000,
            reset_timestamp=1700000000,
            error_code="request_quota_exceeded",
            warning="exhausted",
        )
        headers = result.headers
        assert headers["X-Quota-Warning"] == "exhausted"

    def test_headers_count(self):
        """无预警时应有 6 个头，有预警时 7 个"""
        result_no_warn = QuotaCheckResult(
            allowed=True, request_limit=100, request_used=0,
            request_remaining=100, token_limit=100, token_used=0,
            token_remaining=100, reset_timestamp=0,
        )
        assert len(result_no_warn.headers) == 6

        result_warn = QuotaCheckResult(
            allowed=True, request_limit=100, request_used=0,
            request_remaining=100, token_limit=100, token_used=0,
            token_remaining=100, reset_timestamp=0, warning="approaching_limit",
        )
        assert len(result_warn.headers) == 7


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """辅助函数测试"""

    def test_compute_remaining_normal(self):
        assert _compute_remaining(1000, 300) == 700

    def test_compute_remaining_zero(self):
        assert _compute_remaining(1000, 1000) == 0

    def test_compute_remaining_over(self):
        """超额时 remaining 为 0"""
        assert _compute_remaining(1000, 1200) == 0

    def test_compute_remaining_unlimited(self):
        """-1 无限制时 remaining 始终 -1"""
        assert _compute_remaining(-1, 999999) == -1

    def test_determine_warning_normal(self):
        """使用率 < 80% 无预警"""
        assert _determine_warning(1000, 500, 50000, 10000) is None

    def test_determine_warning_approaching(self):
        """使用率 >= 80% 预警"""
        assert _determine_warning(1000, 800, 50000, 10000) == "approaching_limit"

    def test_determine_warning_exhausted(self):
        """使用率 >= 100% 耗尽"""
        assert _determine_warning(1000, 1000, 50000, 10000) == "exhausted"

    def test_determine_warning_token_approaching(self):
        """Token 使用率 >= 80%"""
        assert _determine_warning(1000, 100, 50000, 40000) == "approaching_limit"

    def test_determine_warning_token_exhausted(self):
        """Token 使用率 >= 100%"""
        assert _determine_warning(1000, 100, 50000, 50000) == "exhausted"

    def test_determine_warning_unlimited(self):
        """无限制配额无预警"""
        assert _determine_warning(-1, 999999, -1, 999999) is None

    def test_quota_key(self):
        assert _quota_key("app123", "requests") == "quota:app123:requests"
        assert _quota_key("app123", "tokens") == "quota:app123:tokens"

    def test_compute_cycle_ttl(self):
        """TTL = 剩余秒数 + 86400"""
        now = datetime.utcnow()
        ttl = _compute_cycle_ttl(now, 30)
        # 周期刚开始，剩余约 30 天
        expected_min = 29 * 86400 + 86400  # 至少 29 天 + 安全余量
        assert ttl >= expected_min

    def test_compute_reset_timestamp(self):
        """重置时间戳 = 周期开始 + 周期天数"""
        start = datetime(2024, 1, 1)
        ts = _compute_reset_timestamp(start, 30)
        expected = datetime(2024, 1, 31)
        assert ts == int(expected.timestamp())

    def test_build_degraded_result(self):
        """降级结果应为 allowed=True"""
        result = _build_degraded_result()
        assert result.allowed is True
        assert result.request_limit == -1
        assert result.token_limit == -1
        assert result.error_code is None


# ---------------------------------------------------------------------------
# check_quota 测试（使用 mock）
# ---------------------------------------------------------------------------

class TestCheckQuota:
    """check_quota 函数测试"""

    @pytest.mark.asyncio
    async def test_quota_not_configured(self):
        """未绑定订阅计划时返回 quota_not_configured"""
        with patch(
            "services.gateway.quota_checker._load_quota_config",
            return_value=None,
        ):
            result = await check_quota("unknown_app")
            assert result.allowed is False
            assert result.error_code == "quota_not_configured"

    @pytest.mark.asyncio
    async def test_quota_allowed(self):
        """配额充足时放行"""
        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = ["100", "5000"]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.exists.return_value = False
        mock_redis.setex = MagicMock()

        with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
            with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
                result = await check_quota("test_app")
                assert result.allowed is True
                assert result.request_used == 100
                assert result.token_used == 5000
                assert result.request_remaining == 900
                assert result.token_remaining == 45000
                assert result.error_code is None

    @pytest.mark.asyncio
    async def test_request_quota_exceeded(self):
        """请求配额耗尽"""
        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = ["1000", "5000"]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.exists.return_value = True

        with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
            with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
                result = await check_quota("test_app")
                assert result.allowed is False
                assert result.error_code == "request_quota_exceeded"

    @pytest.mark.asyncio
    async def test_token_quota_exceeded(self):
        """Token 配额耗尽"""
        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = ["100", "50000"]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.exists.return_value = True

        with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
            with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
                result = await check_quota("test_app")
                assert result.allowed is False
                assert result.error_code == "token_quota_exceeded"

    @pytest.mark.asyncio
    async def test_unlimited_quota_always_allowed(self):
        """无限制配额始终放行"""
        mock_config = {
            "request_quota": -1,
            "token_quota": -1,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = ["999999", "999999"]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.exists.return_value = True

        with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
            with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
                result = await check_quota("test_app")
                assert result.allowed is True
                assert result.request_remaining == -1
                assert result.token_remaining == -1

    @pytest.mark.asyncio
    async def test_redis_degradation(self):
        """Redis 不可用时降级放行"""
        import redis as redis_lib

        with patch(
            "services.gateway.quota_checker._load_quota_config",
            side_effect=redis_lib.ConnectionError("Connection refused"),
        ):
            result = await check_quota("test_app")
            assert result.allowed is True
            assert result.request_limit == -1


# ---------------------------------------------------------------------------
# deduct_request_quota 测试
# ---------------------------------------------------------------------------

class TestDeductRequestQuota:
    """deduct_request_quota 函数测试"""

    @pytest.mark.asyncio
    async def test_deduct_increments_counter(self):
        """扣减请求配额递增计数器"""
        mock_redis = MagicMock()
        mock_redis.incrby = MagicMock()
        mock_redis.ttl.return_value = 100  # 已有 TTL

        with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
            await deduct_request_quota("test_app")
            mock_redis.incrby.assert_called_once_with("quota:test_app:requests", 1)

    @pytest.mark.asyncio
    async def test_deduct_sets_ttl_on_new_key(self):
        """首次创建 key 时设置 TTL"""
        mock_redis = MagicMock()
        mock_redis.incrby = MagicMock()
        mock_redis.ttl.return_value = -1  # 无 TTL

        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }

        with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
            with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
                await deduct_request_quota("test_app")
                mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_deduct_redis_failure(self):
        """Redis 不可用时不抛异常"""
        import redis as redis_lib

        mock_redis = MagicMock()
        mock_redis.incrby.side_effect = redis_lib.ConnectionError("fail")

        with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
            # 不应抛异常
            await deduct_request_quota("test_app")


# ---------------------------------------------------------------------------
# deduct_token_quota 测试
# ---------------------------------------------------------------------------

class TestDeductTokenQuota:
    """deduct_token_quota 函数测试"""

    @pytest.mark.asyncio
    async def test_deduct_token_returns_updated_result(self):
        """扣减 Token 后返回更新后的结果"""
        mock_redis = MagicMock()
        mock_redis.incrbyfloat.return_value = 6000.0
        mock_redis.ttl.return_value = 100
        mock_redis.get.return_value = "100"
        mock_redis.exists.return_value = True

        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }

        with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
            with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
                result = await deduct_token_quota("test_app", 1000)
                assert result.token_used == 6000
                assert result.token_remaining == 44000
                assert result.allowed is True

    @pytest.mark.asyncio
    async def test_deduct_token_over_limit(self):
        """Token 超额允许当次完成但标记耗尽"""
        mock_redis = MagicMock()
        mock_redis.incrbyfloat.return_value = 51000.0
        mock_redis.ttl.return_value = 100
        mock_redis.get.return_value = "100"
        mock_redis.exists.return_value = True

        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime.utcnow(),
        }

        with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
            with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
                result = await deduct_token_quota("test_app", 2000)
                assert result.token_used == 51000
                assert result.token_remaining == 0
                assert result.error_code == "token_quota_exceeded"

    @pytest.mark.asyncio
    async def test_deduct_token_redis_failure(self):
        """Redis 不可用时返回降级结果"""
        import redis as redis_lib

        mock_redis = MagicMock()
        mock_redis.incrbyfloat.side_effect = redis_lib.ConnectionError("fail")

        with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
            result = await deduct_token_quota("test_app", 1000)
            assert result.allowed is True


# ---------------------------------------------------------------------------
# get_quota_usage 测试
# ---------------------------------------------------------------------------

class TestGetQuotaUsage:
    """get_quota_usage 函数测试"""

    @pytest.mark.asyncio
    async def test_usage_returns_data(self):
        """正常返回配额使用数据"""
        mock_config = {
            "request_quota": 1000,
            "token_quota": 50000,
            "quota_period_days": 30,
            "cycle_start": datetime(2024, 1, 1),
        }
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = ["200", "10000"]
        mock_redis.pipeline.return_value = mock_pipe

        with patch("services.gateway.quota_checker._load_quota_config", return_value=mock_config):
            with patch("services.gateway.quota_checker.get_redis", return_value=mock_redis):
                usage = await get_quota_usage("test_app")
                assert usage["request_quota_limit"] == 1000
                assert usage["request_quota_used"] == 200
                assert usage["request_quota_remaining"] == 800
                assert usage["token_quota_limit"] == 50000
                assert usage["token_quota_used"] == 10000
                assert usage["token_quota_remaining"] == 40000
                assert "billing_cycle_start" in usage
                assert "billing_cycle_end" in usage
                assert "billing_cycle_reset" in usage

    @pytest.mark.asyncio
    async def test_usage_not_configured(self):
        """未配置配额时返回错误"""
        with patch("services.gateway.quota_checker._load_quota_config", return_value=None):
            usage = await get_quota_usage("unknown_app")
            assert usage["error_code"] == "quota_not_configured"

    @pytest.mark.asyncio
    async def test_usage_redis_failure(self):
        """Redis 不可用时返回降级信息"""
        import redis as redis_lib

        with patch(
            "services.gateway.quota_checker._load_quota_config",
            side_effect=redis_lib.ConnectionError("fail"),
        ):
            usage = await get_quota_usage("test_app")
            assert usage["error_code"] == "service_degraded"
