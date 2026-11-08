"""Generate prototype templates and spreadsheets for development and tests.

The template exercises the features daisywriter reads: real Word MERGEFIELDs
(complex and simple), typed {{placeholders}} (one split across formatting
runs), a DATE field, bold and underline, justification, indents, a tab stop,
a manual line break, and a page header that is ignored.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import docx
import openpyxl
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

HEADERS = ["FirstName", "LastName", "Company", "Address1", "Address2", "City", "State", "Zip",
           "OrderNumber", "Product", "OrderDate", "Amount"]

RECORDS = [
    ["Eleanor", "Whitfield", "Whitfield & Daughters Stationery", "1427 Maple Avenue", "Suite 200",
     "Springfield", "IL", "62704", "A-10233", "Smith-Corona Galaxie 12", dt.date(2026, 10, 14), 89.5],
    ["Thomas", "O'Brien", None, "88 Harbor Road", None, "Gloucester", "MA", "01930", "A-10241",
     "Olympia SM9", dt.date(2026, 10, 20), 125],
    ["José", "Álvarez", "Álvarez Translation Services", "310 Cedar Street", "Apt 4B", "Santa Fe",
     "NM", "87501", "A-10252", "Hermes 3000", dt.date(2026, 10, 27), 148.75],
    ["Priya", "Raman", "Raman Consulting LLC", "5 Elm Court", None, "Ann Arbor", "MI", "48104",
     "A-10259", "IBM Selectric II", dt.date(2026, 11, 2), 210.0],
    ["Walter", "Kowalczyk", "The Kowalczyk Family Trust for Historic Office Machines",
     "742 Evergreen Terrace", None, "Portland", "OR", "97201", "A-10260",
     "Brother Correctronic 50", dt.date(2026, 11, 3), 64.25],
]


# ---------------------------------------------------------------- docx helpers

def _run(bold=False, underline=False):
    r = OxmlElement("w:r")
    if bold or underline:
        rpr = OxmlElement("w:rPr")
        if bold:
            rpr.append(OxmlElement("w:b"))
        if underline:
            u = OxmlElement("w:u")
            u.set(qn("w:val"), "single")
            rpr.append(u)
        r.append(rpr)
    return r


def _text_el(tag, text):
    t = OxmlElement(tag)
    t.text = text
    t.set(qn("xml:space"), "preserve")
    return t


def add_field(paragraph, instr: str, result: str, bold=False, underline=False):
    """Insert a complex field (fldChar begin / instrText / separate / result / end)."""
    p = paragraph._p
    for kind, payload in (("begin", None), ("instr", instr), ("separate", None),
                          ("result", result), ("end", None)):
        r = _run(bold, underline)
        if kind == "instr":
            r.append(_text_el("w:instrText", f" {payload} "))
        elif kind == "result":
            r.append(_text_el("w:t", payload))
        else:
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r.append(fc)
        p.append(r)


def add_simple_field(paragraph, instr: str, result: str):
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), f" {instr} ")
    r = _run()
    r.append(_text_el("w:t", result))
    fld.append(r)
    paragraph._p.append(fld)


def add_mergefield(paragraph, name: str, **kw):
    add_field(paragraph, f"MERGEFIELD {name} \\* MERGEFORMAT", f"«{name}»", **kw)


def add_break(paragraph):
    r = paragraph.add_run()
    r._r.append(OxmlElement("w:br"))


def make_template(path: str | Path, markers: bool = False) -> Path:
    """A block-style business letter."""
    path = Path(path)
    d = docx.Document()
    normal = d.styles["Normal"]
    normal.font.name = "Courier New"
    normal.font.size = Pt(12)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)
    for section in d.sections:
        section.left_margin = section.right_margin = Inches(1)
        section.header.paragraphs[0].text = "HOLLIS TYPEWRITER REPAIR · 19 Platen Lane · Ames, Iowa"

    def para(text="", align=None):
        p = d.add_paragraph(text)
        if align is not None:
            p.alignment = align
        return p

    add_field(para(), 'DATE \\@ "MMMM d, yyyy"', "November 8, 2026")
    para()
    p = para()
    add_mergefield(p, "FirstName")
    p.add_run(" ")
    add_mergefield(p, "LastName")
    add_simple_field(para(), "MERGEFIELD Company", "«Company»")
    add_mergefield(para(), "Address1")
    add_mergefield(para(), "Address2")
    p = para()
    add_mergefield(p, "City")
    p.add_run(", ")
    add_mergefield(p, "State")
    p.add_run("  ")
    add_mergefield(p, "Zip")
    para()
    p = para()
    p.add_run("Re:").bold = True
    p.add_run(" Your order {{OrderNumber}}")
    para()
    p = para()
    p.add_run("Dear {{First")  # Word often splits typed text like this
    p.add_run("Name}},")
    para()
    if markers:
        para("{{body}}")

    body = []
    p = para("Thank you for ordering the {{Product}} on {{OrderDate:MMMM d}}. We are pleased "
             "to tell you that the machine has been inspected, cleaned, and adjusted in our shop, "
             "and that it left here today by parcel post.", WD_ALIGN_PARAGRAPH.JUSTIFY)
    body.append(p)
    p = para("Your invoice total is {{Amount}}. Please note that the machine comes "
             "with a ")
    p.add_run("fabric").bold = True
    p.add_run(" ribbon; carbon film ribbons are ")
    p.add_run("not").underline = True
    p.add_run(" compatible with this model.")
    body.append(p)
    p = para("“A typewriter that is cleaned once a year will outlast its owner.” "
             "— our founder, 1952")
    p.paragraph_format.left_indent = Inches(0.5)
    p.paragraph_format.right_indent = Inches(0.5)
    body.append(p)
    p = para("Order number:\t{{OrderNumber}}")
    p.paragraph_format.tab_stops.add_tab_stop(Inches(1.5))
    add_break(p)
    p.add_run("Shipped:\t{{Today}}")
    body.append(p)
    p = para("If you have any questions, please write to us at the address above. We hope you "
             "enjoy many years of happy typing.")
    body.append(p)
    for p in body:
        p.paragraph_format.space_after = Pt(12)

    if markers:
        para("{{/body}}")
    para("Sincerely,")
    para()
    para()
    para()
    p = para("Margaret Hollis")
    add_break(p)
    p.add_run("Service Manager")
    para()
    para("Enc.")
    d.save(str(path))
    return path


def make_data(path: str | Path, rows=None, headers=None) -> Path:
    path = Path(path)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Customers"
    ws.append(headers or HEADERS)
    for row in rows if rows is not None else RECORDS:
        ws.append(row)
    for col, header in enumerate(headers or HEADERS, start=1):
        letter = openpyxl.utils.get_column_letter(col)
        ws.column_dimensions[letter].width = 18
        if header == "Zip":
            for cell in ws[letter][1:]:
                cell.number_format = "@"
        if header == "OrderDate":
            for cell in ws[letter][1:]:
                cell.number_format = "m/d/yyyy"
        if header == "Amount":
            for cell in ws[letter][1:]:
                cell.number_format = '"$"#,##0.00'
    wb.save(str(path))
    return path


def make_samples(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return [make_template(directory / "letter-template.docx"),
            make_template(directory / "letter-template-markers.docx", markers=True),
            make_data(directory / "letter-data.xlsx")]
