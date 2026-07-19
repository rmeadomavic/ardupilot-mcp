"""Tests for the actuation safety gate.

The gate is the repository's non-negotiable safety layer:
- actuation tools are OFF by default
- even when enabled, refuse on a real (non-loopback) link unless a second
  explicit flag is set.
"""

from __future__ import annotations

import pytest

from ardupilot_mcp.safety import ActuationDenied, SafetyGate, classify_link


@pytest.mark.parametrize(
    "conn_str",
    [
        "udp:127.0.0.1:14550",
        "udpin:127.0.0.1:14550",
        "tcp:localhost:5760",
        "udp:0.0.0.0:14550",  # bind-any inbound is still a local socket
    ],
)
def test_loopback_links_classified_local(conn_str):
    assert classify_link(conn_str) == "local"


@pytest.mark.parametrize(
    "conn_str",
    [
        "serial:/dev/ttyACM0:115200",
        "serial:COM7:57600",
        "udp:192.168.1.50:14550",
        "tcp:10.0.0.7:5760",
    ],
)
def test_serial_and_remote_ip_classified_real(conn_str):
    assert classify_link(conn_str) == "real"


def test_actuation_denied_by_default():
    gate = SafetyGate(actuation_enabled=False, allow_real_vehicle=False)
    with pytest.raises(ActuationDenied):
        gate.check("local")


def test_actuation_allowed_on_local_when_enabled():
    gate = SafetyGate(actuation_enabled=True, allow_real_vehicle=False)
    gate.check("local")  # should not raise


def test_actuation_denied_on_real_link_without_real_flag():
    gate = SafetyGate(actuation_enabled=True, allow_real_vehicle=False)
    with pytest.raises(ActuationDenied):
        gate.check("real")


def test_actuation_allowed_on_real_link_with_both_flags():
    gate = SafetyGate(actuation_enabled=True, allow_real_vehicle=True)
    gate.check("real")  # should not raise


def test_real_flag_alone_does_not_enable_actuation():
    gate = SafetyGate(actuation_enabled=False, allow_real_vehicle=True)
    with pytest.raises(ActuationDenied):
        gate.check("local")
