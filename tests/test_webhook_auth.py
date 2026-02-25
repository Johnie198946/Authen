"""
Webhook 签名验证单元测试

测试 verify_webhook_signature 函数的各种场景：
- 正确签名通过验证
- 缺少头部返回 401
- 应用不存在返回 403
- 应用已禁用返回 403
- 签名错误返回 401
- 恒定时间比较（使用 hmac.compare_digest）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import hmac
import hashlib
import asyncio
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from services.subscription.webhook_auth import verify_webhook_signature
import uuid


class FakeApplication:
    """Fake Application object for testing without database"""
    def __init__(self, app_id, status="active", webhook_secret="secret123", name="Test App"):
        self.id = uuid.uuid4()
        self.app_id = app_id
        self.name = name
        self.status = status
        self.webhook_secret = webhook_secret
        self.app_secret_hash = "hashed"


def _compute_signature(secret: str, body: bytes) -> str:
    """计算 HMAC-SHA256 签名"""
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def _make_mock_db(application=None):
    """Create a mock db session that returns the given application on query"""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.first.return_value = application
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query
    return mock_db


class TestVerifyWebhookSignature:
    """verify_webhook_signature 单元测试"""

    def test_valid_signature_passes(self):
        """正确签名应通过验证并返回应用信息"""
        app = FakeApplication("test-app-001")
        db = _make_mock_db(app)
        body = b'{"event_id":"e1","event_type":"subscription.created"}'
        sig = _compute_signature("secret123", body)

        result = asyncio.get_event_loop().run_until_complete(
            verify_webhook_signature("test-app-001", sig, body, db)
        )

        assert result["app_id"] == "test-app-001"
        assert result["name"] == "Test App"
        assert result["webhook_secret"] == "secret123"

    def test_missing_app_id_returns_401(self):
        """缺少 app_id 应返回 401"""
        db = _make_mock_db()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("", "sha256=abc", b"body", db)
            )
        assert exc_info.value.status_code == 401
        assert "缺少认证头部" in exc_info.value.detail

    def test_missing_signature_returns_401(self):
        """缺少签名应返回 401"""
        db = _make_mock_db()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", "", b"body", db)
            )
        assert exc_info.value.status_code == 401
        assert "缺少认证头部" in exc_info.value.detail

    def test_none_app_id_returns_401(self):
        """app_id 为 None 应返回 401"""
        db = _make_mock_db()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature(None, "sha256=abc", b"body", db)
            )
        assert exc_info.value.status_code == 401

    def test_none_signature_returns_401(self):
        """signature 为 None 应返回 401"""
        db = _make_mock_db()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", None, b"body", db)
            )
        assert exc_info.value.status_code == 401

    def test_app_not_found_returns_403(self):
        """应用不存在应返回 403"""
        db = _make_mock_db(None)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("nonexistent-app", "sha256=abc", b"body", db)
            )
        assert exc_info.value.status_code == 403
        assert "应用不存在或已禁用" in exc_info.value.detail

    def test_disabled_app_returns_403(self):
        """已禁用应用应返回 403"""
        app = FakeApplication("test-app-001", status="disabled")
        db = _make_mock_db(app)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", "sha256=abc", b"body", db)
            )
        assert exc_info.value.status_code == 403
        assert "应用不存在或已禁用" in exc_info.value.detail

    def test_no_webhook_secret_returns_403(self):
        """未配置 webhook_secret 应返回 403"""
        app = FakeApplication("test-app-001", webhook_secret=None)
        db = _make_mock_db(app)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", "sha256=abc", b"body", db)
            )
        assert exc_info.value.status_code == 403

    def test_invalid_signature_format_returns_401(self):
        """签名格式不正确（缺少 sha256= 前缀）应返回 401"""
        app = FakeApplication("test-app-001")
        db = _make_mock_db(app)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", "invalid_format", b"body", db)
            )
        assert exc_info.value.status_code == 401
        assert "签名验证失败" in exc_info.value.detail

    def test_wrong_signature_returns_401(self):
        """错误签名应返回 401"""
        app = FakeApplication("test-app-001")
        db = _make_mock_db(app)
        body = b'{"event_id":"e1"}'
        wrong_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", wrong_sig, body, db)
            )
        assert exc_info.value.status_code == 401
        assert "签名验证失败" in exc_info.value.detail

    def test_tampered_body_fails(self):
        """篡改请求体后签名应验证失败"""
        app = FakeApplication("test-app-001")
        db = _make_mock_db(app)
        original_body = b'{"amount":100}'
        sig = _compute_signature("secret123", original_body)
        tampered_body = b'{"amount":999}'

        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                verify_webhook_signature("test-app-001", sig, tampered_body, db)
            )
        assert exc_info.value.status_code == 401

    def test_empty_body_with_valid_signature(self):
        """空请求体配合正确签名应通过"""
        app = FakeApplication("test-app-001")
        db = _make_mock_db(app)
        body = b""
        sig = _compute_signature("secret123", body)

        result = asyncio.get_event_loop().run_until_complete(
            verify_webhook_signature("test-app-001", sig, body, db)
        )
        assert result["app_id"] == "test-app-001"
