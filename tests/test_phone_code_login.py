from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import services.auth.main as auth_main
from shared.models.user import Base, User


class FakeRedis:
    def __init__(self, phone: str, code: str):
        self.values = {f"sms_code:{phone}": code}

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)

    def issue(self, phone: str, code: str):
        self.values[f"sms_code:{phone}"] = code


def test_phone_code_login_auto_registers_then_reuses_user(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    phone = "+8613900000001"
    redis = FakeRedis(phone, "123456")

    monkeypatch.setattr(auth_main, "get_redis", lambda: redis)
    monkeypatch.setattr(
        auth_main,
        "create_sso_session",
        lambda _user_id, _db: SimpleNamespace(session_token="sso-token"),
    )
    monkeypatch.setattr(auth_main, "create_access_token", lambda _claims: "access-token")
    monkeypatch.setattr(auth_main, "create_refresh_token", lambda _claims: "refresh-token")

    first = asyncio.run(
        auth_main.login_with_phone_code(
            auth_main.PhoneCodeLoginRequest(phone=phone, code="123456"), db
        )
    )
    created = db.query(User).filter(User.phone == phone).one()

    assert first.is_new_user is True
    assert first.user["id"] == str(created.id)
    assert created.status == "active"
    assert created.password_hash is None
    assert created.password_changed is True
    assert f"sms_code:{phone}" not in redis.values

    redis.issue(phone, "654321")
    second = asyncio.run(
        auth_main.login_with_phone_code(
            auth_main.PhoneCodeLoginRequest(phone=phone, code="654321"), db
        )
    )

    assert second.is_new_user is False
    assert second.user["id"] == first.user["id"]
    assert db.query(User).filter(User.phone == phone).count() == 1
    db.close()
