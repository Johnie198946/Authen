"""
Admin Service 自动配置规则 API 单元测试

测试 GET/PUT/DELETE /api/v1/admin/applications/{app_id}/auto-provision 端点。
使用 mock DB session 避免 SQLite 不支持 PostgreSQL UUID 类型的问题。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from fastapi import Query, HTTPException
from unittest.mock import MagicMock
from datetime import datetime
import uuid

from shared.database import get_db
from shared.models.application import Application, AutoProvisionConfig
from shared.models.permission import Role, Permission
from shared.models.organization import Organization
from shared.models.subscription import SubscriptionPlan
from services.admin.main import app, require_super_admin


# ---------------------------------------------------------------------------
# In-memory stores for testing
# ---------------------------------------------------------------------------

class Store:
    """In-memory store for all model types."""

    def __init__(self):
        self.apps = {}           # keyed by app_id
        self.configs = {}        # keyed by application.id (UUID)
        self.roles = {}          # keyed by role.id (UUID)
        self.permissions = {}    # keyed by permission.id (UUID)
        self.organizations = {}  # keyed by org.id (UUID)
        self.plans = {}          # keyed by plan.id (UUID)

    def reset(self):
        self.apps.clear()
        self.configs.clear()
        self.roles.clear()
        self.permissions.clear()
        self.organizations.clear()
        self.plans.clear()


store = Store()


class FakeQuery:
    """Mimics SQLAlchemy query chain for multiple model types."""

    def __init__(self, model, store_ref):
        self._model = model
        self._store = store_ref
        self._filters = {}
        self._filter_in = {}  # for .in_() filters

    def filter(self, *args):
        for arg in args:
            try:
                col_name = arg.left.key
                # Handle .in_() operator - check for 'in_op' specifically
                op_name = getattr(arg.operator, '__name__', '') if hasattr(arg, 'operator') else ''
                if op_name == 'in_op':
                    value = arg.right.effective_value if hasattr(arg.right, 'effective_value') else arg.right.value
                    self._filter_in[col_name] = value
                else:
                    value = arg.right.effective_value if hasattr(arg.right, 'effective_value') else arg.right.value
                    self._filters[col_name] = value
            except Exception:
                pass
        return self

    def order_by(self, *args):
        return self

    def first(self):
        if self._model == Application:
            app_id = self._filters.get("app_id")
            if app_id:
                return self._store.apps.get(app_id)
            return None
        elif self._model == AutoProvisionConfig:
            app_uuid = self._filters.get("application_id")
            if app_uuid:
                return self._store.configs.get(app_uuid)
            return None
        elif self._model == Organization:
            org_id = self._filters.get("id")
            if org_id:
                return self._store.organizations.get(org_id)
            return None
        elif self._model == SubscriptionPlan:
            plan_id = self._filters.get("id")
            if plan_id:
                return self._store.plans.get(plan_id)
            return None
        return None

    def all(self):
        if self._model == Role or (hasattr(self._model, 'key') and self._model.key == 'id' and 'id' in self._filter_in):
            # Handle Role.id.in_() query
            ids = self._filter_in.get("id", [])
            results = []
            for rid in ids:
                if rid in self._store.roles:
                    obj = MagicMock()
                    obj.id = rid
                    results.append(obj)
            return results
        if self._model == Permission or (hasattr(self._model, 'key') and self._model.key == 'id'):
            ids = self._filter_in.get("id", [])
            results = []
            for pid in ids:
                if pid in self._store.permissions:
                    obj = MagicMock()
                    obj.id = pid
                    results.append(obj)
            return results
        return []


class FakeColumnQuery:
    """Handles queries like db.query(Role.id).filter(Role.id.in_(...))"""

    def __init__(self, model_class, column_name, store_ref):
        self._model_class = model_class
        self._column_name = column_name
        self._store = store_ref
        self._filter_in_values = []

    def filter(self, *args):
        for arg in args:
            try:
                if hasattr(arg, 'right'):
                    val = arg.right.effective_value if hasattr(arg.right, 'effective_value') else arg.right.value
                    self._filter_in_values = val
            except Exception:
                pass
        return self

    def all(self):
        results = []
        if self._model_class == Role:
            lookup = self._store.roles
        elif self._model_class == Permission:
            lookup = self._store.permissions
        else:
            lookup = {}

        for item_id in self._filter_in_values:
            if item_id in lookup:
                obj = MagicMock()
                obj.id = item_id
                results.append(obj)
        return results


class FakeSession:
    """Mimics SQLAlchemy Session for auto-provision tests."""

    def __init__(self, store_ref):
        self._store = store_ref

    def query(self, model):
        # Handle column-level queries like db.query(Role.id)
        if hasattr(model, 'property') and hasattr(model, 'class_'):
            return FakeColumnQuery(model.class_, model.key, self._store)
        if hasattr(model, 'key') and hasattr(model, 'class_'):
            return FakeColumnQuery(model.class_, model.key, self._store)
        return FakeQuery(model, self._store)

    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        if isinstance(obj, AutoProvisionConfig):
            if not obj.id:
                obj.id = uuid.uuid4()
            if not obj.created_at:
                obj.created_at = datetime.utcnow()
            if not obj.updated_at:
                obj.updated_at = datetime.utcnow()
            self._store.configs[obj.application_id] = obj
        elif isinstance(obj, Application):
            if not obj.id:
                obj.id = uuid.uuid4()
            if not obj.created_at:
                obj.created_at = datetime.utcnow()
            if not obj.updated_at:
                obj.updated_at = datetime.utcnow()
            obj._persisted = True
            self._store.apps[obj.app_id] = obj

    def delete(self, obj):
        if isinstance(obj, AutoProvisionConfig):
            self._store.configs.pop(obj.application_id, None)
        elif isinstance(obj, Application):
            self._store.apps.pop(obj.app_id, None)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Dependency overrides
# ---------------------------------------------------------------------------

def override_get_db():
    session = FakeSession(store)
    try:
        yield session
    finally:
        session.close()


def override_require_super_admin(user_id: str = Query(..., description="当前用户ID")):
    """Override that always passes super admin check."""
    return user_id


# Apply overrides
app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[require_super_admin] = override_require_super_admin

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_store():
    """每个测试前清空存储"""
    store.reset()
    yield
    store.reset()


def _create_app(name="TestApp"):
    """Helper: create an application via API and return response data."""
    resp = client.post(
        "/api/v1/admin/applications?user_id=admin1",
        json={"name": name},
    )
    assert resp.status_code == 201
    return resp.json()


def _add_role(name="test_role"):
    """Helper: add a role to the in-memory store and return its UUID."""
    role_id = uuid.uuid4()
    role = MagicMock(spec=Role)
    role.id = role_id
    role.name = name
    store.roles[role_id] = role
    return role_id


def _add_permission(name="test_perm"):
    """Helper: add a permission to the in-memory store and return its UUID."""
    perm_id = uuid.uuid4()
    perm = MagicMock(spec=Permission)
    perm.id = perm_id
    perm.name = name
    store.permissions[perm_id] = perm
    return perm_id


def _add_organization(name="test_org"):
    """Helper: add an organization to the in-memory store and return its UUID."""
    org_id = uuid.uuid4()
    org = MagicMock(spec=Organization)
    org.id = org_id
    org.name = name
    store.organizations[org_id] = org
    return org_id


def _add_subscription_plan(name="test_plan"):
    """Helper: add a subscription plan to the in-memory store and return its UUID."""
    plan_id = uuid.uuid4()
    plan = MagicMock(spec=SubscriptionPlan)
    plan.id = plan_id
    plan.name = name
    store.plans[plan_id] = plan
    return plan_id


BASE_URL = "/api/v1/admin/applications"


# ===========================================================================
# Task 3.1: GET/PUT/DELETE 正常流程测试
# ===========================================================================

class TestAutoProvisionNormalFlow:
    """GET/PUT/DELETE 正常流程测试"""

    def test_get_default_config_when_none_exists(self):
        """GET 不存在配置时应返回默认空配置"""
        app_data = _create_app("AutoProvApp")
        resp = client.get(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == app_data["app_id"]
        assert data["role_ids"] == []
        assert data["permission_ids"] == []
        assert data["organization_id"] is None
        assert data["subscription_plan_id"] is None
        assert data["is_enabled"] is False

    def test_put_create_config(self):
        """PUT 创建新的自动配置规则"""
        app_data = _create_app("AutoProvApp")
        role_id = _add_role("viewer")
        perm_id = _add_permission("read_data")
        org_id = _add_organization("engineering")
        plan_id = _add_subscription_plan("basic")

        payload = {
            "role_ids": [str(role_id)],
            "permission_ids": [str(perm_id)],
            "organization_id": str(org_id),
            "subscription_plan_id": str(plan_id),
            "is_enabled": True,
        }
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == app_data["app_id"]
        assert str(role_id) in data["role_ids"]
        assert str(perm_id) in data["permission_ids"]
        assert data["organization_id"] == str(org_id)
        assert data["subscription_plan_id"] == str(plan_id)
        assert data["is_enabled"] is True

    def test_put_update_existing_config(self):
        """PUT 更新已存在的自动配置规则"""
        app_data = _create_app("AutoProvApp")
        role_id1 = _add_role("viewer")
        role_id2 = _add_role("editor")

        # Create initial config
        payload1 = {
            "role_ids": [str(role_id1)],
            "is_enabled": True,
        }
        resp1 = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json=payload1,
        )
        assert resp1.status_code == 200

        # Update config
        payload2 = {
            "role_ids": [str(role_id1), str(role_id2)],
            "is_enabled": False,
        }
        resp2 = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json=payload2,
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert len(data["role_ids"]) == 2
        assert data["is_enabled"] is False

    def test_get_after_put(self):
        """PUT 创建后 GET 应返回相同配置"""
        app_data = _create_app("AutoProvApp")
        role_id = _add_role("admin")

        payload = {
            "role_ids": [str(role_id)],
            "is_enabled": True,
        }
        client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json=payload,
        )

        resp = client.get(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert str(role_id) in data["role_ids"]
        assert data["is_enabled"] is True

    def test_delete_config(self):
        """DELETE 删除自动配置规则"""
        app_data = _create_app("AutoProvApp")
        role_id = _add_role("viewer")

        # Create config first
        client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"role_ids": [str(role_id)], "is_enabled": True},
        )

        # Delete it
        resp = client.delete(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_get_after_delete_returns_default(self):
        """DELETE 后 GET 应返回默认空配置"""
        app_data = _create_app("AutoProvApp")
        role_id = _add_role("viewer")

        # Create then delete
        client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"role_ids": [str(role_id)], "is_enabled": True},
        )
        client.delete(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1"
        )

        # GET should return default
        resp = client.get(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_ids"] == []
        assert data["is_enabled"] is False

    def test_put_with_empty_optional_fields(self):
        """PUT 仅设置 is_enabled，其余字段为空"""
        app_data = _create_app("AutoProvApp")
        payload = {"is_enabled": True}
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_ids"] == []
        assert data["permission_ids"] == []
        assert data["organization_id"] is None
        assert data["subscription_plan_id"] is None
        assert data["is_enabled"] is True

    def test_delete_nonexistent_config_succeeds(self):
        """DELETE 不存在的配置应成功（幂等）"""
        app_data = _create_app("AutoProvApp")
        resp = client.delete(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ===========================================================================
# Task 3.2: 无效 role_ids/permission_ids/organization_id/subscription_plan_id 的 400 错误测试
# ===========================================================================

class TestAutoProvisionInvalidIds:
    """无效引用 ID 应返回 400 错误"""

    def test_invalid_role_ids(self):
        """不存在的 role_ids 应返回 400"""
        app_data = _create_app("AutoProvApp")
        fake_role_id = str(uuid.uuid4())
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"role_ids": [fake_role_id], "is_enabled": True},
        )
        assert resp.status_code == 400
        assert "角色ID" in resp.json()["detail"]

    def test_invalid_permission_ids(self):
        """不存在的 permission_ids 应返回 400"""
        app_data = _create_app("AutoProvApp")
        fake_perm_id = str(uuid.uuid4())
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"permission_ids": [fake_perm_id], "is_enabled": True},
        )
        assert resp.status_code == 400
        assert "权限ID" in resp.json()["detail"]

    def test_invalid_organization_id(self):
        """不存在的 organization_id 应返回 400"""
        app_data = _create_app("AutoProvApp")
        fake_org_id = str(uuid.uuid4())
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"organization_id": fake_org_id, "is_enabled": True},
        )
        assert resp.status_code == 400
        assert "组织ID" in resp.json()["detail"]

    def test_invalid_subscription_plan_id(self):
        """不存在的 subscription_plan_id 应返回 400"""
        app_data = _create_app("AutoProvApp")
        fake_plan_id = str(uuid.uuid4())
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"subscription_plan_id": fake_plan_id, "is_enabled": True},
        )
        assert resp.status_code == 400
        assert "订阅计划ID" in resp.json()["detail"]

    def test_invalid_role_id_format(self):
        """无效格式的 role_ids 应返回 400"""
        app_data = _create_app("AutoProvApp")
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"role_ids": ["not-a-uuid"], "is_enabled": True},
        )
        assert resp.status_code == 400

    def test_mixed_valid_and_invalid_role_ids(self):
        """部分有效部分无效的 role_ids 应返回 400"""
        app_data = _create_app("AutoProvApp")
        valid_role_id = _add_role("valid_role")
        fake_role_id = str(uuid.uuid4())
        resp = client.put(
            f"{BASE_URL}/{app_data['app_id']}/auto-provision?user_id=admin1",
            json={"role_ids": [str(valid_role_id), fake_role_id], "is_enabled": True},
        )
        assert resp.status_code == 400


# ===========================================================================
# Task 3.3: 非超级管理员访问返回 403 的测试
# ===========================================================================

class TestAutoProvisionForbidden:
    """非超级管理员访问应返回 403"""

    @pytest.fixture(autouse=True)
    def setup_forbidden_override(self):
        """Override require_super_admin to reject non-admin users."""
        from fastapi import HTTPException

        def reject_non_admin(user_id: str = Query(..., description="当前用户ID")):
            raise HTTPException(status_code=403, detail="只有超级管理员可以访问此接口")

        app.dependency_overrides[require_super_admin] = reject_non_admin
        yield
        # Restore the permissive override
        app.dependency_overrides[require_super_admin] = override_require_super_admin

    def test_get_forbidden(self):
        """非超级管理员 GET 应返回 403"""
        resp = client.get(
            f"{BASE_URL}/some-app-id/auto-provision?user_id=regular_user"
        )
        assert resp.status_code == 403

    def test_put_forbidden(self):
        """非超级管理员 PUT 应返回 403"""
        resp = client.put(
            f"{BASE_URL}/some-app-id/auto-provision?user_id=regular_user",
            json={"is_enabled": True},
        )
        assert resp.status_code == 403

    def test_delete_forbidden(self):
        """非超级管理员 DELETE 应返回 403"""
        resp = client.delete(
            f"{BASE_URL}/some-app-id/auto-provision?user_id=regular_user"
        )
        assert resp.status_code == 403


# ===========================================================================
# Task 3.4: 应用不存在时返回 404 的测试
# ===========================================================================

class TestAutoProvisionNotFound:
    """应用不存在时应返回 404"""

    def test_get_nonexistent_app(self):
        """GET 不存在的应用应返回 404"""
        resp = client.get(
            f"{BASE_URL}/nonexistent-app-id/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 404
        assert "应用不存在" in resp.json()["detail"]

    def test_put_nonexistent_app(self):
        """PUT 不存在的应用应返回 404"""
        resp = client.put(
            f"{BASE_URL}/nonexistent-app-id/auto-provision?user_id=admin1",
            json={"is_enabled": True},
        )
        assert resp.status_code == 404
        assert "应用不存在" in resp.json()["detail"]

    def test_delete_nonexistent_app(self):
        """DELETE 不存在的应用应返回 404"""
        resp = client.delete(
            f"{BASE_URL}/nonexistent-app-id/auto-provision?user_id=admin1"
        )
        assert resp.status_code == 404
        assert "应用不存在" in resp.json()["detail"]
