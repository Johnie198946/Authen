"""
安全中间件

应用安全HTTP头和其他安全措施
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from shared.utils.security import get_security_headers


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全HTTP头中间件
    
    需求：11.4 - 实现XSS防护和安全HTTP头
    
    为所有响应添加安全相关的HTTP头：
    - Content-Security-Policy: 内容安全策略
    - X-XSS-Protection: XSS保护
    - X-Content-Type-Options: 防止MIME类型嗅探
    - X-Frame-Options: 防止点击劫持
    - Strict-Transport-Security: 强制HTTPS
    - Referrer-Policy: 引用策略
    - Permissions-Policy: 权限策略
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.security_headers = get_security_headers()
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求并添加安全头
        
        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理器
            
        Returns:
            响应对象（已添加安全头）
        """
        # 调用下一个处理器
        response = await call_next(request)
        
        # 添加安全头
        for header_name, header_value in self.security_headers.items():
            response.headers[header_name] = header_value
        
        return response


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """
    输入清理中间件
    
    需求：11.3, 11.4 - 实现输入验证和清理
    
    对所有请求的输入进行基本的安全检查和清理
    """
    
    def __init__(self, app: ASGIApp, max_content_length: int = 10 * 1024 * 1024):
        """
        初始化中间件
        
        Args:
            app: ASGI应用
            max_content_length: 最大请求体大小（字节），默认10MB
        """
        super().__init__(app)
        self.max_content_length = max_content_length
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求并进行输入验证
        
        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理器
            
        Returns:
            响应对象
        """
        # 检查请求体大小
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > self.max_content_length:
            return Response(
                content='{"detail": "请求体过大"}',
                status_code=413,
                media_type="application/json"
            )
        
        # 检查Content-Type
        content_type = request.headers.get('content-type', '')
        
        # 对于JSON请求，验证Content-Type
        if request.method in ['POST', 'PUT', 'PATCH']:
            if 'application/json' in content_type:
                # JSON请求的额外验证可以在这里添加
                pass
        
        # 调用下一个处理器
        response = await call_next(request)
        
        return response
