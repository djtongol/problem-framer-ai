"""Lightweight loaders and keyword retrieval for the Problem Framer reference data.

Works on Streamlit's free tier: pandas only, no vector DB, no extra installs.
Files expected next to this module (or pass a data_dir): metrics.csv, decisions.csv, diagnostic_lens.csv
"""
import re
from pathlib import Path
import pandas as pd

try:
    import streamlit as st
    _cache = st.cache_data
except Exception:  # lets you test outside Streamlit
    def _cache(fn):
        return fn

DATA_DIR = Path(__file__).parent.parent / "data"
_STOP = {"the","a","an","of","and","or","to","in","on","for","is","are","we","our","my","by","with","at","it","this","that",
         "what","why","how","do","does","did","has","have","been","from","as","be","can","should","will","than","more","less",
         "getting","worse","better","rising","dropping","falling","growing","going","taking","too","long","keep","keeps","after","before",
         "our","your","not","dont","trust","numbers","number","data"}


@_cache
def load_metrics(data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    df = pd.read_csv(Path(data_dir) / "metrics.csv", encoding="utf-8-sig").fillna("")
    # near-duplicate rows are hidden from suggestions; the canonical row stays
    return df[df["duplicate_of"] == ""].reset_index(drop=True)


@_cache
def load_decisions(data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    return pd.read_csv(Path(data_dir) / "decisions.csv", encoding="utf-8-sig").fillna("")


@_cache
def load_lens(data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    return pd.read_csv(Path(data_dir) / "diagnostic_lens.csv", encoding="utf-8-sig").fillna("")


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in _STOP and len(w) > 1}


def _score(query_tokens: set, fields: list) -> float:
    """fields = [(text, weight), ...]"""
    s = 0.0
    for text, w in fields:
        s += w * len(query_tokens & _tokens(text))
    return s


_TIER_RANK = {"headliner": 0, "drilldown": 1, "diagnostic": 2}


def _phrase_bonus(query: str, aliases: str) -> float:
    """+6 when a whole alias phrase appears in the user's text (e.g. 'late flights')."""
    q = " " + re.sub(r"[^a-z0-9 ]+", " ", query.lower().replace("'", "")) + " "
    return 6.0 if any(a.strip() and f" {a.strip().lower()} " in q for a in aliases.split(";")) else 0.0


def search_metrics(query: str, k: int = 8, domain: str | None = None, min_score: float = 3.0,
                   data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    """Name/alias hits are required to qualify; definition/category hits only break ties."""
    df = load_metrics(data_dir)
    if domain:
        df = df[df["domain"].str.contains(domain, case=False, regex=False)]
    q = _tokens(query)
    if not q:
        return df.head(0)
    scores = [
        _score(q, [(r.metric_name, 3), (r.aliases, 3), (r.category, 1), (r.definition, 0.5), (r.domain, 0.5)])
        + _phrase_bonus(query, r.aliases)
        for r in df.itertuples()
    ]
    out = df.assign(_score=scores, _tier=df["tier"].map(_TIER_RANK).fillna(3))
    out = out[out["_score"] >= min_score].sort_values(["_score", "_tier"], ascending=[False, True]).head(k)
    return out.drop(columns=["_score", "_tier"])


def search_decisions(query: str, k: int = 4, data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    df = load_decisions(data_dir)
    q = _tokens(query)
    scores = [_score(q, [(r.decision_label, 3), (r.example_phrasing, 2), (r.domain_tags, 1)]) for r in df.itertuples()]
    out = df.assign(_score=scores)
    return out[out["_score"] > 0].sort_values("_score", ascending=False).head(k).drop(columns="_score")


def search_lens(query: str, k: int = 2, min_score: float = 6.0, data_dir: str = str(DATA_DIR)) -> pd.DataFrame:
    df = load_lens(data_dir)
    q = _tokens(query)
    scores = [_score(q, [(r.symptom, 3), (r.diagnostic_check, 1), (r.domain, 1)]) for r in df.itertuples()]
    out = df.assign(_score=scores)
    return out[out["_score"] >= min_score].sort_values("_score", ascending=False).head(k).drop(columns="_score")


def format_metrics_reference(df: pd.DataFrame) -> str:
    """Compact text for the {metrics_reference} prompt variable (about 40 tokens per metric)."""
    lines = []
    for r in df.itertuples():
        status = " (unverified)" if "unverified" in r.source_status else ""
        lines.append(f"- {r.metric_id} | {r.metric_name} | {r.unit} | {r.polarity} | slice by: {r.typical_dimensions}{status}")
    return "\n".join(lines)


def format_decisions_reference(df: pd.DataFrame) -> str:
    return "\n".join(f"- {r.decision_id} | {r.decision_label} | usually owned by: {r.typical_owner_roles}" for r in df.itertuples())


def format_lens_reference(df: pd.DataFrame) -> str:
    return "\n".join(f"- If: {r.symptom} -> check: {r.diagnostic_check}" for r in df.itertuples())


def build_reference_context(user_text: str) -> dict:
    """Call once per user turn and fill the prompt variables from the result.

    Decisions are passed in full (32 short lines, about 600 tokens): the list is small, so the model
    picks the best fit itself, which is more reliable than keyword retrieval. Metrics and lenses are
    retrieved per turn so the prompt stays small.
    """
    return {
        "metrics_reference": format_metrics_reference(search_metrics(user_text, k=8)),
        "decisions_reference": format_decisions_reference(load_decisions()),
        "lens_reference": format_lens_reference(search_lens(user_text, k=2)),
    }
