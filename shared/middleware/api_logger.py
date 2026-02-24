"""
API调用日志中间件

记录所有API请求的详细信息，包括：
- 请求路径
- HTTP方法
- 请求参数
- 响应状态码
- 响应时间
- 用户ID（如果有）
- IP地址

需求：9.8 - API网关应记录所有API调用日志
"""
import time
import json
import uuid
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from sqlalchemy.orm import Session
from datetime import datetime


class APILoggerMiddleware(BaseHTTPMiddleware):
    """
    API调用日志中间件
    
    自动记录所有API请求的详细信息到数据库。
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求并记录日志
        
        Args:
            request: FastAPI请求对象
            call_next: 下一个中间件或路由处理器
            
        Returns:
            响应对象
        """
        # 记录开始时间
        start_time = time.time()
        
        # 提取请求信息
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        
        # 提取用户ID（从JWT token或查询参数）
        user_id = None
        try:
            # 尝试从Authorization头提取
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                # 解析JWT获取用户ID（简化版，实际应该使用jwt库）
                from shared.utils.jwt import decode_token
                payload = decode_token(token)
                if payload:
                    user_id = payload.get("sub")
        except Exception:
            pass
        
        # 如果没有从token获取，尝试从查询参数获取
        if not user_id:
            user_id = query_params.get("user_id")
        
        # 提取IP地址
        ip_address = get_client_ip(request)
        
        # 提取用户代理
        user_agent = request.headers.get("User-Agent")
        
        # 读取请求体（仅用于日志，不影响后续处理）
        request_body = None
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                # 保存原始请求体
                body_bytes = await request.body()
                # 重新设置请求体，以便后续处理可以读取
                async def receive():
                    return {"type": "http.request", "body": body_bytes}
                request._receive = receive
                
                # 尝试解析为JSON
                if body_bytes:
                    try:
                        request_body = json.loads(body_bytes.decode())
                        # 过滤敏感信息
                        request_body = filter_sensitive_data(request_body)
                    except Exception:
                        request_body = {"_raw": body_bytes.decode()[:500]}  # 限制长度
        except Exception as e:
            request_body = {"_error": f"Failed to read body: {str(e)}"}
        
        # 处理请求
        response = await call_next(request)
        
        # 计算响应时间
        response_time = time.time() - start_time
        
        # 记录日志到数据库（异步，不阻塞响应）
        try:
            # 创建日志记录
            log_data = {
                "method": method,
                "path": path,
                "query_params": query_params,
                "request_body": request_body,
                "status_code": response.status_code,
                "response_time": round(response_time * 1000, 2),  # 转换为毫秒
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # 异步记录到数据库
            await log_api_call(log_data)
        except Exception as e:
            # 日志记录失败不应该影响响应
            print(f"API日志记录失败: {str(e)}")
        
        # 添加响应时间头
        response.headers["X-Response-Time"] = f"{response_time * 1000:.2f}ms"
        
        return response


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


def filter_sensitive_data(data: dict) -> dict:
    """
    过滤敏感数据
    
    将密码、token等敏感字段替换为"***"
    
    Args:
        data: 原始数据字典
        
    Returns:
        过滤后的数据字典
    """
    if not isinstance(data, dict):
        return data
    
    sensitive_fields = [
        "password", "old_password", "new_password",
        "token", "access_token", "refresh_token",
        "secret", "api_key", "private_key",
        "credit_card", "ssn"
    ]
    
    filtered_data = {}
    for key, value in data.items():
        if key.lower() in sensitive_fields:
            filtered_data[key] = "***"
        elif isinstance(value, dict):
            filtered_data[key] = filter_sensitive_data(value)
        elif isinstance(value, list):
            filtered_data[key] = [
                filter_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            filtered_data[key] = value
    
    return filtered_data


async def log_api_call(log_data: dict) -> None:
    """
    记录API调用到数据库
    
    Args:
        log_data: 日志数据
    """
    from shared.database import SessionLocal
    from shared.models.system import APILog
    
    db = SessionLocal()
    try:
        # 转换user_id为UUID
        user_id = None
        if log_data.get("user_id"):
            try:
                user_id = uuid.UUID(log_data["user_id"])
            except (ValueError, TypeError):
                pass
        
        # 创建API日志记录
        api_log = APILog(
            user_id=user_id,
            method=log_data["method"],
            path=log_data["path"],
            query_params=log_data.get("query_params"),
            request_body=log_data.get("request_body"),
            status_code=log_data["status_code"],
            response_time=log_data["response_time"],
            ip_address=log_data.get("ip_address"),
            user_agent=log_data.get("user_agent")
        )
        
        db.add(api_log)
        db.commit()
    except Exception as e:
        print(f"保存API日志到数据库失败: {str(e)}")
        db.rollback()
    finally:
        db.close()
