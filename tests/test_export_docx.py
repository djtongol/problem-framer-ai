"""Tests for src/export_docx.py."""
from io import BytesIO

from docx import Document

from conftest import read_fixture
from src.brief_parser import parse_brief
from src.export_docx import LEGEND, brief_to_docx

GOOD = read_fixture("good_brief")


def all_text(doc) -> str:
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    for section in doc.sections:
        parts.extend(p.text for p in section.header.paragraphs + section.footer.paragraphs)
    return "\n".join(parts)


def build(text: str):
    data = brief_to_docx(parse_brief(text))
    assert data[:2] == b"PK"  # a .docx is a zip file
    return Document(BytesIO(data))


def test_good_brief_exports_a_complete_document():
    doc = build(GOOD)
    text = all_text(doc)
    assert "Billing Ticket Resolution Time in EU Support" in text
    assert "DRAFT" not in text
    assert len(doc.tables) >= 6
    assert "Prepared with Problem Framer AI" in text


def test_page_setup_is_letter_with_one_inch_margins():
    section = build(GOOD).sections[0]
    assert round(section.page_width.inches, 2) == 8.5 and round(section.page_height.inches, 2) == 11
    assert round(section.left_margin.inches, 2) == 1.0


def test_tags_become_daggers_and_legend_is_present():
    text = all_text(build(GOOD))
    assert "[Suggested]" not in text and "[Stated]" not in text
    assert "\u2020" in text and LEGEND in text


def test_suggested_values_are_italic():
    doc = build(GOOD)
    italic_runs = [r for t in doc.tables for row in t.rows for c in row.cells
                   for p in c.paragraphs for r in p.runs if r.italic]
    assert any("Monthly" in r.text for r in italic_runs)


def test_sign_off_table_is_last_and_empty():
    doc = build(GOOD)
    table = doc.tables[-1]
    assert [c.text for c in table.rows[0].cells] == ["Role", "Name", "Date", "Signature"]
    assert [r.cells[0].text for r in table.rows[1:]] == ["Prepared by", "Reviewed by", "Approved by (Decision authority)"]
    assert all(c.text == "" for r in table.rows[1:] for c in r.cells[1:])


def test_draft_brief_gets_draft_markers():
    draft = GOOD.replace("Ready for review", "Draft").replace("Confidence: Medium", "Confidence: Low")
    doc = build(draft)
    assert "DRAFT" in [p.text for p in doc.paragraphs]
    assert any("DRAFT - not yet approved" in p.text for p in doc.sections[0].header.paragraphs)


def test_supporting_questions_and_blueprint_tables():
    doc = build(GOOD)
    headers = [[c.text for c in t.rows[0].cells] for t in doc.tables]
    assert ["ID", "Question", "Metric", "Timeframe"] in headers
    assert ["Data element", "Source", "Owner", "Granularity", "Issues"] in headers
    assert ["Item", "Content"] in headers and ["Term", "Meaning"] in headers
    assert "North Star" in all_text(doc)


def test_changes_line_is_shown():
    text = GOOD.replace("STATUS: BRIEF\n", "STATUS: BRIEF\nChanges: Owner is now the COO.\n")
    assert "Owner is now the COO." in all_text(build(text))


def test_partial_brief_still_exports():
    assert len(build("STATUS: BRIEF\n## BUSINESS REQUIREMENTS BRIEF\nTitle: Tiny\n").tables) >= 1
