"""
属性测试：超级管理员创建管理员

Feature: unified-auth-platform, Property 26: 超级管理员创建管理员

对于超级管理员，应该能够成功创建其他管理员账号，且新创建的管理员应该拥有管理员角色。

验证需求：6.4
"""
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

# 导入必要的模块
from shared.database import SessionLocal, engine, Base
from shared.models.user import User
from shared.models.permission import Role, Permission, UserRole, RolePermission
from shared.utils.crypto import hash_password
from services.user.main import app

# 创建测试客户端
client = TestClient(app)


# ==================== 测试数据生成器 ====================

@st.composite
def valid_usernames(draw):
    """生成有效的用户名（3-50个字符，字母数字）"""
    length = draw(st.integers(min_value=3, max_value=50))
    return draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), min_codepoint=ord('a')),
        min_size=length,
        max_size=length
    ))


@st.composite
def valid_emails(draw):
    """生成有效的邮箱地址"""
    local_part = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll', 'Nd'), min_codepoint=ord('a')),
        min_size=1,
        max_size=20
    ))
    domain = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Ll',), min_codepoint=ord('a')),
        min_size=3,
        max_size=10
    ))
    tld = draw(st.sampled_from(['com', 'org', 'net', 'edu']))
    return f"{local_part}@{domain}.{tld}"


@st.composite
def valid_passwords(draw):
    """生成有效的密码（8-32个字符，包含大小写字母和数字）"""
    length = draw(st.integers(min_value=8, max_value=32))
    # 确保包含大写、小写和数字
    password = (
        draw(st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=1, max_size=1)) +
        draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=1)) +
        draw(st.text(alphabet='0123456789', min_size=1, max_size=1)) +
        draw(st.text(
            alphabet=st.characters(
                whitelist_categories=('Lu', 'Ll', 'Nd'),
                whitelist_characters='!@#$%^&*()'
            ),
            min_size=length - 3,
            max_size=length - 3
        ))
    )
    # 打乱顺序
    password_list = list(password)
    draw(st.randoms()).shuffle(password_list)
    return ''.join(password_list)


# ==================== Fixtures ====================

