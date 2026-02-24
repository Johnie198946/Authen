"""
Redis 缓存管理模块单元测试

测试 services/gateway/cache.py 中的缓存读写和失效逻辑：
- get_app_methods: 登录方式缓存读写
- get_app_scopes: 权限范围缓存读写
- get_app_oauth_config: OAuth 配置缓存读写
- invalidate_app_cache: 全量缓存失效
- invalidate_app_methods_cache: 登录方式缓存失效
- invalidate_app_scopes_cache: 权限范围缓存失效
- invalidate_app_oauth_cache: OAuth 配置缓存失效
- invalidate_app_config_cache: 基本信息缓存失效
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.cache import (
    get_app_methods,
    get_app_scopes,
    get_app_oauth_config,
    invalidate_app_cache,
    invalidate_app_methods_cache,
    invalidate_app_scopes_cache,
    invalidate_app_oauth_cache,
    invalidate_app_config_cache,
    APP_CACHE_PREFIX,
    APP_CACHE_TTL,
)


# ==================== Fixtures ====================

@pytest.fixture
def app_id():
    return str(uuid.uuid4())


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def mock_app():
    """模拟 Application ORM 对象"""
    app = MagicMock()
    app.id = uuid.uuid4()
    app.app_id = str(uuid.uuid4())
    return app


# ==================== get_app_methods ====================

class TestGetAppMethods:
    """登录方式缓存读写测试"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_methods(self, app_id, mock_redis):
        """缓存命中时直接返回，不查询数据库"""
        mock_redis.smembers.return_value = {"email", "phone"}

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db") as mock_get_db:
                result = await get_app_methods(app_id)

                assert result == {"email", "phone"}
                mock_redis.smembers.assert_called_once_with(f"{APP_CACHE_PREFIX}{app_id}:methods")
                mock_get_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_caches(self, app_id, mock_redis):
        """缓存未命中时查询数据库并写入缓存"""
        mock_redis.smembers.return_value = set()

        mock_method_email = MagicMock()
        mock_method_email.method = "email"
        mock_method_phone = MagicMock()
        mock_method_phone.method = "phone"

        mock_app_obj = MagicMock()
        mock_app_obj.id = uuid.uuid4()

        mock_db = MagicMock()
        # First query: Application lookup
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app_obj
        # Second query: AppLoginMethod lookup - need to handle chained filter
        mock_query_chain = MagicMock()
        mock_query_chain.filter.return_value.all.return_value = [mock_method_email, mock_method_phone]

        # Make query() return different mocks based on call count
        call_count = [0]
        original_query = mock_db.query

        def side_effect_query(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_query.return_value
            return mock_query_chain

        mock_db.query.side_effect = side_effect_query

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db", return_value=mock_db):
                result = await get_app_methods(app_id)

                assert result == {"email", "phone"}
                mock_redis.sadd.assert_called_once()
                mock_redis.expire.assert_called_once_with(
                    f"{APP_CACHE_PREFIX}{app_id}:methods", APP_CACHE_TTL
                )
                mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_not_found_returns_empty_set(self, app_id, mock_redis):
        """应用不存在时返回空集合"""
        mock_redis.smembers.return_value = set()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db", return_value=mock_db):
                result = await get_app_methods(app_id)

                assert result == set()
                mock_redis.sadd.assert_not_called()
                mock_db.close.assert_called_once()


# ==================== get_app_scopes ====================

class TestGetAppScopes:
    """权限范围缓存读写测试"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_scopes(self, app_id, mock_redis):
        """缓存命中时直接返回"""
        mock_redis.smembers.return_value = {"user:read", "auth:login"}

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db") as mock_get_db:
                result = await get_app_scopes(app_id)

                assert result == {"user:read", "auth:login"}
                mock_redis.smembers.assert_called_once_with(f"{APP_CACHE_PREFIX}{app_id}:scopes")
                mock_get_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_caches(self, app_id, mock_redis):
        """缓存未命中时查询数据库并写入缓存"""
        mock_redis.smembers.return_value = set()

        mock_scope1 = MagicMock()
        mock_scope1.scope = "user:read"
        mock_scope2 = MagicMock()
        mock_scope2.scope = "auth:login"

        mock_app_obj = MagicMock()
        mock_app_obj.id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app_obj

        mock_query_chain = MagicMock()
        mock_query_chain.filter.return_value.all.return_value = [mock_scope1, mock_scope2]

        call_count = [0]
        original_query = mock_db.query

        def side_effect_query(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_query.return_value
            return mock_query_chain

        mock_db.query.side_effect = side_effect_query

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db", return_value=mock_db):
                result = await get_app_scopes(app_id)

                assert result == {"user:read", "auth:login"}
                mock_redis.sadd.assert_called_once()
                mock_redis.expire.assert_called_once_with(
                    f"{APP_CACHE_PREFIX}{app_id}:scopes", APP_CACHE_TTL
                )
                mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_not_found_returns_empty_set(self, app_id, mock_redis):
        """应用不存在时返回空集合"""
        mock_redis.smembers.return_value = set()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db", return_value=mock_db):
                result = await get_app_scopes(app_id)

                assert result == set()
                mock_redis.sadd.assert_not_called()
                mock_db.close.assert_called_once()


# ==================== get_app_oauth_config ====================

class TestGetAppOauthConfig:
    """OAuth 配置缓存读写测试"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_decrypted_config(self, app_id, mock_redis):
        """缓存命中时解密并返回"""
        mock_redis.hgetall.return_value = {"encrypted_config": "encrypted-data"}

        decrypted = {"client_id": "test-id", "client_secret": "test-secret"}

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("shared.utils.crypto.decrypt_config", return_value=decrypted):
                with patch("services.gateway.cache._get_db") as mock_get_db:
                    result = await get_app_oauth_config(app_id, "google")

                    assert result == decrypted
                    mock_redis.hgetall.assert_called_once_with(
                        f"{APP_CACHE_PREFIX}{app_id}:oauth:google"
                    )
                    mock_get_db.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_caches(self, app_id, mock_redis):
        """缓存未命中时查询数据库并写入缓存"""
        mock_redis.hgetall.return_value = {}

        mock_app_obj = MagicMock()
        mock_app_obj.id = uuid.uuid4()

        mock_login_method = MagicMock()
        mock_login_method.oauth_config = "encrypted-db-data"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app_obj

        mock_query_chain = MagicMock()
        mock_query_chain.filter.return_value.first.return_value = mock_login_method

        call_count = [0]
        original_query = mock_db.query

        def side_effect_query(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_query.return_value
            return mock_query_chain

        mock_db.query.side_effect = side_effect_query

        decrypted = {"client_id": "db-id", "client_secret": "db-secret"}

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("shared.utils.crypto.decrypt_config", return_value=decrypted):
                with patch("services.gateway.cache._get_db", return_value=mock_db):
                    result = await get_app_oauth_config(app_id, "wechat")

                    assert result == decrypted
                    mock_redis.hset.assert_called_once_with(
                        f"{APP_CACHE_PREFIX}{app_id}:oauth:wechat",
                        "encrypted_config",
                        "encrypted-db-data",
                    )
                    mock_redis.expire.assert_called_once_with(
                        f"{APP_CACHE_PREFIX}{app_id}:oauth:wechat", APP_CACHE_TTL
                    )
                    mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_oauth_config_returns_none(self, app_id, mock_redis):
        """未配置 OAuth 时返回 None"""
        mock_redis.hgetall.return_value = {}

        mock_app_obj = MagicMock()
        mock_app_obj.id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app_obj

        mock_query_chain = MagicMock()
        mock_query_chain.filter.return_value.first.return_value = None

        call_count = [0]
        original_query = mock_db.query

        def side_effect_query(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_query.return_value
            return mock_query_chain

        mock_db.query.side_effect = side_effect_query

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("services.gateway.cache._get_db", return_value=mock_db):
                result = await get_app_oauth_config(app_id, "apple")

                assert result is None
                mock_redis.hset.assert_not_called()
                mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_corrupted_cache_falls_back_to_db(self, app_id, mock_redis):
        """缓存数据损坏时删除缓存并回退到数据库"""
        mock_redis.hgetall.return_value = {"encrypted_config": "corrupted-data"}

        mock_app_obj = MagicMock()
        mock_app_obj.id = uuid.uuid4()

        mock_login_method = MagicMock()
        mock_login_method.oauth_config = "valid-encrypted-data"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app_obj

        mock_query_chain = MagicMock()
        mock_query_chain.filter.return_value.first.return_value = mock_login_method

        call_count = [0]
        original_query = mock_db.query

        def side_effect_query(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_query.return_value
            return mock_query_chain

        mock_db.query.side_effect = side_effect_query

        decrypted = {"client_id": "id", "client_secret": "secret"}
        decrypt_call_count = [0]

        def mock_decrypt(data):
            decrypt_call_count[0] += 1
            if decrypt_call_count[0] == 1:
                raise ValueError("解密失败")
            return decrypted

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            with patch("shared.utils.crypto.decrypt_config", side_effect=mock_decrypt):
                with patch("services.gateway.cache._get_db", return_value=mock_db):
                    result = await get_app_oauth_config(app_id, "google")

                    assert result == decrypted
                    # 损坏的缓存应被删除
                    mock_redis.delete.assert_called_once_with(
                        f"{APP_CACHE_PREFIX}{app_id}:oauth:google"
                    )
                    mock_db.close.assert_called_once()


# ==================== 缓存失效 ====================

class TestInvalidateAppCache:
    """全量缓存失效测试"""

    def test_deletes_all_matching_keys(self, app_id, mock_redis):
        """应删除所有 app:{app_id}* 模式的 key"""
        keys_batch1 = [
            f"app:{app_id}",
            f"app:{app_id}:methods",
            f"app:{app_id}:scopes",
        ]
        keys_batch2 = [f"app:{app_id}:oauth:google"]

        mock_redis.scan.side_effect = [
            (42, keys_batch1),
            (0, keys_batch2),
        ]
        mock_redis.delete.return_value = 3

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_cache(app_id)

            assert mock_redis.scan.call_count == 2
            assert mock_redis.delete.call_count == 2

    def test_no_keys_to_delete(self, app_id, mock_redis):
        """没有匹配的 key 时返回 0"""
        mock_redis.scan.return_value = (0, [])

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_cache(app_id)

            assert result == 0
            mock_redis.delete.assert_not_called()


class TestInvalidateSpecificCache:
    """特定缓存失效测试"""

    def test_invalidate_methods_cache(self, app_id, mock_redis):
        """删除登录方式缓存"""
        mock_redis.delete.return_value = 1

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_methods_cache(app_id)

            assert result is True
            mock_redis.delete.assert_called_once_with(f"{APP_CACHE_PREFIX}{app_id}:methods")

    def test_invalidate_scopes_cache(self, app_id, mock_redis):
        """删除权限范围缓存"""
        mock_redis.delete.return_value = 1

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_scopes_cache(app_id)

            assert result is True
            mock_redis.delete.assert_called_once_with(f"{APP_CACHE_PREFIX}{app_id}:scopes")

    def test_invalidate_oauth_cache(self, app_id, mock_redis):
        """删除 OAuth 配置缓存"""
        mock_redis.delete.return_value = 1

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_oauth_cache(app_id, "google")

            assert result is True
            mock_redis.delete.assert_called_once_with(
                f"{APP_CACHE_PREFIX}{app_id}:oauth:google"
            )

    def test_invalidate_config_cache(self, app_id, mock_redis):
        """删除基本信息缓存"""
        mock_redis.delete.return_value = 1

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_config_cache(app_id)

            assert result == 1
            mock_redis.delete.assert_called_once_with(f"{APP_CACHE_PREFIX}{app_id}")

    def test_invalidate_nonexistent_key_returns_false(self, app_id, mock_redis):
        """删除不存在的 key 返回 False"""
        mock_redis.delete.return_value = 0

        with patch("services.gateway.cache.get_redis", return_value=mock_redis):
            result = invalidate_app_methods_cache(app_id)
            assert result is False
