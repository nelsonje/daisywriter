"""The window, driven with pytest-qt against the fake transport and the emulator.

Dialogs are replaced: confirm() answers from a script and records the
questions, inform() records messages, choose_pdf() returns a path.
"""
import shutil

import docx
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction

from daisywriter.gui import main_window as mw
from daisywriter.gui.main_window import COL_CHECK, COL_STATUS, EMULATOR, MainWindow
from daisywriter.session import PRINTED, Session
from daisywriter.transports.fake import FakeTransport


@pytest.fixture
def files(sample_dir, tmp_path):
    for name in ("letter-template.docx", "letter-data.xlsx"):
        shutil.copy(sample_dir / name, tmp_path / name)
    return tmp_path / "letter-template.docx", tmp_path / "letter-data.xlsx"


class Dialogs:
    def __init__(self, answers=None):
        self.answers = answers or {}  # title -> True/False (default True)
        self.asked, self.told = [], []

    def confirm(self, title, text, yes="Continue", no="Cancel"):
        self.asked.append((title, text))
        return self.answers.get(title, True)

    def inform(self, title, text, warning=False):
        self.told.append((title, text))


def open_window(qtbot, tmp_path, template, data, dialogs=None):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    store.setValue("template", str(template))
    store.setValue("data", str(data))
    w = MainWindow(store)
    qtbot.addWidget(w)
    d = dialogs or Dialogs()
    w.confirm, w.inform = d.confirm, d.inform
    w.open_file = lambda path: None
    return w, d


def checked(w):
    return [r + 1 for r in range(w.table.rowCount())
            if w.table.item(r, COL_CHECK).checkState() == Qt.CheckState.Checked]


def check_only(w, numbers):
    w.check_where(lambda st: False)
    for n in numbers:
        w.table.item(n - 1, COL_CHECK).setCheckState(Qt.CheckState.Checked)


def status(w, n):
    return w.table.item(n - 1, COL_STATUS).text()


@pytest.fixture
def fake(monkeypatch):
    t = FakeTransport()
    monkeypatch.setattr(mw, "open_transport", lambda profile, dry_run=None: t)
    return t


def print_and_wait(qtbot, w):
    w.print_button.click()
    qtbot.waitUntil(lambda: w.worker is None, timeout=10000)


def test_loads_letters_issues_and_preview(qtbot, tmp_path, files):
    w, _ = open_window(qtbot, tmp_path, *files)
    assert w.table.rowCount() == 5
    assert w.profile_combo.currentData() == "swintec-1146cmp"
    assert checked(w) == [1, 2, 3, 4, 5]  # nothing printed yet
    assert w.sheet_combo.currentText() == "Customers"
    assert w.selected_letter().number == 1
    sheets = w.preview.view.sheets
    assert len(sheets) == 1 and len(sheets[0].strikes) > 500
    assert w.preview.view.body_rows[0]  # the body is shaded
    assert w.issues.topLevelItemCount() > 0


def test_issue_click_selects_its_letter(qtbot, tmp_path, files):
    w, _ = open_window(qtbot, tmp_path, *files)
    item = next(w.issues.topLevelItem(i) for i in range(w.issues.topLevelItemCount())
                if w.issues.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) == 2)
    w._issue_clicked(item)
    assert w.selected_letter().number == 2


def test_print_checked_letters(qtbot, tmp_path, files, fake):
    w, d = open_window(qtbot, tmp_path, *files)
    check_only(w, [1, 3])
    print_and_wait(qtbot, w)
    assert [t for t, _ in d.asked] == ["Paper", "Paper"]  # one prompt per sheet
    assert "letter 1, page 1" in d.asked[0][1] and "letter 3, page 1" in d.asked[1][1]
    assert status(w, 1).startswith("printed") and status(w, 3).startswith("printed")
    assert status(w, 2) == "not printed"
    assert checked(w) == []  # printed letters are unchecked
    assert fake.closed and b"Dear" in fake.data
    saved = Session.load(files[1])
    assert sorted(s.status for s in saved.letters.values()) == [PRINTED, PRINTED]

    # a new window remembers, and offers the rest
    w2, _ = open_window(qtbot, tmp_path, *files)
    assert status(w2, 1).startswith("printed") and checked(w2) == [2, 4, 5]


def test_reprint_asks_first(qtbot, tmp_path, files, fake):
    w, d = open_window(qtbot, tmp_path, *files, Dialogs({"Print again?": False}))
    check_only(w, [2])
    print_and_wait(qtbot, w)
    check_only(w, [2])
    w.print_button.click()
    assert d.asked[-1][0] == "Print again?" and w.worker is None


def test_stop_at_the_paper_prompt(qtbot, tmp_path, files, fake):
    w, _ = open_window(qtbot, tmp_path, *files, Dialogs({"Paper": False}))
    check_only(w, [1, 2])
    print_and_wait(qtbot, w)
    assert status(w, 1) == "not printed" and fake.data == b"\x18"  # only CAN
    assert "0 of 2 letters printed. Stopped." in w.statusBar().currentMessage()


def test_failure_is_recorded(qtbot, tmp_path, files, fake):
    fake.fail_after = 5
    w, d = open_window(qtbot, tmp_path, *files)
    check_only(w, [1, 2])
    print_and_wait(qtbot, w)
    assert status(w, 1).startswith("failed") and status(w, 2) == "not printed"
    assert "simulated timeout" in w.table.item(0, COL_STATUS).toolTip()
    assert d.told and "failed" in d.told[-1][1]


