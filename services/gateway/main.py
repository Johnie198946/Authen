"""
统一 API 网关主服务

FastAPI 应用（端口 8008），作为三方系统对接平台的唯一入口。
网关本身不实现业务逻辑，通过内部 HTTP 调用路由到下游微服务。

中间件:
  - RequestIdMiddleware: 为每个请求生成唯一 request_id
  - 限流头注入 & 审计日志: 通过 AuditLogMiddleware 实现

端点:
  - /health: 健康检查（网关自身 + 下游微服务）
  - /api/v1/gateway/info: 网关版本与配置信息

需求: 8.1, 8.3, 8.4
"""
import sys
import os
import logging
import time

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

import httpx

from jose import ExpiredSignatureError, JWTError, jwt as jose_jwt

from shared.config import settings
from shared.database import SessionLocal
from shared.models.application import Application, AppUser
from shared.utils.health_check import check_overall_health
from shared.utils.jwt import create_access_token, create_refresh_token, decode_token
from services.gateway.cache import get_app_methods, get_app_oauth_config
from services.gateway.dependencies import get_app_credential_from_request, get_app_from_cache_or_db
from services.gateway.error_handler import (
    RequestIdMiddleware,
    create_error_response,
    gateway_exception_handler,
    gateway_validation_exception_handler,
    gateway_generic_exception_handler,
)
from services.gateway.rate_limiter import check_rate_limit
from services.gateway.router import ServiceRouter, get_service_router
from services.gateway.scope_checker import check_scope

logger = logging.getLogger("gateway")

# ---------------------------------------------------------------------------
# 网关版本与配置常量
# ---------------------------------------------------------------------------
GATEWAY_VERSION = "1.0.0"
SUPPORTED_API_VERSIONS = ["v1"]
AVAILABLE_LOGIN_METHODS = ["email", "phone", "wechat", "alipay", "google", "apple"]


# 下游微服务配置（用于健康检查）
DOWNSTREAM_SERVICES = {
    "auth": {"name": "Auth Service", "url": "http://localhost:8001", "health_path": "/health"},
    "sso": {"name": "SSO Service", "url": "http://localhost:8002", "health_path": "/health"},
    "user": {"name": "User Service", "url": "http://localhost:8003", "health_path": "/health"},
    "permission": {"name": "Permission Service", "url": "http://localhost:8004", "health_path": "/health"},
}


# ---------------------------------------------------------------------------
# 审计日志中间件
# ---------------------------------------------------------------------------

