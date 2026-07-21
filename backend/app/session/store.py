import secrets
from typing import Protocol

from app.session.models import SessionData


class SessionStore(Protocol):
    def create(self, data: SessionData) -> str: ...
    def get(self, session_id: str) -> SessionData | None: ...
    def update(self, session_id: str, data: SessionData) -> None: ...
    def delete(self, session_id: str) -> None: ...


class InMemorySessionStore:
    """Single-process, in-memory session store. Fine for one-admin/localhost use.

    Swap for a Redis-backed implementation later (behind the same Protocol)
    if this ever needs to run multi-process or survive restarts.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}

    def create(self, data: SessionData) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = data
        return session_id

    def get(self, session_id: str) -> SessionData | None:
        return self._sessions.get(session_id)

    def update(self, session_id: str, data: SessionData) -> None:
        self._sessions[session_id] = data

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
