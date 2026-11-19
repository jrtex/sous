"""In-memory cooking sessions: just the recent chat history per session."""

from __future__ import annotations

import secrets
import threading
from collections import deque
from dataclasses import dataclass, field

from sous import config


@dataclass
class Session:
    id: str
    recipe_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=config.HISTORY_TURNS * 2))

    def add_turn(self, question: str, answer: str) -> None:
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})


class SessionStore:
    def __init__(self, max_sessions: int = 200):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._max = max_sessions

    def create(self, recipe_id: str) -> Session:
        with self._lock:
            if len(self._sessions) >= self._max:  # drop the oldest
                self._sessions.pop(next(iter(self._sessions)))
            s = Session(id=secrets.token_urlsafe(12), recipe_id=recipe_id)
            self._sessions[s.id] = s
            return s

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)
