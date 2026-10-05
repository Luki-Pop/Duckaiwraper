# --------------------------------------------------------------
# main_window.py
# --------------------------------------------------------------
# SessionPanel : session list + editable name + notes + summarise
# MainWindow   : hosts SessionPanel (left) + QWebEngineView (right)
#
# The broken API client (DuckAI) is no longer used.
# We talk to duck.ai through the embedded browser only.
# --------------------------------------------------------------

import os
import pathlib
import platform
from datetime import datetime

from PyQt6 import QtWidgets, QtCore, QtGui, QtWebEngineWidgets

from duckai.history import HistoryDB
from settings import load_settings, save_settings
from autostart import set_autostart, is_autostart_enabled


# ------------------------------------------------------------------
# Resolve config directory (matches settings.py logic)
# Privacy note: the DB and context files live here — user-owned,
# not world-readable by default on either platform.
# ------------------------------------------------------------------
def _config_dir() -> pathlib.Path:
    if platform.system() == "Windows":
        base = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home()))
    else:
        base = pathlib.Path.home() / ".config"
    p = base / "DuckAIWrapper"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ------------------------------------------------------------------
# JS helpers
# ------------------------------------------------------------------

# Injected into the webview to submit a prompt to duck.ai.
# Uses React's native value setter so the framework detects the change.
# ⚠️  If duck.ai changes its DOM, update the SELECTORS lists below.
_JS_INJECT = r"""
(function(text) {
    // --- SELECTORS: update these if duck.ai changes its HTML ---
    var inputSelectors = [
        'textarea[placeholder]',
        'textarea#chat-input',
        'textarea',
    ];
    var submitSelectors = [
        'button[type="submit"]',
        'button[aria-label*="Send"]',
        'button[aria-label*="send"]',
    ];
    // -----------------------------------------------------------

    var input = null;
    for (var i = 0; i < inputSelectors.length; i++) {
        input = document.querySelector(inputSelectors[i]);
        if (input) break;
    }
    if (!input) return 'NO_INPUT';

    // React tracks value via the native setter, not .value directly.
    var proto = input.tagName === 'TEXTAREA'
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(input, text);
    input.dispatchEvent(new Event('input',  { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    // Give React 500 ms to process the value before submitting.
    setTimeout(function() {
        var btn = null;
        for (var j = 0; j < submitSelectors.length; j++) {
            var candidate = document.querySelector(submitSelectors[j]);
            if (candidate && !candidate.disabled) { btn = candidate; break; }
        }
        if (btn) {
            btn.click();
        } else {
            // Fallback: Enter key
            input.dispatchEvent(new KeyboardEvent('keydown',
                { key: 'Enter', code: 'Enter', bubbles: true }));
        }
    }, 500);

    return 'OK';
})(PROMPT_PLACEHOLDER);
"""

# Polls the page for the latest assistant reply.
# Returns '' while nothing is present, 'LOADING' while streaming,
# or the response text once stable.
# ⚠️  Update RESPONSE_SELECTORS if duck.ai changes its HTML.
_JS_POLL = r"""
(function() {
    // --- SELECTORS: update these if duck.ai changes its HTML ---
    var responseSelectors = [
        '[data-message-role="assistant"]',
        '[class*="message--assistant"]',
        '[class*="assistant-message"]',
        '[class*="chat-message"][class*="assistant"]',
    ];
    var loadingSelectors = [
        '[class*="typing"]',
        '[class*="loading"]',
        '[class*="cursor"]',
        '[class*="spinner"]',
    ];
    // -----------------------------------------------------------

    var lastMsg = null;
    for (var i = 0; i < responseSelectors.length; i++) {
        var all = document.querySelectorAll(responseSelectors[i]);
        if (all.length > 0) { lastMsg = all[all.length - 1]; break; }
    }
    if (!lastMsg) return '';

    // Still streaming?
    for (var j = 0; j < loadingSelectors.length; j++) {
        if (lastMsg.querySelector(loadingSelectors[j])) return 'LOADING';
    }

    return (lastMsg.innerText || lastMsg.textContent || '').trim();
})();
"""


# ======================================================================
# SessionPanel
# ======================================================================

