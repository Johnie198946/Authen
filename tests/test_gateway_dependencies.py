"""
应用凭证验证模块单元测试

测试 services/gateway/dependencies.py 中的核心验证逻辑：
- verify_app_credential: 凭证验证（401/403 行为）
- get_app_from_cache_or_db: 缓存优先加载
- get_app_credential_from_request: 从请求头提取凭证
"""
import json
import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.utils.crypto import hash_password, verify_password
from services.gateway.dependencies import (
    verify_app_credential,
    get_app_from_cache_or_db,
    get_app_credential_from_request,
    APP_CACHE_PREFIX,
    APP_CACHE_TTL,
)


# ==================== Fixtures ====================

@pytest.fixture
def sample_app_secret():
    return "test-secret-at-least-32-bytes-long!!"


@pytest.fixture
def sample_app_data(sample_app_secret):
    return {
        "id": str(uuid.uuid4()),
        "name": "Test App",
        "app_id": str(uuid.uuid4()),
        "app_secret_hash": hash_password(sample_app_secret),
        "status": "active",
        "rate_limit": 60,
    }


@pytest.fixture
def disabled_app_data(sample_app_secret):
    return {
        "id": str(uuid.uuid4()),
        "name": "Disabled App",
        "app_id": str(uuid.uuid4()),
        "app_secret_hash": hash_password(sample_app_secret),
        "status": "disabled",
        "rate_limit": 60,
    }


# ==================== verify_app_credential ====================

class TestVerifyAppCredential:
    """verify_app_credential 函数测试"""

    @pytest.mark.asyncio
    async def test_valid_credential_returns_app_data(self, sample_app_data, sample_app_secret):
        """有效凭证应返回应用配置"""
        with patch(
            "services.gateway.dependencies.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=sample_app_data,
        ):
            result = await verify_app_credential(
                sample_app_data["app_id"], sample_app_secret
            )
            assert result["app_id"] == sample_app_data["app_id"]
            assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_nonexistent_app_id_returns_401(self):
        """app_id 不存在应返回 401"""
        with patch(
            "services.gateway.dependencies.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_app_credential("nonexistent-id", "any-secret")
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "凭证无效"

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self, sample_app_data):
        """app_secret 错误应返回 401"""
        with patch(
            "services.gateway.dependencies.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=sample_app_data,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_app_credential(sample_app_data["app_id"], "wrong-secret")
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "凭证无效"

    @pytest.mark.asyncio
    async def test_disabled_app_returns_403(self, disabled_app_data, sample_app_secret):
        """禁用的应用应返回 403"""
        with patch(
            "services.gateway.dependencies.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=disabled_app_data,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_app_credential(
                    disabled_app_data["app_id"], sample_app_secret
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "应用已被禁用"

    @pytest.mark.asyncio
    async def test_401_does_not_distinguish_failure_reason(self, sample_app_data):
        """401 错误不应区分 app_id 不存在和 app_secret 错误"""
        # Case 1: app_id 不存在
        with patch(
            "services.gateway.dependencies.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc1:
                await verify_app_credential("nonexistent", "any")

        # Case 2: app_secret 错误
        with patch(
            "services.gateway.dependencies.get_app_from_cache_or_db",
            new_callable=AsyncMock,
            return_value=sample_app_data,
        ):
            with pytest.raises(HTTPException) as exc2:
                await verify_app_credential(sample_app_data["app_id"], "wrong")

        # 两种情况应返回完全相同的错误
        assert exc1.value.status_code == exc2.value.status_code == 401
        assert exc1.value.detail == exc2.value.detail == "凭证无效"


# ==================== get_app_from_cache_or_db ====================

class TestGetAppFromCacheOrDb:
    """get_app_from_cache_or_db 函数测试"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self, sample_app_data):
        """缓存命中时应直接返回缓存数据，不查询数据库"""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(sample_app_data)

        with patch("services.gateway.dependencies.get_redis", return_value=mock_redis):
            with patch("services.gateway.dependencies._get_db") as mock_get_db:
                result = await get_app_from_cache_or_db(sample_app_data["app_id"])

                assert result == sample_app_data
                mock_redis.get.assert_called_once_with(
                    f"{APP_CACHE_PREFIX}{sample_app_data['app_id']}"
                )
                mock_get_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_caches(self, sample_app_data):
        """缓存未命中时应查询数据库并写入缓存"""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        mock_app = MagicMock()
        mock_app.id = uuid.UUID(sample_app_data["id"])
        mock_app.name = sample_app_data["name"]
        mock_app.app_id = sample_app_data["app_id"]
        mock_app.app_secret_hash = sample_app_data["app_secret_hash"]
        mock_app.status = sample_app_data["status"]
        mock_app.rate_limit = sample_app_data["rate_limit"]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app

        with patch("services.gateway.dependencies.get_redis", return_value=mock_redis):
            with patch("services.gateway.dependencies._get_db", return_value=mock_db):
                result = await get_app_from_cache_or_db(sample_app_data["app_id"])

                assert result["app_id"] == sample_app_data["app_id"]
                assert result["status"] == "active"
                mock_redis.setex.assert_called_once()
                call_args = mock_redis.setex.call_args
                assert call_args[0][0] == f"{APP_CACHE_PREFIX}{sample_app_data['app_id']}"
                assert call_args[0][1] == APP_CACHE_TTL
                mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_not_found_returns_none(self):
        """应用不存在时应返回 None"""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("services.gateway.dependencies.get_redis", return_value=mock_redis):
            with patch("services.gateway.dependencies._get_db", return_value=mock_db):
                result = await get_app_from_cache_or_db("nonexistent-id")

                assert result is None
                mock_redis.setex.assert_not_called()
                mock_db.close.assert_called_once()


# ==================== get_app_credential_from_request ====================

class TestGetAppCredentialFromRequest:
    """get_app_credential_from_request 函数测试"""

    @pytest.mark.asyncio
    async def test_valid_headers_returns_app_data(self, sample_app_data, sample_app_secret):
        """有效的请求头应返回应用配置并注入 request.state"""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda key: {
            "X-App-Id": sample_app_data["app_id"],
            "X-App-Secret": sample_app_secret,
        }.get(key)
        mock_request.state = MagicMock()

        with patch(
            "services.gateway.dependencies.verify_app_credential",
            new_callable=AsyncMock,
            return_value=sample_app_data,
        ):
            result = await get_app_credential_from_request(mock_request)
            assert result == sample_app_data
            assert mock_request.state.app == sample_app_data

    @pytest.mark.asyncio
    async def test_missing_app_id_returns_401(self):
        """缺少 X-App-Id 应返回 401"""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda key: {
            "X-App-Id": None,
            "X-App-Secret": "some-secret",
        }.get(key)

        with pytest.raises(HTTPException) as exc_info:
            await get_app_credential_from_request(mock_request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "凭证无效"

    @pytest.mark.asyncio
    async def test_missing_app_secret_returns_401(self):
        """缺少 X-App-Secret 应返回 401"""
        mock_request = MagicMock()
        mock_request.headers.get.side_effect = lambda key: {
            "X-App-Id": "some-id",
            "X-App-Secret": None,
        }.get(key)

        with pytest.raises(HTTPException) as exc_info:
            await get_app_credential_from_request(mock_request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "凭证无效"

    @pytest.mark.asyncio
    async def test_missing_both_headers_returns_401(self):
        """两个请求头都缺少应返回 401"""
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_app_credential_from_request(mock_request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "凭证无效"
