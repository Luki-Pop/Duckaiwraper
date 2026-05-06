# --------------------------------------------------------------
#  main_window.py
# --------------------------------------------------------------
#   - ChatPanel  : session selector + chat view + input line
#   - MainWindow : creates DuckAI client, arranges UI, handles
#                  geometry & preferences
# --------------------------------------------------------------

import os
from PyQt6 import QtWidgets, QtCore, QtGui, QtWebEngineWidgets
from duckai.client import DuckAI          # client + HistoryDB are exported here
from settings import load_settings, save_settings
from autostart import set_autostart, is_autostart_enabled

# ----------------------------------------------------------------------
# 1️⃣  ChatPanel – the persistent chat column
# ----------------------------------------------------------------------
class ChatPanel(QtWidgets.QWidget):
    """Left‑hand panel that shows history and lets the user send messages."""
    def __init__(self, duck_client: DuckAI, parent=None):
        super().__init__(parent)
        self.client = duck_client

        # ------------------------------------------------------------------
        # Session selector (combo‑box) + “New” button
        # ------------------------------------------------------------------
        self.session_cb = QtWidgets.QComboBox()
        self.session_cb.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow
        )
        self.session_cb.currentIndexChanged.connect(self._on_session_change)

        self.new_sess_btn = QtWidgets.QPushButton("New")
        self.new_sess_btn.clicked.connect(self._new_session)

        sess_layout = QtWidgets.QHBoxLayout()
        sess_layout.addWidget(QtWidgets.QLabel("Session:"))
        sess_layout.addWidget(self.session_cb, 1)
        sess_layout.addWidget(self.new_sess_btn)

        # ------------------------------------------------------------------
        # Chat view – read‑only QTextEdit
        # ------------------------------------------------------------------
        self.chat_view = QtWidgets.QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setMinimumWidth(280)
        self.chat_view.setWordWrapMode(QtGui.QTextOption.WrapMode.WordWrap)

        # ------------------------------------------------------------------
        # Input line + Send button
        # ------------------------------------------------------------------
        self.input_line = QtWidgets.QLineEdit()
        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.clicked.connect(self._send_message)
        self.input_line.returnPressed.connect(self._send_message)

        inp_layout = QtWidgets.QHBoxLayout()
        inp_layout.addWidget(self.input_line, 1)
        inp_layout.addWidget(self.send_btn)

        # ------------------------------------------------------------------
        # Assemble the vertical layout
        # ------------------------------------------------------------------
        v = QtWidgets.QVBoxLayout(self)
        v.addLayout(sess_layout)
        v.addWidget(self.chat_view, 1)
        v.addLayout(inp_layout)

        # ------------------------------------------------------------------
        # Initialise session list
        # ------------------------------------------------------------------
        self._refresh_sessions()
        if self.session_cb.count() == 0:
            self._new_session()
        else:
            self.session_cb.setCurrentIndex(0)

    # ----------------------------------------------------------------------
    # Session handling utilities
    # ----------------------------------------------------------------------
    def _refresh_sessions(self):
        """Fill the combo box with all stored session IDs."""
        self.session_cb.blockSignals(True)
        self.session_cb.clear()
        sessions = self.client.history.list_sessions()
        self.session_cb.addItems(sessions)
        self.session_cb.blockSignals(False)

    def _new_session(self):
        """Create a fresh UUID session and switch to it."""
        new_id = self.client.history.new_session()
        self._refresh_sessions()
        idx = self.session_cb.findText(new_id)
        self.session_cb.setCurrentIndex(idx)

    def _on_session_change(self, _idx):
        """Load history for the newly selected session."""
        sid = self.session_cb.currentText()
        if sid:
            self.client.session_id = sid
            self._load_chat_history()

    # ----------------------------------------------------------------------
    # History view helpers
    # ----------------------------------------------------------------------
    def _load_chat_history(self):
        """Read stored messages for the active session and display them."""
        self.chat_view.clear()
        msgs = self.client.history.load_history(self.client.session_id)
        for msg in msgs:
            # msg.timestamp is a datetime; convert to QDateTime for formatting
            ts = QtCore.QDateTime(msg.timestamp)
            self._append_message(msg.role, msg.content, ts)

    def _append_message(self, role: str, text: str,
                        ts: QtCore.QDateTime | None = None):
        """Append a coloured line to the QTextEdit."""
        colour = "#0066CC" if role == "user" else "#009900"
        stamp = f"[{ts.toString('yyyy-MM-dd HH:mm')}] " if ts else ""
        self.chat_view.setTextColor(QtGui.QColor(colour))
        self.chat_view.append(f"{stamp}{role.title()}: {text}")

        # Optional: limit total blocks to avoid unbounded growth
        self.chat_view.document().setMaximumBlockCount(500)

    # ----------------------------------------------------------------------
    # Send a new prompt to DuckAI
    # ----------------------------------------------------------------------
    def _send_message(self):
        user_txt = self.input_line.text().strip()
        if not user_txt:
            return
        self.input_line.clear()
        self._append_message("user", user_txt,
                             QtCore.QDateTime.currentDateTime())

        # Disable UI while waiting for the network reply
        self.input_line.setEnabled(False)
        self.send_btn.setEnabled(False)

        # Use a short timer to move the network call off the UI thread.
        # For a production app replace this with a QThread/QFuture.
        QtCore.QTimer.singleShot(10, lambda: self._fetch_reply(user_txt))

    def _fetch_reply(self, prompt: str):
        try:
            reply = self.client.chat(prompt)   # persistence happens inside client
            self._append_message("assistant", reply,
                                 QtCore.QDateTime.currentDateTime())
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", str(exc))
        finally:
            self.input_line.setEnabled(True)
            self.send_btn.setEnabled(True)
            self.input_line.setFocus()


