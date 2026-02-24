"""
组织架构服务
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
from shared.database import get_db
from shared.models.organization import Organization, UserOrganization, OrganizationPermission
from shared.config import settings

app = FastAPI(title="组织架构服务", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class OrgCreate(BaseModel):
    name: str
    parent_id: Optional[str] = None

class OrgResponse(BaseModel):
    id: str
    name: str
    parent_id: Optional[str]
    path: str
    level: int
    children: Optional[List['OrgResponse']] = None

@app.get("/")
async def root():
    return {"service": "组织架构服务", "status": "running"}

@app.get("/api/v1/organizations/tree")
async def get_organization_tree(db: Session = Depends(get_db)):
    """获取组织树"""
    def build_tree(parent_id=None):
        orgs = db.query(Organization).filter(Organization.parent_id == parent_id).all()
        return [OrgResponse(
            id=str(org.id), name=org.name, parent_id=str(org.parent_id) if org.parent_id else None,
            path=org.path, level=org.level, children=build_tree(org.id)
        ) for org in orgs]
    return build_tree()

@app.post("/api/v1/organizations", response_model=OrgResponse)
async def create_organization(org_data: OrgCreate, db: Session = Depends(get_db)):
    """创建组织节点"""
    parent = None
    path = f"/{org_data.name}"
    level = 0
    parent_uuid = None
    
    if org_data.parent_id:
        # Convert string UUID to UUID object
        try:
            parent_uuid = uuid.UUID(org_data.parent_id) if isinstance(org_data.parent_id, str) else org_data.parent_id
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的父节点ID")
        
        parent = db.query(Organization).filter(Organization.id == parent_uuid).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父节点不存在")
        path = f"{parent.path}/{org_data.name}"
        level = parent.level + 1
        if level >= 10:
            raise HTTPException(status_code=400, detail="组织层级不能超过10层")
    
    org = Organization(name=org_data.name, parent_id=parent_uuid, path=path, level=level)
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrgResponse(id=str(org.id), name=org.name, parent_id=str(org.parent_id) if org.parent_id else None, path=org.path, level=org.level)

@app.put("/api/v1/organizations/{org_id}", response_model=OrgResponse)
async def update_organization(org_id: str, org_data: OrgCreate, db: Session = Depends(get_db)):
    """更新组织节点"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    org.name = org_data.name
    db.commit()
    db.refresh(org)
    return OrgResponse(id=str(org.id), name=org.name, parent_id=str(org.parent_id) if org.parent_id else None, path=org.path, level=org.level)

@app.delete("/api/v1/organizations/{org_id}")
async def delete_organization(org_id: str, db: Session = Depends(get_db)):
    """删除组织节点"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    children = db.query(Organization).filter(Organization.parent_id == org_uuid).count()
    if children > 0:
        raise HTTPException(status_code=400, detail="无法删除有子节点的组织")
    db.delete(org)
    db.commit()
    return {"success": True, "message": "组织已删除"}

@app.post("/api/v1/organizations/{org_id}/users")
async def assign_users_to_org(org_id: str, user_ids: List[str], db: Session = Depends(get_db)):
    """分配用户到组织"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    for user_id in user_ids:
        try:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        except ValueError:
            continue  # Skip invalid UUIDs
        
        existing = db.query(UserOrganization).filter(
            UserOrganization.user_id == user_uuid, 
            UserOrganization.organization_id == org_uuid
        ).first()
        if not existing:
            user_org = UserOrganization(user_id=user_uuid, organization_id=org_uuid)
            db.add(user_org)
    db.commit()
    return {"success": True, "message": "用户已分配"}

@app.get("/api/v1/organizations/{org_id}/users")
async def get_organization_users(org_id: str, db: Session = Depends(get_db)):
    """查询组织的用户"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    user_orgs = db.query(UserOrganization).filter(
        UserOrganization.organization_id == org_uuid
    ).all()
    
    user_ids = [str(uo.user_id) for uo in user_orgs]
    return {"organization_id": org_id, "user_ids": user_ids}

@app.delete("/api/v1/organizations/{org_id}/users/{user_id}")
async def remove_user_from_org(org_id: str, user_id: str, db: Session = Depends(get_db)):
    """从组织移除用户"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID")
    
    user_org = db.query(UserOrganization).filter(
        UserOrganization.user_id == user_uuid,
        UserOrganization.organization_id == org_uuid
    ).first()
    
    if not user_org:
        raise HTTPException(status_code=404, detail="用户不在该组织中")
    
    db.delete(user_org)
    db.commit()
    return {"success": True, "message": "用户已从组织移除"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)


