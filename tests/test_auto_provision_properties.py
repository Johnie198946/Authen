"""
用户自动配置属性测试

Feature: user-auto-provision, Properties 1-4, 9

使用 Hypothesis 属性测试框架验证自动配置规则管理 API 的正确性属性。
复用 test_admin_auto_provision.py 中的 FakeSession/Store 模式。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
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
# In-memory stores for testing (same pattern as test_admin_auto_provision.py)
# ---------------------------------------------------------------------------

class Store:
    """In-memory store for all model types."""

    def __init__(self):
        self.apps = {}
        self.configs = {}
        self.roles = {}
        self.permissions = {}
        self.organizations = {}
        self.plans = {}

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
        self._filter_in = {}

    def filter(self, *args):
        for arg in args:
            try:
                col_name = arg.left.key
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
            # Cascade: also delete associated config
            app_uuid = obj.id
            self._store.configs.pop(app_uuid, None)
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

BASE_URL = "/api/v1/admin/applications"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_store():
    """每个测试前清空存储"""
    store.reset()
    # Restore permissive overrides (in case a previous test changed them)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_super_admin] = override_require_super_admin
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


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Strategy for generating a list of 0-5 role IDs (from freshly created roles)
num_roles_st = st.integers(min_value=0, max_value=5)
num_perms_st = st.integers(min_value=0, max_value=5)
bool_st = st.booleans()
optional_bool_st = st.sampled_from([True, False])


# ===========================================================================
# Property 1: 配置读写往返一致性（Config Round-Trip）
# Feature: user-auto-provision, Property 1: Config Round-Trip
# ===========================================================================

class TestProperty1ConfigRoundTrip:
    """
    Property 1: 配置读写往返一致性

    对于任意有效的自动配置数据（role_ids、permission_ids、organization_id、
    subscription_plan_id、is_enabled 的任意合法组合），通过 PUT 保存后再通过
    GET 读取，应返回与保存时等价的配置数据。

    **Validates: Requirements 2.1, 2.2, 1.4**
    Feature: user-auto-provision, Property 1: Config Round-Trip
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_roles=num_roles_st,
        num_perms=num_perms_st,
        include_org=bool_st,
        include_plan=bool_st,
        is_enabled=bool_st,
    )
    def test_put_then_get_returns_equivalent_config(
        self, num_roles, num_perms, include_org, include_plan, is_enabled
    ):
        """
        属性测试：PUT 保存配置后 GET 读取应返回等价数据

        Feature: user-auto-provision, Property 1: Config Round-Trip
        **Validates: Requirements 2.1, 2.2, 1.4**
        """
        store.reset()

        # Create application
        app_data = _create_app(f"PropApp_{uuid.uuid4().hex[:6]}")
        app_id = app_data["app_id"]

        # Create valid referenced entities
        role_ids = [str(_add_role(f"role_{i}")) for i in range(num_roles)]
        perm_ids = [str(_add_permission(f"perm_{i}")) for i in range(num_perms)]
        org_id = str(_add_organization("org")) if include_org else None
        plan_id = str(_add_subscription_plan("plan")) if include_plan else None

        # Build payload
        payload = {"is_enabled": is_enabled}
        if role_ids:
            payload["role_ids"] = role_ids
        if perm_ids:
            payload["permission_ids"] = perm_ids
        if org_id:
            payload["organization_id"] = org_id
        if plan_id:
            payload["subscription_plan_id"] = plan_id

        # PUT
        put_resp = client.put(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1",
            json=payload,
        )
        assert put_resp.status_code == 200

        # GET
        get_resp = client.get(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()

        # Verify round-trip equivalence
        assert data["application_id"] == app_id
        assert sorted(data["role_ids"]) == sorted(role_ids)
        assert sorted(data["permission_ids"]) == sorted(perm_ids)
        assert data["organization_id"] == org_id
        assert data["subscription_plan_id"] == plan_id
        assert data["is_enabled"] == is_enabled


# ===========================================================================
# Property 2: 无效引用 ID 校验（Invalid Reference Rejection）
# Feature: user-auto-provision, Property 2: Invalid Reference Rejection
# ===========================================================================

class TestProperty2InvalidReferenceRejection:
    """
    Property 2: 无效引用 ID 校验

    对于任意不存在于目标表中的引用 ID（role_ids 中的角色 ID、permission_ids
    中的权限 ID、organization_id、subscription_plan_id），PUT 端点应返回
    HTTP 400 错误，且响应体包含具体的无效 ID 信息。

    **Validates: Requirements 2.4, 2.5, 2.6, 2.7**
    Feature: user-auto-provision, Property 2: Invalid Reference Rejection
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        invalid_field=st.sampled_from(["role_ids", "permission_ids", "organization_id", "subscription_plan_id"]),
    )
    def test_nonexistent_reference_ids_return_400(self, invalid_field):
        """
        属性测试：不存在的引用 ID 应返回 400

        Feature: user-auto-provision, Property 2: Invalid Reference Rejection
        **Validates: Requirements 2.4, 2.5, 2.6, 2.7**
        """
        store.reset()

        app_data = _create_app(f"PropApp_{uuid.uuid4().hex[:6]}")
        app_id = app_data["app_id"]

        # Generate a random non-existent UUID
        fake_id = str(uuid.uuid4())

        payload = {"is_enabled": True}
        if invalid_field == "role_ids":
            payload["role_ids"] = [fake_id]
        elif invalid_field == "permission_ids":
            payload["permission_ids"] = [fake_id]
        elif invalid_field == "organization_id":
            payload["organization_id"] = fake_id
        elif invalid_field == "subscription_plan_id":
            payload["subscription_plan_id"] = fake_id

        resp = client.put(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1",
            json=payload,
        )
        assert resp.status_code == 400


# ===========================================================================
# Property 3: 应用删除级联清除配置（Cascade Deletion）
# Feature: user-auto-provision, Property 3: Cascade Deletion
# ===========================================================================

class TestProperty3CascadeDeletion:
    """
    Property 3: 应用删除级联清除配置

    对于任意拥有自动配置规则的应用，删除该应用后，对应的
    AutoProvisionConfig 记录应不再存在于数据库中。

    **Validates: Requirements 1.3**
    Feature: user-auto-provision, Property 3: Cascade Deletion
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_roles=st.integers(min_value=0, max_value=3),
        is_enabled=bool_st,
    )
    def test_deleting_app_removes_auto_provision_config(self, num_roles, is_enabled):
        """
        属性测试：删除应用后自动配置规则也被删除

        Feature: user-auto-provision, Property 3: Cascade Deletion
        **Validates: Requirements 1.3**
        """
        store.reset()

        # Create application
        app_data = _create_app(f"CascadeApp_{uuid.uuid4().hex[:6]}")
        app_id = app_data["app_id"]

        # Create valid roles and set up config
        role_ids = [str(_add_role(f"role_{i}")) for i in range(num_roles)]
        payload = {"is_enabled": is_enabled}
        if role_ids:
            payload["role_ids"] = role_ids

        # PUT config
        put_resp = client.put(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1",
            json=payload,
        )
        assert put_resp.status_code == 200

        # Verify config exists
        get_resp = client.get(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1"
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["is_enabled"] == is_enabled

        # Delete the application
        del_resp = client.delete(
            f"{BASE_URL}/{app_id}?user_id=admin1"
        )
        assert del_resp.status_code == 204

        # Verify config no longer accessible (app is gone → 404)
        get_resp2 = client.get(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1"
        )
        assert get_resp2.status_code == 404


# ===========================================================================
# Property 4: 一对一唯一约束（One-to-One Uniqueness）
# Feature: user-auto-provision, Property 4: One-to-One Uniqueness
# ===========================================================================

class TestProperty4OneToOneUniqueness:
    """
    Property 4: 一对一唯一约束

    对于任意应用，数据库中最多只能存在一条与之关联的 AutoProvisionConfig
    记录。多次 PUT 同一应用的配置应更新而非创建新记录。

    **Validates: Requirements 1.1**
    Feature: user-auto-provision, Property 4: One-to-One Uniqueness
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_updates=st.integers(min_value=2, max_value=5),
    )
    def test_multiple_puts_result_in_single_config(self, num_updates):
        """
        属性测试：多次 PUT 同一应用只产生一条配置记录

        Feature: user-auto-provision, Property 4: One-to-One Uniqueness
        **Validates: Requirements 1.1**
        """
        store.reset()

        app_data = _create_app(f"UniqueApp_{uuid.uuid4().hex[:6]}")
        app_id = app_data["app_id"]

        last_enabled = None
        for i in range(num_updates):
            is_enabled = (i % 2 == 0)
            last_enabled = is_enabled
            payload = {"is_enabled": is_enabled}

            resp = client.put(
                f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1",
                json=payload,
            )
            assert resp.status_code == 200

        # GET should return exactly one config with the last update's value
        get_resp = client.get(
            f"{BASE_URL}/{app_id}/auto-provision?user_id=admin1"
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["is_enabled"] == last_enabled
        assert data["application_id"] == app_id

        # Verify only one config exists in the store for this app
        app_obj = store.apps.get(app_id)
        if app_obj:
            config_count = sum(
                1 for k, v in store.configs.items()
                if v.application_id == app_obj.id
            )
            assert config_count == 1


# ===========================================================================
# Property 9: 超级管理员权限控制（Super Admin Access Control）
# Feature: user-auto-provision, Property 9: Super Admin Access Control
# ===========================================================================

class TestProperty9SuperAdminAccessControl:
    """
    Property 9: 超级管理员权限控制

    对于任意非超级管理员用户，访问自动配置规则管理的所有端点
    （GET、PUT、DELETE）应返回 403 Forbidden。

    **Validates: Requirements 2.8**
    Feature: user-auto-provision, Property 9: Super Admin Access Control
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        method=st.sampled_from(["GET", "PUT", "DELETE"]),
        user_id=st.text(
            alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
            min_size=3,
            max_size=20,
        ),
    )
    def test_non_super_admin_gets_403(self, method, user_id):
        """
        属性测试：非超级管理员访问任何端点都返回 403

        Feature: user-auto-provision, Property 9: Super Admin Access Control
        **Validates: Requirements 2.8**
        """
        store.reset()

        # Override require_super_admin to reject all users
        def reject_non_admin(user_id: str = Query(..., description="当前用户ID")):
            raise HTTPException(status_code=403, detail="只有超级管理员可以访问此接口")

        app.dependency_overrides[require_super_admin] = reject_non_admin

        try:
            fake_app_id = "some-app-id"
            url = f"{BASE_URL}/{fake_app_id}/auto-provision?user_id={user_id}"

            if method == "GET":
                resp = client.get(url)
            elif method == "PUT":
                resp = client.put(url, json={"is_enabled": True})
            elif method == "DELETE":
                resp = client.delete(url)

            assert resp.status_code == 403
        finally:
            # Restore permissive override
            app.dependency_overrides[require_super_admin] = override_require_super_admin


