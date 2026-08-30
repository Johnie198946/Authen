"""
JWT工具模块
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import uuid

from jose import JWTError, jwt

from shared.config import settings


INTERACTIVE_HUMAN_AUTH_METHODS = {
    "pwd", "mfa", "passkey", "sms", "otp", "oidc", "oauth"
}


def human_principal_claims(auth_method: str) -> Dict:
    """Build auditable claims only for an interactive human authentication event."""
    normalized_method = str(auth_method or "").strip().lower()
    if normalized_method not in INTERACTIVE_HUMAN_AUTH_METHODS:
        raise ValueError("unsupported interactive human authentication method")
    return {
        "principal_type": "human",
        "amr": [normalized_method],
        "auth_time": int(datetime.now(timezone.utc).timestamp()),
    }


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建访问令牌

    Args:
        data: 要编码的数据
        expires_delta: 过期时间增量

    Returns:
        str: JWT令牌
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # 这些注册声明必须由发行方生成，不能由调用方覆盖。
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_ACCESS_AUDIENCE,
        "token_use": "access",
        "jti": str(uuid.uuid4()),
    })

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建刷新令牌

    Args:
        data: 要编码的数据
        expires_delta: 过期时间增量

    Returns:
        str: JWT令牌
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_REFRESH_AUDIENCE,
        "token_use": "refresh",
        "jti": str(uuid.uuid4()),
    })

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_id_token(data: Dict, client_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建OpenID Connect ID令牌

    Args:
        data: 要编码的用户数据
        client_id: 客户端ID
        expires_delta: 过期时间增量

    Returns:
        str: ID令牌
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": settings.JWT_ISSUER,
        "aud": client_id,
        "token_use": "id",
        "jti": str(uuid.uuid4()),
    })

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(
    token: str,
    audience: Optional[str] = None,
    token_use: Optional[str] = None,
) -> Optional[Dict]:
    """
    解码和验证JWT令牌。可选地强制 audience 和 token_use。

    Args:
        token: JWT令牌
        audience: 预期的受众
        token_use: 预期用途（access/refresh/id）

    Returns:
        Optional[Dict]: 解码后的数据，验证失败返回None
    """
    try:
        options = {"verify_aud": audience is not None}
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=audience,
            issuer=settings.JWT_ISSUER,
            options=options,
        )
        if token_use and payload.get("token_use") != token_use:
            return None
        return payload
    except JWTError:
        return None


def verify_token(token: str, audience: Optional[str] = None, token_use: Optional[str] = None) -> bool:
    """验证JWT令牌是否有效。"""
    return decode_token(token, audience, token_use) is not None
