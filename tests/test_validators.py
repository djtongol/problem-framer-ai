"""Tests for src/validators.py."""
import pytest

from conftest import read_fixture
from src.validators import validate_reply

GOOD = read_fixture("good_brief")


def joined(problems: list[str]) -> str:
    return " ".join(problems)


def test_prompt_examples_are_valid():
    for name in ("good_brief", "good_clarify", "guidance_clarify"):
        assert validate_reply(read_fixture(name)) == [], name


def test_bad_brief_reports_missing_section_and_bracket():
    problems = joined(validate_reply(read_fixture("bad_brief")))
    assert "### 6. SUCCESS METRICS" in problems
    assert "[Question]" in problems


@pytest.mark.parametrize("reply", ["", "Hello", "Sure.\nSTATUS: CLARIFY\nx", "STATUS: BRIEFING\nx"])
def test_first_line_must_be_a_status_line(reply):
    assert "first line" in joined(validate_reply(reply))


def test_chat_reply_is_valid_and_empty_chat_is_not():
    assert validate_reply("STATUS: CHAT\nThat is outside my role. Want to refine the brief?") == []
    assert "no content" in joined(validate_reply("STATUS: CHAT\n\n"))


def test_clarify_rules():
    assert "CLARIFICATION NEEDED" in joined(validate_reply("STATUS: CLARIFY\n1. What? (Example answer: x)"))
    five = "STATUS: CLARIFY\n## CLARIFICATION NEEDED\n" + "\n".join(f"{i}. Q{i}?" for i in range(1, 6))
    assert "at most 4" in joined(validate_reply(five))
    none = "STATUS: CLARIFY\n## CLARIFICATION NEEDED\nSo far I understand: x"
    assert "at least one numbered" in joined(validate_reply(none))


def test_brief_rules():
    cases = {
        'start with "How did"': GOOD.replace("Question: How did median", "Question: What was median"),
        "in order to decide": GOOD.replace("in order to decide", "to choose"),
        "at least 4": GOOD.replace("Q4: How many tickets are escalated, and how long do they wait?\n"
                                   "Metric: Escalation rate and median escalation wait in hours\n"
                                   "Timeframe: Last 6 months\n", ""),
        "missing its Timeframe": GOOD.replace("Metric: Tickets per agent per week\nTimeframe: Last 6 months\n",
                                              "Metric: Tickets per agent per week\n"),
        "different formats": GOOD.replace("Alternative: Report", "Alternative: Dashboard"),
        "Document status must be Draft or Ready": GOOD.replace("Ready for review", "Done"),
        "Confidence must be": GOOD.replace("Confidence: Medium", "Confidence: Very high"),
        "Draft when Confidence is Low": GOOD.replace("Confidence: Medium", "Confidence: Low"),
        "header block is missing the field: Version": GOOD.replace("Version: 1.0\n", ""),
        "Markdown tables": GOOD.replace("### 5. STAKEHOLDERS\n", "### 5. STAKEHOLDERS\n| a | b |\n|---|---|\n"),
        "out of order": GOOD.replace("### 2. BUSINESS CONTEXT", "### 7. SCOPE", 1),
    }
    for expected, text in cases.items():
        assert expected in joined(validate_reply(text)), expected


def test_text_after_section_10_is_flagged():
    problems = validate_reply(GOOD + "Let me know if you want changes.\n")
    assert 'Section 10 must contain only lines that start with "- "' in joined(problems)


def test_changes_line_is_allowed():
    text = GOOD.replace("STATUS: BRIEF\n", "STATUS: BRIEF\nChanges: Owner updated.\n").replace("Version: 1.0", "Version: 1.1")
    assert validate_reply(text) == []
