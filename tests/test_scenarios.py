"""Offline versions of the 8 scenarios in docs/MANUAL_TESTS.md.

These check the validators, the parser and the turn pipeline on canned replies.
They cannot prove what the real model will say; the live checks are in the manual checklist.
"""
import re

from conftest import read_fixture
from src.brief_parser import parse_brief
from src.chain import parse_status, run_turn
from src.validators import validate_reply

GOOD = read_fixture("good_brief")
CLARIFY = read_fixture("good_clarify")
GUIDANCE = read_fixture("guidance_clarify")
SUGGESTION_LINE = "These are suggestions, not facts."
DRAFT = GOOD.replace("Ready for review", "Draft").replace("Confidence: Medium", "Confidence: Low")
REVISED = (GOOD.replace("STATUS: BRIEF\n", "STATUS: BRIEF\nChanges: The decision owner is now the COO.\n")
           .replace("Version: 1.0", "Version: 1.1")
           .replace("Decision authority: Head of Customer Support [Stated]", "Decision authority: COO [Stated]"))
CONFLICT = (GOOD.replace("Assumptions:\n", "Assumptions:\n- The period was first stated as the last 6 months, then changed to last quarter; "
                                          "the newest statement is used [Suggested]\n")
            .replace("### 10. OPEN QUESTIONS AND DECISIONS NEEDED\n",
                     "### 10. OPEN QUESTIONS AND DECISIONS NEEDED\n- Confirm whether the period is the last quarter or the last 6 months. "
                     "| Owner: Head of Customer Support | Needed by: Unknown - to be confirmed\n"))
CHAT = "STATUS: CHAT\nWriting SQL is outside my role; I can refine the brief if you like."
HISTORY = [{"role": "user", "content": "our sales are declining"}]


def test_1_vague_start_gives_one_to_four_questions_with_examples():
    assert validate_reply(CLARIFY) == [] and parse_status(CLARIFY) == "CLARIFY"
    questions = [ln for ln in CLARIFY.splitlines() if re.match(r"^\d+\.\s", ln)]
    assert 1 <= len(questions) <= 4
    assert all("(Example answer:" in q for q in questions)


def test_2_full_answers_give_a_ready_brief():
    brief = parse_brief(GOOD)
    assert validate_reply(GOOD) == [] and parse_status(GOOD) == "BRIEF"
    assert brief.header["Confidence"] in ("High", "Medium")
    assert brief.header["Document status"] == "Ready for review"


def test_3_dont_know_gives_lettered_options_and_the_suggestion_line():
    assert validate_reply(GUIDANCE) == [] and parse_status(GUIDANCE) == "CLARIFY"
    assert all(f"{letter})" in GUIDANCE for letter in "ABCD")
    assert SUGGESTION_LINE in GUIDANCE


def test_4_second_vague_answer_gets_options(use_fake_model, settings):
    model = use_fake_model([CLARIFY, GUIDANCE])
    first = run_turn(HISTORY, settings, "2026-11-19")
    history = HISTORY + [{"role": "assistant", "content": first.text}, {"role": "user", "content": "not sure"}]
    second = run_turn(history, settings, "2026-11-19")
    assert "A)" not in first.text and "A)" in second.text and SUGGESTION_LINE in second.text
    assert second.status == "CLARIFY" and second.problems == []
    assert len(model.calls[1]) == 4  # system prompt plus three chat messages


def test_5_nothing_useful_twice_gives_a_low_confidence_draft():
    brief = parse_brief(DRAFT)
    assert validate_reply(DRAFT) == [] and parse_status(DRAFT) == "BRIEF"
    assert (brief.header["Document status"], brief.header["Confidence"]) == ("Draft", "Low")


def test_6_correction_gives_a_new_brief_with_version_1_1_and_changes():
    brief = parse_brief(REVISED)
    assert validate_reply(REVISED) == []
    assert brief.header["Version"] == "1.1" and brief.changes
    assert brief.sections[5].fields["Decision authority"]["text"] == "COO"


def test_7_out_of_scope_request_gets_a_one_sentence_chat_reply():
    assert validate_reply(CHAT) == [] and parse_status(CHAT) == "CHAT"
    assert len(CHAT.splitlines()) == 2 and CHAT.count(".") == 1


def test_8_conflict_shows_in_assumptions_and_open_questions():
    brief = parse_brief(CONFLICT)
    assert validate_reply(CONFLICT) == []
    assumptions = " ".join(item["text"] for item in brief.sections[7].lists["Assumptions"])
    open_questions = " ".join(row["question"]["text"] for row in brief.sections[10].rows)
    assert "last quarter" in assumptions and "last quarter" in open_questions
