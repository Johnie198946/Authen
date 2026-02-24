"""
SSO服务属性测试

使用Hypothesis进行基于属性的测试，验证SSO功能的通用属性。
每个属性测试至少运行100次迭代。
"""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Table, MetaData
from sqlalchemy.orm import sessionmaker, Session
from shared.models.user import Base, User, SSOSession
from shared.utils.crypto import hash_password
from shared.utils.sso_session import (
    create_sso_session,
    get_sso_session,
    validate_sso_session,
    delete_sso_session,
    delete_user_sso_sessions
)
from fastapi.testclient import TestClient
from shared.database import get_db
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sso.main import app as sso_app
from services.auth.main import app as auth_app


# 测试数据库配置
TEST_DATABASE_URL = "sqlite:///./test_sso_properties.db"
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
sso_app.dependency_overrides[get_db] = override_get_db
auth_app.dependency_overrides[get_db] = override_get_db

# 创建测试客户端
sso_client = TestClient(sso_app)
auth_client = TestClient(auth_app)


# Hypothesis配置
settings.register_profile("default", 
    max_examples=100,  # 每个属性测试至少100次迭代
    deadline=None,  # 禁用超时限制
    suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile("default")


# 测试数据生成器
@st.composite
def valid_usernames(draw):
    """生成有效的用户名"""
    return draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_-'),
        min_size=3,
        max_size=50
    ))


@st.composite
def valid_emails(draw):
    """生成有效的邮箱地址"""
    local = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='._-'),
        min_size=1,
        max_size=20
    ))
    domain = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-'),
        min_size=1,
        max_size=20
    ))
    tld = draw(st.sampled_from(['com', 'org', 'net', 'edu', 'io']))
    return f"{local}@{domain}.{tld}"


@st.composite
def valid_passwords(draw):
    """生成有效的密码（符合复杂度要求）"""
    return draw(st.text(
        alphabet=st.characters(
            whitelist_categories=('Lu', 'Ll', 'Nd'),
            whitelist_characters='!@#$%^&*()'
        ),
        min_size=8,
        max_size=32
    ))


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前设置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def create_test_user(username: str, email: str, password: str, db: Session) -> User:
    """创建测试用户"""
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        status="active"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============================================================================
# 属性 8：SSO全局会话创建
# ============================================================================

@given(
    username=valid_usernames(),
    email=valid_emails(),
    password=valid_passwords()
)
@settings(max_examples=100)
def test_property_8_sso_session_creation(username, email, password):
    """
    Feature: unified-auth-platform, Property 8: SSO全局会话创建
    
    **Validates: Requirements 2.1**
    
    对于任意客户端应用，当用户在该应用中成功登录时，
    系统应该创建一个全局SSO会话，且该会话可以被其他应用查询到。
    
    属性：
    1. 登录成功后必须创建SSO会话
    2. SSO会话必须有唯一的session_token
    3. SSO会话必须关联到正确的用户
    4. SSO会话必须有有效的过期时间（在未来）
    5. SSO会话可以通过session_token查询到
    """
    db = TestingSessionLocal()
    try:
        # 清理数据库以避免唯一约束冲突
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        
        # 创建用户
        user = create_test_user(username, email, password, db)
        
        # 用户登录
        response = auth_client.post(
            "/api/v1/auth/login",
            json={
                "identifier": email,
                "password": password
            }
        )
        
        # 验证登录成功
        assert response.status_code == 200, \
            f"登录应该成功，状态码：{response.status_code}"
        
        data = response.json()
        
        # 属性1：登录成功后必须创建SSO会话
        assert "sso_session_token" in data, \
            "登录响应必须包含SSO会话令牌"
        assert data["sso_session_token"] is not None, \
            "SSO会话令牌不能为空"
        
        session_token = data["sso_session_token"]
        
        # 属性2：SSO会话必须有唯一的session_token
        assert len(session_token) > 0, \
            "SSO会话令牌长度必须大于0"
        
        # 属性3：SSO会话必须关联到正确的用户
        session = db.query(SSOSession).filter(
            SSOSession.session_token == session_token
        ).first()
        
        assert session is not None, \
            "SSO会话必须在数据库中创建"
        assert str(session.user_id) == str(user.id), \
            "SSO会话必须关联到正确的用户"
        
        # 属性4：SSO会话必须有有效的过期时间（在未来）
        assert session.expires_at > datetime.utcnow(), \
            "SSO会话过期时间必须在未来"
        
        # 属性5：SSO会话可以通过session_token查询到
        validate_response = sso_client.get(
            f"/api/v1/sso/session/validate?session_token={session_token}"
        )
        
        assert validate_response.status_code == 200, \
            f"SSO会话验证应该成功，状态码：{validate_response.status_code}"
        
        validate_data = validate_response.json()
        assert validate_data["valid"] is True, \
            "SSO会话必须有效"
        assert validate_data["user"]["id"] == str(user.id), \
            "验证响应必须返回正确的用户ID"
        
    finally:
        # 清理数据
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        db.close()


