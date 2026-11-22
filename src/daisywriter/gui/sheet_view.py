"""Draws the sheets of a letter as the emulated typewriter types them.

The preview comes from the same bytes that go to the typewriter, so it shows
re-strikes, underscores and where text lands on the paper. Lines in the letter
body (where typing errors may be added) are shaded, and faint lines mark the
margins.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QWidget

from ..frame import Frame
from ..merge import Letter
from ..pdf import CARRIER_PLAY_IN
from ..profile import Profile
from ..transports.emulator import STEPS_PER_INCH, UNITS_PER_INCH, Sheet

GAP = 16  # pixels around and between sheets
INK = QColor(0, 0, 0, 215)
BODY = QColor(255, 236, 160, 110)
GUIDE = QColor(120, 160, 220, 90)


class SheetsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sheets: list[Sheet] = []
        self.body_rows: list[set[int]] = []  # per sheet: 6-lpi rows with body text
        self.profile: Profile | None = None
        self.frame = Frame()
        self.font = QFont("Courier New")
        self.font.setStyleHint(QFont.StyleHint.TypeWriter)
        self.setAutoFillBackground(False)

    @property
    def stock(self):
        return self.frame.stock

    def show_letter(self, sheets: list[Sheet], letter: Letter | None, profile: Profile, frame: Frame):
        self.sheets, self.profile, self.frame = sheets, profile, frame
        self.body_rows = []
        for page in letter.pages if letter else []:
            self.body_rows.append({frame.top_lines + i for i, line in enumerate(page.lines)
                                   if any(c.body for c in line.cells)})
        self._fit()
        self.update()

    def clear(self):
        self.sheets = []
        self._fit()
        self.update()

    def scale(self) -> float:
        """Pixels per inch at the current width."""
        return max(1.0, (self.width() - 2 * GAP) / self.stock.width_in)

    def _fit(self):
        page_h = self.stock.length_in * self.scale()
        n = max(1, len(self.sheets))
        self.setMinimumHeight(int(n * page_h + (n + 1) * GAP))

    def resizeEvent(self, event):
        self._fit()
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), self.palette().window())
        s = self.scale()
        w, h = self.stock.width_in * s, self.stock.length_in * s
        self.font.setPixelSize(max(1, round(s / 6)))  # 12 pt Courier: 10 characters per inch
        p.setFont(self.font)
        for n, sheet in enumerate(self.sheets):
            top = GAP + n * (h + GAP)
            paper = QRectF(GAP, top, w, h)
            p.fillRect(paper.translated(2, 3), QColor(0, 0, 0, 40))
            p.fillRect(paper, Qt.GlobalColor.white)
            self._decorate(p, n, paper, s)
            p.setPen(INK)
            for st in sheet.strikes:
                x = GAP + (st.x / STEPS_PER_INCH + (CARRIER_PLAY_IN if st.from_right else 0)
                           - self.frame.shift_in) * s
                y = top + st.y / UNITS_PER_INCH * s
                if y <= top + h:
                    p.drawText(QPointF(x, y), st.ch)
        p.end()

    def _decorate(self, p: QPainter, n: int, paper: QRectF, s: float):
        prof = self.profile
        if prof is None:
            return
        left_in, right_in, _, _ = self.frame.margins_in(prof)
        left = paper.left() + left_in * s
        right = paper.right() - right_in * s
        line = s / prof.lines_per_inch
        for row in self.body_rows[n] if n < len(self.body_rows) else ():
            p.fillRect(QRectF(left, paper.top() + (row - 0.8) * line, right - left, line), BODY)
        pen = QPen(GUIDE, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(left, paper.top()), QPointF(left, paper.bottom()))
        p.drawLine(QPointF(right, paper.top()), QPointF(right, paper.bottom()))


class PreviewArea(QScrollArea):
    """Scrolls the sheets, scaled to the width of the pane."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = SheetsView()
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
