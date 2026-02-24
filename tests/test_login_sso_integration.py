"""
测试登录与SSO会话集成

需求：2.1 - 用户在任一应用登录成功时创建全局会话
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.user import Base, User, SSOSession
from shared.database import get_db
from shared.utils.crypto import hash_password
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auth.main import app


# 测试数据库配置
TEST_DATABASE_URL = "sqlite:///./test_login_sso.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# 覆盖依赖
app.dependency_overrides[get_db] = override_get_db

# 创建测试客户端
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前设置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user():
    """创建测试用户"""
    db = TestingSessionLocal()
    try:
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("TestPass123!"),
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def test_login_creates_sso_session(test_user):
    """
    测试登录时创建SSO会话
    
    需求：2.1 - 用户在任一应用登录成功时创建全局会话
    """
    # 登录
    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "test@example.com",
            "password": "TestPass123!"
        }
    )
    
    assert response.status_code == 200, f"登录应该成功，状态码：{response.status_code}"
    
    data = response.json()
    
    # 验证响应包含SSO会话令牌
    assert "sso_session_token" in data, "登录响应应该包含SSO会话令牌"
    assert data["sso_session_token"] is not None
    assert len(data["sso_session_token"]) > 0
    
    # 验证响应包含其他必要字段
    assert "access_token" in data
    assert "refresh_token" in data
    assert "user" in data
    
    # 验证SSO会话已在数据库中创建
    db = TestingSessionLocal()
    try:
        session = db.query(SSOSession).filter(
            SSOSession.session_token == data["sso_session_token"]
        ).first()
        
        assert session is not None, "SSO会话应该在数据库中创建"
        assert str(session.user_id) == str(test_user.id), "会话应该关联到正确的用户"
        assert session.expires_at is not None, "会话应该有过期时间"
        assert session.last_activity_at is not None, "会话应该有最后活动时间"
    finally:
        db.close()


def test_multiple_logins_create_multiple_sessions(test_user):
    """
    测试多次登录创建多个会话
    
    需求：2.1 - 每次登录都应该创建新的SSO会话
    """
    # 第一次登录
    response1 = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "test@example.com",
            "password": "TestPass123!"
        }
    )
    assert response1.status_code == 200
    session_token1 = response1.json()["sso_session_token"]
    
    # 第二次登录
    response2 = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "test@example.com",
            "password": "TestPass123!"
        }
    )
    assert response2.status_code == 200
    session_token2 = response2.json()["sso_session_token"]
    
    # 两个会话令牌应该不同
    assert session_token1 != session_token2, "每次登录应该创建不同的会话"
    
    # 验证两个会话都存在
    db = TestingSessionLocal()
    try:
        sessions = db.query(SSOSession).filter(
            SSOSession.user_id == test_user.id
        ).all()
        
        assert len(sessions) == 2, "应该有两个会话"
        
        session_tokens = [s.session_token for s in sessions]
        assert session_token1 in session_tokens
        assert session_token2 in session_tokens
    finally:
        db.close()


def test_login_with_phone_creates_sso_session():
    """测试使用手机号登录也创建SSO会话"""
    # 先创建用户
    db = TestingSessionLocal()
    try:
        user = User(
            username="phoneuser",
            phone="+8613800138000",
            password_hash=hash_password("TestPass123!"),
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    
    # 使用手机号登录
    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "+8613800138000",
            "password": "TestPass123!"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # 验证SSO会话令牌存在
    assert "sso_session_token" in data
    assert data["sso_session_token"] is not None
    
    # 验证会话在数据库中
    db = TestingSessionLocal()
    try:
        session = db.query(SSOSession).filter(
            SSOSession.session_token == data["sso_session_token"]
        ).first()
        
        assert session is not None
        assert str(session.user_id) == str(user_id)
    finally:
        db.close()


def test_failed_login_does_not_create_session():
    """测试登录失败不创建SSO会话"""
    # 创建用户
    db = TestingSessionLocal()
    try:
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("TestPass123!"),
            status="active"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()
    
    # 使用错误密码登录
    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "test@example.com",
            "password": "WrongPassword!"
        }
    )
    
    assert response.status_code == 401, "错误密码应该返回401"
    
    # 验证没有创建SSO会话
    db = TestingSessionLocal()
    try:
        sessions = db.query(SSOSession).filter(
            SSOSession.user_id == user_id
        ).all()
        
        assert len(sessions) == 0, "登录失败不应该创建SSO会话"
    finally:
        db.close()


def test_sso_session_token_is_unique():
    """测试SSO会话令牌是唯一的"""
    # 创建多个用户并登录
    session_tokens = []
    
    for i in range(5):
        # 创建用户
        db = TestingSessionLocal()
        try:
            user = User(
                username=f"user{i}",
                email=f"user{i}@example.com",
                password_hash=hash_password("TestPass123!"),
                status="active"
            )
            db.add(user)
            db.commit()
        finally:
            db.close()
        
        # 登录
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": f"user{i}@example.com",
                "password": "TestPass123!"
            }
        )
        
        assert response.status_code == 200
        session_token = response.json()["sso_session_token"]
        session_tokens.append(session_token)
    
    # 验证所有令牌都是唯一的
    assert len(session_tokens) == len(set(session_tokens)), \
        "所有SSO会话令牌应该是唯一的"


def test_sso_session_has_correct_expiry():
    """测试SSO会话有正确的过期时间"""
    # 创建用户
    db = TestingSessionLocal()
    try:
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("TestPass123!"),
            status="active"
        )
        db.add(user)
        db.commit()
    finally:
        db.close()
    
    # 登录
    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "test@example.com",
            "password": "TestPass123!"
        }
    )
    
    assert response.status_code == 200
    session_token = response.json()["sso_session_token"]
    
    # 检查会话过期时间
    db = TestingSessionLocal()
    try:
        from datetime import datetime, timedelta
        
        session = db.query(SSOSession).filter(
            SSOSession.session_token == session_token
        ).first()
        
        assert session is not None
        
        # 验证过期时间在未来
        assert session.expires_at > datetime.utcnow(), \
            "会话过期时间应该在未来"
        
        # 验证过期时间大约是24小时后（允许1分钟误差）
        expected_expiry = datetime.utcnow() + timedelta(hours=24)
        time_diff = abs((session.expires_at - expected_expiry).total_seconds())
        assert time_diff < 60, \
            f"会话过期时间应该大约是24小时后，实际差异：{time_diff}秒"
    finally:
        db.close()
