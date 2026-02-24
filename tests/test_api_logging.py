"""
API调用日志测试

测试API日志中间件的功能，验证：
- 请求信息记录
- 响应时间记录
- 敏感数据过滤
- 用户ID提取

需求：9.8 - API网关应记录所有API调用日志
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import time

from shared.database import Base, get_db
from shared.models.system import APILog
from shared.models.user import User
from shared.middleware.api_logger import APILoggerMiddleware, filter_sensitive_data
from shared.utils.crypto import hash_password
from shared.utils.jwt import create_access_token


# 测试数据库设置
TEST_DATABASE_URL = "sqlite:///./test_api_logging.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """创建测试数据库"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_app(db):
    """创建测试应用"""
    app = FastAPI()
    
    # 添加API日志中间件
    app.add_middleware(APILoggerMiddleware)
    
    # 覆盖数据库依赖
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    # 添加测试端点
    @app.get("/test")
    async def test_endpoint():
        return {"message": "test"}
    
    @app.post("/test")
    async def test_post_endpoint(data: dict):
        return {"received": data}
    
    @app.get("/test/error")
    async def test_error_endpoint():
        raise Exception("Test error")
    
    return app


@pytest.fixture
def test_user(db):
    """创建测试用户"""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("password123"),
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_api_logging_get_request(test_app, db):
    """
    测试GET请求日志记录
    
    验证：
    - 记录请求方法
    - 记录请求路径
    - 记录查询参数
    - 记录响应状态码
    - 记录响应时间
    """
    client = TestClient(test_app)
    
    # 发送GET请求
    response = client.get("/test?param1=value1&param2=value2")
    
    assert response.status_code == 200
    
    # 等待日志记录完成
    time.sleep(0.5)
    
    # 查询日志
    api_log = db.query(APILog).filter(APILog.path == "/test").first()
    
    assert api_log is not None
    assert api_log.method == "GET"
    assert api_log.path == "/test"
    assert api_log.query_params == {"param1": "value1", "param2": "value2"}
    assert api_log.status_code == "200"
    assert api_log.response_time is not None
    assert float(api_log.response_time) > 0


def test_api_logging_post_request(test_app, db):
    """
    测试POST请求日志记录
    
    验证：
    - 记录请求体
    - 过滤敏感数据
    """
    client = TestClient(test_app)
    
    # 发送POST请求
    request_data = {
        "username": "testuser",
        "password": "secret123",
        "email": "test@example.com"
    }
    
    response = client.post("/test", json=request_data)
    
    assert response.status_code == 200
    
    # 等待日志记录完成
    time.sleep(0.5)
    
    # 查询日志
    api_log = db.query(APILog).filter(
        APILog.path == "/test",
        APILog.method == "POST"
    ).first()
    
    assert api_log is not None
    assert api_log.method == "POST"
    assert api_log.request_body is not None
    
    # 验证敏感数据被过滤
    assert api_log.request_body["username"] == "testuser"
    assert api_log.request_body["password"] == "***"  # 密码应该被过滤
    assert api_log.request_body["email"] == "test@example.com"


def test_api_logging_with_user_id(test_app, db, test_user):
    """
    测试带用户ID的请求日志记录
    
    验证：
    - 从JWT token提取用户ID
    - 记录用户ID到日志
    """
    client = TestClient(test_app)
    
    # 创建JWT token
    token = create_access_token({
        "sub": str(test_user.id),
        "username": test_user.username
    })
    
    # 发送带token的请求
    response = client.get(
        "/test",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    
    # 等待日志记录完成
    time.sleep(0.5)
    
    # 查询日志
    api_log = db.query(APILog).filter(APILog.path == "/test").first()
    
    assert api_log is not None
    assert api_log.user_id == test_user.id


def test_api_logging_response_time_header(test_app):
    """
    测试响应时间头
    
    验证：
    - 响应包含X-Response-Time头
    - 响应时间格式正确
    """
    client = TestClient(test_app)
    
    response = client.get("/test")
    
    assert response.status_code == 200
    assert "X-Response-Time" in response.headers
    
    # 验证响应时间格式（应该是 "X.XXms"）
    response_time = response.headers["X-Response-Time"]
    assert response_time.endswith("ms")
    
    # 提取数值部分
    time_value = float(response_time[:-2])
    assert time_value > 0


def test_filter_sensitive_data():
    """
    测试敏感数据过滤函数
    
    验证：
    - 密码字段被过滤
    - Token字段被过滤
    - 嵌套对象中的敏感字段被过滤
    - 非敏感字段保持不变
    """
    # 测试简单对象
    data = {
        "username": "testuser",
        "password": "secret123",
        "email": "test@example.com",
        "access_token": "token123"
    }
    
    filtered = filter_sensitive_data(data)
    
    assert filtered["username"] == "testuser"
    assert filtered["password"] == "***"
    assert filtered["email"] == "test@example.com"
    assert filtered["access_token"] == "***"
    
    # 测试嵌套对象
    nested_data = {
        "user": {
            "username": "testuser",
            "password": "secret123"
        },
        "credentials": {
            "api_key": "key123",
            "secret": "secret456"
        }
    }
    
    filtered_nested = filter_sensitive_data(nested_data)
    
    assert filtered_nested["user"]["username"] == "testuser"
    assert filtered_nested["user"]["password"] == "***"
    assert filtered_nested["credentials"]["api_key"] == "***"
    assert filtered_nested["credentials"]["secret"] == "***"
    
    # 测试数组
    array_data = {
        "users": [
            {"username": "user1", "password": "pass1"},
            {"username": "user2", "password": "pass2"}
        ]
    }
    
    filtered_array = filter_sensitive_data(array_data)
    
    assert filtered_array["users"][0]["username"] == "user1"
    assert filtered_array["users"][0]["password"] == "***"
    assert filtered_array["users"][1]["username"] == "user2"
    assert filtered_array["users"][1]["password"] == "***"


def test_api_logging_ip_address(test_app, db):
    """
    测试IP地址记录
    
    验证：
    - 记录客户端IP地址
    """
    client = TestClient(test_app)
    
    # 发送请求
    response = client.get("/test")
    
    assert response.status_code == 200
    
    # 等待日志记录完成
    time.sleep(0.5)
    
    # 查询日志
    api_log = db.query(APILog).filter(APILog.path == "/test").first()
    
    assert api_log is not None
    assert api_log.ip_address is not None  # TestClient会提供一个IP地址


def test_api_logging_user_agent(test_app, db):
    """
    测试用户代理记录
    
    验证：
    - 记录User-Agent头
    """
    client = TestClient(test_app)
    
    # 发送带User-Agent的请求
    response = client.get(
        "/test",
        headers={"User-Agent": "TestClient/1.0"}
    )
    
    assert response.status_code == 200
    
    # 等待日志记录完成
    time.sleep(0.5)
    
    # 查询日志
    api_log = db.query(APILog).filter(APILog.path == "/test").first()
    
    assert api_log is not None
    assert api_log.user_agent == "TestClient/1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
