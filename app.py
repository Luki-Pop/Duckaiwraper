import os, sys
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from PyQt6 import QtWidgets, QtCore, QtWebEngineWidgets, QtGui
from settings import load_settings, save_settings
from autostart import set_autostart, is_autostart_enabled

URL = "https://duck.ai"

class PreferencesDialog(QtWidgets.QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.settings = settings

        self.url_edit = QtWidgets.QLineEdit(settings.get("start_url", ""))
        self.width_spin = QtWidgets.QSpinBox(); self.width_spin.setRange(400, 3840)
        self.width_spin.setValue(settings.get("width", 1200))
        self.height_spin = QtWidgets.QSpinBox(); self.height_spin.setRange(300, 2160)
        self.height_spin.setValue(settings.get("height", 800))
        self.autostart_cb = QtWidgets.QCheckBox("Autostart on login")
        # show actual system state OR stored pref
        self.autostart_cb.setChecked(is_autostart_enabled() or settings.get("autostart", False))

        form = QtWidgets.QFormLayout()
        form.addRow("Start URL:", self.url_edit)
        form.addRow("Window width:", self.width_spin)
        form.addRow("Window height:", self.height_spin)
        form.addRow("", self.autostart_cb)

        self.test_btn = QtWidgets.QPushButton("Test autostart")
        self.test_btn.clicked.connect(self.on_test_autostart)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        v = QtWidgets.QVBoxLayout()
        v.addLayout(form)
        v.addWidget(self.test_btn)
        v.addWidget(btns)
        self.setLayout(v)

    def on_test_autostart(self):
        # toggle temporarily and report status (does not persist until OK)
        desired = not is_autostart_enabled()
        ok = set_autostart(desired)
        if ok:
            QtWidgets.QMessageBox.information(self, "Autostart", f"Autostart {'enabled' if desired else 'disabled'} (system change).")
        else:
            QtWidgets.QMessageBox.warning(self, "Autostart", "Autostart operation failed on this OS or missing permissions.")

    def accept(self):
        self.settings["start_url"] = self.url_edit.text().strip() or self.settings["start_url"]
        self.settings["width"] = int(self.width_spin.value())
        self.settings["height"] = int(self.height_spin.value())
        self.settings["autostart"] = bool(self.autostart_cb.isChecked())
        super().accept()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        # sync autostart stored value with actual system state
        self.settings["autostart"] = is_autostart_enabled() or self.settings.get("autostart", False)

        self.setWindowTitle("Duck.ai")
        w = self.settings.get("width", 1200)
        h = self.settings.get("height", 800)
        self.resize(w, h)
        x = self.settings.get("x"); y = self.settings.get("y")
        if x is not None and y is not None:
            self.move(x, y)

        self.web = QtWebEngineWidgets.QWebEngineView()
        self.web.setUrl(QtCore.QUrl(self.settings.get("start_url", URL)))
        self.setCentralWidget(self.web)

        pref_action = QtGui.QAction("Preferences", self)
        pref_action.triggered.connect(self.open_preferences)
        men = self.menuBar().addMenu("App")
        men.addAction(pref_action)
        men.addSeparator()
        quit_action = QtGui.QAction("Quit", self); quit_action.triggered.connect(self.close)
        men.addAction(quit_action)

    def open_preferences(self):
        dlg = PreferencesDialog(self.settings.copy(), self)
        if dlg.exec():
            self.settings.update(dlg.settings)
            self.resize(self.settings["width"], self.settings["height"])
            self.web.setUrl(QtCore.QUrl(self.settings["start_url"]))
            save_settings(self.settings)
            set_autostart(bool(self.settings.get("autostart", False)))

    def closeEvent(self, ev):
        geo = self.geometry()
        self.settings["x"] = geo.x()
        self.settings["y"] = geo.y()
        self.settings["width"] = geo.width()
        self.settings["height"] = geo.height()
        save_settings(self.settings)
        super().closeEvent(ev)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    # ensure autostart reflects choice (best-effort)
    set_autostart(window.settings.get("autostart", False))
    sys.exit(app.exec())
