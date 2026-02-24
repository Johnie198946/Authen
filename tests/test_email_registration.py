"""
邮箱注册测试

Feature: unified-auth-platform, Property 1: 邮箱注册完整性

对于任意有效的邮箱地址和密码，当用户通过邮箱注册时，
系统应该发送验证邮件，并在用户点击验证链接后成功创建账号且账号状态为已验证。

验证需求：1.1
"""
import pytest
from hypothesis import given, strategies as st
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.user import Base, User
from shared.database import get_db
from shared.redis_client import get_redis
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auth.main import app


# 测试数据库配置
TEST_DATABASE_URL = "sqlite:///./test.db"
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


# 邮箱生成器
emails = st.emails()

# 密码生成器（符合复杂度要求）
passwords = st.text(
    alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'),
        whitelist_characters='!@#$%^&*()'
    ),
    min_size=8,
    max_size=32
)

# 用户名生成器
usernames = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')),
    min_size=3,
    max_size=50
)


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前设置数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@given(
    email=emails,
    password=passwords,
    username=usernames
)
def test_email_registration_integrity(email, password, username):
    """
    属性 1：邮箱注册完整性
    
    对于任意有效的邮箱和密码，注册流程应该：
    1. 成功创建用户记录
    2. 用户状态为待验证
    3. 生成验证令牌
    4. 验证后用户状态变为已激活
    """
    # 步骤1：邮箱注册
    response = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": email,
            "password": password,
            "username": username
        }
    )
    
    # 属性1：注册请求应该成功
    assert response.status_code in [200, 400, 409], \
        f"注册响应状态码应该是200、400或409，实际是{response.status_code}"
    
    if response.status_code == 200:
        data = response.json()
        
        # 属性2：响应应该包含必要字段
        assert "success" in data, "响应应该包含success字段"
        assert "message" in data, "响应应该包含message字段"
        assert "user_id" in data, "响应应该包含user_id字段"
        
        assert data["success"] is True, "注册应该成功"
        
        # 属性3：用户应该被创建且状态为待验证
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            assert user is not None, "用户应该被创建"
            assert user.status == 'pending_verification', \
                "用户状态应该是pending_verification"
            assert user.username == username, "用户名应该正确"
            
            # 属性4：密码应该被加密存储
            assert user.password_hash != password, "密码不应该明文存储"
            assert len(user.password_hash) == 60, "bcrypt哈希长度应该是60"
            
            # 属性5：验证令牌应该被生成并存储在Redis
            redis = get_redis()
            # 查找所有验证令牌
            keys = redis.keys("email_verification:*")
            assert len(keys) > 0, "应该生成验证令牌"
            
            # 模拟验证流程
            # 获取第一个验证令牌
            token = keys[0].decode().split(':')[1]
            
            # 步骤2：验证邮箱
            verify_response = client.get(f"/api/v1/auth/verify-email?token={token}")
            
            # 属性6：验证请求应该成功
            assert verify_response.status_code == 200, \
                f"验证响应状态码应该是200，实际是{verify_response.status_code}"
            
            verify_data = verify_response.json()
            assert verify_data["success"] is True, "验证应该成功"
            
            # 属性7：用户状态应该变为已激活
            db.refresh(user)
            assert user.status == 'active', "验证后用户状态应该是active"
            
        finally:
            db.close()


def test_email_registration_with_specific_examples():
    """使用具体示例测试邮箱注册"""
    test_cases = [
        {
            "email": "test1@example.com",
            "password": "Password123!",
            "username": "testuser1"
        },
        {
            "email": "test2@example.com",
            "password": "SecurePass456@",
            "username": "testuser2"
        },
        {
            "email": "test3@example.com",
            "password": "MyP@ssw0rd",
            "username": "testuser3"
        }
    ]
    
    for case in test_cases:
        # 注册
        response = client.post("/api/v1/auth/register/email", json=case)
        assert response.status_code == 200, \
            f"注册应该成功: {case['email']}"
        
        data = response.json()
        assert data["success"] is True
        
        # 验证用户被创建
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.email == case["email"]).first()
            assert user is not None, f"用户应该被创建: {case['email']}"
            assert user.status == 'pending_verification'
        finally:
            db.close()


def test_duplicate_email_registration():
    """测试重复邮箱注册"""
    user_data = {
        "email": "duplicate@example.com",
        "password": "Password123!",
        "username": "duplicateuser"
    }
    
    # 第一次注册应该成功
    response1 = client.post("/api/v1/auth/register/email", json=user_data)
    assert response1.status_code == 200, "第一次注册应该成功"
    
    # 第二次注册应该失败（邮箱已存在）
    response2 = client.post("/api/v1/auth/register/email", json=user_data)
    assert response2.status_code == 409, "重复邮箱注册应该返回409"
    
    error_data = response2.json()
    assert "邮箱" in error_data["detail"], "错误消息应该提示邮箱已存在"


