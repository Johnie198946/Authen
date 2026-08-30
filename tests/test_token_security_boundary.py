import asyncio
import inspect
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import jwt

from shared.config import settings
from shared.utils.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    human_principal_claims,
)


def _human_data():
    return {"sub": "user-1", **human_principal_claims("pwd")}


def test_access_and_refresh_tokens_have_non_interchangeable_registered_claims():
    access_token = create_access_token(_human_data())
    refresh_token = create_refresh_token(_human_data())

    access = jwt.get_unverified_claims(access_token)
    refresh = jwt.get_unverified_claims(refresh_token)

    assert access["token_use"] == "access"
    assert access["aud"] == settings.JWT_ACCESS_AUDIENCE
    assert refresh["token_use"] == "refresh"
    assert refresh["aud"] == settings.JWT_REFRESH_AUDIENCE
    assert access["jti"] != refresh["jti"]

    assert decode_token(
        access_token,
        audience=settings.JWT_ACCESS_AUDIENCE,
        token_use="access",
    )
    assert decode_token(
        refresh_token,
        audience=settings.JWT_REFRESH_AUDIENCE,
        token_use="refresh",
    )
    assert decode_token(
        refresh_token,
        audience=settings.JWT_ACCESS_AUDIENCE,
        token_use="access",
    ) is None
    assert decode_token(
        access_token,
        audience=settings.JWT_REFRESH_AUDIENCE,
        token_use="refresh",
    ) is None


def test_access_token_is_rejected_by_refresh_endpoint():
    from services.auth.main import RefreshTokenRequest, refresh_token

    request = RefreshTokenRequest(refresh_token=create_access_token(_human_data()))
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(refresh_token(request))
    assert excinfo.value.status_code == 401


class _FakeRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = value

    def getdel(self, key):
        return self.values.pop(key, None)


class _FakeQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *_args):
        return self

    def first(self):
        return self.user


class _FakeDB:
    def __init__(self, user=None):
        self.user = user

    def query(self, *_args):
        return _FakeQuery(self.user)


def test_sso_authorize_uses_authenticated_session_not_query_user(monkeypatch):
    import services.sso.main as sso

    assert "user_id" not in inspect.signature(sso.authorize).parameters
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        settings,
        "SSO_CLIENTS_JSON",
        json.dumps({
            "client-1": {
                "client_secret": "secret-1",
                "redirect_uris": ["https://client.example/callback"],
            }
        }),
    )
    monkeypatch.setattr(sso, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(
        sso,
        "validate_sso_session",
        lambda token, db: (
            True,
            "",
            SimpleNamespace(user_id="session-user"),
        ),
    )

    result = asyncio.run(sso.authorize(
        client_id="client-1",
        redirect_uri="https://client.example/callback",
        response_type="code",
        scope="openid",
        state="state-1",
        session_token="session-token",
        db=_FakeDB(),
    ))
    stored = json.loads(fake_redis.values[f"auth_code:{result['authorization_code']}"])
    assert stored["user_id"] == "session-user"


def test_sso_token_requires_client_secret_and_consumes_code_once(monkeypatch):
    import services.sso.main as sso

    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        settings,
        "SSO_CLIENTS_JSON",
        json.dumps({
            "client-1": {
                "client_secret": "secret-1",
                "redirect_uris": ["https://client.example/callback"],
            }
        }),
    )
    monkeypatch.setattr(sso, "get_redis", lambda: fake_redis)
    fake_redis.values["auth_code:code-1"] = json.dumps({
        "client_id": "client-1",
        "redirect_uri": "https://client.example/callback",
        "user_id": "user-1",
    })
    bad = sso.TokenRequest(
        grant_type="authorization_code",
        code="code-1",
        client_id="client-1",
        client_secret="wrong",
        redirect_uri="https://client.example/callback",
    )
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(sso.token(bad, db=_FakeDB()))
    assert excinfo.value.status_code == 401
    assert "auth_code:code-1" in fake_redis.values

    user = SimpleNamespace(id="user-1", username="user", email="u@example.com")
    good = bad.model_copy(update={"client_secret": "secret-1"})
    response = asyncio.run(sso.token(good, db=_FakeDB(user)))
    assert jwt.get_unverified_claims(response.access_token)["token_use"] == "access"
    with pytest.raises(HTTPException) as replay:
        asyncio.run(sso.token(good, db=_FakeDB(user)))
    assert replay.value.status_code == 400
