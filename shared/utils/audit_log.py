"""
审计日志工具模块

提供审计日志记录装饰器和辅助函数，用于记录系统中的敏感操作。

需求：6.5, 11.9, 13.1, 13.2 - 记录超级管理员操作、敏感操作审计日志
"""
from functools import wraps
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from fastapi import Request
from sqlalchemy.orm import Session
import uuid
import inspect
import json


def get_client_ip(request: Request) -> Optional[str]:
    """
    获取客户端IP地址
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        客户端IP地址
    """
    # 优先从X-Forwarded-For头获取（处理代理情况）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For可能包含多个IP，取第一个
        return forwarded_for.split(",")[0].strip()
    
    # 从X-Real-IP头获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # 从客户端直接获取
    if request.client:
        return request.client.host
    
    return None


def get_user_agent(request: Request) -> Optional[str]:
    """
    获取用户代理字符串
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        用户代理字符串
    """
    return request.headers.get("User-Agent")


def create_audit_log(
    db: Session,
    user_id: Optional[uuid.UUID],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[uuid.UUID] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    创建审计日志记录
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        action: 操作类型（如：login, logout, create_user, update_role等）
        resource_type: 资源类型（如：user, role, permission等）
        resource_id: 资源ID
        details: 操作详情（JSON格式）
        ip_address: IP地址
        user_agent: 用户代理字符串
    """
    from shared.models.system import AuditLog
    
    try:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.add(audit_log)
        db.commit()
    except Exception as e:
        # 审计日志记录失败不应该影响主业务流程
        # 记录错误但不抛出异常
        print(f"审计日志记录失败: {str(e)}")
        db.rollback()


def audit_log(
    action: str,
    resource_type: Optional[str] = None,
    get_resource_id: Optional[Callable] = None,
    get_details: Optional[Callable] = None
):
    """
    审计日志装饰器
    
    用于自动记录API端点的操作日志。装饰器会自动提取请求信息（IP地址、用户代理）
    和用户信息，并在操作完成后记录审计日志。
    
    Args:
        action: 操作类型（如：login, logout, create_user等）
        resource_type: 资源类型（如：user, role, permission等）
        get_resource_id: 从函数参数或返回值中提取资源ID的函数
        get_details: 从函数参数或返回值中提取详情的函数
        
    Example:
        @audit_log(
            action="create_user",
            resource_type="user",
            get_resource_id=lambda result: result.get("user_id"),
            get_details=lambda kwargs, result: {
                "username": kwargs.get("username"),
                "email": kwargs.get("email")
            }
        )
        async def create_user_endpoint(...):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 提取请求对象和数据库会话
            request: Optional[Request] = None
            db: Optional[Session] = None
            user_id: Optional[str] = None
            
            # 从参数中查找Request、Session和user_id
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            for param_name, param_value in bound_args.arguments.items():
                if isinstance(param_value, Request):
                    request = param_value
                elif isinstance(param_value, Session):
                    db = param_value
                elif param_name == "user_id" and isinstance(param_value, str):
                    user_id = param_value
            
            # 执行原函数
            result = await func(*args, **kwargs)
            
            # 记录审计日志
            if db is not None:
                try:
                    # 提取资源ID
                    resource_id = None
                    if get_resource_id:
                        try:
                            resource_id_str = get_resource_id(result)
                            if resource_id_str:
                                resource_id = uuid.UUID(resource_id_str)
                        except (ValueError, TypeError, AttributeError):
                            pass
                    
                    # 提取详情
                    details = None
                    if get_details:
                        try:
                            details = get_details(kwargs, result)
                        except Exception:
                            pass
                    
                    # 提取IP地址和用户代理
                    ip_address = None
                    user_agent_str = None
                    if request:
                        ip_address = get_client_ip(request)
                        user_agent_str = get_user_agent(request)
                    
                    # 转换user_id为UUID
                    user_uuid = None
                    if user_id:
                        try:
                            user_uuid = uuid.UUID(user_id)
                        except (ValueError, TypeError):
                            pass
                    
                    # 创建审计日志
                    create_audit_log(
                        db=db,
                        user_id=user_uuid,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        details=details,
                        ip_address=ip_address,
                        user_agent=user_agent_str
                    )
                except Exception as e:
                    # 审计日志记录失败不应该影响主业务流程
                    print(f"审计日志装饰器记录失败: {str(e)}")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 提取请求对象和数据库会话
            request: Optional[Request] = None
            db: Optional[Session] = None
            user_id: Optional[str] = None
            
            # 从参数中查找Request、Session和user_id
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            for param_name, param_value in bound_args.arguments.items():
                if isinstance(param_value, Request):
                    request = param_value
                elif isinstance(param_value, Session):
                    db = param_value
                elif param_name == "user_id" and isinstance(param_value, str):
                    user_id = param_value
            
            # 执行原函数
            result = func(*args, **kwargs)
            
            # 记录审计日志
            if db is not None:
                try:
                    # 提取资源ID
                    resource_id = None
                    if get_resource_id:
                        try:
                            resource_id_str = get_resource_id(result)
                            if resource_id_str:
                                resource_id = uuid.UUID(resource_id_str)
                        except (ValueError, TypeError, AttributeError):
                            pass
                    
                    # 提取详情
                    details = None
                    if get_details:
                        try:
                            details = get_details(kwargs, result)
                        except Exception:
                            pass
                    
                    # 提取IP地址和用户代理
                    ip_address = None
                    user_agent_str = None
                    if request:
                        ip_address = get_client_ip(request)
                        user_agent_str = get_user_agent(request)
                    
                    # 转换user_id为UUID
                    user_uuid = None
                    if user_id:
                        try:
                            user_uuid = uuid.UUID(user_id)
                        except (ValueError, TypeError):
                            pass
                    
                    # 创建审计日志
                    create_audit_log(
                        db=db,
                        user_id=user_uuid,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        details=details,
                        ip_address=ip_address,
                        user_agent=user_agent_str
                    )
                except Exception as e:
                    # 审计日志记录失败不应该影响主业务流程
                    print(f"审计日志装饰器记录失败: {str(e)}")
            
            return result
        
        # 根据函数类型返回对应的包装器
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_authentication_event(
    db: Session,
    user_id: Optional[uuid.UUID],
    action: str,
    success: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    记录用户认证事件日志
    
    需求：13.1 - 记录所有用户认证事件（成功/失败）
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        action: 操作类型（login, logout, register等）
        success: 是否成功
        ip_address: IP地址
        user_agent: 用户代理字符串
        details: 额外详情
    """
    log_details = {
        "success": success,
        **(details or {})
    }
    
    create_audit_log(
        db=db,
        user_id=user_id,
        action=action,
        resource_type="authentication",
        details=log_details,
        ip_address=ip_address,
        user_agent=user_agent
    )


def log_admin_operation(
    db: Session,
    user_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: Optional[uuid.UUID] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    记录管理操作日志
    
    需求：13.2 - 记录所有管理操作（创建、修改、删除）
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        action: 操作类型（create, update, delete等）
        resource_type: 资源类型（user, role, permission等）
        resource_id: 资源ID
        details: 操作详情
        ip_address: IP地址
        user_agent: 用户代理字符串
    """
    create_audit_log(
        db=db,
        user_id=user_id,
        action=f"{action}_{resource_type}",
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )


def log_permission_change(
    db: Session,
    user_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    记录权限变更日志
    
    需求：13.2 - 记录权限变更
    
    Args:
        db: 数据库会话
        user_id: 操作用户ID
        action: 操作类型（assign_permission, revoke_permission等）
        target_type: 目标类型（role, user, organization等）
        target_id: 目标ID
        details: 变更详情
        ip_address: IP地址
        user_agent: 用户代理字符串
    """
    create_audit_log(
        db=db,
        user_id=user_id,
        action=action,
        resource_type="permission_change",
        resource_id=target_id,
        details={
            "target_type": target_type,
            **(details or {})
        },
        ip_address=ip_address,
        user_agent=user_agent
    )


def log_super_admin_operation(
    db: Session,
    user_id: uuid.UUID,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[uuid.UUID] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> None:
    """
    记录超级管理员操作日志
    
    需求：6.5 - 记录超级管理员的所有操作日志
    
    Args:
        db: 数据库会话
        user_id: 超级管理员用户ID
        action: 操作类型
        resource_type: 资源类型
        resource_id: 资源ID
        details: 操作详情
        ip_address: IP地址
        user_agent: 用户代理字符串
    """
    log_details = {
        "is_super_admin": True,
        **(details or {})
    }
    
    create_audit_log(
        db=db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=log_details,
        ip_address=ip_address,
        user_agent=user_agent
    )
