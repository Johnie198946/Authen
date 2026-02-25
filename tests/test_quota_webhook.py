"""
配额超限 Webhook 通知测试

测试覆盖:
- push_quota_webhook: 推送成功/失败/超时/签名
- _check_and_send_warning: 阈值触发 Webhook 推送
- _get_app_webhook_config: 查询应用 Webhook 配置
- _maybe_push_webhook: 条件推送逻辑

需求: 9.1, 9.2, 9.4
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import hmac
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from services.subscription.webhook_push import push_quota_webhook


# ---------------------------------------------------------------------------
# push_quota_webhook 测试
# ---------------------------------------------------------------------------

class TestPushQuotaWebhook:
    """测试 Webhook 推送函数"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app_id = "test-app-001"
        self.webhook_url = "https://example.com/webhook"
        self.webhook_secret = "test-secret-key"

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_success(self, mock_client_cls):
        """成功推送 Webhook 应返回 True"""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id=self.app_id,
                webhook_url=self.webhook_url,
                webhook_secret=self.webhook_secret,
                event_type="quota.warning",
                resource="request",
                current_used=85,
                limit=100,
                reset_timestamp=1700000000,
            )
        )

        assert result is True
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["headers"]["X-Event-Type"] == "quota.warning"
        assert "X-Webhook-Signature" in call_kwargs[1]["headers"]

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_without_secret(self, mock_client_cls):
        """无 webhook_secret 时不应包含签名头"""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id=self.app_id,
                webhook_url=self.webhook_url,
                webhook_secret=None,
                event_type="quota.exhausted",
                resource="token",
                current_used=1000,
                limit=1000,
                reset_timestamp=1700000000,
            )
        )

        assert result is True
        call_kwargs = mock_client.post.call_args
        assert "X-Webhook-Signature" not in call_kwargs[1]["headers"]

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_server_error(self, mock_client_cls):
        """服务端返回 5xx 应返回 False"""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id=self.app_id,
                webhook_url=self.webhook_url,
                webhook_secret=None,
                event_type="quota.warning",
                resource="request",
                current_used=85,
                limit=100,
                reset_timestamp=1700000000,
            )
        )

        assert result is False

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_connection_error(self, mock_client_cls):
        """连接失败应返回 False 且不抛异常"""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id=self.app_id,
                webhook_url=self.webhook_url,
                webhook_secret=None,
                event_type="quota.warning",
                resource="request",
                current_used=85,
                limit=100,
                reset_timestamp=1700000000,
            )
        )

        assert result is False

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_timeout(self, mock_client_cls):
        """超时应返回 False 且不抛异常"""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id=self.app_id,
                webhook_url=self.webhook_url,
                webhook_secret=None,
                event_type="quota.exhausted",
                resource="token",
                current_used=1000,
                limit=1000,
                reset_timestamp=1700000000,
            )
        )

        assert result is False

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_payload_structure(self, mock_client_cls):
        """推送的 payload 应包含正确的结构"""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id="app-123",
                webhook_url=self.webhook_url,
                webhook_secret=None,
                event_type="quota.warning",
                resource="request",
                current_used=85,
                limit=100,
                reset_timestamp=1700000000,
            )
        )

        call_kwargs = mock_client.post.call_args
        body = json.loads(call_kwargs[1]["content"])

        assert body["event_type"] == "quota.warning"
        assert "event_id" in body
        assert "timestamp" in body
        assert body["data"]["app_id"] == "app-123"
        assert body["data"]["resource"] == "request"
        assert body["data"]["current_used"] == 85
        assert body["data"]["limit"] == 100
        assert body["data"]["usage_percentage"] == 85.0
        assert body["data"]["reset_at"] == 1700000000

    @patch("services.subscription.webhook_push.httpx.AsyncClient")
    def test_push_signature_verification(self, mock_client_cls):
        """签名应可通过 HMAC-SHA256 验证"""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        secret = "my-secret"
        asyncio.get_event_loop().run_until_complete(
            push_quota_webhook(
                app_id="app-123",
                webhook_url=self.webhook_url,
                webhook_secret=secret,
                event_type="quota.exhausted",
                resource="token",
                current_used=1000,
                limit=1000,
                reset_timestamp=1700000000,
            )
        )

        call_kwargs = mock_client.post.call_args
        body_str = call_kwargs[1]["content"]
        sig_header = call_kwargs[1]["headers"]["X-Webhook-Signature"]

        # Verify signature
        assert sig_header.startswith("sha256=")
        provided_hex = sig_header[len("sha256="):]
        expected_hex = hmac.new(
            secret.encode("utf-8"),
            body_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert provided_hex == expected_hex


# ---------------------------------------------------------------------------
# _check_and_send_warning + Webhook 集成测试
# ---------------------------------------------------------------------------

class TestCheckAndSendWarningWebhook:
    """测试 _check_and_send_warning 的 Webhook 推送集成"""

    @patch("services.gateway.quota_checker._maybe_push_webhook", new_callable=AsyncMock)
    @patch("services.gateway.quota_checker.get_redis")
    def test_warning_triggers_webhook(self, mock_get_redis, mock_push):
        """80% 预警应触发 quota.warning Webhook 推送"""
        from services.gateway.quota_checker import _check_and_send_warning

        mock_redis = MagicMock()
        mock_redis.exists.return_value = False
        mock_get_redis.return_value = mock_redis
        mock_push.return_value = None

        asyncio.get_event_loop().run_until_complete(
            _check_and_send_warning(
                app_id="test-app",
                request_limit=100,
                request_used=85,
                token_limit=-1,
                token_used=0,
                ttl=86400,
                reset_timestamp=1700000000,
            )
        )

        # Should have been called with quota.warning
        assert mock_push.call_count >= 1
        calls = mock_push.call_args_list
        event_types = [c[1].get("event_type", c[0][1] if len(c[0]) > 1 else None) for c in calls]
        assert "quota.warning" in event_types

    @patch("services.gateway.quota_checker._maybe_push_webhook", new_callable=AsyncMock)
    @patch("services.gateway.quota_checker.get_redis")
    def test_exhausted_triggers_webhook(self, mock_get_redis, mock_push):
        """100% 耗尽应触发 quota.exhausted Webhook 推送"""
        from services.gateway.quota_checker import _check_and_send_warning

        mock_redis = MagicMock()
        mock_redis.exists.return_value = False
        mock_get_redis.return_value = mock_redis
        mock_push.return_value = None

        asyncio.get_event_loop().run_until_complete(
            _check_and_send_warning(
                app_id="test-app",
                request_limit=100,
                request_used=100,
                token_limit=-1,
                token_used=0,
                ttl=86400,
                reset_timestamp=1700000000,
            )
        )

        # Should have been called with quota.exhausted
        calls = mock_push.call_args_list
        event_types = [c[1].get("event_type", c[0][1] if len(c[0]) > 1 else None) for c in calls]
        assert "quota.exhausted" in event_types

    @patch("services.gateway.quota_checker._maybe_push_webhook", new_callable=AsyncMock)
    @patch("services.gateway.quota_checker.get_redis")
    def test_no_webhook_below_threshold(self, mock_get_redis, mock_push):
        """使用率低于 80% 不应触发 Webhook"""
        from services.gateway.quota_checker import _check_and_send_warning

        mock_redis = MagicMock()
        mock_redis.exists.return_value = False
        mock_get_redis.return_value = mock_redis

        asyncio.get_event_loop().run_until_complete(
            _check_and_send_warning(
                app_id="test-app",
                request_limit=100,
                request_used=50,
                token_limit=-1,
                token_used=0,
                ttl=86400,
                reset_timestamp=1700000000,
            )
        )

        mock_push.assert_not_called()

    @patch("services.gateway.quota_checker._maybe_push_webhook", new_callable=AsyncMock)
    @patch("services.gateway.quota_checker.get_redis")
    def test_no_duplicate_webhook(self, mock_get_redis, mock_push):
        """已发送过预警的不应重复触发 Webhook"""
        from services.gateway.quota_checker import _check_and_send_warning

        mock_redis = MagicMock()
        # warning_sent:80 already exists
        mock_redis.exists.return_value = True
        mock_get_redis.return_value = mock_redis

        asyncio.get_event_loop().run_until_complete(
            _check_and_send_warning(
                app_id="test-app",
                request_limit=100,
                request_used=85,
                token_limit=-1,
                token_used=0,
                ttl=86400,
                reset_timestamp=1700000000,
            )
        )

        mock_push.assert_not_called()

    @patch("services.gateway.quota_checker._maybe_push_webhook", new_callable=AsyncMock)
    @patch("services.gateway.quota_checker.get_redis")
    def test_token_warning_triggers_webhook(self, mock_get_redis, mock_push):
        """Token 配额 80% 预警也应触发 Webhook"""
        from services.gateway.quota_checker import _check_and_send_warning

        mock_redis = MagicMock()
        mock_redis.exists.return_value = False
        mock_get_redis.return_value = mock_redis
        mock_push.return_value = None

        asyncio.get_event_loop().run_until_complete(
            _check_and_send_warning(
                app_id="test-app",
                request_limit=-1,
                request_used=0,
                token_limit=10000,
                token_used=8500,
                ttl=86400,
                reset_timestamp=1700000000,
            )
        )

        assert mock_push.call_count >= 1


# ---------------------------------------------------------------------------
# _maybe_push_webhook 测试
# ---------------------------------------------------------------------------

class TestMaybePushWebhook:
    """测试条件推送逻辑"""

    @patch("services.gateway.quota_checker._get_app_webhook_config", new_callable=AsyncMock)
    @patch("services.subscription.webhook_push.push_quota_webhook", new_callable=AsyncMock)
    def test_push_when_url_configured(self, mock_push, mock_get_config):
        """应用配置了 webhook_url 时应推送"""
        from services.gateway.quota_checker import _maybe_push_webhook

        mock_get_config.return_value = {
            "webhook_url": "https://example.com/hook",
            "webhook_secret": "secret",
        }
        mock_push.return_value = True

        result = asyncio.get_event_loop().run_until_complete(
            _maybe_push_webhook(
                app_id="test-app",
                event_type="quota.warning",
                resource="request",
                used=85,
                limit=100,
                reset_timestamp=1700000000,
                cached_config=None,
            )
        )

        mock_push.assert_called_once()
        assert result is not None
        assert result["webhook_url"] == "https://example.com/hook"

    @patch("services.gateway.quota_checker._get_app_webhook_config", new_callable=AsyncMock)
    def test_no_push_when_no_url(self, mock_get_config):
        """应用未配置 webhook_url 时不应推送"""
        from services.gateway.quota_checker import _maybe_push_webhook

        mock_get_config.return_value = None

        result = asyncio.get_event_loop().run_until_complete(
            _maybe_push_webhook(
                app_id="test-app",
                event_type="quota.warning",
                resource="request",
                used=85,
                limit=100,
                reset_timestamp=1700000000,
                cached_config=None,
            )
        )

        assert result is None

    @patch("services.subscription.webhook_push.push_quota_webhook", new_callable=AsyncMock)
    def test_uses_cached_config(self, mock_push):
        """传入 cached_config 时不应重新查询数据库"""
        from services.gateway.quota_checker import _maybe_push_webhook

        cached = {
            "webhook_url": "https://cached.example.com/hook",
            "webhook_secret": None,
        }
        mock_push.return_value = True

        result = asyncio.get_event_loop().run_until_complete(
            _maybe_push_webhook(
                app_id="test-app",
                event_type="quota.exhausted",
                resource="token",
                used=1000,
                limit=1000,
                reset_timestamp=1700000000,
                cached_config=cached,
            )
        )

        mock_push.assert_called_once()
        assert result == cached

    @patch("services.gateway.quota_checker._get_app_webhook_config", new_callable=AsyncMock)
    @patch("services.subscription.webhook_push.push_quota_webhook", new_callable=AsyncMock)
    def test_push_error_non_blocking(self, mock_push, mock_get_config):
        """推送异常不应阻塞主流程"""
        from services.gateway.quota_checker import _maybe_push_webhook

        mock_get_config.return_value = {
            "webhook_url": "https://example.com/hook",
            "webhook_secret": None,
        }
        mock_push.side_effect = Exception("Unexpected error")

        # Should not raise
        result = asyncio.get_event_loop().run_until_complete(
            _maybe_push_webhook(
                app_id="test-app",
                event_type="quota.warning",
                resource="request",
                used=85,
                limit=100,
                reset_timestamp=1700000000,
                cached_config=None,
            )
        )

        # Should still return the config
        assert result is not None


# ---------------------------------------------------------------------------
# _get_app_webhook_config 测试
# ---------------------------------------------------------------------------

class TestGetAppWebhookConfig:
    """测试应用 Webhook 配置查询"""

    @patch("services.gateway.quota_checker._get_db")
    def test_returns_config_when_url_set(self, mock_get_db):
        """应用配置了 webhook_url 时应返回配置"""
        from services.gateway.quota_checker import _get_app_webhook_config

        mock_app = MagicMock()
        mock_app.webhook_url = "https://example.com/hook"
        mock_app.webhook_secret = "secret-key"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app
        mock_get_db.return_value = mock_db

        result = asyncio.get_event_loop().run_until_complete(
            _get_app_webhook_config("test-app")
        )

        assert result is not None
        assert result["webhook_url"] == "https://example.com/hook"
        assert result["webhook_secret"] == "secret-key"
        mock_db.close.assert_called_once()

    @patch("services.gateway.quota_checker._get_db")
    def test_returns_none_when_no_url(self, mock_get_db):
        """应用未配置 webhook_url 时应返回 None"""
        from services.gateway.quota_checker import _get_app_webhook_config

        mock_app = MagicMock()
        mock_app.webhook_url = None
        mock_app.webhook_secret = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app
        mock_get_db.return_value = mock_db

        result = asyncio.get_event_loop().run_until_complete(
            _get_app_webhook_config("test-app")
        )

        assert result is None
        mock_db.close.assert_called_once()

    @patch("services.gateway.quota_checker._get_db")
    def test_returns_none_when_app_not_found(self, mock_get_db):
        """应用不存在时应返回 None"""
        from services.gateway.quota_checker import _get_app_webhook_config

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = mock_db

        result = asyncio.get_event_loop().run_until_complete(
            _get_app_webhook_config("nonexistent-app")
        )

        assert result is None
        mock_db.close.assert_called_once()
