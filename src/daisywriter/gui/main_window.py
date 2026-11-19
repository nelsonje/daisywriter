"""The daisywriter window: pick a template and data, review letters, print them.

Top: the template, data file, worksheet, typewriter and merge settings.
Left: one row per letter, with a checkbox, page count, issues and print status.
Right: the selected letter's sheets as the typewriter will type them.
Bottom: validation issues (click one to see its letter) and the print controls.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import shutil
import sys
import tempfile
import zipfile
from importlib import metadata, resources
from pathlib import Path

from PySide6.QtCore import QDate, QFileSystemWatcher, QSettings, QStandardPaths, Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import issues as I
from ..errors import ErrorSettings
from ..job import PrintOptions
from ..layout import LayoutSettings, PageNumbers
from ..merge import Letter, MergeSettings
from ..pipeline import Merge, Settings, run
from ..profile import DEFAULT_PROFILE, builtin_profiles
from ..session import FAILED, NOT_PRINTED, PRINTED, PRINTING, Session
from ..transports import TransportError, open_transport
from ..transports.emulator import Emulator, emulate
from .check_header import CheckHeader
from .sheet_view import PreviewArea
from .worker import STOPPED_PART_WAY, PrintWorker

TYPEWRITER, EMULATOR = "typewriter", "emulator"


def app_icon() -> QIcon:
    """The daisywheel icon (packaging/make_icon.py draws it)."""
    icon = QIcon()
    icons = resources.files("daisywriter.gui") / "icons"
    for size in (16, 32, 48, 256):
        with resources.as_file(icons / f"daisywriter-{size}.png") as path:
            icon.addFile(str(path))
    return icon
COL_CHECK, COL_NUM, COL_WHO, COL_PAGES, COL_ISSUES, COL_STATUS = range(6)
LEVEL_COLORS = {I.Level.ERROR: QColor("#c62828"), I.Level.WARNING: QColor("#b26a00"),
                I.Level.INFO: QColor("#555555")}
STATUS_COLORS = {PRINTED: QColor("#2e7d32"), FAILED: QColor("#c62828"), PRINTING: QColor("#1565c0")}


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.setWindowTitle("daisywriter")
        self.setWindowIcon(app_icon())
        self.store = settings or QSettings("daisywriter", "daisywriter")
        self.merge: Merge | None = None
        self.session: Session | None = None
        self.load_error = ""
        self.thread: QThread | None = None
        self.worker: PrintWorker | None = None
        self.emulator_pdf: Path | None = None
        self._build()
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed)
        self._reload_timer = QTimer(self, singleShot=True, interval=500, timeout=self.reload)
        self._restore()

    # Layout

    def _build(self):
        files = QGridLayout()
        self.template_edit, self.data_edit = QLineEdit(), QLineEdit()
        for row, (label, edit, kind) in enumerate([("Template", self.template_edit, "Word (*.docx)"),
                                                   ("Data", self.data_edit, "Excel (*.xlsx)")]):
            edit.setPlaceholderText(f"choose a {kind.split()[0]} file")
            edit.editingFinished.connect(self.reload)
            browse = QPushButton("Browse…")
            browse.clicked.connect(lambda _=False, e=edit, k=kind: self._browse(e, k))
            files.addWidget(QLabel(label), row, 0)
            files.addWidget(edit, row, 1)
            files.addWidget(browse, row, 2)
        self.sheet_combo = QComboBox()
        self.sheet_combo.setToolTip("worksheet with the records (first row = column names)")
        self.sheet_combo.activated.connect(lambda _: self.reload())
        files.addWidget(QLabel("Sheet"), 1, 3)
        files.addWidget(self.sheet_combo, 1, 4)
        self.profile_combo = QComboBox()
        for pid, prof in builtin_profiles().items():
            self.profile_combo.addItem(prof.name, pid)
        self.profile_combo.activated.connect(lambda _: self.reload())
        files.addWidget(QLabel("Typewriter"), 0, 3)
        files.addWidget(self.profile_combo, 0, 4)
        files.setColumnStretch(1, 1)

        options = QHBoxLayout()
        self.today_edit = QDateEdit(QDate.currentDate(), calendarPopup=True)
        self.today_edit.setDisplayFormat("MMMM d, yyyy")
        self.today_edit.setToolTip("the date typed for {{Today}} and Word DATE fields")
        self.today_edit.dateChanged.connect(lambda _: self.reload())
        self.page_numbers = QComboBox()
        for label, mode in [("No page numbers", "off"), ("Page numbers after page 1", "after_first"),
                            ("Page numbers on every page", "all")]:
            self.page_numbers.addItem(label, mode)
        self.page_numbers.activated.connect(lambda _: self.reload())
        self.justify = QCheckBox("Justify paragraphs Word justifies", checked=True)
        self.justify.toggled.connect(lambda _: self.reload())
        reload_button = QPushButton("Reload")
        reload_button.setToolTip("read the template and data again (F5)")
        reload_button.clicked.connect(self.reload)
        for w in (QLabel("Date"), self.today_edit, self.page_numbers, self.justify):
            options.addWidget(w)
        options.addSpacing(16)
        self.errors_box = QCheckBox("Typing errors")
        self.errors_box.setToolTip("add typing errors with strikeover corrections to the letter body, "
                                   "never in merged values; the same ones each time you print")
        self.error_rate = QDoubleSpinBox(decimals=1, minimum=0.5, maximum=10, singleStep=0.5, value=1.0)
        self.error_rate.setSuffix(" per 100 words")
        self.error_style = QComboBox()
        for label, style in [("x-outs and overstrikes", "mix"), ("x-outs only", "xout"),
                             ("overstrikes where possible", "overstrike")]:
            self.error_style.addItem(label, style)
        self.reroll_button = QPushButton("New errors")
        self.reroll_button.setToolTip("different typing errors for the selected letter")
        self.reroll_button.clicked.connect(lambda: self.reroll(all_letters=False))
        self.errors_box.toggled.connect(self._errors_changed)
        self.error_rate.editingFinished.connect(self._errors_changed)
        self.error_style.activated.connect(lambda _: self._errors_changed())
        for w in (self.errors_box, self.error_rate, self.error_style, self.reroll_button):
            options.addWidget(w)
        options.addStretch(1)
        options.addWidget(reload_button)

        self.table = QTableWidget(0, 6)
        self.check_header = CheckHeader(COL_CHECK, self.table)
        self.check_header.setToolTip("check or uncheck every letter")
        self.check_header.clicked_check.connect(self._toggle_all)
        self.table.setHorizontalHeader(self.check_header)
        self.table.setHorizontalHeaderLabels(["", "#", "Letter", "Pages", "Issues", "Status"])
        self.table.itemChanged.connect(self._item_changed)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_WHO, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(COL_CHECK, self.check_header.indicator_width() + 16)
        self.table.itemSelectionChanged.connect(self._show_selected)

        checks = QHBoxLayout()
        not_printed = QPushButton("Check not printed")
        not_printed.setToolTip("check the letters that haven't been printed, and uncheck the rest")
        not_printed.clicked.connect(lambda: self.check_where(lambda st: st != PRINTED))
        checks.addWidget(not_printed)
        checks.addStretch(1)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.table)
        lv.addLayout(checks)

        self.preview = PreviewArea()
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(self.preview)
        split.setSizes([480, 720])

        self.issues = QTreeWidget()
        self.issues.setHeaderLabels(["", "Where", "Problem"])
        self.issues.setRootIsDecorated(False)
        self.issues.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.issues.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.issues.itemClicked.connect(self._issue_clicked)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.addWidget(split)
        vsplit.addWidget(self.issues)
        vsplit.setSizes([600, 140])

        bottom = QHBoxLayout()
        self.target = QComboBox()
        self.target.addItem("Print on the typewriter", TYPEWRITER)
        self.target.addItem("Print on the emulator (PDF)", EMULATOR)
        self.status_button = QPushButton("Check typewriter")
        self.status_button.clicked.connect(self.check_typewriter)
        self.status_label = QLabel("")
        self.print_button = QPushButton("Print checked letters")
        self.print_button.setDefault(True)
        self.print_button.clicked.connect(self.print_checked)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip("stop when the line being typed is finished")
        self.stop_button.clicked.connect(self.stop_printing)
        for w in (self.status_button, self.status_label):
            bottom.addWidget(w)
        bottom.addStretch(1)
        for w in (self.target, self.print_button, self.stop_button):
            bottom.addWidget(w)
        bottom.addSpacing(24)
        self.quit_button = QPushButton("Exit" if sys.platform == "win32" else "Quit")
        self.quit_button.setToolTip("close daisywriter (asks first if letters are printing)")
        self.quit_button.clicked.connect(self.close)
        bottom.addWidget(self.quit_button)

        central = QWidget()
        v = QVBoxLayout(central)
        v.addLayout(files)
        v.addLayout(options)
        v.addWidget(vsplit, 1)
        v.addLayout(bottom)
        self.setCentralWidget(central)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(240)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)

        self._menus()
        self.resize(1200, 820)

    def _menus(self):
        """Native menus: on macOS, Quit and About move to the application menu, and
        Qt types Ctrl as ⌘ (⌘Q, ⌘O, ⌘P); on Windows, Quit is File > Exit (Alt+F4)."""
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "Open &Template…", "Ctrl+O",
                     lambda: self._browse(self.template_edit, "Word (*.docx)"))
        self._action(file_menu, "Open &Data…", "Ctrl+Shift+O",
                     lambda: self._browse(self.data_edit, "Excel (*.xlsx)"))
        self._action(file_menu, "&Reload", ["F5", "Ctrl+R"], self.reload)
        file_menu.addSeparator()
        windows = sys.platform == "win32"
        self.quit_action = self._action(file_menu, "E&xit" if windows else "&Quit",
                                        "Alt+F4" if windows else "Ctrl+Q", self.close)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        letters_menu = self.menuBar().addMenu("&Letters")
        self.print_action = self._action(letters_menu, "&Print Checked Letters",
                                         "Ctrl+P", self.print_checked)
        self.stop_action = self._action(letters_menu, "&Stop Printing", "Ctrl+.", self.stop_printing)
        self.stop_action.setEnabled(False)
        letters_menu.addSeparator()
        self.reroll_action = self._action(letters_menu, "&New Typing Errors for This Letter", None,
                                          lambda: self.reroll(all_letters=False))
        self.reroll_all_action = self._action(letters_menu, "New Typing Errors for &All Letters", None,
                                              lambda: self.reroll(all_letters=True))
        help_menu = self.menuBar().addMenu("&Help")
        self.guide_action = self._action(help_menu, "daisywriter &User Guide", "F1", self.show_guide)
        self.samples_action = self._action(help_menu, "Open &Sample Letters", None, self.open_samples)
        help_menu.addSeparator()
        about = self._action(help_menu, "&About daisywriter", None, self._about)
        about.setMenuRole(QAction.MenuRole.AboutRole)

    def _action(self, menu, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            keys = shortcut if isinstance(shortcut, list) else [shortcut]
            action.setShortcuts([QKeySequence(k) for k in keys])
        action.triggered.connect(lambda _=False: slot())
        menu.addAction(action)
        return action

    def show_guide(self):
        if getattr(self, "_guide", None) is None:
            text = (resources.files("daisywriter.gui") / "user_guide.md").read_text(encoding="utf-8")
            self._guide = QDialog(self)
            self._guide.setWindowTitle("daisywriter user guide")
            browser = QTextBrowser(self._guide)
            browser.setOpenExternalLinks(True)
            browser.setMarkdown(text)
            QVBoxLayout(self._guide).addWidget(browser)
            self._guide.resize(760, 820)
        self._guide.show()
        self._guide.raise_()

    def _about(self):
        try:
            version = metadata.version("daisywriter")
        except metadata.PackageNotFoundError:
            version = "(development)"
        QMessageBox.about(self, "About daisywriter",
                          f"<b>daisywriter</b> {version}<p>Mail merge from Word and Excel "
                          "onto daisywheel typewriters.</p>")

    def samples_dir(self) -> Path:
        """Where Open Sample Letters puts the files (tests replace this)."""
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        return Path(documents or Path.home()) / "daisywriter samples"

    def open_samples(self):
        """Put the sample letters in Documents and open them. Files already there are
        kept, in case they've been changed."""
        if self.worker is not None:
            return
        from ..samples import make_samples
        folder = self.samples_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            for made in make_samples(tmp):
                if not (folder / made.name).exists():
                    shutil.copy(made, folder / made.name)
        self.template_edit.setText(str(folder / "letter-template.docx"))
        self.data_edit.setText(str(folder / "letter-data.xlsx"))
        self.reload()
        self.inform("Sample letters",
                    f"The sample letters are open. They're in {folder}, to look at in Word and Excel."
                    "\n\nClick a letter in the list to see it as it will be typed. To try printing "
                    "without paper, choose \"Print on the emulator (PDF)\" next to the Print button.")

    # Settings and files

    def _restore(self):
        self.template_edit.setText(self.store.value("template", "", str))
        self.data_edit.setText(self.store.value("data", "", str))
        i = self.profile_combo.findData(self.store.value("profile", DEFAULT_PROFILE, str))
        if i >= 0:
            self.profile_combo.setCurrentIndex(i)
        self._sheet_wanted = self.store.value("sheet", "", str)
        for w in (self.errors_box, self.error_rate, self.error_style):
            w.blockSignals(True)
        self.errors_box.setChecked(self.store.value("errors", False, bool))
        self.error_rate.setValue(self.store.value("error_rate", 1.0, float))
        self.error_style.setCurrentIndex(max(0, self.error_style.findData(
            self.store.value("error_style", "mix", str))))
        for w in (self.errors_box, self.error_rate, self.error_style):
            w.blockSignals(False)
        self._enable_error_controls()
        self.reload()

    def _save_choices(self):
        self.store.setValue("template", self.template_edit.text())
        self.store.setValue("data", self.data_edit.text())
        self.store.setValue("profile", self.profile_combo.currentData())
        self.store.setValue("sheet", self.sheet_combo.currentText())
        self.store.setValue("errors", self.errors_box.isChecked())
        self.store.setValue("error_rate", self.error_rate.value())
        self.store.setValue("error_style", self.error_style.currentData())

    def _browse(self, edit: QLineEdit, kind: str):
        start = edit.text() or self.data_edit.text() or self.template_edit.text() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose a file", str(Path(start).parent), kind)
        if path:
            edit.setText(path)
            self.reload()

    def _file_changed(self, path: str):
        # Word and Excel save by replacing the file; watch the new one and reload once
        if Path(path).exists() and path not in self.watcher.files():
            self.watcher.addPath(path)
        self._reload_timer.start()

    def _watch(self, *paths: Path):
        if self.watcher.files():
            self.watcher.removePaths(self.watcher.files())
        existing = [str(p) for p in paths if p.exists()]
        if existing:
            self.watcher.addPaths(existing)

    def _fill_sheets(self, data: Path):
        current = self.sheet_combo.currentText() or self._sheet_wanted
        import openpyxl
        from openpyxl.utils.exceptions import InvalidFileException
        names = []
        with contextlib.suppress(OSError, ValueError, KeyError, zipfile.BadZipFile, InvalidFileException):
            wb = openpyxl.load_workbook(data, read_only=True)  # the merge reports unreadable files
            names = wb.sheetnames
            wb.close()
        self.sheet_combo.clear()
        self.sheet_combo.addItems(names)
        if current in names:
            self.sheet_combo.setCurrentText(current)

    def settings(self, session: Session | None = None) -> Settings:
        today = self.today_edit.date()
        errors = ErrorSettings(enabled=self.errors_box.isChecked(), rate=self.error_rate.value(),
                               style=self.error_style.currentData(),
                               salt=session.salt if session else 0,
                               letter_salts=dict(session.salts) if session else {})
        return Settings(
            profile=self.profile_combo.currentData(),
            sheet=self.sheet_combo.currentText() or None,
            merge=MergeSettings(today=dt.date(today.year(), today.month(), today.day())),
            layout=LayoutSettings(justify=self.justify.isChecked(),
                                  page_numbers=PageNumbers(self.page_numbers.currentData())),
            errors=errors)

    # Typing errors

    def _enable_error_controls(self):
        on = self.errors_box.isChecked()
        for w in (self.error_rate, self.error_style, self.reroll_button, self.reroll_action,
                  self.reroll_all_action):
            w.setEnabled(on)

    def _errors_changed(self):
        self._enable_error_controls()
        self.reload()

    def reroll(self, all_letters: bool):
        """Different typing errors for the selected letter, or for every letter."""
        letter = self.selected_letter()
        if self.session is None or not self.errors_box.isChecked() or (letter is None and not all_letters):
            return
        if all_letters:
            self.session.reroll()
        else:
            self.session.reroll(self.template_edit.text(), letter)
        self.reload()

    # Loading

    def reload(self):
        if self.worker is not None:
            return  # don't change the letters while they're printing
        template, data = Path(self.template_edit.text()), Path(self.data_edit.text())
        selected = self.selected_letter()
        kept = (self.checked_numbers(), self.table.rowCount()) if self.merge else None
        self.merge, self.session, self.load_error = None, None, ""
        if template.is_file() and data.is_file():
            if self.sheet_combo.count() == 0 or self.sheet_combo.property("file") != str(data):
                self._fill_sheets(data)
                self.sheet_combo.setProperty("file", str(data))
            try:
                self.session = Session.load(data)
                self.merge = run(template, data, self.settings(self.session))
            except ValueError as e:
                self.load_error = str(e)
            self._watch(template, data)
            self._save_choices()
        elif self.template_edit.text() or self.data_edit.text():
            missing = [str(p) for p in (template, data) if str(p) not in ("", ".") and not p.is_file()]
            self.load_error = ("not found: " + ", ".join(missing)) if missing else ""
        self._fill_table(selected.number if selected else 1, kept)
        self._fill_issues()

    def _fill_table(self, select: int, kept: tuple[set[int], int] | None = None):
        """kept: (checked letter numbers, row count) from before a reload."""
        self.table.setRowCount(0)
        letters = self.merge.letters if self.merge else []
        self.table.setRowCount(len(letters))
        for row, letter in enumerate(letters):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                           | Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, COL_CHECK, check)
            num = QTableWidgetItem(str(letter.number))
            num.setData(Qt.ItemDataRole.UserRole, letter.number)
            self.table.setItem(row, COL_NUM, num)
            self.table.setItem(row, COL_WHO, QTableWidgetItem(letter.summary()))
            self.table.setItem(row, COL_PAGES, QTableWidgetItem(str(len(letter.pages))))
            self.table.setItem(row, COL_ISSUES, self._issue_item(letter))
            self.table.setItem(row, COL_STATUS, QTableWidgetItem())
            self._show_status(letter)
        if kept and kept[1] == len(letters):  # the same letters: keep the user's checks
            self._set_checks([r + 1 in kept[0] for r in range(len(letters))])
        else:
            self.check_where(lambda st: st != PRINTED)
        self._update_check_header()
        if letters:
            self.table.selectRow(min(select, len(letters)) - 1)
        else:
            self.preview.view.clear()
        self._update_title()

    def _issue_item(self, letter: Letter) -> QTableWidgetItem:
        counts = {lvl: sum(1 for i in letter.issues if i.level is lvl) for lvl in I.Level}
        parts = [f"{counts[I.Level.ERROR]} error{'s' * (counts[I.Level.ERROR] != 1)}"
                 if counts[I.Level.ERROR] else "",
                 f"{counts[I.Level.WARNING]} warning{'s' * (counts[I.Level.WARNING] != 1)}"
                 if counts[I.Level.WARNING] else ""]
        item = QTableWidgetItem(", ".join(p for p in parts if p))
        worst = max((i.level for i in letter.issues if i.level > I.Level.INFO), default=None)
        if worst is not None:
            item.setForeground(QBrush(LEVEL_COLORS[worst]))
        return item

    def _row_of(self, number: int) -> int:
        return number - 1  # letters are numbered from 1 in table order

    def _show_status(self, letter: Letter):
        st = self.session.state(self.template_edit.text(), letter) if self.session else None
        status = st.status if st else NOT_PRINTED
        text = status
        if status == PRINTING and self.worker is None:
            text = "interrupted"
        elif st and st.changed_since(letter):
            text = "printed (changed since)"
        if st and st.when and status != NOT_PRINTED:
            text += f" {st.when.replace('T', ' ')[:16]}"
        item = self.table.item(self._row_of(letter.number), COL_STATUS)
        item.setText(text)
        item.setToolTip(st.message if st and st.message else "")
        item.setForeground(QBrush(STATUS_COLORS.get(status, QColor("#555555"))))

    def _fill_issues(self):
        self.issues.clear()
        if self.load_error:
            self._add_issue(I.error(self.load_error))
        if not self.merge:
            if not self.load_error:
                self._add_issue(I.info("choose a Word template and an Excel data file"))
            return
        if self.session and self.session.problem:
            self._add_issue(I.warning(self.session.problem, "session"))
        for issue in sorted(self.merge.all_issues(), key=lambda i: -i.level):
            self._add_issue(issue)

    def _add_issue(self, issue: I.Issue):
        item = QTreeWidgetItem([issue.level.label, issue.where, issue.message])
        item.setForeground(0, QBrush(LEVEL_COLORS[issue.level]))
        item.setData(0, Qt.ItemDataRole.UserRole, issue.letter)
        item.setToolTip(2, issue.message)
        self.issues.addTopLevelItem(item)

    def _issue_clicked(self, item: QTreeWidgetItem):
        number = item.data(0, Qt.ItemDataRole.UserRole)
        if number:
            self.table.selectRow(self._row_of(number))

    def _update_title(self):
        name = Path(self.data_edit.text()).name if self.merge else ""
        self.setWindowTitle(f"daisywriter — {name}" if name else "daisywriter")

    # Selection and preview

    def letter(self, number: int) -> Letter:
        return self.merge.letters[number - 1]

    def selected_letter(self) -> Letter | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or not self.merge:
            return None
        return self.letter(self.table.item(rows[0].row(), COL_NUM).data(Qt.ItemDataRole.UserRole))

    def checked_numbers(self) -> set[int]:
        items = [self.table.item(r, COL_CHECK) for r in range(self.table.rowCount())]
        return {r + 1 for r, item in enumerate(items)  # rows are None while the table fills
                if item is not None and item.checkState() == Qt.CheckState.Checked}

    def checked_letters(self) -> list[Letter]:
        if not self.merge:
            return []
        return [self.letter(self.table.item(r, COL_NUM).data(Qt.ItemDataRole.UserRole))
                for r in range(self.table.rowCount())
                if self.table.item(r, COL_CHECK).checkState() == Qt.CheckState.Checked]

    def check_where(self, pick):
        """Check the letters whose status pick(status) accepts, and uncheck the rest."""
        states = []
        for r in range(self.table.rowCount()):
            letter = self.letter(r + 1)
            st = self.session.state(self.template_edit.text(), letter).status if self.session else NOT_PRINTED
            states.append(pick(st))
        self._set_checks(states)

    def _set_checks(self, states: list[bool]):
        blocked = self.table.blockSignals(True)  # one header update, not one per row
        for r, on in enumerate(states):
            self.table.item(r, COL_CHECK).setCheckState(
                Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.table.blockSignals(blocked)
        self._update_check_header()

    def _item_changed(self, item: QTableWidgetItem):
        if item.column() == COL_CHECK:
            self._update_check_header()

    def _update_check_header(self):
        rows, n = self.table.rowCount(), len(self.checked_numbers())
        self.check_header.set_state(Qt.CheckState.Unchecked if n == 0 or rows == 0 else
                                    Qt.CheckState.Checked if n == rows else Qt.CheckState.PartiallyChecked)

    def _toggle_all(self):
        """Check every letter, or uncheck them all if they're all checked."""
        rows = self.table.rowCount()
        self._set_checks([len(self.checked_numbers()) < rows] * rows)

    def _show_selected(self):
        letter = self.selected_letter()
        if letter is None or self.merge is None:
            self.preview.view.clear()
            return
        opts = self._options()
        sheets = emulate([letter], self.merge.profile, opts).sheets
        self.preview.view.show_letter(sheets, letter, self.merge.profile, opts.stock, opts.top_lines)
        self.statusBar().showMessage(
            f"Letter {letter.number}: row {letter.record.row} of the spreadsheet, "
            f"{len(letter.pages)} page{'s' * (len(letter.pages) != 1)}", 5000)

    def _options(self) -> PrintOptions:
        lay = self.merge.settings.layout
        return PrintOptions.for_profile(self.merge.profile, stock=lay.stock, top_lines=lay.top_lines)

    # Dialogs (tests replace these)

    def confirm(self, title: str, text: str, yes: str = "Continue", no: str = "Cancel") -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, title, text, parent=self)
        ok = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
        box.addButton(no, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(ok)
        box.exec()
        return box.clickedButton() is ok

    def inform(self, title: str, text: str, warning: bool = False):
        (QMessageBox.warning if warning else QMessageBox.information)(self, title, text)

    def choose_pdf(self) -> Path | None:
        start = Path(self.data_edit.text()).with_suffix(".pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Save the emulated sheets", str(start), "PDF (*.pdf)")
        return Path(path) if path else None

    def open_file(self, path: Path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # The typewriter

    def check_typewriter(self):
        if not self.merge and self.profile_combo.currentData() is None:
            return
        from ..profile import load_profile
        profile = load_profile(self.profile_combo.currentData())
        try:
            t = open_transport(profile)
        except TransportError as e:
            self._set_status_light(False, str(e))
            return
        try:
            st = t.status()
        finally:
            t.close()
        if st is None:
            self._set_status_light(True, "connected")
        else:
            self._set_status_light(st.ready, st.explain())

    def _set_status_light(self, ok: bool, text: str):
        color = "#2e7d32" if ok else "#c62828"
        self.status_label.setText(f"<span style='color:{color}'>●</span> {text}")
        self.status_label.setToolTip(text)

    # Printing

    def print_checked(self):
        if self.merge is None or self.worker is not None:
            return
        letters = self.checked_letters()
        if not letters:
            self.inform("Nothing to print", "Check the letters to print in the list first.")
            return
        if I.has_errors(self.merge.issues):
            self.inform("Can't print", "The template or data has errors (see the list at the bottom). "
                        "Fix them, then reload.", warning=True)
            return
        bad = [str(x.number) for x in letters if I.has_errors(x.issues)]
        if bad:
            self.inform("Can't print", f"Letter{'s' * (len(bad) != 1)} {', '.join(bad)} "
                        "ha{} errors (see the list at the bottom). Fix them or uncheck them."
                        .format("ve" if len(bad) != 1 else "s"), warning=True)
            return
        printed = [str(x.number) for x in letters
                   if self.session.state(self.template_edit.text(), x).status == PRINTED]
        if printed and not self.confirm(
                "Print again?", f"Letter{'s' * (len(printed) != 1)} {', '.join(printed)} "
                f"{'were' if len(printed) != 1 else 'was'} already printed. Print again?",
                "Print again", "Cancel"):
            return
        profile, opts = self.merge.profile, self._options()
        emulated = self.target.currentData() == EMULATOR
        if emulated:
            self.emulator_pdf = self.choose_pdf()
            if self.emulator_pdf is None:
                return
            transport = Emulator(profile, opts.paper, opts.stock)
        else:
            try:
                transport = open_transport(profile)
            except TransportError as e:
                self._set_status_light(False, str(e))
                self.inform("Can't reach the typewriter", str(e), warning=True)
                return
        self._start(PrintWorker(transport, letters, profile, opts, auto_yes=emulated))

    def _start(self, worker: PrintWorker):
        self.worker = worker
        self.thread = QThread(self)
        worker.moveToThread(self.thread)
        worker.asked.connect(self._answer_prompt)
        worker.progress.connect(self._on_progress)
        worker.letter_state.connect(self._on_letter_state)
        worker.finished.connect(self._on_finished)
        self.thread.started.connect(worker.run)
        for w in (self.print_button, self.print_action, self.target, self.status_button):
            w.setEnabled(False)
        for w in (self.stop_button, self.stop_action):
            w.setEnabled(True)
        self.progress.setValue(0)
        self.progress.show()
        self.thread.start()

    def _answer_prompt(self, message: str):
        self.worker.answer(self.confirm("Paper", message, "Continue", "Stop printing"))

    def _on_progress(self, letter: int, page: int, sent: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(sent)
        self.statusBar().showMessage(f"Typing letter {letter}, page {page}: line {sent} of {total}")

    def _on_letter_state(self, number: int, status: str, message: str):
        letter = self.letter(number)
        self.session.mark(self.template_edit.text(), letter, status, message)
        self._show_status(letter)
        if status == PRINTED:
            self.table.item(self._row_of(number), COL_CHECK).setCheckState(Qt.CheckState.Unchecked)

    def stop_printing(self):
        if self.worker:
            self.worker.stop()
            self.statusBar().showMessage("Stopping when the line being typed is finished…")

    def _on_finished(self, summary: str):
        worker = self.worker
        self.thread.quit()
        self.thread.wait()
        self.worker, self.thread = None, None
        for w in (self.print_button, self.print_action, self.target, self.status_button):
            w.setEnabled(True)
        for w in (self.stop_button, self.stop_action):
            w.setEnabled(False)
        self.progress.hide()
        self.statusBar().showMessage(summary, 10000)
        if isinstance(worker.transport, Emulator):
            self._emulated(worker.transport, summary)
        elif "failed" in summary or STOPPED_PART_WAY in summary:
            self.inform("Printing stopped", summary, warning=True)

    def _emulated(self, emulator: Emulator, summary: str):
        from ..pdf import write_pdf
        write_pdf(self.emulator_pdf, emulator.sheets, self._options().stock)
        found = "\n".join(f"• {e}" for e in emulator.events) or "No problems found."
        if self.confirm("Emulator", f"{summary}\n\n{found}\n\nSaved {self.emulator_pdf.name}.",
                        "Open the PDF", "Close"):
            self.open_file(self.emulator_pdf)

    def closeEvent(self, event):
        if self.worker is not None:
            if not self.confirm("Printing", "Letters are still printing. Stop and quit?",
                                "Stop and quit", "Keep printing"):
                event.ignore()
                return
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(5000)
        self._save_choices()
        super().closeEvent(event)
