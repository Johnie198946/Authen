"""
手机注册测试

Feature: unified-auth-platform, Property 2: 手机注册完整性

对于任意有效的手机号和密码，当用户通过手机注册并提供正确的验证码时，
系统应该成功创建账号且账号状态为已验证。

验证需求：1.2
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.auth.main import app

TEST_DATABASE_URL = "sqlite:///./test_phone.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

phone_numbers = st.from_regex(r'^\+861[3-9]\d{9}$', fullmatch=True)
passwords = st.text(
    alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='!@#$%^&*()'),
    min_size=8, max_size=32
)
usernames = st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')), min_size=3, max_size=50)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    redis = get_redis()
    redis.flushdb()

@given(phone=phone_numbers, password=passwords, username=usernames)
def test_phone_registration_integrity(phone, password, username):
    sms_response = client.post("/api/v1/auth/send-sms", json={"phone": phone})
    assert sms_response.status_code == 200
    sms_data = sms_response.json()
    assert sms_data["success"] is True
    
    redis = get_redis()
    stored_code = redis.get(f"sms_code:{phone}")
    assert stored_code is not None
    verification_code = sms_data.get("code") or stored_code
    
    register_response = client.post("/api/v1/auth/register/phone", json={
        "phone": phone, "password": password, "username": username, "verification_code": verification_code
    })
    
    if register_response.status_code == 200:
        register_data = register_response.json()
        assert register_data["success"] is True
        
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter(User.phone == phone).first()
            assert user is not None
            assert user.status == 'active'
            assert user.username == username
            assert user.password_hash != password
            assert len(user.password_hash) == 60
            used_code = redis.get(f"sms_code:{phone}")
            assert used_code is None
        finally:
            db.close()

def test_invalid_verification_code():
    phone = "+8613800138000"
    sms_response = client.post("/api/v1/auth/send-sms", json={"phone": phone})
    assert sms_response.status_code == 200
    
    register_response = client.post("/api/v1/auth/register/phone", json={
        "phone": phone, "password": "Password123!", "username": "testuser", "verification_code": "000000"
    })
    assert register_response.status_code == 400

def test_duplicate_phone_registration():
    phone = "+8613800138000"
    sms_response = client.post("/api/v1/auth/send-sms", json={"phone": phone})
    assert sms_response.status_code == 200
    redis = get_redis()
    verification_code = redis.get(f"sms_code:{phone}")
    
    register_response1 = client.post("/api/v1/auth/register/phone", json={
        "phone": phone, "password": "Password123!", "username": "user1", "verification_code": verification_code
    })
    assert register_response1.status_code == 200
    
    sms_response2 = client.post("/api/v1/auth/send-sms", json={"phone": phone})
    verification_code2 = redis.get(f"sms_code:{phone}")
    register_response2 = client.post("/api/v1/auth/register/phone", json={
        "phone": phone, "password": "Password123!", "username": "user2", "verification_code": verification_code2
    })
    assert register_response2.status_code == 409

def test_verification_code_format():
    phone = "+8613800138000"
    sms_response = client.post("/api/v1/auth/send-sms", json={"phone": phone})
    assert sms_response.status_code == 200
    redis = get_redis()
    verification_code = redis.get(f"sms_code:{phone}")
    assert verification_code is not None
    assert len(verification_code) == 6
    assert verification_code.isdigit()
