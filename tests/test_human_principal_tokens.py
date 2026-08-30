import asyncio
from types import SimpleNamespace

from services.auth import main as auth_service
from shared.utils.jwt import decode_token


class _Query:
    def __init__(self, user):
        self._user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._user


class _Db:
    def __init__(self, user):
        self._user = user

    def query(self, _model):
        return _Query(self._user)

    def commit(self):
        return None


def test_password_login_issues_auditable_human_tokens(monkeypatch):
    user = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        username="johnie",
        email="johnie@example.com",
        phone=None,
        password_hash="unused",
        status="active",
        failed_login_attempts=0,
        locked_until=None,
        last_login_at=None,
        password_changed=True,
    )
    monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)
    monkeypatch.setattr(
        auth_service,
        "create_sso_session",
        lambda *_args: SimpleNamespace(session_token="test-sso-session"),
    )

    response = asyncio.run(
        auth_service.login(
            auth_service.LoginRequest(identifier="johnie", password="correct-password"),
            _Db(user),
        )
    )

    access_claims = decode_token(response.access_token)
    refresh_claims = decode_token(response.refresh_token)
    assert access_claims is not None
    assert refresh_claims is not None
    assert access_claims["principal_type"] == "human"
    assert access_claims["amr"] == ["pwd"]
    assert isinstance(access_claims["auth_time"], int)
    assert refresh_claims["principal_type"] == "human"
    assert refresh_claims["amr"] == ["pwd"]
    assert refresh_claims["auth_time"] == access_claims["auth_time"]
