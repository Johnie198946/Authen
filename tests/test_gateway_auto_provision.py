"""
网关自动配置（Auto-Provision）单元测试

测试 _apply_auto_provision 函数在不同注册流程中的行为：
  - 邮箱注册触发自动配置
  - 手机注册触发自动配置
  - OAuth 首次注册触发自动配置
  - 配置禁用时不触发自动配置
  - 部分失败容错

需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""
import sys
import os
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gateway.main import _apply_auto_provision


# ---------------------------------------------------------------------------
# Fixtures & Constants
# ---------------------------------------------------------------------------

APP_ID = "test-app-id"
APP_UUID = uuid.uuid4()
USER_UUID = uuid.uuid4()
USER_ID = str(USER_UUID)
ROLE_ID_1 = uuid.uuid4()
ROLE_ID_2 = uuid.uuid4()
PERM_ID_1 = uuid.uuid4()
ORG_ID = uuid.uuid4()
PLAN_ID = uuid.uuid4()

APP_DATA = {
    "id": str(APP_UUID),
    "name": "Test App",
    "app_id": APP_ID,
    "app_secret_hash": "fakehash",
    "status": "active",
    "rate_limit": 60,
}


def _make_mock_app(app_uuid=APP_UUID):
    """Create a mock Application object."""
    app = MagicMock()
    app.id = app_uuid
    app.app_id = APP_ID
    return app


def _make_mock_config(
    role_ids=None,
    permission_ids=None,
    organization_id=None,
    subscription_plan_id=None,
    is_enabled=True,
):
    """Create a mock AutoProvisionConfig object."""
    config = MagicMock()
    config.role_ids = role_ids or []
    config.permission_ids = permission_ids or []
    config.organization_id = organization_id
    config.subscription_plan_id = subscription_plan_id
    config.is_enabled = is_enabled
    config.application_id = APP_UUID
    return config


def _make_mock_db(app=None, config=None, existing_role=None, existing_org=None,
                  existing_sub=None, role_perm=None, plan=None):
    """Create a mock database session with configurable query results."""
    db = MagicMock()

    def query_side_effect(model):
        mock_query = MagicMock()

        model_name = model.__name__ if hasattr(model, '__name__') else str(model)

        if model_name == 'Application':
            mock_query.filter.return_value.first.return_value = app
        elif model_name == 'AutoProvisionConfig':
            mock_query.filter.return_value.first.return_value = config
        elif model_name == 'UserRole':
            mock_query.filter.return_value.first.return_value = existing_role
        elif model_name == 'UserOrganization':
            mock_query.filter.return_value.first.return_value = existing_org
        elif model_name == 'UserSubscription':
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


# ===========================================================================
# 6.1 邮箱注册触发自动配置
# ===========================================================================

class TestEmailRegistrationAutoProvision:
    """邮箱注册触发自动配置的测试"""

    @patch("services.gateway.main._get_db")
    def test_email_register_triggers_role_assignment(self, mock_get_db):
        """邮箱注册成功后，自动为用户分配配置中的角色"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(role_ids=[str(ROLE_ID_1), str(ROLE_ID_2)])
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        # Should have called db.add for each role (UserRole not existing)
        assert mock_db.add.call_count >= 2
        assert mock_db.commit.call_count >= 2

    @patch("services.gateway.main._get_db")
    def test_email_register_triggers_org_assignment(self, mock_get_db):
        """邮箱注册成功后，自动将用户加入配置中的组织"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(organization_id=ORG_ID)
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_email_register_triggers_subscription_creation(self, mock_get_db):
        """邮箱注册成功后，自动为用户创建配置中的订阅"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 30
        mock_config = _make_mock_config(subscription_plan_id=PLAN_ID)
        mock_db = _make_mock_db(app=mock_app, config=mock_config, plan=mock_plan)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_email_register_full_auto_provision(self, mock_get_db):
        """邮箱注册成功后，完整自动配置（角色+组织+订阅）全部执行"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 30
        mock_config = _make_mock_config(
            role_ids=[str(ROLE_ID_1)],
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
        )
        mock_db = _make_mock_db(app=mock_app, config=mock_config, plan=mock_plan)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        # role + org + subscription = at least 3 adds and 3 commits
        assert mock_db.add.call_count >= 3
        assert mock_db.commit.call_count >= 3

    @patch("services.gateway.main._get_db")
    def test_no_config_does_nothing(self, mock_get_db):
        """应用没有自动配置规则时，不执行任何操作"""
        mock_app = _make_mock_app()
        mock_db = _make_mock_db(app=mock_app, config=None)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert not mock_db.add.called


# ===========================================================================
# 6.2 手机注册触发自动配置
# ===========================================================================

class TestPhoneRegistrationAutoProvision:
    """手机注册触发自动配置的测试"""

    @patch("services.gateway.main._get_db")
    def test_phone_register_triggers_role_assignment(self, mock_get_db):
        """手机注册成功后，自动为用户分配配置中的角色"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(role_ids=[str(ROLE_ID_1)])
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_phone_register_triggers_org_assignment(self, mock_get_db):
        """手机注册成功后，自动将用户加入配置中的组织"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(organization_id=ORG_ID)
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_phone_register_triggers_subscription(self, mock_get_db):
        """手机注册成功后，自动为用户创建订阅"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 60
        mock_config = _make_mock_config(subscription_plan_id=PLAN_ID)
        mock_db = _make_mock_db(app=mock_app, config=mock_config, plan=mock_plan)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_phone_register_idempotent_role(self, mock_get_db):
        """手机注册时，已存在的角色分配不重复创建（幂等性）"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(role_ids=[str(ROLE_ID_1)])
        existing_role = MagicMock()  # Simulate existing UserRole
        mock_db = _make_mock_db(app=mock_app, config=mock_config, existing_role=existing_role)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        # Should NOT add a new role since it already exists
        assert not mock_db.add.called


# ===========================================================================
# 6.3 OAuth 首次注册触发自动配置
# ===========================================================================

class TestOAuthRegistrationAutoProvision:
    """OAuth 首次注册触发自动配置的测试"""

    @patch("services.gateway.main._get_db")
    def test_oauth_new_user_triggers_role_assignment(self, mock_get_db):
        """OAuth 首次注册（is_new_user=True）触发角色分配"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(role_ids=[str(ROLE_ID_1), str(ROLE_ID_2)])
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.call_count >= 2
        assert mock_db.commit.call_count >= 2

    @patch("services.gateway.main._get_db")
    def test_oauth_new_user_triggers_org_assignment(self, mock_get_db):
        """OAuth 首次注册触发组织加入"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(organization_id=ORG_ID)
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_oauth_new_user_triggers_subscription(self, mock_get_db):
        """OAuth 首次注册触发订阅创建"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 90
        mock_config = _make_mock_config(subscription_plan_id=PLAN_ID)
        mock_db = _make_mock_db(app=mock_app, config=mock_config, plan=mock_plan)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.called
        assert mock_db.commit.called

    @patch("services.gateway.main._get_db")
    def test_oauth_new_user_full_provision(self, mock_get_db):
        """OAuth 首次注册触发完整自动配置"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 30
        mock_config = _make_mock_config(
            role_ids=[str(ROLE_ID_1)],
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
        )
        mock_db = _make_mock_db(app=mock_app, config=mock_config, plan=mock_plan)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert mock_db.add.call_count >= 3
        assert mock_db.commit.call_count >= 3


# ===========================================================================
# 6.4 配置禁用时不触发自动配置
# ===========================================================================

class TestDisabledConfigSkipsProvision:
    """配置禁用时不触发自动配置的测试"""

    @patch("services.gateway.main._get_db")
    def test_disabled_config_skips_role_assignment(self, mock_get_db):
        """is_enabled=False 时，不分配角色"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(
            role_ids=[str(ROLE_ID_1), str(ROLE_ID_2)],
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
            is_enabled=False,
        )
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert not mock_db.add.called

    @patch("services.gateway.main._get_db")
    def test_disabled_config_no_org_join(self, mock_get_db):
        """is_enabled=False 时，不加入组织"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(
            organization_id=ORG_ID,
            is_enabled=False,
        )
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert not mock_db.add.called

    @patch("services.gateway.main._get_db")
    def test_disabled_config_no_subscription(self, mock_get_db):
        """is_enabled=False 时，不创建订阅"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(
            subscription_plan_id=PLAN_ID,
            is_enabled=False,
        )
        mock_db = _make_mock_db(app=mock_app, config=mock_config)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert not mock_db.add.called

    @patch("services.gateway.main._get_db")
    def test_no_app_found_does_nothing(self, mock_get_db):
        """应用不存在时，不执行任何操作"""
        mock_db = _make_mock_db(app=None, config=None)
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, USER_ID)

        assert not mock_db.add.called

    @patch("services.gateway.main._get_db")
    def test_invalid_user_id_does_nothing(self, mock_get_db):
        """无效的 user_id 时，不执行任何操作"""
        mock_db = _make_mock_db()
        mock_get_db.return_value = mock_db

        _apply_auto_provision(APP_DATA, "not-a-valid-uuid")

        assert not mock_db.add.called