class SessionPanel(QtWidgets.QWidget):
    """
    Left panel.  Responsibilities:
      1. List sessions stored in SQLite.
      2. Let the user name a session and write free-form notes.
      3. Drive the summarise flow in the main web view.
    """

    def __init__(
        self,
        history: HistoryDB,
        web_view: QtWebEngineWidgets.QWebEngineView,
        config_dir: pathlib.Path,
        parent=None,
    ):
        super().__init__(parent)
        self.history = history
        self.web = web_view
        self.config_dir = config_dir

        # Internal state for the summarise flow
        self._pending_prompt: str = ""
        self._pending_session_id: str = ""
        self._last_poll_text: str = ""
        self._poll_count: int = 0
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.timeout.connect(self._poll_response)

        self._build_ui()
        self._refresh_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ── Top bar: New / Delete ──────────────────────────────────────
        bar = QtWidgets.QHBoxLayout()
        self.new_btn = QtWidgets.QPushButton("＋ New session")
        self.del_btn = QtWidgets.QPushButton("🗑 Delete")
        self.del_btn.setEnabled(False)
        self.new_btn.clicked.connect(self._new_session)
        self.del_btn.clicked.connect(self._delete_session)
        bar.addWidget(self.new_btn)
        bar.addWidget(self.del_btn)
        layout.addLayout(bar)

        # ── Session list ───────────────────────────────────────────────
        layout.addWidget(QtWidgets.QLabel("Sessions:"))
        self.session_list = QtWidgets.QListWidget()
        self.session_list.setMinimumWidth(240)
        self.session_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.session_list, stretch=1)

        # ── Session name ───────────────────────────────────────────────
        layout.addWidget(QtWidgets.QLabel("Name:"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Give this session a name…")
        self.name_edit.editingFinished.connect(self._save_name)
        layout.addWidget(self.name_edit)

        # ── Notes ──────────────────────────────────────────────────────
        layout.addWidget(QtWidgets.QLabel("Notes (used for context summary):"))
        self.notes_edit = QtWidgets.QTextEdit()
        self.notes_edit.setPlaceholderText(
            "Jot down what you discussed, key points, follow-up questions…"
        )
        self.notes_edit.setMinimumHeight(120)
        self.notes_edit.textChanged.connect(self._autosave_notes)
        layout.addWidget(self.notes_edit, stretch=2)

        # ── Summarise button ───────────────────────────────────────────
        self.summarise_btn = QtWidgets.QPushButton(
            "✦ Summarise notes → copy as context"
        )
        self.summarise_btn.setToolTip(
            "Sends your notes to duck.ai, copies the summary to clipboard\n"
            "and saves a .txt file in your config folder."
        )
        self.summarise_btn.clicked.connect(self._start_summarise)
        layout.addWidget(self.summarise_btn)

        # ── Status label ───────────────────────────────────────────────
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: grey; font-size: 11px;")
        layout.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Session list helpers
    # ------------------------------------------------------------------

    def _refresh_list(self):
        """Rebuild the QListWidget from the database."""
        self.session_list.blockSignals(True)
        current_id = self._current_session_id()
        self.session_list.clear()

        for sid, name, created_at in self.history.list_sessions_detail():
            label = name if name else created_at[:16]   # fallback: date
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, sid)
            self.session_list.addItem(item)

        # Restore selection
        if current_id:
            for i in range(self.session_list.count()):
                if self.session_list.item(i).data(
                    QtCore.Qt.ItemDataRole.UserRole
                ) == current_id:
                    self.session_list.setCurrentRow(i)
                    break
        elif self.session_list.count() > 0:
            self.session_list.setCurrentRow(0)

        self.session_list.blockSignals(False)
        self._update_del_btn()

    def _current_session_id(self) -> str:
        item = self.session_list.currentItem()
        if item:
            return item.data(QtCore.Qt.ItemDataRole.UserRole)
        return ""

    def _update_del_btn(self):
        self.del_btn.setEnabled(self.session_list.count() > 0)

    def _new_session(self):
        sid = self.history.new_session()
        self._refresh_list()
        # Select the new session (it's at the top — newest first)
        self.session_list.setCurrentRow(0)
        self.name_edit.setFocus()
        self._set_status(f"New session created.")

    def _delete_session(self):
        sid = self._current_session_id()
        if not sid:
            return
        reply = QtWidgets.QMessageBox.question(
            self, "Delete session",
            "Delete this session and its notes permanently?",
            QtWidgets.QMessageBox.StandardButton.Yes |
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.history.delete_session(sid)
            self._refresh_list()

    def _on_row_changed(self, _row):
        """Load name + notes for the newly selected session."""
        sid = self._current_session_id()
        if not sid:
            return
        self.name_edit.blockSignals(True)
        self.notes_edit.blockSignals(True)

        self.name_edit.setText(self._get_session_name(sid))
        self.notes_edit.setPlainText(self.history.get_notes(sid))

        self.name_edit.blockSignals(False)
        self.notes_edit.blockSignals(False)
        self._update_del_btn()
        self.status_label.setText("")

    def _get_session_name(self, session_id: str) -> str:
        """Fetch just the name for a session_id."""
        for sid, name, _ in self.history.list_sessions_detail():
            if sid == session_id:
                return name
        return ""

    # ------------------------------------------------------------------
    # Save name + notes
    # ------------------------------------------------------------------

    def _save_name(self):
        sid = self._current_session_id()
        if sid:
            name = self.name_edit.text().strip()
            self.history.rename_session(sid, name)
            self._refresh_list()

    def _autosave_notes(self):
        """Save notes automatically as the user types."""
        sid = self._current_session_id()
        if sid:
            self.history.set_notes(sid, self.notes_edit.toPlainText())

    # ------------------------------------------------------------------
    # Summarise flow
    # ------------------------------------------------------------------

    def _start_summarise(self):
        sid = self._current_session_id()
        if not sid:
            self._set_status("❌ No session selected.")
            return

        notes = self.notes_edit.toPlainText().strip()
        if not notes:
            self._set_status("❌ Add some notes first.")
            return

        # Build the prompt we will send to duck.ai
        self._pending_prompt = (
            "Please summarise the following notes concisely. "
            "The summary will be pasted at the start of a new AI chat session "
            "to provide context. Be brief and factual:\n\n" + notes
        )
        self._pending_session_id = sid

        self.summarise_btn.setEnabled(False)
        self._set_status("⏳ Loading fresh duck.ai…")

        # Navigate to a fresh duck.ai and wait for the page to load.
        # We disconnect any pre-existing connection to avoid double-firing.
        try:
            self.web.loadFinished.disconnect(self._on_page_ready)
        except TypeError:
            pass
        self.web.loadFinished.connect(self._on_page_ready)
        self.web.setUrl(QtCore.QUrl("https://duck.ai"))

    def _on_page_ready(self, ok: bool):
        """Called once duck.ai has finished loading."""
        try:
            self.web.loadFinished.disconnect(self._on_page_ready)
        except TypeError:
            pass

        if not ok:
            self._set_status("❌ Failed to load duck.ai. Check your connection.")
            self.summarise_btn.setEnabled(True)
            return

        self._set_status("⏳ Waiting for duck.ai to initialise…")
        # Give the page's JavaScript 2 seconds to boot before injecting.
        QtCore.QTimer.singleShot(2000, self._inject_prompt)

    def _inject_prompt(self):
        self._set_status("⏳ Injecting summarise prompt…")
        # Safely embed the prompt string in the JS snippet.
        escaped = self._pending_prompt.replace("\\", "\\\\").replace(
            "`", "\\`"
        ).replace("'", "\\'")
        js = _JS_INJECT.replace("PROMPT_PLACEHOLDER", f"'{escaped}'")
        self.web.page().runJavaScript(js, self._on_inject_done)

    def _on_inject_done(self, result):
        if result == "OK":
            self._set_status("⏳ Waiting for duck.ai to respond…")
            self._last_poll_text = ""
            self._poll_count = 0
            self._poll_timer.start(2000)   # poll every 2 s
        else:
            # 'NO_INPUT' or None — the DOM selector didn't match
            self._set_status(
                "⚠️  Could not find duck.ai's input field. "
                "duck.ai may have updated their page. "
                "See the JS selectors in main_window.py (_JS_INJECT)."
            )
            self.summarise_btn.setEnabled(True)

    def _poll_response(self):
        self._poll_count += 1
        if self._poll_count > 45:   # ~90 second timeout
            self._poll_timer.stop()
            self._set_status(
                "⏳ Timed out waiting for duck.ai. "
                "Try clicking Summarise again, or copy the response manually."
            )
            self.summarise_btn.setEnabled(True)
            return
        self.web.page().runJavaScript(_JS_POLL, self._on_poll_result)

    def _on_poll_result(self, text: str):
        if not text or text == "LOADING":
            return  # still waiting — next timer tick will retry

        if text == self._last_poll_text and len(text) > 40:
            # Text is stable for one full 2-second cycle → assume complete
            self._poll_timer.stop()
            self._on_summary_complete(text)
        else:
            self._last_poll_text = text

    def _on_summary_complete(self, summary: str):
        """Summary received — copy to clipboard and save .txt file."""
        # 1. Copy to clipboard
        QtWidgets.QApplication.clipboard().setText(summary)

        # 2. Build a .txt file in the config dir
        #    Privacy note: file stays on the user's machine, never sent anywhere
        session_name = self.name_edit.text().strip() or "session"
        safe_name = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in session_name
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"context_{safe_name}_{timestamp}.txt".replace(" ", "_")
        filepath = self.config_dir / "contexts" / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        header = (
            f"=== DuckAI Context File ===\n"
            f"Session : {session_name}\n"
            f"Created : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"===========================\n\n"
        )
        filepath.write_text(header + summary, encoding="utf-8")

        self.summarise_btn.setEnabled(True)
        self._set_status(
            f"✅ Summary copied to clipboard!\n"
            f"File saved: {filepath.name}\n"
            f"Paste it as your first message in the new duck.ai chat."
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        self.status_label.setText(msg)


# ======================================================================
# MainWindow
# ======================================================================

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        self.settings["autostart"] = (
            is_autostart_enabled() or self.settings.get("autostart", False)
        )

        # ------------------------------------------------------------------
        # DB path: always the same file regardless of launch directory.
        # Privacy note: stored next to settings.json, user-owned.
        # ------------------------------------------------------------------
        self._config_dir = _config_dir()
        db_path = str(self._config_dir / "chat_history.db")
        self.history = HistoryDB(db_path=db_path)

        # ------------------------------------------------------------------
        # Window geometry
        # ------------------------------------------------------------------
        self.setWindowTitle("Duck.ai")
        self.resize(
            self.settings.get("width", 1200),
            self.settings.get("height", 800),
        )
        if (x := self.settings.get("x")) is not None and (
            y := self.settings.get("y")
        ) is not None:
            self.move(x, y)

        # ------------------------------------------------------------------
        # Web view (right side) — uses a private off-the-record profile
        # so Qt writes no cookies or cache to disk.
        # Privacy note: QWebEngineProfile.defaultProfile() DOES write to disk.
        # Using an off-the-record profile avoids that entirely.
        # ------------------------------------------------------------------
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        private_profile = QWebEngineProfile(self)   # unnamed = off-the-record
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEnginePage
        private_page = QWebEnginePage(private_profile, self)

        self.web = QWebEngineView()
        self.web.setPage(private_page)
        start_url = self.settings.get("start_url", "https://duck.ai")
        self.web.setUrl(QtCore.QUrl(start_url))

        # ------------------------------------------------------------------
        # Session panel (left side)
        # ------------------------------------------------------------------
        self.session_panel = SessionPanel(
            history=self.history,
            web_view=self.web,
            config_dir=self._config_dir,
        )

        # ------------------------------------------------------------------
        # Layout
        # ------------------------------------------------------------------
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.session_panel)
        splitter.addWidget(self.web)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        # ------------------------------------------------------------------
        # Menus
        # ------------------------------------------------------------------
        app_menu = self.menuBar().addMenu("App")
        pref_action = QtGui.QAction("Preferences", self)
        pref_action.triggered.connect(self.open_preferences)
        app_menu.addAction(pref_action)
        app_menu.addSeparator()
        app_menu.addAction(
            QtGui.QAction("Quit", self, triggered=self.close)
        )

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def open_preferences(self):
        from preferences import PreferencesDialog
        dlg = PreferencesDialog(self.settings.copy(), self)
        if dlg.exec():
            self.settings.update(dlg.settings)
            self.resize(self.settings["width"], self.settings["height"])
            self.web.setUrl(QtCore.QUrl(self.settings["start_url"]))
            save_settings(self.settings)
            set_autostart(bool(self.settings.get("autostart", False)))

    # ------------------------------------------------------------------
    # Remember geometry on close
    # ------------------------------------------------------------------

    def closeEvent(self, ev):
        geo = self.geometry()
        self.settings["x"] = geo.x()
        self.settings["y"] = geo.y()
        self.settings["width"] = geo.width()
        self.settings["height"] = geo.height()
        save_settings(self.settings)
        self.history.close()
        super().closeEvent(ev)
