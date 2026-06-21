"""Parameter store: the request-then-collect accumulator.

ArduPilot params arrive as a stream of PARAM_VALUE messages, each carrying the
total ``param_count``. The background recv thread feeds them here; tool calls
read from the store and can block until a specific param (or the full table)
has arrived.
"""

from __future__ import annotations

import fnmatch
import threading
from typing import Any


def _decode_param_id(param_id: Any) -> str:
    if isinstance(param_id, bytes):
        param_id = param_id.decode("ascii", "replace")
    return param_id.split("\x00", 1)[0]


class ParamStore:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._values: dict[str, float] = {}
        self._count: int | None = None

    def apply(self, msg: Any) -> None:
        """Ingest a PARAM_VALUE message. Thread-safe; wakes any waiters."""
        name = _decode_param_id(msg.param_id)
        with self._cond:
            self._values[name] = msg.param_value
            count = getattr(msg, "param_count", None)
            if count:
                self._count = int(count)
            self._cond.notify_all()

    def get(self, name: str) -> float | None:
        with self._cond:
            return self._values.get(name)

    def match(self, glob: str) -> dict[str, float]:
        with self._cond:
            return {k: v for k, v in self._values.items() if fnmatch.fnmatch(k, glob)}

    def all(self) -> dict[str, float]:
        with self._cond:
            return dict(self._values)

    def is_complete(self) -> bool:
        with self._cond:
            return self._count is not None and len(self._values) >= self._count

    def wait_for(self, name: str, timeout: float) -> float | None:
        """Block until ``name`` is present or ``timeout`` elapses."""
        with self._cond:
            if name in self._values:
                return self._values[name]
            self._cond.wait_for(lambda: name in self._values, timeout=timeout)
            return self._values.get(name)

    def wait_for_value(self, name: str, value: float, timeout: float, tol: float = 1e-6) -> bool:
        """Block until ``name`` reads approximately ``value`` (set-confirm echo)."""
        with self._cond:
            ok = self._cond.wait_for(
                lambda: name in self._values and abs(self._values[name] - value) <= tol,
                timeout=timeout,
            )
            return ok

    def wait_complete(self, timeout: float) -> bool:
        with self._cond:
            return self._cond.wait_for(
                lambda: self._count is not None and len(self._values) >= self._count,
                timeout=timeout,
            )
