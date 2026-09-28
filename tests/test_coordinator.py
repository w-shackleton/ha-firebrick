"""Tests for rate calculation."""

from __future__ import annotations

import pytest

from custom_components.firebrick.api import FirebrickStatus, parse_ports
from custom_components.firebrick.coordinator import byte_counters, compute_rates

from .conftest import load_fixture


def _counters(fixture: str) -> dict[str, int]:
    _, ports = parse_ports(load_fixture(fixture))
    return byte_counters(FirebrickStatus(firmware=None, ports=ports))


def test_rates_from_two_samples() -> None:
    """Rates are byte deltas converted to bits per second."""
    rates = compute_rates(_counters("ports_1.xml"), _counters("ports_2.xml"), 10.0)

    assert rates["port_1_rx"] == pytest.approx((428935098887 - 428926764214) * 8 / 10)
    assert rates["port_4_tx"] == pytest.approx((429498775121 - 429490127303) * 8 / 10)
    # Ports without counters produce nothing.
    assert "port_2_rx" not in rates


def test_counter_reset_skips_rate() -> None:
    """A counter going backwards (router reboot) yields no rate, not a negative one."""
    rates = compute_rates({"a": 1000, "b": 10}, {"a": 50, "b": 20}, 1.0)
    assert rates == {"b": 80.0}


def test_no_elapsed_time() -> None:
    """Zero elapsed time yields no rates."""
    assert compute_rates({"a": 1}, {"a": 2}, 0) == {}