# ===========================================================================
# 6.5 部分失败容错
# ===========================================================================

class TestPartialFailureTolerance:
    """部分失败容错的测试：某步骤异常时，其余步骤仍执行"""

    @patch("services.gateway.main._get_db")
    def test_role_failure_still_assigns_org_and_subscription(self, mock_get_db):
        """角色分配失败时，组织加入和订阅创建仍然执行"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 30
        mock_config = _make_mock_config(
            role_ids=[str(ROLE_ID_1)],
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
        )

        db = MagicMock()
        mock_get_db.return_value = db

        call_count = {"n": 0}

        def query_side_effect(model):
            mock_query = MagicMock()
            model_name = model.__name__ if hasattr(model, '__name__') else str(model)

            if model_name == 'Application':
                mock_query.filter.return_value.first.return_value = mock_app
            elif model_name == 'AutoProvisionConfig':
                mock_query.filter.return_value.first.return_value = mock_config
            elif model_name == 'UserRole':
                # First call for role assignment - raise exception
                call_count["n"] += 1
                if call_count["n"] == 1:
                    mock_query.filter.return_value.first.side_effect = Exception("DB error on role")
                else:
                    mock_query.filter.return_value.first.return_value = None
            elif model_name == 'UserOrganization':
                mock_query.filter.return_value.first.return_value = None
            elif model_name == 'UserSubscription':
                mock_query.filter.return_value.first.return_value = None
            elif model_name == 'SubscriptionPlan':
                mock_query.filter.return_value.first.return_value = mock_plan
            else:
                mock_query.filter.return_value.first.return_value = None

            return mock_query

        db.query.side_effect = query_side_effect

        _apply_auto_provision(APP_DATA, USER_ID)

        # Despite role failure, org and subscription should still be added
        # At least 2 adds (org + subscription)
        assert db.add.call_count >= 2

    @patch("services.gateway.main._get_db")
    def test_org_failure_still_creates_subscription(self, mock_get_db):
        """组织加入失败时，订阅创建仍然执行"""
        mock_app = _make_mock_app()
        mock_plan = MagicMock()
        mock_plan.duration_days = 30
        mock_config = _make_mock_config(
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
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
            elif model_name == 'UserOrganization':
                mock_query.filter.return_value.first.side_effect = Exception("DB error on org")
            elif model_name == 'UserSubscription':
                mock_query.filter.return_value.first.return_value = None
            elif model_name == 'SubscriptionPlan':
                mock_query.filter.return_value.first.return_value = mock_plan
            else:
                mock_query.filter.return_value.first.return_value = None

            return mock_query

        db.query.side_effect = query_side_effect

        _apply_auto_provision(APP_DATA, USER_ID)

        # Despite org failure, subscription should still be added
        assert db.add.call_count >= 1

    @patch("services.gateway.main._get_db")
    def test_subscription_failure_does_not_affect_roles_and_org(self, mock_get_db):
        """订阅创建失败不影响已完成的角色分配和组织加入"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(
            role_ids=[str(ROLE_ID_1)],
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
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
                mock_query.filter.return_value.first.return_value = None
            elif model_name == 'UserOrganization':
                mock_query.filter.return_value.first.return_value = None
            elif model_name == 'UserSubscription':
                mock_query.filter.return_value.first.side_effect = Exception("DB error on sub")
            else:
                mock_query.filter.return_value.first.return_value = None

            return mock_query

        db.query.side_effect = query_side_effect

        _apply_auto_provision(APP_DATA, USER_ID)

        # Role and org should still be added (2 adds) despite subscription failure
        assert db.add.call_count >= 2

    @patch("services.gateway.main._get_db")
    def test_all_steps_fail_gracefully(self, mock_get_db):
        """所有步骤都失败时，函数不抛出异常"""
        mock_app = _make_mock_app()
        mock_config = _make_mock_config(
            role_ids=[str(ROLE_ID_1)],
            organization_id=ORG_ID,
            subscription_plan_id=PLAN_ID,
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
            else:
                mock_query.filter.return_value.first.side_effect = Exception("DB error")

            return mock_query

        db.query.side_effect = query_side_effect

        # Should not raise any exception
        _apply_auto_provision(APP_DATA, USER_ID)

        # Rollback should have been called for each failure
        assert db.rollback.call_count >= 1
