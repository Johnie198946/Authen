"""
账号锁定机制测试

Feature: unified-auth-platform, Property 6: 账号锁定机制

对于任意用户账号，当连续输入错误密码5次后，账号应该被锁定15分钟，
在锁定期间任何登录尝试都应该被拒绝。

验证需求：1.6
"""
import pytest
import time
from hypothesis import given, strategies as st
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.models.user import Base, User
from shared.utils.crypto import hash_password
from shared.database import get_db
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.auth.main import app

TEST_DATABASE_URL = "sqlite:///./test_lockout.db"
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

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def create_test_user(email, password):
    db = TestingSessionLocal()
    try:
        user = User(
            username="testuser",
            email=email,
            password_hash=hash_password(password),
            status='active'
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

def test_account_lockout_after_five_failures():
    """测试5次失败后账号锁定"""
    email = "lockout@example.com"
    correct_password = "Password123!"
    create_test_user(email, correct_password)
    
    # 尝试5次错误密码
    for i in range(5):
        response = client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": "WrongPassword123!"
        })
        if i < 4:
            assert response.status_code == 401, f"第{i+1}次失败应该返回401"
        else:
            assert response.status_code == 403, "第5次失败应该锁定账号并返回403"
    
    # 验证账号被锁定
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user.failed_login_attempts == 5
        assert user.locked_until is not None
        assert user.status == 'locked'
    finally:
        db.close()

def test_locked_account_rejects_login():
    """测试锁定期间拒绝登录"""
    email = "locked@example.com"
    correct_password = "Password123!"
    create_test_user(email, correct_password)
    
    # 触发锁定
    for _ in range(5):
        client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": "WrongPassword!"
        })
    
    # 使用正确密码也应该被拒绝
    response = client.post("/api/v1/auth/login", json={
        "identifier": email,
        "password": correct_password
    })
    assert response.status_code == 403
    assert "锁定" in response.json()["detail"]

def test_successful_login_resets_failure_count():
    """测试成功登录重置失败计数"""
    email = "reset@example.com"
    correct_password = "Password123!"
    create_test_user(email, correct_password)
    
    # 尝试2次错误密码
    for _ in range(2):
        client.post("/api/v1/auth/login", json={
            "identifier": email,
            "password": "WrongPassword!"
        })
    
    # 成功登录
    response = client.post("/api/v1/auth/login", json={
        "identifier": email,
        "password": correct_password
    })
    assert response.status_code == 200
    
    # 验证失败计数被重置
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
    finally:
        db.close()

def test_remaining_attempts_message():
    """测试剩余尝试次数提示"""
    email = "attempts@example.com"
    correct_password = "Password123!"
    create_test_user(email, correct_password)
    
    # 第一次失败
    response = client.post("/api/v1/auth/login", json={
        "identifier": email,
        "password": "WrongPassword!"
    })
    assert response.status_code == 401
    assert "4" in response.json()["detail"]  # 剩余4次