class AuditLogMiddleware(BaseHTTPMiddleware):
    """
    审计日志中间件：记录所有 API 请求的审计信息。

    记录内容: app_id、请求路径、HTTP 方法、响应状态码、响应时间。
    使用 shared/utils/audit_log 模块写入数据库。

    需求: 6.5
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start_time = time.time()
        response = await call_next(request)
        response_time_ms = round((time.time() - start_time) * 1000, 2)

        # 异步记录审计日志（不阻塞响应）
        try:
            app_id = request.headers.get("X-App-Id", "anonymous")
            request_id = getattr(request.state, "request_id", None)

            logger.info(
                "gateway_audit | request_id=%s app_id=%s method=%s path=%s status=%d time=%.2fms",
                request_id,
                app_id,
                request.method,
                request.url.path,
                response.status_code,
                response_time_ms,
            )

            # 写入数据库审计日志（仅对 API 路径）
            if request.url.path.startswith("/api/"):
                _record_audit_log(
                    app_id=app_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    response_time_ms=response_time_ms,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("User-Agent"),
                )
        except Exception as e:
            # 审计日志失败不影响主流程
            logger.warning("审计日志记录失败: %s", str(e))

        return response


def _record_audit_log(
    app_id: str,
    method: str,
    path: str,
    status_code: int,
    response_time_ms: float,
    ip_address: str = None,
    user_agent: str = None,
) -> None:
    """将审计日志写入数据库（同步，在后台执行）"""
    try:
        from shared.database import SessionLocal
        from shared.utils.audit_log import create_audit_log

        db = SessionLocal()
        try:
            create_audit_log(
                db=db,
                user_id=None,
                action="gateway_api_request",
                resource_type="gateway",
                details={
                    "app_id": app_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "response_time_ms": response_time_ms,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning("审计日志数据库写入失败: %s", str(e))


# ---------------------------------------------------------------------------
# FastAPI 应用创建
# ---------------------------------------------------------------------------

app = FastAPI(
    title="统一 API 网关",
    description="统一身份认证和权限管理平台 - API 网关服务",
    version=GATEWAY_VERSION,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册中间件（执行顺序：后注册的先执行）
# 1. 审计日志中间件（最外层，记录完整请求生命周期）
app.add_middleware(AuditLogMiddleware)
# 2. RequestId 中间件（为每个请求生成唯一 ID）
app.add_middleware(RequestIdMiddleware)

# 注册异常处理器
app.add_exception_handler(StarletteHTTPException, gateway_exception_handler)
app.add_exception_handler(RequestValidationError, gateway_validation_exception_handler)
app.add_exception_handler(Exception, gateway_generic_exception_handler)


# ---------------------------------------------------------------------------
# 启动事件：验证下游微服务连接
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_verify_downstream():
    """
    启动时验证与所有下游微服务的连接。

    连接失败时记录错误日志但允许服务启动（降级模式）。

    需求: 8.3
    """
    logger.info("Gateway 启动中，验证下游微服务连接...")

    for service_key, service_info in DOWNSTREAM_SERVICES.items():
        url = f"{service_info['url']}{service_info['health_path']}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code < 400:
                    logger.info("✓ %s (%s) 连接正常", service_info["name"], service_info["url"])
                else:
                    logger.warning(
                        "⚠ %s (%s) 返回状态码 %d（降级模式）",
                        service_info["name"],
                        service_info["url"],
                        resp.status_code,
                    )
        except Exception as e:
            logger.error(
                "✗ %s (%s) 连接失败: %s（降级模式）",
                service_info["name"],
                service_info["url"],
                str(e),
            )

    logger.info("Gateway 启动完成（端口 8008）")


# ---------------------------------------------------------------------------
# /health 端点
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """
    健康检查端点。

    返回网关自身及所有下游微服务的健康状态。
    复用 shared/utils/health_check 检查本地组件（数据库、Redis、RabbitMQ），
    并通过 HTTP 检查下游微服务的可用性。

    需求: 8.1
    """
    # 1. 检查本地组件（数据库、Redis、RabbitMQ）
    local_health = check_overall_health()

    # 2. 检查下游微服务
    downstream_status = {}
    for service_key, service_info in DOWNSTREAM_SERVICES.items():
        url = f"{service_info['url']}{service_info['health_path']}"
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                response_time = round((time.time() - start_time) * 1000, 2)
                if resp.status_code < 400:
                    downstream_status[service_key] = {
                        "status": "healthy",
                        "message": f"{service_info['name']} 运行正常",
                        "response_time": response_time,
                    }
                else:
                    downstream_status[service_key] = {
                        "status": "unhealthy",
                        "message": f"{service_info['name']} 返回状态码 {resp.status_code}",
                        "response_time": response_time,
                    }
        except Exception as e:
            response_time = round((time.time() - start_time) * 1000, 2)
            downstream_status[service_key] = {
                "status": "unhealthy",
                "message": f"{service_info['name']} 不可用: {str(e)}",
                "response_time": response_time,
            }

    # 3. 计算整体状态
    all_components = {**local_health.get("components", {}), **downstream_status}
    healthy_count = sum(1 for c in all_components.values() if c.get("status") == "healthy")
    total_count = len(all_components)

    if healthy_count == total_count:
        overall_status = "healthy"
        overall_message = "所有组件运行正常"
    elif healthy_count > 0:
        overall_status = "degraded"
        overall_message = f"{healthy_count}/{total_count} 组件运行正常"
    else:
        overall_status = "unhealthy"
        overall_message = "所有组件都不可用"

    status_code = 200 if overall_status in ("healthy", "degraded") else 503

    from datetime import datetime

    result = {
        "status": overall_status,
        "message": overall_message,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            **local_health.get("components", {}),
            **{f"downstream_{k}": v for k, v in downstream_status.items()},
        },
    }

    return JSONResponse(status_code=status_code, content=result)


# ---------------------------------------------------------------------------
# /api/v1/gateway/info 端点
# ---------------------------------------------------------------------------

@app.get("/api/v1/gateway/info")
async def gateway_info():
    """
    网关信息端点。

    返回网关版本、支持的 API 版本列表和可用的登录方式类型列表。

    需求: 8.4
    """
    return {
        "version": GATEWAY_VERSION,
        "supported_api_versions": SUPPORTED_API_VERSIONS,
        "available_login_methods": AVAILABLE_LOGIN_METHODS,
    }


# ---------------------------------------------------------------------------
# 认证类 API 端点辅助函数
# ---------------------------------------------------------------------------

def _get_db():
    """创建数据库会话"""
    return SessionLocal()


async def _run_auth_pipeline(
    request: Request,
    login_method: str,
    scope_endpoint: str,
) -> dict:
    """
    执行认证端点的通用前置流水线：
    凭证验证 → 登录方式检查 → Scope 检查 → 限流

    Args:
        request: FastAPI Request 对象
        login_method: 需要检查的登录方式（email/phone/wechat 等）
        scope_endpoint: Scope 检查用的端点路径（去掉 /api/v1/gateway/ 前缀）

    Returns:
        应用配置字典

    Raises:
        HTTPException: 各阶段验证失败时抛出
    """
    # 1. 凭证验证
    app_data = await get_app_credential_from_request(request)
    app_id = app_data["app_id"]

    # 2. 登录方式检查
    if login_method:
        enabled_methods = await get_app_methods(app_id)
        if login_method not in enabled_methods:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "login_method_disabled",
                    "message": f"登录方式 {login_method} 未启用",
                    "enabled_methods": sorted(enabled_methods),
                },
            )

    # 3. Scope 检查
    await check_scope(app_id, scope_endpoint)

    # 4. 限流
    rate_limit_val = app_data.get("rate_limit", 60)
    rl_result = await check_rate_limit(app_id, rate_limit_val)
    # 将限流结果存入 request state，供响应时注入 headers
    request.state.rate_limit_result = rl_result
    if not rl_result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "rate_limit_exceeded",
                "message": "请求频率超过限制",
                "retry_after": rl_result.retry_after,
            },
        )

    return app_data


def _inject_rate_limit_headers(response: JSONResponse, request: Request) -> JSONResponse:
    """将限流头注入到响应中"""
    rl_result = getattr(request.state, "rate_limit_result", None)
    if rl_result:
        for key, value in rl_result.headers.items():
            response.headers[key] = value
    return response


def _inject_app_id_into_tokens(body: dict, app_id: str) -> dict:
    """
    在登录/OAuth/刷新响应中，重新签发包含 app_id 的 Token。

    解码原始 Token payload，注入 app_id 字段后重新签发。
    """
    if "access_token" in body:
        payload = decode_token(body["access_token"])
        if payload:
            # 移除 JWT 标准字段，保留业务字段
            new_payload = {k: v for k, v in payload.items() if k not in ("exp", "iat", "iss")}
            new_payload["app_id"] = app_id
            body["access_token"] = create_access_token(new_payload)

    if "refresh_token" in body:
        payload = decode_token(body["refresh_token"])
        if payload:
            new_payload = {k: v for k, v in payload.items() if k not in ("exp", "iat", "iss")}
            new_payload["app_id"] = app_id
            body["refresh_token"] = create_refresh_token(new_payload)

    return body


def _create_app_user_binding(app_data: dict, user_id: str) -> None:
    """
    注册成功后创建 AppUser 绑定记录。

    如果绑定已存在则忽略（幂等操作）。
    """
    db = _get_db()
    try:
        from sqlalchemy import and_

        app = db.query(Application).filter(Application.app_id == app_data["app_id"]).first()
        if not app:
            return

        import uuid as uuid_mod
        try:
            user_uuid = uuid_mod.UUID(user_id)
        except (ValueError, AttributeError):
            return

        existing = (
            db.query(AppUser)
            .filter(
                and_(
                    AppUser.application_id == app.id,
                    AppUser.user_id == user_uuid,
                )
            )
            .first()
        )
        if not existing:
            app_user = AppUser(
                application_id=app.id,
                user_id=user_uuid,
            )
            db.add(app_user)
            db.commit()
    except Exception as e:
        logger.warning("创建 AppUser 绑定失败: %s", str(e))
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/auth/register/email
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/auth/register/email")
async def gateway_register_email(request: Request):
    """
    邮箱注册端点。

    流水线: 凭证验证 → email 登录方式检查 → auth:register Scope 检查 → 限流 → 路由到 Auth Service → 创建 AppUser 绑定

    需求: 3.1, 3.7, 3.8, 4.6
    """
    app_data = await _run_auth_pipeline(request, "email", "auth/register/email")
    request_id = getattr(request.state, "request_id", None)

    # 读取请求体
    body = await request.json()

    # 路由到 Auth Service
    router = get_service_router()
    result = await router.forward("auth", "POST", "/api/v1/auth/register/email", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    # 注册成功 → 创建 AppUser 绑定
    if status_code < 400 and resp_body.get("user_id"):
        _create_app_user_binding(app_data, resp_body["user_id"])

    # 注入 request_id 到成功响应
    if status_code < 400 and request_id:
        resp_body["request_id"] = request_id

    # 错误响应使用统一格式
    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "注册失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/auth/register/phone
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/auth/register/phone")
async def gateway_register_phone(request: Request):
    """
    手机注册端点。

    流水线: 凭证验证 → phone 登录方式检查 → auth:register Scope 检查 → 限流 → 路由到 Auth Service → 创建 AppUser 绑定

    需求: 3.2, 3.7, 3.8, 4.6
    """
    app_data = await _run_auth_pipeline(request, "phone", "auth/register/phone")
    request_id = getattr(request.state, "request_id", None)

    body = await request.json()

    router = get_service_router()
    result = await router.forward("auth", "POST", "/api/v1/auth/register/phone", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    # 注册成功 → 创建 AppUser 绑定
    if status_code < 400 and resp_body.get("user_id"):
        _create_app_user_binding(app_data, resp_body["user_id"])

    if status_code < 400 and request_id:
        resp_body["request_id"] = request_id

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "注册失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/auth/login
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/auth/login")
async def gateway_login(request: Request):
    """
    登录端点。

    流水线: 凭证验证 → Scope 检查 → 限流 → 路由到 Auth Service → Token 注入 app_id

    登录不检查具体的 login_method（identifier 可以是邮箱或手机号，由 Auth Service 判断）。

    需求: 3.3, 4.6
    """
    app_data = await _run_auth_pipeline(request, "", "auth/login")
    request_id = getattr(request.state, "request_id", None)

    body = await request.json()

    router = get_service_router()
    result = await router.forward("auth", "POST", "/api/v1/auth/login", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    # 登录成功 → 注入 app_id 到 Token
    if status_code < 400:
        resp_body = _inject_app_id_into_tokens(resp_body, app_data["app_id"])
        if request_id:
            resp_body["request_id"] = request_id

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "登录失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/auth/oauth/{provider}
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/auth/oauth/{provider}")
async def gateway_oauth(provider: str, request: Request):
    """
    OAuth 登录端点。

    使用应用级 OAuth 配置（而非全局配置）调用 Auth Service。

    流水线: 凭证验证 → provider 登录方式检查 → auth:login Scope 检查 → 限流 → 获取应用级 OAuth 配置 → 路由到 Auth Service → Token 注入 app_id

    需求: 3.4, 3.7, 4.6
    """
    app_data = await _run_auth_pipeline(request, provider, f"auth/oauth/{provider}")
    request_id = getattr(request.state, "request_id", None)
    app_id = app_data["app_id"]

    body = await request.json()

    # 获取应用级 OAuth 配置
    oauth_config = await get_app_oauth_config(app_id, provider)
    if oauth_config:
        # 将应用级 OAuth 配置注入请求体，覆盖全局配置
        body["client_id"] = oauth_config.get("client_id")
        body["client_secret"] = oauth_config.get("client_secret")

    router = get_service_router()
    result = await router.forward("auth", "POST", f"/api/v1/auth/oauth/{provider}", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    # OAuth 成功 → 注入 app_id 到 Token
    if status_code < 400:
        resp_body = _inject_app_id_into_tokens(resp_body, app_id)
        # 如果是新用户，创建 AppUser 绑定
        if resp_body.get("is_new_user") and resp_body.get("user", {}).get("id"):
            _create_app_user_binding(app_data, resp_body["user"]["id"])
        if request_id:
            resp_body["request_id"] = request_id

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "OAuth 认证失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/auth/refresh
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/auth/refresh")
async def gateway_refresh(request: Request):
    """
    Token 刷新端点。

    流水线: 凭证验证 → auth:login Scope 检查 → 限流 → 路由到 Auth Service → Token 注入 app_id

    需求: 3.5, 4.6
    """
    app_data = await _run_auth_pipeline(request, "", "auth/refresh")
    request_id = getattr(request.state, "request_id", None)

    body = await request.json()

    router = get_service_router()
    result = await router.forward("auth", "POST", "/api/v1/auth/refresh", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    # 刷新成功 → 注入 app_id 到新 Token
    if status_code < 400:
        resp_body = _inject_app_id_into_tokens(resp_body, app_data["app_id"])
        if request_id:
            resp_body["request_id"] = request_id

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "Token 刷新失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# Bearer Token 鉴权辅助函数
# ---------------------------------------------------------------------------

def _extract_bearer_token(request: Request) -> str:
    """
    从 Authorization 请求头中提取 Bearer Token。

    Args:
        request: FastAPI Request 对象

    Returns:
        Token 字符串

    Raises:
        HTTPException: 401 缺少或格式错误的 Authorization 头
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error_code": "invalid_token", "message": "缺少或格式错误的 Authorization 头"},
        )
    return auth_header[7:]