# ============================================================================
# 属性 9：SSO自动认证
# ============================================================================

@given(
    username=valid_usernames(),
    email=valid_emails(),
    password=valid_passwords()
)
@settings(max_examples=100)
def test_property_9_sso_auto_authentication(username, email, password):
    """
    Feature: unified-auth-platform, Property 9: SSO自动认证
    
    **Validates: Requirements 2.2**
    
    对于任意两个客户端应用A和B，当用户在应用A登录后访问应用B时，
    应用B应该能够通过SSO会话自动完成认证，无需用户再次输入凭证。
    
    属性：
    1. 在应用A登录后创建的SSO会话可以在应用B中验证
    2. 应用B验证SSO会话时应该返回正确的用户信息
    3. 应用B不需要用户再次输入密码
    4. SSO会话在两个应用中返回相同的用户ID
    """
    db = TestingSessionLocal()
    try:
        # 清理数据库
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        
        # 创建用户
        user = create_test_user(username, email, password, db)
        
        # 模拟应用A：用户登录
        login_response = auth_client.post(
            "/api/v1/auth/login",
            json={
                "identifier": email,
                "password": password
            }
        )
        
        assert login_response.status_code == 200, \
            "应用A登录应该成功"
        
        session_token = login_response.json()["sso_session_token"]
        
        # 属性1：在应用A登录后创建的SSO会话可以在应用B中验证
        # 模拟应用B：验证SSO会话
        validate_response = sso_client.get(
            f"/api/v1/sso/session/validate?session_token={session_token}"
        )
        
        assert validate_response.status_code == 200, \
            "应用B应该能够验证SSO会话"
        
        validate_data = validate_response.json()
        
        # 属性2：应用B验证SSO会话时应该返回正确的用户信息
        assert validate_data["valid"] is True, \
            "SSO会话在应用B中应该有效"
        assert "user" in validate_data, \
            "验证响应必须包含用户信息"
        
        # 属性3：应用B不需要用户再次输入密码
        # （通过SSO会话令牌即可完成认证，无需密码）
        assert validate_data["user"]["username"] == username, \
            "应用B应该获取到正确的用户名"
        assert validate_data["user"]["email"] == email, \
            "应用B应该获取到正确的邮箱"
        
        # 属性4：SSO会话在两个应用中返回相同的用户ID
        app_a_user_id = login_response.json()["user"]["id"]
        app_b_user_id = validate_data["user"]["id"]
        
        assert app_a_user_id == app_b_user_id, \
            "SSO会话在两个应用中必须返回相同的用户ID"
        
    finally:
        # 清理数据
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        db.close()


# ============================================================================
# 属性 10：SSO全局登出
# ============================================================================

@given(
    username=valid_usernames(),
    email=valid_emails(),
    password=valid_passwords(),
    num_sessions=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100)