def test_errors_block_printing(qtbot, tmp_path, files, fake):
    template = tmp_path / "bad.docx"
    doc = docx.Document()
    doc.add_paragraph("Dear {{NoSuchColumn}},")
    doc.save(str(template))
    w, d = open_window(qtbot, tmp_path, template, files[1])
    w.print_button.click()
    assert w.worker is None and d.told[-1][0] == "Can't print"


def test_print_on_the_emulator(qtbot, tmp_path, files):
    w, d = open_window(qtbot, tmp_path, *files, Dialogs({"Emulator": False}))
    pdf = tmp_path / "out.pdf"
    w.choose_pdf = lambda: pdf
    w.target.setCurrentIndex(w.target.findData(EMULATOR))
    check_only(w, [2])
    print_and_wait(qtbot, w)
    assert pdf.read_bytes().startswith(b"%PDF")
    assert d.asked[-1][0] == "Emulator" and "No problems found" in d.asked[-1][1]
    assert not any(t == "Paper" for t, _ in d.asked)  # no paper prompts on the emulator
    assert status(w, 2).startswith("printed")


def test_reload_after_the_data_changes(qtbot, tmp_path, files):
    w, _ = open_window(qtbot, tmp_path, *files)
    import openpyxl
    wb = openpyxl.load_workbook(files[1])
    wb.active.delete_rows(3)
    wb.save(files[1])
    w.reload()
    assert w.table.rowCount() == 4


def test_missing_files_are_reported(qtbot, tmp_path):
    w, _ = open_window(qtbot, tmp_path, tmp_path / "nope.docx", tmp_path / "nope.xlsx")
    assert w.table.rowCount() == 0
    assert "not found" in w.issues.topLevelItem(0).text(2)


def test_menus_quit_and_print(qtbot, tmp_path, files, fake):
    w, _ = open_window(qtbot, tmp_path, *files)
    w.show()
    assert w.quit_action.menuRole() == QAction.MenuRole.QuitRole
    assert not w.quit_action.shortcut().isEmpty()
    check_only(w, [1])
    w.print_action.trigger()
    assert not w.print_action.isEnabled() and w.stop_action.isEnabled()
    qtbot.waitUntil(lambda: w.worker is None, timeout=10000)
    assert w.print_action.isEnabled() and not w.stop_action.isEnabled()
    w.quit_action.trigger()
    assert not w.isVisible()


def test_quit_button_asks_while_printing(qtbot, tmp_path, files, fake):
    w, d = open_window(qtbot, tmp_path, *files, Dialogs({"Printing": False}))
    w.show()
    prompts = []
    w._answer_prompt = prompts.append  # leave the paper prompt open: the job waits
    check_only(w, [1])
    w.print_button.click()
    qtbot.waitUntil(lambda: bool(prompts), timeout=5000)
    w.quit_button.click()  # answered "Keep printing"
    assert w.isVisible() and d.asked[-1][0] == "Printing"
    w.worker.answer(True)
    qtbot.waitUntil(lambda: w.worker is None, timeout=10000)
    assert status(w, 1).startswith("printed")
    w.quit_button.click()
    assert not w.isVisible()


def test_typing_errors_and_new_errors(qtbot, tmp_path, files):
    w, _ = open_window(qtbot, tmp_path, *files)
    assert not w.errors_box.isChecked() and not w.reroll_button.isEnabled()
    assert not any(x.typing_errors for x in w.merge.letters)
    check_only(w, [2, 4])
    w.error_rate.setValue(10)
    w.errors_box.setChecked(True)  # reloads with errors
    assert w.reroll_button.isEnabled()
    assert all(x.typing_errors for x in w.merge.letters)
    assert checked(w) == [2, 4]  # the user's checks survive the reload
    w.table.selectRow(1)
    letter = w.selected_letter()
    assert any(c.over for page in letter.pages for line in page.lines for c in line.cells)

    before = [x.paragraphs for x in w.merge.letters]
    w.reroll_button.click()  # the selected letter (2) only
    after = [x.paragraphs for x in w.merge.letters]
    assert after[1] != before[1] and after[0] == before[0] and after[2:] == before[2:]
    assert w.selected_letter().number == 2

    w.reroll_all_action.trigger()
    assert all(a != b for a, b in zip(after, [x.paragraphs for x in w.merge.letters], strict=True))

    # the choices and the re-rolls come back in a new window
    again = [x.paragraphs for x in w.merge.letters]
    w.close()
    w2, _ = open_window(qtbot, tmp_path, *files)
    assert w2.errors_box.isChecked() and w2.error_rate.value() == 10
    assert [x.paragraphs for x in w2.merge.letters] == again


def test_header_checkbox(qtbot, tmp_path, files):
    from PySide6.QtCore import QPoint
    w, _ = open_window(qtbot, tmp_path, *files)
    w.show()
    header = w.check_header

    def click():
        x = header.sectionViewportPosition(COL_CHECK) + header.sectionSize(COL_CHECK) // 2
        qtbot.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, header.height() // 2))

    assert header.state == Qt.CheckState.Checked and checked(w) == [1, 2, 3, 4, 5]
    click()  # all checked: uncheck all
    assert header.state == Qt.CheckState.Unchecked and checked(w) == []
    w.table.item(2, COL_CHECK).setCheckState(Qt.CheckState.Checked)  # the user checks one
    assert header.state == Qt.CheckState.PartiallyChecked
    click()  # some checked: check all
    assert header.state == Qt.CheckState.Checked and checked(w) == [1, 2, 3, 4, 5]
    click()
    click()  # none checked: check all
    assert checked(w) == [1, 2, 3, 4, 5]
    w.table.item(0, COL_CHECK).setCheckState(Qt.CheckState.Unchecked)
    assert header.state == Qt.CheckState.PartiallyChecked