# ----------------------------------------------------------------------
# 2️⃣  MainWindow – top‑level window that hosts ChatPanel + browser
# ----------------------------------------------------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        # --------------------------------------------------------------
        # Load stored UI settings (size, position, start URL, etc.)
        # --------------------------------------------------------------
        self.settings = load_settings()
        self.settings["autostart"] = (
            is_autostart_enabled() or self.settings.get("autostart", False)
        )

        # --------------------------------------------------------------
        # 1️⃣ Initialise the DuckAI client (creates HistoryDB automatically)
        # --------------------------------------------------------------
        self.duck_client = DuckAI(
            system_prompt="You are a helpful assistant.",
            max_history=200,               # keep up to 200 messages per session
        )   # a session_id is generated lazily on first use

        # --------------------------------------------------------------
        # 2️⃣ Build the UI – splitter with ChatPanel (left) + Web view (right)
        # --------------------------------------------------------------
        self.setWindowTitle("Duck.ai")
        self.resize(
            self.settings.get("width", 1200),
            self.settings.get("height", 800)
        )
        if (x := self.settings.get("x")) is not None and (y := self.settings.get("y")) is not None:
            self.move(x, y)

        # ---- Chat panel -------------------------------------------------
        self.chat_panel = ChatPanel(self.duck_client)

        # ---- Web view (unchanged) ---------------------------------------
        self.web = QtWebEngineWidgets.QWebEngineView()
        start_url = self.settings.get("start_url", "https://duck.ai")
        self.web.setUrl(QtCore.QUrl(start_url))

        # ---- Splitter ----------------------------------------------------
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.chat_panel)
        splitter.addWidget(self.web)
        splitter.setStretchFactor(0, 0)   # chat panel keeps its min width
        splitter.setStretchFactor(1, 1)   # web view expands

        self.setCentralWidget(splitter)

        # --------------------------------------------------------------
        # 3️⃣ Menus – keep existing ones, add “Preferences”
        # --------------------------------------------------------------
        pref_action = QtGui.QAction("Preferences", self)
        pref_action.triggered.connect(self.open_preferences)

        app_menu = self.menuBar().addMenu("App")
        app_menu.addAction(pref_action)
        app_menu.addSeparator()
        app_menu.addAction(QtGui.QAction("Quit", self, triggered=self.close))

    # ------------------------------------------------------------------
    # Preferences dialog – moved to preferences.py to avoid circular imports
    # ------------------------------------------------------------------
    def open_preferences(self):
        from preferences import PreferencesDialog   # lazy import

        dlg = PreferencesDialog(self.settings.copy(), self)
        if dlg.exec():
            self.settings.update(dlg.settings)
            # Apply geometry changes immediately
            self.resize(self.settings["width"], self.settings["height"])
            self.web.setUrl(QtCore.QUrl(self.settings["start_url"]))
            save_settings(self.settings)
            set_autostart(bool(self.settings.get("autostart", False)))

    # ------------------------------------------------------------------
    # Remember window geometry on close
    # ------------------------------------------------------------------
    def closeEvent(self, ev):
        geo = self.geometry()
        self.settings["x"] = geo.x()
        self.settings["y"] = geo.y()
        self.settings["width"] = geo.width()
        self.settings["height"] = geo.height()
        save_settings(self.settings)
        super().closeEvent(ev)
