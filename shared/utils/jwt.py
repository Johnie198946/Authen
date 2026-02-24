"""
JWT Token工具模块
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
from jose import JWTError, jwt
from shared.config import settings


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建Access Token
    
    Args:
        data: Token载荷数据
        expires_delta: 过期时间增量
        
    Returns:
        JWT Token字符串
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": settings.APP_NAME
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict) -> str:
    """
    创建Refresh Token
    
    Args:
        data: Token载荷数据
        
    Returns:
        JWT Token字符串
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": settings.APP_NAME
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_id_token(user_data: Dict, client_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建OpenID Connect ID Token
    
    Args:
        user_data: 用户信息数据（包含sub, email, username等）
        client_id: 客户端应用ID
        expires_delta: 过期时间增量
        
    Returns:
        JWT ID Token字符串
    """
    to_encode = user_data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": settings.APP_NAME,
        "aud": client_id  # OpenID Connect要求ID Token包含audience
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str, audience: Optional[str] = None) -> Optional[Dict]:
    """
    解码并验证Token
    
    Args:
        token: JWT Token字符串
        audience: 可选的audience验证（用于ID Token）
        
    Returns:
        Token载荷数据，验证失败返回None
    """
    try:
        options = {"verify_aud": False}  # 默认不验证audience，因为不是所有token都有aud
        if audience:
            options = {"verify_aud": True}
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM],
                audience=audience,
                options=options
            )
        else:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM],
                options=options
            )
        return payload
    except JWTError as e:
        # 可以记录错误日志用于调试
        # print(f"JWT decode error: {e}")
        return None
