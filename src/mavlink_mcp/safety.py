"""Actuation safety gate — the non-negotiable layer.

Rules (from the build handover, do not relax):
1. Actuation tools (arm/disarm, raw command_long) are OFF by default.
2. Even when enabled, refuse on a *real* (non-loopback / serial) link unless a
   second explicit flag is set.

An agent must never arm or command a real vehicle by accident.
"""

from __future__ import annotations

LinkKind = str  # "local" | "real"

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}
_NET_SCHEMES = {"udp", "udpin", "udpout", "tcp", "tcpin", "tcpout"}


class ActuationDenied(RuntimeError):
    """Raised when an actuation request is blocked by the safety gate."""


def classify_link(conn_str: str) -> LinkKind:
    """Classify a pymavlink connection string as a 'local' or 'real' link.

    Local: a loopback network socket (SITL). Real: a serial port or a network
    socket pointed at a non-loopback host. Unknown shapes are treated as 'real'
    — fail safe toward more restriction, never less.
    """
    scheme, _, rest = conn_str.partition(":")
    scheme = scheme.lower()
    if scheme in _NET_SCHEMES:
        host = rest.split(":", 1)[0].strip()
        return "local" if host in _LOOPBACK_HOSTS else "real"
    # serial:, device path, or anything unrecognized → treat as a real vehicle.
    return "real"


class SafetyGate:
    """Decides whether actuation is permitted for the current link."""

    def __init__(self, *, actuation_enabled: bool, allow_real_vehicle: bool) -> None:
        self.actuation_enabled = actuation_enabled
        self.allow_real_vehicle = allow_real_vehicle

    def check(self, link_kind: LinkKind) -> None:
        """Raise ActuationDenied unless actuation is permitted on this link."""
        if not self.actuation_enabled:
            raise ActuationDenied(
                "Actuation is disabled. Start the server with actuation enabled "
                "to allow arm/disarm/command_long."
            )
        if link_kind == "real" and not self.allow_real_vehicle:
            raise ActuationDenied(
                "Refusing to actuate a real (non-SITL) vehicle. Set the "
                "allow-real-vehicle flag to override — this can move hardware."
            )
