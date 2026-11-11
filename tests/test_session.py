import dataclasses

from daisywriter.layout import Cell, Line, Page
from daisywriter.merge import Letter
from daisywriter.records import Record
from daisywriter.session import FAILED, NOT_PRINTED, PRINTED, Session, session_path


def letter(row=2, values=None, text="x"):
    return Letter(row - 1, Record(row, values or {"Name": "Ann"}), [],
                  pages=[Page(1, [Line([Cell(ch) for ch in text])])])


def test_round_trip_and_matching(tmp_path):
    data = tmp_path / "clients.xlsx"
    assert session_path(data) == tmp_path / "clients.daisywriter.json"
    s = Session.load(data)
    s.mark("t.docx", letter(), PRINTED)
    s.mark("t.docx", letter(3, {"Name": "Bob"}), FAILED, "simulated timeout")

    again = Session.load(data)
    assert again.state("t.docx", letter()).status == PRINTED
    assert again.state("t.docx", letter(3, {"Name": "Bob"})).message == "simulated timeout"
    # another template, or an edited row, is a different letter
    assert again.state("other.docx", letter()).status == NOT_PRINTED
    assert again.state("t.docx", letter(values={"Name": "Anne"})).status == NOT_PRINTED


def test_changed_since_printing(tmp_path):
    s = Session.load(tmp_path / "d.xlsx")
    st = s.mark("t.docx", letter(text="hello"), PRINTED)
    assert not st.changed_since(letter(text="hello"))
    assert st.changed_since(letter(text="hullo"))
    bold = letter(text="hello")
    bold.pages[0].lines[0].cells[0] = dataclasses.replace(bold.pages[0].lines[0].cells[0], bold=True)
    assert st.changed_since(bold)


def test_unreadable_file_starts_fresh(tmp_path):
    session_path(tmp_path / "d.xlsx").write_text("{not json", encoding="utf-8")
    s = Session.load(tmp_path / "d.xlsx")
    assert s.letters == {} and "couldn't read" in s.problem
    s.mark("t.docx", letter(), PRINTED)  # and saving replaces it
    assert Session.load(tmp_path / "d.xlsx").problem == ""
