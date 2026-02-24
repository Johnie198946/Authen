"""
测试用户角色关联功能
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
from services.permission.main import app
import uuid

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_user_roles.db"
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

@pytest.fixture
def db_session():
    """提供数据库会话"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def test_user(db_session):
    """创建测试用户"""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture
def test_roles(db_session):
    """创建测试角色"""
    roles = []
    for i in range(3):
        role = Role(
            id=uuid.uuid4(),
            name=f"test_role_{i}",
            description=f"Test Role {i}"
        )
        db_session.add(role)
        roles.append(role)
    db_session.commit()
    for role in roles:
        db_session.refresh(role)
    return roles

@pytest.fixture
def test_permissions(db_session):
    """创建测试权限"""
    permissions = []
    for i in range(3):
        perm = Permission(
            id=uuid.uuid4(),
            name=f"test:permission_{i}",
            resource="test",
            action=f"action_{i}",
            description=f"Test Permission {i}"
        )
        db_session.add(perm)
        permissions.append(perm)
    db_session.commit()
    for perm in permissions:
        db_session.refresh(perm)
    return permissions


class TestUserRoleAssignment:
    """测试用户角色分配"""
    
    def test_assign_single_role_to_user(self, test_user, test_roles):
        """测试为用户分配单个角色"""
        role_id = str(test_roles[0].id)
        user_id = str(test_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": [role_id]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["assigned_count"] == 1
        assert "成功分配" in data["message"]
    
    def test_assign_multiple_roles_to_user(self, test_user, test_roles):
        """测试为用户分配多个角色"""
        role_ids = [str(role.id) for role in test_roles]
        user_id = str(test_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": role_ids}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["assigned_count"] == 3
    
    def test_assign_duplicate_role_to_user(self, test_user, test_roles, db_session):
        """测试重复分配角色（应该忽略已存在的）"""
        role_id = str(test_roles[0].id)
        user_id = str(test_user.id)
        
        # 第一次分配
        response1 = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": [role_id]}
        )
        assert response1.status_code == 200
        assert response1.json()["assigned_count"] == 1
        
        # 第二次分配相同角色
        response2 = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": [role_id]}
        )
        assert response2.status_code == 200
        assert response2.json()["assigned_count"] == 0  # 没有新分配
    
    def test_assign_nonexistent_role_to_user(self, test_user):
        """测试分配不存在的角色"""
        fake_role_id = str(uuid.uuid4())
        user_id = str(test_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": [fake_role_id]}
        )
        
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]


class TestUserRoleQuery:
    """测试用户角色查询"""
    
    def test_get_user_roles_empty(self, test_user):
        """测试查询没有角色的用户"""
        user_id = str(test_user.id)
        
        response = client.get(f"/api/v1/users/{user_id}/roles")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_get_user_roles_with_roles(self, test_user, test_roles, db_session):
        """测试查询有角色的用户"""
        user_id = str(test_user.id)
        
        # 分配角色
        for role in test_roles[:2]:
            user_role = UserRole(user_id=test_user.id, role_id=role.id)
            db_session.add(user_role)
        db_session.commit()
        
        response = client.get(f"/api/v1/users/{user_id}/roles")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        # 验证返回的数据结构
        for item in data:
            assert "user_id" in item
            assert "role_id" in item
            assert "role_name" in item
            assert "role_description" in item
            assert item["user_id"] == user_id
    
    def test_get_user_roles_returns_correct_info(self, test_user, test_roles, db_session):
        """测试查询返回正确的角色信息"""
        user_id = str(test_user.id)
        role = test_roles[0]
        
        # 分配角色
        user_role = UserRole(user_id=test_user.id, role_id=role.id)
        db_session.add(user_role)
        db_session.commit()
        
        response = client.get(f"/api/v1/users/{user_id}/roles")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["role_name"] == role.name
        assert data[0]["role_description"] == role.description


