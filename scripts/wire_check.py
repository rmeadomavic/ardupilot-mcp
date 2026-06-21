"""Offline real-wire integration check — no ArduPilot/SITL required.

Spins up a minimal pymavlink "vehicle" on a real UDP socket and drives the
*real* MavlinkConnection path against it (master is None -> mavlink_connection +
wait_heartbeat + live recv loop + genuine MAVLink (de)serialization).

This validates everything the unit tests stub with a fake master: the actual
wire, the data-stream nudge, the param request/collect round trip, set-param
confirmation, STATUSTEXT flow, and arm via COMMAND_ACK. For real prearm logic
and the genuine param table, use scripts/sitl_check.py against ArduPilot SITL.

Run:  python scripts/wire_check.py
"""

from __future__ import annotations

import sys
import threading
import time

from pymavlink import mavutil

from ardupilot_mcp.connection import MavlinkConnection

PORT = 14650  # off the usual 14550 to avoid colliding with a real GCS


def fake_vehicle(stop: threading.Event) -> None:
    """A barebones MAVLink vehicle: heartbeats + telemetry, answers params and
    arm. Sends TO the GCS port (mirrors `sim_vehicle.py --out udp:host:PORT`)."""
    v = mavutil.mavlink_connection(f"udpout:127.0.0.1:{PORT}", source_system=1, source_component=1)
    params = {"ATC_RAT_RLL_P": 0.135, "WPNAV_SPEED": 500.0, "BATT_CAPACITY": 5000.0}
    last = 0.0
    while not stop.is_set():
        now = time.time()
        if now - last > 0.25:
            v.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_QUADROTOR,
                mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                0,
                0,  # custom_mode 0 -> STABILIZE for a quad
                mavutil.mavlink.MAV_STATE_STANDBY,
            )
            v.mav.attitude_send(0, 0.01, 0.02, 0.03, 0, 0, 0)
            # voltage_battery=12600 mV, current=-1, remaining=87%
            v.mav.sys_status_send(0, 0, 0, 0, 12600, -1, 87, 0, 0, 0, 0, 0, 0)
            v.mav.gps_raw_int_send(0, 3, int(35.1 * 1e7), int(-79.4 * 1e7), 100000, 0, 0, 0, 0, 11)
            v.mav.global_position_int_send(
                0, int(35.1 * 1e7), int(-79.4 * 1e7), 100000, 50000, 0, 0, 0, 0
            )
            v.mav.statustext_send(mavutil.mavlink.MAV_SEVERITY_WARNING, b"PreArm: GPS not healthy")
            last = now
        try:
            msg = v.recv_match(blocking=True, timeout=0.1)
        except OSError:
            # Windows raises WinError 10054 when the GCS socket closes; benign.
            break
        if msg is None:
            continue
        t = msg.get_type()
        if t == "PARAM_REQUEST_READ":
            name = msg.param_id
            name = name.decode() if isinstance(name, bytes) else name
            name = name.split("\x00", 1)[0]
            v.mav.param_value_send(
                name.encode("ascii"),
                params.get(name, 0.0),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
                len(params),
                0,
            )
        elif t == "PARAM_REQUEST_LIST":
            for i, (k, val) in enumerate(params.items()):
                v.mav.param_value_send(
                    k.encode("ascii"),
                    val,
                    mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
                    len(params),
                    i,
                )
        elif t == "PARAM_SET":
            name = msg.param_id
            name = name.decode() if isinstance(name, bytes) else name
            name = name.split("\x00", 1)[0]
            params[name] = msg.param_value
            v.mav.param_value_send(
                name.encode("ascii"),
                msg.param_value,
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
                len(params),
                0,
            )
        elif t == "COMMAND_LONG":
            v.mav.command_ack_send(msg.command, mavutil.mavlink.MAV_RESULT_ACCEPTED)


def main() -> int:
    stop = threading.Event()
    th = threading.Thread(target=fake_vehicle, args=(stop,), daemon=True)
    th.start()

    fails = []

    def check(label, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label} {detail}")
        if not cond:
            fails.append(label)

    print(f"Connecting MavlinkConnection to udpin:127.0.0.1:{PORT} (real path)...")
    c = MavlinkConnection(f"udpin:127.0.0.1:{PORT}", actuation_enabled=True)
    c.start()  # real path: mavlink_connection + wait_heartbeat(30)
    print("  heartbeat received, recv loop running")
    time.sleep(1.0)  # let telemetry populate the cache

    state = c.vehicle_state()
    check("link_kind local", state["link_kind"] == "local", state["link_kind"])
    check("mode decoded", state["mode"] == "STABILIZE", repr(state["mode"]))
    check("battery voltage", state["battery_voltage_v"] == 12.6, str(state["battery_voltage_v"]))
    check("gps sats", state["satellites"] == 11, str(state["satellites"]))
    check("attitude present", state["attitude"] is not None)
    check("position present", state["position"] is not None)

    val = c.get_param("ATC_RAT_RLL_P", timeout=5)
    # float32 wire precision: 0.135 round-trips to ~0.13500000536.
    check("get_param round trip", val is not None and abs(val - 0.135) < 1e-5, str(val))

    ok = c.set_param("WPNAV_SPEED", 750.0, timeout=5)
    check("set_param confirmed", ok is True)
    check("set_param new value", c.get_param("WPNAV_SPEED", timeout=5) == 750.0)

    allp = c.list_params(timeout=10)
    check("list_params full table", len(allp) >= 3, f"n={len(allp)}")

    st = c.recent_statustext(5)
    check(
        "statustext flow", any("PreArm" in e["text"] for e in st), st[0]["text"] if st else "(none)"
    )

    res = c.arm(timeout=5)
    check("arm COMMAND_ACK", res == 0, f"result={res}")

    c.stop()
    stop.set()
    th.join(timeout=2)

    print()
    if fails:
        print(f"RESULT: FAIL ({len(fails)}): {', '.join(fails)}")
        return 1
    print("RESULT: PASS — real MAVLink wire validated end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