def _decode_bearer_token(token: str) -> dict:
    """
    解码 Bearer Token，区分过期和无效两种错误。

    使用 jose 库直接解码以区分 ExpiredSignatureError 和其他 JWTError。

    Args:
        token: JWT Token 字符串

    Returns:
        Token payload 字典

    Raises:
        HTTPException: 401 token_expired 或 invalid_token
    """
    try:
        payload = jose_jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "token_expired", "message": "Token 已过期"},
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "invalid_token", "message": "Token 无效"},
        )


def _validate_app_id_in_token(payload: dict) -> str:
    """
    验证 Token payload 中包含 app_id 字段。

    Args:
        payload: Token payload 字典

    Returns:
        app_id 字符串

    Raises:
        HTTPException: 401 invalid_token（Token 中缺少 app_id）
    """
    app_id = payload.get("app_id")
    if not app_id:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "invalid_token", "message": "Token 中缺少 app_id"},
        )
    return app_id


def _check_app_user_binding(app_id: str, user_id: str) -> None:
    """
    检查用户是否绑定到指定应用。

    Args:
        app_id: 应用的 app_id
        user_id: 用户 ID

    Raises:
        HTTPException: 403 user_not_bound（用户不属于该应用）
    """
    db = _get_db()
    try:
        from sqlalchemy import and_
        import uuid as uuid_mod

        app = db.query(Application).filter(Application.app_id == app_id).first()
        if not app:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "user_not_bound", "message": "用户不属于该应用"},
            )

        try:
            user_uuid = uuid_mod.UUID(user_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "user_not_bound", "message": "用户不属于该应用"},
            )

        existing = (
            db.query(AppUser)
            .filter(
                and_(
                    AppUser.application_id == app.id,
                    AppUser.user_id == user_uuid,
                )
            )
            .first()
        )
        if not existing:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "user_not_bound", "message": "用户不属于该应用"},
            )
    finally:
        db.close()


