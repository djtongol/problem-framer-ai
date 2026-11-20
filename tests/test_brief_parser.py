"""Tests for src/brief_parser.py."""
from conftest import read_fixture
from src.brief_parser import parse_brief, split_tag

GOOD = read_fixture("good_brief")


def test_good_brief_structure():
    brief = parse_brief(GOOD)
    assert brief.title == "Billing Ticket Resolution Time in EU Support"
    assert brief.header["Confidence"] == "Medium"
    assert len(brief.sections[4].rows) == 4
    assert len(brief.sections[8].rows) == 2
    assert len(brief.sections[10].rows) == 3
    assert any(item["label"] == "North Star" for item in brief.sections[9].blueprint)
    assert brief.sections[9].fields["Primary"]["text"] == "Dashboard"
    assert brief.sections[9].blueprint_format == "Dashboard"
    assert sorted(brief.sections) == list(range(1, 11))
    assert brief.extra == [] and all(not s.extra for s in brief.sections.values())


def test_provenance_tags_are_kept_separately():
    brief = parse_brief(GOOD)
    assert brief.sections[5].fields["Primary stakeholder"] == {"text": "Head of Customer Support", "tag": "Stated"}
    assert brief.sections[5].fields["Reporting cadence"]["tag"] == "Suggested"
    assert brief.sections[5].fields["Consulted"] == {"text": "Unknown - to be confirmed", "tag": ""}
    hypothesis = brief.sections[3].lists["Initial hypotheses"][0]
    assert hypothesis["tag"] == "Suggested" and "[Suggested]" not in hypothesis["text"]
    assert split_tag("Plain value") == {"text": "Plain value", "tag": ""}


def test_supporting_questions_and_rows():
    brief = parse_brief(GOOD)
    q1 = brief.sections[4].rows[0]
    assert q1 == {"id": "Q1", "question": "Which ticket categories show the largest increase in resolution time?",
                  "metric": "Median hours to close by category", "timeframe": "Last 6 months"}
    row = brief.sections[8].rows[0]
    assert row["data_element"]["text"] == "Ticket opened and closed timestamps" and row["granularity"]["text"] == "Per event"
    open_q = brief.sections[10].rows[0]
    assert open_q["owner"]["text"] == "Head of Customer Support" and open_q["needed_by"]["text"].startswith("Unknown")


def test_scope_lists_and_blueprint_order():
    brief = parse_brief(GOOD)
    assert list(brief.sections[7].lists) == ["In scope", "Out of scope", "Assumptions",
                                              "Constraints and dependencies", "Risks", "Glossary"]
    labels = [b["label"] for b in brief.sections[9].blueprint]
    assert labels[:2] == ["North Star", "Supporting KPIs"] and labels[-1] == "Design rules"
    assert brief.sections[9].blueprint[3] == {"label": "Row 1", "content": brief.sections[9].blueprint[3]["content"]}
    assert brief.sections[9].blueprint[3]["content"].startswith("KPI strip | ")


def test_blueprint_split_prefers_pipe_when_it_comes_first():
    text = GOOD.replace("Primary: Dashboard", "Primary: Report").replace(
        "Blueprint (Dashboard):\nNorth Star: x", "Blueprint (Report):\nNorth Star: x")
    text = text.replace("Blueprint (Dashboard):", "Blueprint (Report):")
    text = text.replace("North Star:", "D1. Headline for Q1 | Bullets:", 1)
    item = parse_brief(text).sections[9].blueprint[0]
    assert item["label"] == "D1. Headline for Q1" and item["content"].startswith("Bullets:")


def test_changes_line_and_crlf_input():
    text = GOOD.replace("STATUS: BRIEF\n", "STATUS: BRIEF\nChanges: Owner is now the COO.\n").replace("\n", "\r\n")
    brief = parse_brief(text)
    assert brief.changes == "Owner is now the COO." and brief.title.endswith("EU Support")


def test_unknown_lines_go_to_extra_without_crashing():
    text = GOOD.replace("### 5. STAKEHOLDERS\n", "### 5. STAKEHOLDERS\nA stray remark\n")
    text = text.replace("### 10. OPEN QUESTIONS AND DECISIONS NEEDED\n", "### 10. OPEN QUESTIONS AND DECISIONS NEEDED\nStray text\n")
    text += "\n### 11. SURPRISE\nsomething\n"
    brief = parse_brief(text)
    assert "A stray remark" in brief.sections[5].extra
    assert "Stray text" in brief.sections[10].extra
    assert "### 11. SURPRISE" in " ".join(brief.extra) or 11 in brief.sections


def test_garbage_input_does_not_crash():
    brief = parse_brief("not a brief at all")
    assert brief.sections == {} and brief.title == ""
