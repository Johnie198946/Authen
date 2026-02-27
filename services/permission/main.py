"""
权限服务主入口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from functools import wraps
from shared.database import get_db
from shared.models.permission import Role, Permission, RolePermission, UserRole
from shared.redis_client import get_redis
from shared.config import settings
import json

app = FastAPI(title="权限服务", description="权限管理服务", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 超级管理员识别函数
def is_super_admin(user_id: str, db: Session) -> bool:
    """
    检查用户是否为超级管理员
    
    Args:
        user_id: 用户ID
        db: 数据库会话
    
    Returns:
        bool: 用户是否为超级管理员
    """
    import uuid as uuid_lib
    
    # 转换user_id为UUID对象
    try:
        user_uuid = uuid_lib.UUID(user_id)
    except ValueError:
        return False
    
    # 先检查缓存
    redis = get_redis()
    cache_key = f"user_is_super_admin:{user_id}"
    cached = redis.get(cache_key)
    
    if cached is not None:
        return str(cached) == 'true'
    
    # 缓存未命中，从数据库查询
    # 查询用户是否拥有super_admin角色
    super_admin_role = db.query(Role).filter(Role.name == "super_admin").first()
    if not super_admin_role:
        # 缓存结果（TTL 5分钟）
        redis.setex(cache_key, 300, 'false')
        return False
    
    user_role = db.query(UserRole).filter(
        UserRole.user_id == user_uuid,
        UserRole.role_id == super_admin_role.id
    ).first()
    
    is_admin = user_role is not None
    
    # 缓存结果（TTL 5分钟）
    redis.setex(cache_key, 300, 'true' if is_admin else 'false')
    
    return is_admin


# 权限验证函数
def check_permission(user_id: str, required_permission: str, db: Session) -> bool:
    """
    检查用户是否拥有指定权限
    
    超级管理员拥有所有权限，跳过权限检查
    
    Args:
        user_id: 用户ID
        required_permission: 所需权限名称（格式：resource:action，如 user:create）
        db: 数据库会话
    
    Returns:
        bool: 用户是否拥有该权限
    """
    import uuid as uuid_lib
    
    # 转换user_id为UUID对象
    try:
        user_uuid = uuid_lib.UUID(user_id)
    except ValueError:
        return False
    
    # 检查是否为超级管理员，超级管理员拥有所有权限
    if is_super_admin(user_id, db):
        return True
    
    # 先检查缓存
    redis = get_redis()
    cache_key = f"user_permissions:{user_id}"
    cached = redis.get(cache_key)
    
    if cached:
        permissions_data = json.loads(cached)
        user_permissions = permissions_data.get("permissions", [])
        # 检查权限列表中是否包含所需权限
        for perm in user_permissions:
            if perm.get("name") == required_permission:
                return True
        return False
    
    # 缓存未命中，从数据库查询
    # 查询用户角色
    user_roles = db.query(UserRole).filter(UserRole.user_id == user_uuid).all()
    role_ids = [ur.role_id for ur in user_roles]
    
    # 查询角色权限
    permissions = []
    for role_id in role_ids:
        role_perms = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
        for rp in role_perms:
            perm = db.query(Permission).filter(Permission.id == rp.permission_id).first()
            if perm:
                permissions.append({
                    "id": str(perm.id),
                    "name": perm.name,
                    "resource": perm.resource,
                    "action": perm.action,
                    "source": "role"
                })
    
    # 缓存权限（TTL 5分钟）
    redis.setex(cache_key, 300, json.dumps({"permissions": permissions}))
    
    # 检查是否拥有所需权限
    for perm in permissions:
        if perm.get("name") == required_permission:
            return True
    
    return False


def invalidate_role_permissions_cache(role_id: str, db: Session):
    """
    使角色相关的所有用户权限缓存失效
    
    Args:
        role_id: 角色ID
        db: 数据库会话
    """
    import uuid as uuid_lib
    
    try:
        role_uuid = uuid_lib.UUID(role_id)
    except ValueError:
        return
    
    redis = get_redis()
    user_roles = db.query(UserRole).filter(UserRole.role_id == role_uuid).all()
    for ur in user_roles:
        redis.delete(f"user_permissions:{ur.user_id}")


def invalidate_user_permissions_cache(user_id: str):
    """
    使用户权限缓存失效
    
    Args:
        user_id: 用户ID
    """
    redis = get_redis()
    redis.delete(f"user_permissions:{user_id}")
    redis.delete(f"user_is_super_admin:{user_id}")  # 同时清除超级管理员缓存


def require_permission(permission_name: str):
    """
    权限装饰器，用于保护需要特定权限的API端点
    
    超级管理员会跳过权限检查，自动通过
    
    Args:
        permission_name: 所需权限名称（格式：resource:action）
    
    Usage:
        @app.get("/api/v1/users")
        @require_permission("user:list")
        async def list_users(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从kwargs中获取user_id和db
            user_id = kwargs.get("user_id") or kwargs.get("current_user_id")
            db = kwargs.get("db")
            
            if not user_id:
                raise HTTPException(status_code=401, detail="未认证")
            
            if not db:
                raise HTTPException(status_code=500, detail="数据库会话未找到")
            
            # 检查权限（超级管理员会自动通过）
            if not check_permission(user_id, permission_name, db):
                raise HTTPException(
                    status_code=403,
                    detail=f"无权限访问：需要 {permission_name} 权限"
                )
            
            # 权限检查通过，执行原函数
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None

class RoleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_system_role: bool

class PermissionCreate(BaseModel):
    name: str
    resource: str
    action: str
    description: Optional[str] = None

class PermissionResponse(BaseModel):
    id: str
    name: str
    resource: str
    action: str
    description: Optional[str]

@app.get("/")
async def root():
    return {"service": "权限服务", "status": "running"}

@app.get("/api/v1/roles", response_model=List[RoleResponse])
async def list_roles(db: Session = Depends(get_db)):
    """获取角色列表"""
    roles = db.query(Role).all()
    return [RoleResponse(id=str(r.id), name=r.name, description=r.description, is_system_role=r.is_system_role) for r in roles]

@app.post("/api/v1/roles", response_model=RoleResponse)
async def create_role(role_data: RoleCreate, db: Session = Depends(get_db)):
    """创建角色"""
    existing = db.query(Role).filter(Role.name == role_data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="角色名已存在")
    
    role = Role(name=role_data.name, description=role_data.description)
    db.add(role)
    db.commit()
    db.refresh(role)
    return RoleResponse(id=str(role.id), name=role.name, description=role.description, is_system_role=role.is_system_role)

@app.put("/api/v1/roles/{role_id}", response_model=RoleResponse)
async def update_role(role_id: str, role_data: RoleCreate, db: Session = Depends(get_db)):
    """更新角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.is_system_role:
        raise HTTPException(status_code=403, detail="无法修改系统角色")
    
    role.name = role_data.name
    role.description = role_data.description
    db.commit()
    db.refresh(role)
    return RoleResponse(id=str(role.id), name=role.name, description=role.description, is_system_role=role.is_system_role)

@app.delete("/api/v1/roles/{role_id}")
async def delete_role(role_id: str, db: Session = Depends(get_db)):
    """删除角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.is_system_role:
        raise HTTPException(status_code=403, detail="无法删除系统角色")
    
    db.delete(role)
    db.commit()
    return {"success": True, "message": "角色已删除"}

@app.get("/api/v1/permissions", response_model=List[PermissionResponse])
async def list_permissions(db: Session = Depends(get_db)):
    """获取权限列表"""
    permissions = db.query(Permission).all()
    return [PermissionResponse(id=str(p.id), name=p.name, resource=p.resource, action=p.action, description=p.description) for p in permissions]

@app.post("/api/v1/permissions", response_model=PermissionResponse)
async def create_permission(perm_data: PermissionCreate, db: Session = Depends(get_db)):
    """创建权限"""
    existing = db.query(Permission).filter(Permission.name == perm_data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="权限名已存在")
    
    permission = Permission(name=perm_data.name, resource=perm_data.resource, action=perm_data.action, description=perm_data.description)
    db.add(permission)
    db.commit()
    db.refresh(permission)
    return PermissionResponse(id=str(permission.id), name=permission.name, resource=permission.resource, action=permission.action, description=permission.description)

@app.put("/api/v1/permissions/{perm_id}", response_model=PermissionResponse)
async def update_permission(perm_id: str, perm_data: PermissionCreate, db: Session = Depends(get_db)):
    """更新权限"""
    import uuid as uuid_lib
    try:
        perm_uuid = uuid_lib.UUID(perm_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的权限ID格式")
    perm = db.query(Permission).filter(Permission.id == perm_uuid).first()
    if not perm:
        raise HTTPException(status_code=404, detail="权限不存在")
    perm.name = perm_data.name
    perm.resource = perm_data.resource
    perm.action = perm_data.action
    perm.description = perm_data.description
    db.commit()
    db.refresh(perm)
    return PermissionResponse(id=str(perm.id), name=perm.name, resource=perm.resource, action=perm.action, description=perm.description)

@app.delete("/api/v1/permissions/{perm_id}")
async def delete_permission(perm_id: str, db: Session = Depends(get_db)):
    """删除权限"""
    import uuid as uuid_lib
    try:
        perm_uuid = uuid_lib.UUID(perm_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的权限ID格式")
    perm = db.query(Permission).filter(Permission.id == perm_uuid).first()
    if not perm:
        raise HTTPException(status_code=404, detail="权限不存在")
    # 检查是否有角色在使用该权限
    in_use = db.query(RolePermission).filter(RolePermission.permission_id == perm_uuid).count()
    if in_use > 0:
        raise HTTPException(status_code=400, detail=f"该权限正在被 {in_use} 个角色使用，无法删除")
    db.delete(perm)
    db.commit()
    return {"success": True, "message": "权限已删除"}

@app.get("/api/v1/roles/{role_id}/permissions")
async def get_role_permissions(role_id: str, db: Session = Depends(get_db)):
    """获取角色的权限列表"""
    import uuid as uuid_lib
    try:
        role_uuid = uuid_lib.UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的角色ID格式")
    
    role = db.query(Role).filter(Role.id == role_uuid).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    role_perms = db.query(RolePermission).filter(RolePermission.role_id == role_uuid).all()
    result = []
    for rp in role_perms:
        perm = db.query(Permission).filter(Permission.id == rp.permission_id).first()
        if perm:
            result.append(PermissionResponse(id=str(perm.id), name=perm.name, resource=perm.resource, action=perm.action, description=perm.description))
    return result

@app.post("/api/v1/roles/{role_id}/permissions")
async def assign_permissions_to_role(role_id: str, permission_ids: List[str], db: Session = Depends(get_db)):
    """为角色分配权限"""
    import uuid as uuid_lib
    
    # 转换role_id为UUID对象
    try:
        role_uuid = uuid_lib.UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的角色ID格式")
    
    role = db.query(Role).filter(Role.id == role_uuid).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    for perm_id in permission_ids:
        try:
            perm_uuid = uuid_lib.UUID(perm_id)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"无效的权限ID格式: {perm_id}")
        
        existing = db.query(RolePermission).filter(
            RolePermission.role_id == role_uuid,
            RolePermission.permission_id == perm_uuid
        ).first()
        if not existing:
            role_perm = RolePermission(role_id=role_uuid, permission_id=perm_uuid)
            db.add(role_perm)
    
    db.commit()
    
    # 清除相关用户的权限缓存
    invalidate_role_permissions_cache(role_id, db)
    
    return {"success": True, "message": "权限已分配"}


@app.delete("/api/v1/roles/{role_id}/permissions/{permission_id}")
async def remove_permission_from_role(role_id: str, permission_id: str, db: Session = Depends(get_db)):
    """从角色移除权限"""
    import uuid as uuid_lib
    
    # 转换ID为UUID对象
    try:
        role_uuid = uuid_lib.UUID(role_id)
        perm_uuid = uuid_lib.UUID(permission_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的ID格式")
    
    # 检查角色是否存在
    role = db.query(Role).filter(Role.id == role_uuid).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 检查权限是否存在
    permission = db.query(Permission).filter(Permission.id == perm_uuid).first()
    if not permission:
        raise HTTPException(status_code=404, detail="权限不存在")
    
    # 查找并删除角色权限关联
    role_perm = db.query(RolePermission).filter(
        RolePermission.role_id == role_uuid,
        RolePermission.permission_id == perm_uuid
    ).first()
    
    if not role_perm:
        raise HTTPException(status_code=404, detail="角色权限关联不存在")
    
    db.delete(role_perm)
    db.commit()
    
    # 清除所有拥有该角色的用户的权限缓存
    invalidate_role_permissions_cache(role_id, db)
    
    return {"success": True, "message": "权限已从角色移除"}


class UserRoleAssign(BaseModel):
    role_ids: List[str]

class UserRoleResponse(BaseModel):
    user_id: str
    role_id: str
    role_name: str
    role_description: Optional[str]

@app.post("/api/v1/users/{user_id}/roles")
async def assign_roles_to_user(user_id: str, data: UserRoleAssign, db: Session = Depends(get_db)):
    """为用户分配角色"""
    import uuid as uuid_lib
    
    # 转换user_id为UUID对象
    try:
        user_uuid = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    
    # 验证所有角色是否存在
    for role_id in data.role_ids:
        try:
            role_uuid = uuid_lib.UUID(role_id)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"无效的角色ID格式: {role_id}")
        
        role = db.query(Role).filter(Role.id == role_uuid).first()
        if not role:
            raise HTTPException(status_code=404, detail=f"角色 {role_id} 不存在")
    
    # 分配角色
    assigned_count = 0
    for role_id in data.role_ids:
        role_uuid = uuid_lib.UUID(role_id)
        existing = db.query(UserRole).filter(UserRole.user_id == user_uuid, UserRole.role_id == role_uuid).first()
        if not existing:
            user_role = UserRole(user_id=user_uuid, role_id=role_uuid)
            db.add(user_role)
            assigned_count += 1
    
    db.commit()
    
    # 清除用户权限缓存
    invalidate_user_permissions_cache(user_id)
    
    return {"success": True, "message": f"成功分配 {assigned_count} 个角色", "assigned_count": assigned_count}

@app.get("/api/v1/users/{user_id}/roles", response_model=List[UserRoleResponse])
async def get_user_roles(user_id: str, db: Session = Depends(get_db)):
    """查询用户的角色"""
    import uuid as uuid_lib
    
    # 转换user_id为UUID对象
    try:
        user_uuid = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    
    user_roles = db.query(UserRole).filter(UserRole.user_id == user_uuid).all()
    
    result = []
    for ur in user_roles:
        role = db.query(Role).filter(Role.id == ur.role_id).first()
        if role:
            result.append(UserRoleResponse(
                user_id=str(ur.user_id),
                role_id=str(ur.role_id),
                role_name=role.name,
                role_description=role.description
            ))
    
    return result

@app.delete("/api/v1/users/{user_id}/roles/{role_id}")
async def remove_role_from_user(user_id: str, role_id: str, db: Session = Depends(get_db)):
    """移除用户的角色"""
    import uuid as uuid_lib
    
    # 转换ID为UUID对象
    try:
        user_uuid = uuid_lib.UUID(user_id)
        role_uuid = uuid_lib.UUID(role_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的ID格式")
    
    user_role = db.query(UserRole).filter(UserRole.user_id == user_uuid, UserRole.role_id == role_uuid).first()
    if not user_role:
        raise HTTPException(status_code=404, detail="用户角色关联不存在")
    
    db.delete(user_role)
    db.commit()
    
    # 清除用户权限缓存
    invalidate_user_permissions_cache(user_id)
    
    return {"success": True, "message": "角色已移除"}

@app.get("/api/v1/users/{user_id}/permissions")
async def get_user_permissions(user_id: str, db: Session = Depends(get_db)):
    """获取用户权限"""
    import uuid as uuid_lib
    
    # 转换user_id为UUID对象
    try:
        user_uuid = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    
    redis = get_redis()
    cached = redis.get(f"user_permissions:{user_id}")
    
    if cached:
        import json
        return json.loads(cached)
    
    # 查询用户角色
    user_roles = db.query(UserRole).filter(UserRole.user_id == user_uuid).all()
    role_ids = [ur.role_id for ur in user_roles]
    
    # 查询角色权限
    permissions = []
    for role_id in role_ids:
        role_perms = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
        for rp in role_perms:
            perm = db.query(Permission).filter(Permission.id == rp.permission_id).first()
            if perm:
                permissions.append({
                    "id": str(perm.id),
                    "name": perm.name,
                    "resource": perm.resource,
                    "action": perm.action,
                    "source": "role"
                })
    
    # 缓存5分钟
    import json
    redis.setex(f"user_permissions:{user_id}", 300, json.dumps({"permissions": permissions}))
    
    return {"permissions": permissions}


class CheckPermissionRequest(BaseModel):
    permission: str

@app.post("/api/v1/users/{user_id}/check-permission")
async def check_user_permission(
    user_id: str,
    body: CheckPermissionRequest,
    db: Session = Depends(get_db)
):
    """
    检查用户是否拥有指定权限
    
    Args:
        user_id: 用户ID
        body.permission: 权限名称（格式：resource:action）
    
    Returns:
        {"has_permission": bool}
    """
    has_permission = check_permission(user_id, body.permission, db)
    return {
        "user_id": user_id,
        "permission": body.permission,
        "has_permission": has_permission
    }


@app.get("/api/v1/users/{user_id}/is-super-admin")
async def check_user_is_super_admin(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    检查用户是否为超级管理员
    
    Args:
        user_id: 用户ID
    
    Returns:
        {"is_super_admin": bool}
    """
    is_admin = is_super_admin(user_id, db)
    return {
        "user_id": user_id,
        "is_super_admin": is_admin
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