# ===========================================================================
# Gateway Property Tests (Properties 5, 6, 7, 8, 10)
# These test _apply_auto_provision from services/gateway/main.py using mocks.
# ===========================================================================

from unittest.mock import patch


def _make_mock_app_obj(app_uuid=None):
    """Create a mock Application object for gateway tests."""
    app_obj = MagicMock()
    app_obj.id = app_uuid or uuid.uuid4()
    app_obj.app_id = "test-app-id"
    return app_obj


def _make_mock_config_obj(
    app_uuid=None,
    role_ids=None,
    permission_ids=None,
    organization_id=None,
    subscription_plan_id=None,
    is_enabled=True,
):
    """Create a mock AutoProvisionConfig object for gateway tests."""
    config = MagicMock()
    config.role_ids = role_ids or []
    config.permission_ids = permission_ids or []
    config.organization_id = organization_id
    config.subscription_plan_id = subscription_plan_id
    config.is_enabled = is_enabled
    config.application_id = app_uuid or uuid.uuid4()
    return config


def _make_gateway_mock_db(
    app_obj=None,
    config_obj=None,
    existing_role=None,
    existing_org=None,
    existing_sub=None,
    role_perm=None,
    plan=None,
    role_query_side_effect=None,
    org_query_side_effect=None,
    sub_query_side_effect=None,
):
    """Create a mock database session for gateway _apply_auto_provision tests."""
    db = MagicMock()

    def query_side_effect(model):
        mock_query = MagicMock()
        model_name = model.__name__ if hasattr(model, '__name__') else str(model)

        if model_name == 'Application':
            mock_query.filter.return_value.first.return_value = app_obj
        elif model_name == 'AutoProvisionConfig':
            mock_query.filter.return_value.first.return_value = config_obj
        elif model_name == 'UserRole':
            if role_query_side_effect:
                mock_query.filter.return_value.first.side_effect = role_query_side_effect
            else:
                mock_query.filter.return_value.first.return_value = existing_role
        elif model_name == 'UserOrganization':
            if org_query_side_effect:
                mock_query.filter.return_value.first.side_effect = org_query_side_effect
            else:
                mock_query.filter.return_value.first.return_value = existing_org
        elif model_name == 'UserSubscription':
            if sub_query_side_effect:
                mock_query.filter.return_value.first.side_effect = sub_query_side_effect
            else:
                mock_query.filter.return_value.first.return_value = existing_sub
        elif model_name == 'RolePermission':
            mock_query.filter.return_value.first.return_value = role_perm
        elif model_name == 'SubscriptionPlan':
            mock_query.filter.return_value.first.return_value = plan
        else:
            mock_query.filter.return_value.first.return_value = None

        return mock_query

    db.query.side_effect = query_side_effect
    return db


