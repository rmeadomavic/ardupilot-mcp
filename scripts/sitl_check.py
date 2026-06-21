"""Validate mavlink-mcp against a real ArduPilot SITL instance.

Unlike wire_check.py (a fake pymavlink vehicle), this drives the live
MavlinkConnection against a genuine ArduPilot stack: real param table, real
boot/prearm STATUSTEXT, real mode logic, real arming checks. This is the
no-arm-diagnosis demo end to end.

Prereq: an ArduPilot SITL binary listening on tcp:127.0.0.1:5760, e.g.
    build/sitl/bin/arducopter --model quad --speedup 10 \
        --defaults Tools/autotest/default_params/copter.parm -I0

Run:  python scripts/sitl_check.py [tcp:127.0.0.1:5760]
"""

from __future__ import annotations

import json
import sys
import time

from mavlink_mcp.connection import MavlinkConnection


def main() -> int:
    conn_str = sys.argv[1] if len(sys.argv) > 1 else "tcp:127.0.0.1:5760"
    print(f"Connecting to real SITL at {conn_str} ...")
    c = MavlinkConnection(conn_str, actuation_enabled=True)
    c.start()
    print(f"  heartbeat OK. link_kind={c.link_kind}")
    time.sleep(3)  # let telemetry + boot STATUSTEXT accumulate

    print("\n== vehicle_state ==")
    print(json.dumps(c.vehicle_state(), indent=2))

    print("\n== real params (targeted gets) ==")
    for name in ("FRAME_CLASS", "WPNAV_SPEED", "ARMING_CHECK", "BATT_MONITOR"):
        print(f"  {name} = {c.get_param(name, timeout=5)}")

    # prove set_param round-trips on the real stack
    orig = c.get_param("WPNAV_SPEED", timeout=5)
    c.set_param("WPNAV_SPEED", 600.0, timeout=5)
    print(f"  WPNAV_SPEED {orig} -> {c.get_param('WPNAV_SPEED', timeout=5)} (set confirmed)")

    print("\n== recent STATUSTEXT (real boot/prearm stream) ==")
    for e in c.recent_statustext(15):
        print(f"  [{e['severity']}] {e['text']}")

    print("\n== set_mode GUIDED ==")
    try:
        c.set_mode("GUIDED")
        time.sleep(1.5)
        print(f"  mode now: {c.vehicle_state()['mode']}")
    except ValueError as e:
        print(f"  {e}")

    print("\n== ARM attempt (the no-arm-diagnosis demo) ==")
    res = c.arm(timeout=6)
    names = {0: "ACCEPTED", 1: "TEMP_REJECTED", 2: "DENIED", 4: "FAILED"}
    print(f"  arm result: {names.get(res, res)}")
    if res != 0:
        print("  vehicle refused — prearm reasons:")
        for e in c.recent_statustext(10):
            if "rm" in e["text"].lower() or e["severity"] <= 4:
                print(f"    [{e['severity']}] {e['text']}")

    c.stop()
    print("\nRESULT: connected to real ArduPilot SITL and exercised the full v1 surface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
