"""
测试超级管理员权限检查功能

需求：6.2, 6.3
属性 25：超级管理员无限权限
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base, get_db
from shared.models.permission import Role, Permission, UserRole, RolePermission
from shared.models.user import User
from services.permission.main import app, is_super_admin, check_permission
import uuid
from unittest.mock import MagicMock, patch

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_super_admin_permissions.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis for all tests"""
    with patch('services.permission.main.get_redis') as mock_get_redis:
        mock_redis_client = MagicMock()
        # 默认返回None（缓存未命中）
        mock_redis_client.get.return_value = None
        mock_redis_client.setex.return_value = True
        mock_redis_client.delete.return_value = True
        mock_get_redis.return_value = mock_redis_client
        yield mock_redis_client

@pytest.fixture
def db_session():
    """提供数据库会话"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def super_admin_role(db_session):
    """创建超级管理员角色"""
    role = Role(
        id=uuid.uuid4(),
        name="super_admin",
        description="超级管理员，拥有所有权限",
        is_system_role=True
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role

@pytest.fixture
def regular_role(db_session):
    """创建普通角色"""
    role = Role(
        id=uuid.uuid4(),
        name="regular_user",
        description="普通用户",
        is_system_role=False
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role

@pytest.fixture
def test_permission(db_session):
    """创建测试权限"""
    perm = Permission(
        id=uuid.uuid4(),
        name="test:action",
        resource="test",
        action="action",
        description="Test Permission"
    )
    db_session.add(perm)
    db_session.commit()
    db_session.refresh(perm)
    return perm

@pytest.fixture
def super_admin_user(db_session, super_admin_role):
    """创建超级管理员用户"""
    user = User(
        id=uuid.uuid4(),
        username="admin",
        email="admin@example.com",
        password_hash="hashed_password",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # 分配超级管理员角色
    user_role = UserRole(user_id=user.id, role_id=super_admin_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user

@pytest.fixture
def regular_user(db_session, regular_role):
    """创建普通用户"""
    user = User(
        id=uuid.uuid4(),
        username="regular",
        email="regular@example.com",
        password_hash="hashed_password",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    # 分配普通角色
    user_role = UserRole(user_id=user.id, role_id=regular_role.id)
    db_session.add(user_role)
    db_session.commit()
    
    return user


class TestSuperAdminIdentification:
    """测试超级管理员识别"""
    
    def test_identify_super_admin(self, super_admin_user, db_session):
        """测试识别超级管理员"""
        user_id = str(super_admin_user.id)
        
        result = is_super_admin(user_id, db_session)
        
        assert result is True
    
    def test_identify_regular_user_as_not_super_admin(self, regular_user, db_session):
        """测试识别普通用户不是超级管理员"""
        user_id = str(regular_user.id)
        
        result = is_super_admin(user_id, db_session)
        
        assert result is False
    
    def test_identify_user_without_roles_as_not_super_admin(self, db_session):
        """测试没有角色的用户不是超级管理员"""
        user = User(
            id=uuid.uuid4(),
            username="noroles",
            email="noroles@example.com",
            password_hash="hashed_password",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        user_id = str(user.id)
        result = is_super_admin(user_id, db_session)
        
        assert result is False
    
    def test_identify_nonexistent_user_as_not_super_admin(self, db_session):
        """测试不存在的用户不是超级管理员"""
        fake_user_id = str(uuid.uuid4())
        
        result = is_super_admin(fake_user_id, db_session)
        
        assert result is False
    
    def test_is_super_admin_api_endpoint(self, super_admin_user):
        """测试超级管理员检查API端点"""
        user_id = str(super_admin_user.id)
        
        response = client.get(f"/api/v1/users/{user_id}/is-super-admin")
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert data["is_super_admin"] is True
    
    def test_is_super_admin_api_endpoint_for_regular_user(self, regular_user):
        """测试普通用户的超级管理员检查API端点"""
        user_id = str(regular_user.id)
        
        response = client.get(f"/api/v1/users/{user_id}/is-super-admin")
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert data["is_super_admin"] is False


class TestSuperAdminPermissionBypass:
    """测试超级管理员权限检查跳过"""
    
    def test_super_admin_has_permission_without_explicit_grant(self, super_admin_user, test_permission, db_session):
        """
        测试超级管理员拥有权限，即使没有显式授予
        
        验证需求：6.2, 6.3
        属性 25：超级管理员无限权限
        """
        user_id = str(super_admin_user.id)
        permission_name = test_permission.name
        
        # 超级管理员没有被显式授予这个权限
        # 但check_permission应该返回True
        result = check_permission(user_id, permission_name, db_session)
        
        assert result is True
    
    def test_super_admin_has_any_permission(self, super_admin_user, db_session):
        """测试超级管理员拥有任意权限"""
        user_id = str(super_admin_user.id)
        
        # 测试多个不存在的权限
        test_permissions = [
            "user:create",
            "user:delete",
            "role:update",
            "organization:delete",
            "subscription:create",
            "audit:read",
            "config:update",
            "nonexistent:permission"
        ]
        
        for perm_name in test_permissions:
            result = check_permission(user_id, perm_name, db_session)
            assert result is True, f"超级管理员应该拥有权限: {perm_name}"
    
    def test_regular_user_does_not_have_permission_without_grant(self, regular_user, test_permission, db_session):
        """测试普通用户没有未授予的权限"""
        user_id = str(regular_user.id)
        permission_name = test_permission.name
        
        # 普通用户没有被授予这个权限
        result = check_permission(user_id, permission_name, db_session)
        
        assert result is False
    
    def test_super_admin_check_permission_api(self, super_admin_user):
        """测试超级管理员通过API检查权限"""
        user_id = str(super_admin_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/check-permission",
            params={"permission_name": "any:permission"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["has_permission"] is True
    
    def test_regular_user_check_permission_api(self, regular_user):
        """测试普通用户通过API检查权限"""
        user_id = str(regular_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/check-permission",
            params={"permission_name": "any:permission"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["has_permission"] is False


class TestSuperAdminPermissionCaching:
    """测试超级管理员权限缓存"""
    
    def test_super_admin_status_is_cached(self, super_admin_user, db_session):
        """测试超级管理员状态被缓存"""
        user_id = str(super_admin_user.id)
        
        # 第一次调用（缓存未命中）
        result1 = is_super_admin(user_id, db_session)
        assert result1 is True
        
        # 第二次调用（应该从缓存读取）
        result2 = is_super_admin(user_id, db_session)
        assert result2 is True
    
    def test_permission_check_uses_super_admin_cache(self, super_admin_user, db_session):
        """测试权限检查使用超级管理员缓存"""
        user_id = str(super_admin_user.id)
        
        # 多次检查不同权限
        permissions = ["user:create", "role:delete", "org:update"]
        
        for perm in permissions:
            result = check_permission(user_id, perm, db_session)
            assert result is True


class TestSuperAdminWithExplicitPermissions:
    """测试超级管理员同时拥有显式权限"""
    
    def test_super_admin_with_explicit_permission_still_bypasses_check(
        self, super_admin_user, super_admin_role, test_permission, db_session
    ):
        """测试超级管理员即使有显式权限也跳过检查"""
        user_id = str(super_admin_user.id)
        
        # 为超级管理员角色显式添加权限
        role_perm = RolePermission(
            role_id=super_admin_role.id,
            permission_id=test_permission.id
        )
        db_session.add(role_perm)
        db_session.commit()
        
        # 检查权限（应该通过超级管理员检查，而不是权限检查）
        result = check_permission(user_id, test_permission.name, db_session)
        assert result is True
        
        # 检查其他未授予的权限（也应该通过）
        result2 = check_permission(user_id, "other:permission", db_session)
        assert result2 is True


class TestEdgeCases:
    """测试边界情况"""
    
    def test_invalid_user_id_format(self, db_session):
        """测试无效的用户ID格式"""
        result = is_super_admin("invalid-uuid", db_session)
        assert result is False
        
        result2 = check_permission("invalid-uuid", "any:permission", db_session)
        assert result2 is False
    
    def test_empty_user_id(self, db_session):
        """测试空用户ID"""
        result = is_super_admin("", db_session)
        assert result is False
        
        result2 = check_permission("", "any:permission", db_session)
        assert result2 is False
    
    def test_super_admin_role_does_not_exist(self, db_session):
        """测试超级管理员角色不存在的情况"""
        user = User(
            id=uuid.uuid4(),
            username="testuser",
            email="test@example.com",
            password_hash="hashed_password",
            status="active"
        )
        db_session.add(user)
        db_session.commit()
        
        user_id = str(user.id)
        
        # 没有创建super_admin角色
        result = is_super_admin(user_id, db_session)
        assert result is False


class TestSuperAdminOperations:
    """测试超级管理员操作"""
    
    def test_super_admin_can_perform_all_operations(self, super_admin_user, db_session):
        """
        测试超级管理员可以执行所有操作
        
        验证需求：6.2, 6.3
        属性 25：超级管理员无限权限
        """
        user_id = str(super_admin_user.id)
        
        # 定义所有可能的操作权限
        all_operations = [
            # 用户管理
            "user:create", "user:read", "user:update", "user:delete",
            # 角色管理
            "role:create", "role:read", "role:update", "role:delete",
            # 权限管理
            "permission:create", "permission:read", "permission:update", "permission:delete",
            # 组织管理
            "organization:create", "organization:read", "organization:update", "organization:delete",
            # 订阅管理
            "subscription:create", "subscription:read", "subscription:update", "subscription:delete",
            # 审计日志
            "audit:read",
            # 系统配置
            "config:read", "config:update",
        ]
        
        # 超级管理员应该拥有所有权限
        for operation in all_operations:
            result = check_permission(user_id, operation, db_session)
            assert result is True, f"超级管理员应该拥有权限: {operation}"
    
    def test_regular_user_cannot_perform_admin_operations(self, regular_user, db_session):
        """测试普通用户不能执行管理员操作"""
        user_id = str(regular_user.id)
        
        admin_operations = [
            "user:delete",
            "role:create",
            "permission:delete",
            "organization:delete",
            "config:update"
        ]
        
        # 普通用户不应该拥有这些权限
        for operation in admin_operations:
            result = check_permission(user_id, operation, db_session)
            assert result is False, f"普通用户不应该拥有权限: {operation}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