# Hypothesis strategies for gateway property tests
role_count_st = st.integers(min_value=0, max_value=5)
perm_count_st = st.integers(min_value=0, max_value=3)
include_org_st = st.booleans()
include_plan_st = st.booleans()


def _build_app_data(app_id="test-app-id"):
    return {
        "id": str(uuid.uuid4()),
        "name": "Test App",
        "app_id": app_id,
        "app_secret_hash": "fakehash",
        "status": "active",
        "rate_limit": 60,
    }


# ===========================================================================
# Property 5: 注册自动配置执行（Auto-Provision on Registration）
# Feature: user-auto-provision, Property 5: Auto-Provision on Registration
# ===========================================================================

class TestProperty5AutoProvisionOnRegistration:
    """
    Property 5: 注册自动配置执行

    对于任意拥有已启用自动配置规则的应用，通过任意注册路径成功注册的用户，
    应自动获得配置中指定的所有角色、权限、组织归属和订阅计划。

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
    Feature: user-auto-provision, Property 5: Auto-Provision on Registration
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_roles=role_count_st,
        include_org=include_org_st,
        include_plan=include_plan_st,
    )
    @patch("services.gateway.main._get_db")
    def test_enabled_config_provisions_all_resources(
        self, mock_get_db, num_roles, include_org, include_plan
    ):
        """
        属性测试：启用的配置应为新用户分配所有配置的资源

        Feature: user-auto-provision, Property 5: Auto-Provision on Registration
        **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
        """
        from services.gateway.main import _apply_auto_provision

        app_uuid = uuid.uuid4()
        user_id = str(uuid.uuid4())

        role_ids = [str(uuid.uuid4()) for _ in range(num_roles)]
        org_id = uuid.uuid4() if include_org else None
        plan_id = uuid.uuid4() if include_plan else None

        mock_app = _make_mock_app_obj(app_uuid)
        mock_plan_obj = None
        if include_plan:
            mock_plan_obj = MagicMock()
            mock_plan_obj.duration_days = 30

        mock_config = _make_mock_config_obj(
            app_uuid=app_uuid,
            role_ids=role_ids,
            organization_id=org_id,
            subscription_plan_id=plan_id,
            is_enabled=True,
        )

        mock_db = _make_gateway_mock_db(
            app_obj=mock_app,
            config_obj=mock_config,
            plan=mock_plan_obj,
        )
        mock_get_db.return_value = mock_db

        app_data = _build_app_data()
        _apply_auto_provision(app_data, user_id)

        # Count expected adds: one per role + (1 if org) + (1 if plan)
        expected_adds = num_roles
        if include_org:
            expected_adds += 1
        if include_plan:
            expected_adds += 1

        assert mock_db.add.call_count == expected_adds
        # Each add should be followed by a commit
        assert mock_db.commit.call_count == expected_adds


# ===========================================================================
# Property 6: 禁用配置不触发自动配置（Disabled Config Skipped）
# Feature: user-auto-provision, Property 6: Disabled Config Skipped
# ===========================================================================

class TestProperty6DisabledConfigSkipped:
    """
    Property 6: 禁用配置不触发自动配置

    对于任意拥有自动配置规则但 is_enabled=False 的应用，通过该应用注册的
    用户不应获得任何自动分配的角色、权限、组织或订阅。

    **Validates: Requirements 3.8**
    Feature: user-auto-provision, Property 6: Disabled Config Skipped
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_roles=role_count_st,
        include_org=include_org_st,
        include_plan=include_plan_st,
    )
    @patch("services.gateway.main._get_db")
    def test_disabled_config_does_not_provision(
        self, mock_get_db, num_roles, include_org, include_plan
    ):
        """
        属性测试：禁用的配置不应触发任何自动分配

        Feature: user-auto-provision, Property 6: Disabled Config Skipped
        **Validates: Requirements 3.8**
        """
        from services.gateway.main import _apply_auto_provision

        app_uuid = uuid.uuid4()
        user_id = str(uuid.uuid4())

        role_ids = [str(uuid.uuid4()) for _ in range(num_roles)]
        org_id = uuid.uuid4() if include_org else None
        plan_id = uuid.uuid4() if include_plan else None

        mock_app = _make_mock_app_obj(app_uuid)
        mock_config = _make_mock_config_obj(
            app_uuid=app_uuid,
            role_ids=role_ids,
            organization_id=org_id,
            subscription_plan_id=plan_id,
            is_enabled=False,  # DISABLED
        )

        mock_db = _make_gateway_mock_db(
            app_obj=mock_app,
            config_obj=mock_config,
        )
        mock_get_db.return_value = mock_db

        app_data = _build_app_data()
        _apply_auto_provision(app_data, user_id)

        # No resources should be added when config is disabled
        assert mock_db.add.call_count == 0
        assert mock_db.commit.call_count == 0


