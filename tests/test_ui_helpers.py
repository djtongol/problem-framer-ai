"""Tests for src/ui_helpers.py (pure functions only)."""
from conftest import read_fixture
from src.ui_helpers import (escape_dollars, extract_options, format_for_display, progress_text,
                            render_tags, strip_status_line)


def test_render_tags():
    assert render_tags("A [Stated] B [Suggested]") == "A :green[Stated] B :orange[Suggested]"


def test_strip_status_line():
    assert strip_status_line("STATUS: BRIEF\n## BUSINESS REQUIREMENTS BRIEF\nx") == "## BUSINESS REQUIREMENTS BRIEF\nx"
    assert strip_status_line("no status line") == "no status line"


def test_extract_options_skips_none_of_these():
    options = extract_options(read_fixture("guidance_clarify"))
    assert [letter for letter, _ in options] == ["A", "B", "C"]
    assert options[0][1] == "Median hours from ticket opened to closed"
    assert extract_options(read_fixture("good_clarify")) == []


def test_format_for_display_keeps_line_breaks_and_escapes_dollars():
    out = format_for_display("Label: $5 [Stated]\nNext: x")
    assert out == "Label: \\$5 :green[Stated]  \nNext: x"
    assert escape_dollars("$1") == "\\$1"


def test_progress_text():
    assert progress_text(3, 12) == "Turn 3 of 12"
