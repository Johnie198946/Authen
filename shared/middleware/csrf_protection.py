"""
CSRF保护中间件

自动验证所有状态改变请求（POST、PUT、DELETE、PATCH）的CSRF Token。

需求：11.2 - 实现CSRF保护机制
"""
from typing import Callable, List, Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from shared.utils.csrf import (
    get_csrf_token_from_request,
    validate_and_consume_csrf_token,
    verify_csrf_token
)


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF保护中间件
    
    自动验证所有状态改变请求的CSRF Token。
    """
    
    # 需要CSRF保护的HTTP方法
    PROTECTED_METHODS = ["POST", "PUT", "DELETE", "PATCH"]
    
    # 默认豁免路径（不需要CSRF保护）
    DEFAULT_EXEMPT_PATHS = [
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",  # 登录接口豁免
        "/api/v1/auth/register/email",  # 注册接口豁免
        "/api/v1/auth/register/phone",  # 注册接口豁免
        "/api/v1/auth/oauth/",  # OAuth接口豁免
    ]
    
    def __init__(
        self,
        app: ASGIApp,
        exempt_paths: Optional[List[str]] = None,
        require_token_consumption: bool = False
    ):
        """
        初始化CSRF保护中间件
        
        Args:
            app: ASGI应用
            exempt_paths: 额外的豁免路径列表
            require_token_consumption: 是否要求Token一次性使用（从Redis消费）
        """
        super().__init__(app)
        
        # 合并豁免路径
        self.exempt_paths = self.DEFAULT_EXEMPT_PATHS.copy()
        if exempt_paths:
            self.exempt_paths.extend(exempt_paths)
        
        self.require_token_consumption = require_token_consumption
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求并验证CSRF Token
        
        Args:
            request: FastAPI请求对象
            call_next: 下一个中间件或路由处理器
            
        Returns:
            响应对象
        """
        # 检查是否需要CSRF保护
        if not self._requires_csrf_protection(request):
            return await call_next(request)
        
        # 提取CSRF Token
        csrf_token = get_csrf_token_from_request(request)
        
        if not csrf_token:
            # 尝试从请求体获取（POST表单）
            csrf_token = await self._get_token_from_body(request)
        
        if not csrf_token:
            # 返回403响应而不是抛出异常
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing"}
            )
        
        # 提取用户ID和会话ID（如果有）
        user_id = self._get_user_id_from_request(request)
        session_id = self._get_session_id_from_request(request)
        
        # 验证CSRF Token
        try:
            if self.require_token_consumption:
                # 验证并消费Token（一次性使用）
                is_valid = validate_and_consume_csrf_token(
                    csrf_token,
                    user_id=user_id,
                    session_id=session_id
                )
            else:
                # 只验证Token格式
                is_valid = verify_csrf_token(csrf_token, session_id)
        except Exception as e:
            # 捕获所有其他验证过程中的异常，返回403
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid CSRF token"}
            )
        
        if not is_valid:
            # 返回403响应而不是抛出异常
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid CSRF token"}
            )
        
        # Token验证通过，继续处理请求
        return await call_next(request)
    
    def _requires_csrf_protection(self, request: Request) -> bool:
        """
        检查请求是否需要CSRF保护
        
        Args:
            request: FastAPI请求对象
            
        Returns:
            是否需要CSRF保护
        """
        # 检查HTTP方法
        if request.method not in self.PROTECTED_METHODS:
            return False
        
        # 检查路径是否在豁免列表中
        path = request.url.path
        
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return False
        
        return True
    
    async def _get_token_from_body(self, request: Request) -> Optional[str]:
        """
        从请求体获取CSRF Token
        
        Args:
            request: FastAPI请求对象
            
        Returns:
            CSRF Token或None
        """
        try:
            # 检查Content-Type
            content_type = request.headers.get("Content-Type", "")
            
            # 检查Content-Length，如果为0或不存在，直接返回None
            content_length = request.headers.get("Content-Length", "0")
            if content_length == "0":
                return None
            
            if "application/json" in content_type:
                # JSON请求体
                body = await request.body()
                if not body:
                    return None
                    
                import json
                data = json.loads(body.decode())
                
                # 重新设置请求体，以便后续处理可以读取
                async def receive():
                    return {"type": "http.request", "body": body}
                request._receive = receive
                
                return data.get("csrf_token")
            
            elif "application/x-www-form-urlencoded" in content_type:
                # 表单请求体
                form = await request.form()
                return form.get("csrf_token")
        
        except Exception:
            pass
        
        return None
    
    def _get_user_id_from_request(self, request: Request) -> Optional[str]:
        """
        从请求中提取用户ID
        
        Args:
            request: FastAPI请求对象
            
        Returns:
            用户ID或None
        """
        try:
            # 从Authorization头提取
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                
                from shared.utils.jwt import decode_token
                payload = decode_token(token)
                if payload:
                    return payload.get("sub")
        except Exception:
            pass
        
        return None
    
    def _get_session_id_from_request(self, request: Request) -> Optional[str]:
        """
        从请求中提取会话ID
        
        Args:
            request: FastAPI请求对象
            
        Returns:
            会话ID或None
        """
        # 从Cookie获取会话ID
        return request.cookies.get("session_id")
