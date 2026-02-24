"""
Admin Service Scope 配置 API 单元测试

测试 Task 6.5 中实现的 2 个 Scope 配置端点：
  - GET  /api/v1/admin/applications/{app_id}/scopes
  - PUT  /api/v1/admin/applications/{app_id}/scopes

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
from shared.models.application import Application, AppLoginMethod, AppScope
from services.admin.main import app, require_super_admin


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

class InMemoryStore:
    """In-memory store for Application and AppScope."""

    def __init__(self):
        self.apps = {}            # keyed by app_id
        self.login_methods = {}   # keyed by (application_id, method)
        self.scopes = {}          # keyed by (application_id, scope)

    def reset(self):
        self.apps.clear()
        self.login_methods.clear()
        self.scopes.clear()

    # -- Application helpers --
    def add_app(self, app_obj):
        self.apps[app_obj.app_id] = app_obj

    def delete_app(self, app_obj):
        self.apps.pop(app_obj.app_id, None)
        to_remove = [k for k in self.login_methods if k[0] == app_obj.id]
        for k in to_remove:
            del self.login_methods[k]
        to_remove = [k for k in self.scopes if k[0] == app_obj.id]
        for k in to_remove:
            del self.scopes[k]

    def query_app_by_app_id(self, app_id):
        return self.apps.get(app_id)

    # -- LoginMethod helpers --
    def add_login_method(self, lm):
        self.login_methods[(lm.application_id, lm.method)] = lm

    def query_login_methods_by_app(self, application_id):
        return [v for k, v in self.login_methods.items() if k[0] == application_id]

    def query_login_method(self, application_id, method):
        return self.login_methods.get((application_id, method))

    # -- Scope helpers --
    def add_scope(self, scope_obj):
        self.scopes[(scope_obj.application_id, scope_obj.scope)] = scope_obj

    def query_scopes_by_app(self, application_id):
        return [v for k, v in self.scopes.items() if k[0] == application_id]

    def delete_scopes_by_app(self, application_id):
        to_remove = [k for k in self.scopes if k[0] == application_id]
        count = len(to_remove)
        for k in to_remove:
            del self.scopes[k]
        return count


store = InMemoryStore()


class FakeQuery:
    """Mimics SQLAlchemy query chain for Application, AppLoginMethod, and AppScope."""

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
        if self._model is AppScope:
            application_id = self._filters.get("application_id")
            if application_id:
                return self._store.query_scopes_by_app(application_id)
        if self._model is AppLoginMethod:
            application_id = self._filters.get("application_id")
            if application_id:
                return self._store.query_login_methods_by_app(application_id)
        if self._model is Application:
            return list(self._store.apps.values())
        return []

    def delete(self, synchronize_session=None):
        if self._model is AppScope:
            application_id = self._filters.get("application_id")
            if application_id:
                return self._store.delete_scopes_by_app(application_id)
        return 0


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
            if isinstance(obj, AppScope):
                if not obj.id:
                    obj.id = uuid.uuid4()
                if not obj.created_at:
                    obj.created_at = datetime.utcnow()
                self._store.add_scope(obj)
            elif isinstance(obj, AppLoginMethod):
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
# GET /api/v1/admin/applications/{app_id}/scopes
# ---------------------------------------------------------------------------

class TestGetScopes:
    def test_empty_list(self):
        """新应用应返回空 Scope 列表"""
        created = _create_app("EmptyApp")
        resp = client.get(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_id"] == created["app_id"]
        assert data["scopes"] == []

    def test_app_not_found(self):
        """不存在的应用应返回 404"""
        resp = client.get(
            "/api/v1/admin/applications/nonexistent/scopes?user_id=admin1"
        )
        assert resp.status_code == 404

    def test_returns_configured_scopes(self):
        """配置后应返回 Scope 列表"""
        created = _create_app("ScopeApp")
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read", "auth:login"]},
        )
        resp = client.get(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scopes"]) == 2
        scope_names = {s["scope"] for s in data["scopes"]}
        assert scope_names == {"user:read", "auth:login"}


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/applications/{app_id}/scopes
# ---------------------------------------------------------------------------

class TestUpdateScopes:
    def test_set_scopes(self):
        """设置 Scope 列表"""
        created = _create_app("SetScopes")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read", "user:write", "auth:login"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scopes"]) == 3
        scope_names = {s["scope"] for s in data["scopes"]}
        assert scope_names == {"user:read", "user:write", "auth:login"}

    def test_replace_scopes(self):
        """更新应完全替换旧的 Scope"""
        created = _create_app("ReplaceScopes")
        # 先设置
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read", "auth:login"]},
        )
        # 再替换
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["role:read", "org:write"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scopes"]) == 2
        scope_names = {s["scope"] for s in data["scopes"]}
        assert scope_names == {"role:read", "org:write"}

    def test_clear_scopes(self):
        """传空列表应清除所有 Scope"""
        created = _create_app("ClearScopes")
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read"]},
        )
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": []},
        )
        assert resp.status_code == 200
        assert resp.json()["scopes"] == []

    def test_invalid_scope_rejected(self):
        """无效的 Scope 值应返回 400"""
        created = _create_app("InvalidScope")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read", "invalid:scope"]},
        )
        assert resp.status_code == 400
        assert "invalid:scope" in resp.json()["detail"]

    def test_app_not_found(self):
        """更新不存在应用的 Scope 应返回 404"""
        resp = client.put(
            "/api/v1/admin/applications/nonexistent/scopes?user_id=admin1",
            json={"scopes": ["user:read"]},
        )
        assert resp.status_code == 404

    def test_duplicate_scopes_deduplicated(self):
        """重复的 Scope 应被去重"""
        created = _create_app("DuplicateScopes")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read", "user:read", "auth:login"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scopes"]) == 2
        scope_names = {s["scope"] for s in data["scopes"]}
        assert scope_names == {"user:read", "auth:login"}

    def test_all_valid_scopes(self):
        """所有有效 Scope 都应被接受"""
        created = _create_app("AllScopes")
        all_scopes = [
            "user:read", "user:write",
            "auth:login", "auth:register",
            "role:read", "role:write",
            "org:read", "org:write",
        ]
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": all_scopes},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scopes"]) == 8

    def test_response_fields(self):
        """响应应包含所有必要字段"""
        created = _create_app("FieldsApp")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/scopes?user_id=admin1",
            json={"scopes": ["user:read"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "app_id" in data
        assert "scopes" in data
        scope = data["scopes"][0]
        assert "id" in scope
        assert "scope" in scope
        assert "created_at" in scope
