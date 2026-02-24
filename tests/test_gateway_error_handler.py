"""
统一错误处理与 request_id 生成模块的单元测试

测试覆盖:
  - generate_request_id: UUID 格式、唯一性
  - create_error_response: 统一格式、响应头
  - gateway_exception_handler: HTTPException 转换
  - gateway_validation_exception_handler: 验证错误转换
  - gateway_generic_exception_handler: 兜底异常处理
  - RequestIdMiddleware: request_id 注入与响应头
  - _extract_error_code_and_message: detail 格式解析

需求: 9.1, 9.2, 9.3, 9.4
"""
import json
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.gateway.error_handler import (
    RequestIdMiddleware,
    create_error_response,
    gateway_exception_handler,
    gateway_generic_exception_handler,
    gateway_validation_exception_handler,
    generate_request_id,
    _extract_error_code_and_message,
)


# ---------------------------------------------------------------------------
# generate_request_id 测试
# ---------------------------------------------------------------------------

class TestGenerateRequestId:
    """测试 request_id 生成"""

    def test_returns_valid_uuid(self):
        """生成的 request_id 应为合法 UUID 格式"""
        rid = generate_request_id()
        parsed = uuid.UUID(rid)
        assert str(parsed) == rid

    def test_returns_uuid4(self):
        """生成的 UUID 应为版本 4"""
        rid = generate_request_id()
        parsed = uuid.UUID(rid)
        assert parsed.version == 4

    def test_unique_ids(self):
        """多次调用应生成不同的 request_id"""
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# create_error_response 测试
# ---------------------------------------------------------------------------

class TestCreateErrorResponse:
    """测试统一错误响应构建"""

    def test_response_body_format(self):
        """响应体应仅包含 error_code、message、request_id 三个字段"""
        resp = create_error_response(401, "invalid_credentials", "凭证无效", "test-id")
        body = json.loads(resp.body)
        assert set(body.keys()) == {"error_code", "message", "request_id"}
        assert body["error_code"] == "invalid_credentials"
        assert body["message"] == "凭证无效"
        assert body["request_id"] == "test-id"

    def test_status_code(self):
        """响应状态码应与传入一致"""
        resp = create_error_response(403, "app_disabled", "应用已被禁用", "rid")
        assert resp.status_code == 403

    def test_x_request_id_header(self):
        """响应头应包含 X-Request-Id"""
        resp = create_error_response(500, "internal_error", "内部错误", "my-rid")
        assert resp.headers.get("X-Request-Id") == "my-rid"

    def test_auto_generate_request_id(self):
        """未传入 request_id 时应自动生成"""
        resp = create_error_response(400, "validation_error", "参数错误")
        body = json.loads(resp.body)
        # 验证自动生成的是合法 UUID
        uuid.UUID(body["request_id"])
        assert resp.headers.get("X-Request-Id") == body["request_id"]

    def test_no_extra_fields(self):
        """响应体不应包含额外字段"""
        resp = create_error_response(502, "upstream_error", "下游错误", "rid")
        body = json.loads(resp.body)
        assert len(body) == 3


# ---------------------------------------------------------------------------
# _extract_error_code_and_message 测试
# ---------------------------------------------------------------------------

class TestExtractErrorCodeAndMessage:
    """测试从 HTTPException detail 中提取 error_code 和 message"""

    def test_dict_with_error_code_and_message(self):
        """dict 格式 detail 应提取 error_code 和 message"""
        code, msg = _extract_error_code_and_message(
            403, {"error_code": "insufficient_scope", "message": "权限不足"}
        )
        assert code == "insufficient_scope"
        assert msg == "权限不足"

    def test_dict_without_error_code(self):
        """dict 缺少 error_code 时应使用状态码映射的默认值"""
        code, msg = _extract_error_code_and_message(
            401, {"message": "凭证无效"}
        )
        assert code == "invalid_credentials"
        assert msg == "凭证无效"

    def test_string_detail(self):
        """字符串 detail 应作为 message，error_code 从状态码映射"""
        code, msg = _extract_error_code_and_message(401, "凭证无效")
        assert code == "invalid_credentials"
        assert msg == "凭证无效"

    def test_none_detail(self):
        """None detail 应返回默认错误信息"""
        code, msg = _extract_error_code_and_message(500, None)
        assert code == "internal_error"
        assert msg == "未知错误"

    def test_unknown_status_code(self):
        """未映射的状态码应默认为 internal_error"""
        code, msg = _extract_error_code_and_message(418, "I'm a teapot")
        assert code == "internal_error"
        assert msg == "I'm a teapot"


