"""
统一错误处理与 request_id 生成模块

提供:
  1. generate_request_id() - 生成唯一 UUID request_id
  2. create_error_response() - 创建统一格式的错误 JSON 响应
  3. gateway_exception_handler() - FastAPI 异常处理器，捕获 HTTPException 并返回统一格式
  4. RequestIdMiddleware - ASGI 中间件，为每个请求注入 request_id 并通过 X-Request-Id 响应头返回

统一错误响应格式:
  {
      "error_code": "invalid_credentials",
      "message": "凭证无效",
      "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }

错误码定义:
  invalid_credentials  401  app_id 或 app_secret 无效
  app_disabled         403  应用已被禁用
  token_expired        401  access_token 已过期
  invalid_token        401  access_token 格式无效
  login_method_disabled 400 登录方式未启用
  insufficient_scope   403  缺少所需权限范围
  user_not_bound       403  用户不属于该应用
  rate_limit_exceeded  429  请求频率超限
  service_unavailable  503  下游服务不可用
  upstream_error       502  下游非预期错误
  validation_error     422  请求参数验证失败
  internal_error       500  网关内部错误

需求: 9.1, 9.2, 9.3, 9.4
"""
import uuid
from typing import Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


# ---------------------------------------------------------------------------
# HTTP 状态码到默认 error_code 的映射
# ---------------------------------------------------------------------------
STATUS_CODE_ERROR_MAP = {
    400: "login_method_disabled",
    401: "invalid_credentials",
    403: "app_disabled",
    404: "not_found",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_error",
    502: "upstream_error",
    503: "service_unavailable",
}


# ---------------------------------------------------------------------------
# request_id 生成
# ---------------------------------------------------------------------------

def generate_request_id() -> str:
    """
    生成唯一的 request_id（UUID4 格式）。

    Returns:
        UUID 字符串，如 "550e8400-e29b-41d4-a716-446655440000"
    """
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 统一错误响应构建
# ---------------------------------------------------------------------------

def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    request_id: Optional[str] = None,
) -> JSONResponse:
    """
    创建统一格式的错误 JSON 响应。

    响应体仅包含 error_code、message、request_id 三个字段，
    不暴露任何下游微服务的实现细节。

    Args:
        status_code: HTTP 状态码
        error_code: 机器可读的错误码（如 "invalid_credentials"）
        message: 人类可读的错误描述
        request_id: 请求追踪 ID，为 None 时自动生成

    Returns:
        JSONResponse 包含统一错误格式和 X-Request-Id 响应头
    """
    if request_id is None:
        request_id = generate_request_id()

    body = {
        "error_code": error_code,
        "message": message,
        "request_id": request_id,
    }

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers={"X-Request-Id": request_id},
    )


# ---------------------------------------------------------------------------
# 从 HTTPException detail 中提取 error_code
# ---------------------------------------------------------------------------

def _extract_error_code_and_message(
    status_code: int,
    detail,
) -> tuple:
    """
    从 HTTPException 的 detail 中提取 error_code 和 message。

    支持以下 detail 格式:
      - dict: {"error_code": "...", "message": "..."}
      - str: 直接作为 message，error_code 从状态码映射
      - 其他: 转为字符串作为 message

    Args:
        status_code: HTTP 状态码
        detail: HTTPException 的 detail 字段

    Returns:
        (error_code, message) 元组
    """
    default_code = STATUS_CODE_ERROR_MAP.get(status_code, "internal_error")

    if isinstance(detail, dict):
        error_code = detail.get("error_code", default_code)
        message = detail.get("message", str(detail))
        return error_code, message

    if isinstance(detail, str):
        return default_code, detail

    return default_code, str(detail) if detail else "未知错误"


# ---------------------------------------------------------------------------
# FastAPI 异常处理器
# ---------------------------------------------------------------------------

async def gateway_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """
    FastAPI 异常处理器，捕获 HTTPException 并返回统一错误格式。

    从请求 state 中获取 request_id（由 RequestIdMiddleware 注入），
    将 HTTPException 的 detail 转换为统一的 {error_code, message, request_id} 格式。
    隐藏下游微服务的实现细节（5xx 错误不透传原始错误信息）。

    Args:
        request: FastAPI Request 对象
        exc: 捕获的 HTTPException

    Returns:
        统一格式的 JSONResponse
    """
    request_id = getattr(request.state, "request_id", None) or generate_request_id()

    error_code, message = _extract_error_code_and_message(
        exc.status_code, exc.detail
    )

    return create_error_response(
        status_code=exc.status_code,
        error_code=error_code,
        message=message,
        request_id=request_id,
    )


async def gateway_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    FastAPI 请求验证异常处理器。

    将 Pydantic 验证错误转换为统一的 validation_error 格式，
    隐藏内部字段名等实现细节。

    Args:
        request: FastAPI Request 对象
        exc: 捕获的 RequestValidationError

    Returns:
        统一格式的 JSONResponse（422 validation_error）
    """
    request_id = getattr(request.state, "request_id", None) or generate_request_id()

    return create_error_response(
        status_code=422,
        error_code="validation_error",
        message="请求参数验证失败",
        request_id=request_id,
    )


async def gateway_generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    兜底异常处理器，捕获所有未处理的异常。

    将未预期的异常转换为 500 internal_error，
    不暴露任何内部错误堆栈或实现细节。

    Args:
        request: FastAPI Request 对象
        exc: 捕获的异常

    Returns:
        统一格式的 JSONResponse（500 internal_error）
    """
    request_id = getattr(request.state, "request_id", None) or generate_request_id()

    return create_error_response(
        status_code=500,
        error_code="internal_error",
        message="网关内部错误",
        request_id=request_id,
    )


# ---------------------------------------------------------------------------
# Request ID 中间件
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    ASGI 中间件：为每个请求生成唯一 request_id。

    行为:
      - 在请求进入时生成 UUID request_id 并存入 request.state.request_id
      - 在响应返回时将 request_id 写入 X-Request-Id 响应头
      - 所有请求（包括成功和失败）都会携带 X-Request-Id
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = generate_request_id()
        request.state.request_id = request_id

        response = await call_next(request)

        # 注入 X-Request-Id 响应头（如果异常处理器已设置则不覆盖）
        if "X-Request-Id" not in response.headers:
            response.headers["X-Request-Id"] = request_id

        return response
