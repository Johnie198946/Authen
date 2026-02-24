"""
安全工具模块

提供SQL注入防护、XSS防护等安全功能
"""
import re
import html
from typing import Any, Dict, List, Optional
import bleach


# ==================== SQL注入防护 ====================

def sanitize_sql_input(value: str) -> str:
    """
    清理SQL输入，防止SQL注入
    
    需求：11.3 - 实现SQL注入防护
    
    注意：这是额外的防护层，主要防护应该使用SQLAlchemy的参数化查询
    
    Args:
        value: 输入值
        
    Returns:
        清理后的值
    """
    if not isinstance(value, str):
        return value
    
    # 移除常见的SQL注入关键字和字符
    dangerous_patterns = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|DECLARE)\b)",
        r"(--|;|\/\*|\*\/|xp_|sp_)",
        r"('(\s)*(OR|AND)(\s)*')",
        r"(=(\s)*(SELECT|INSERT|UPDATE|DELETE))",
    ]
    
    cleaned_value = value
    for pattern in dangerous_patterns:
        cleaned_value = re.sub(pattern, "", cleaned_value, flags=re.IGNORECASE)
    
    return cleaned_value


def validate_sql_safe(value: str) -> tuple[bool, Optional[str]]:
    """
    验证输入是否包含SQL注入风险
    
    需求：11.3 - 实现输入验证和清理
    
    Args:
        value: 输入值
        
    Returns:
        (是否安全, 错误消息)
    """
    if not isinstance(value, str):
        return True, None
    
    # 检测SQL注入特征
    sql_injection_patterns = [
        (r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|DECLARE)\b)", "包含SQL关键字"),
        (r"(--|;|\/\*|\*\/)", "包含SQL注释符号"),
        (r"('(\s)*(OR|AND)(\s)*')", "包含SQL逻辑运算符"),
        (r"(=(\s)*(SELECT|INSERT|UPDATE|DELETE))", "包含SQL子查询"),
        (r"(xp_|sp_)", "包含存储过程调用"),
    ]
    
    for pattern, message in sql_injection_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            return False, f"输入不安全: {message}"
    
    return True, None


def sanitize_order_by(column: str, allowed_columns: List[str]) -> str:
    """
    清理ORDER BY子句，防止SQL注入
    
    需求：11.3 - 防止通过ORDER BY进行SQL注入
    
    Args:
        column: 排序列名
        allowed_columns: 允许的列名列表
        
    Returns:
        清理后的列名
        
    Raises:
        ValueError: 如果列名不在允许列表中
    """
    # 移除空格和特殊字符
    cleaned_column = re.sub(r'[^\w]', '', column)
    
    # 检查是否在允许列表中
    if cleaned_column not in allowed_columns:
        raise ValueError(f"不允许的排序列: {column}")
    
    return cleaned_column


def sanitize_like_pattern(pattern: str) -> str:
    """
    清理LIKE模式，防止SQL注入
    
    需求：11.3 - 防止通过LIKE模式进行SQL注入
    
    Args:
        pattern: LIKE模式
        
    Returns:
        清理后的模式
    """
    # 转义特殊字符
    escaped = pattern.replace('\\', '\\\\')
    escaped = escaped.replace('%', '\\%')
    escaped = escaped.replace('_', '\\_')
    escaped = escaped.replace('[', '\\[')
    escaped = escaped.replace(']', '\\]')
    
    return escaped


# ==================== XSS防护 ====================

def sanitize_html(html_content: str, allowed_tags: Optional[List[str]] = None) -> str:
    """
    清理HTML内容，防止XSS攻击
    
    需求：11.4 - 实现HTML输出转义
    
    Args:
        html_content: HTML内容
        allowed_tags: 允许的HTML标签列表（默认为空，即移除所有标签）
        
    Returns:
        清理后的HTML
    """
    if not html_content:
        return ""
    
    # 默认允许的标签（如果需要保留某些标签）
    if allowed_tags is None:
        allowed_tags = []
    
    # 允许的属性
    allowed_attributes = {
        'a': ['href', 'title'],
        'img': ['src', 'alt'],
    }
    
    # 使用bleach清理HTML
    cleaned = bleach.clean(
        html_content,
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )
    
    return cleaned


def escape_html(text: str) -> str:
    """
    转义HTML特殊字符
    
    需求：11.4 - 实现HTML输出转义
    
    Args:
        text: 文本内容
        
    Returns:
        转义后的文本
    """
    if not text:
        return ""
    
    return html.escape(text)


