"""Tests for src/chain.py (no real API calls)."""
import re

import pytest

from conftest import read_fixture
from src.chain import (ChainError, _content_text, _supports_temperature, build_system_prompt,
                       parse_status, run_turn)

HISTORY = [{"role": "user", "content": "Our support tickets are taking too long to close."}]


@pytest.mark.parametrize("reply,expected", [
    ("STATUS: CLARIFY\nbody", "CLARIFY"), ("STATUS: BRIEF\nbody", "BRIEF"),
    ("STATUS: CHAT\nbody", "CHAT"), ("hello", "UNKNOWN"), ("", "UNKNOWN"),
    ("STATUS: MAYBE\nbody", "UNKNOWN"),
])
def test_parse_status(reply, expected):
    assert parse_status(reply) == expected


def test_build_system_prompt_leaves_no_placeholders():
    prompt = build_system_prompt(["our support tickets are taking too long to close"], "2026-11-19")
    assert "2026-11-19" in prompt
    assert not re.search(r"\{(current_date|metrics_reference|decisions_reference|lens_reference)\}", prompt)
    assert not re.search(r"\{[a-z_]+\}", prompt)


def test_user_texts_change_metrics_reference():
    tickets = build_system_prompt(["support tickets taking too long to close"], "2026-11-19")
    flights = build_system_prompt(["late flights at SFO getting worse"], "2026-11-19")
    assert "CSV-001" in tickets and "AVO-001" not in tickets
    assert "AVO-001" in flights and "CSV-001" not in flights


def test_empty_user_texts_use_none_marker():
    prompt = build_system_prompt([], "2026-11-19")
    assert "METRICS_REFERENCE: (none)" in prompt
    assert not re.search(r"\{[a-z_]+\}", prompt)


def test_run_turn_ok_no_retry(use_fake_model, settings):
    model = use_fake_model([read_fixture("good_clarify")])
    result = run_turn(HISTORY, settings, "2026-11-19")
    assert (result.status, result.problems, result.retried) == ("CLARIFY", [], False)
    assert len(model.calls) == 1


def test_run_turn_retries_once_and_fixes(use_fake_model, settings):
    model = use_fake_model(["Sure! Here you go.", read_fixture("good_clarify")])
    result = run_turn(HISTORY, settings, "2026-11-19")
    assert result.retried is True and result.problems == [] and result.status == "CLARIFY"
    assert len(model.calls) == 2
    last = model.calls[1][-1].content
    assert "Rewrite the full reply and fix only these problems" in last
    assert "first line" in last


def test_run_turn_returns_problems_when_retry_still_bad(use_fake_model, settings):
    use_fake_model(["bad one", "bad two"])
    result = run_turn(HISTORY, settings, "2026-11-19")
    assert result.retried is True and result.problems and result.text == "bad two"


def test_run_turn_keeps_first_reply_if_retry_call_fails(use_fake_model, settings):
    use_fake_model(["bad one", RuntimeError("boom")])
    result = run_turn(HISTORY, settings, "2026-11-19")
    assert result.text == "bad one" and result.problems and result.retried is False


def test_errors_are_friendly_and_never_leak_keys(use_fake_model, settings):
    class AuthenticationError(Exception):
        pass

    use_fake_model([AuthenticationError("Incorrect API key provided: sk-secret123")])
    with pytest.raises(ChainError) as err:
        run_turn(HISTORY, settings, "2026-11-19")
    assert "key" in str(err.value).lower() and "sk-secret123" not in str(err.value)

    use_fake_model([RuntimeError("weird sk-secret123")])
    with pytest.raises(ChainError) as err:
        run_turn(HISTORY, settings, "2026-11-19")
    assert "sk-secret123" not in str(err.value)


def test_rate_limit_and_network_messages(use_fake_model, settings):
    class RateLimitError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    use_fake_model([RateLimitError("x")])
    with pytest.raises(ChainError, match="rate limiting"):
        run_turn(HISTORY, settings, "2026-11-19")
    use_fake_model([APIConnectionError("x")])
    with pytest.raises(ChainError, match="Could not reach"):
        run_turn(HISTORY, settings, "2026-11-19")


def test_empty_reply_raises(use_fake_model, settings):
    use_fake_model(["   "])
    with pytest.raises(ChainError, match="empty reply"):
        run_turn(HISTORY, settings, "2026-11-19")


def test_content_blocks_are_flattened():
    blocks = [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "STATUS: CHAT\n"},
              "more", {"type": "text", "text": " text"}]
    assert _content_text(blocks) == "STATUS: CHAT\nmore text"


def test_supports_temperature():
    assert _supports_temperature("gpt-4.1-mini") and _supports_temperature("gemini-2.5-flash")
    assert not _supports_temperature("gpt-5-mini") and not _supports_temperature("o3-mini")
