"""
邮箱验证码注册测试

验证需求：4.1, 4.2, 4.3, 4.4, 4.5, 4.6

使用 mock DB session 避免 SQLite 不支持 PostgreSQL UUID 类型的问题。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from datetime import datetime
import uuid

from shared.database import get_db
from shared.redis_client import get_redis
from shared.models.user import User
from services.auth.main import app


# ---------------------------------------------------------------------------
# In-memory user store
# ---------------------------------------------------------------------------

class InMemoryUserStore:
    def __init__(self):
        self.users = []

    def reset(self):
        self.users.clear()

    def add(self, user_obj):
        self.users.append(user_obj)

    def find_by_email(self, email):
        for u in self.users:
            if u.email == email:
                return u
        return None

    def find_by_username(self, username):
        for u in self.users:
            if u.username == username:
                return u
        return None


store = InMemoryUserStore()


class FakeQuery:
    def __init__(self, store_ref):
        self._store = store_ref
        self._filters = {}

    def filter(self, *args):
        for arg in args:
            try:
                col_name = arg.left.key
                value = arg.right.effective_value
                self._filters[col_name] = value
            except Exception:
                pass
        return self

    def first(self):
        email = self._filters.get("email")
        if email:
            return self._store.find_by_email(email)
        username = self._filters.get("username")
        if username:
            return self._store.find_by_username(username)
        return None


class FakeSession:
    def __init__(self, store_ref):
        self._store = store_ref
        self._pending = None

    def query(self, model):
        return FakeQuery(self._store)

    def add(self, obj):
        self._pending = obj

    def commit(self):
        if self._pending:
            self._store.add(self._pending)

    def refresh(self, obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if not getattr(obj, "created_at", None):
            obj.created_at = datetime.utcnow()
        if not getattr(obj, "updated_at", None):
            obj.updated_at = datetime.utcnow()

    def close(self):
        self._pending = None


def override_get_db():
    session = FakeSession(store)
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup():
    """每个测试前清理 store 和 Redis"""
    store.reset()
    redis = get_redis()
    redis.flushdb()
    yield
    store.reset()
    redis.flushdb()


def _store_code(email: str, code: str = "123456"):
    redis = get_redis()
    redis.setex(f"email_code:{email}", 300, code)


# ==================== Tests ====================


def test_email_registration_success():
    """注册成功：验证码匹配，用户状态为 active，验证码被删除"""
    email = "test1@example.com"
    code = "654321"
    _store_code(email, code)

    response = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": email,
            "password": "Password123!",
            "username": "testuser1",
            "verification_code": code,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "注册成功"
    assert "user_id" in data

    # 用户状态应为 active
    user = store.find_by_email(email)
    assert user is not None
    assert user.status == "active"
    assert user.username == "testuser1"
    assert user.password_hash != "Password123!"

    # 验证码应被删除
    redis = get_redis()
    assert redis.get(f"email_code:{email}") is None


def test_registration_with_multiple_examples():
    """使用多个具体示例测试注册"""
    cases = [
        ("a@example.com", "Password123!", "userA", "111111"),
        ("b@example.com", "SecurePass456@", "userB", "222222"),
        ("c@example.com", "MyP@ssw0rd", "userC", "333333"),
    ]
    for email, password, username, code in cases:
        _store_code(email, code)
        resp = client.post(
            "/api/v1/auth/register/email",
            json={
                "email": email,
                "password": password,
                "username": username,
                "verification_code": code,
            },
        )
        assert resp.status_code == 200, f"注册应该成功: {email}"
        user = store.find_by_email(email)
        assert user is not None
        assert user.status == "active"


def test_invalid_verification_code_returns_400():
    """验证码无效或已过期返回 400"""
    # 没有存储验证码
    resp = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "nocode@example.com",
            "password": "Password123!",
            "username": "nocodeuser",
            "verification_code": "999999",
        },
    )
    assert resp.status_code == 400
    assert "验证码无效或已过期" in resp.json()["detail"]


def test_wrong_verification_code_returns_400():
    """验证码不匹配返回 400"""
    email = "wrong@example.com"
    _store_code(email, "123456")

    resp = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": email,
            "password": "Password123!",
            "username": "wrongcodeuser",
            "verification_code": "654321",
        },
    )
    assert resp.status_code == 400
    assert "验证码无效或已过期" in resp.json()["detail"]


def test_duplicate_email_returns_409():
    """邮箱已注册返回 409"""
    email = "dup@example.com"
    _store_code(email, "111111")

    resp1 = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": email,
            "password": "Password123!",
            "username": "dupuser1",
            "verification_code": "111111",
        },
    )
    assert resp1.status_code == 200

    # 第二次注册需要新验证码
    _store_code(email, "222222")
    resp2 = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": email,
            "password": "Password123!",
            "username": "dupuser2",
            "verification_code": "222222",
        },
    )
    assert resp2.status_code == 409
    assert "邮箱已被注册" in resp2.json()["detail"]


def test_duplicate_username_returns_409():
    """用户名已使用返回 409"""
    _store_code("u1@example.com", "111111")
    resp1 = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "u1@example.com",
            "password": "Password123!",
            "username": "sameuser",
            "verification_code": "111111",
        },
    )
    assert resp1.status_code == 200

    _store_code("u2@example.com", "222222")
    resp2 = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": "u2@example.com",
            "password": "Password123!",
            "username": "sameuser",
            "verification_code": "222222",
        },
    )
    assert resp2.status_code == 409
    assert "用户名已被使用" in resp2.json()["detail"]


def test_invalid_email_format_returns_422():
    """无效邮箱格式返回 422（Pydantic EmailStr 校验）"""
    for bad_email in ["notanemail", "@example.com", "user@", ""]:
        resp = client.post(
            "/api/v1/auth/register/email",
            json={
                "email": bad_email,
                "password": "Password123!",
                "username": "testuser",
                "verification_code": "123456",
            },
        )
        assert resp.status_code == 422, f"无效邮箱应返回 422: {bad_email}"


def test_weak_password_returns_400():
    """密码强度不足返回 400"""
    for weak_pw in ["123", "password", "12345678", "abcdefgh"]:
        email = "weakpw@example.com"
        _store_code(email, "123456")
        resp = client.post(
            "/api/v1/auth/register/email",
            json={
                "email": email,
                "password": weak_pw,
                "username": "testuser",
                "verification_code": "123456",
            },
        )
        assert resp.status_code == 400, f"弱密码应被拒绝: {weak_pw}"


def test_verification_code_deleted_after_registration():
    """注册成功后验证码被删除（单次使用）"""
    email = "onetime@example.com"
    _store_code(email, "123456")

    resp = client.post(
        "/api/v1/auth/register/email",
        json={
            "email": email,
            "password": "Password123!",
            "username": "onetimeuser",
            "verification_code": "123456",
        },
    )
    assert resp.status_code == 200

    redis = get_redis()
    assert redis.get(f"email_code:{email}") is None
