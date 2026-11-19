"""Load runtime settings from Streamlit secrets or a user-supplied key."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import streamlit as st

DEFAULT_MODEL_NAME = "claude-sonnet-5-5"
DEFAULT_FAST_MODEL_NAME = "claude-haiku-5-5"


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


def get_settings(
    user_api_key: str | None = None,
    user_access_code: str | None = None,
) -> Settings:
    """Build settings from the caller's key or the server key.

    A non-empty user_api_key replaces the server key and skips the access-code
    check. Using the server key requires user_access_code to equal ACCESS_CODE.
    """
    secrets = st.secrets
    model_name = _secret_text(secrets, "MODEL_NAME") or DEFAULT_MODEL_NAME
    fast_model_name = _secret_text(secrets, "FAST_MODEL_NAME") or DEFAULT_FAST_MODEL_NAME
    own_key = _clean(user_api_key)

    if own_key:
        return Settings(
            api_key=own_key,
            model_name=model_name,
            fast_model_name=fast_model_name,
            access_code=None,
            using_own_key=True,
        )

    server_key = _secret_text(secrets, "ANTHROPIC_API_KEY")
    if not server_key:
        raise AccessDenied(
            "No API key is available. Enter your own key or configure the server key."
        )

    expected_code = _secret_text(secrets, "ACCESS_CODE")
    provided_code = _clean(user_access_code)
    if not expected_code or provided_code != expected_code:
        raise AccessDenied("Access code does not match.")

    return Settings(
        api_key=server_key,
        model_name=model_name,
        fast_model_name=fast_model_name,
        access_code=expected_code,
        using_own_key=False,
    )


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
