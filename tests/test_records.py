import datetime as dt

import openpyxl
import pytest

from daisywriter.issues import Level
from daisywriter.records import load_records, normalize, sheet_names
from daisywriter.samples import make_data


def test_sample_data(sample_dir):
    ds = load_records(sample_dir / "letter-data.xlsx")
    assert ds.sheet == "Customers" and len(ds.records) == 5
    first = ds.records[0]
    assert first.row == 2 and first.values["FirstName"] == "Eleanor"
    assert isinstance(first.values["OrderDate"], dt.datetime)
    assert first.values["Zip"] == "62704"
    assert not [i for i in ds.issues if i.level > Level.INFO]


def test_header_matching():
    assert normalize("First Name") == normalize("first_name") == normalize("FirstName")


def test_lookup_and_suggest(sample_dir):
    ds = load_records(sample_dir / "letter-data.xlsx")
    assert ds.header_for("first_name") == "FirstName"
    assert ds.header_for("Frist") is None
    assert ds.suggest("FristName") == "FirstName"


def test_problem_spreadsheet(tmp_path):
    path = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Zip", "name", None, "Total"])
    ws.append(["Ann", 2134, "dup", "orphan data", "=1+1"])  # formula without a saved result
    ws.append([None, None, None, None, None])
    ws.append(["Bob", "02134", None, None, 5])
    wb.save(str(path))
    ds = load_records(path)
    msgs = [(i.level, i.message) for i in ds.issues]
    assert len(ds.records) == 2  # the empty row is skipped
    assert any(lvl is Level.ERROR and "same name" in m for lvl, m in msgs)
    assert any(lvl is Level.WARNING and "column D has data but no header" in m for lvl, m in msgs)
    assert any(lvl is Level.ERROR and "E2 has a formula" in m for lvl, m in msgs)
    assert any(lvl is Level.WARNING and "ZIP 2134" in m for lvl, m in msgs)


def test_sheet_selection(tmp_path):
    path = make_data(tmp_path / "d.xlsx")
    assert sheet_names(path) == ["Customers"]
    with pytest.raises(ValueError, match="no sheet named"):
        load_records(path, "Nope")


def test_headers_only(tmp_path):
    ds = load_records(make_data(tmp_path / "d.xlsx", rows=[]))
    assert any("no data rows" in i.message for i in ds.issues)
