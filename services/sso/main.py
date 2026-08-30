"""
SSO服务主入口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, status, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import secrets
from shared.database import get_db
from shared.models.user import User, SSOSession
from shared.utils.jwt import create_access_token, create_id_token, decode_token, human_principal_claims
from shared.utils.sso_session import (
    get_sso_session,
    validate_sso_session,
    update_session_activity,
    delete_sso_session,
    delete_user_sso_sessions
)
from shared.redis_client import get_redis
from shared.config import settings

app = FastAPI(title="SSO服务", description="单点登录服务", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenRequest(BaseModel):
    grant_type: str
    code: str
    client_id: str
    client_secret: str
    redirect_uri: str

class TokenResponse(BaseModel):
    access_token: str
    id_token: str
    token_type: str = "Bearer"
    expires_in: int


def _registered_sso_client(client_id: str, redirect_uri: str) -> dict:
    """Return an explicitly configured client and require an exact redirect URI."""
    try:
        clients = json.loads(settings.SSO_CLIENTS_JSON or "{}")
    except (TypeError, ValueError):
        raise HTTPException(status_code=503, detail="SSO客户端配置无效")
    client = clients.get(client_id) if isinstance(clients, dict) else None
    if not isinstance(client, dict):
        raise HTTPException(status_code=400, detail="未注册的SSO客户端")
    allowed_redirects = client.get("redirect_uris") or []
    if redirect_uri not in allowed_redirects:
        raise HTTPException(status_code=400, detail="redirect_uri未注册")
    return client

@app.get("/")
async def root():
    return {"service": "SSO服务", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "sso"}

@app.get("/api/v1/sso/authorize")
async def authorize(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query(...),
    scope: str = Query(default="openid profile email"),
    state: str = Query(default=None),
    session_token: str = Header(..., alias="X-SSO-Session"),
    db: Session = Depends(get_db)
):
    """OAuth 2.0授权端点"""
    if response_type != "code":
        raise HTTPException(status_code=400, detail="不支持的response_type")
    
    _registered_sso_client(client_id, redirect_uri)
    is_valid, error_msg, session = validate_sso_session(session_token, db)
    if not is_valid or session is None:
        raise HTTPException(status_code=401, detail=error_msg or "用户未登录")
    
    # 生成授权码
    auth_code = secrets.token_urlsafe(32)
    redis = get_redis()
    # JSON 避免 redirect_uri 中的冒号造成解析歧义；短 TTL 且只能交换一次。
    redis.setex(
        f"auth_code:{auth_code}",
        120,
        json.dumps({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "user_id": str(session.user_id),
        }, separators=(",", ":")),
    )
    
    return {"authorization_code": auth_code, "state": state}

@app.post("/api/v1/sso/token", response_model=TokenResponse)
async def token(request: TokenRequest, db: Session = Depends(get_db)):
    """Token端点 - 交换授权码获取Token"""
    if request.grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="不支持的grant_type")
    
    client = _registered_sso_client(request.client_id, request.redirect_uri)
    expected_secret = str(client.get("client_secret") or "")
    if not expected_secret or not secrets.compare_digest(request.client_secret, expected_secret):
        raise HTTPException(status_code=401, detail="客户端认证失败")

    redis = get_redis()
    key = f"auth_code:{request.code}"
    # Redis >= 6.2 GETDEL 保证授权码不会被并发重放。
    stored_data = redis.getdel(key)
    if not stored_data:
        raise HTTPException(status_code=400, detail="无效的授权码")
    
    try:
        stored = json.loads(stored_data)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="授权码数据格式错误")

    if stored.get("client_id") != request.client_id or stored.get("redirect_uri") != request.redirect_uri:
        raise HTTPException(status_code=400, detail="客户端信息不匹配")
    user_id = stored.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="授权码数据格式错误")
    
    # 从数据库获取用户信息
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 生成Access Token
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email,
        "client_id": request.client_id,
        **human_principal_claims("oidc"),
    }
    access_token = create_access_token(token_data)
    
    # 生成ID Token（OpenID Connect）
    id_token_data = {
        "sub": str(user.id),
        "name": user.username,
        "email": user.email,
        "email_verified": user.email is not None,
        "preferred_username": user.username
    }
    id_token = create_id_token(id_token_data, request.client_id)
    
    return TokenResponse(
        access_token=access_token,
        id_token=id_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@app.get("/api/v1/sso/userinfo")
async def userinfo(authorization: str = Header(None), db: Session = Depends(get_db)):
    """UserInfo端点 - 返回用户信息（OpenID Connect）"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权")
    
    token = authorization.split(" ")[1]
    payload = decode_token(
        token,
        audience=settings.JWT_ACCESS_AUDIENCE,
        token_use="access",
    )
    if not payload:
        raise HTTPException(status_code=401, detail="Token无效")
    
    # 从Token中获取用户ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token中缺少用户ID")
    
    # 从数据库获取用户信息
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 返回OpenID Connect标准的用户信息
    return {
        "sub": str(user.id),
        "name": user.username,
        "preferred_username": user.username,
        "email": user.email,
        "email_verified": user.email is not None,
        "phone_number": user.phone,
        "phone_number_verified": user.phone is not None,
        "updated_at": int(user.updated_at.timestamp()) if user.updated_at else None
    }

