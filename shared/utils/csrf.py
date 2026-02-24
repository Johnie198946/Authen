"""
CSRF保护工具

提供CSRF Token的生成、验证和管理功能。

需求：11.2 - 实现CSRF保护机制
"""
import secrets
import hashlib
import hmac
from typing import Optional
from datetime import datetime, timedelta
from shared.config import settings


# CSRF Token配置
CSRF_TOKEN_LENGTH = 32  # Token长度（字节）
CSRF_TOKEN_EXPIRE_MINUTES = 60  # Token有效期（分钟）


def generate_csrf_token(session_id: Optional[str] = None) -> str:
    """
    生成CSRF Token
    
    Args:
        session_id: 可选的会话ID，用于绑定Token到特定会话
        
    Returns:
        CSRF Token字符串
    """
    # 生成随机Token
    random_token = secrets.token_hex(CSRF_TOKEN_LENGTH)
    
    # 如果提供了session_id，将其与Token绑定
    if session_id:
        # 使用HMAC签名，防止Token被伪造
        signature = hmac.new(
            settings.JWT_SECRET_KEY.encode(),
            f"{random_token}:{session_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"{random_token}:{signature}"
    
    return random_token


def verify_csrf_token(
    token: str,
    session_id: Optional[str] = None
) -> bool:
    """
    验证CSRF Token
    
    Args:
        token: 要验证的CSRF Token
        session_id: 可选的会话ID，用于验证Token绑定
        
    Returns:
        Token是否有效
    """
    if not token:
        return False
    
    # 如果Token包含签名（带有session_id绑定）
    if ":" in token and session_id:
        try:
            random_token, signature = token.split(":", 1)
            
            # 重新计算签名
            expected_signature = hmac.new(
                settings.JWT_SECRET_KEY.encode(),
                f"{random_token}:{session_id}".encode(),
                hashlib.sha256
            ).hexdigest()
            
            # 使用常量时间比较，防止时序攻击
            return hmac.compare_digest(signature, expected_signature)
        except ValueError:
            return False
    
    # 简单Token验证（无session_id绑定）
    # 只检查Token格式是否正确
    return len(token) == CSRF_TOKEN_LENGTH * 2  # hex编码后长度翻倍


def store_csrf_token(token: str, user_id: Optional[str] = None) -> None:
    """
    存储CSRF Token到Redis
    
    Args:
        token: CSRF Token
        user_id: 可选的用户ID
    """
    from shared.redis_client import get_redis
    
    redis_client = get_redis()
    
    # 构建Redis key
    if user_id:
        key = f"csrf_token:{user_id}:{token}"
    else:
        key = f"csrf_token:{token}"
    
    # 存储Token，设置过期时间
    redis_client.setex(
        key,
        CSRF_TOKEN_EXPIRE_MINUTES * 60,
        "1"
    )


def validate_and_consume_csrf_token(
    token: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> bool:
    """
    验证并消费CSRF Token（一次性使用）
    
    Args:
        token: CSRF Token
        user_id: 可选的用户ID
        session_id: 可选的会话ID
        
    Returns:
        Token是否有效
    """
    from shared.redis_client import get_redis
    
    # 首先验证Token格式
    if not verify_csrf_token(token, session_id):
        return False
    
    redis_client = get_redis()
    
    # 构建Redis key
    if user_id:
        key = f"csrf_token:{user_id}:{token}"
    else:
        key = f"csrf_token:{token}"
    
    # 检查Token是否存在
    exists = redis_client.exists(key)
    
    if not exists:
        return False
    
    # 删除Token（一次性使用）
    redis_client.delete(key)
    
    return True


def get_csrf_token_from_request(request) -> Optional[str]:
    """
    从请求中提取CSRF Token
    
    优先级：
    1. X-CSRF-Token 请求头
    2. csrf_token 表单字段
    3. csrf_token 查询参数
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        CSRF Token或None
    """
    # 从请求头获取
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token
    
    # 从表单字段获取（需要异步处理）
    # 这里返回None，由中间件处理
    
    # 从查询参数获取
    token = request.query_params.get("csrf_token")
    if token:
        return token
    
    return None
