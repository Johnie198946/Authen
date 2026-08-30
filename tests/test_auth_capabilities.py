from __future__ import annotations

import asyncio

from fastapi import HTTPException

import services.auth.main as auth_main
import services.notification.sms_service as sms_module
import shared.utils.oauth_client as oauth_client_module
import shared.utils.validators as validators


class FakeRedis:
    def __init__(self):
        self.values = {}

    def exists(self, key):
        return key in self.values

    def setex(self, key, ttl, value):
        self.values[key] = (ttl, value)


class FakeSMSService:
    def __init__(self, *, ready=True, send_ok=True):
        self.sms_client = object() if ready else None
        self.send_ok = send_ok

    def send_verification_sms(self, phone, code):
        return self.send_ok


def _alipay_env(monkeypatch):
    monkeypatch.setenv("ALIPAY_APP_ID", "app-id")
    monkeypatch.setenv("ALIPAY_APP_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("ALIPAY_PUBLIC_KEY", "public-key")


def test_sms_environment_requires_template_code(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "aliyun")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "secret")
    monkeypatch.setenv("ALIYUN_SMS_SIGN_NAME", "sign")
    monkeypatch.delenv("ALIYUN_SMS_TEMPLATE_CODE", raising=False)
    assert sms_module.SMSService._environment_config() is None


def test_capabilities_report_real_sms_and_alipay_readiness(monkeypatch):
    monkeypatch.setattr(sms_module, "SMSService", lambda: FakeSMSService(ready=True))
    _alipay_env(monkeypatch)
    payload = asyncio.run(auth_main.auth_capabilities())
    assert payload["phone"] == {"enabled": True, "reason": "configured"}
    assert payload["oauth"]["alipay"] == {"enabled": True, "reason": "configured"}
    assert payload["oauth"]["wechat"]["enabled"] is False


def test_sms_code_is_persisted_only_after_provider_success(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(auth_main, "get_redis", lambda: redis)
    monkeypatch.setattr(validators, "validate_phone", lambda _phone: True)
    monkeypatch.setattr(auth_main.settings, "DEBUG", False)
    monkeypatch.setattr(sms_module, "SMSService", lambda: FakeSMSService(send_ok=True))
    result = asyncio.run(auth_main.send_sms_code(auth_main.SendSMSRequest(phone="+8613800138000")))
    assert result["success"] is True
    assert result["code"] is None
    assert "sms_code:+8613800138000" in redis.values
    assert "code_rate:sms:+8613800138000" in redis.values


def test_sms_provider_failure_does_not_create_ghost_code(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(auth_main, "get_redis", lambda: redis)
    monkeypatch.setattr(validators, "validate_phone", lambda _phone: True)
    monkeypatch.setattr(auth_main.settings, "DEBUG", False)
    monkeypatch.setattr(sms_module, "SMSService", lambda: FakeSMSService(send_ok=False))
    try:
        asyncio.run(auth_main.send_sms_code(auth_main.SendSMSRequest(phone="+8613800138000")))
    except HTTPException as error:
        assert error.status_code == 503
    else:
        raise AssertionError("provider failure must be explicit")
    assert redis.values == {}


def test_alipay_authorize_uses_validated_provider_config(monkeypatch):
    _alipay_env(monkeypatch)
    monkeypatch.setenv("OAUTH_ALLOWED_REDIRECT_URIS", "https://example.com/callback")
    captured = {}

    class FakeClient:
        async def get_authorization_url(self, state):
            return f"https://alipay.example/authorize?state={state}"

    def fake_factory(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(oauth_client_module, "get_oauth_client", fake_factory)
    result = asyncio.run(auth_main.oauth_authorize(
        "alipay", "https://example.com/callback", "state-1"
    ))
    assert result["state"] == "state-1"
    assert captured["provider_public_key"] == "public-key"
    assert captured["client_secret"] == "private-key"
