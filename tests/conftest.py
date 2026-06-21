"""Shared test fixtures: fake MAVLink messages without a real link."""

from __future__ import annotations


class FakeMsg:
    """Minimal stand-in for a pymavlink message object.

    Real pymavlink messages expose ``get_type()`` and attribute access for
    fields. That's all the cache layer depends on, so we fake just that.
    """

    def __init__(self, msg_type: str, **fields):
        self._type = msg_type
        self.__dict__.update(fields)

    def get_type(self) -> str:
        return self._type
