"""
权限服务属性测试

Feature: unified-auth-platform, Properties 18-20: 权限验证和缓存

验证需求：4.3, 4.4, 4.5
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base, get_db
from shared.models.permission import Role, Permission, UserRole, RolePermission
from shared.models.user import User
from services.permission.main import app
import uuid

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_permission_properties.db"
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

# Hypothesis策略
role_names = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
    min_size=3,
    max_size=50
)

permission_names = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
    min_size=3,
    max_size=50
)

resource_names = st.sampled_from(['user', 'role', 'permission', 'organization', 'subscription'])
action_names = st.sampled_from(['create', 'read', 'update', 'delete', 'list'])

@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestProperty18UserRolePermissionInheritance:
    """
    属性 18：用户角色权限继承
    
    对于任意用户和角色，当管理员为用户分配角色时，
    用户应该自动获得该角色的所有权限。
    
    **验证需求：4.3**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        role_name=role_names,
        num_permissions=st.integers(min_value=1, max_value=5)
    )
    def test_user_inherits_all_role_permissions(self, role_name, num_permissions):
        """
        属性测试：用户从角色继承所有权限
        
        给定：一个角色和多个权限
        当：为角色分配权限，然后为用户分配该角色
        则：用户应该拥有该角色的所有权限
        """
        # 获取数据库会话
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建角色
            role = Role(
                id=uuid.uuid4(),
                name=f"{role_name}_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            role_id = str(role.id)
            
            # 创建权限并分配给角色
            created_permissions = []
            for i in range(num_permissions):
                perm = Permission(
                    id=uuid.uuid4(),
                    name=f"test:perm_{uuid.uuid4().hex[:8]}",
                    resource="test",
                    action=f"action_{i}",
                    description=f"Test permission {i}"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
                created_permissions.append(perm)
                
                # 分配权限给角色
                role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
                db_session.add(role_perm)
            
            db_session.commit()
            
            # 为用户分配角色
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 查询用户权限
            response = client.get(f"/api/v1/users/{user_id}/permissions")
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            assert "permissions" in data
            user_permissions = data["permissions"]
            
            # 用户应该拥有角色的所有权限
            assert len(user_permissions) == num_permissions
            
            # 验证每个权限都来自角色
            permission_ids = {perm.id for perm in created_permissions}
            for user_perm in user_permissions:
                assert user_perm["source"] == "role"
                assert uuid.UUID(user_perm["id"]) in permission_ids
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        num_roles=st.integers(min_value=2, max_value=4),
        perms_per_role=st.integers(min_value=1, max_value=3)
    )
    def test_user_inherits_permissions_from_multiple_roles(self, num_roles, perms_per_role):
        """
        属性测试：用户从多个角色继承权限
        
        给定：多个角色，每个角色有多个权限
        当：为用户分配所有角色
        则：用户应该拥有所有角色的所有权限
        """
        # 获取数据库会话
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            total_permissions = 0
            all_permission_ids = set()
            
            # 创建多个角色，每个角色有多个权限
            for role_idx in range(num_roles):
                role = Role(
                    id=uuid.uuid4(),
                    name=f"role_{uuid.uuid4().hex[:8]}",
                    description=f"Test role {role_idx}"
                )
                db_session.add(role)
                db_session.commit()
                db_session.refresh(role)
                
                # 为角色创建权限
                for perm_idx in range(perms_per_role):
                    perm = Permission(
                        id=uuid.uuid4(),
                        name=f"test:perm_{uuid.uuid4().hex[:8]}",
                        resource="test",
                        action=f"action_{role_idx}_{perm_idx}",
                        description=f"Test permission {role_idx}_{perm_idx}"
                    )
                    db_session.add(perm)
                    db_session.commit()
                    db_session.refresh(perm)
                    all_permission_ids.add(perm.id)
                    
                    # 分配权限给角色
                    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
                    db_session.add(role_perm)
                    total_permissions += 1
                
                db_session.commit()
                
                # 为用户分配角色
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db_session.add(user_role)
            
            db_session.commit()
            
            # 查询用户权限
            response = client.get(f"/api/v1/users/{user_id}/permissions")
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            user_permissions = data["permissions"]
            
            # 用户应该拥有所有角色的所有权限
            assert len(user_permissions) == total_permissions
            
            # 验证所有权限都被继承
            inherited_permission_ids = {uuid.UUID(perm["id"]) for perm in user_permissions}
            assert inherited_permission_ids == all_permission_ids
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(role_name=role_names)
    def test_user_without_role_has_no_permissions(self, role_name):
        """
        属性测试：没有角色的用户没有权限
        
        给定：一个没有分配任何角色的用户
        当：查询用户权限
        则：用户应该没有任何权限
        """
        # 获取数据库会话
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户（不分配角色）
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 查询用户权限
            response = client.get(f"/api/v1/users/{user_id}/permissions")
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            assert "permissions" in data
            assert len(data["permissions"]) == 0
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        role_name=role_names,
        num_permissions=st.integers(min_value=1, max_value=5)
    )
    def test_removing_role_removes_permissions(self, role_name, num_permissions):
        """
        属性测试：移除角色后权限也被移除
        
        给定：用户有一个角色和相关权限
        当：移除用户的角色
        则：用户应该失去该角色的所有权限
        """
        # 获取数据库会话
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建角色和权限
            role = Role(
                id=uuid.uuid4(),
                name=f"{role_name}_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            role_id = str(role.id)
            
            for i in range(num_permissions):
                perm = Permission(
                    id=uuid.uuid4(),
                    name=f"test:perm_{uuid.uuid4().hex[:8]}",
                    resource="test",
                    action=f"action_{i}",
                    description=f"Test permission {i}"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
                
                role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
                db_session.add(role_perm)
            
            db_session.commit()
            
            # 为用户分配角色
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 验证用户有权限
            response1 = client.get(f"/api/v1/users/{user_id}/permissions")
            assert response1.status_code == 200
            assert len(response1.json()["permissions"]) == num_permissions
            
            # 移除角色
            remove_response = client.delete(f"/api/v1/users/{user_id}/roles/{role_id}")
            assert remove_response.status_code == 200
            
            # 验证用户失去权限
            response2 = client.get(f"/api/v1/users/{user_id}/permissions")
            assert response2.status_code == 200
            assert len(response2.json()["permissions"]) == 0
        finally:
            db_session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



class TestProperty19PermissionVerificationCorrectness:
    """
    属性 19：权限验证正确性
    
    对于任意用户和资源访问请求，系统应该正确验证用户是否拥有所需权限，
    有权限时允许访问，无权限时拒绝访问。
    
    **验证需求：4.4**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        resource=resource_names,
        action=action_names
    )
    def test_user_with_permission_can_access(self, resource, action):
        """
        属性测试：拥有权限的用户可以访问
        
        给定：用户拥有特定权限
        当：检查该权限
        则：应该返回True（允许访问）
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建角色
            role = Role(
                id=uuid.uuid4(),
                name=f"role_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            
            # 创建权限
            permission_name = f"{resource}:{action}"
            # Check if permission already exists
            existing_perm = db_session.query(Permission).filter(Permission.name == permission_name).first()
            if existing_perm:
                perm = existing_perm
            else:
                perm = Permission(
                    id=uuid.uuid4(),
                    name=permission_name,
                    resource=resource,
                    action=action,
                    description=f"Test permission for {resource}:{action}"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
            
            # 分配权限给角色
            role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
            db_session.add(role_perm)
            db_session.commit()
            
            # 分配角色给用户
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 检查权限
            response = client.post(
                f"/api/v1/users/{user_id}/check-permission",
                params={"permission_name": permission_name}
            )
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            assert data["has_permission"] is True
            assert data["permission"] == permission_name
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        resource=resource_names,
        action=action_names
    )
    def test_user_without_permission_cannot_access(self, resource, action):
        """
        属性测试：没有权限的用户不能访问
        
        给定：用户没有特定权限
        当：检查该权限
        则：应该返回False（拒绝访问）
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户（不分配任何权限）
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 检查权限（用户没有任何权限）
            permission_name = f"{resource}:{action}"
            response = client.post(
                f"/api/v1/users/{user_id}/check-permission",
                params={"permission_name": permission_name}
            )
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            assert data["has_permission"] is False
            assert data["permission"] == permission_name
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        has_resource=resource_names,
        has_action=action_names,
        check_resource=resource_names,
        check_action=action_names
    )
    def test_permission_check_is_specific(self, has_resource, has_action, check_resource, check_action):
        """
        属性测试：权限检查是精确的
        
        给定：用户拥有权限A
        当：检查权限B
        则：只有当A==B时返回True，否则返回False
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建角色
            role = Role(
                id=uuid.uuid4(),
                name=f"role_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            
            # 创建并分配权限A
            has_permission_name = f"{has_resource}:{has_action}"
            # Check if permission already exists
            existing_perm = db_session.query(Permission).filter(Permission.name == has_permission_name).first()
            if existing_perm:
                perm = existing_perm
            else:
                perm = Permission(
                    id=uuid.uuid4(),
                    name=has_permission_name,
                    resource=has_resource,
                    action=has_action,
                    description=f"Test permission"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
            
            role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
            db_session.add(role_perm)
            db_session.commit()
            
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 检查权限B
            check_permission_name = f"{check_resource}:{check_action}"
            response = client.post(
                f"/api/v1/users/{user_id}/check-permission",
                params={"permission_name": check_permission_name}
            )
            
            # 验证
            assert response.status_code == 200
            data = response.json()
            
            # 只有当权限完全匹配时才应该返回True
            expected_result = (has_permission_name == check_permission_name)
            assert data["has_permission"] == expected_result
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        resource=resource_names,
        action=action_names,
        num_roles=st.integers(min_value=2, max_value=4)
    )
    def test_permission_from_any_role_grants_access(self, resource, action, num_roles):
        """
        属性测试：来自任一角色的权限都能授予访问
        
        给定：用户有多个角色，其中一个角色有所需权限
        当：检查该权限
        则：应该返回True
        """
        db_session = TestingSessionLocal()
        try:
            # 创建测试用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建权限
            permission_name = f"{resource}:{action}"
            # Check if permission already exists
            existing_perm = db_session.query(Permission).filter(Permission.name == permission_name).first()
            if existing_perm:
                perm = existing_perm
            else:
                perm = Permission(
                    id=uuid.uuid4(),
                    name=permission_name,
                    resource=resource,
                    action=action,
                    description=f"Test permission"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
            
            # 创建多个角色，只有一个角色有该权限
            import random
            role_with_permission_idx = random.randint(0, num_roles - 1)
            
            for i in range(num_roles):
                role = Role(
                    id=uuid.uuid4(),
                    name=f"role_{uuid.uuid4().hex[:8]}",
                    description=f"Test role {i}"
                )
                db_session.add(role)
                db_session.commit()
                db_session.refresh(role)
                
                # 只为选中的角色分配权限
                if i == role_with_permission_idx:
                    role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
                    db_session.add(role_perm)
                    db_session.commit()
                
                # 为用户分配所有角色
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db_session.add(user_role)
            
            db_session.commit()
            
            # 检查权限
            response = client.post(
                f"/api/v1/users/{user_id}/check-permission",
                params={"permission_name": permission_name}
            )
            
            # 验证：即使只有一个角色有该权限，用户也应该能访问
            assert response.status_code == 200
            data = response.json()
            assert data["has_permission"] is True
        finally:
            db_session.close()



class TestProperty20RolePermissionUpdateImmediateEffect:
    """
    属性 20：角色权限更新即时生效
    
    对于任意角色，当管理员修改该角色的权限时，
    所有拥有该角色的用户的权限应该立即更新（通过缓存失效机制）。
    
    **验证需求：4.5**
    """
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        resource=resource_names,
        action=action_names,
        num_users=st.integers(min_value=1, max_value=3)
    )
    def test_adding_permission_to_role_updates_all_users(self, resource, action, num_users):
        """
        属性测试：为角色添加权限后，所有用户立即获得该权限
        
        给定：多个用户拥有同一角色
        当：为该角色添加新权限
        则：所有用户应该立即拥有该新权限
        """
        db_session = TestingSessionLocal()
        try:
            # 创建角色
            role = Role(
                id=uuid.uuid4(),
                name=f"role_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            role_id = str(role.id)
            
            # 创建多个用户并分配角色
            user_ids = []
            for i in range(num_users):
                user = User(
                    id=uuid.uuid4(),
                    username=f"testuser_{uuid.uuid4().hex[:8]}",
                    email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                    password_hash="hashed_password",
                    status="active"
                )
                db_session.add(user)
                db_session.commit()
                db_session.refresh(user)
                user_ids.append(str(user.id))
                
                # 分配角色给用户
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db_session.add(user_role)
            
            db_session.commit()
            
            # 验证用户初始没有权限
            for user_id in user_ids:
                response = client.get(f"/api/v1/users/{user_id}/permissions")
                assert response.status_code == 200
                assert len(response.json()["permissions"]) == 0
            
            # 创建权限
            permission_name = f"{resource}:{action}"
            existing_perm = db_session.query(Permission).filter(Permission.name == permission_name).first()
            if existing_perm:
                perm = existing_perm
            else:
                perm = Permission(
                    id=uuid.uuid4(),
                    name=permission_name,
                    resource=resource,
                    action=action,
                    description=f"Test permission"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
            
            # 为角色添加权限
            response = client.post(
                f"/api/v1/roles/{role_id}/permissions",
                json=[str(perm.id)]
            )
            assert response.status_code == 200
            
            # 验证所有用户立即拥有该权限
            for user_id in user_ids:
                response = client.get(f"/api/v1/users/{user_id}/permissions")
                assert response.status_code == 200
                permissions = response.json()["permissions"]
                assert len(permissions) == 1
                assert permissions[0]["name"] == permission_name
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        resource=resource_names,
        action=action_names,
        num_users=st.integers(min_value=1, max_value=3)
    )
    def test_removing_permission_from_role_updates_all_users(self, resource, action, num_users):
        """
        属性测试：从角色移除权限后，所有用户立即失去该权限
        
        给定：多个用户拥有同一角色，该角色有某个权限
        当：从该角色移除该权限
        则：所有用户应该立即失去该权限
        """
        db_session = TestingSessionLocal()
        try:
            # 创建角色
            role = Role(
                id=uuid.uuid4(),
                name=f"role_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            role_id = str(role.id)
            
            # 创建权限
            permission_name = f"{resource}:{action}"
            existing_perm = db_session.query(Permission).filter(Permission.name == permission_name).first()
            if existing_perm:
                perm = existing_perm
            else:
                perm = Permission(
                    id=uuid.uuid4(),
                    name=permission_name,
                    resource=resource,
                    action=action,
                    description=f"Test permission"
                )
                db_session.add(perm)
                db_session.commit()
                db_session.refresh(perm)
            
            # 为角色分配权限
            role_perm = RolePermission(role_id=role.id, permission_id=perm.id)
            db_session.add(role_perm)
            db_session.commit()
            
            # 创建多个用户并分配角色
            user_ids = []
            for i in range(num_users):
                user = User(
                    id=uuid.uuid4(),
                    username=f"testuser_{uuid.uuid4().hex[:8]}",
                    email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                    password_hash="hashed_password",
                    status="active"
                )
                db_session.add(user)
                db_session.commit()
                db_session.refresh(user)
                user_ids.append(str(user.id))
                
                # 分配角色给用户
                user_role = UserRole(user_id=user.id, role_id=role.id)
                db_session.add(user_role)
            
            db_session.commit()
            
            # 验证用户初始拥有权限
            for user_id in user_ids:
                response = client.get(f"/api/v1/users/{user_id}/permissions")
                assert response.status_code == 200
                permissions = response.json()["permissions"]
                assert len(permissions) == 1
                assert permissions[0]["name"] == permission_name
            
            # 从角色移除权限
            response = client.delete(f"/api/v1/roles/{role_id}/permissions/{perm.id}")
            assert response.status_code == 200
            
            # 验证所有用户立即失去该权限
            for user_id in user_ids:
                response = client.get(f"/api/v1/users/{user_id}/permissions")
                assert response.status_code == 200
                permissions = response.json()["permissions"]
                assert len(permissions) == 0
        finally:
            db_session.close()
    
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    @given(
        resource1=resource_names,
        action1=action_names,
        resource2=resource_names,
        action2=action_names
    )
    def test_cache_invalidation_is_immediate(self, resource1, action1, resource2, action2):
        """
        属性测试：缓存失效是即时的
        
        给定：用户拥有角色A的权限，权限已被缓存
        当：修改角色A的权限
        则：用户的权限缓存应该立即失效，下次查询返回新权限
        """
        db_session = TestingSessionLocal()
        try:
            # 创建用户
            user = User(
                id=uuid.uuid4(),
                username=f"testuser_{uuid.uuid4().hex[:8]}",
                email=f"test_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(user)
            db_session.commit()
            db_session.refresh(user)
            user_id = str(user.id)
            
            # 创建角色
            role = Role(
                id=uuid.uuid4(),
                name=f"role_{uuid.uuid4().hex[:8]}",
                description="Test role"
            )
            db_session.add(role)
            db_session.commit()
            db_session.refresh(role)
            role_id = str(role.id)
            
            # 创建第一个权限
            perm1_name = f"{resource1}:{action1}"
            existing_perm1 = db_session.query(Permission).filter(Permission.name == perm1_name).first()
            if existing_perm1:
                perm1 = existing_perm1
            else:
                perm1 = Permission(
                    id=uuid.uuid4(),
                    name=perm1_name,
                    resource=resource1,
                    action=action1,
                    description=f"Test permission 1"
                )
                db_session.add(perm1)
                db_session.commit()
                db_session.refresh(perm1)
            
            # 为角色分配第一个权限
            role_perm1 = RolePermission(role_id=role.id, permission_id=perm1.id)
            db_session.add(role_perm1)
            db_session.commit()
            
            # 为用户分配角色
            user_role = UserRole(user_id=user.id, role_id=role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 第一次查询权限（会被缓存）
            response1 = client.get(f"/api/v1/users/{user_id}/permissions")
            assert response1.status_code == 200
            perms1 = response1.json()["permissions"]
            assert len(perms1) == 1
            assert perms1[0]["name"] == perm1_name
            
            # 创建第二个权限
            perm2_name = f"{resource2}:{action2}"
            if perm2_name != perm1_name:  # 只有当权限不同时才添加
                existing_perm2 = db_session.query(Permission).filter(Permission.name == perm2_name).first()
                if existing_perm2:
                    perm2 = existing_perm2
                else:
                    perm2 = Permission(
                        id=uuid.uuid4(),
                        name=perm2_name,
                        resource=resource2,
                        action=action2,
                        description=f"Test permission 2"
                    )
                    db_session.add(perm2)
                    db_session.commit()
                    db_session.refresh(perm2)
                
                # 为角色添加第二个权限
                response_add = client.post(
                    f"/api/v1/roles/{role_id}/permissions",
                    json=[str(perm2.id)]
                )
                assert response_add.status_code == 200
                
                # 立即查询权限（缓存应该已失效）
                response2 = client.get(f"/api/v1/users/{user_id}/permissions")
                assert response2.status_code == 200
                perms2 = response2.json()["permissions"]
                
                # 用户应该拥有两个权限
                assert len(perms2) == 2
                perm_names = {p["name"] for p in perms2}
                assert perm1_name in perm_names
                assert perm2_name in perm_names
        finally:
            db_session.close()