@pytest.fixture(scope="function")
def db_session():
    """创建测试数据库会话"""
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 创建会话
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        # 清理所有表
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def setup_roles_and_permissions(db_session):
    """设置角色和权限"""
    # 创建权限
    permissions = [
        Permission(
            name="user:create",
            resource="user",
            action="create",
            description="创建用户",
            created_at=datetime.utcnow()
        ),
        Permission(
            name="user:read",
            resource="user",
            action="read",
            description="查看用户",
            created_at=datetime.utcnow()
        ),
        Permission(
            name="role:read",
            resource="role",
            action="read",
            description="查看角色",
            created_at=datetime.utcnow()
        ),
    ]
    
    for perm in permissions:
        db_session.add(perm)
    db_session.flush()
    
    # 创建超级管理员角色
    super_admin_role = Role(
        name="super_admin",
        description="超级管理员",
        is_system_role=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(super_admin_role)
    
    # 创建管理员角色
    admin_role = Role(
        name="admin",
        description="管理员",
        is_system_role=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(admin_role)
    db_session.flush()
    
    # 为超级管理员角色分配所有权限
    for perm in permissions:
        role_perm = RolePermission(
            role_id=super_admin_role.id,
            permission_id=perm.id,
            created_at=datetime.utcnow()
        )
        db_session.add(role_perm)
    
    # 为管理员角色分配部分权限
    admin_perms = [p for p in permissions if p.name in ["user:read", "role:read"]]
    for perm in admin_perms:
        role_perm = RolePermission(
            role_id=admin_role.id,
            permission_id=perm.id,
            created_at=datetime.utcnow()
        )
        db_session.add(role_perm)
    
    db_session.commit()
    
    return {
        "super_admin_role": super_admin_role,
        "admin_role": admin_role,
        "permissions": permissions
    }


@pytest.fixture(scope="function")
def super_admin_user(db_session, setup_roles_and_permissions):
    """创建超级管理员用户"""
    roles = setup_roles_and_permissions
    
    # 创建超级管理员用户
    user = User(
        username="super_admin_test",
        email="superadmin@test.com",
        password_hash=hash_password("TestPass123!"),
        status="active",
        password_changed=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.flush()
    
    # 分配超级管理员角色
    user_role = UserRole(
        user_id=user.id,
        role_id=roles["super_admin_role"].id,
        created_at=datetime.utcnow()
    )
    db_session.add(user_role)
    db_session.commit()
    db_session.refresh(user)
    
    return user


@pytest.fixture(scope="function")
def regular_user(db_session, setup_roles_and_permissions):
    """创建普通用户"""
    user = User(
        username="regular_user_test",
        email="regular@test.com",
        password_hash=hash_password("TestPass123!"),
        status="active",
        password_changed=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    
    return user


# ==================== 属性测试 ====================

class TestAdminCreationProperties:
    """
    属性 26：超级管理员创建管理员
    
    验证需求：6.4
    """
    
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    @given(
        username=valid_usernames(),
        email=valid_emails(),
        password=valid_passwords()
    )
    def test_super_admin_can_create_admin(
        self,
        username,
        email,
        password,
        super_admin_user,
        db_session
    ):
        """
        属性：超级管理员可以创建管理员账号
        
        对于任意有效的用户名、邮箱和密码，当超级管理员创建管理员时，
        应该成功创建账号并分配管理员角色。
        """
        # 确保用户名和邮箱唯一
        existing_user = db_session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        assume(existing_user is None)
        
        # 超级管理员创建管理员
        response = client.post(
            "/api/v1/admin/create-admin",
            params={"current_user_id": str(super_admin_user.id)},
            json={
                "username": username,
                "email": email,
                "password": password
            }
        )
        
        # 断言：创建成功
        assert response.status_code == 200, f"创建失败: {response.json()}"
        
        data = response.json()
        assert data["success"] is True
        assert data["username"] == username
        assert "user_id" in data
        
        # 验证：用户已创建
        created_user = db_session.query(User).filter(User.username == username).first()
        assert created_user is not None, "用户未创建"
        assert created_user.email == email
        assert created_user.status == "active"
        assert created_user.password_changed is False, "新管理员应该需要修改密码"
        
        # 验证：用户拥有管理员角色
        admin_role = db_session.query(Role).filter(Role.name == "admin").first()
        assert admin_role is not None, "管理员角色不存在"
        
        user_role = db_session.query(UserRole).filter(
            UserRole.user_id == created_user.id,
            UserRole.role_id == admin_role.id
        ).first()
        assert user_role is not None, "用户未分配管理员角色"
    
    @settings(
        max_examples=30,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    @given(
        username=valid_usernames(),
        email=valid_emails(),
        password=valid_passwords()
    )
    def test_regular_user_cannot_create_admin(
        self,
        username,
        email,
        password,
        regular_user,
        db_session
    ):
        """
        属性：普通用户不能创建管理员账号
        
        对于任意有效的用户名、邮箱和密码，当普通用户尝试创建管理员时，
        应该被拒绝（403 Forbidden）。
        """
        # 确保用户名和邮箱唯一
        existing_user = db_session.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        assume(existing_user is None)
        
        # 普通用户尝试创建管理员
        response = client.post(
            "/api/v1/admin/create-admin",
            params={"current_user_id": str(regular_user.id)},
            json={
                "username": username,
                "email": email,
                "password": password
            }
        )
        
        # 断言：创建被拒绝
        assert response.status_code == 403, "普通用户不应该能创建管理员"
        
        data = response.json()
        assert "只有超级管理员" in data["detail"]
        
        # 验证：用户未创建
        created_user = db_session.query(User).filter(User.username == username).first()
        assert created_user is None, "用户不应该被创建"
    
    def test_super_admin_create_admin_with_duplicate_username(
        self,
        super_admin_user,
        db_session
    ):
        """
        测试：超级管理员创建管理员时用户名重复
        
        当用户名已存在时，应该返回409冲突错误。
        """
        # 创建一个已存在的用户
        existing_user = User(
            username="existing_admin",
            email="existing@test.com",
            password_hash=hash_password("TestPass123!"),
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(existing_user)
        db_session.commit()
        
        # 尝试创建同名用户
        response = client.post(
            "/api/v1/admin/create-admin",
            params={"current_user_id": str(super_admin_user.id)},
            json={
                "username": "existing_admin",
                "email": "newemail@test.com",
                "password": "NewPass123!"
            }
        )
        
        # 断言：返回冲突错误
        assert response.status_code == 409
        assert "用户名已存在" in response.json()["detail"]
    
    def test_super_admin_create_admin_with_duplicate_email(
        self,
        super_admin_user,
        db_session
    ):
        """
        测试：超级管理员创建管理员时邮箱重复
        
        当邮箱已存在时，应该返回409冲突错误。
        """
        # 创建一个已存在的用户
        existing_user = User(
            username="existing_user",
            email="existing@test.com",
            password_hash=hash_password("TestPass123!"),
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(existing_user)
        db_session.commit()
        
        # 尝试创建同邮箱用户
        response = client.post(
            "/api/v1/admin/create-admin",
            params={"current_user_id": str(super_admin_user.id)},
            json={
                "username": "newadmin",
                "email": "existing@test.com",
                "password": "NewPass123!"
            }
        )
        
        # 断言：返回冲突错误
        assert response.status_code == 409
        assert "邮箱已存在" in response.json()["detail"]
    
    def test_created_admin_requires_password_change(
        self,
        super_admin_user,
        db_session
    ):
        """
        测试：新创建的管理员需要修改密码
        
        验证新创建的管理员的password_changed字段为False。
        """
        # 创建管理员
        response = client.post(
            "/api/v1/admin/create-admin",
            params={"current_user_id": str(super_admin_user.id)},
            json={
                "username": "newadmin123",
                "email": "newadmin@test.com",
                "password": "InitialPass123!"
            }
        )
        
        assert response.status_code == 200
        
        # 验证password_changed字段
        created_user = db_session.query(User).filter(
            User.username == "newadmin123"
        ).first()
        
        assert created_user is not None
        assert created_user.password_changed is False, (
            "新创建的管理员应该需要修改密码"
        )
    
    def test_super_admin_create_admin_without_email_or_phone(
        self,
        super_admin_user,
        db_session
    ):
        """
        测试：创建管理员时必须提供邮箱或手机号
        
        当既没有邮箱也没有手机号时，应该返回400错误。
        """
        response = client.post(
            "/api/v1/admin/create-admin",
            params={"current_user_id": str(super_admin_user.id)},
            json={
                "username": "noemailadmin",
                "password": "TestPass123!"
            }
        )
        
        # 断言：返回错误
        assert response.status_code == 400
        assert "邮箱或手机号" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
