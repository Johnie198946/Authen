"""
CSRF保护测试

测试CSRF Token生成、验证和中间件功能。

需求：11.2 - 实现CSRF保护机制
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.utils.csrf import (
    generate_csrf_token,
    verify_csrf_token,
    store_csrf_token,
    validate_and_consume_csrf_token,
    get_csrf_token_from_request
)
from shared.middleware.csrf_protection import CSRFProtectionMiddleware
from unittest.mock import Mock, patch


# ==================== CSRF Token生成和验证测试 ====================

def test_generate_csrf_token():
    """
    测试CSRF Token生成
    
    验证：
    - Token生成成功
    - Token长度正确
    - Token格式正确（hex编码）
    """
    token = generate_csrf_token()
    
    assert token is not None
    assert len(token) == 64  # 32字节 * 2（hex编码）
    assert all(c in '0123456789abcdef' for c in token)


def test_generate_csrf_token_with_session():
    """
    测试带会话ID的CSRF Token生成
    
    验证：
    - Token包含签名
    - Token格式正确
    """
    session_id = "test_session_123"
    token = generate_csrf_token(session_id)
    
    assert token is not None
    assert ":" in token  # 包含签名分隔符
    
    parts = token.split(":")
    assert len(parts) == 2
    assert len(parts[0]) == 64  # 随机Token部分
    assert len(parts[1]) == 64  # HMAC签名部分


def test_verify_csrf_token_simple():
    """
    测试简单CSRF Token验证
    
    验证：
    - 有效Token验证通过
    - 无效Token验证失败
    """
    # 生成Token
    token = generate_csrf_token()
    
    # 验证Token
    assert verify_csrf_token(token) is True
    
    # 验证无效Token
    assert verify_csrf_token("invalid_token") is False
    assert verify_csrf_token("") is False
    assert verify_csrf_token(None) is False


def test_verify_csrf_token_with_session():
    """
    测试带会话ID的CSRF Token验证
    
    验证：
    - 正确的session_id验证通过
    - 错误的session_id验证失败
    """
    session_id = "test_session_123"
    token = generate_csrf_token(session_id)
    
    # 使用正确的session_id验证
    assert verify_csrf_token(token, session_id) is True
    
    # 使用错误的session_id验证
    assert verify_csrf_token(token, "wrong_session") is False
    
    # 不提供session_id验证（应该失败，因为Token包含签名）
    assert verify_csrf_token(token) is False


@patch('shared.redis_client.get_redis')
def test_store_csrf_token(mock_get_redis):
    """
    测试CSRF Token存储
    
    验证：
    - Token存储到Redis
    - 设置正确的过期时间
    """
    mock_redis = Mock()
    mock_get_redis.return_value = mock_redis
    
    token = generate_csrf_token()
    user_id = "user_123"
    
    store_csrf_token(token, user_id)
    
    # 验证Redis调用
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    
    assert f"csrf_token:{user_id}:{token}" in call_args[0][0]
    assert call_args[0][1] == 3600  # 60分钟 * 60秒
    assert call_args[0][2] == "1"


@patch('shared.redis_client.get_redis')
def test_validate_and_consume_csrf_token(mock_get_redis):
    """
    测试CSRF Token验证和消费
    
    验证：
    - 有效Token验证通过并被删除
    - Token只能使用一次
    """
    mock_redis = Mock()
    mock_get_redis.return_value = mock_redis
    
    token = generate_csrf_token()
    
    # 模拟Token存在
    mock_redis.exists.return_value = True
    
    # 验证并消费Token
    result = validate_and_consume_csrf_token(token)
    
    assert result is True
    mock_redis.exists.assert_called_once()
    mock_redis.delete.assert_called_once()


@patch('shared.redis_client.get_redis')
def test_validate_and_consume_csrf_token_not_exists(mock_get_redis):
    """
    测试不存在的CSRF Token验证
    
    验证：
    - 不存在的Token验证失败
    """
    mock_redis = Mock()
    mock_get_redis.return_value = mock_redis
    
    token = generate_csrf_token()
    
    # 模拟Token不存在
    mock_redis.exists.return_value = False
    
    # 验证Token
    result = validate_and_consume_csrf_token(token)
    
    assert result is False
    mock_redis.exists.assert_called_once()
    mock_redis.delete.assert_not_called()


# ==================== CSRF中间件测试 ====================

def test_csrf_middleware_get_request():
    """
    测试CSRF中间件 - GET请求
    
    验证：
    - GET请求不需要CSRF Token
    - 请求正常通过
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.get("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    response = client.get("/test")
    
    assert response.status_code == 200
    assert response.json() == {"message": "success"}


def test_csrf_middleware_post_without_token():
    """
    测试CSRF中间件 - POST请求缺少Token
    
    验证：
    - POST请求缺少CSRF Token时被拒绝
    - 返回403错误
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/test")
    
    assert response.status_code == 403
    assert "CSRF token missing" in response.json()["detail"]


def test_csrf_middleware_post_with_valid_token():
    """
    测试CSRF中间件 - POST请求带有效Token
    
    验证：
    - POST请求带有效CSRF Token时通过
    - 请求正常处理
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 生成有效Token
    token = generate_csrf_token()
    
    # 发送带Token的请求
    response = client.post(
        "/test",
        headers={"X-CSRF-Token": token}
    )
    
    assert response.status_code == 200
    assert response.json() == {"message": "success"}


def test_csrf_middleware_post_with_invalid_token():
    """
    测试CSRF中间件 - POST请求带无效Token
    
    验证：
    - POST请求带无效CSRF Token时被拒绝
    - 返回403错误
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # 发送带无效Token的请求
    response = client.post(
        "/test",
        headers={"X-CSRF-Token": "invalid_token"}
    )
    
    assert response.status_code == 403
    assert "Invalid CSRF token" in response.json()["detail"]


def test_csrf_middleware_exempt_paths():
    """
    测试CSRF中间件 - 豁免路径
    
    验证：
    - 豁免路径不需要CSRF Token
    - 登录、注册等接口正常工作
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/api/v1/auth/login")
    async def login():
        return {"message": "login success"}
    
    @app.post("/api/v1/auth/register/email")
    async def register():
        return {"message": "register success"}
    
    client = TestClient(app)
    
    # 登录接口不需要CSRF Token
    response = client.post("/api/v1/auth/login")
    assert response.status_code == 200
    
    # 注册接口不需要CSRF Token
    response = client.post("/api/v1/auth/register/email")
    assert response.status_code == 200


def test_csrf_middleware_put_request():
    """
    测试CSRF中间件 - PUT请求
    
    验证：
    - PUT请求需要CSRF Token
    - 缺少Token时被拒绝
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.put("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # 不带Token的PUT请求
    response = client.put("/test")
    assert response.status_code == 403
    
    # 带有效Token的PUT请求
    token = generate_csrf_token()
    client2 = TestClient(app)
    response = client2.put(
        "/test",
        headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200


def test_csrf_middleware_delete_request():
    """
    测试CSRF中间件 - DELETE请求
    
    验证：
    - DELETE请求需要CSRF Token
    - 缺少Token时被拒绝
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.delete("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app, raise_server_exceptions=False)
    
    # 不带Token的DELETE请求
    response = client.delete("/test")
    assert response.status_code == 403
    
    # 带有效Token的DELETE请求
    token = generate_csrf_token()
    client2 = TestClient(app)
    response = client2.delete(
        "/test",
        headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200


def test_csrf_middleware_token_in_query_params():
    """
    测试CSRF中间件 - Token在查询参数中
    
    验证：
    - 支持从查询参数获取Token
    - Token验证正常工作
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 生成有效Token
    token = generate_csrf_token()
    
    # Token在查询参数中
    response = client.post(f"/test?csrf_token={token}")
    
    assert response.status_code == 200
    assert response.json() == {"message": "success"}


def test_csrf_middleware_token_in_json_body():
    """
    测试CSRF中间件 - Token在JSON请求体中
    
    验证：
    - 支持从JSON请求体获取Token
    - Token验证正常工作
    """
    app = FastAPI()
    app.add_middleware(CSRFProtectionMiddleware)
    
    @app.post("/test")
    async def test_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 生成有效Token
    token = generate_csrf_token()
    
    # Token在JSON请求体中
    response = client.post(
        "/test",
        json={"csrf_token": token, "data": "test"}
    )
    
    assert response.status_code == 200
    assert response.json() == {"message": "success"}


def test_get_csrf_token_from_request_header():
    """
    测试从请求头提取CSRF Token
    
    验证：
    - 正确提取X-CSRF-Token头
    """
    mock_request = Mock()
    mock_request.headers.get.return_value = "test_token_123"
    mock_request.query_params.get.return_value = None
    
    token = get_csrf_token_from_request(mock_request)
    
    assert token == "test_token_123"
    mock_request.headers.get.assert_called_with("X-CSRF-Token")


def test_get_csrf_token_from_request_query():
    """
    测试从查询参数提取CSRF Token
    
    验证：
    - 正确提取csrf_token查询参数
    """
    mock_request = Mock()
    mock_request.headers.get.return_value = None
    mock_request.query_params.get.return_value = "test_token_456"
    
    token = get_csrf_token_from_request(mock_request)
    
    assert token == "test_token_456"


def test_csrf_middleware_custom_exempt_paths():
    """
    测试CSRF中间件 - 自定义豁免路径
    
    验证：
    - 可以添加自定义豁免路径
    - 自定义路径不需要CSRF Token
    """
    app = FastAPI()
    app.add_middleware(
        CSRFProtectionMiddleware,
        exempt_paths=["/api/v1/custom/endpoint"]
    )
    
    @app.post("/api/v1/custom/endpoint")
    async def custom_endpoint():
        return {"message": "success"}
    
    client = TestClient(app)
    
    # 自定义豁免路径不需要Token
    response = client.post("/api/v1/custom/endpoint")
    assert response.status_code == 200
