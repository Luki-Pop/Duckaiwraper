# --------------------------------------------------------------
#  preferences.py
# --------------------------------------------------------------
import os
from PyQt6 import QtWidgets, QtCore, QtGui
from settings import load_settings, save_settings
from autostart import set_autostart, is_autostart_enabled

URL = "https://duck.ai"


class PreferencesDialog(QtWidgets.QDialog):
    """
    Dialog that lets the user edit:
    • Start‑up URL (the page loaded in the right pane)
    • Window size (width × height)
    • Autostart flag (launch on login)
    The dialog works on a copy of the settings dict; the caller
    decides whether to persist the changes.
    """

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)

        # Keep a *copy* so the caller can decide to apply or discard.
        self.settings = settings.copy()

        # ------------------------------------------------------------------
        # 1️⃣  URL selector
        # ------------------------------------------------------------------
        self.url_edit = QtWidgets.QLineEdit(self.settings.get("start_url", URL))
        url_layout = QtWidgets.QFormLayout()
        url_layout.addRow("Start URL:", self.url_edit)

        # ------------------------------------------------------------------
        # 2️⃣  Window size (width × height)
        # ------------------------------------------------------------------
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(400, 5000)
        self.width_spin.setValue(self.settings.get("width", 1200))

        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(300, 3000)
        self.height_spin.setValue(self.settings.get("height", 800))

        size_layout = QtWidgets.QHBoxLayout()
        size_layout.addWidget(QtWidgets.QLabel("Width:"))
        size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QtWidgets.QLabel("Height:"))
        size_layout.addWidget(self.height_spin)

        size_box = QtWidgets.QGroupBox("Window size")
        size_box.setLayout(size_layout)

        # ------------------------------------------------------------------
        # 3️⃣  Autostart checkbox
        # ------------------------------------------------------------------
        self.autostart_chk = QtWidgets.QCheckBox("Launch at system start‑up")
        self.autostart_chk.setChecked(
            bool(self.settings.get("autostart", is_autostart_enabled()))
        )

        # ------------------------------------------------------------------
        # 4️⃣  Buttons (OK / Cancel)
        # ------------------------------------------------------------------
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._accept)
        self.button_box.rejected.connect(self.reject)

        # ------------------------------------------------------------------
        # 5️⃣  Assemble the main layout
        # ------------------------------------------------------------------
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(url_layout)
        main_layout.addWidget(size_box)
        main_layout.addWidget(self.autostart_chk)
        main_layout.addStretch(1)
        main_layout.addWidget(self.button_box)

    # ----------------------------------------------------------------------
    # Slot: user pressed OK → write back to the *original* settings dict
    # ----------------------------------------------------------------------
    def _accept(self):
        # URL
        self.settings["start_url"] = self.url_edit.text().strip() or URL

        # Size
        self.settings["width"] = self.width_spin.value()
        self.settings["height"] = self.height_spin.value()

        # Autostart flag (stored as a plain boolean)
        self.settings["autostart"] = self.autostart_chk.isChecked()

        # Persist to disk so the next launch sees the same values
        save_settings(self.settings)

        # Apply the autostart change immediately (the MainWindow also does it,
        # but calling it here ensures the flag takes effect even if the user
        # closes the app without opening the main window again.)
        set_autostart(self.settings["autostart"])

        self.accept()