async def _run_bearer_pipeline(
    request: Request,
    scope_endpoint: str,
    target_user_id: str = None,
) -> dict:
    """
    执行 Bearer Token 端点的通用前置流水线：
    Token 提取 → Token 解码 → app_id 验证 → 应用状态检查 → AppUser 绑定检查 → Scope 检查 → 限流

    Args:
        request: FastAPI Request 对象
        scope_endpoint: Scope 检查用的端点路径
        target_user_id: 目标用户 ID（用于 AppUser 绑定检查，None 时使用 Token 中的 sub）

    Returns:
        包含 app_id, user_id, payload 的字典

    Raises:
        HTTPException: 各阶段验证失败时抛出
    """
    # 1. 提取 Bearer Token
    token = _extract_bearer_token(request)

    # 2. 解码 Token（区分过期和无效）
    payload = _decode_bearer_token(token)

    # 3. 验证 app_id
    app_id = _validate_app_id_in_token(payload)

    # 4. 检查应用状态
    app_data = await get_app_from_cache_or_db(app_id)
    if not app_data:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "invalid_token", "message": "Token 中的应用不存在"},
        )
    if app_data.get("status") != "active":
        raise HTTPException(
            status_code=403,
            detail={"error_code": "app_disabled", "message": "应用已被禁用"},
        )

    # 5. 检查 AppUser 绑定
    user_id = target_user_id or payload.get("sub")
    if user_id:
        _check_app_user_binding(app_id, user_id)

    # 6. Scope 检查
    await check_scope(app_id, scope_endpoint)

    # 7. 限流
    rate_limit_val = app_data.get("rate_limit", 60)
    rl_result = await check_rate_limit(app_id, rate_limit_val)
    request.state.rate_limit_result = rl_result
    if not rl_result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error_code": "rate_limit_exceeded",
                "message": "请求频率超过限制",
                "retry_after": rl_result.retry_after,
            },
        )

    return {
        "app_id": app_id,
        "user_id": user_id,
        "payload": payload,
        "app_data": app_data,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/gateway/users/{user_id}
# ---------------------------------------------------------------------------

@app.get("/api/v1/gateway/users/{user_id}")
async def gateway_get_user(user_id: str, request: Request):
    """
    查询用户信息端点。

    流水线: Bearer Token 鉴权 → user:read Scope 检查 → 限流 → 路由到 User Service

    需求: 7.1, 7.5
    """
    bearer_data = await _run_bearer_pipeline(request, f"users/{user_id}", target_user_id=user_id)
    request_id = getattr(request.state, "request_id", None)

    router = get_service_router()
    result = await router.forward("user", "GET", f"/api/v1/users/{user_id}")

    status_code = result["status_code"]
    resp_body = result["body"]

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "用户查询失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    if request_id:
        resp_body["request_id"] = request_id

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# GET /api/v1/gateway/users/{user_id}/roles
# ---------------------------------------------------------------------------

@app.get("/api/v1/gateway/users/{user_id}/roles")
async def gateway_get_user_roles(user_id: str, request: Request):
    """
    查询用户角色端点。

    流水线: Bearer Token 鉴权 → role:read Scope 检查 → 限流 → 路由到 Permission Service

    需求: 7.2, 7.5
    """
    bearer_data = await _run_bearer_pipeline(request, f"users/{user_id}/roles", target_user_id=user_id)
    request_id = getattr(request.state, "request_id", None)

    router = get_service_router()
    result = await router.forward("permission", "GET", f"/api/v1/permissions/users/{user_id}/roles")

    status_code = result["status_code"]
    resp_body = result["body"]

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "角色查询失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    if request_id:
        resp_body["request_id"] = request_id

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/users/{user_id}/permissions/check
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/users/{user_id}/permissions/check")
async def gateway_check_user_permission(user_id: str, request: Request):
    """
    检查用户权限端点。

    流水线: Bearer Token 鉴权 → role:read Scope 检查 → 限流 → 路由到 Permission Service

    需求: 7.3, 7.5
    """
    bearer_data = await _run_bearer_pipeline(request, f"users/{user_id}/permissions/check", target_user_id=user_id)
    request_id = getattr(request.state, "request_id", None)

    body = await request.json()

    router = get_service_router()
    result = await router.forward("permission", "POST", f"/api/v1/permissions/users/{user_id}/check", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "权限检查失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    if request_id:
        resp_body["request_id"] = request_id

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# POST /api/v1/gateway/auth/change-password
# ---------------------------------------------------------------------------

@app.post("/api/v1/gateway/auth/change-password")
async def gateway_change_password(request: Request):
    """
    修改密码端点。

    流水线: Bearer Token 鉴权 → user:write Scope 检查 → 限流 → 路由到 Auth Service

    需求: 7.4, 7.5
    """
    bearer_data = await _run_bearer_pipeline(request, "auth/change-password")
    request_id = getattr(request.state, "request_id", None)

    body = await request.json()

    router = get_service_router()
    result = await router.forward("auth", "POST", "/api/v1/auth/change-password", json=body)

    status_code = result["status_code"]
    resp_body = result["body"]

    if status_code >= 400:
        error_code = resp_body.get("error_code", "upstream_error")
        message = resp_body.get("message", "密码修改失败")
        response = create_error_response(status_code, error_code, message, request_id)
        return _inject_rate_limit_headers(response, request)

    if request_id:
        resp_body["request_id"] = request_id

    response = JSONResponse(status_code=status_code, content=resp_body)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return _inject_rate_limit_headers(response, request)


# ---------------------------------------------------------------------------
# 根路径
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """根路径"""
    return {"service": "统一 API 网关", "status": "running"}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8008)