# ---------------------------------------------------------------------------
# FastAPI 异常处理器测试（使用 TestClient 集成测试）
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    """创建带有统一错误处理的测试 FastAPI 应用"""
    app = FastAPI()

    # 注册中间件
    app.add_middleware(RequestIdMiddleware)

    # 注册异常处理器
    app.add_exception_handler(StarletteHTTPException, gateway_exception_handler)
    app.add_exception_handler(RequestValidationError, gateway_validation_exception_handler)
    app.add_exception_handler(Exception, gateway_generic_exception_handler)

    # 测试端点
    @app.get("/ok")
    async def ok_endpoint():
        return {"status": "ok"}

    @app.get("/error-401")
    async def error_401():
        raise HTTPException(status_code=401, detail="凭证无效")

    @app.get("/error-403-dict")
    async def error_403_dict():
        raise HTTPException(
            status_code=403,
            detail={"error_code": "insufficient_scope", "message": "权限不足"},
        )

    @app.get("/error-503")
    async def error_503():
        raise HTTPException(status_code=503, detail="下游服务不可用")

    @app.get("/error-500-unexpected")
    async def error_500_unexpected():
        raise RuntimeError("unexpected internal error")

    class StrictBody(BaseModel):
        name: str = Field(..., min_length=1)

    @app.post("/validate")
    async def validate_endpoint(body: StrictBody):
        return {"name": body.name}

    return app


@pytest.fixture
def client():
    app = _create_test_app()
    return TestClient(app, raise_server_exceptions=False)


class TestGatewayExceptionHandler:
    """测试 HTTPException 统一错误处理"""

    def test_401_string_detail(self, client):
        """字符串 detail 的 401 应返回统一格式"""
        resp = client.get("/error-401")
        assert resp.status_code == 401
        body = resp.json()
        assert set(body.keys()) == {"error_code", "message", "request_id"}
        assert body["error_code"] == "invalid_credentials"
        assert body["message"] == "凭证无效"
        uuid.UUID(body["request_id"])  # 合法 UUID

    def test_403_dict_detail(self, client):
        """dict detail 的 403 应提取 error_code"""
        resp = client.get("/error-403-dict")
        assert resp.status_code == 403
        body = resp.json()
        assert body["error_code"] == "insufficient_scope"
        assert body["message"] == "权限不足"

    def test_503_error(self, client):
        """503 应返回 service_unavailable"""
        resp = client.get("/error-503")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error_code"] == "service_unavailable"

    def test_x_request_id_in_error_response(self, client):
        """错误响应应包含 X-Request-Id 头"""
        resp = client.get("/error-401")
        rid = resp.headers.get("X-Request-Id")
        assert rid is not None
        uuid.UUID(rid)  # 合法 UUID

    def test_error_response_request_id_matches_header(self, client):
        """响应体中的 request_id 应与 X-Request-Id 头一致"""
        resp = client.get("/error-401")
        body = resp.json()
        assert body["request_id"] == resp.headers.get("X-Request-Id")

    def test_no_internal_details_leaked(self, client):
        """错误响应不应泄露内部实现细节"""
        resp = client.get("/error-401")
        body = resp.json()
        # 仅包含三个字段
        assert len(body) == 3
        # 不包含 traceback、detail、stack 等内部信息
        for key in ["traceback", "stack", "detail", "exception"]:
            assert key not in body


class TestGatewayValidationExceptionHandler:
    """测试请求验证异常处理"""

    def test_validation_error_format(self, client):
        """验证错误应返回 422 + validation_error"""
        resp = client.post("/validate", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error_code"] == "validation_error"
        assert body["message"] == "请求参数验证失败"
        uuid.UUID(body["request_id"])

    def test_validation_error_hides_field_details(self, client):
        """验证错误不应暴露内部字段名"""
        resp = client.post("/validate", json={})
        body = resp.json()
        # 不包含 pydantic 的 detail 数组
        assert "detail" not in body
        assert "loc" not in str(body)


class TestGatewayGenericExceptionHandler:
    """测试兜底异常处理"""

    def test_unexpected_error_returns_500(self, client):
        """未处理的异常应返回 500 internal_error"""
        resp = client.get("/error-500-unexpected")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error_code"] == "internal_error"
        assert body["message"] == "网关内部错误"

    def test_unexpected_error_hides_details(self, client):
        """未处理的异常不应暴露内部错误信息"""
        resp = client.get("/error-500-unexpected")
        body = resp.json()
        assert "unexpected internal error" not in body["message"]
        assert "RuntimeError" not in body["message"]


# ---------------------------------------------------------------------------
# RequestIdMiddleware 测试
# ---------------------------------------------------------------------------

class TestRequestIdMiddleware:
    """测试 request_id 中间件"""

    def test_success_response_has_x_request_id(self, client):
        """成功响应应包含 X-Request-Id 头"""
        resp = client.get("/ok")
        assert resp.status_code == 200
        rid = resp.headers.get("X-Request-Id")
        assert rid is not None
        uuid.UUID(rid)

    def test_different_requests_have_different_ids(self, client):
        """不同请求应有不同的 request_id"""
        resp1 = client.get("/ok")
        resp2 = client.get("/ok")
        rid1 = resp1.headers.get("X-Request-Id")
        rid2 = resp2.headers.get("X-Request-Id")
        assert rid1 != rid2

    def test_error_response_has_x_request_id(self, client):
        """错误响应也应包含 X-Request-Id 头"""
        resp = client.get("/error-401")
        rid = resp.headers.get("X-Request-Id")
        assert rid is not None
        uuid.UUID(rid)
