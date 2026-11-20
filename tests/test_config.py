"""Tests for settings resolution. No real API calls."""

from __future__ import annotations

import pytest

from src.config import AccessDenied, get_settings


def _patch_secrets(monkeypatch: pytest.MonkeyPatch, secrets: dict[str, str]) -> None:
    """Replace st.secrets with a plain dict for one test."""
    monkeypatch.setattr("src.config.st.secrets", secrets)


def test_user_key_skips_access_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller-supplied key is used and does not require the access code."""
    _patch_secrets(
        monkeypatch,
        {
            "OPENAI_API_KEY": "server-key",
            "ACCESS_CODE": "friends",
            "MODEL_NAME": "gpt-4.1-mini",
            "FAST_MODEL_NAME": "gpt-4.1-nano",
        },
    )

    settings = get_settings(user_api_key="  user-key  ", user_access_code=None)

    assert settings.api_key == "user-key"
    assert settings.using_own_key is True
    assert settings.access_code is None
    assert settings.model_name == "gpt-4.1-mini"
    assert settings.fast_model_name == "gpt-4.1-nano"
    assert settings.max_user_turns == 12
    assert settings.max_output_tokens == 4096


def test_server_key_requires_matching_access_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server key is returned only when the access code matches."""
    _patch_secrets(
        monkeypatch,
        {"OPENAI_API_KEY": "server-key", "ACCESS_CODE": "friends"},
    )

    settings = get_settings(user_access_code=" friends ")

    assert settings.api_key == "server-key"
    assert settings.using_own_key is False
    assert settings.access_code == "friends"
    assert settings.model_name == "gpt-4.1-mini"
    assert settings.fast_model_name == "gpt-4.1-nano"


def test_wrong_access_code_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrong or missing access code never unlocks the server key."""
    _patch_secrets(
        monkeypatch,
        {"OPENAI_API_KEY": "server-key", "ACCESS_CODE": "friends"},
    )

    with pytest.raises(AccessDenied, match="Access code does not match"):
        get_settings(user_access_code="nope")

    with pytest.raises(AccessDenied, match="Access code does not match"):
        get_settings()


def test_missing_server_key_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank user key and a missing server key is a clear denial."""
    _patch_secrets(monkeypatch, {"ACCESS_CODE": "friends"})

    with pytest.raises(AccessDenied, match="No API key is available"):
        get_settings(user_api_key="   ")


def test_model_names_come_from_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured model names override the defaults."""
    _patch_secrets(
        monkeypatch,
        {
            "OPENAI_API_KEY": "server-key",
            "ACCESS_CODE": "friends",
            "MODEL_NAME": "gemini-2.5-flash",
            "FAST_MODEL_NAME": "gemini-2.5-flash-lite",
        },
    )

    settings = get_settings(user_access_code="friends")

    assert settings.model_name == "gemini-2.5-flash"
    assert settings.fast_model_name == "gemini-2.5-flash-lite"


def test_denial_messages_do_not_include_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure text must not echo the key or the access code."""
    _patch_secrets(
        monkeypatch,
        {"OPENAI_API_KEY": "server-key-secret", "ACCESS_CODE": "friends-code"},
    )

    with pytest.raises(AccessDenied) as exc_info:
        get_settings(user_access_code="wrong")

    message = str(exc_info.value)
    assert "server-key-secret" not in message
    assert "friends-code" not in message
