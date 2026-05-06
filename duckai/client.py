# duckai/client.py
import json
import requests
from typing import Optional, List

from .history import HistoryDB, ChatMessage

API_URL = "https://duckduckgo.com/ai/api"   # whatever endpoint the repo uses


class DuckAI:
    def __init__(
        self,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        history_db: Optional[HistoryDB] = None,
        session_id: Optional[str] = None,
        max_history: Optional[int] = None,
    ):
        """
        Parameters
        ----------
        api_key: optional token for the DuckAI endpoint.
        system_prompt: optional system‑level instruction.
        history_db: a HistoryDB instance – if omitted a new one with default
                    `chat_history.db` is created.
        session_id: if supplied the client will use that session; otherwise a
                    new session is created on‑the‑fly.
        max_history: pass-through to HistoryDB – caps the number of stored
                     messages per session.
        """
        self.api_key = api_key
        self.system_prompt = system_prompt

        # ------------------------------------------------------------------
        # Initialise the persistence layer
        # ------------------------------------------------------------------
        self.history = history_db or HistoryDB(max_history=max_history)
        self.session_id = session_id or self.history.new_session()

    # ------------------------------------------------------------------
    # Payload construction – historic messages become context
    # ------------------------------------------------------------------
    def _build_payload(self, user_prompt: str) -> dict:
        # 1️⃣ Load historic messages for this session
        historic: List[ChatMessage] = self.history.load_history(self.session_id)

        # 2️⃣ Convert them to the API’s message format
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        for msg in historic:
            messages.append({"role": msg.role, "content": msg.content})

        # 3️⃣ Append the fresh user query
        messages.append({"role": "user", "content": user_prompt})

        return {"messages": messages}

    # ------------------------------------------------------------------
    # Low‑level HTTP call
    # ------------------------------------------------------------------
    def _post(self, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Public chat method – stores the turn afterwards
    # ------------------------------------------------------------------
    def chat(self, user_prompt: str) -> str:
        payload = self._build_payload(user_prompt)
        response = self._post(payload)

        # Expected shape: {"choices":[{"message":{"content":"..."} }]}
        assistant_reply = response["choices"][0]["message"]["content"]

        # 4️⃣ Persist both sides of the turn
        self.history.add_message(self.session_id, "user", user_prompt)
        self.history.add_message(self.session_id, "assistant", assistant_reply)

        return assistant_reply

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    def list_sessions(self) -> List[str]:
        return self.history.list_sessions()

    def switch_session(self, session_id: str) -> None:
        """Swap to an existing session; raises if the id does not exist."""
        if session_id not in self.list_sessions():
            raise ValueError(f"Session {session_id!r} not found")
        self.session_id = session_id

    def reset_current_session(self) -> None:
        """Delete all messages in the active session but keep the session row."""
        self.history.delete_session(self.session_id)
        # Re‑create the empty session entry so the id stays usable
        self.history.new_session()   # creates a brand‑new uuid
        self.session_id = self.history.list_sessions()[0]

    def close(self) -> None:
        self.history.close()