def test_property_10_sso_global_logout(username, email, password, num_sessions):
    """
    Feature: unified-auth-platform, Property 10: SSO全局登出
    
    **Validates: Requirements 2.3**
    
    对于任意客户端应用，当用户在该应用中登出时，
    系统应该终止全局SSO会话，且所有其他应用的会话也应该失效。
    
    属性：
    1. 用户可以创建多个SSO会话
    2. 全局登出应该删除用户的所有SSO会话
    3. 全局登出后，所有会话令牌都应该失效
    4. 全局登出后，验证任何会话令牌都应该失败
    """
    db = TestingSessionLocal()
    try:
        # 清理数据库
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        
        # 创建用户
        user = create_test_user(username, email, password, db)
        
        # 属性1：用户可以创建多个SSO会话
        # 模拟用户在多个应用中登录
        session_tokens = []
        for i in range(num_sessions):
            login_response = auth_client.post(
                "/api/v1/auth/login",
                json={
                    "identifier": email,
                    "password": password
                }
            )
            
            assert login_response.status_code == 200, \
                f"第{i+1}次登录应该成功"
            
            session_token = login_response.json()["sso_session_token"]
            session_tokens.append(session_token)
        
        # 验证所有会话都有效
        for token in session_tokens:
            validate_response = sso_client.get(
                f"/api/v1/sso/session/validate?session_token={token}"
            )
            assert validate_response.status_code == 200, \
                "登出前所有会话都应该有效"
        
        # 属性2：全局登出应该删除用户的所有SSO会话
        # 使用第一个会话令牌执行全局登出
        logout_response = sso_client.post(
            f"/api/v1/sso/logout-all?session_token={session_tokens[0]}"
        )
        
        assert logout_response.status_code == 200, \
            "全局登出应该成功"
        
        logout_data = logout_response.json()
        
        # 属性3：全局登出后，所有会话令牌都应该失效
        assert logout_data["sessions_deleted"] == num_sessions, \
            f"应该删除{num_sessions}个会话"
        
        # 属性4：全局登出后，验证任何会话令牌都应该失败
        for token in session_tokens:
            validate_response = sso_client.get(
                f"/api/v1/sso/session/validate?session_token={token}"
            )
            assert validate_response.status_code == 401, \
                "全局登出后所有会话都应该失效"
        
        # 验证数据库中没有该用户的活跃会话
        remaining_sessions = db.query(SSOSession).filter(
            SSOSession.user_id == user.id
        ).all()
        
        assert len(remaining_sessions) == 0, \
            "全局登出后数据库中不应该有该用户的会话"
        
    finally:
        # 清理数据
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        db.close()


# ============================================================================
# 属性 11：SSO身份验证响应
# ============================================================================

@given(
    username=valid_usernames(),
    email=valid_emails(),
    password=valid_passwords()
)
@settings(max_examples=100)
def test_property_11_sso_identity_verification_response(username, email, password):
    """
    Feature: unified-auth-platform, Property 11: SSO身份验证响应
    
    **Validates: Requirements 2.4**
    
    对于任意有效的SSO会话，当客户端应用请求验证用户身份时，
    系统应该返回用户的认证状态和基本信息（用户ID、用户名、邮箱）。
    
    属性：
    1. 验证有效的SSO会话应该返回成功状态
    2. 响应必须包含用户的基本信息
    3. 用户ID必须与创建会话的用户一致
    4. 用户名必须与创建会话的用户一致
    5. 邮箱必须与创建会话的用户一致
    6. 响应必须包含会话的时间信息
    """
    db = TestingSessionLocal()
    try:
        # 清理数据库
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        
        # 创建用户
        user = create_test_user(username, email, password, db)
        
        # 用户登录创建SSO会话
        login_response = auth_client.post(
            "/api/v1/auth/login",
            json={
                "identifier": email,
                "password": password
            }
        )
        
        assert login_response.status_code == 200, \
            "登录应该成功"
        
        session_token = login_response.json()["sso_session_token"]
        
        # 属性1：验证有效的SSO会话应该返回成功状态
        validate_response = sso_client.get(
            f"/api/v1/sso/session/validate?session_token={session_token}"
        )
        
        assert validate_response.status_code == 200, \
            "验证有效的SSO会话应该返回200状态码"
        
        validate_data = validate_response.json()
        
        assert validate_data["valid"] is True, \
            "验证响应必须指示会话有效"
        
        # 属性2：响应必须包含用户的基本信息
        assert "user" in validate_data, \
            "响应必须包含user字段"
        
        user_info = validate_data["user"]
        
        assert "id" in user_info, \
            "用户信息必须包含id字段"
        assert "username" in user_info, \
            "用户信息必须包含username字段"
        assert "email" in user_info, \
            "用户信息必须包含email字段"
        
        # 属性3：用户ID必须与创建会话的用户一致
        assert user_info["id"] == str(user.id), \
            "返回的用户ID必须与创建会话的用户一致"
        
        # 属性4：用户名必须与创建会话的用户一致
        assert user_info["username"] == username, \
            "返回的用户名必须与创建会话的用户一致"
        
        # 属性5：邮箱必须与创建会话的用户一致
        assert user_info["email"] == email, \
            "返回的邮箱必须与创建会话的用户一致"
        
        # 属性6：响应必须包含会话的时间信息
        assert "session" in validate_data, \
            "响应必须包含session字段"
        
        session_info = validate_data["session"]
        
        assert "created_at" in session_info, \
            "会话信息必须包含created_at字段"
        assert "expires_at" in session_info, \
            "会话信息必须包含expires_at字段"
        assert "last_activity_at" in session_info, \
            "会话信息必须包含last_activity_at字段"
        
        # 验证时间格式有效
        from datetime import datetime
        try:
            datetime.fromisoformat(session_info["created_at"])
            datetime.fromisoformat(session_info["expires_at"])
            datetime.fromisoformat(session_info["last_activity_at"])
        except ValueError:
            pytest.fail("会话时间信息必须是有效的ISO格式")
        
    finally:
        # 清理数据
        db.query(SSOSession).delete()
        db.query(User).delete()
        db.commit()
        db.close()


