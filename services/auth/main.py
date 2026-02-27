"""
认证服务主入口
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import uuid
from shared.database import get_db
from shared.models.user import User
from shared.utils.crypto import hash_password, verify_password
from shared.utils.jwt import create_access_token, create_refresh_token
from shared.utils.validators import validate_password, validate_username
from shared.utils.sso_session import create_sso_session
from shared.redis_client import get_redis
from shared.config import settings
from shared.middleware.api_logger import APILoggerMiddleware
from shared.utils.health_check import check_overall_health

app = FastAPI(
    title="认证服务",
    description="统一身份认证和权限管理平台 - 认证服务",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加API日志中间件
app.add_middleware(APILoggerMiddleware)


# ==================== 请求/响应模型 ====================

class EmailRegisterRequest(BaseModel):
    """邮箱注册请求"""
    email: EmailStr
    password: str
    username: str
    verification_code: str


class EmailRegisterResponse(BaseModel):
    """邮箱注册响应"""
    success: bool
    message: str
    user_id: str


class LoginRequest(BaseModel):
    """登录请求"""
    identifier: str  # 邮箱或手机号
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    sso_session_token: str  # SSO会话令牌
    token_type: str = "Bearer"
    expires_in: int
    user: dict


class RefreshTokenRequest(BaseModel):
    """刷新Token请求"""
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """刷新Token响应"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class PhoneRegisterRequest(BaseModel):
    """手机注册请求"""
    phone: str
    password: str
    username: str
    verification_code: str


class PhoneRegisterResponse(BaseModel):
    """手机注册响应"""
    success: bool
    message: str
    user_id: str


class SendSMSRequest(BaseModel):
    """发送短信验证码请求"""
    phone: str


class OAuthCallbackRequest(BaseModel):
    """OAuth回调请求"""
    code: str
    redirect_uri: str


class OAuthResponse(BaseModel):
    """OAuth认证响应"""
    access_token: str
    refresh_token: str
    sso_session_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: dict
    is_new_user: bool  # 是否是新用户

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str

class ChangePasswordResponse(BaseModel):
    """修改密码响应"""
    success: bool
    message: str

class FirstLoginCheckResponse(BaseModel):
    """首次登录检查响应"""
    requires_password_change: bool
    message: str


class SendEmailCodeRequest(BaseModel):
    """发送邮箱验证码请求"""
    email: str


class PhoneCodeLoginRequest(BaseModel):
    """手机验证码登录请求"""
    phone: str
    code: str


class EmailCodeLoginRequest(BaseModel):
    """邮箱验证码登录请求"""
    email: str
    code: str


# ==================== 验证码辅助函数 ====================

