"""
系统初始化脚本

功能：
1. 创建超级管理员账号（admin/123456）
2. 创建系统角色和权限
3. 创建根组织节点

需求：6.1
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from shared.database import SessionLocal, engine, Base
from shared.models import User, Role, Permission, UserRole, Organization, RolePermission
from shared.utils.crypto import hash_password
from datetime import datetime


def create_super_admin(db: Session) -> User:
    """
    创建超级管理员账号
    
    Args:
        db: 数据库会话
        
    Returns:
        创建的超级管理员用户对象
    """
    # 检查是否已存在超级管理员
    existing_admin = db.query(User).filter(User.username == "admin").first()
    if existing_admin:
        print("⚠️  超级管理员账号已存在，跳过创建")
        return existing_admin
    
    # 创建超级管理员账号
    admin_user = User(
        username="admin",
        email="admin@unified-auth.local",
        password_hash=hash_password("123456"),
        status="active",
        password_changed=False,  # 初始密码未修改，首次登录需要修改
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(admin_user)
    db.flush()  # 刷新以获取ID
    
    print(f"✅ 超级管理员账号创建成功")
    print(f"   用户名: admin")
    print(f"   密码: 123456")
    print(f"   用户ID: {admin_user.id}")
    
    return admin_user


def create_system_permissions(db: Session) -> dict:
    """
    创建系统权限
    
    Args:
        db: 数据库会话
        
    Returns:
        权限字典 {name: Permission对象}
    """
    # 定义系统权限
    permissions_data = [
        # 用户管理权限
        {"name": "user:create", "resource": "user", "action": "create", "description": "创建用户"},
        {"name": "user:read", "resource": "user", "action": "read", "description": "查看用户"},
        {"name": "user:update", "resource": "user", "action": "update", "description": "更新用户"},
        {"name": "user:delete", "resource": "user", "action": "delete", "description": "删除用户"},
        
        # 角色管理权限
        {"name": "role:create", "resource": "role", "action": "create", "description": "创建角色"},
        {"name": "role:read", "resource": "role", "action": "read", "description": "查看角色"},
        {"name": "role:update", "resource": "role", "action": "update", "description": "更新角色"},
        {"name": "role:delete", "resource": "role", "action": "delete", "description": "删除角色"},
        
        # 权限管理权限
        {"name": "permission:create", "resource": "permission", "action": "create", "description": "创建权限"},
        {"name": "permission:read", "resource": "permission", "action": "read", "description": "查看权限"},
        {"name": "permission:update", "resource": "permission", "action": "update", "description": "更新权限"},
        {"name": "permission:delete", "resource": "permission", "action": "delete", "description": "删除权限"},
        
        # 组织管理权限
        {"name": "organization:create", "resource": "organization", "action": "create", "description": "创建组织"},
        {"name": "organization:read", "resource": "organization", "action": "read", "description": "查看组织"},
        {"name": "organization:update", "resource": "organization", "action": "update", "description": "更新组织"},
        {"name": "organization:delete", "resource": "organization", "action": "delete", "description": "删除组织"},
        
        # 订阅管理权限
        {"name": "subscription:create", "resource": "subscription", "action": "create", "description": "创建订阅"},
        {"name": "subscription:read", "resource": "subscription", "action": "read", "description": "查看订阅"},
        {"name": "subscription:update", "resource": "subscription", "action": "update", "description": "更新订阅"},
        {"name": "subscription:delete", "resource": "subscription", "action": "delete", "description": "删除订阅"},
        
        # 审计日志权限
        {"name": "audit:read", "resource": "audit", "action": "read", "description": "查看审计日志"},
        
        # 系统配置权限
        {"name": "config:read", "resource": "config", "action": "read", "description": "查看系统配置"},
        {"name": "config:update", "resource": "config", "action": "update", "description": "更新系统配置"},
    ]
    
    permissions = {}
    created_count = 0
    
    for perm_data in permissions_data:
        # 检查权限是否已存在
        existing_perm = db.query(Permission).filter(Permission.name == perm_data["name"]).first()
        if existing_perm:
            permissions[perm_data["name"]] = existing_perm
            continue
        
        # 创建新权限
        permission = Permission(
            name=perm_data["name"],
            resource=perm_data["resource"],
            action=perm_data["action"],
            description=perm_data["description"],
            created_at=datetime.utcnow()
        )
        db.add(permission)
        db.flush()
        permissions[perm_data["name"]] = permission
        created_count += 1
    
    print(f"✅ 系统权限创建完成（新建 {created_count} 个，已存在 {len(permissions_data) - created_count} 个）")
    
    return permissions


def create_system_roles(db: Session, permissions: dict) -> dict:
    """
    创建系统角色
    
    Args:
        db: 数据库会话
        permissions: 权限字典
        
    Returns:
        角色字典 {name: Role对象}
    """
    # 定义系统角色及其权限
    roles_data = {
        "super_admin": {
            "description": "超级管理员，拥有所有权限",
            "permissions": list(permissions.keys())  # 所有权限
        },
        "admin": {
            "description": "管理员，拥有大部分管理权限",
            "permissions": [
                "user:create", "user:read", "user:update", "user:delete",
                "role:read", "organization:read", "organization:create", 
                "organization:update", "subscription:read", "subscription:update",
                "audit:read"
            ]
        },
        "user": {
            "description": "普通用户，拥有基本权限",
            "permissions": [
                "user:read",  # 只能查看自己的信息
                "subscription:read"  # 查看自己的订阅
            ]
        }
    }
    
    roles = {}
    created_count = 0
    
    for role_name, role_info in roles_data.items():
        # 检查角色是否已存在
        existing_role = db.query(Role).filter(Role.name == role_name).first()
        if existing_role:
            roles[role_name] = existing_role
            print(f"⚠️  角色 '{role_name}' 已存在，跳过创建")
            continue
        
        # 创建新角色
        role = Role(
            name=role_name,
            description=role_info["description"],
            is_system_role=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(role)
        db.flush()
        
        # 为角色分配权限
        for perm_name in role_info["permissions"]:
            if perm_name in permissions:
                role_permission = RolePermission(
                    role_id=role.id,
                    permission_id=permissions[perm_name].id,
                    created_at=datetime.utcnow()
                )
                db.add(role_permission)
        
        roles[role_name] = role
        created_count += 1
        print(f"✅ 角色 '{role_name}' 创建成功（包含 {len(role_info['permissions'])} 个权限）")
    
    print(f"✅ 系统角色创建完成（新建 {created_count} 个）")
    
    return roles


def assign_super_admin_role(db: Session, admin_user: User, roles: dict):
    """
    为超级管理员分配角色
    
    Args:
        db: 数据库会话
        admin_user: 超级管理员用户对象
        roles: 角色字典
    """
    super_admin_role = roles.get("super_admin")
    if not super_admin_role:
        print("❌ 超级管理员角色不存在")
        return
    
    # 检查是否已分配角色
    existing_user_role = db.query(UserRole).filter(
        UserRole.user_id == admin_user.id,
        UserRole.role_id == super_admin_role.id
    ).first()
    
    if existing_user_role:
        print("⚠️  超级管理员角色已分配，跳过")
        return
    
    # 分配超级管理员角色
    user_role = UserRole(
        user_id=admin_user.id,
        role_id=super_admin_role.id,
        created_at=datetime.utcnow()
    )
    db.add(user_role)
    
    print(f"✅ 超级管理员角色分配成功")


def create_root_organization(db: Session) -> Organization:
    """
    创建根组织节点
    
    Args:
        db: 数据库会话
        
    Returns:
        创建的根组织对象
    """
    # 检查是否已存在根组织
    existing_root = db.query(Organization).filter(
        Organization.parent_id == None,
        Organization.level == 0
    ).first()
    
    if existing_root:
        print(f"⚠️  根组织节点已存在: {existing_root.name}")
        return existing_root
    
    # 创建根组织节点
    root_org = Organization(
        name="根组织",
        parent_id=None,
        path="/root",
        level=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(root_org)
    db.flush()
    
    print(f"✅ 根组织节点创建成功")
    print(f"   组织名称: {root_org.name}")
    print(f"   组织路径: {root_org.path}")
    print(f"   组织ID: {root_org.id}")
    
    return root_org


def init_system():
    """
    初始化系统
    """
    print("=" * 60)
    print("开始系统初始化...")
    print("=" * 60)
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 1. 创建超级管理员账号
        print("\n[1/4] 创建超级管理员账号...")
        admin_user = create_super_admin(db)
        
        # 2. 创建系统权限
        print("\n[2/4] 创建系统权限...")
        permissions = create_system_permissions(db)
        
        # 3. 创建系统角色
        print("\n[3/4] 创建系统角色...")
        roles = create_system_roles(db, permissions)
        
        # 4. 为超级管理员分配角色
        print("\n[4/4] 为超级管理员分配角色...")
        assign_super_admin_role(db, admin_user, roles)
        
        # 5. 创建根组织节点
        print("\n[5/5] 创建根组织节点...")
        root_org = create_root_organization(db)
        
        # 提交事务
        db.commit()
        
        print("\n" + "=" * 60)
        print("✅ 系统初始化完成！")
        print("=" * 60)
        print("\n📋 初始化摘要:")
        print(f"   - 超级管理员: admin / 123456")
        print(f"   - 系统权限数: {len(permissions)}")
        print(f"   - 系统角色数: {len(roles)}")
        print(f"   - 根组织: {root_org.name}")
        print("\n⚠️  重要提示:")
        print("   1. 请在首次登录后立即修改超级管理员密码")
        print("   2. 超级管理员拥有无限权限，请妥善保管账号")
        print("   3. 所有操作都会被记录到审计日志")
        print("=" * 60)
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 系统初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_system()
