from collections import defaultdict
from collections.abc import Iterable
from threading import Lock


class SessionMemoryStore:
    """Thread-safe in-memory session store."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._messages: dict[str, list[str]] = defaultdict(list)

    def add(self, session_id: str, message: str) -> None:
        with self._lock:
            self._messages[session_id].append(message)

    def get(self, session_id: str) -> list[str]:
        with self._lock:
            return list(self._messages.get(session_id, []))

    def extend(self, session_id: str, messages: Iterable[str]) -> None:
        with self._lock:
            self._messages[session_id].extend(messages)