class TestUserRoleRemoval:
    """测试用户角色移除"""
    
    def test_remove_role_from_user(self, test_user, test_roles, db_session):
        """测试移除用户的角色"""
        user_id = str(test_user.id)
        role_id = str(test_roles[0].id)
        
        # 先分配角色
        user_role = UserRole(user_id=test_user.id, role_id=test_roles[0].id)
        db_session.add(user_role)
        db_session.commit()
        
        # 移除角色
        response = client.delete(f"/api/v1/users/{user_id}/roles/{role_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "已移除" in data["message"]
        
        # 验证角色已被移除
        verify_response = client.get(f"/api/v1/users/{user_id}/roles")
        assert len(verify_response.json()) == 0
    
    def test_remove_nonexistent_role_from_user(self, test_user, test_roles):
        """测试移除不存在的用户角色关联"""
        user_id = str(test_user.id)
        role_id = str(test_roles[0].id)
        
        # 没有分配角色，直接尝试移除
        response = client.delete(f"/api/v1/users/{user_id}/roles/{role_id}")
        
        assert response.status_code == 404
        assert "不存在" in response.json()["detail"]
    
    def test_remove_one_role_keeps_others(self, test_user, test_roles, db_session):
        """测试移除一个角色不影响其他角色"""
        user_id = str(test_user.id)
        
        # 分配多个角色
        for role in test_roles:
            user_role = UserRole(user_id=test_user.id, role_id=role.id)
            db_session.add(user_role)
        db_session.commit()
        
        # 移除第一个角色
        role_id_to_remove = str(test_roles[0].id)
        response = client.delete(f"/api/v1/users/{user_id}/roles/{role_id_to_remove}")
        assert response.status_code == 200
        
        # 验证其他角色仍然存在
        verify_response = client.get(f"/api/v1/users/{user_id}/roles")
        remaining_roles = verify_response.json()
        assert len(remaining_roles) == 2
        remaining_role_ids = [r["role_id"] for r in remaining_roles]
        assert role_id_to_remove not in remaining_role_ids


class TestUserRolePermissionInheritance:
    """测试用户通过角色继承权限"""
    
    def test_user_inherits_permissions_from_role(self, test_user, test_roles, test_permissions, db_session):
        """测试用户从角色继承权限"""
        user_id = str(test_user.id)
        role = test_roles[0]
        
        # 为角色分配权限
        for perm in test_permissions:
            role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
            db_session.add(role_perm)
        db_session.commit()
        
        # 为用户分配角色
        user_role = UserRole(user_id=test_user.id, role_id=role.id)
        db_session.add(user_role)
        db_session.commit()
        
        # 查询用户权限
        response = client.get(f"/api/v1/users/{user_id}/permissions")
        
        assert response.status_code == 200
        data = response.json()
        assert "permissions" in data
        assert len(data["permissions"]) == 3
        
        # 验证权限来源
        for perm in data["permissions"]:
            assert perm["source"] == "role"
    
    def test_user_inherits_permissions_from_multiple_roles(self, test_user, test_roles, test_permissions, db_session):
        """测试用户从多个角色继承权限"""
        user_id = str(test_user.id)
        
        # 为第一个角色分配前两个权限
        for perm in test_permissions[:2]:
            role_perm = RolePermission(role_id=test_roles[0].id, permission_id=perm.id)
            db_session.add(role_perm)
        
        # 为第二个角色分配第三个权限
        role_perm = RolePermission(role_id=test_roles[1].id, permission_id=test_permissions[2].id)
        db_session.add(role_perm)
        db_session.commit()
        
        # 为用户分配两个角色
        for role in test_roles[:2]:
            user_role = UserRole(user_id=test_user.id, role_id=role.id)
            db_session.add(user_role)
        db_session.commit()
        
        # 查询用户权限
        response = client.get(f"/api/v1/users/{user_id}/permissions")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["permissions"]) == 3


class TestDataValidation:
    """测试数据验证"""
    
    def test_assign_roles_with_empty_list(self, test_user):
        """测试使用空列表分配角色"""
        user_id = str(test_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": []}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["assigned_count"] == 0
    
    def test_assign_roles_with_invalid_uuid(self, test_user):
        """测试使用无效的UUID"""
        user_id = str(test_user.id)
        
        response = client.post(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": ["invalid-uuid"]}
        )
        
        # 应该返回404（角色不存在）或422（UUID格式错误）
        assert response.status_code in [404, 422, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