# ============================================================================
# 额外的边界测试
# ============================================================================

def test_sso_session_isolation_between_users():
    """
    测试不同用户的SSO会话隔离
    
    验证一个用户的SSO会话不能被另一个用户访问或影响
    """
    db = TestingSessionLocal()
    try:
        # 创建两个用户
        user1 = create_test_user("user1", "user1@example.com", "Pass123!", db)
        user2 = create_test_user("user2", "user2@example.com", "Pass456!", db)
        
        # 两个用户分别登录
        login1 = auth_client.post(
            "/api/v1/auth/login",
            json={"identifier": "user1@example.com", "password": "Pass123!"}
        )
        login2 = auth_client.post(
            "/api/v1/auth/login",
            json={"identifier": "user2@example.com", "password": "Pass456!"}
        )
        
        assert login1.status_code == 200
        assert login2.status_code == 200
        
        token1 = login1.json()["sso_session_token"]
        token2 = login2.json()["sso_session_token"]
        
        # 验证会话返回正确的用户
        validate1 = sso_client.get(f"/api/v1/sso/session/validate?session_token={token1}")
        validate2 = sso_client.get(f"/api/v1/sso/session/validate?session_token={token2}")
        
        assert validate1.json()["user"]["id"] == str(user1.id)
        assert validate2.json()["user"]["id"] == str(user2.id)
        
        # user1登出不应影响user2
        logout1 = sso_client.post(f"/api/v1/sso/logout?session_token={token1}")
        assert logout1.status_code == 200
        
        # user1的会话应该失效
        validate1_after = sso_client.get(f"/api/v1/sso/session/validate?session_token={token1}")
        assert validate1_after.status_code == 401
        
        # user2的会话应该仍然有效
        validate2_after = sso_client.get(f"/api/v1/sso/session/validate?session_token={token2}")
        assert validate2_after.status_code == 200
        
    finally:
        db.close()


def test_sso_session_expiry():
    """
    测试SSO会话过期处理
    
    验证过期的会话不能被验证
    """
    db = TestingSessionLocal()
    try:
        # 创建用户
        user = create_test_user("testuser", "test@example.com", "Pass123!", db)
        
        # 创建会话
        session = create_sso_session(str(user.id), db)
        
        # 手动设置会话为过期
        session.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
        
        # 验证过期会话应该失败
        validate_response = sso_client.get(
            f"/api/v1/sso/session/validate?session_token={session.session_token}"
        )
        
        assert validate_response.status_code == 401, \
            "过期的会话应该返回401"
        
    finally:
        db.close()


def test_sso_session_with_invalid_token():
    """
    测试使用无效令牌验证SSO会话
    
    验证系统正确处理无效的会话令牌
    """
    # 使用不存在的令牌
    validate_response = sso_client.get(
        "/api/v1/sso/session/validate?session_token=invalid_token_12345"
    )
    
    assert validate_response.status_code == 401, \
        "无效的会话令牌应该返回401"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
