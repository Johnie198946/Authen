"""
Admin Service 登录方式配置 API 单元测试

测试 Task 6.2 中实现的 2 个登录方式配置端点：
  - GET  /api/v1/admin/applications/{app_id}/login-methods
  - PUT  /api/v1/admin/applications/{app_id}/login-methods

使用 mock DB session 避免 SQLite 不支持 PostgreSQL UUID 类型的问题。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi import Query
from datetime import datetime
import uuid

from shared.database import get_db
from shared.models.application import Application, AppLoginMethod
from shared.utils.crypto import encrypt_config, decrypt_config
from services.admin.main import app, require_super_admin


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

class InMemoryStore:
    """In-memory store for Application and AppLoginMethod."""

    def __init__(self):
        self.apps = {}            # keyed by app_id
        self.login_methods = {}   # keyed by (application_id, method)

    def reset(self):
        self.apps.clear()
        self.login_methods.clear()

    # -- Application helpers --
    def add_app(self, app_obj):
        self.apps[app_obj.app_id] = app_obj

    def delete_app(self, app_obj):
        self.apps.pop(app_obj.app_id, None)
        # Cascade delete login methods
        to_remove = [k for k in self.login_methods if k[0] == app_obj.id]
        for k in to_remove:
            del self.login_methods[k]

    def query_app_by_app_id(self, app_id):
        return self.apps.get(app_id)

    # -- LoginMethod helpers --
    def add_login_method(self, lm):
        self.login_methods[(lm.application_id, lm.method)] = lm

    def query_login_methods_by_app(self, application_id):
        return [v for k, v in self.login_methods.items() if k[0] == application_id]

    def query_login_method(self, application_id, method):
        return self.login_methods.get((application_id, method))


store = InMemoryStore()


class FakeQuery:
    """Mimics SQLAlchemy query chain for Application and AppLoginMethod."""

    def __init__(self, store_ref, model):
        self._store = store_ref
        self._model = model
        self._filters = {}

    def filter(self, *args):
        for arg in args:
            try:
                col_name = arg.left.key
                value = arg.right.effective_value
                self._filters[col_name] = value
            except Exception:
                pass
        return self

    def order_by(self, *args):
        return self

    def first(self):
        if self._model is Application:
            app_id = self._filters.get("app_id")
            if app_id:
                return self._store.query_app_by_app_id(app_id)
        elif self._model is AppLoginMethod:
            application_id = self._filters.get("application_id")
            method = self._filters.get("method")
            if application_id and method:
                return self._store.query_login_method(application_id, method)
        return None

    def all(self):
        if self._model is AppLoginMethod:
            application_id = self._filters.get("application_id")
            if application_id:
                return self._store.query_login_methods_by_app(application_id)
        if self._model is Application:
            return list(self._store.apps.values())
        return []


class FakeSession:
    """Mimics SQLAlchemy Session."""

    def __init__(self, store_ref):
        self._store = store_ref
        self._pending = []

    def query(self, model):
        return FakeQuery(self._store, model)

    def add(self, obj):
        self._pending.append(obj)

    def commit(self):
        for obj in self._pending:
            if isinstance(obj, AppLoginMethod):
                if not obj.id:
                    obj.id = uuid.uuid4()
                if not obj.created_at:
                    obj.created_at = datetime.utcnow()
                if not obj.updated_at:
                    obj.updated_at = datetime.utcnow()
                self._store.add_login_method(obj)
            elif isinstance(obj, Application):
                if not obj.id:
                    obj.id = uuid.uuid4()
                if not obj.created_at:
                    obj.created_at = datetime.utcnow()
                if not obj.updated_at:
                    obj.updated_at = datetime.utcnow()
                self._store.add_app(obj)
        self._pending.clear()

    def refresh(self, obj):
        if isinstance(obj, Application):
            if not hasattr(obj, '_persisted') or not obj._persisted:
                if not obj.id:
                    obj.id = uuid.uuid4()
                if not obj.created_at:
                    obj.created_at = datetime.utcnow()
                if not obj.updated_at:
                    obj.updated_at = datetime.utcnow()
                obj._persisted = True
                self._store.add_app(obj)

    def delete(self, obj):
        if isinstance(obj, Application):
            self._store.delete_app(obj)

    def close(self):
        pass


def override_get_db():
    session = FakeSession(store)
    try:
        yield session
    finally:
        session.close()


def override_require_super_admin(user_id: str = Query(..., description="当前用户ID")):
    return user_id


# Override dependencies
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[require_super_admin] = override_require_super_admin

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    """每个测试前清空存储"""
    store.reset()
    yield
    store.reset()


def _create_app(name="TestApp"):
    """Helper: create an application via API."""
    resp = client.post(
        "/api/v1/admin/applications?user_id=admin1",
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/v1/admin/applications/{app_id}/login-methods
# ---------------------------------------------------------------------------

class TestGetLoginMethods:
    def test_empty_list(self):
        """新应用应返回空登录方式列表"""
        created = _create_app("EmptyApp")
        resp = client.get(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_id"] == created["app_id"]
        assert data["login_methods"] == []

    def test_app_not_found(self):
        """不存在的应用应返回 404"""
        resp = client.get(
            "/api/v1/admin/applications/nonexistent/login-methods?user_id=admin1"
        )
        assert resp.status_code == 404

    def test_returns_configured_methods(self):
        """配置后应返回登录方式列表"""
        created = _create_app("MethodApp")
        # 配置 email 和 phone
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": True},
                {"method": "phone", "is_enabled": False},
            ]},
        )
        resp = client.get(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["login_methods"]) == 2
        methods_map = {m["method"]: m for m in data["login_methods"]}
        assert methods_map["email"]["is_enabled"] is True
        assert methods_map["phone"]["is_enabled"] is False

    def test_oauth_secret_masked(self):
        """OAuth 配置的 client_secret 应仅展示末尾 4 位"""
        created = _create_app("OAuthApp")
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {
                    "method": "wechat",
                    "is_enabled": True,
                    "client_id": "wx_test_id",
                    "client_secret": "wx_super_secret_key_12345678",
                },
            ]},
        )
        resp = client.get(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1"
        )
        assert resp.status_code == 200
        wechat = resp.json()["login_methods"][0]
        assert wechat["client_id"] == "wx_test_id"
        assert wechat["client_secret_masked"] == "****5678"
        # Should NOT contain the full secret
        assert "wx_super_secret_key_12345678" not in str(wechat)


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/applications/{app_id}/login-methods
# ---------------------------------------------------------------------------

class TestUpdateLoginMethods:
    def test_create_non_oauth_methods(self):
        """创建非 OAuth 登录方式（email/phone）"""
        created = _create_app("NonOAuth")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": True},
                {"method": "phone", "is_enabled": True},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["login_methods"]) == 2

    def test_create_oauth_method_with_config(self):
        """创建 OAuth 登录方式需要 client_id 和 client_secret"""
        created = _create_app("OAuthCreate")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {
                    "method": "google",
                    "is_enabled": True,
                    "client_id": "google_client_id",
                    "client_secret": "google_client_secret_abcd",
                },
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["login_methods"]) == 1
        google = data["login_methods"][0]
        assert google["method"] == "google"
        assert google["is_enabled"] is True
        assert google["client_id"] == "google_client_id"
        assert google["client_secret_masked"] == "****abcd"

    def test_oauth_enable_without_client_id_rejected(self):
        """启用 OAuth 方式但缺少 client_id 应返回 400"""
        created = _create_app("MissingClientId")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {
                    "method": "wechat",
                    "is_enabled": True,
                    "client_secret": "some_secret",
                },
            ]},
        )
        assert resp.status_code == 400

    def test_oauth_enable_without_client_secret_rejected(self):
        """启用 OAuth 方式但缺少 client_secret 应返回 400"""
        created = _create_app("MissingSecret")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {
                    "method": "alipay",
                    "is_enabled": True,
                    "client_id": "alipay_id",
                },
            ]},
        )
        assert resp.status_code == 400

    def test_oauth_disable_without_config_ok(self):
        """禁用 OAuth 方式不需要 client_id/client_secret"""
        created = _create_app("DisableOAuth")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "apple", "is_enabled": False},
            ]},
        )
        assert resp.status_code == 200

    def test_invalid_method_rejected(self):
        """不支持的登录方式应返回 400"""
        created = _create_app("InvalidMethod")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "twitter", "is_enabled": True},
            ]},
        )
        assert resp.status_code == 400

    def test_app_not_found(self):
        """更新不存在应用的登录方式应返回 404"""
        resp = client.put(
            "/api/v1/admin/applications/nonexistent/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": True},
            ]},
        )
        assert resp.status_code == 404

    def test_update_existing_method(self):
        """更新已存在的登录方式"""
        created = _create_app("UpdateExisting")
        # 先创建
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": True},
            ]},
        )
        # 再更新为禁用
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": False},
            ]},
        )
        assert resp.status_code == 200
        email = [m for m in resp.json()["login_methods"] if m["method"] == "email"][0]
        assert email["is_enabled"] is False

    def test_oauth_config_encrypted_storage(self):
        """OAuth 配置应以加密形式存储"""
        created = _create_app("EncryptedApp")
        app_id = created["app_id"]
        client.put(
            f"/api/v1/admin/applications/{app_id}/login-methods?user_id=admin1",
            json={"login_methods": [
                {
                    "method": "google",
                    "is_enabled": True,
                    "client_id": "gid_123",
                    "client_secret": "gsecret_456789",
                },
            ]},
        )
        # Verify the stored oauth_config is encrypted (not plaintext)
        app_obj = store.query_app_by_app_id(app_id)
        lm = store.query_login_method(app_obj.id, "google")
        assert lm.oauth_config is not None
        # The raw stored value should not contain plaintext secret
        assert "gsecret_456789" not in lm.oauth_config
        # But decrypting should recover the original
        decrypted = decrypt_config(lm.oauth_config)
        assert decrypted["client_id"] == "gid_123"
        assert decrypted["client_secret"] == "gsecret_456789"

    def test_multiple_methods_bulk_update(self):
        """批量更新多个登录方式"""
        created = _create_app("BulkApp")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": True},
                {"method": "phone", "is_enabled": True},
                {
                    "method": "wechat",
                    "is_enabled": True,
                    "client_id": "wx_id",
                    "client_secret": "wx_secret_1234",
                },
                {"method": "alipay", "is_enabled": False},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["login_methods"]) == 4
        methods_map = {m["method"]: m for m in data["login_methods"]}
        assert methods_map["email"]["is_enabled"] is True
        assert methods_map["phone"]["is_enabled"] is True
        assert methods_map["wechat"]["is_enabled"] is True
        assert methods_map["wechat"]["client_id"] == "wx_id"
        assert methods_map["alipay"]["is_enabled"] is False

    def test_response_fields(self):
        """响应应包含所有必要字段"""
        created = _create_app("FieldsApp")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/login-methods?user_id=admin1",
            json={"login_methods": [
                {"method": "email", "is_enabled": True},
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "app_id" in data
        assert "login_methods" in data
        lm = data["login_methods"][0]
        assert "id" in lm
        assert "method" in lm
        assert "is_enabled" in lm
        assert "created_at" in lm
        assert "updated_at" in lm
