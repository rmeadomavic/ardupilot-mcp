"""Tests for MavlinkConnection using an injected fake master (no real link)."""

from __future__ import annotations

import queue
import time

import pytest

from ardupilot_mcp.connection import MavlinkConnection
from ardupilot_mcp.safety import ActuationDenied

from .conftest import FakeMsg


def _pv(name, value, count=3, index=0):
    return FakeMsg(
        "PARAM_VALUE",
        param_id=name,
        param_value=value,
        param_count=count,
        param_index=index,
    )


class FakeMaster:
    """Stand-in for a mavutil connection. Drives recv from an inbox queue and
    records every send so tests can assert on protocol behavior."""

    def __init__(self):
        self.target_system = 1
        self.target_component = 1
        self.mav = self
        self.sent = []
        self.closed = False
        self._inbox = queue.Queue()
        self._modes = {"STABILIZE": 0, "GUIDED": 4, "LOITER": 5, "RTL": 6}

    # --- recv side ---
    def feed(self, msg):
        self._inbox.put(msg)

    def recv_match(self, blocking=False, timeout=None, type=None):
        try:
            return self._inbox.get(timeout=timeout or 0.01)
        except queue.Empty:
            return None

    # --- send side (mav.*_send and mavutil helpers) ---
    def param_request_read_send(self, ts, tc, name, index):
        nm = name.decode() if isinstance(name, bytes) else name
        nm = nm.split("\x00", 1)[0]
        self.sent.append(("read", nm))
        self.feed(_pv(nm, 0.135))

    def param_request_list_send(self, ts, tc):
        self.sent.append(("list",))
        self.feed(_pv("A", 1.0, count=2, index=0))
        self.feed(_pv("B", 2.0, count=2, index=1))

    def param_set_send(self, name, value, parm_type=None):
        self.sent.append(("set", name, value))
        self.feed(_pv(name, value))

    def mode_mapping(self):
        return dict(self._modes)

    def set_mode(self, mode_id):
        self.sent.append(("mode", mode_id))

    def request_data_stream_send(self, ts, tc, stream_id, rate, start):
        self.sent.append(("stream", rate, start))

    def command_long_send(self, ts, tc, command, confirmation, p1, *rest):
        # Arm/disarm command (400). param1: 1 arm, 0 disarm. Echo a COMMAND_ACK.
        if command == 400:
            self.sent.append(("arm" if p1 == 1 else "disarm",))
            self.feed(FakeMsg("COMMAND_ACK", command=400, result=self.next_ack_result))
        else:
            self.sent.append(("cmd", command))

    # result the simulated vehicle returns for the next arm/disarm (0 == ACCEPTED)
    next_ack_result = 0

    def close(self):
        self.closed = True


@pytest.fixture
def conn():
    master = FakeMaster()
    c = MavlinkConnection("udp:127.0.0.1:14550", master=master)
    c.start()
    yield c
    c.stop()


@pytest.fixture
def conn_act():
    """Connection with actuation explicitly enabled, for gated-path happy tests."""
    master = FakeMaster()
    c = MavlinkConnection("udp:127.0.0.1:14550", master=master, actuation_enabled=True)
    c.start()
    yield c
    c.stop()


def test_link_kind_from_conn_str():
    c = MavlinkConnection("serial:COM7:57600", master=FakeMaster())
    assert c.link_kind == "real"


def test_recv_loop_caches_messages(conn):
    conn.master.feed(FakeMsg("ATTITUDE", roll=0.5, pitch=0.0, yaw=1.0))
    time.sleep(0.1)
    assert conn.cache.latest("ATTITUDE").roll == 0.5


def test_statustext_flows_to_cache(conn):
    conn.master.feed(FakeMsg("STATUSTEXT", severity=4, text="PreArm: 3D fix"))
    time.sleep(0.1)
    assert conn.recent_statustext(5)[0]["text"] == "PreArm: 3D fix"


