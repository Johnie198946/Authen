"""
测试SSO服务端点

需求：2.1, 2.2 - SSO会话管理端点测试
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.user import Base, User
from shared.database import get_db
from shared.utils.crypto import hash_password
from shared.utils.sso_session import create_sso_session
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sso.main import app


# 测试数据库配置
TEST_DATABASE_URL = "sqlite:///./test_sso_endpoints.db"
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


@pytest.fixture
def test_session(test_user):
    """创建测试SSO会话"""
    db = TestingSessionLocal()
    try:
        session = create_sso_session(str(test_user.id), db)
        return session
    finally:
        db.close()


def test_validate_session_endpoint(test_session):
    """
    测试验证SSO会话端点
    
    需求：2.2 - 其他应用可以查询和验证SSO会话
    """
    response = client.get(
        f"/api/v1/sso/session/validate?session_token={test_session.session_token}"
    )
    
    assert response.status_code == 200, f"验证会话应该成功，状态码：{response.status_code}"
    
    data = response.json()
    assert data["valid"] is True, "会话应该有效"
    assert "user" in data, "响应应该包含用户信息"
    assert "session" in data, "响应应该包含会话信息"
    
    # 验证用户信息
    user_data = data["user"]
    assert "id" in user_data
    assert "username" in user_data
    assert user_data["username"] == "testuser"
    assert user_data["email"] == "test@example.com"
    
    # 验证会话信息
    session_data = data["session"]
    assert "created_at" in session_data
    assert "expires_at" in session_data
    assert "last_activity_at" in session_data


def test_validate_invalid_session():
    """测试验证无效会话"""
    response = client.get(
        "/api/v1/sso/session/validate?session_token=invalid_token"
    )
    
    assert response.status_code == 401, "无效会话应该返回401"
    
    data = response.json()
    assert "detail" in data


def test_get_session_info_endpoint(test_session):
    """
    测试查询SSO会话信息端点
    
    需求：2.2 - 查询SSO会话详细信息
    """
    response = client.get(
        f"/api/v1/sso/session/info?session_token={test_session.session_token}"
    )
    
    assert response.status_code == 200, f"查询会话信息应该成功，状态码：{response.status_code}"
    
    data = response.json()
    assert "session_id" in data
    assert "user_id" in data
    assert "username" in data
    assert data["username"] == "testuser"
    assert "email" in data
    assert data["email"] == "test@example.com"
    assert "created_at" in data
    assert "expires_at" in data
    assert "last_activity_at" in data


def test_get_nonexistent_session_info():
    """测试查询不存在的会话信息"""
    response = client.get(
        "/api/v1/sso/session/info?session_token=nonexistent_token"
    )
    
    assert response.status_code == 404, "不存在的会话应该返回404"


def test_update_activity_endpoint(test_session):
    """
    测试更新会话活动时间端点
    
    需求：2.1, 2.2 - 更新会话的最后活动时间
    """
    response = client.post(
        f"/api/v1/sso/session/update-activity?session_token={test_session.session_token}"
    )
    
    assert response.status_code == 200, f"更新活动时间应该成功，状态码：{response.status_code}"
    
    data = response.json()
    assert data["success"] is True
    assert "message" in data


def test_update_nonexistent_session_activity():
    """测试更新不存在的会话活动时间"""
    response = client.post(
        "/api/v1/sso/session/update-activity?session_token=nonexistent_token"
    )
    
    assert response.status_code == 404, "不存在的会话应该返回404"


def test_logout_endpoint(test_session):
    """
    测试登出端点
    
    需求：2.3 - 用户在任一应用登出时终止全局会话
    """
    response = client.post(
        f"/api/v1/sso/logout?session_token={test_session.session_token}"
    )
    
    assert response.status_code == 200, f"登出应该成功，状态码：{response.status_code}"
    
    data = response.json()
    assert data["success"] is True
    assert "message" in data
    
    # 验证会话已被删除
    validate_response = client.get(
        f"/api/v1/sso/session/validate?session_token={test_session.session_token}"
    )
    assert validate_response.status_code == 401, "登出后会话应该无效"


def test_logout_nonexistent_session():
    """测试登出不存在的会话"""
    response = client.post(
        "/api/v1/sso/logout?session_token=nonexistent_token"
    )
    
    assert response.status_code == 404, "不存在的会话应该返回404"


def test_logout_all_endpoint(test_user):
    """
    测试全局登出所有会话端点
    
    需求：2.3 - 用户在任一应用登出时终止所有应用的会话
    """
    # 创建多个会话
    db = TestingSessionLocal()
    try:
        session1 = create_sso_session(str(test_user.id), db)
        session2 = create_sso_session(str(test_user.id), db)
        session3 = create_sso_session(str(test_user.id), db)
    finally:
        db.close()
    
    # 使用第一个会话登出所有会话
    response = client.post(
        f"/api/v1/sso/logout-all?session_token={session1.session_token}"
    )
    
    assert response.status_code == 200, f"全局登出应该成功，状态码：{response.status_code}"
    
    data = response.json()
    assert data["success"] is True
    assert data["sessions_deleted"] == 3, "应该删除3个会话"
    
    # 验证所有会话都已失效
    for session in [session1, session2, session3]:
        validate_response = client.get(
            f"/api/v1/sso/session/validate?session_token={session.session_token}"
        )
        assert validate_response.status_code == 401, \
            f"会话{session.session_token}应该已失效"


def test_session_validation_updates_activity(test_session):
    """
    测试验证会话时自动更新活动时间
    
    需求：2.2 - 验证会话时应该更新最后活动时间
    """
    # 获取初始活动时间
    db = TestingSessionLocal()
    try:
        from shared.models.user import SSOSession
        session = db.query(SSOSession).filter(
            SSOSession.session_token == test_session.session_token
        ).first()
        original_activity = session.last_activity_at
    finally:
        db.close()
    
    # 等待一小段时间
    import time
    time.sleep(0.1)
    
    # 验证会话
    response = client.get(
        f"/api/v1/sso/session/validate?session_token={test_session.session_token}"
    )
    assert response.status_code == 200
    
    # 检查活动时间是否更新
    db = TestingSessionLocal()
    try:
        session = db.query(SSOSession).filter(
            SSOSession.session_token == test_session.session_token
        ).first()
        assert session.last_activity_at > original_activity, \
            "验证会话应该更新最后活动时间"
    finally:
        db.close()


def test_complete_sso_flow(test_user):
    """
    测试完整的SSO流程
    
    需求：2.1, 2.2, 2.3 - 完整的SSO会话生命周期
    """
    db = TestingSessionLocal()
    try:
        # 1. 创建会话（模拟用户登录）
        session = create_sso_session(str(test_user.id), db)
        assert session is not None
        
        # 2. 验证会话（模拟其他应用验证用户身份）
        validate_response = client.get(
            f"/api/v1/sso/session/validate?session_token={session.session_token}"
        )
        assert validate_response.status_code == 200
        assert validate_response.json()["valid"] is True
        
        # 3. 查询会话信息
        info_response = client.get(
            f"/api/v1/sso/session/info?session_token={session.session_token}"
        )
        assert info_response.status_code == 200
        assert info_response.json()["username"] == "testuser"
        
        # 4. 更新活动时间
        update_response = client.post(
            f"/api/v1/sso/session/update-activity?session_token={session.session_token}"
        )
        assert update_response.status_code == 200
        
        # 5. 登出（终止会话）
        logout_response = client.post(
            f"/api/v1/sso/logout?session_token={session.session_token}"
        )
        assert logout_response.status_code == 200
        
        # 6. 验证会话已失效
        final_validate = client.get(
            f"/api/v1/sso/session/validate?session_token={session.session_token}"
        )
        assert final_validate.status_code == 401
        
    finally:
        db.close()


def test_multiple_users_session_isolation():
    """测试多个用户的会话隔离"""
    db = TestingSessionLocal()
    try:
        # 创建两个用户
        user1 = User(
            username="user1",
            email="user1@example.com",
            password_hash=hash_password("Pass123!"),
            status="active"
        )
        user2 = User(
            username="user2",
            email="user2@example.com",
            password_hash=hash_password("Pass123!"),
            status="active"
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)
        
        # 为每个用户创建会话
        session1 = create_sso_session(str(user1.id), db)
        session2 = create_sso_session(str(user2.id), db)
        
        # 验证user1的会话
        response1 = client.get(
            f"/api/v1/sso/session/validate?session_token={session1.session_token}"
        )
        assert response1.status_code == 200
        assert response1.json()["user"]["username"] == "user1"
        
        # 验证user2的会话
        response2 = client.get(
            f"/api/v1/sso/session/validate?session_token={session2.session_token}"
        )
        assert response2.status_code == 200
        assert response2.json()["user"]["username"] == "user2"
        
        # 登出user1不应影响user2
        logout_response = client.post(
            f"/api/v1/sso/logout?session_token={session1.session_token}"
        )
        assert logout_response.status_code == 200
        
        # user1的会话应该失效
        validate1 = client.get(
            f"/api/v1/sso/session/validate?session_token={session1.session_token}"
        )
        assert validate1.status_code == 401
        
        # user2的会话应该仍然有效
        validate2 = client.get(
            f"/api/v1/sso/session/validate?session_token={session2.session_token}"
        )
        assert validate2.status_code == 200
        
    finally:
        db.close()
