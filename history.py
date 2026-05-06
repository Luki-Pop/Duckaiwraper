import sqlite3, uuid
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ChatMessage:
    role: str          # 'user' or 'assistant'
    content: str
    timestamp: datetime

class HistoryDB:
    """Very small SQLite wrapper that stores sessions and their messages."""
    def __init__(self, db_path: str = "chat_history.db", max_history: Optional[int] = None):
        self.db_path = db_path
        self.max_history = max_history
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT CHECK(role IN ('user','assistant')),
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            """
        )
        self.conn.commit()

    # ---------- session helpers ----------
    def new_session(self) -> str:
        sid = str(uuid.uuid4())
        cur = self.conn.cursor()
        cur.execute("INSERT INTO sessions (session_id) VALUES (?)", (sid,))
        self.conn.commit()
        return sid

    def list_sessions(self) -> List[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT session_id FROM sessions ORDER BY created_at DESC")
        return [row[0] for row in cur.fetchall()]

    def delete_session(self, session_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cur.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()

    # ---------- message helpers ----------
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
        rows = cur.fetchall()
        return [
            ChatMessage(role=r[0], content=r[1],
                         timestamp=datetime.fromisoformat(r[2]))
            for r in rows
        ]

    def close(self) -> None:
        self.conn.close()
