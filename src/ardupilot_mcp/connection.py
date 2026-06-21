"""MavlinkConnection: the async-stream-to-sync-cache bridge.

A background thread owns the mavutil link and is the *only* reader. It pumps
every message into the cache and routes PARAM_VALUE into the param store. Tool
calls read from those stores and, for params, can block until the requested
data arrives — never touching the link directly, so there's no concurrent
``recv_match`` from two threads.
"""

from __future__ import annotations

import threading
from typing import Any

from .cache import MessageCache
from .params import ParamStore
from .safety import SafetyGate, classify_link

# Message types worth caching as "latest of type" for vehicle_state.
_CACHE_TYPES = {
    "HEARTBEAT",
    "SYS_STATUS",
    "GPS_RAW_INT",
    "GLOBAL_POSITION_INT",
    "ATTITUDE",
    "VFR_HUD",
    "EKF_STATUS_REPORT",
    "BATTERY_STATUS",
    "STATUSTEXT",
}


class MavlinkConnection:
    def __init__(
        self,
        conn_str: str,
        *,
        master: Any | None = None,
        source_system: int = 255,
        actuation_enabled: bool = False,
        allow_real_vehicle: bool = False,
        recv_timeout: float = 0.5,
        stream_rate_hz: int = 4,
    ) -> None:
        self.conn_str = conn_str
        self.link_kind = classify_link(conn_str)
        self._injected_master = master
        self._source_system = source_system
        self._recv_timeout = recv_timeout
        self._stream_rate_hz = stream_rate_hz

        self.master: Any | None = master
        self.cache = MessageCache()
        self.params = ParamStore()
        self.gate = SafetyGate(
            actuation_enabled=actuation_enabled,
            allow_real_vehicle=allow_real_vehicle,
        )

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # COMMAND_ACK correlation: command id -> result code.
        self._ack_cond = threading.Condition()
        self._acks: dict[int, int] = {}

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self.master is None:
            from pymavlink import mavutil

            self.master = mavutil.mavlink_connection(
                self.conn_str, source_system=self._source_system
            )
            self.master.wait_heartbeat(timeout=30)
        self._stop.clear()
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        self._request_streams()

    def _request_streams(self) -> None:
        """Ask the vehicle to stream telemetry.

        ArduPilot will not necessarily push ATTITUDE/GLOBAL_POSITION_INT/
        SYS_STATUS to a freshly connected link, which would leave the cache
        (and vehicle_state) empty. REQUEST_DATA_STREAM is deprecated but still
        honored by ArduPilot and is the most compatible nudge.
        """
        try:
            from pymavlink import mavutil

            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                self._stream_rate_hz,
                1,
            )
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self.master is not None:
            try:
                self.master.close()
            except Exception:
                pass

    def _recv_loop(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self.master.recv_match(blocking=True, timeout=self._recv_timeout)
            except Exception:
                continue
            if msg is None:
                continue
            msg_type = msg.get_type()
            if msg_type == "PARAM_VALUE":
                self.params.apply(msg)
            elif msg_type == "COMMAND_ACK":
                self._record_ack(msg)
            self.cache.update(msg)

    def _record_ack(self, msg: Any) -> None:
        with self._ack_cond:
            self._acks[int(msg.command)] = int(msg.result)
            self._ack_cond.notify_all()

    def _wait_ack(self, command: int, timeout: float) -> int | None:
        """Block for the COMMAND_ACK result of ``command``, or None on timeout."""
        with self._ack_cond:
            ok = self._ack_cond.wait_for(lambda: command in self._acks, timeout=timeout)
            return self._acks.get(command) if ok else None

    # ------------------------------------------------------------------ #
    # read tools
    # ------------------------------------------------------------------ #
    def recent_statustext(self, n: int = 10) -> list[dict[str, Any]]:
        return self.cache.recent_statustext(n)

    def vehicle_state(self) -> dict[str, Any]:
        """Snapshot the vehicle from cached telemetry. Missing fields are None."""
        hb = self.cache.latest("HEARTBEAT")
        sys_status = self.cache.latest("SYS_STATUS")
        gps = self.cache.latest("GPS_RAW_INT")
        pos = self.cache.latest("GLOBAL_POSITION_INT")
        att = self.cache.latest("ATTITUDE")

        armed = None
        mode = None
        if hb is not None:
            from pymavlink import mavutil

            base_mode = getattr(hb, "base_mode", 0)
            armed = bool(base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            mode = self._mode_name(getattr(hb, "custom_mode", None))

        return {
            "connected": self.master is not None,
            "link_kind": self.link_kind,
            "armed": armed,
            "mode": mode,
            "gps_fix": getattr(gps, "fix_type", None) if gps else None,
            "satellites": getattr(gps, "satellites_visible", None) if gps else None,
            "battery_voltage_v": (
                getattr(sys_status, "voltage_battery", None) / 1000.0
                if sys_status and getattr(sys_status, "voltage_battery", None) not in (None, -1)
                else None
            ),
            "battery_remaining_pct": (
                getattr(sys_status, "battery_remaining", None) if sys_status else None
            ),
            "attitude": (
                {
                    "roll": getattr(att, "roll", None),
                    "pitch": getattr(att, "pitch", None),
                    "yaw": getattr(att, "yaw", None),
                }
                if att
                else None
            ),
            "position": (
                {
                    "lat": getattr(pos, "lat", None) / 1e7 if pos else None,
                    "lon": getattr(pos, "lon", None) / 1e7 if pos else None,
                    "alt_m": getattr(pos, "alt", None) / 1000.0 if pos else None,
                }
                if pos
                else None
            ),
        }

    # ------------------------------------------------------------------ #
    # param tools
    # ------------------------------------------------------------------ #
    def get_param(self, name: str, timeout: float = 5.0) -> float | None:
        self.master.mav.param_request_read_send(
            self.master.target_system,
            self.master.target_component,
            name.encode("ascii"),
            -1,
        )
        return self.params.wait_for(name, timeout=timeout)

    def set_param(self, name: str, value: float, timeout: float = 5.0) -> bool:
        self.master.param_set_send(name, float(value))
        return self.params.wait_for_value(name, float(value), timeout=timeout)

    def list_params(self, glob: str | None = None, timeout: float = 30.0) -> dict[str, float]:
        self.master.mav.param_request_list_send(
            self.master.target_system, self.master.target_component
        )
        self.params.wait_complete(timeout=timeout)
        return self.params.match(glob) if glob else self.params.all()

    # ------------------------------------------------------------------ #
    # mode
    # ------------------------------------------------------------------ #
    def _mode_map(self) -> dict[str, int]:
        try:
            return self.master.mode_mapping() or {}
        except Exception:
            return {}

    def _mode_name(self, custom_mode: int | None) -> str | None:
        if custom_mode is None:
            return None
        for name, mid in self._mode_map().items():
            if mid == custom_mode:
                return name
        return str(custom_mode)

    def set_mode(self, mode: str) -> None:
        mapping = self._mode_map()
        key = mode.upper()
        if key not in mapping:
            raise ValueError(f"Unknown mode {mode!r}. Known: {', '.join(sorted(mapping))}")
        self.master.set_mode(mapping[key])

    # ------------------------------------------------------------------ #
    # gated actuation
    # ------------------------------------------------------------------ #
    def arm(self, timeout: float = 3.0) -> int | None:
        """ARM via MAV_CMD_COMPONENT_ARM_DISARM, confirmed by COMMAND_ACK.

        Returns the MAV_RESULT code (0 == ACCEPTED) or None if no ack arrived.
        A non-zero/None result means the vehicle did NOT arm — check
        recent_statustext() for the prearm reason.
        """
        return self._arm_disarm(1, timeout)

    def disarm(self, timeout: float = 3.0) -> int | None:
        """DISARM, confirmed by COMMAND_ACK. Returns MAV_RESULT (0 == ACCEPTED)."""
        return self._arm_disarm(0, timeout)

    def _arm_disarm(self, value: int, timeout: float) -> int | None:
        self.gate.check(self.link_kind)
        from pymavlink import mavutil

        cmd = mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
        with self._ack_cond:
            self._acks.pop(cmd, None)  # drop any stale ack before sending
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            cmd,
            0,  # confirmation
            value,  # param1: 1 arm, 0 disarm
            0,
            0,
            0,
            0,
            0,
            0,
        )
        return self._wait_ack(cmd, timeout)