# ===========================================================================
# Property 7: 自动配置幂等性（Idempotent Provisioning）
# Feature: user-auto-provision, Property 7: Idempotent Provisioning
# ===========================================================================

class TestProperty7IdempotentProvisioning:
    """
    Property 7: 自动配置幂等性

    对于任意用户和任意自动配置规则，执行两次自动配置后的系统状态应与执行
    一次完全相同——不产生重复的角色分配、权限分配、组织关联或订阅记录。

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    Feature: user-auto-provision, Property 7: Idempotent Provisioning
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_roles=role_count_st,
        include_org=include_org_st,
        include_plan=include_plan_st,
    )
    @patch("services.gateway.main._get_db")
    def test_second_provision_adds_nothing(
        self, mock_get_db, num_roles, include_org, include_plan
    ):
        """
        属性测试：第二次执行自动配置不应产生任何新的分配

        Feature: user-auto-provision, Property 7: Idempotent Provisioning
        **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
        """
        from services.gateway.main import _apply_auto_provision

        app_uuid = uuid.uuid4()
        user_id = str(uuid.uuid4())

        role_ids = [str(uuid.uuid4()) for _ in range(num_roles)]
        org_id = uuid.uuid4() if include_org else None
        plan_id = uuid.uuid4() if include_plan else None

        mock_app = _make_mock_app_obj(app_uuid)
        mock_plan_obj = None
        if include_plan:
            mock_plan_obj = MagicMock()
            mock_plan_obj.duration_days = 30

        mock_config = _make_mock_config_obj(
            app_uuid=app_uuid,
            role_ids=role_ids,
            organization_id=org_id,
            subscription_plan_id=plan_id,
            is_enabled=True,
        )

        # Second run: all resources already exist
        existing_role = MagicMock()  # Simulates existing UserRole
        existing_org = MagicMock()   # Simulates existing UserOrganization
        existing_sub = MagicMock()   # Simulates existing UserSubscription

        mock_db = _make_gateway_mock_db(
            app_obj=mock_app,
            config_obj=mock_config,
            existing_role=existing_role,
            existing_org=existing_org,
            existing_sub=existing_sub,
            plan=mock_plan_obj,
        )
        mock_get_db.return_value = mock_db

        app_data = _build_app_data()
        _apply_auto_provision(app_data, user_id)

        # When all resources already exist, nothing should be added
        assert mock_db.add.call_count == 0


# ===========================================================================
# Property 8: 部分失败容错（Partial Failure Tolerance）
# Feature: user-auto-provision, Property 8: Partial Failure Tolerance
# ===========================================================================

class TestProperty8PartialFailureTolerance:
    """
    Property 8: 部分失败容错

    对于任意自动配置规则，若其中某一项分配操作失败，其余分配操作应继续
    执行完成，且用户注册本身不受影响。

    **Validates: Requirements 3.7**
    Feature: user-auto-provision, Property 8: Partial Failure Tolerance
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        failing_step=st.sampled_from(["role", "org", "subscription"]),
    )
    @patch("services.gateway.main._get_db")
    def test_one_step_failure_does_not_block_others(
        self, mock_get_db, failing_step
    ):
        """
        属性测试：单步失败不阻止其余步骤执行

        Feature: user-auto-provision, Property 8: Partial Failure Tolerance
        **Validates: Requirements 3.7**
        """
        from services.gateway.main import _apply_auto_provision

        app_uuid = uuid.uuid4()
        user_id = str(uuid.uuid4())
        role_id = str(uuid.uuid4())
        org_id = uuid.uuid4()
        plan_id = uuid.uuid4()

        mock_app = _make_mock_app_obj(app_uuid)
        mock_plan_obj = MagicMock()
        mock_plan_obj.duration_days = 30

        mock_config = _make_mock_config_obj(
            app_uuid=app_uuid,
            role_ids=[role_id],
            organization_id=org_id,
            subscription_plan_id=plan_id,
            is_enabled=True,
        )

        db = MagicMock()
        mock_get_db.return_value = db

        def query_side_effect(model):
            mock_query = MagicMock()
            model_name = model.__name__ if hasattr(model, '__name__') else str(model)

            if model_name == 'Application':
                mock_query.filter.return_value.first.return_value = mock_app
            elif model_name == 'AutoProvisionConfig':
                mock_query.filter.return_value.first.return_value = mock_config
            elif model_name == 'UserRole':
                if failing_step == "role":
                    mock_query.filter.return_value.first.side_effect = Exception("DB error on role")
                else:
                    mock_query.filter.return_value.first.return_value = None
            elif model_name == 'UserOrganization':
                if failing_step == "org":
                    mock_query.filter.return_value.first.side_effect = Exception("DB error on org")
                else:
                    mock_query.filter.return_value.first.return_value = None
            elif model_name == 'UserSubscription':
                if failing_step == "subscription":
                    mock_query.filter.return_value.first.side_effect = Exception("DB error on sub")
                else:
                    mock_query.filter.return_value.first.return_value = None
            elif model_name == 'SubscriptionPlan':
                mock_query.filter.return_value.first.return_value = mock_plan_obj
            else:
                mock_query.filter.return_value.first.return_value = None

            return mock_query

        db.query.side_effect = query_side_effect

        # Should not raise any exception
        _apply_auto_provision(_build_app_data(), user_id)

        # The non-failing steps should still have added resources.
        # Total possible adds = 3 (1 role + 1 org + 1 subscription)
        # One step fails, so we expect at least 2 successful adds.
        assert db.add.call_count >= 2
        # Rollback should be called for the failing step
        assert db.rollback.call_count >= 1


