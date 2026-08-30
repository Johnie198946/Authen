"""Production-safe OAuth settings and validation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


PLACEHOLDER_VALUES = {
    "",
    "your_wechat_app_id",
    "your_wechat_app_secret",
    "your_alipay_app_id",
    "your_alipay_app_secret",
    "your_alipay_app_private_key",
    "your_alipay_public_key",
}


@dataclass(frozen=True)
class OAuthProviderConfig:
    client_id: str
    client_secret: str
    provider_public_key: str = ""
    mode: str = ""
    requires_public_key: bool = False

    @property
    def is_configured(self) -> bool:
        required = [self.client_id, self.client_secret]
        if self.requires_public_key:
            required.append(self.provider_public_key)
        return all(value.strip() not in PLACEHOLDER_VALUES for value in required)


def _env(name: str, legacy_name: str = "") -> str:
    value = os.environ.get(name, "").strip()
    if not value and legacy_name:
        value = os.environ.get(legacy_name, "").strip()
    return value.replace("\\n", "\n")


def get_provider_config(provider: str) -> OAuthProviderConfig:
    if provider == "wechat":
        return OAuthProviderConfig(
            client_id=_env("WECHAT_APP_ID"),
            client_secret=_env("WECHAT_APP_SECRET"),
            mode=_env("WECHAT_OAUTH_MODE") or "website",
        )
    if provider == "alipay":
        return OAuthProviderConfig(
            client_id=_env("ALIPAY_APP_ID"),
            client_secret=_env("ALIPAY_APP_PRIVATE_KEY", "ALIPAY_APP_SECRET"),
            provider_public_key=_env("ALIPAY_PUBLIC_KEY"),
            requires_public_key=True,
        )
    if provider == "google":
        return OAuthProviderConfig(
            client_id=_env("GOOGLE_CLIENT_ID"),
            client_secret=_env("GOOGLE_CLIENT_SECRET"),
        )
    if provider == "apple":
        return OAuthProviderConfig(
            client_id=_env("APPLE_CLIENT_ID"),
            client_secret=_env("APPLE_CLIENT_SECRET"),
        )
    raise ValueError(f"不支持的OAuth提供商: {provider}")


def allowed_redirect_uris() -> set[str]:
    return {
        value.strip()
        for value in os.environ.get("OAUTH_ALLOWED_REDIRECT_URIS", "").split(",")
        if value.strip()
    }


def validate_redirect_uri(uri: str, *, debug: bool = False) -> bool:
    allowed = allowed_redirect_uris()
    if uri in allowed:
        return True
    if not debug:
        return False
    parsed = urlsplit(uri)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "localhost",
    }


def allow_debug_verification_codes() -> bool:
    return os.environ.get("ALLOW_DEBUG_VERIFICATION_CODES", "false").lower() in {
        "1",
        "true",
        "yes",
    }