def sanitize_javascript(js_content: str) -> str:
    """
    清理JavaScript内容，防止XSS攻击
    
    需求：11.4 - 防止JavaScript注入
    
    Args:
        js_content: JavaScript内容
        
    Returns:
        清理后的内容
    """
    if not js_content:
        return ""
    
    # 移除危险的JavaScript模式
    dangerous_patterns = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",  # 事件处理器
        r"eval\s*\(",
        r"setTimeout\s*\(",
        r"setInterval\s*\(",
    ]
    
    cleaned = js_content
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    return cleaned


def validate_url(url: str) -> tuple[bool, Optional[str]]:
    """
    验证URL是否安全
    
    需求：11.4 - 防止恶意URL
    
    Args:
        url: URL地址
        
    Returns:
        (是否安全, 错误消息)
    """
    if not url:
        return True, None
    
    # 检查协议
    allowed_protocols = ['http', 'https']
    protocol_pattern = r'^(\w+):'
    match = re.match(protocol_pattern, url.lower())
    
    if match:
        protocol = match.group(1)
        if protocol not in allowed_protocols:
            return False, f"不允许的协议: {protocol}"
    
    # 检查危险模式
    dangerous_patterns = [
        (r'javascript:', "包含JavaScript协议"),
        (r'data:', "包含Data协议"),
        (r'vbscript:', "包含VBScript协议"),
        (r'file:', "包含File协议"),
    ]
    
    for pattern, message in dangerous_patterns:
        if re.search(pattern, url.lower()):
            return False, f"URL不安全: {message}"
    
    return True, None


def sanitize_json_output(data: Any) -> Any:
    """
    清理JSON输出，防止XSS
    
    需求：11.4 - 防止通过JSON响应进行XSS攻击
    
    Args:
        data: 数据对象
        
    Returns:
        清理后的数据
    """
    if isinstance(data, str):
        return escape_html(data)
    elif isinstance(data, dict):
        return {k: sanitize_json_output(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json_output(item) for item in data]
    else:
        return data


# ==================== 输入验证 ====================

def validate_input_length(value: str, min_length: int = 0, max_length: int = 1000) -> tuple[bool, Optional[str]]:
    """
    验证输入长度
    
    Args:
        value: 输入值
        min_length: 最小长度
        max_length: 最大长度
        
    Returns:
        (是否有效, 错误消息)
    """
    if not isinstance(value, str):
        return False, "输入必须是字符串"
    
    length = len(value)
    
    if length < min_length:
        return False, f"输入长度不能少于{min_length}个字符"
    
    if length > max_length:
        return False, f"输入长度不能超过{max_length}个字符"
    
    return True, None


def validate_alphanumeric(value: str, allow_spaces: bool = False) -> tuple[bool, Optional[str]]:
    """
    验证输入是否只包含字母和数字
    
    Args:
        value: 输入值
        allow_spaces: 是否允许空格
        
    Returns:
        (是否有效, 错误消息)
    """
    if not isinstance(value, str):
        return False, "输入必须是字符串"
    
    if allow_spaces:
        pattern = r'^[a-zA-Z0-9\s]+$'
    else:
        pattern = r'^[a-zA-Z0-9]+$'
    
    if not re.match(pattern, value):
        return False, "输入只能包含字母和数字" + ("及空格" if allow_spaces else "")
    
    return True, None


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，防止路径遍历攻击
    
    Args:
        filename: 文件名
        
    Returns:
        清理后的文件名
    """
    if not filename:
        return ""
    
    # 移除路径分隔符
    cleaned = filename.replace('/', '').replace('\\', '')
    
    # 移除特殊字符
    cleaned = re.sub(r'[^\w\s.-]', '', cleaned)
    
    # 移除开头的点（隐藏文件）
    cleaned = cleaned.lstrip('.')
    
    return cleaned


# ==================== Content Security Policy ====================

def get_csp_header() -> Dict[str, str]:
    """
    获取Content Security Policy头
    
    需求：11.4 - 实现Content-Security-Policy头
    
    Returns:
        CSP头字典
    """
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # 生产环境应移除unsafe-*
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
    
    return {
        "Content-Security-Policy": "; ".join(csp_directives)
    }


def get_security_headers() -> Dict[str, str]:
    """
    获取所有安全相关的HTTP头
    
    需求：11.4 - 实现安全HTTP头
    
    Returns:
        安全头字典
    """
    headers = {
        # XSS保护
        "X-XSS-Protection": "1; mode=block",
        
        # 防止MIME类型嗅探
        "X-Content-Type-Options": "nosniff",
        
        # 防止点击劫持
        "X-Frame-Options": "DENY",
        
        # 强制HTTPS
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        
        # 引用策略
        "Referrer-Policy": "strict-origin-when-cross-origin",
        
        # 权限策略
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }
    
    # 添加CSP头
    headers.update(get_csp_header())
    
    return headers