def generate_verification_code() -> str:
    """生成 6 位数字验证码"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def check_rate_limit(redis_client, code_type: str, target: str) -> bool:
    """检查验证码发送频率限制，返回 True 表示被限制"""
    return redis_client.exists(f"code_rate:{code_type}:{target}")


def set_rate_limit(redis_client, code_type: str, target: str):
    """设置频率限制标记，60 秒 TTL"""
    redis_client.setex(f"code_rate:{code_type}:{target}", 60, "1")


def store_verification_code(redis_client, key: str, code: str, ttl: int = 300):
    """存储验证码到 Redis"""
    redis_client.setex(key, ttl, code)


def verify_and_delete_code(redis_client, key: str, submitted_code: str) -> bool:
    """验证并删除验证码，返回是否匹配"""
    stored = redis_client.get(key)
    if not stored or stored != submitted_code:
        return False
    redis_client.delete(key)
    return True


# ==================== API端点 ====================

@app.get("/")
async def root():
    """根路径"""
    return {"service": "认证服务", "status": "running"}


@app.get("/health")
async def health_check():
    """
    系统健康检查端点
    
    需求：13.4 - 提供系统健康检查接口
    
    检查以下组件的健康状态：
    - 数据库连接
    - Redis连接
    - RabbitMQ连接
    
    Returns:
        健康状态信息，包括各组件的状态和响应时间
    """
    health_status = check_overall_health()
    
    # 根据健康状态设置HTTP状态码
    if health_status["status"] == "healthy":
        status_code = 200
    elif health_status["status"] == "degraded":
        status_code = 200  # 部分可用仍返回200
    else:
        status_code = 503  # 服务不可用
    
    return JSONResponse(
        status_code=status_code,
        content=health_status
    )


@app.get("/api/v1/auth/csrf-token")
async def get_csrf_token():
    """
    获取CSRF Token
    
    需求：11.2 - 实现CSRF保护机制
    
    生成并返回一个新的CSRF Token，前端应该在所有状态改变请求中包含此Token。
    
    Returns:
        包含CSRF Token的响应
    """
    from shared.utils.csrf import generate_csrf_token, store_csrf_token
    
    # 生成CSRF Token
    csrf_token = generate_csrf_token()
    
    # 存储Token到Redis（可选，用于一次性Token验证）
    store_csrf_token(csrf_token)
    
    return {
        "csrf_token": csrf_token,
        "expires_in": 3600  # 1小时
    }


@app.post("/api/v1/auth/register/email", response_model=EmailRegisterResponse)
async def register_with_email(
    request: EmailRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    邮箱验证码注册

    需求：4.1–4.6 - 使用邮箱验证码完成注册，验证通过后直接激活账号
    """
    # 验证验证码
    redis = get_redis()
    if not verify_and_delete_code(redis, f"email_code:{request.email}", request.verification_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码无效或已过期"
        )

    # 检查邮箱是否已存在
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="邮箱已被注册"
        )

    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已被使用"
        )

    # 验证用户名
    is_valid, error_msg = validate_username(request.username)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # 验证密码强度
    is_valid, error_msg = validate_password(request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # 创建用户（验证码已验证，直接激活）
    hashed_password = hash_password(request.password)
    new_user = User(
        username=request.username,
        email=request.email,
        password_hash=hashed_password,
        status='active'
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return EmailRegisterResponse(
        success=True,
        message="注册成功",
        user_id=str(new_user.id)
    )


@app.get("/api/v1/auth/verify-email")
async def verify_email(
    token: str,
    db: Session = Depends(get_db)
):
    """
    验证邮箱
    
    需求：1.1 - 用户点击验证链接后激活账号
    """
    redis = get_redis()
    user_id = redis.get(f"email_verification:{token}")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证令牌无效或已过期"
        )
    
    # 更新用户状态为已激活
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    user.status = 'active'
    db.commit()
    
    # 删除验证令牌
    redis.delete(f"email_verification:{token}")
    
    return {"success": True, "message": "邮箱验证成功"}


@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    用户登录
    
    需求：1.4 - 用户使用任一认证方式登录时，生成Access Token和Refresh Token
    需求：1.6 - 连续输入错误密码5次后锁定账号15分钟
    """
    # 查找用户（通过用户名、邮箱或手机号）
    user = db.query(User).filter(
        (User.username == request.identifier) | (User.email == request.identifier) | (User.phone == request.identifier)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 检查账号是否被锁定
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining_time = (user.locked_until - datetime.utcnow()).seconds // 60
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账号已被锁定，请在{remaining_time}分钟后重试"
        )
    
    # 验证密码
    if not verify_password(request.password, user.password_hash):
        # 增加失败次数
        user.failed_login_attempts += 1
        
        # 如果失败次数达到5次，锁定账号15分钟
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
            user.status = 'locked'
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="密码错误次数过多，账号已被锁定15分钟"
            )
        
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"用户名或密码错误（剩余尝试次数：{5 - user.failed_login_attempts}）"
        )
    
    # 登录成功，重置失败次数
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    if user.status == 'locked':
        user.status = 'active'
    db.commit()
    
    # 创建SSO全局会话
    # 需求：2.1 - 用户在任一应用登录成功时创建全局会话
    sso_session = create_sso_session(str(user.id), db)
    
    # 生成Token
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        sso_session_token=sso_session.session_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "requires_password_change": not user.password_changed  # 添加密码修改标记
        }
    )


@app.get("/api/v1/auth/check-first-login/{user_id}", response_model=FirstLoginCheckResponse)
async def check_first_login(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    检查用户是否首次登录（需要修改密码）
    
    需求：6.6 - 首次登录后强制修改默认密码
    
    Args:
        user_id: 用户ID
        db: 数据库会话
        
    Returns:
        是否需要修改密码
    """
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的用户ID格式"
        )
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    requires_change = not user.password_changed
    
    return FirstLoginCheckResponse(
        requires_password_change=requires_change,
        message="需要修改密码" if requires_change else "密码已修改"
    )


