"""Format checks for model replies (STATUS line, CLARIFY and BRIEF structure)."""

from __future__ import annotations

import re

STATUS_LINES = ("STATUS: CLARIFY", "STATUS: BRIEF", "STATUS: CHAT")
HEADERS = [
    "## BUSINESS REQUIREMENTS BRIEF",
    "### EXECUTIVE SUMMARY",
    "### 1. PROBLEM STATEMENT",
    "### 2. BUSINESS CONTEXT",
    "### 3. PRIMARY BUSINESS QUESTION",
    "### 4. SUPPORTING QUESTIONS",
    "### 5. STAKEHOLDERS",
    "### 6. SUCCESS METRICS",
    "### 7. SCOPE",
    "### 8. DATA REQUIREMENTS",
    "### 9. RECOMMENDED DELIVERABLE",
    "### 10. OPEN QUESTIONS AND DECISIONS NEEDED",
]
HEADER_FIELDS = [
    "Title", "Prepared for", "Prepared by", "Date", "Version",
    "Document status", "Confidence", "Approval status",
]
FORMATS = ("Dashboard", "Report", "Presentation")
_BRACKET = re.compile(r"\[[^\]\n]*\]")


def validate_reply(reply: str) -> list[str]:
    """Return a list of problems with the reply (an empty list means it is OK)."""
    lines = reply.splitlines()
    first = lines[0].rstrip() if lines else ""
    if first not in STATUS_LINES:
        return [
            "The first line must be exactly one of: STATUS: CLARIFY, STATUS: BRIEF, "
            "STATUS: CHAT, with nothing before it."
        ]
    body = [ln for ln in lines[1:] if ln.strip()]
    if not body:
        return ["There is no content after the status line."]
    if first == "STATUS: CLARIFY":
        return _check_clarify(lines)
    if first == "STATUS: BRIEF":
        return _check_brief(lines)
    return []


def _check_clarify(lines: list[str]) -> list[str]:
    problems: list[str] = []
    if "## CLARIFICATION NEEDED" not in [ln.strip() for ln in lines]:
        problems.append('A CLARIFY reply must contain the header "## CLARIFICATION NEEDED".')
    numbered = [ln for ln in lines if re.match(r"^\d+\.\s", ln)]
    if not numbered:
        problems.append("A CLARIFY reply must contain at least one numbered question.")
    if len(numbered) > 4:
        problems.append(f"A CLARIFY reply may have at most 4 numbered questions (found {len(numbered)}).")
    return problems


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Map each known header to the lines that follow it, up to the next known header."""
    positions = {}
    for i, ln in enumerate(lines):
        if ln.strip() in HEADERS and ln.strip() not in positions:
            positions[ln.strip()] = i
    ordered = sorted(positions.items(), key=lambda kv: kv[1])
    out = {}
    for idx, (header, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else len(lines)
        out[header] = lines[start + 1:end]
    return out


def _field(block: list[str], label: str) -> str | None:
    for ln in block:
        m = re.match(rf"^{re.escape(label)}:\s*(.*)$", ln.strip())
        if m:
            return m.group(1).strip()
    return None


def _check_brief(lines: list[str]) -> list[str]:
    problems: list[str] = []
    stripped = [ln.strip() for ln in lines]
    missing = [h for h in HEADERS if h not in stripped]
    if missing:
        problems.append("Missing headers: " + "; ".join(missing) + ".")
    present = [stripped.index(h) for h in HEADERS if h in stripped]
    if present != sorted(present):
        problems.append("The brief headers are out of order. Use the exact order from the template.")
    sections = _split_sections(lines)

    header_block = sections.get(HEADERS[0], [])
    for label in HEADER_FIELDS:
        if not _field(header_block, label):
            problems.append(f"The header block is missing the field: {label}.")
    status = _field(header_block, "Document status")
    conf = _field(header_block, "Confidence")
    if status and status not in ("Draft", "Ready for review"):
        problems.append("Document status must be Draft or Ready for review.")
    if conf and conf not in ("High", "Medium", "Low"):
        problems.append("Confidence must be High, Medium or Low.")
    if status in ("Draft", "Ready for review") and conf in ("High", "Medium", "Low"):
        if (conf == "Low") != (status == "Draft"):
            problems.append("Document status must be Draft when Confidence is Low, otherwise Ready for review.")

    problems += _check_section3(sections.get("### 3. PRIMARY BUSINESS QUESTION", []))
    problems += _check_section4(sections.get("### 4. SUPPORTING QUESTIONS", []))
    problems += _check_section9(sections.get("### 9. RECOMMENDED DELIVERABLE", []))
    problems += _check_section10(sections.get("### 10. OPEN QUESTIONS AND DECISIONS NEEDED", []))

    bad = sorted({b for b in _BRACKET.findall("\n".join(lines[1:])) if b not in ("[Stated]", "[Suggested]")})
    if bad:
        problems.append("Leftover brackets found: " + ", ".join(bad) + ". Only [Stated] and [Suggested] are allowed.")
    if any(re.match(r"^\s*\|", ln) or re.match(r"^\s*:?-{3,}:?\s*\|", ln) for ln in lines):
        problems.append("Markdown tables are not allowed in a brief. Use Label: value lines.")
    return problems


def _check_section3(block: list[str]) -> list[str]:
    question = _field(block, "Question")
    if question is None:
        return []  # a missing header is reported elsewhere
    out = []
    if not question.startswith("How did"):
        out.append('The Section 3 Question must start with "How did".')
    if "in order to decide" not in question:
        out.append('The Section 3 Question must contain "in order to decide".')
    return out


def _check_section4(block: list[str]) -> list[str]:
    groups: list[list[str]] = []
    for ln in block:
        if re.match(r"^Q\d+:", ln.strip()):
            groups.append([ln.strip()])
        elif groups:
            groups[-1].append(ln.strip())
    out = []
    if len(groups) < 4:
        out.append(f"Section 4 needs at least 4 supporting questions (found {len(groups)}).")
    if len(groups) > 8:
        out.append(f"Section 4 allows at most 8 supporting questions (found {len(groups)}).")
    for g in groups:
        qid = g[0].split(":")[0]
        for label in ("Metric", "Timeframe"):
            if _field(g[1:], label) is None:
                out.append(f"{qid} is missing its {label} line.")
    return out


def _check_section9(block: list[str]) -> list[str]:
    primary, alt = _field(block, "Primary"), _field(block, "Alternative")
    out = []
    for label, val in (("Primary", primary), ("Alternative", alt)):
        if val is not None and val not in FORMATS:
            out.append(f"Section 9 {label} must be Dashboard, Report or Presentation.")
    if primary and primary == alt:
        out.append("Section 9 Primary and Alternative must be different formats.")
    return out


def _check_section10(block: list[str]) -> list[str]:
    content = [ln for ln in block if ln.strip()]
    out = []
    if content and any(not ln.lstrip().startswith("- ") for ln in content):
        out.append('Section 10 must contain only lines that start with "- " and no text after it.')
    if len(content) > 8:
        out.append(f"Section 10 allows at most 8 lines (found {len(content)}).")
    return out
