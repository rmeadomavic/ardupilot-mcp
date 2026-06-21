"""Smoke tests: the server module imports and registers its tools cleanly."""

from __future__ import annotations

import asyncio

from ardupilot_mcp import server


def test_server_object_exists():
    assert server.mcp.name == "ardupilot-mcp"


def test_expected_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {
        "ardupilot_connect",
        "ardupilot_vehicle_state",
        "ardupilot_recent_statustext",
        "ardupilot_get_param",
        "ardupilot_set_param",
        "ardupilot_list_params",
        "ardupilot_set_mode",
        "ardupilot_arm",
        "ardupilot_disarm",
    } <= names


def test_read_tools_annotated_readonly():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert tools["ardupilot_vehicle_state"].annotations.readOnlyHint is True
    assert tools["ardupilot_arm"].annotations.destructiveHint is True


def test_tools_error_cleanly_when_not_connected():
    server._conn = None
    try:
        server.vehicle_state()
    except RuntimeError as e:
        assert "Not connected" in str(e)
    else:
        raise AssertionError("expected RuntimeError when not connected")