# ===========================================================================
# Property 10: 删除配置后不再生效（Deleted Config Inactive）
# Feature: user-auto-provision, Property 10: Deleted Config Inactive
# ===========================================================================

class TestProperty10DeletedConfigInactive:
    """
    Property 10: 删除配置后不再生效

    对于任意应用，删除其自动配置规则后，通过该应用注册的新用户不应获得
    任何自动分配。

    **Validates: Requirements 2.3, 3.8**
    Feature: user-auto-provision, Property 10: Deleted Config Inactive
    """

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    @given(
        num_roles=role_count_st,
        include_org=include_org_st,
        include_plan=include_plan_st,
    )
    @patch("services.gateway.main._get_db")
    def test_deleted_config_does_not_provision(
        self, mock_get_db, num_roles, include_org, include_plan
    ):
        """
        属性测试：删除配置后注册不触发任何自动分配

        Feature: user-auto-provision, Property 10: Deleted Config Inactive
        **Validates: Requirements 2.3, 3.8**
        """
        from services.gateway.main import _apply_auto_provision

        app_uuid = uuid.uuid4()
        user_id = str(uuid.uuid4())

        # Config is None (deleted)
        mock_app = _make_mock_app_obj(app_uuid)
        mock_db = _make_gateway_mock_db(
            app_obj=mock_app,
            config_obj=None,  # Config has been deleted
        )
        mock_get_db.return_value = mock_db

        app_data = _build_app_data()
        _apply_auto_provision(app_data, user_id)

        # No resources should be added when config doesn't exist
        assert mock_db.add.call_count == 0
        assert mock_db.commit.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
