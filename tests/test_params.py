"""Tests for the param store (the request-then-collect accumulator)."""

from __future__ import annotations

import threading

from ardupilot_mcp.params import ParamStore

from .conftest import FakeMsg


def _pv(name, value, count=3, index=0):
    return FakeMsg(
        "PARAM_VALUE",
        param_id=name,
        param_value=value,
        param_count=count,
        param_index=index,
    )


def test_get_unknown_is_none():
    store = ParamStore()
    assert store.get("ATC_RAT_RLL_P") is None


def test_apply_then_get():
    store = ParamStore()
    store.apply(_pv("ATC_RAT_RLL_P", 0.135))
    assert store.get("ATC_RAT_RLL_P") == 0.135


def test_apply_overwrites_with_newer_value():
    store = ParamStore()
    store.apply(_pv("SERIAL1_BAUD", 57.0))
    store.apply(_pv("SERIAL1_BAUD", 115.0))
    assert store.get("SERIAL1_BAUD") == 115.0


def test_param_id_bytes_are_decoded_and_null_stripped():
    store = ParamStore()
    store.apply(_pv(b"WPNAV_SPEED\x00\x00\x00\x00\x00", 500.0))
    assert store.get("WPNAV_SPEED") == 500.0


def test_count_and_completeness():
    store = ParamStore()
    assert not store.is_complete()
    store.apply(_pv("A", 1.0, count=2, index=0))
    assert not store.is_complete()
    store.apply(_pv("B", 2.0, count=2, index=1))
    assert store.is_complete()


def test_glob_listing():
    store = ParamStore()
    store.apply(_pv("ATC_RAT_RLL_P", 0.1))
    store.apply(_pv("ATC_RAT_PIT_P", 0.2))
    store.apply(_pv("WPNAV_SPEED", 500.0))
    matched = store.match("ATC_RAT_*")
    assert matched == {"ATC_RAT_RLL_P": 0.1, "ATC_RAT_PIT_P": 0.2}


def test_wait_for_returns_when_value_arrives():
    store = ParamStore()

    def producer():
        store.apply(_pv("BATT_CAPACITY", 5000.0))

    t = threading.Timer(0.05, producer)
    t.start()
    assert store.wait_for("BATT_CAPACITY", timeout=2.0) == 5000.0
    t.join()


def test_wait_for_times_out_to_none():
    store = ParamStore()
    assert store.wait_for("NOPE", timeout=0.05) is None
