"""
属性测试：超级管理员权限

属性 25：超级管理员无限权限
验证需求：6.2, 6.3

对于超级管理员账号，执行任何操作时都应该跳过权限检查，
且所有操作都应该成功（除非是系统错误）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base
from shared.models.permission import Role, Permission, UserRole, RolePermission
from shared.models.user import User
from services.permission.main import is_super_admin, check_permission
import uuid
from unittest.mock import MagicMock, patch

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_super_admin_properties.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Hypothesis配置
settings.register_profile("default", 
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture]
)
settings.load_profile("default")


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


def get_db_session():
    """获取数据库会话"""
    return TestingSessionLocal()


def create_super_admin_role(db_session):
    """创建超级管理员角色"""
    # 检查是否已存在
    existing = db_session.query(Role).filter(Role.name == "super_admin").first()
    if existing:
        return existing
    
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


def create_regular_role(db_session, name=None):
    """创建普通角色"""
    if name is None:
        name = f"regular_user_{uuid.uuid4().hex[:8]}"
    role = Role(
        id=uuid.uuid4(),
        name=name,
        description="普通用户",
        is_system_role=False
    )
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


# Hypothesis策略：生成权限名称
@st.composite
def permission_names(draw):
    """
    生成权限名称策略
    格式：resource:action
    """
    resources = st.sampled_from([
        "user", "role", "permission", "organization", 
        "subscription", "audit", "config", "system",
        "report", "notification", "template", "log"
    ])
    actions = st.sampled_from([
        "create", "read", "update", "delete", 
        "list", "export", "import", "execute",
        "approve", "reject", "publish", "archive"
    ])
    
    resource = draw(resources)
    action = draw(actions)
    return f"{resource}:{action}"


# Hypothesis策略：生成用户名
def usernames():
    """生成用户名策略"""
    return st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), min_codepoint=65, max_codepoint=122),
        min_size=5,
        max_size=20
    ).filter(lambda x: x.isalnum()).map(lambda x: f"{x}_{uuid.uuid4().hex[:8]}")


# Hypothesis策略：生成邮箱
def emails():
    """生成邮箱策略"""
    return st.emails().map(lambda x: f"{uuid.uuid4().hex[:8]}_{x}")


class TestSuperAdminUnlimitedPermissions:
    """
    属性 25：超级管理员无限权限
    
    **Validates: Requirements 6.2, 6.3**
    
    对于超级管理员账号，执行任何操作时都应该跳过权限检查，
    且所有操作都应该成功（除非是系统错误）。
    """
    
    @given(permission_name=permission_names())
    def test_super_admin_has_any_permission(self, permission_name):
        """
        属性：超级管理员拥有任意权限
        
        对于任意权限名称，超级管理员都应该拥有该权限，
        即使该权限未在数据库中定义或未显式授予。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建超级管理员用户（使用唯一的用户名和邮箱）
            unique_id = uuid.uuid4().hex[:8]
            super_admin = User(
                id=uuid.uuid4(),
                username=f"admin_{unique_id}",
                email=f"admin_{unique_id}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 检查权限
            user_id = str(super_admin.id)
            has_permission = check_permission(user_id, permission_name, db_session)
            
            # 断言：超级管理员应该拥有任意权限
            assert has_permission is True, (
                f"超级管理员应该拥有权限 '{permission_name}'，但检查返回 False"
            )
        finally:
            db_session.close()
    
    @given(
        permission_name=permission_names(),
        username=usernames(),
        email=emails()
    )
    def test_super_admin_bypasses_permission_check_for_any_user(
        self,
        permission_name,
        username,
        email
    ):
        """
        属性：超级管理员跳过权限检查（不同用户）
        
        对于任意用户名和邮箱创建的超级管理员，
        都应该拥有任意权限，验证超级管理员检查不依赖于特定用户属性。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建具有随机属性的超级管理员
            super_admin = User(
                id=uuid.uuid4(),
                username=username,
                email=email,
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 检查权限
            user_id = str(super_admin.id)
            has_permission = check_permission(user_id, permission_name, db_session)
            
            # 断言：任何超级管理员都应该拥有任意权限
            assert has_permission is True, (
                f"用户 '{username}' 作为超级管理员应该拥有权限 '{permission_name}'"
            )
        finally:
            db_session.close()
    
    @given(
        permission_names_list=st.lists(permission_names(), min_size=1, max_size=20, unique=True)
    )
    def test_super_admin_has_multiple_permissions(self, permission_names_list):
        """
        属性：超级管理员拥有多个权限
        
        对于任意权限列表，超级管理员都应该同时拥有所有这些权限。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建超级管理员（使用唯一ID）
            unique_id = uuid.uuid4().hex[:8]
            super_admin = User(
                id=uuid.uuid4(),
                username=f"admin_{unique_id}",
                email=f"admin_{unique_id}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            user_id = str(super_admin.id)
            
            # 检查所有权限
            for permission_name in permission_names_list:
                has_permission = check_permission(user_id, permission_name, db_session)
                assert has_permission is True, (
                    f"超级管理员应该拥有权限 '{permission_name}'"
                )
        finally:
            db_session.close()
    
    @given(permission_name=permission_names())
    def test_regular_user_does_not_have_arbitrary_permission(self, permission_name):
        """
        属性：普通用户不拥有任意权限（对比测试）
        
        对于任意权限，普通用户（非超级管理员）不应该自动拥有该权限，
        除非显式授予。这验证了超级管理员的特殊性。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建普通角色
            regular_role = create_regular_role(db_session)
            
            # 创建普通用户
            regular_user = User(
                id=uuid.uuid4(),
                username=f"regular_{uuid.uuid4().hex[:8]}",
                email=f"regular_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(regular_user)
            db_session.commit()
            db_session.refresh(regular_user)
            
            # 分配普通角色
            user_role = UserRole(user_id=regular_user.id, role_id=regular_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 检查权限
            user_id = str(regular_user.id)
            has_permission = check_permission(user_id, permission_name, db_session)
            
            # 断言：普通用户不应该自动拥有任意权限
            assert has_permission is False, (
                f"普通用户不应该自动拥有权限 '{permission_name}'"
            )
        finally:
            db_session.close()


class TestSuperAdminWithExplicitPermissions:
    """
    测试超级管理员即使有显式权限也跳过检查
    """
    
    @given(permission_name=permission_names())
    def test_super_admin_bypasses_check_even_with_explicit_permission(self, permission_name):
        """
        属性：超级管理员即使有显式权限也跳过检查
        
        即使为超级管理员角色显式添加了某个权限，
        超级管理员仍然应该通过超级管理员检查而不是权限检查，
        这意味着他们也拥有其他未显式授予的权限。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建权限
            permission = Permission(
                id=uuid.uuid4(),
                name=permission_name,
                resource=permission_name.split(':')[0],
                action=permission_name.split(':')[1],
                description=f"Test permission: {permission_name}"
            )
            db_session.add(permission)
            db_session.commit()
            db_session.refresh(permission)
            
            # 为超级管理员角色显式添加权限
            role_perm = RolePermission(
                role_id=super_admin_role.id,
                permission_id=permission.id
            )
            db_session.add(role_perm)
            db_session.commit()
            
            # 创建超级管理员
            super_admin = User(
                id=uuid.uuid4(),
                username=f"admin_{uuid.uuid4().hex[:8]}",
                email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            user_id = str(super_admin.id)
            
            # 检查显式授予的权限
            has_explicit_permission = check_permission(user_id, permission_name, db_session)
            assert has_explicit_permission is True
            
            # 检查其他未授予的权限（应该也通过）
            other_permission = "other:permission"
            has_other_permission = check_permission(user_id, other_permission, db_session)
            assert has_other_permission is True, (
                "超级管理员应该拥有所有权限，包括未显式授予的权限"
            )
        finally:
            db_session.close()


class TestSuperAdminIdentification:
    """
    测试超级管理员识别的属性
    """
    
    @given(
        username=usernames(),
        email=emails()
    )
    def test_user_with_super_admin_role_is_identified(self, username, email):
        """
        属性：拥有super_admin角色的用户被识别为超级管理员
        
        对于任意用户，只要分配了super_admin角色，
        就应该被识别为超级管理员。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建用户
            user = User(
                id=uuid.uuid4(),
                username=username,
                email=email,
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
            
            # 检查是否被识别为超级管理员
            user_id = str(user.id)
            is_admin = is_super_admin(user_id, db_session)
            
            assert is_admin is True, (
                f"用户 '{username}' 拥有super_admin角色，应该被识别为超级管理员"
            )
        finally:
            db_session.close()
    
    @given(
        username=usernames(),
        email=emails()
    )
    def test_user_without_super_admin_role_is_not_identified(self, username, email):
        """
        属性：没有super_admin角色的用户不被识别为超级管理员
        
        对于任意用户，如果没有分配super_admin角色，
        就不应该被识别为超级管理员。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建普通角色
            regular_role = create_regular_role(db_session)
            
            # 创建用户
            user = User(
                id=uuid.uuid4(),
                username=username,
                email=email,
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
            
            # 检查是否被识别为超级管理员
            user_id = str(user.id)
            is_admin = is_super_admin(user_id, db_session)
            
            assert is_admin is False, (
                f"用户 '{username}' 没有super_admin角色，不应该被识别为超级管理员"
            )
        finally:
            db_session.close()


class TestSuperAdminPermissionInvariant:
    """
    测试超级管理员权限的不变性
    """
    
    @given(
        permission_names_list=st.lists(permission_names(), min_size=5, max_size=10, unique=True)
    )
    def test_super_admin_permission_invariant_across_operations(self, permission_names_list):
        """
        属性：超级管理员权限在多次操作中保持不变
        
        对于任意权限列表，超级管理员在多次检查中
        都应该一致地拥有所有权限。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建超级管理员
            super_admin = User(
                id=uuid.uuid4(),
                username=f"admin_{uuid.uuid4().hex[:8]}",
                email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            user_id = str(super_admin.id)
            
            # 第一次检查所有权限
            first_check_results = []
            for permission_name in permission_names_list:
                has_permission = check_permission(user_id, permission_name, db_session)
                first_check_results.append(has_permission)
                assert has_permission is True
            
            # 第二次检查所有权限（应该得到相同结果）
            second_check_results = []
            for permission_name in permission_names_list:
                has_permission = check_permission(user_id, permission_name, db_session)
                second_check_results.append(has_permission)
                assert has_permission is True
            
            # 验证两次检查结果一致
            assert first_check_results == second_check_results, (
                "超级管理员权限检查结果应该在多次操作中保持一致"
            )
        finally:
            db_session.close()


class TestSuperAdminEdgeCases:
    """
    测试超级管理员的边界情况
    """
    
    @given(permission_name=permission_names())
    def test_super_admin_with_empty_permission_database(self, permission_name):
        """
        属性：即使权限表为空，超级管理员仍拥有所有权限
        
        即使数据库中没有定义任何权限，
        超级管理员仍然应该拥有任意权限。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 确保权限表为空
            db_session.query(Permission).delete()
            db_session.commit()
            
            # 创建超级管理员
            super_admin = User(
                id=uuid.uuid4(),
                username=f"admin_{uuid.uuid4().hex[:8]}",
                email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 检查权限
            user_id = str(super_admin.id)
            has_permission = check_permission(user_id, permission_name, db_session)
            
            assert has_permission is True, (
                "即使权限表为空，超级管理员仍应该拥有所有权限"
            )
        finally:
            db_session.close()
    
    @given(
        permission_name=permission_names(),
        num_regular_roles=st.integers(min_value=1, max_value=5)
    )
    def test_super_admin_with_multiple_roles(self, permission_name, num_regular_roles):
        """
        属性：拥有多个角色的超级管理员仍然拥有无限权限
        
        即使超级管理员同时拥有多个普通角色，
        仍然应该拥有所有权限。
        
        **Validates: Requirements 6.2, 6.3**
        """
        db_session = get_db_session()
        try:
            # 创建超级管理员角色
            super_admin_role = create_super_admin_role(db_session)
            
            # 创建超级管理员
            super_admin = User(
                id=uuid.uuid4(),
                username=f"admin_{uuid.uuid4().hex[:8]}",
                email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
                password_hash="hashed_password",
                status="active"
            )
            db_session.add(super_admin)
            db_session.commit()
            db_session.refresh(super_admin)
            
            # 分配超级管理员角色
            user_role = UserRole(user_id=super_admin.id, role_id=super_admin_role.id)
            db_session.add(user_role)
            db_session.commit()
            
            # 分配多个普通角色
            for i in range(num_regular_roles):
                regular_role = create_regular_role(db_session, name=f"regular_role_{i}_{uuid.uuid4().hex[:8]}")
                user_role = UserRole(user_id=super_admin.id, role_id=regular_role.id)
                db_session.add(user_role)
            
            db_session.commit()
            
            # 检查权限
            user_id = str(super_admin.id)
            has_permission = check_permission(user_id, permission_name, db_session)
            
            assert has_permission is True, (
                f"拥有 {num_regular_roles + 1} 个角色的超级管理员仍应该拥有所有权限"
            )
        finally:
            db_session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
