"""
SSO会话管理工具函数
"""
import secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from shared.models.user import SSOSession
from shared.config import settings


def create_sso_session(user_id, db: Session) -> SSOSession:
    """
    创建SSO全局会话
    
    需求：2.1 - 用户在任一应用登录成功时创建全局会话
    
    Args:
        user_id: 用户ID (可以是字符串或UUID对象)
        db: 数据库会话
        
    Returns:
        SSOSession: 创建的SSO会话对象
    """
    import uuid as uuid_module
    
    # 确保user_id是UUID对象
    if isinstance(user_id, str):
        user_id = uuid_module.UUID(user_id)
    
    # 生成唯一的会话令牌
    session_token = secrets.token_urlsafe(64)
    
    # 计算过期时间（默认24小时）
    expires_at = datetime.utcnow() + timedelta(hours=settings.SSO_SESSION_EXPIRE_HOURS)
    
    # 创建会话记录
    sso_session = SSOSession(
        user_id=user_id,
        session_token=session_token,
        expires_at=expires_at,
        last_activity_at=datetime.utcnow()
    )
    
    db.add(sso_session)
    db.commit()
    db.refresh(sso_session)
    
    return sso_session


def get_sso_session(session_token: str, db: Session) -> SSOSession:
    """
    查询SSO会话
    
    需求：2.2 - 其他应用可以查询SSO会话来验证用户身份
    
    Args:
        session_token: 会话令牌
        db: 数据库会话
        
    Returns:
        SSOSession: SSO会话对象，如果不存在或已过期返回None
    """
    session = db.query(SSOSession).filter(
        SSOSession.session_token == session_token
    ).first()
    
    if not session:
        return None
    
    # 检查会话是否过期
    if session.expires_at < datetime.utcnow():
        # 删除过期会话
        db.delete(session)
        db.commit()
        return None
    
    return session


def validate_sso_session(session_token: str, db: Session) -> tuple[bool, str, SSOSession]:
    """
    验证SSO会话是否有效
    
    需求：2.2 - 验证SSO会话的有效性
    
    Args:
        session_token: 会话令牌
        db: 数据库会话
        
    Returns:
        tuple: (是否有效, 错误消息, 会话对象)
    """
    if not session_token:
        return False, "会话令牌不能为空", None
    
    session = get_sso_session(session_token, db)
    
    if not session:
        return False, "会话不存在或已过期", None
    
    return True, "", session


def update_session_activity(session_token: str, db: Session) -> bool:
    """
    更新会话活动时间
    
    需求：2.1, 2.2 - 更新会话的最后活动时间，用于跟踪用户活动
    
    Args:
        session_token: 会话令牌
        db: 数据库会话
        
    Returns:
        bool: 是否更新成功
    """
    session = db.query(SSOSession).filter(
        SSOSession.session_token == session_token
    ).first()
    
    if not session:
        return False
    
    # 检查会话是否过期
    if session.expires_at < datetime.utcnow():
        # 删除过期会话
        db.delete(session)
        db.commit()
        return False
    
    # 更新最后活动时间
    session.last_activity_at = datetime.utcnow()
    db.commit()
    
    return True


def delete_sso_session(session_token: str, db: Session) -> bool:
    """
    删除SSO会话（用于登出）
    
    需求：2.3 - 用户登出时终止全局会话
    
    Args:
        session_token: 会话令牌
        db: 数据库会话
        
    Returns:
        bool: 是否删除成功
    """
    session = db.query(SSOSession).filter(
        SSOSession.session_token == session_token
    ).first()
    
    if not session:
        return False
    
    db.delete(session)
    db.commit()
    
    return True


def delete_user_sso_sessions(user_id: str, db: Session) -> int:
    """
    删除用户的所有SSO会话（用于全局登出）
    
    需求：2.3 - 用户在任一应用登出时终止所有应用的会话
    
    Args:
        user_id: 用户ID
        db: 数据库会话
        
    Returns:
        int: 删除的会话数量
    """
    sessions = db.query(SSOSession).filter(
        SSOSession.user_id == user_id
    ).all()
    
    count = len(sessions)
    
    for session in sessions:
        db.delete(session)
    
    db.commit()
    
    return count


def get_user_active_sessions(user_id: str, db: Session) -> list[SSOSession]:
    """
    获取用户的所有活跃会话
    
    Args:
        user_id: 用户ID
        db: 数据库会话
        
    Returns:
        list[SSOSession]: 活跃会话列表
    """
    sessions = db.query(SSOSession).filter(
        SSOSession.user_id == user_id,
        SSOSession.expires_at > datetime.utcnow()
    ).all()
    
    return sessions
