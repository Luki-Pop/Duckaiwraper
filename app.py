#!/usr/bin/env python3
import sys
from PyQt6 import QtWidgets, QtCore

# ----------------------------------------------------------------------
#  New imports – the revised UI lives in main_window.py
# ----------------------------------------------------------------------
from main_window import MainWindow
from autostart import set_autostart
from PyQt6.QtCore import Qt, QCoreApplication

def main() -> int:
    """Create the Qt application, show the main window, and start the event loop."""
    # Enable high‑DPI scaling on modern monitors (optional but nice)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)

    # ------------------------------------------------------------------
    # 1️⃣  Initialise the main window (now contains ChatPanel + browser)
    # ------------------------------------------------------------------
    win = MainWindow()
    win.show()

    # ------------------------------------------------------------------
    # 2️⃣  Apply stored autostart preference
    # ------------------------------------------------------------------
    set_autostart(win.settings.get("autostart", False))

    # --------------------------------------------------------------
    # 3️⃣  Enter the Qt event loop
    # --------------------------------------------------------------
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
