"""
用户服务主入口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import uuid
from shared.database import get_db
from shared.models.user import User
from shared.models.permission import Role, UserRole
from shared.utils.crypto import hash_password
from shared.config import settings

app = FastAPI(title="用户服务", description="用户管理服务", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserCreate(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    status: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str]
    phone: Optional[str]
    status: str
    created_at: datetime
    last_login_at: Optional[datetime]

class UserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    users: List[UserResponse]

class AdminCreateRequest(BaseModel):
    """创建管理员请求"""
    username: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str

class AdminCreateResponse(BaseModel):
    """创建管理员响应"""
    success: bool
    message: str
    user_id: str
    username: str

@app.get("/")
async def root():
    return {"service": "用户服务", "status": "running"}

@app.get("/api/v1/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取用户列表"""
    query = db.query(User)
    
    if search:
        query = query.filter(
            (User.username.contains(search)) |
            (User.email.contains(search)) |
            (User.phone.contains(search))
        )
    
    if status:
        query = query.filter(User.status == status)
    
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return UserListResponse(
        total=total,
        page=page,
        page_size=page_size,
        users=[UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            phone=user.phone,
            status=user.status,
            created_at=user.created_at,
            last_login_at=user.last_login_at
        ) for user in users]
    )

@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    """获取用户详情"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )

@app.post("/api/v1/users", response_model=UserResponse)
async def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """创建用户"""
    if not user_data.email and not user_data.phone:
        raise HTTPException(status_code=400, detail="邮箱或手机号至少提供一个")
    
    if user_data.email:
        existing = db.query(User).filter(User.email == user_data.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="邮箱已存在")
    
    if user_data.phone:
        existing = db.query(User).filter(User.phone == user_data.phone).first()
        if existing:
            raise HTTPException(status_code=409, detail="手机号已存在")
    
    user = User(
        username=user_data.username,
        email=user_data.email,
        phone=user_data.phone,
        password_hash=hash_password(user_data.password),
        status='active'
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )

@app.put("/api/v1/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate, db: Session = Depends(get_db)):
    """更新用户"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if user_data.username:
        user.username = user_data.username
    if user_data.email:
        user.email = user_data.email
    if user_data.phone:
        user.phone = user_data.phone
    if user_data.status:
        user.status = user_data.status
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )

@app.delete("/api/v1/users/{user_id}")
async def delete_user(user_id: str, db: Session = Depends(get_db)):
    """删除用户"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    db.delete(user)
    db.commit()
    return {"success": True, "message": "用户已删除"}

@app.post("/api/v1/users/{user_id}/reset-password")
async def reset_user_password(user_id: str, db: Session = Depends(get_db)):
    """重置用户密码为默认密码 123456"""
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的用户ID格式")
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password("123456")
    user.password_changed = False
    user.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "密码已重置为 123456"}

@app.post("/api/v1/admin/create-admin", response_model=AdminCreateResponse)
async def create_admin(
    request: AdminCreateRequest,
    current_user_id: str = Query(..., description="当前用户ID"),
    db: Session = Depends(get_db)
):
    """
    创建管理员账号
    
    需求：6.4 - 只有超级管理员可以创建管理员
    
    Args:
        request: 管理员创建请求
        current_user_id: 当前用户ID（从认证Token中获取）
        db: 数据库会话
        
    Returns:
        创建的管理员信息
        
    Raises:
        HTTPException: 如果当前用户不是超级管理员或创建失败
    """
    from services.permission.main import is_super_admin
    
    # 验证当前用户是否为超级管理员
    if not is_super_admin(current_user_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员可以创建管理员账号"
        )
    
    # 验证邮箱或手机号至少提供一个
    if not request.email and not request.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱或手机号至少提供一个"
        )
    
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在"
        )
    
    # 检查邮箱是否已存在
    if request.email:
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱已存在"
            )
    
    # 检查手机号是否已存在
    if request.phone:
        existing_user = db.query(User).filter(User.phone == request.phone).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="手机号已存在"
            )
    
    # 创建管理员用户
    admin_user = User(
        username=request.username,
        email=request.email,
        phone=request.phone,
        password_hash=hash_password(request.password),
        status='active',
        password_changed=False  # 首次登录需要修改密码
    )
    
    db.add(admin_user)
    db.flush()  # 获取用户ID
    
    # 查找admin角色
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        # 如果admin角色不存在，回滚并返回错误
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="系统角色未初始化，请先运行系统初始化脚本"
        )
    
    # 为用户分配admin角色
    user_role = UserRole(
        user_id=admin_user.id,
        role_id=admin_role.id,
        created_at=datetime.utcnow()
    )
    db.add(user_role)
    
    # 提交事务
    db.commit()
    db.refresh(admin_user)
    
    return AdminCreateResponse(
        success=True,
        message="管理员账号创建成功",
        user_id=str(admin_user.id),
        username=admin_user.username
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
