"""Shared test helpers: a fake chat model, fixture loader and default settings."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


class FakeModel:
    """Returns scripted replies (or raises scripted exceptions) and records every call."""

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls: list = []

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(content=reply)


def read_fixture(name: str) -> str:
    """Read tests/fixtures/<name>.txt."""
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture
def settings() -> Settings:
    return Settings(api_key="test-key", model_name="main", fast_model_name="fast",
                    access_code=None, provider="openai")


@pytest.fixture
def use_fake_model(monkeypatch):
    """Call install(replies) to route every model call to a FakeModel; returns the model."""
    def install(replies: list) -> FakeModel:
        model = FakeModel(replies)
        monkeypatch.setattr("src.chain._get_model", lambda settings, model_name=None: model)
        return model
    return install
