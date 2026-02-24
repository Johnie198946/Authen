"""
验证工具模块
"""
import re
from typing import Optional


def validate_email(email: str) -> bool:
    """
    验证邮箱格式
    
    Args:
        email: 邮箱地址
        
    Returns:
        是否为有效邮箱
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_phone(phone: str) -> bool:
    """
    验证手机号格式（中国）
    
    Args:
        phone: 手机号
        
    Returns:
        是否为有效手机号
    """
    pattern = r'^\+?86?1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def validate_password(password: str) -> tuple[bool, Optional[str]]:
    """
    验证密码强度
    
    密码要求：
    - 长度8-32位
    - 至少包含一个大写字母
    - 至少包含一个小写字母
    - 至少包含一个数字
    
    Args:
        password: 密码
        
    Returns:
        (是否有效, 错误消息)
    """
    if len(password) < 8:
        return False, "密码长度至少8位"
    
    if len(password) > 32:
        return False, "密码长度不能超过32位"
    
    if not re.search(r'[A-Z]', password):
        return False, "密码必须包含至少一个大写字母"
    
    if not re.search(r'[a-z]', password):
        return False, "密码必须包含至少一个小写字母"
    
    if not re.search(r'\d', password):
        return False, "密码必须包含至少一个数字"
    
    return True, None


def validate_username(username: str) -> tuple[bool, Optional[str]]:
    """
    验证用户名格式
    
    用户名要求：
    - 长度3-50位
    - 只能包含字母、数字、下划线
    
    Args:
        username: 用户名
        
    Returns:
        (是否有效, 错误消息)
    """
    if len(username) < 3:
        return False, "用户名长度至少3位"
    
    if len(username) > 50:
        return False, "用户名长度不能超过50位"
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含字母、数字和下划线"
    
    return True, None
