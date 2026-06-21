"""FastMCP server exposing the MAVLink tools.

SITL-first: the default connection target is local SITL. Actuation tools are
registered but gated — see ``safety.py``. Wiring only; the testable logic lives
in cache/params/safety/connection.
"""

from __future__ import annotations

import argparse
import json
import os

from mcp.server.fastmcp import FastMCP

from .connection import MavlinkConnection
from .safety import ActuationDenied

DEFAULT_CONN = "udp:127.0.0.1:14550"

mcp = FastMCP("mavlink-mcp")

# Process-wide connection, configured by main() before mcp.run().
_conn: MavlinkConnection | None = None


def _require_conn() -> MavlinkConnection:
    if _conn is None or _conn.master is None:
        raise RuntimeError("Not connected. Call connect() first.")
    return _conn


# ---------------------------------------------------------------------- #
# connection
# ---------------------------------------------------------------------- #
@mcp.tool()
def connect(conn_str: str = DEFAULT_CONN) -> dict:
    """Connect to a vehicle. conn_str examples: 'udp:127.0.0.1:14550' (SITL),
    'tcp:127.0.0.1:5760', 'serial:/dev/ttyACM0:115200'. Default is local SITL."""
    global _conn
    if _conn is not None:
        _conn.stop()
    _conn = MavlinkConnection(
        conn_str,
        actuation_enabled=_conn.gate.actuation_enabled if _conn else False,
        allow_real_vehicle=_conn.gate.allow_real_vehicle if _conn else False,
    )
    _conn.start()
    return {"connected": True, "conn_str": conn_str, "link_kind": _conn.link_kind}


@mcp.tool()
def vehicle_state() -> dict:
    """Current vehicle snapshot: mode, armed, GPS fix/sats, battery, attitude,
    position. Reads from cached telemetry — returns instantly."""
    return _require_conn().vehicle_state()


@mcp.tool()
def recent_statustext(n: int = 10) -> list[dict]:
    """Last n STATUSTEXT / prearm messages, newest first. The no-arm diagnostic
    goldmine — read this to see why a vehicle refuses to arm."""
    return _require_conn().recent_statustext(n)


# ---------------------------------------------------------------------- #
# params
# ---------------------------------------------------------------------- #
@mcp.tool()
def get_param(name: str) -> dict:
    """Read one parameter by exact name (e.g. 'ATC_RAT_RLL_P')."""
    val = _require_conn().get_param(name)
    return {"name": name, "value": val, "found": val is not None}


@mcp.tool()
def set_param(name: str, value: float) -> dict:
    """Set one parameter and confirm via the echoed PARAM_VALUE."""
    ok = _require_conn().set_param(name, value)
    return {"name": name, "value": value, "confirmed": ok}


@mcp.tool()
def list_params(glob: str | None = None) -> dict:
    """List parameters, optionally filtered by glob (e.g. 'ATC_RAT_*'). Without a
    glob this fetches the full table — slow on first call."""
    return _require_conn().list_params(glob)


@mcp.tool()
def set_mode(mode: str) -> dict:
    """Set flight mode by name (e.g. 'GUIDED', 'STABILIZE', 'RTL')."""
    _require_conn().set_mode(mode)
    return {"mode": mode, "set": True}


# ---------------------------------------------------------------------- #
# gated actuation — OFF unless started with --enable-actuation
# ---------------------------------------------------------------------- #
@mcp.tool()
def arm() -> dict:
    """ARM the vehicle. Gated: requires --enable-actuation, and on a real link
    also --allow-real-vehicle. Can move hardware."""
    try:
        _require_conn().arm()
        return {"armed": True}
    except ActuationDenied as e:
        return {"armed": False, "denied": str(e)}


@mcp.tool()
def disarm() -> dict:
    """DISARM the vehicle. Same gating as arm()."""
    try:
        _require_conn().disarm()
        return {"armed": False}
    except ActuationDenied as e:
        return {"denied": str(e)}


# ---------------------------------------------------------------------- #
# live telemetry resource
# ---------------------------------------------------------------------- #
@mcp.resource("mavlink://telemetry")
def telemetry() -> str:
    """Live telemetry snapshot as JSON (same data as vehicle_state)."""
    if _conn is None or _conn.master is None:
        return json.dumps({"connected": False})
    return json.dumps(_conn.vehicle_state())


# ---------------------------------------------------------------------- #
# entrypoint
# ---------------------------------------------------------------------- #
def _build_conn(args) -> MavlinkConnection:
    return MavlinkConnection(
        args.connect,
        actuation_enabled=args.enable_actuation,
        allow_real_vehicle=args.allow_real_vehicle,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="MAVLink/ArduPilot MCP server (SITL-first).")
    parser.add_argument(
        "--connect",
        default=os.environ.get("MAVLINK_MCP_CONNECT", DEFAULT_CONN),
        help=f"Connection string (default: {DEFAULT_CONN}, i.e. local SITL).",
    )
    parser.add_argument(
        "--enable-actuation",
        action="store_true",
        help="Allow arm/disarm/command_long. OFF by default.",
    )
    parser.add_argument(
        "--allow-real-vehicle",
        action="store_true",
        help="Allow actuation on a real (non-SITL) link. Requires --enable-actuation.",
    )
    parser.add_argument(
        "--no-autoconnect",
        action="store_true",
        help="Start the server without connecting; call the connect tool later.",
    )
    args = parser.parse_args()

    global _conn
    _conn = _build_conn(args)
    if not args.no_autoconnect:
        _conn.start()

    mcp.run()


if __name__ == "__main__":
    main()