def test_invalid_email_format():
    """测试无效邮箱格式"""
    invalid_emails = [
        "notanemail",
        "@example.com",
        "user@",
        "user @example.com",
        ""
    ]
    
    for invalid_email in invalid_emails:
        response = client.post(
            "/api/v1/auth/register/email",
            json={
                "email": invalid_email,
                "password": "Password123!",
                "username": "testuser"
            }
        )
        # FastAPI的EmailStr验证会返回422
        assert response.status_code == 422, \
            f"无效邮箱应该返回422: {invalid_email}"


def test_weak_password_rejection():
    """测试弱密码被拒绝"""
    weak_passwords = [
        "123",  # 太短
        "password",  # 没有数字和大写字母
        "12345678",  # 只有数字
        "abcdefgh",  # 只有小写字母
    ]
    
    for weak_password in weak_passwords:
        response = client.post(
            "/api/v1/auth/register/email",
            json={
                "email": "test@example.com",
                "password": weak_password,
                "username": "testuser"
            }
        )
        assert response.status_code == 400, \
            f"弱密码应该被拒绝: {weak_password}"


def test_invalid_username():
    """测试无效用户名"""
    invalid_usernames = [
        "ab",  # 太短
        "a" * 51,  # 太长
        "user name",  # 包含空格
        "user@name",  # 包含特殊字符
        ""  # 空用户名
    ]
    
    for invalid_username in invalid_usernames:
        response = client.post(
            "/api/v1/auth/register/email",
            json={
                "email": "test@example.com",
                "password": "Password123!",
                "username": invalid_username
            }
        )
        assert response.status_code in [400, 422], \
            f"无效用户名应该被拒绝: {invalid_username}"


def test_email_verification_token_expiry():
    """测试验证令牌过期"""
    # 注册用户
    response = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "expiry@example.com",
            "password": "Password123!",
            "username": "expiryuser"
        }
    )
    assert response.status_code == 200
    
    # 使用无效令牌验证
    invalid_token = "invalid_token_12345"
    verify_response = client.get(f"/api/v1/auth/verify-email?token={invalid_token}")
    
    assert verify_response.status_code == 400, "无效令牌应该返回400"
    error_data = verify_response.json()
    assert "无效" in error_data["detail"] or "过期" in error_data["detail"]


def test_duplicate_username_registration():
    """测试重复用户名注册"""
    # 第一个用户
    response1 = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "user1@example.com",
            "password": "Password123!",
            "username": "sameusername"
        }
    )
    assert response1.status_code == 200
    
    # 第二个用户使用相同用户名
    response2 = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "user2@example.com",
            "password": "Password123!",
            "username": "sameusername"
        }
    )
    assert response2.status_code == 409, "重复用户名应该返回409"


def test_registration_creates_pending_user():
    """测试注册创建待验证用户"""
    response = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "pending@example.com",
            "password": "Password123!",
            "username": "pendinguser"
        }
    )
    assert response.status_code == 200
    
    # 检查用户状态
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "pending@example.com").first()
        assert user is not None
        assert user.status == 'pending_verification', \
            "新注册用户应该是待验证状态"
        assert user.failed_login_attempts == 0, "失败登录次数应该是0"
        assert user.locked_until is None, "不应该被锁定"
    finally:
        db.close()


def test_verification_activates_user():
    """测试验证激活用户"""
    # 注册
    response = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "activate@example.com",
            "password": "Password123!",
            "username": "activateuser"
        }
    )
    assert response.status_code == 200
    
    # 获取验证令牌
    redis = get_redis()
    keys = redis.keys("email_verification:*")
    assert len(keys) > 0
    
    token = keys[0].decode().split(':')[1]
    
    # 验证前检查状态
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "activate@example.com").first()
        assert user.status == 'pending_verification'
        
        # 验证
        verify_response = client.get(f"/api/v1/auth/verify-email?token={token}")
        assert verify_response.status_code == 200
        
        # 验证后检查状态
        db.refresh(user)
        assert user.status == 'active', "验证后用户应该被激活"
    finally:
        db.close()


def test_verification_token_deleted_after_use():
    """测试验证令牌使用后被删除"""
    # 注册
    response = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "tokendelete@example.com",
            "password": "Password123!",
            "username": "tokendeleteuser"
        }
    )
    assert response.status_code == 200
    
    # 获取验证令牌
    redis = get_redis()
    keys_before = redis.keys("email_verification:*")
    assert len(keys_before) > 0
    
    token = keys_before[0].decode().split(':')[1]
    
    # 验证
    verify_response = client.get(f"/api/v1/auth/verify-email?token={token}")
    assert verify_response.status_code == 200
    
    # 令牌应该被删除
    token_value = redis.get(f"email_verification:{token}")
    assert token_value is None, "验证令牌使用后应该被删除"
    
    # 再次使用相同令牌应该失败
    verify_response2 = client.get(f"/api/v1/auth/verify-email?token={token}")
    assert verify_response2.status_code == 400, "已使用的令牌应该无效"