def test_get_param_requests_and_returns(conn):
    val = conn.get_param("ATC_RAT_RLL_P", timeout=2.0)
    assert val == 0.135
    assert ("read", "ATC_RAT_RLL_P") in conn.master.sent


def test_set_param_confirms_echo(conn_act):
    ok = conn_act.set_param("WPNAV_SPEED", 750.0, timeout=2.0)
    assert ok is True
    assert ("set", "WPNAV_SPEED", 750.0) in conn_act.master.sent


def test_set_param_denied_on_real_link_without_real_flag():
    master = FakeMaster()
    c = MavlinkConnection("serial:COM7:57600", master=master, actuation_enabled=True)
    with pytest.raises(ActuationDenied):
        c.set_param("WPNAV_SPEED", 750.0)
    assert ("set", "WPNAV_SPEED", 750.0) not in master.sent


@pytest.mark.parametrize("conn_str", ["udp:127.0.0.1:14550", "serial:COM7:57600"])
def test_set_param_rejects_arming_check_on_any_link(conn_str):
    master = FakeMaster()
    c = MavlinkConnection(
        conn_str,
        master=master,
        actuation_enabled=True,
        allow_real_vehicle=True,
    )
    with pytest.raises(ActuationDenied, match="ARMING_CHECK"):
        c.set_param("arming_check", 0)
    assert not any(sent[0] == "set" for sent in master.sent)


def test_list_params_collects_full_table(conn):
    params = conn.list_params(timeout=2.0)
    assert params == {"A": 1.0, "B": 2.0}


def test_set_mode_maps_name_to_id(conn_act):
    conn_act.set_mode("GUIDED")
    assert ("mode", 4) in conn_act.master.sent


def test_set_mode_denied_on_real_link_without_real_flag():
    master = FakeMaster()
    c = MavlinkConnection("serial:COM7:57600", master=master, actuation_enabled=True)
    with pytest.raises(ActuationDenied):
        c.set_mode("GUIDED")
    assert ("mode", 4) not in master.sent


def test_set_mode_rejects_unknown(conn_act):
    with pytest.raises(ValueError):
        conn_act.set_mode("WARP_SPEED")


def test_arm_denied_by_default(conn):
    with pytest.raises(ActuationDenied):
        conn.arm()
    assert ("arm",) not in conn.master.sent


def test_arm_allowed_when_actuation_enabled_returns_accepted():
    master = FakeMaster()
    c = MavlinkConnection("udp:127.0.0.1:14550", master=master, actuation_enabled=True)
    c.start()
    try:
        result = c.arm(timeout=2.0)
        assert result == 0  # MAV_RESULT_ACCEPTED
        assert ("arm",) in master.sent
    finally:
        c.stop()


def test_arm_reports_rejection_from_command_ack():
    master = FakeMaster()
    master.next_ack_result = 4  # MAV_RESULT_FAILED (e.g. prearm refused)
    c = MavlinkConnection("udp:127.0.0.1:14550", master=master, actuation_enabled=True)
    c.start()
    try:
        result = c.arm(timeout=2.0)
        assert result == 4  # the tool must surface the refusal, not claim success
    finally:
        c.stop()


def test_disarm_confirmed_via_ack():
    master = FakeMaster()
    c = MavlinkConnection("udp:127.0.0.1:14550", master=master, actuation_enabled=True)
    c.start()
    try:
        assert c.disarm(timeout=2.0) == 0
        assert ("disarm",) in master.sent
    finally:
        c.stop()


def test_arm_denied_on_real_link_without_real_flag():
    master = FakeMaster()
    c = MavlinkConnection("serial:COM7:57600", master=master, actuation_enabled=True)
    c.start()
    try:
        with pytest.raises(ActuationDenied):
            c.arm()
    finally:
        c.stop()


def test_start_requests_data_streams(conn):
    assert any(s[0] == "stream" for s in conn.master.sent)


def test_stop_closes_master(conn):
    conn.stop()
    assert conn.master.closed is True
