"""Tests for the reference data layer (src/reference_loader.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reference_loader import (  # noqa: E402
    build_reference_context,
    load_metrics,
    search_metrics,
)

REQUIRED_COLUMNS = {
    "metric_id",
    "metric_name",
    "aliases",
    "polarity",
    "typical_dimensions",
}


def test_load_metrics_shape_and_duplicates_hidden():
    df = load_metrics()
    assert len(df) > 250
    assert REQUIRED_COLUMNS <= set(df.columns)
    assert (df["duplicate_of"] == "").all()


def test_search_late_flights_returns_avo_001_first():
    out = search_metrics("late flights at SFO getting worse")
    assert len(out) > 0
    assert out.iloc[0]["metric_id"] == "AVO-001"


def test_search_support_tickets_returns_csv_001_first():
    out = search_metrics("support tickets taking too long to close")
    assert len(out) > 0
    assert out.iloc[0]["metric_id"] == "CSV-001"


def test_build_reference_context_keys_and_decision_lines():
    ctx = build_reference_context("customers are leaving")
    assert set(ctx) == {"metrics_reference", "decisions_reference", "lens_reference"}
    lines = [ln for ln in ctx["decisions_reference"].splitlines() if ln.strip()]
    assert len(lines) == 32


def test_build_reference_context_empty_input_does_not_crash():
    ctx = build_reference_context("")
    assert ctx["metrics_reference"] == ""
    assert isinstance(ctx["decisions_reference"], str)
    assert isinstance(ctx["lens_reference"], str)
