"""Read merge records from an Excel (.xlsx) workbook. The first row holds the headers."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from . import issues as I
from .excelfmt import format_excel

ZIP_HEADER = re.compile(r"^(zip|zipcode|postal|postalcode|postcode|zip\+4)$")


def normalize(name: str) -> str:
    """Header/field matching ignores case, spaces and underscores.

    Word turns a "First Name" column into a FirstName or First_Name merge field,
    so all three spellings must match.
    """
    return re.sub(r"[\s_]+", "", name).casefold()


@dataclass
class Record:
    row: int  # Excel row number
    values: dict[str, object]  # header -> raw cell value
    formats: dict[str, str] = field(default_factory=dict)  # header -> Excel number format


@dataclass
class DataSet:
    path: str
    sheet: str
    headers: list[str]
    records: list[Record]
    issues: list[I.Issue] = field(default_factory=list)

    def header_for(self, name: str) -> str | None:
        key = normalize(name)
        for h in self.headers:
            if normalize(h) == key:
                return h
        return None

    def suggest(self, name: str) -> str | None:
        by_norm = {normalize(h): h for h in self.headers}
        close = difflib.get_close_matches(normalize(name), list(by_norm), n=1, cutoff=0.6)
        return by_norm[close[0]] if close else None


def sheet_names(path: str | Path) -> list[str]:
    wb = openpyxl.load_workbook(str(path), read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def load_records(path: str | Path, sheet: str | None = None) -> DataSet:
    path = Path(path)
    try:
        values_wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        formulas_wb = openpyxl.load_workbook(str(path), read_only=True, data_only=False)
    except Exception as e:  # openpyxl raises several types for bad files
        raise ValueError(f"{path.name} isn't a readable Excel .xlsx file ({e})") from e
    try:
        if sheet is not None and sheet not in values_wb.sheetnames:
            raise ValueError(f"{path.name} has no sheet named {sheet!r} "
                             f"(sheets: {', '.join(values_wb.sheetnames)})")
        name = sheet or values_wb.sheetnames[0]
        cells = [[(c.value, getattr(c, "number_format", None)) for c in row]
                 for row in values_wb[name].iter_rows()]
        formula_rows = list(formulas_wb[name].iter_rows(values_only=True))
    finally:
        values_wb.close()
        formulas_wb.close()
    rows = [[v for v, _ in row] for row in cells]
    formats = [[f for _, f in row] for row in cells]
    return _build(str(path), name, rows, formula_rows, formats)


def _build(path, sheet, rows, formula_rows, formats=None) -> DataSet:
    issues: list[I.Issue] = []
    if not rows:
        return DataSet(path, sheet, [], [], [I.error(f"sheet {sheet!r} is empty", "data")])

    header_row = rows[0]
    columns: list[tuple[int, str]] = []  # (column index, header)
    seen: dict[str, str] = {}
    for c, h in enumerate(header_row):
        text = str(h).strip() if h is not None else ""
        col = get_column_letter(c + 1)
        if not text:
            if any(c < len(r) and r[c] not in (None, "") for r in rows[1:]):
                issues.append(I.warning(f"column {col} has data but no header, so it's ignored",
                                        "data"))
            continue
        key = normalize(text)
        if key in seen:
            issues.append(I.error(f"headers \"{seen[key]}\" and \"{text}\" (column {col}) "
                                  "are the same name", "data"))
            continue
        seen[key] = text
        columns.append((c, text))
    if not columns:
        issues.append(I.error("the first row has no headers", "data"))

    records = []
    for r, row in enumerate(rows[1:], start=2):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in row):
            continue
        values, fmts = {}, {}
        frow_fmt = formats[r - 1] if formats and r - 1 < len(formats) else ()
        for c, h in columns:
            v = row[c] if c < len(row) else None
            fmt = frow_fmt[c] if c < len(frow_fmt) else None
            if fmt and fmt != "General":
                fmts[h] = fmt
            if v is None:
                frow = formula_rows[r - 1] if r - 1 < len(formula_rows) else ()
                f = frow[c] if c < len(frow) else None
                if isinstance(f, str) and f.startswith("="):
                    issues.append(I.error(
                        f"cell {get_column_letter(c + 1)}{r} has a formula with no saved result; "
                        "open the file in Excel and save it", "data"))
            shown = format_excel(v, fmt) or ""
            if isinstance(v, (int, float)) and not isinstance(v, bool) and ZIP_HEADER.match(
                    normalize(h)) and 0 <= v < 10000 and len(shown) < 5:
                issues.append(I.warning(
                    f"cell {get_column_letter(c + 1)}{r}: ZIP {int(v)} is stored as a number, so a "
                    "leading zero may be lost; give the column Excel's Special > Zip Code format",
                    "data"))
            values[h] = v
        records.append(Record(r, values, fmts))
    if not records and columns:
        issues.append(I.error("there are no data rows under the headers", "data"))
    return DataSet(path, sheet, [h for _, h in columns], records, issues)
