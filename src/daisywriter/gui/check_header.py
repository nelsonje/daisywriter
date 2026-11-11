"""A table header with a checkbox for checking every row.

The checkbox shows the rows: checked when all are checked, empty when none
are, and a dash when only some are. Clicking it checks every row, or unchecks
every row when all are already checked.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtWidgets import QHeaderView, QStyle, QStyleOptionButton

STATES = {Qt.CheckState.Checked: QStyle.StateFlag.State_On,
          Qt.CheckState.Unchecked: QStyle.StateFlag.State_Off,
          Qt.CheckState.PartiallyChecked: QStyle.StateFlag.State_NoChange}


class CheckHeader(QHeaderView):
    clicked_check = Signal()  # the user clicked the checkbox

    def __init__(self, column: int = 0, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.column = column
        self.state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self._section_clicked)

    def set_state(self, state: Qt.CheckState):
        if state != self.state:
            self.state = state
            self.viewport().update()

    def indicator_width(self) -> int:
        return self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, self)

    def _section_clicked(self, index: int):
        if index == self.column:
            self.clicked_check.emit()

    def paintSection(self, painter, rect, index):
        painter.save()
        super().paintSection(painter, rect, index)
        painter.restore()
        if index != self.column:
            return
        opt = QStyleOptionButton()
        w = self.indicator_width()
        h = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, None, self)
        opt.rect = QRect(rect.x() + (rect.width() - w) // 2, rect.y() + (rect.height() - h) // 2, w, h)
        opt.state = QStyle.StateFlag.State_Enabled | STATES[self.state]
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, opt, painter, self)
