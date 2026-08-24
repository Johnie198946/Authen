from urllib.parse import parse_qs, urlsplit

import pytest

from shared.oauth_settings import get_provider_config, validate_redirect_uri
from shared.utils.oauth_client import AlipayOAuthClient, WeChatOAuthClient


@pytest.mark.asyncio
async def test_wechat_website_login_uses_qr_scope_and_encoded_callback():
    client = WeChatOAuthClient(
        "wx-app",
        "wx-secret",
        "https://example.com/oauth/callback?source=web",
        mode="website",
    )

    url = await client.get_authorization_url("state-value")
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    assert parsed.path == "/connect/qrconnect"
    assert query["scope"] == ["snsapi_login"]
    assert query["redirect_uri"] == ["https://example.com/oauth/callback?source=web"]
    assert query["state"] == ["state-value"]


@pytest.mark.asyncio
async def test_alipay_exchange_failure_never_creates_mock_identity(monkeypatch):
    client = AlipayOAuthClient(
        "alipay-app",
        "invalid-private-key",
        "https://example.com/oauth/callback",
        provider_public_key="invalid-public-key",
    )

    async def fail(*args, **kwargs):
        raise ValueError("provider rejected request")

    monkeypatch.setattr(client, "_gateway_call", fail)
    with pytest.raises(ValueError, match="provider rejected"):
        await client.exchange_code_for_token("invalid-code")


def test_production_redirect_requires_exact_allowlist(monkeypatch):
    callback = "https://example.com/api/v1/auth/oauth/wechat/callback"
    monkeypatch.setenv("OAUTH_ALLOWED_REDIRECT_URIS", callback)

    assert validate_redirect_uri(callback, debug=False)
    assert not validate_redirect_uri(
        "https://evil.example/api/v1/auth/oauth/wechat/callback", debug=False
    )


def test_alipay_requires_private_and_public_keys(monkeypatch):
    monkeypatch.setenv("ALIPAY_APP_ID", "2026000000000000")
    monkeypatch.setenv("ALIPAY_APP_PRIVATE_KEY", "private")
    monkeypatch.delenv("ALIPAY_PUBLIC_KEY", raising=False)

    assert get_provider_config("alipay").is_configured is False
