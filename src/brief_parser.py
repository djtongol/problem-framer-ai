"""Parse a BRIEF reply into Python objects.

Tagged values (sections 1 to 10) are dicts {"text": ..., "tag": ...} where tag is
"Stated", "Suggested" or "". Section 4 rows hold plain strings (no tags by design).
Unknown lines never crash the parser: they go into an "extra" list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TAG = re.compile(r"\s*\[(Stated|Suggested)\]\s*\.?\s*$")
_LABEL = re.compile(r"^([^:|]{1,60}):\s*(.*)$")
_SECTION = re.compile(r"^###\s+(\d+)\.\s+(.*)$")


def split_tag(value: str) -> dict[str, str]:
    """'Customer Support [Stated]' -> {'text': 'Customer Support', 'tag': 'Stated'}."""
    value = value.strip()
    m = _TAG.search(value)
    if not m:
        return {"text": value, "tag": ""}
    return {"text": value[:m.start()].strip(), "tag": m.group(1)}


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


@dataclass
class Section:
    """One numbered section of the brief."""

    number: int
    title: str
    fields: dict[str, dict] = field(default_factory=dict)
    lists: dict[str, list[dict]] = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)  # sections 4, 8, 10
    blueprint: list[dict] = field(default_factory=list)  # section 9: [{"label", "content"}]
    blueprint_format: str = ""
    extra: list[str] = field(default_factory=list)


@dataclass
class Brief:
    """A parsed Business Requirements Brief."""

    header: dict[str, str] = field(default_factory=dict)
    exec_summary: dict[str, str] = field(default_factory=dict)
    sections: dict[int, Section] = field(default_factory=dict)
    changes: str = ""
    extra: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.header.get("Title", "")


def parse_brief(text: str) -> Brief:
    """Parse the text of a STATUS: BRIEF reply (the STATUS line is optional)."""
    brief = Brief()
    block_name, block = "preamble", []
    blocks: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("STATUS:"):
            continue
        if s.startswith("## ") or s.startswith("### "):
            blocks.append((block_name, block))
            block_name, block = s, []
        else:
            block.append(line)
    blocks.append((block_name, block))

    for name, lines in blocks:
        if name == "preamble":
            _parse_preamble(brief, lines)
        elif name == "## BUSINESS REQUIREMENTS BRIEF":
            brief.header = _plain_fields(lines, brief.extra)
        elif name == "### EXECUTIVE SUMMARY":
            brief.exec_summary = _plain_fields(lines, brief.extra)
        elif _SECTION.match(name):
            m = _SECTION.match(name)
            sec = Section(number=int(m.group(1)), title=m.group(2).strip())
            _parse_section(sec, lines)
            brief.sections[sec.number] = sec
        else:
            brief.extra.append(name)
            brief.extra.extend(ln.strip() for ln in lines if ln.strip())
    return brief


def _parse_preamble(brief: Brief, lines: list[str]) -> None:
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.lower().startswith("changes:"):
            brief.changes = s.split(":", 1)[1].strip()
        else:
            brief.extra.append(s)


def _plain_fields(lines: list[str], extra: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = _LABEL.match(s)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
        else:
            extra.append(s)
    return out


def _parse_section(sec: Section, lines: list[str]) -> None:
    if sec.number == 4:
        return _parse_questions(sec, lines)
    if sec.number == 8:
        return _parse_data_rows(sec, lines)
    if sec.number == 10:
        return _parse_open_questions(sec, lines)
    current_list: str | None = None
    in_blueprint = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if in_blueprint:
            sec.blueprint.append(_split_blueprint_line(s))
            continue
        if s.startswith("- "):
            if current_list is None:
                sec.extra.append(s)
            else:
                sec.lists[current_list].append(split_tag(s[2:]))
            continue
        m = _LABEL.match(s)
        if not m:
            sec.extra.append(s)
            continue
        label, value = m.group(1).strip(), m.group(2).strip()
        if sec.number == 9 and label.startswith("Blueprint"):
            fmt = re.search(r"\(([^)]*)\)", label)
            sec.blueprint_format = fmt.group(1).strip() if fmt else ""
            in_blueprint = True
            if value:
                sec.blueprint.append(_split_blueprint_line(value))
            continue
        if value:
            sec.fields[label] = split_tag(value)
            current_list = None
        else:
            sec.lists[label] = []
            current_list = label


def _split_blueprint_line(line: str) -> dict[str, str]:
    """Split at the first ':' or ' | ', whichever comes first."""
    line = line[2:] if line.startswith("- ") else line
    cuts = [(i, w) for i, w in ((line.find(":"), 1), (line.find(" | "), 3)) if i >= 0]
    if not cuts:
        return {"label": line.strip(), "content": ""}
    i, width = min(cuts)
    return {"label": line[:i].strip(), "content": line[i + width:].strip()}


def _parse_questions(sec: Section, lines: list[str]) -> None:
    row: dict[str, str] | None = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        q = re.match(r"^(Q\d+):\s*(.*)$", s)
        if q:
            row = {"id": q.group(1), "question": split_tag(q.group(2))["text"], "metric": "", "timeframe": ""}
            sec.rows.append(row)
            continue
        m = _LABEL.match(s)
        if row is not None and m and m.group(1).strip() in ("Metric", "Timeframe"):
            row[m.group(1).strip().lower()] = split_tag(m.group(2))["text"]
        else:
            sec.extra.append(s)


def _parse_data_rows(sec: Section, lines: list[str]) -> None:
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"^\d+\.\s*(.*)$", s)
        if not m:
            sec.extra.append(s)
            continue
        row: dict = {}
        for part in m.group(1).split(" | "):
            kv = _LABEL.match(part.strip())
            if kv:
                row[_slug(kv.group(1))] = split_tag(kv.group(2))
            else:
                sec.extra.append(part.strip())
        sec.rows.append(row)


def _parse_open_questions(sec: Section, lines: list[str]) -> None:
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if not s.startswith("- "):
            sec.extra.append(s)
            continue
        parts = s[2:].split(" | ")
        row: dict = {"question": split_tag(parts[0]), "owner": split_tag(""), "needed_by": split_tag("")}
        for part in parts[1:]:
            kv = _LABEL.match(part.strip())
            if kv:
                row[_slug(kv.group(1))] = split_tag(kv.group(2))
            else:
                sec.extra.append(part.strip())
        sec.rows.append(row)
