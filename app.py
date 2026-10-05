import sqlite3
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ChatMessage:
    role: str           # 'user' or 'assistant'
    content: str
    timestamp: datetime


class HistoryDB:
    """
    SQLite wrapper for sessions and notes.

    Schema
    ------
    sessions  : session_id | name | notes | created_at
    messages  : id | session_id | role | content | timestamp
                (kept for future use; not written by the current UI)
    """

    def __init__(
        self,
        db_path: str = "chat_history.db",
        max_history: Optional[int] = None,
    ):
        self.db_path = db_path
        self.max_history = max_history
        # check_same_thread=False is safe here because all calls happen on
        # the Qt main thread.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema + migration
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL DEFAULT '',
                notes      TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role       TEXT CHECK(role IN ('user','assistant')),
                content    TEXT,
                timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            """
        )
        # Safe migration for databases created before name/notes were added.
        for col in ("name", "notes"):
            try:
                cur.execute(
                    f"ALTER TABLE sessions ADD COLUMN {col} TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass  # column already exists — that is fine
        self.conn.commit()

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def new_session(self, name: str = "") -> str:
        sid = str(uuid.uuid4())
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO sessions (session_id, name) VALUES (?, ?)",
            (sid, name),
        )
        self.conn.commit()
        return sid

    def list_sessions(self) -> List[str]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT session_id FROM sessions ORDER BY created_at DESC"
        )
        return [row[0] for row in cur.fetchall()]

    def list_sessions_detail(self) -> List[Tuple[str, str, str]]:
        """Return (session_id, name, created_at) newest-first."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT session_id, name, created_at FROM sessions ORDER BY created_at DESC"
        )
        return cur.fetchall()

    def rename_session(self, session_id: str, name: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE sessions SET name = ? WHERE session_id = ?",
            (name, session_id),
        )
        self.conn.commit()

    def delete_session(self, session_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cur.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def get_notes(self, session_id: str) -> str:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT notes FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = cur.fetchone()
        return row[0] if row else ""

    def set_notes(self, session_id: str, notes: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE sessions SET notes = ? WHERE session_id = ?",
            (notes, session_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Messages (kept for completeness; not used by SessionPanel)
    # ------------------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?,?,?)",
            (session_id, role, content),
        )
        self.conn.commit()
        if self.max_history:
            cur.execute(
                """
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                    LIMIT (SELECT COUNT(*) - ? FROM messages WHERE session_id = ?)
                )
                """,
                (session_id, self.max_history, session_id),
            )
            self.conn.commit()

    def load_history(self, session_id: str) -> List[ChatMessage]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT role, content, timestamp
            FROM messages
            WHERE session_id = ?
            ORDER BY timestamp
            """,
            (session_id,),
        )
        return [
            ChatMessage(
                role=r[0],
                content=r[1],
                timestamp=datetime.fromisoformat(r[2]),
            )
            for r in cur.fetchall()
        ]

    def close(self) -> None:
        self.conn.close()
