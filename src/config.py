"""Load runtime settings from Streamlit secrets or a user-supplied key.

Supports two providers: "openai" (default when PROVIDER is not set) and "google"
(Gemini). Set PROVIDER in secrets.toml to switch.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import streamlit as st

DEFAULT_MODEL_NAME = "gpt-4.1-mini"
DEFAULT_FAST_MODEL_NAME = "gpt-4.1-nano"
DEFAULT_PROVIDER = "openai"
MAX_MESSAGE_CHARS = 4000

# provider -> (secret name for the server key, default main model, default fast model)
PROVIDERS: dict[str, tuple[str, str, str]] = {
    "openai": ("OPENAI_API_KEY", DEFAULT_MODEL_NAME, DEFAULT_FAST_MODEL_NAME),
    "google": ("GOOGLE_API_KEY", "gemini-2.5-flash", "gemini-2.5-flash-lite"),
}


class AccessDenied(Exception):
    """Raised when the server key is used without the matching access code."""


@dataclass
class Settings:
    """Resolved API and model settings for one session."""

    api_key: str
    model_name: str
    fast_model_name: str
    access_code: str | None
    max_user_turns: int = 12
    max_output_tokens: int = 4096
    using_own_key: bool = False
    provider: str = DEFAULT_PROVIDER
    max_message_chars: int = MAX_MESSAGE_CHARS


def get_settings(
    user_api_key: str | None = None,
    user_access_code: str | None = None,
) -> Settings:
    """Build settings from the caller's key or the server key.

    A non-empty user_api_key replaces the server key and skips the access-code
    check. Using the server key requires user_access_code to equal ACCESS_CODE
    when ACCESS_CODE is set; if it is not set, the server key is used without a code.
    """
    secrets = st.secrets
    provider = (_secret_text(secrets, "PROVIDER") or DEFAULT_PROVIDER).lower()
    if provider not in PROVIDERS:
        raise AccessDenied(
            f"Unknown PROVIDER '{provider}'. Use one of: {', '.join(PROVIDERS)}."
        )
    key_name, default_main, default_fast = PROVIDERS[provider]
    model_name = _secret_text(secrets, "MODEL_NAME") or default_main
    fast_model_name = _secret_text(secrets, "FAST_MODEL_NAME") or default_fast
    own_key = _clean(user_api_key)

    if own_key:
        return Settings(
            api_key=own_key,
            model_name=model_name,
            fast_model_name=fast_model_name,
            access_code=None,
            using_own_key=True,
            provider=provider,
        )

    server_key = _secret_text(secrets, key_name)
    if not server_key and provider == "google":
        server_key = _secret_text(secrets, "GEMINI_API_KEY")  # accepted alias
    if not server_key:
        raise AccessDenied(
            "No API key is available. Enter your own key or configure the server key."
        )

    expected_code = _secret_text(secrets, "ACCESS_CODE")
    provided_code = _clean(user_access_code)
    if expected_code and provided_code != expected_code:
        raise AccessDenied("Access code does not match.")

    return Settings(
        api_key=server_key,
        model_name=model_name,
        fast_model_name=fast_model_name,
        access_code=expected_code,
        using_own_key=False,
        provider=provider,
    )


def access_code_required() -> bool:
    """True when ACCESS_CODE is set in secrets; when it is not set, no code is asked for."""
    return bool(_secret_text(st.secrets, "ACCESS_CODE"))


def _secret_text(secrets: Mapping[str, Any], key: str) -> str | None:
    """Return a stripped secret value, or None when it is missing or blank."""
    if key not in secrets:
        return None
    return _clean(secrets[key])


def _clean(value: Any) -> str | None:
    """Return stripped text, or None for missing and blank values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
