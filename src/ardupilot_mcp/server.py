"""FastMCP server exposing the ArduPilot/MAVLink tools.

SITL-first: the default connection target is local SITL. Actuation tools are
registered but gated (see ``safety.py``). All logging goes to stderr so stdout
stays pure JSON-RPC for the stdio transport.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .connection import MavlinkConnection
from .safety import ActuationDenied

DEFAULT_CONN = "tcp:127.0.0.1:5760"  # ArduPilot SITL's native serve port

log = logging.getLogger("ardupilot_mcp")

mcp = FastMCP("ardupilot-mcp")

READ_ONLY = ToolAnnotations(readOnlyHint=True)
ACTUATING = ToolAnnotations(destructiveHint=True)

# Process-wide connection, configured by main() before mcp.run().
_conn: MavlinkConnection | None = None


def _require_conn() -> MavlinkConnection:
    if _conn is None or _conn.master is None:
        raise RuntimeError("Not connected. Call ardupilot_connect first.")
    return _conn


# ---------------------------------------------------------------------- #
# connection
# ---------------------------------------------------------------------- #
@mcp.tool(name="ardupilot_connect")
def connect(conn_str: str = DEFAULT_CONN) -> dict:
    """Connect to a vehicle.

    Args:
        conn_str: pymavlink connection string. Examples: 'tcp:127.0.0.1:5760'
            (SITL), 'udp:127.0.0.1:14550', 'serial:/dev/ttyACM0:115200'.
            Defaults to local SITL.
    """
    global _conn
    actuation = _conn.gate.actuation_enabled if _conn else False
    allow_real = _conn.gate.allow_real_vehicle if _conn else False
    if _conn is not None:
        _conn.stop()
    _conn = MavlinkConnection(conn_str, actuation_enabled=actuation, allow_real_vehicle=allow_real)
    _conn.start()
    return {"connected": True, "conn_str": conn_str, "link_kind": _conn.link_kind}


@mcp.tool(name="ardupilot_vehicle_state", annotations=READ_ONLY)
def vehicle_state() -> dict:
    """Current vehicle snapshot: mode, armed, GPS fix/sats, battery, attitude,
    position. Reads from cached telemetry and returns immediately."""
    return _require_conn().vehicle_state()


@mcp.tool(name="ardupilot_recent_statustext", annotations=READ_ONLY)
def recent_statustext(n: int = 10) -> list[dict]:
    """Recent STATUSTEXT / prearm messages, newest first.

    This is how you diagnose a no-arm: when arming is refused, the reason
    appears here (e.g. 'PreArm: GPS not healthy').

    Args:
        n: how many recent messages to return.
    """
    return _require_conn().recent_statustext(n)


# ---------------------------------------------------------------------- #
# params
# ---------------------------------------------------------------------- #
@mcp.tool(name="ardupilot_get_param", annotations=READ_ONLY)
def get_param(name: str) -> dict:
    """Read one parameter by exact name.

    Args:
        name: parameter name, e.g. 'ATC_RAT_RLL_P'.
    """
    val = _require_conn().get_param(name)
    return {"name": name, "value": val, "found": val is not None}


@mcp.tool(name="ardupilot_set_param", annotations=ACTUATING)
def set_param(name: str, value: float) -> dict:
    """Set one parameter and confirm via the echoed PARAM_VALUE.

    Args:
        name: parameter name.
        value: new value (transported as float32).
    """
    ok = _require_conn().set_param(name, value)
    return {"name": name, "value": value, "confirmed": ok}


@mcp.tool(name="ardupilot_list_params", annotations=READ_ONLY)
def list_params(glob: str | None = None) -> dict:
    """List parameters, optionally filtered by glob.

    Args:
        glob: shell glob to filter names, e.g. 'ATC_RAT_*'. Without a glob this
            fetches the full table, which is slow on first call.
    """
    return _require_conn().list_params(glob)


@mcp.tool(name="ardupilot_set_mode", annotations=ACTUATING)
def set_mode(mode: str) -> dict:
    """Send a request to set flight mode by name.

    This reports that the command was sent; it does not confirm the resulting
    mode from a subsequent heartbeat.

    Args:
        mode: mode name, e.g. 'GUIDED', 'STABILIZE', 'RTL'. Valid names depend
            on the vehicle type.
    """
    _require_conn().set_mode(mode)
    return {"mode": mode, "command_sent": True}


# ---------------------------------------------------------------------- #
# gated actuation — OFF unless started with --enable-actuation
# ---------------------------------------------------------------------- #
_RESULT_NAMES = {
    0: "ACCEPTED",
    1: "TEMPORARILY_REJECTED",
    2: "DENIED",
    3: "UNSUPPORTED",
    4: "FAILED",
    5: "IN_PROGRESS",
}


def _arm_result(conn, value: int) -> dict:
    result = conn.arm() if value else conn.disarm()
    accepted = result == 0
    out = {
        "command": "arm" if value else "disarm",
        "accepted": accepted,
        "result_code": result,
        "result": _RESULT_NAMES.get(result, "NO_ACK" if result is None else str(result)),
    }
    if not accepted:
        # The vehicle refused (or didn't ack). Surface the prearm reason.
        out["recent_statustext"] = conn.recent_statustext(5)
    return out


@mcp.tool(name="ardupilot_arm", annotations=ACTUATING)
def arm() -> dict:
    """ARM the vehicle, confirmed via COMMAND_ACK.

    Gated: requires --enable-actuation, and on a real link also
    --allow-real-vehicle. Safety checks are respected (no force-arm). If the
    vehicle refuses, the prearm STATUSTEXT is returned so you can diagnose it.
    """
    try:
        return _arm_result(_require_conn(), 1)
    except ActuationDenied as e:
        return {"command": "arm", "accepted": False, "denied": str(e)}


@mcp.tool(name="ardupilot_disarm", annotations=ACTUATING)
def disarm() -> dict:
    """DISARM the vehicle, confirmed via COMMAND_ACK. Same gating as arm."""
    try:
        return _arm_result(_require_conn(), 0)
    except ActuationDenied as e:
        return {"command": "disarm", "accepted": False, "denied": str(e)}


# ---------------------------------------------------------------------- #
# live telemetry resource
# ---------------------------------------------------------------------- #
@mcp.resource("ardupilot://telemetry")
def telemetry() -> str:
    """Live telemetry snapshot as JSON (same data as ardupilot_vehicle_state)."""
    if _conn is None or _conn.master is None:
        return json.dumps({"connected": False})
    return json.dumps(_conn.vehicle_state())


# ---------------------------------------------------------------------- #
# entrypoint
# ---------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="ArduPilot/MAVLink MCP server (SITL-first).")
    parser.add_argument(
        "--connect",
        default=os.environ.get("ARDUPILOT_MCP_CONNECT", DEFAULT_CONN),
        help=f"Connection string (default: {DEFAULT_CONN}, i.e. local SITL).",
    )
    parser.add_argument(
        "--enable-actuation",
        action="store_true",
        help="Allow arm/disarm/set_param/set_mode. OFF by default.",
    )
    parser.add_argument(
        "--allow-real-vehicle",
        action="store_true",
        help="Allow actuation on a real (non-SITL) link. Requires --enable-actuation.",
    )
    parser.add_argument(
        "--no-autoconnect",
        action="store_true",
        help="Start the server without connecting; call ardupilot_connect later.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s: %(message)s")

    global _conn
    _conn = MavlinkConnection(
        args.connect,
        actuation_enabled=args.enable_actuation,
        allow_real_vehicle=args.allow_real_vehicle,
    )
    if not args.no_autoconnect:
        log.info("connecting to %s (actuation=%s)", args.connect, args.enable_actuation)
        _conn.start()
        log.info("connected: link_kind=%s", _conn.link_kind)

    mcp.run()


if __name__ == "__main__":
    main()