@app.get("/api/v1/sso/session/validate")
async def validate_session(
    session_token: str = Query(..., description="SSO会话令牌"),
    db: Session = Depends(get_db)
):
    """
    验证SSO会话
    
    需求：2.2 - 其他应用可以查询和验证SSO会话
    需求：2.4 - 返回用户认证状态和基本信息
    """
    is_valid, error_msg, session = validate_sso_session(session_token, db)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg
        )
    
    # 更新会话活动时间
    update_session_activity(session_token, db)
    
    # 获取用户信息
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return {
        "valid": True,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "phone": user.phone
        },
        "session": {
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "last_activity_at": session.last_activity_at.isoformat()
        }
    }


@app.get("/api/v1/sso/session/info")
async def get_session_info(
    session_token: str = Query(..., description="SSO会话令牌"),
    db: Session = Depends(get_db)
):
    """
    查询SSO会话信息
    
    需求：2.2 - 查询SSO会话详细信息
    """
    session = get_sso_session(session_token, db)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或已过期"
        )
    
    # 获取用户信息
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return {
        "session_id": str(session.id),
        "user_id": str(session.user_id),
        "username": user.username,
        "email": user.email,
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "last_activity_at": session.last_activity_at.isoformat()
    }


@app.post("/api/v1/sso/session/update-activity")
async def update_activity(
    session_token: str = Query(..., description="SSO会话令牌"),
    db: Session = Depends(get_db)
):
    """
    更新会话活动时间
    
    需求：2.1, 2.2 - 更新会话的最后活动时间
    """
    success = update_session_activity(session_token, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或已过期"
        )
    
    return {
        "success": True,
        "message": "会话活动时间已更新"
    }


@app.post("/api/v1/sso/logout")
async def logout(
    session_token: str = Query(..., description="SSO会话令牌"),
    db: Session = Depends(get_db)
):
    """
    全局登出
    
    需求：2.3 - 用户在任一应用登出时终止全局会话
    """
    success = delete_sso_session(session_token, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )
    
    return {"success": True, "message": "全局登出成功"}


@app.post("/api/v1/sso/logout-all")
async def logout_all(
    session_token: str = Query(..., description="SSO会话令牌"),
    db: Session = Depends(get_db)
):
    """
    全局登出所有会话
    
    需求：2.3 - 用户在任一应用登出时终止所有应用的会话
    """
    # 首先验证会话并获取用户ID
    is_valid, error_msg, session = validate_sso_session(session_token, db)
    
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg
        )
    
    # 删除该用户的所有会话
    count = delete_user_sso_sessions(str(session.user_id), db)
    
    return {
        "success": True,
        "message": f"已登出所有会话",
        "sessions_deleted": count
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