@app.post("/api/v1/auth/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: ChangePasswordRequest,
    user_id: str = Query(..., description="用户ID"),
    db: Session = Depends(get_db)
):
    """
    修改密码
    
    需求：6.6 - 实现强制密码修改流程
    
    Args:
        request: 修改密码请求
        user_id: 用户ID（从认证Token中获取）
        db: 数据库会话
        
    Returns:
        修改结果
    """
    from shared.utils.validators import validate_password
    
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的用户ID格式"
        )
    
    # 查找用户
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    # 验证旧密码
    if not verify_password(request.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="旧密码不正确"
        )
    
    # 验证新密码强度
    is_valid, error_msg = validate_password(request.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # 检查新密码是否与旧密码相同
    if verify_password(request.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与旧密码相同"
        )
    
    # 更新密码
    user.password_hash = hash_password(request.new_password)
    user.password_changed = True
    user.updated_at = datetime.utcnow()
    
    # 撤销所有现有的Refresh Token（强制重新登录）
    from shared.models.user import RefreshToken
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False
    ).update({
        "revoked": True,
        "revoked_at": datetime.utcnow()
    })
    
    db.commit()
    
    return ChangePasswordResponse(
        success=True,
        message="密码修改成功，请重新登录"
    )


@app.post("/api/v1/auth/refresh", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """
    刷新Access Token
    
    需求：1.5 - 使用Refresh Token获取新的Access Token
    """
    from shared.utils.jwt import decode_token
    
    # 验证Refresh Token
    payload = decode_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token无效或已过期"
        )
    
    # 生成新的Access Token
    token_data = {
        "sub": payload["sub"]
    }
    access_token = create_access_token(token_data)
    
    return RefreshTokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@app.post("/api/v1/auth/logout")
async def logout():
    """
    用户登出
    
    需求：2.3 - 登出时撤销Refresh Token
    """
    # TODO: 实现Token撤销逻辑
    return {"success": True, "message": "登出成功"}


@app.post("/api/v1/auth/send-sms")
async def send_sms_code(request: SendSMSRequest):
    """
    发送短信验证码
    
    需求：1.2 - 发送短信验证码
    """
    from shared.utils.validators import validate_phone
    
    # 验证手机号格式
    if not validate_phone(request.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号格式不正确"
        )
    
    # 获取 Redis 客户端
    redis = get_redis()
    
    # 检查频率限制
    if check_rate_limit(redis, "sms", request.phone):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="发送过于频繁，请60秒后重试"
        )
    
    # 生成6位验证码
    verification_code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    # 存储到Redis，5分钟过期
    redis.setex(
        f"sms_code:{request.phone}",
        300,  # 5分钟
        verification_code
    )
    
    # 设置频率限制
    set_rate_limit(redis, "sms", request.phone)
    
    # TODO: 调用通知服务发送短信
    # 开发环境下直接返回验证码（生产环境应该删除）
    return {
        "success": True,
        "message": "验证码已发送",
        "code": verification_code if settings.DEBUG else None
    }


@app.post("/api/v1/auth/send-email-code")
async def send_email_code(request: SendEmailCodeRequest):
    """
    发送邮箱验证码

    需求：1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.1, 7.2, 7.3
    """
    from shared.utils.validators import validate_email
    from services.notification.email_service import EmailService

    # 校验邮箱格式
    if not validate_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱格式不正确"
        )

    redis = get_redis()

    # 检查频率限制
    if check_rate_limit(redis, "email", request.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="发送过于频繁，请60秒后重试"
        )

    # 生成 6 位验证码并存储到 Redis
    code = generate_verification_code()
    store_verification_code(redis, f"email_code:{request.email}", code, ttl=300)

    # 设置频率限制
    set_rate_limit(redis, "email", request.email)

    # 调用 EmailService 发送验证码邮件
    email_svc = EmailService()
    send_ok = email_svc.send_verification_code_email(request.email, code)
    if not send_ok and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="邮件发送失败，请稍后重试"
        )

    return {
        "success": True,
        "message": "验证码已发送" if send_ok else "验证码已生成（开发模式，邮件未发送）",
        "code": code if settings.DEBUG else None
    }


@app.post("/api/v1/auth/login/phone-code", response_model=LoginResponse)
async def login_with_phone_code(
    request: PhoneCodeLoginRequest,
    db: Session = Depends(get_db)
):
    """
    手机验证码登录

    需求：2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
    """
    redis = get_redis()

    # 验证验证码
    if not verify_and_delete_code(redis, f"sms_code:{request.phone}", request.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码无效或已过期"
        )

    # 查找用户
    user = db.query(User).filter(User.phone == request.phone).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    # 检查账号锁定
    if user.status == 'locked' or (user.locked_until and user.locked_until > datetime.utcnow()):
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining_time = (user.locked_until - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"账号已被锁定，请在{remaining_time}分钟后重试"
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被锁定"
        )

    # 检查账号未激活
    if user.status == 'pending_verification':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号未激活"
        )

    # 登录成功：重置失败次数、更新最后登录时间
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()

    # 创建SSO全局会话
    sso_session = create_sso_session(str(user.id), db)

    # 生成Token
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        sso_session_token=sso_session.session_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "requires_password_change": not user.password_changed
        }
    )

