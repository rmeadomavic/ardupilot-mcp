"""Smoke tests: the server module imports and registers its tools cleanly."""

from __future__ import annotations

import asyncio

from mavlink_mcp import server


def test_server_object_exists():
    assert server.mcp.name == "mavlink-mcp"


def test_expected_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {
        "connect",
        "vehicle_state",
        "recent_statustext",
        "get_param",
        "set_param",
        "list_params",
        "set_mode",
        "arm",
        "disarm",
    } <= names


def test_tools_error_cleanly_when_not_connected():
    server._conn = None
    try:
        server.vehicle_state()
    except RuntimeError as e:
        assert "Not connected" in str(e)
    else:
        raise AssertionError("expected RuntimeError when not connected")
