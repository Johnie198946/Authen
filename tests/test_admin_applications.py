"""
Admin Service 应用管理 CRUD API 单元测试

测试 Task 6.1 中实现的 7 个应用管理端点。
使用 mock DB session 避免 SQLite 不支持 PostgreSQL UUID 类型的问题。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi import Query
from unittest.mock import MagicMock, patch
from datetime import datetime
import uuid

from shared.database import get_db
from shared.models.application import Application
from services.admin.main import app, require_super_admin


# ---------------------------------------------------------------------------
# In-memory application store for testing
# ---------------------------------------------------------------------------

class InMemoryAppStore:
    """Simple in-memory store that mimics SQLAlchemy query patterns."""

    def __init__(self):
        self.apps = {}  # keyed by app_id

    def reset(self):
        self.apps.clear()

    def add(self, app_obj):
        self.apps[app_obj.app_id] = app_obj

    def delete(self, app_obj):
        self.apps.pop(app_obj.app_id, None)

    def query_all(self, status_filter=None):
        results = list(self.apps.values())
        if status_filter:
            results = [a for a in results if a.status == status_filter]
        return sorted(results, key=lambda a: a.created_at, reverse=True)

    def query_by_app_id(self, app_id):
        return self.apps.get(app_id)


store = InMemoryAppStore()


class FakeQuery:
    """Mimics SQLAlchemy query chain."""

    def __init__(self, store_ref, model=None):
        self._store = store_ref
        self._filters = {}

    def filter(self, *args):
        # Capture filter conditions from SQLAlchemy BinaryExpression
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
        app_id = self._filters.get("app_id")
        if app_id:
            return self._store.query_by_app_id(app_id)
        return None

    def all(self):
        status_filter = self._filters.get("status")
        return self._store.query_all(status_filter)

    def delete(self):
        self._store.reset()


class FakeSession:
    """Mimics SQLAlchemy Session."""

    def __init__(self, store_ref):
        self._store = store_ref

    def query(self, model):
        return FakeQuery(self._store, model)

    def add(self, obj):
        pass  # Will be stored on commit

    def commit(self):
        pass

    def refresh(self, obj):
        # Simulate auto-generated fields
        if not hasattr(obj, '_persisted') or not obj._persisted:
            if not obj.id:
                obj.id = uuid.uuid4()
            if not obj.created_at:
                obj.created_at = datetime.utcnow()
            if not obj.updated_at:
                obj.updated_at = datetime.utcnow()
            obj._persisted = True
            self._store.add(obj)

    def delete(self, obj):
        self._store.delete(obj)

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


def _create_app(name="TestApp", description=None):
    """Helper: create an application via API and return response data."""
    resp = client.post(
        "/api/v1/admin/applications?user_id=admin1",
        json={"name": name, "description": description},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/v1/admin/applications - 创建应用
# ---------------------------------------------------------------------------

class TestCreateApplication:
    def test_create_success(self):
        """创建应用应返回 201 并包含 app_id 和 app_secret"""
        data = _create_app("我的应用", "测试用")
        assert data["name"] == "我的应用"
        assert data["description"] == "测试用"
        assert data["status"] == "active"
        assert data["rate_limit"] == 60
        # app_id 应为合法 UUID
        uuid.UUID(data["app_id"])
        # app_secret 至少 32 字节
        assert len(data["app_secret"]) >= 32

    def test_create_missing_name(self):
        """缺少名称应返回 422"""
        resp = client.post(
            "/api/v1/admin/applications?user_id=admin1",
            json={"description": "no name"},
        )
        assert resp.status_code == 422

    def test_create_empty_name(self):
        """空名称应返回 422"""
        resp = client.post(
            "/api/v1/admin/applications?user_id=admin1",
            json={"name": ""},
        )
        assert resp.status_code == 422

    def test_create_unique_credentials(self):
        """每次创建应生成不同的 app_id 和 app_secret"""
        d1 = _create_app("App1")
        d2 = _create_app("App2")
        assert d1["app_id"] != d2["app_id"]
        assert d1["app_secret"] != d2["app_secret"]


# ---------------------------------------------------------------------------
# GET /api/v1/admin/applications - 应用列表
# ---------------------------------------------------------------------------

class TestListApplications:
    def test_list_empty(self):
        """空列表应返回 total=0"""
        resp = client.get("/api/v1/admin/applications?user_id=admin1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["applications"] == []

    def test_list_with_data(self):
        """创建后应出现在列表中"""
        _create_app("App1")
        _create_app("App2")
        resp = client.get("/api/v1/admin/applications?user_id=admin1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_list_contains_required_fields(self):
        """列表项应包含 name, app_id, status, created_at"""
        _create_app("FieldCheck")
        resp = client.get("/api/v1/admin/applications?user_id=admin1")
        item = resp.json()["applications"][0]
        assert "name" in item
        assert "app_id" in item
        assert "status" in item
        assert "created_at" in item


# ---------------------------------------------------------------------------
# GET /api/v1/admin/applications/{app_id} - 应用详情
# ---------------------------------------------------------------------------

class TestGetApplication:
    def test_get_found(self):
        """存在的应用应返回详情"""
        created = _create_app("DetailApp")
        resp = client.get(f"/api/v1/admin/applications/{created['app_id']}?user_id=admin1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "DetailApp"
        assert resp.json()["app_id"] == created["app_id"]

    def test_get_not_found(self):
        """不存在的应用应返回 404"""
        resp = client.get("/api/v1/admin/applications/nonexistent?user_id=admin1")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/applications/{app_id} - 更新应用
# ---------------------------------------------------------------------------

class TestUpdateApplication:
    def test_update_name(self):
        """更新应用名称"""
        created = _create_app("OldName")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}?user_id=admin1",
            json={"name": "NewName"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewName"

    def test_update_rate_limit(self):
        """更新限流阈值"""
        created = _create_app("RateLimitApp")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}?user_id=admin1",
            json={"rate_limit": 120},
        )
        assert resp.status_code == 200
        assert resp.json()["rate_limit"] == 120

    def test_update_not_found(self):
        """更新不存在的应用应返回 404"""
        resp = client.put(
            "/api/v1/admin/applications/nonexistent?user_id=admin1",
            json={"name": "X"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/applications/{app_id} - 删除应用
# ---------------------------------------------------------------------------

class TestDeleteApplication:
    def test_delete_success(self):
        """删除应用应返回 204"""
        created = _create_app("ToDelete")
        resp = client.delete(f"/api/v1/admin/applications/{created['app_id']}?user_id=admin1")
        assert resp.status_code == 204
        # 确认已删除
        get_resp = client.get(f"/api/v1/admin/applications/{created['app_id']}?user_id=admin1")
        assert get_resp.status_code == 404

    def test_delete_not_found(self):
        """删除不存在的应用应返回 404"""
        resp = client.delete("/api/v1/admin/applications/nonexistent?user_id=admin1")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/admin/applications/{app_id}/reset-secret - 重置密钥
# ---------------------------------------------------------------------------

class TestResetSecret:
    def test_reset_secret_success(self):
        """重置密钥应返回新的 app_secret"""
        created = _create_app("SecretApp")
        old_secret = created["app_secret"]

        resp = client.post(
            f"/api/v1/admin/applications/{created['app_id']}/reset-secret?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_id"] == created["app_id"]
        assert len(data["app_secret"]) >= 32
        assert data["app_secret"] != old_secret
        assert "message" in data

    def test_reset_secret_not_found(self):
        """重置不存在应用的密钥应返回 404"""
        resp = client.post("/api/v1/admin/applications/nonexistent/reset-secret?user_id=admin1")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/applications/{app_id}/status - 启用/禁用应用
# ---------------------------------------------------------------------------

class TestUpdateApplicationStatus:
    def test_disable(self):
        """禁用应用"""
        created = _create_app("StatusApp")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/status?user_id=admin1",
            json={"status": "disabled"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_enable(self):
        """启用应用"""
        created = _create_app("StatusApp2")
        # 先禁用
        client.put(
            f"/api/v1/admin/applications/{created['app_id']}/status?user_id=admin1",
            json={"status": "disabled"},
        )
        # 再启用
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/status?user_id=admin1",
            json={"status": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_invalid_status(self):
        """无效的状态值应返回 400"""
        created = _create_app("InvalidStatusApp")
        resp = client.put(
            f"/api/v1/admin/applications/{created['app_id']}/status?user_id=admin1",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 400

    def test_status_not_found(self):
        """更新不存在应用的状态应返回 404"""
        resp = client.put(
            "/api/v1/admin/applications/nonexistent/status?user_id=admin1",
            json={"status": "disabled"},
        )
        assert resp.status_code == 404
