"""Thread-safe cache of the latest MAVLink message per type.

MAVLink is an async stream; MCP tools are synchronous request/response. A
background thread pumps ``recv_match`` into this cache, and read tools return
from it instantly without blocking on the link.

Single-latest semantics for most types (ATTITUDE, SYS_STATUS, ...); a bounded
ring buffer for STATUSTEXT, which is a stream of discrete events (the prearm
diagnostic goldmine).
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any


class MessageCache:
    def __init__(self, statustext_maxlen: int = 50) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, Any] = {}
        self._statustext: deque[dict[str, Any]] = deque(maxlen=statustext_maxlen)

    def update(self, msg: Any) -> None:
        """Store a freshly received message. Thread-safe."""
        msg_type = msg.get_type()
        with self._lock:
            if msg_type == "STATUSTEXT":
                self._statustext.append(
                    {
                        "severity": getattr(msg, "severity", None),
                        "text": getattr(msg, "text", ""),
                    }
                )
            self._latest[msg_type] = msg

    def latest(self, msg_type: str) -> Any | None:
        """Return the most recent message of ``msg_type``, or None if unseen."""
        with self._lock:
            return self._latest.get(msg_type)

    def types(self) -> set[str]:
        """Set of message types seen so far."""
        with self._lock:
            return set(self._latest)

    def recent_statustext(self, n: int) -> list[dict[str, Any]]:
        """Return up to ``n`` most recent STATUSTEXT entries, newest first."""
        with self._lock:
            items = list(self._statustext)
        items.reverse()
        return items[:n]
