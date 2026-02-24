"""
测试系统初始化脚本

验证需求：6.1
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base
from shared.models import User, Role, Permission, UserRole, Organization, RolePermission
from shared.utils.crypto import verify_password

# 测试数据库
TEST_DATABASE_URL = "sqlite:///./test_system_init.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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


def test_create_super_admin(db_session):
    """
    测试创建超级管理员账号
    
    验证需求：6.1 - 系统初始化时创建超级管理员账号
    """
    from scripts.init_system import create_super_admin
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    
    # 验证用户创建成功
    assert admin_user is not None
    assert admin_user.username == "admin"
    assert admin_user.email == "admin@unified-auth.local"
    assert admin_user.status == "active"
    
    # 验证密码正确
    assert verify_password("123456", admin_user.password_hash)
    
    # 验证用户在数据库中
    db_user = db_session.query(User).filter(User.username == "admin").first()
    assert db_user is not None
    assert db_user.id == admin_user.id


def test_create_super_admin_idempotent(db_session):
    """
    测试重复创建超级管理员是幂等的
    
    验证需求：6.1
    """
    from scripts.init_system import create_super_admin
    
    # 第一次创建
    admin1 = create_super_admin(db_session)
    db_session.commit()
    
    # 第二次创建应该返回相同的用户
    admin2 = create_super_admin(db_session)
    
    assert admin1.id == admin2.id
    assert admin1.username == admin2.username


def test_create_system_permissions(db_session):
    """
    测试创建系统权限
    
    验证需求：6.1
    """
    from scripts.init_system import create_system_permissions
    
    # 创建系统权限
    permissions = create_system_permissions(db_session)
    
    # 验证权限创建成功
    assert len(permissions) > 0
    
    # 验证必要的权限存在
    required_permissions = [
        "user:create", "user:read", "user:update", "user:delete",
        "role:create", "role:read", "role:update", "role:delete",
        "permission:create", "permission:read",
        "organization:create", "organization:read",
        "subscription:create", "subscription:read",
        "audit:read", "config:read", "config:update"
    ]
    
    for perm_name in required_permissions:
        assert perm_name in permissions
        assert permissions[perm_name].name == perm_name
        assert permissions[perm_name].resource is not None
        assert permissions[perm_name].action is not None
    
    # 验证权限在数据库中
    db_perms = db_session.query(Permission).all()
    assert len(db_perms) == len(permissions)


def test_create_system_roles(db_session):
    """
    测试创建系统角色
    
    验证需求：6.1
    """
    from scripts.init_system import create_system_permissions, create_system_roles
    
    # 先创建权限
    permissions = create_system_permissions(db_session)
    db_session.commit()
    
    # 创建系统角色
    roles = create_system_roles(db_session, permissions)
    
    # 验证角色创建成功
    assert len(roles) == 3
    assert "super_admin" in roles
    assert "admin" in roles
    assert "user" in roles
    
    # 验证超级管理员角色
    super_admin_role = roles["super_admin"]
    assert super_admin_role.name == "super_admin"
    assert super_admin_role.is_system_role is True
    assert "超级管理员" in super_admin_role.description
    
    # 验证超级管理员拥有所有权限
    db_session.refresh(super_admin_role)
    role_perms = db_session.query(RolePermission).filter(
        RolePermission.role_id == super_admin_role.id
    ).all()
    assert len(role_perms) == len(permissions)
    
    # 验证管理员角色
    admin_role = roles["admin"]
    assert admin_role.name == "admin"
    assert admin_role.is_system_role is True
    
    # 验证普通用户角色
    user_role = roles["user"]
    assert user_role.name == "user"
    assert user_role.is_system_role is True


def test_assign_super_admin_role(db_session):
    """
    测试为超级管理员分配角色
    
    验证需求：6.1
    """
    from scripts.init_system import (
        create_super_admin,
        create_system_permissions,
        create_system_roles,
        assign_super_admin_role
    )
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    db_session.commit()
    
    # 创建权限和角色
    permissions = create_system_permissions(db_session)
    db_session.commit()
    roles = create_system_roles(db_session, permissions)
    db_session.commit()
    
    # 分配超级管理员角色
    assign_super_admin_role(db_session, admin_user, roles)
    db_session.commit()
    
    # 验证角色分配成功
    user_role = db_session.query(UserRole).filter(
        UserRole.user_id == admin_user.id,
        UserRole.role_id == roles["super_admin"].id
    ).first()
    
    assert user_role is not None
    assert user_role.user_id == admin_user.id
    assert user_role.role_id == roles["super_admin"].id


def test_create_root_organization(db_session):
    """
    测试创建根组织节点
    
    验证需求：6.1
    """
    from scripts.init_system import create_root_organization
    
    # 创建根组织
    root_org = create_root_organization(db_session)
    
    # 验证组织创建成功
    assert root_org is not None
    assert root_org.name == "根组织"
    assert root_org.parent_id is None
    assert root_org.path == "/root"
    assert root_org.level == 0
    
    # 验证组织在数据库中
    db_org = db_session.query(Organization).filter(
        Organization.parent_id == None,
        Organization.level == 0
    ).first()
    
    assert db_org is not None
    assert db_org.id == root_org.id


def test_create_root_organization_idempotent(db_session):
    """
    测试重复创建根组织是幂等的
    
    验证需求：6.1
    """
    from scripts.init_system import create_root_organization
    
    # 第一次创建
    org1 = create_root_organization(db_session)
    db_session.commit()
    
    # 第二次创建应该返回相同的组织
    org2 = create_root_organization(db_session)
    
    assert org1.id == org2.id
    assert org1.name == org2.name


def test_full_system_initialization(db_session):
    """
    测试完整的系统初始化流程
    
    验证需求：6.1 - 系统初始化时创建超级管理员账号、系统角色和权限、根组织节点
    """
    from scripts.init_system import (
        create_super_admin,
        create_system_permissions,
        create_system_roles,
        assign_super_admin_role,
        create_root_organization
    )
    
    # 1. 创建超级管理员
    admin_user = create_super_admin(db_session)
    assert admin_user.username == "admin"
    
    # 2. 创建系统权限
    permissions = create_system_permissions(db_session)
    assert len(permissions) > 0
    
    # 3. 创建系统角色
    roles = create_system_roles(db_session, permissions)
    assert len(roles) == 3
    
    # 4. 分配超级管理员角色
    assign_super_admin_role(db_session, admin_user, roles)
    
    # 5. 创建根组织
    root_org = create_root_organization(db_session)
    assert root_org.name == "根组织"
    
    # 提交所有更改
    db_session.commit()
    
    # 验证所有数据都已正确保存
    # 验证超级管理员
    db_admin = db_session.query(User).filter(User.username == "admin").first()
    assert db_admin is not None
    assert verify_password("123456", db_admin.password_hash)
    
    # 验证超级管理员拥有super_admin角色
    user_roles = db_session.query(UserRole).filter(UserRole.user_id == db_admin.id).all()
    assert len(user_roles) == 1
    assert user_roles[0].role_id == roles["super_admin"].id
    
    # 验证super_admin角色拥有所有权限
    role_perms = db_session.query(RolePermission).filter(
        RolePermission.role_id == roles["super_admin"].id
    ).all()
    assert len(role_perms) == len(permissions)
    
    # 验证根组织存在
    db_root = db_session.query(Organization).filter(
        Organization.parent_id == None
    ).first()
    assert db_root is not None
    assert db_root.path == "/root"


def test_super_admin_password_verification(db_session):
    """
    测试超级管理员密码验证
    
    验证需求：6.1 - 超级管理员密码为123456
    """
    from scripts.init_system import create_super_admin
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    
    # 验证正确的密码
    assert verify_password("123456", admin_user.password_hash) is True
    
    # 验证错误的密码
    assert verify_password("wrong_password", admin_user.password_hash) is False
    assert verify_password("admin", admin_user.password_hash) is False
    assert verify_password("", admin_user.password_hash) is False


def test_system_roles_hierarchy(db_session):
    """
    测试系统角色的权限层级
    
    验证需求：6.1
    """
    from scripts.init_system import create_system_permissions, create_system_roles
    
    # 创建权限和角色
    permissions = create_system_permissions(db_session)
    db_session.commit()
    roles = create_system_roles(db_session, permissions)
    db_session.commit()
    
    # 获取每个角色的权限数量
    super_admin_perms = db_session.query(RolePermission).filter(
        RolePermission.role_id == roles["super_admin"].id
    ).count()
    
    admin_perms = db_session.query(RolePermission).filter(
        RolePermission.role_id == roles["admin"].id
    ).count()
    
    user_perms = db_session.query(RolePermission).filter(
        RolePermission.role_id == roles["user"].id
    ).count()
    
    # 验证权限层级：super_admin > admin > user
    assert super_admin_perms > admin_perms
    assert admin_perms > user_perms
    assert user_perms > 0
    
    # 验证super_admin拥有所有权限
    assert super_admin_perms == len(permissions)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_super_admin_initial_password_not_changed(db_session):
    """
    测试超级管理员初始密码未修改标记
    
    验证需求：6.6 - 超级管理员初始创建时password_changed应为False
    """
    from scripts.init_system import create_super_admin
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    db_session.commit()
    
    # 验证password_changed字段为False
    assert admin_user.password_changed is False
    
    # 从数据库重新查询验证
    db_admin = db_session.query(User).filter(User.username == "admin").first()
    assert db_admin is not None
    assert db_admin.password_changed is False


def test_super_admin_first_login_requires_password_change(db_session):
    """
    测试超级管理员首次登录需要修改密码
    
    验证需求：6.6 - 在首次登录后强制Super_Admin修改默认密码
    """
    from scripts.init_system import create_super_admin
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    db_session.commit()
    
    # 模拟首次登录检查
    # 当password_changed为False时，应该要求修改密码
    assert admin_user.password_changed is False
    
    # 验证密码正确但需要修改
    assert verify_password("123456", admin_user.password_hash) is True
    
    # 首次登录应该被标记为需要修改密码
    requires_password_change = not admin_user.password_changed
    assert requires_password_change is True


def test_super_admin_password_change_updates_flag(db_session):
    """
    测试超级管理员修改密码后更新标记
    
    验证需求：6.6 - 修改密码后password_changed应为True
    """
    from scripts.init_system import create_super_admin
    from shared.utils.crypto import hash_password
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    db_session.commit()
    
    # 验证初始状态
    assert admin_user.password_changed is False
    
    # 模拟修改密码
    new_password = "NewSecurePassword123!"
    admin_user.password_hash = hash_password(new_password)
    admin_user.password_changed = True
    admin_user.updated_at = datetime.utcnow()
    db_session.commit()
    
    # 验证密码已修改
    db_admin = db_session.query(User).filter(User.username == "admin").first()
    assert db_admin.password_changed is True
    assert verify_password(new_password, db_admin.password_hash) is True
    assert verify_password("123456", db_admin.password_hash) is False


def test_super_admin_subsequent_login_no_password_change_required(db_session):
    """
    测试超级管理员修改密码后再次登录不需要强制修改
    
    验证需求：6.6 - 修改密码后的后续登录不应强制修改密码
    """
    from scripts.init_system import create_super_admin
    from shared.utils.crypto import hash_password
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    db_session.commit()
    
    # 模拟首次登录后修改密码
    admin_user.password_hash = hash_password("NewPassword123!")
    admin_user.password_changed = True
    db_session.commit()
    
    # 验证后续登录不需要修改密码
    db_admin = db_session.query(User).filter(User.username == "admin").first()
    requires_password_change = not db_admin.password_changed
    assert requires_password_change is False


def test_super_admin_cannot_use_default_password_after_change(db_session):
    """
    测试超级管理员修改密码后不能使用默认密码
    
    验证需求：6.6 - 确保密码确实被修改
    """
    from scripts.init_system import create_super_admin
    from shared.utils.crypto import hash_password
    
    # 创建超级管理员
    admin_user = create_super_admin(db_session)
    db_session.commit()
    
    # 验证初始密码
    assert verify_password("123456", admin_user.password_hash) is True
    
    # 修改密码
    new_password = "SecureNewPassword456!"
    admin_user.password_hash = hash_password(new_password)
    admin_user.password_changed = True
    db_session.commit()
    
    # 验证不能使用默认密码
    db_admin = db_session.query(User).filter(User.username == "admin").first()
    assert verify_password("123456", db_admin.password_hash) is False
    assert verify_password(new_password, db_admin.password_hash) is True


def test_multiple_super_admins_password_change_tracking(db_session):
    """
    测试多个管理员账号的密码修改跟踪独立性
    
    验证需求：6.6 - 每个账号的password_changed标记应该独立
    """
    from scripts.init_system import create_super_admin
    from shared.utils.crypto import hash_password
    
    # 创建超级管理员
    admin1 = create_super_admin(db_session)
    db_session.commit()
    
    # 创建另一个管理员账号（模拟）
    admin2 = User(
        username="admin2",
        email="admin2@unified-auth.local",
        password_hash=hash_password("123456"),
        status="active",
        password_changed=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(admin2)
    db_session.commit()
    
    # 验证两个账号都需要修改密码
    assert admin1.password_changed is False
    assert admin2.password_changed is False
    
    # 只修改admin1的密码
    admin1.password_hash = hash_password("NewPassword1!")
    admin1.password_changed = True
    db_session.commit()
    
    # 验证admin1已修改，admin2未修改
    db_admin1 = db_session.query(User).filter(User.username == "admin").first()
    db_admin2 = db_session.query(User).filter(User.username == "admin2").first()
    
    assert db_admin1.password_changed is True
    assert db_admin2.password_changed is False


def test_super_admin_password_change_enforcement_in_full_init(db_session):
    """
    测试完整系统初始化后超级管理员密码修改强制要求
    
    验证需求：6.1, 6.6 - 完整初始化流程中的密码修改跟踪
    """
    from scripts.init_system import (
        create_super_admin,
        create_system_permissions,
        create_system_roles,
        assign_super_admin_role,
        create_root_organization
    )
    
    # 完整系统初始化
    admin_user = create_super_admin(db_session)
    permissions = create_system_permissions(db_session)
    roles = create_system_roles(db_session, permissions)
    assign_super_admin_role(db_session, admin_user, roles)
    root_org = create_root_organization(db_session)
    db_session.commit()
    
    # 验证超级管理员需要修改密码
    db_admin = db_session.query(User).filter(User.username == "admin").first()
    assert db_admin is not None
    assert db_admin.password_changed is False
    
    # 验证密码是默认密码
    assert verify_password("123456", db_admin.password_hash) is True
    
    # 模拟首次登录后的密码修改
    from shared.utils.crypto import hash_password
    db_admin.password_hash = hash_password("NewSecurePassword789!")
    db_admin.password_changed = True
    db_session.commit()
    
    # 验证修改成功
    db_admin_updated = db_session.query(User).filter(User.username == "admin").first()
    assert db_admin_updated.password_changed is True
    assert verify_password("NewSecurePassword789!", db_admin_updated.password_hash) is True
    assert verify_password("123456", db_admin_updated.password_hash) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
