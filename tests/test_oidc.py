"""
OpenID Connect功能测试
验证需求：2.4
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.database import Base, get_db
from shared.models.user import User
from shared.utils.jwt import decode_token
from services.sso.main import app
import uuid
from datetime import datetime

# 测试数据库配置
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_oidc.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """每个测试前创建数据库表，测试后清理"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_user():
    """创建测试用户"""
    db = TestingSessionLocal()
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        phone="+8613800138000",
        password_hash="hashed_password",
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = str(user.id)
    db.close()
    return user_id

def test_id_token_generation(test_user):
    """
    测试ID Token生成
    验证需求：2.4
    
    测试场景：
    1. 获取授权码
    2. 交换授权码获取Token
    3. 验证返回的ID Token包含用户信息
    """
    # 步骤1：获取授权码
    response = client.get(
        "/api/v1/sso/authorize",
        params={
            "client_id": "test_client",
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "scope": "openid profile email",
            "user_id": test_user
        }
    )
    assert response.status_code == 200
    auth_code = response.json()["authorization_code"]
    assert auth_code is not None
    
    # 步骤2：交换授权码获取Token
    response = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    assert response.status_code == 200
    token_data = response.json()
    
    # 验证返回的Token结构
    assert "access_token" in token_data
    assert "id_token" in token_data
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in"] > 0
    
    # 步骤3：验证ID Token包含用户信息
    id_token = token_data["id_token"]
    payload = decode_token(id_token)
    
    assert payload is not None
    assert payload["sub"] == test_user
    assert payload["name"] == "testuser"
    assert payload["email"] == "test@example.com"
    assert payload["email_verified"] is True
    assert payload["preferred_username"] == "testuser"
    assert payload["aud"] == "test_client"  # OpenID Connect要求
    assert "iat" in payload
    assert "exp" in payload
    assert "iss" in payload

def test_userinfo_endpoint(test_user):
    """
    测试UserInfo端点
    验证需求：2.4
    
    测试场景：
    1. 获取授权码并交换Token
    2. 使用Access Token访问UserInfo端点
    3. 验证返回的用户信息完整且正确
    """
    # 步骤1：获取授权码
    response = client.get(
        "/api/v1/sso/authorize",
        params={
            "client_id": "test_client",
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "user_id": test_user
        }
    )
    auth_code = response.json()["authorization_code"]
    
    # 交换Token
    response = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    access_token = response.json()["access_token"]
    
    # 步骤2：使用Access Token访问UserInfo端点
    response = client.get(
        "/api/v1/sso/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    assert response.status_code == 200
    userinfo = response.json()
    
    # 步骤3：验证返回的用户信息
    assert userinfo["sub"] == test_user
    assert userinfo["name"] == "testuser"
    assert userinfo["preferred_username"] == "testuser"
    assert userinfo["email"] == "test@example.com"
    assert userinfo["email_verified"] is True
    assert userinfo["phone_number"] == "+8613800138000"
    assert userinfo["phone_number_verified"] is True
    assert "updated_at" in userinfo

def test_userinfo_without_token():
    """
    测试未授权访问UserInfo端点
    验证需求：2.4
    
    测试场景：不提供Token访问UserInfo端点应返回401错误
    """
    response = client.get("/api/v1/sso/userinfo")
    assert response.status_code == 401
    assert "未授权" in response.json()["detail"]

def test_userinfo_with_invalid_token():
    """
    测试使用无效Token访问UserInfo端点
    验证需求：2.4
    
    测试场景：使用无效Token访问UserInfo端点应返回401错误
    """
    response = client.get(
        "/api/v1/sso/userinfo",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401
    assert "Token无效" in response.json()["detail"]

def test_id_token_contains_required_claims(test_user):
    """
    测试ID Token包含所有必需的声明
    验证需求：2.4
    
    OpenID Connect规范要求ID Token必须包含：
    - iss (issuer)
    - sub (subject)
    - aud (audience)
    - exp (expiration time)
    - iat (issued at)
    """
    # 获取授权码
    response = client.get(
        "/api/v1/sso/authorize",
        params={
            "client_id": "test_client",
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "user_id": test_user
        }
    )
    auth_code = response.json()["authorization_code"]
    
    # 交换Token
    response = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    id_token = response.json()["id_token"]
    payload = decode_token(id_token)
    
    # 验证必需的声明
    assert "iss" in payload, "ID Token必须包含iss声明"
    assert "sub" in payload, "ID Token必须包含sub声明"
    assert "aud" in payload, "ID Token必须包含aud声明"
    assert "exp" in payload, "ID Token必须包含exp声明"
    assert "iat" in payload, "ID Token必须包含iat声明"
    
    # 验证声明的值
    assert payload["sub"] == test_user
    assert payload["aud"] == "test_client"
    assert payload["exp"] > payload["iat"]

def test_multiple_users_different_tokens(test_user):
    """
    测试不同用户获取不同的Token
    验证需求：2.4
    
    测试场景：
    1. 创建两个不同的用户
    2. 分别获取Token
    3. 验证Token包含不同的用户信息
    """
    # 创建第二个用户
    db = TestingSessionLocal()
    user2 = User(
        id=uuid.uuid4(),
        username="testuser2",
        email="test2@example.com",
        password_hash="hashed_password",
        status="active"
    )
    db.add(user2)
    db.commit()
    user2_id = str(user2.id)
    db.close()
    
    # 用户1获取Token
    response1 = client.get(
        "/api/v1/sso/authorize",
        params={
            "client_id": "test_client",
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "user_id": test_user
        }
    )
    auth_code1 = response1.json()["authorization_code"]
    
    response1 = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code1,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    id_token1 = response1.json()["id_token"]
    payload1 = decode_token(id_token1)
    
    # 用户2获取Token
    response2 = client.get(
        "/api/v1/sso/authorize",
        params={
            "client_id": "test_client",
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "user_id": user2_id
        }
    )
    auth_code2 = response2.json()["authorization_code"]
    
    response2 = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code2,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    id_token2 = response2.json()["id_token"]
    payload2 = decode_token(id_token2)
    
    # 验证Token包含不同的用户信息
    assert payload1["sub"] != payload2["sub"]
    assert payload1["email"] == "test@example.com"
    assert payload2["email"] == "test2@example.com"
    assert payload1["name"] == "testuser"
    assert payload2["name"] == "testuser2"

def test_authorization_code_single_use(test_user):
    """
    测试授权码只能使用一次
    验证需求：2.4
    
    测试场景：
    1. 获取授权码
    2. 第一次交换成功
    3. 第二次使用相同授权码应失败
    """
    # 获取授权码
    response = client.get(
        "/api/v1/sso/authorize",
        params={
            "client_id": "test_client",
            "redirect_uri": "https://example.com/callback",
            "response_type": "code",
            "user_id": test_user
        }
    )
    auth_code = response.json()["authorization_code"]
    
    # 第一次交换成功
    response1 = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    assert response1.status_code == 200
    
    # 第二次使用相同授权码应失败
    response2 = client.post(
        "/api/v1/sso/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": "test_client",
            "client_secret": "test_secret",
            "redirect_uri": "https://example.com/callback"
        }
    )
    assert response2.status_code == 400
    assert "无效的授权码" in response2.json()["detail"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
