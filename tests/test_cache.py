"""Tests for the thread-safe message cache."""

from __future__ import annotations

import threading

from ardupilot_mcp.cache import MessageCache

from .conftest import FakeMsg


def test_latest_returns_none_for_unseen_type():
    cache = MessageCache()
    assert cache.latest("ATTITUDE") is None


def test_update_stores_latest_of_type():
    cache = MessageCache()
    cache.update(FakeMsg("ATTITUDE", roll=0.1))
    cache.update(FakeMsg("ATTITUDE", roll=0.2))
    msg = cache.latest("ATTITUDE")
    assert msg.roll == 0.2


def test_different_types_kept_separately():
    cache = MessageCache()
    cache.update(FakeMsg("ATTITUDE", roll=0.1))
    cache.update(FakeMsg("SYS_STATUS", voltage_battery=12000))
    assert cache.latest("ATTITUDE").roll == 0.1
    assert cache.latest("SYS_STATUS").voltage_battery == 12000


def test_types_reports_seen_types():
    cache = MessageCache()
    cache.update(FakeMsg("HEARTBEAT"))
    cache.update(FakeMsg("GPS_RAW_INT"))
    assert cache.types() == {"HEARTBEAT", "GPS_RAW_INT"}


def test_statustext_goes_to_ring_buffer_not_latest_slot():
    cache = MessageCache()
    cache.update(FakeMsg("STATUSTEXT", severity=4, text="PreArm: GPS"))
    # STATUSTEXT is a stream, not a single-latest value; recent() exposes it.
    assert cache.recent_statustext(5) == [{"severity": 4, "text": "PreArm: GPS"}]


def test_statustext_recent_returns_last_n_newest_first():
    cache = MessageCache()
    for i in range(5):
        cache.update(FakeMsg("STATUSTEXT", severity=6, text=f"msg{i}"))
    recent = cache.recent_statustext(2)
    assert [e["text"] for e in recent] == ["msg4", "msg3"]


def test_statustext_ring_buffer_caps_size():
    cache = MessageCache(statustext_maxlen=3)
    for i in range(10):
        cache.update(FakeMsg("STATUSTEXT", severity=6, text=f"msg{i}"))
    recent = cache.recent_statustext(100)
    assert len(recent) == 3
    assert [e["text"] for e in recent] == ["msg9", "msg8", "msg7"]


def test_concurrent_updates_do_not_corrupt():
    cache = MessageCache()

    def writer(start):
        for i in range(1000):
            cache.update(FakeMsg("ATTITUDE", roll=start + i))

    threads = [threading.Thread(target=writer, args=(s,)) for s in (0, 10000)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # No assertion on value (race is fine); the point is no crash / no torn state.
    assert cache.latest("ATTITUDE") is not None
