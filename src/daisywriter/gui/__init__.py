"""The daisywriter window (PySide6). Start it with `daisywriter gui` or `daisywriter-gui`."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv if argv is None else ["daisywriter", *argv])
    app.setApplicationName("daisywriter")
    window = MainWindow()
    window.show()
    return app.exec()
