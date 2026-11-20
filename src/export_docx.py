"""Export a parsed Brief to a consulting-style Word document (python-docx)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from src.brief_parser import Brief, Section

NAVY, RED, WHITE = RGBColor(0x1F, 0x3A, 0x5F), RGBColor(0xC0, 0x00, 0x00), RGBColor(0xFF, 0xFF, 0xFF)
LABEL_FILL, BOX_FILL = "E7ECF3", "EAF0F7"
DAGGER = "\u2020"
LEGEND = (f"{DAGGER} Suggested by the AI and not yet confirmed. "
          "Items without a dagger were stated by the author.")
META_FIELDS = ["Prepared for", "Prepared by", "Date", "Version", "Document status", "Confidence", "Approval status"]
SUMMARY_FIELDS = ["Situation", "Complication", "Question", "Recommended output", "Ask of the reader"]


def _style_font(style: Any, size: float, bold: bool | None = None, color: RGBColor | None = None) -> None:
    """Set Calibri on a style and drop the theme font attributes that would override it."""
    style.font.name = "Calibri"
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(attr), None)
    rfonts.set(qn("w:eastAsia"), "Calibri")


def _new_document() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
    _style_font(doc.styles["Normal"], 10.5)
    doc.styles["Normal"].paragraph_format.space_after = Pt(4)
    _style_font(doc.styles["Title"], 24, True, NAVY)
    _style_font(doc.styles["Heading 1"], 14, True, NAVY)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(14)
    doc.styles["Heading 1"].paragraph_format.space_after = Pt(4)
    _style_font(doc.styles["List Bullet"], 10.5)
    return doc


def _shade(cell: Any, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _add_tagged(paragraph: Any, value: Any, bold: bool = False, color: RGBColor | None = None) -> None:
    """Write a str or {'text','tag'} value; Suggested values are italic and end with a dagger."""
    text, tag = (value["text"], value["tag"]) if isinstance(value, dict) else (str(value), "")
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = tag == "Suggested"
    if color is not None:
        run.font.color.rgb = color
    if tag == "Suggested":
        paragraph.add_run(" " + DAGGER)


def _fill(cell: Any, value: Any, bold: bool = False, color: RGBColor | None = None) -> None:
    para = cell.paragraphs[0]
    para.paragraph_format.space_after = Pt(2)
    _add_tagged(para, value, bold, color)


def _table(doc: Document, header: list[str] | None, rows: list[list], widths: list[float],
           label_col: bool = False) -> Any:
    """Add a grid table. label_col shades and bolds the first column (for Label | Value tables)."""
    table = doc.add_table(rows=0, cols=len(widths))
    table.style = "Table Grid"
    table.autofit = False
    if header:
        cells = table.add_row().cells
        for cell, text in zip(cells, header):
            _shade(cell, "1F3A5F")
            _fill(cell, text, bold=True, color=WHITE)
    for row in rows:
        cells = table.add_row().cells
        for i, (cell, value) in enumerate(zip(cells, row)):
            _fill(cell, value, bold=label_col and i == 0)
            if label_col and i == 0:
                _shade(cell, LABEL_FILL)
    for col, width in zip(table.columns, widths):
        col.width = Inches(width)  # sets the grid column (LibreOffice and Word both read it)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = Inches(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def _add_page_field(paragraph: Any) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, end):
        run._r.append(el)


def _header_footer(doc: Document, is_draft: bool) -> None:
    section = doc.sections[0]
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("Prepared with Problem Framer AI  |  Page ")
    _add_page_field(footer)
    for run in footer.runs:
        run.font.size = Pt(9)
    if is_draft:
        head = section.header.paragraphs[0]
        head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = head.add_run("DRAFT - not yet approved")
        run.bold = True
        run.font.color.rgb = RED


def _title_block(doc: Document, brief: Brief, is_draft: bool) -> None:
    doc.add_paragraph(brief.title or "Business Requirements Brief", style="Title")
    if is_draft:
        p = doc.add_paragraph()
        run = p.add_run("DRAFT")
        run.bold, run.font.size, run.font.color.rgb = True, Pt(14), RED
    rows = [[k, brief.header[k]] for k in META_FIELDS if k in brief.header]
    _table(doc, None, rows, [1.8, 4.7], label_col=True)
    if brief.changes:
        p = doc.add_paragraph()
        p.add_run("Changes in this version: ").bold = True
        p.add_run(brief.changes)


def _summary_box(doc: Document, brief: Brief) -> None:
    doc.add_heading("Executive summary", level=1)
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    table.autofit = False
    table.columns[0].width = Inches(6.5)
    cell = table.rows[0].cells[0]
    cell.width = Inches(6.5)
    _shade(cell, BOX_FILL)
    first = True
    for label in SUMMARY_FIELDS + [k for k in brief.exec_summary if k not in SUMMARY_FIELDS]:
        if label not in brief.exec_summary:
            continue
        para = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        para.paragraph_format.space_after = Pt(3)
        para.add_run(f"{label}: ").bold = True
        para.add_run(brief.exec_summary[label])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def _bullets(doc: Document, items: list[dict]) -> None:
    for item in items:
        _add_tagged(doc.add_paragraph(style="List Bullet"), item)


def _label(doc: Document, text: str) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.keep_with_next = True
    para.add_run(text).bold = True


def _glossary(doc: Document, items: list[dict]) -> None:
    rows = []
    for item in items:
        term, sep, meaning = item["text"].partition(": ")
        rows.append([term, {"text": meaning, "tag": item["tag"]}] if sep else [item["text"], ""])
    if len(rows) == 1 and rows[0][1] == "" and rows[0][0].strip(". ").lower() == "none":
        doc.add_paragraph("None.")
        return
    _table(doc, ["Term", "Meaning"], rows, [1.8, 4.7])


def _generic(doc: Document, sec: Section) -> None:
    if sec.fields:
        _table(doc, None, [[k, v] for k, v in sec.fields.items()], [1.8, 4.7], label_col=True)
    for label, items in sec.lists.items():
        _label(doc, label)
        _glossary(doc, items) if label == "Glossary" else _bullets(doc, items)


def _section(doc: Document, sec: Section) -> None:
    doc.add_heading(f"{sec.number}. {sec.title.capitalize()}", level=1)
    if sec.number == 1 and sec.fields:
        for value in sec.fields.values():
            _add_tagged(doc.add_paragraph(), value)
    elif sec.number == 4:
        rows = [[r["id"], r["question"], r["metric"], r["timeframe"]] for r in sec.rows]
        _table(doc, ["ID", "Question", "Metric", "Timeframe"], rows, [0.5, 2.7, 2.0, 1.3])
    elif sec.number == 8:
        keys = ["data_element", "source", "owner", "granularity", "issues"]
        rows = [[r.get(k, "") for k in keys] for r in sec.rows]
        _table(doc, ["Data element", "Source", "Owner", "Granularity", "Issues"], rows, [1.6, 1.3, 1.1, 1.0, 1.5])
    elif sec.number == 10:
        rows = [[r["question"], r["owner"], r["needed_by"]] for r in sec.rows]
        _table(doc, ["Question or decision", "Owner", "Needed by"], rows, [3.4, 1.7, 1.4])
    else:
        _generic(doc, sec)
    if sec.number == 9 and sec.blueprint:
        _label(doc, f"Blueprint ({sec.blueprint_format})" if sec.blueprint_format else "Blueprint")
        _table(doc, ["Item", "Content"], [[b["label"], b["content"]] for b in sec.blueprint], [1.8, 4.7])
    for line in sec.extra:
        doc.add_paragraph(line)


def _closing(doc: Document) -> None:
    para = doc.add_paragraph()
    run = para.add_run(LEGEND)
    run.italic, run.font.size = True, Pt(9)
    doc.add_heading("Sign-off", level=1)
    rows = [["Prepared by", "", "", ""], ["Reviewed by", "", "", ""], ["Approved by (Decision authority)", "", "", ""]]
    _table(doc, ["Role", "Name", "Date", "Signature"], rows, [2.2, 1.7, 1.0, 1.6])


def brief_to_docx(brief: Brief) -> bytes:
    """Return the brief as an in-memory .docx file."""
    is_draft = brief.header.get("Document status", "").strip() == "Draft"
    doc = _new_document()
    doc.core_properties.title = brief.title
    doc.core_properties.author = "Problem Framer AI"
    _header_footer(doc, is_draft)
    _title_block(doc, brief, is_draft)
    _summary_box(doc, brief)
    for number in sorted(brief.sections):
        _section(doc, brief.sections[number])
    _closing(doc)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
