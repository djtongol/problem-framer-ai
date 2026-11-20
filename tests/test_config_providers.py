"""Tests for the provider support added to src/config.py."""
import pytest
import streamlit as st

from src.config import AccessDenied, get_settings


def use_secrets(monkeypatch, secrets: dict) -> None:
    monkeypatch.setattr(st, "secrets", secrets)


def test_no_provider_defaults_to_openai(monkeypatch):
    use_secrets(monkeypatch, {"OPENAI_API_KEY": "k", "ACCESS_CODE": "c"})
    s = get_settings(None, "c")
    assert (s.provider, s.model_name, s.fast_model_name) == ("openai", "gpt-4.1-mini", "gpt-4.1-nano")


def test_google_accepts_gemini_api_key_alias(monkeypatch):
    use_secrets(monkeypatch, {"PROVIDER": "google", "GEMINI_API_KEY": "g2", "ACCESS_CODE": "c"})
    s = get_settings(None, "c")
    assert s.provider == "google" and s.api_key == "g2"


def test_openai_provider_uses_its_key_and_models(monkeypatch):
    use_secrets(monkeypatch, {"PROVIDER": "openai", "OPENAI_API_KEY": "sk-x", "ACCESS_CODE": "c"})
    s = get_settings(None, "c")
    assert s.provider == "openai" and s.api_key == "sk-x" and s.model_name.startswith("gpt")


def test_google_provider_and_model_override(monkeypatch):
    use_secrets(monkeypatch, {"PROVIDER": "Google", "GOOGLE_API_KEY": "g", "ACCESS_CODE": "c",
                              "MODEL_NAME": "gemini-custom"})
    s = get_settings(None, "c")
    assert s.provider == "google" and s.api_key == "g" and s.model_name == "gemini-custom"


def test_no_access_code_configured_means_no_code_needed(monkeypatch):
    use_secrets(monkeypatch, {"OPENAI_API_KEY": "k"})
    s = get_settings(None, None)
    assert s.api_key == "k" and s.access_code is None


def test_own_key_skips_the_access_code(monkeypatch):
    use_secrets(monkeypatch, {"PROVIDER": "openai"})
    s = get_settings("  my-own-key ")
    assert s.using_own_key and s.api_key == "my-own-key" and s.provider == "openai"


def test_wrong_code_missing_key_and_unknown_provider(monkeypatch):
    use_secrets(monkeypatch, {"PROVIDER": "openai", "OPENAI_API_KEY": "k", "ACCESS_CODE": "c"})
    with pytest.raises(AccessDenied, match="Access code"):
        get_settings(None, "nope")
    use_secrets(monkeypatch, {"PROVIDER": "openai", "GOOGLE_API_KEY": "k", "ACCESS_CODE": "c"})
    with pytest.raises(AccessDenied, match="No API key"):
        get_settings(None, "c")
    use_secrets(monkeypatch, {"PROVIDER": "mystery"})
    with pytest.raises(AccessDenied, match="Unknown PROVIDER"):
        get_settings(None, None)