@app.post("/api/v1/auth/login/email-code", response_model=LoginResponse)
async def login_with_email_code(
    request: EmailCodeLoginRequest,
    db: Session = Depends(get_db)
):
    """
    邮箱验证码登录

    需求：3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
    """
    redis = get_redis()

    # 验证验证码
    if not verify_and_delete_code(redis, f"email_code:{request.email}", request.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码无效或已过期"
        )

    # 查找用户
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    # 检查账号锁定
    if user.status == 'locked' or (user.locked_until and user.locked_until > datetime.utcnow()):
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining_time = (user.locked_until - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"账号已被锁定，请在{remaining_time}分钟后重试"
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被锁定"
        )

    # 检查账号未激活
    if user.status == 'pending_verification':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号未激活"
        )

    # 登录成功：重置失败次数、更新最后登录时间
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    db.commit()

    # 创建SSO全局会话
    sso_session = create_sso_session(str(user.id), db)

    # 生成Token
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        sso_session_token=sso_session.session_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "requires_password_change": not user.password_changed
        }
    )



@app.post("/api/v1/auth/register/phone", response_model=PhoneRegisterResponse)
async def register_with_phone(
    request: PhoneRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    手机注册
    
    需求：1.2 - 用户选择手机注册时，发送短信验证码并在验证后创建账号
    """
    from shared.utils.validators import validate_phone
    
    # 验证手机号格式
    if not validate_phone(request.phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号格式不正确"
        )
    
    # 验证用户名
    is_valid, error_msg = validate_username(request.username)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # 验证密码强度
    is_valid, error_msg = validate_password(request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # 验证短信验证码
    redis = get_redis()
    stored_code = redis.get(f"sms_code:{request.phone}")
    
    if not stored_code or stored_code != request.verification_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码无效或已过期"
        )
    
    # 检查手机号是否已存在
    existing_user = db.query(User).filter(User.phone == request.phone).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="手机号已被注册"
        )
    
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已被使用"
        )
    
    # 创建用户（手机注册直接激活）
    hashed_password = hash_password(request.password)
    new_user = User(
        username=request.username,
        phone=request.phone,
        password_hash=hashed_password,
        status='active'
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 删除验证码
    redis.delete(f"sms_code:{request.phone}")
    
    return PhoneRegisterResponse(
        success=True,
        message="注册成功",
        user_id=str(new_user.id)
    )


@app.post("/api/v1/auth/oauth/{provider}", response_model=OAuthResponse)
async def oauth_authenticate(
    provider: str,
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db)
):
    """
    OAuth认证
    
    需求：1.3 - 通过OAuth协议完成认证并创建或关联账号
    支持的提供商：wechat, alipay, google, apple
    """
    from shared.utils.oauth_client import get_oauth_client
    from shared.models.user import OAuthAccount
    
    # 验证提供商
    supported_providers = ["wechat", "alipay", "google", "apple"]
    if provider not in supported_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的OAuth提供商: {provider}"
        )
    
    # 从环境变量获取OAuth配置
    oauth_config = {
        "wechat": {
            "client_id": settings.WECHAT_APP_ID,
            "client_secret": settings.WECHAT_APP_SECRET,
        },
        "alipay": {
            "client_id": settings.ALIPAY_APP_ID,
            "client_secret": settings.ALIPAY_APP_SECRET,
        },
        "google": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
        },
        "apple": {
            "client_id": settings.APPLE_CLIENT_ID,
            "client_secret": settings.APPLE_CLIENT_SECRET,
        }
    }
    
    config = oauth_config.get(provider, {})
    if not config.get("client_id") or not config.get("client_secret"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider} OAuth配置未设置"
        )
    
    try:
        # 创建OAuth客户端
        oauth_client = get_oauth_client(
            provider=provider,
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            redirect_uri=request.redirect_uri
        )
        
        # 用授权码交换访问令牌
        token_data = await oauth_client.exchange_code_for_token(request.code)
        
        # 获取用户信息
        if provider == "wechat":
            user_info = await oauth_client.get_user_info(
                token_data["access_token"],
                openid=token_data.get("openid")
            )
        elif provider == "alipay":
            user_info = await oauth_client.get_user_info(
                token_data["access_token"],
                user_id=token_data.get("user_id")
            )
        elif provider == "apple":
            user_info = await oauth_client.get_user_info(
                token_data["access_token"],
                id_token=token_data.get("id_token")
            )
        else:
            user_info = await oauth_client.get_user_info(token_data["access_token"])
        
        provider_user_id = user_info["provider_user_id"]
        
        # 查找是否已存在OAuth账号
        oauth_account = db.query(OAuthAccount).filter(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id
        ).first()
        
        is_new_user = False
        
        if oauth_account:
            # 已存在OAuth账号，更新令牌
            user = oauth_account.user
            oauth_account.access_token = token_data["access_token"]
            oauth_account.refresh_token = token_data.get("refresh_token")
            if token_data.get("expires_in"):
                oauth_account.token_expires_at = datetime.utcnow() + timedelta(
                    seconds=token_data["expires_in"]
                )
            oauth_account.updated_at = datetime.utcnow()
            db.commit()
        else:
            # 新OAuth账号，需要创建或关联用户
            user = None
            
            # 如果有邮箱，尝试通过邮箱关联现有用户
            if user_info.get("email"):
                user = db.query(User).filter(User.email == user_info["email"]).first()
            
            if not user:
                # 创建新用户
                is_new_user = True
                
                # 生成唯一用户名
                base_username = user_info["username"]
                username = base_username
                counter = 1
                while db.query(User).filter(User.username == username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                # 创建用户（OAuth用户可能没有邮箱，使用占位符）
                user = User(
                    username=username,
                    email=user_info.get("email") or f"{provider}_{provider_user_id}@oauth.placeholder",
                    status='active'  # OAuth用户直接激活
                )
                db.add(user)
                db.flush()  # 获取user.id
            
            # 创建OAuth账号关联
            oauth_account = OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_expires_at=datetime.utcnow() + timedelta(
                    seconds=token_data.get("expires_in", 3600)
                ) if token_data.get("expires_in") else None
            )
            db.add(oauth_account)
            db.commit()
            db.refresh(user)
        
        # 更新最后登录时间
        user.last_login_at = datetime.utcnow()
        db.commit()
        
        # 创建SSO全局会话
        sso_session = create_sso_session(str(user.id), db)
        
        # 生成JWT Token
        token_payload = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email
        }
        
        access_token = create_access_token(token_payload)
        refresh_token = create_refresh_token({"sub": str(user.id)})
        
        return OAuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            sso_session_token=sso_session.session_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={
                "id": str(user.id),
                "username": user.username,
                "email": user.email
            },
            is_new_user=is_new_user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth认证失败: {str(e)}"
        )


@app.get("/api/v1/auth/oauth/{provider}/authorize")
async def oauth_authorize(provider: str, redirect_uri: str, state: str = None):
    """
    获取OAuth授权URL
    
    需求：1.3 - 重定向到OAuth提供商授权页面
    """
    from shared.utils.oauth_client import get_oauth_client
    import secrets
    
    # 验证提供商
    supported_providers = ["wechat", "alipay", "google", "apple"]
    if provider not in supported_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的OAuth提供商: {provider}"
        )
    
    # 从环境变量获取OAuth配置
    oauth_config = {
        "wechat": {
            "client_id": settings.WECHAT_APP_ID,
            "client_secret": settings.WECHAT_APP_SECRET,
        },
        "alipay": {
            "client_id": settings.ALIPAY_APP_ID,
            "client_secret": settings.ALIPAY_APP_SECRET,
        },
        "google": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
        },
        "apple": {
            "client_id": settings.APPLE_CLIENT_ID,
            "client_secret": settings.APPLE_CLIENT_SECRET,
        }
    }
    
    config = oauth_config.get(provider, {})
    if not config.get("client_id") or not config.get("client_secret"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{provider} OAuth配置未设置"
        )
    
    try:
        # 创建OAuth客户端
        oauth_client = get_oauth_client(
            provider=provider,
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            redirect_uri=redirect_uri
        )
        
        # 生成state（如果未提供）
        if not state:
            state = secrets.token_urlsafe(32)
        
        # 获取授权URL
        auth_url = await oauth_client.get_authorization_url(state)
        
        return {
            "authorization_url": auth_url,
            "state": state
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取授权URL失败: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
