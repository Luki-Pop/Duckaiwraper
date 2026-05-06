# duckaiwrapper/client.py
import os
import httpx
from typing import Optional, Generator, List
from .history import HistoryDB, ChatMessage


class AuthError(Exception):
    pass


class DuckAIError(Exception):
    pass


class Response:
    """Simple wrapper returned by query methods."""
    def __init__(self, text: str, session_id: str):
        self.text = text
        self.session_id = session_id

    def __repr__(self):
        return f"<DuckAIResponse session={self.session_id!r} text={self.text[:30]!r}...>"


class DuckAIClient:
    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(
        self,
        api_key: Optional[str] = None,
        db_path: str = "duckai_history.db",
        max_history: Optional[int] = None,
    ):
        self.api_key = api_key or os.getenv("DUCKAI_API_KEY")
        if not self.api_key:
            raise AuthError("DuckAI API key missing")
        self.base_url = "https://api.duck.ai/v1/chat"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.history = HistoryDB(db_path=db_path, max_history=max_history)

    # ------------------------------------------------------------------
    # Session management (public API)
    # ------------------------------------------------------------------
    def start_session(self) -> str:
        """Create a fresh session and return its UUID."""
        return self.history.new_session()

    def list_sessions(self) -> List[str]:
        return self.history.list_sessions()

    def delete_session(self, session_id: str) -> None:
        self.history.delete_session(session_id)

    # ------------------------------------------------------------------
    # Core query methods (synchronous, asynchronous, streaming)
    # ------------------------------------------------------------------
    def _build_payload(self, prompt: str, session_id: str) -> dict:
        """Assemble the full message list (history + new user prompt)."""
        past: List[ChatMessage] = self.history.load_history(session_id)
        messages = [{"role": m.role, "content": m.content} for m in past]
        messages.append({"role": "user", "content": prompt})
        return {"messages": messages}

    def query(self, prompt: str, session_id: Optional[str] = None) -> Response:
        """Blocking request – returns a full answer."""
        if session_id is None:
            session_id = self.start_session()

        payload = self._build_payload(prompt, session_id)

        resp = httpx.post(
            self.base_url,
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]

        # Persist the exchange
        self.history.add_message(session_id, "user", prompt)
        self.history.add_message(session_id, "assistant", answer)

        return Response(text=answer, session_id=session_id)

    async def query_async(self, prompt: str, session_id: Optional[str] = None) -> Response:
        """Async version – useful inside an event loop."""
        if session_id is None:
            session_id = self.start_session()

        payload = self._build_payload(prompt, session_id)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.base_url,
                json=payload,
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]

        self.history.add_message(session_id, "user", prompt)
        self.history.add_message(session_id, "assistant", answer)

        return Response(text=answer, session_id=session_id)

    def stream(self, prompt: str, session_id: Optional[str] = None) -> Generator[str, None, None]:
        """Yield partial tokens as they arrive (synchronous streaming)."""
        if session_id is None:
            session_id = self.start_session()

        payload = self._build_payload(prompt, session_id)
        payload["stream"] = True

        with httpx.StreamingClient() as client:
            with client.stream(
                "POST",
                self.base_url,
                json=payload,
                headers=self.headers,
            ) as response:
                response.raise_for_status()
                full_reply = ""
                for chunk in response.iter_text():
                    full_reply += chunk
                    yield chunk

        # Store after the whole response has been received
        self.history.add_message(session_id, "user", prompt)
        self.history.add_message(session_id, "assistant", full_reply)

    # ------------------------------------------------------------------
    # Clean‑up
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.history.close()
