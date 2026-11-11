"""The daisywriter window (PySide6). Start it with `daisywriter gui` or `daisywriter-gui`."""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow, app_icon

    app = QApplication.instance() or QApplication(sys.argv if argv is None else ["daisywriter", *argv])
    app.setApplicationName("daisywriter")
    app.setWindowIcon(app_icon())  # also the Dock icon on macOS
    window = MainWindow()
    window.show()
    smoke = os.environ.get("DAISYWRITER_SMOKE_TEST")
    if smoke:  # the installer check: open the window, then quit after this many seconds
        QTimer.singleShot(int(float(smoke) * 1000), app.quit)
    return app.exec()