@app.post("/api/v1/organizations/{org_id}/permissions")
async def assign_permissions_to_org(org_id: str, permission_ids: List[str], db: Session = Depends(get_db)):
    """分配权限到组织"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    for perm_id in permission_ids:
        try:
            perm_uuid = uuid.UUID(perm_id) if isinstance(perm_id, str) else perm_id
        except ValueError:
            continue  # Skip invalid UUIDs
        
        existing = db.query(OrganizationPermission).filter(
            OrganizationPermission.organization_id == org_uuid,
            OrganizationPermission.permission_id == perm_uuid
        ).first()
        if not existing:
            org_perm = OrganizationPermission(organization_id=org_uuid, permission_id=perm_uuid)
            db.add(org_perm)
    db.commit()
    return {"success": True, "message": "权限已分配"}

@app.get("/api/v1/organizations/{org_id}/permissions")
async def get_organization_permissions(org_id: str, include_inherited: bool = True, db: Session = Depends(get_db)):
    """查询组织权限（包括继承的权限）"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    # 获取直接权限
    direct_perms = db.query(OrganizationPermission).filter(
        OrganizationPermission.organization_id == org_uuid
    ).all()
    
    permission_ids = {str(op.permission_id) for op in direct_perms}
    
    # 如果需要包含继承的权限，查询所有父节点的权限
    if include_inherited and org.parent_id:
        # 通过递归查询所有父节点
        current_org = org
        while current_org.parent_id:
            parent_org = db.query(Organization).filter(Organization.id == current_org.parent_id).first()
            if not parent_org:
                break
            
            parent_perms = db.query(OrganizationPermission).filter(
                OrganizationPermission.organization_id == parent_org.id
            ).all()
            for pp in parent_perms:
                permission_ids.add(str(pp.permission_id))
            
            current_org = parent_org
    
    return {
        "organization_id": org_id,
        "permission_ids": list(permission_ids),
        "include_inherited": include_inherited
    }

@app.delete("/api/v1/organizations/{org_id}/permissions/{permission_id}")
async def remove_permission_from_org(org_id: str, permission_id: str, db: Session = Depends(get_db)):
    """从组织移除权限"""
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
        perm_uuid = uuid.UUID(permission_id) if isinstance(permission_id, str) else permission_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID")
    
    org_perm = db.query(OrganizationPermission).filter(
        OrganizationPermission.organization_id == org_uuid,
        OrganizationPermission.permission_id == perm_uuid
    ).first()
    
    if not org_perm:
        raise HTTPException(status_code=404, detail="组织没有该权限")
    
    db.delete(org_perm)
    db.commit()
    return {"success": True, "message": "权限已从组织移除"}

class OrgMoveRequest(BaseModel):
    new_parent_id: Optional[str] = None

@app.put("/api/v1/organizations/{org_id}/move", response_model=OrgResponse)
async def move_organization(org_id: str, move_data: OrgMoveRequest, db: Session = Depends(get_db)):
    """
    移动组织节点到新的父节点
    
    移动组织时需要：
    1. 更新组织的parent_id
    2. 更新组织及其所有子节点的path字段
    3. 更新组织及其所有子节点的level字段
    4. 重新计算权限继承（通过缓存失效实现）
    """
    try:
        org_uuid = uuid.UUID(org_id) if isinstance(org_id, str) else org_id
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的组织ID")
    
    # 查询要移动的组织
    org = db.query(Organization).filter(Organization.id == org_uuid).first()
    if not org:
        raise HTTPException(status_code=404, detail="组织不存在")
    
    # 处理新父节点
    new_parent = None
    new_parent_uuid = None
    new_path = f"/{org.name}"
    new_level = 0
    
    if move_data.new_parent_id:
        try:
            new_parent_uuid = uuid.UUID(move_data.new_parent_id) if isinstance(move_data.new_parent_id, str) else move_data.new_parent_id
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的新父节点ID")
        
        # 不能移动到自己
        if new_parent_uuid == org_uuid:
            raise HTTPException(status_code=400, detail="不能将组织移动到自己")
        
        new_parent = db.query(Organization).filter(Organization.id == new_parent_uuid).first()
        if not new_parent:
            raise HTTPException(status_code=404, detail="新父节点不存在")
        
        # 不能移动到自己的子节点（避免循环）
        if new_parent.path.startswith(org.path + "/"):
            raise HTTPException(status_code=400, detail="不能将组织移动到自己的子节点")
        
        new_path = f"{new_parent.path}/{org.name}"
        new_level = new_parent.level + 1
        
        # 检查新层级是否超过限制
        if new_level > 10:
            raise HTTPException(status_code=400, detail="组织层级不能超过10层")
    
    # 保存旧路径，用于更新子节点
    old_path = org.path
    old_level = org.level
    
    # 更新组织的parent_id、path和level
    org.parent_id = new_parent_uuid
    org.path = new_path
    org.level = new_level
    
    # 更新所有子节点的path和level
    # 查询所有子节点（path以旧路径开头的节点）
    descendants = db.query(Organization).filter(
        Organization.path.like(f"{old_path}/%")
    ).all()
    
    level_diff = new_level - old_level
    
    # 先检查所有节点移动后的层级是否会超过限制
    for descendant in descendants:
        new_descendant_level = descendant.level + level_diff
        if new_descendant_level > 10:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"移动后组织 {descendant.name} 的层级将超过10层")
    
    # 如果检查通过，再更新所有节点
    for descendant in descendants:
        # 替换path中的旧路径为新路径
        descendant.path = descendant.path.replace(old_path, new_path, 1)
        # 更新level
        descendant.level = descendant.level + level_diff
    
    # 提交所有更改
    db.commit()
    db.refresh(org)
    
    # TODO: 实现缓存失效逻辑
    # 移动组织后，需要使相关用户的权限缓存失效
    # 这样下次查询权限时会重新计算继承关系
    
    return OrgResponse(
        id=str(org.id),
        name=org.name,
        parent_id=str(org.parent_id) if org.parent_id else None,
        path=org.path,
        level=org.level
    )
