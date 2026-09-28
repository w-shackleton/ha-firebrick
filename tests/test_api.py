"""Tests for FireBrick response parsing."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.firebrick.api import (
    FirebrickConnectionError,
    parse_cqm,
    parse_cqm_index,
    parse_pppoe,
    parse_ports,
    parse_uptime,
)

from .conftest import load_fixture


def test_parse_ports() -> None:
    """Ports XML yields link state and byte counters per physical port."""
    firmware, ports = parse_ports(load_fixture("ports_1.xml"))

    assert firmware == "FB2900 Gallox (V2.06.029 2026-09-22T10:02:40)"
    assert sorted(ports) == [1, 2, 3, 4, 5]

    wan = ports[1]
    assert wan.portgroup == "WAN4"
    assert wan.link_up
    assert wan.speed == "1G"
    assert wan.rx_bytes == 428926764214
    assert wan.tx_bytes == 196432283661

    unused = ports[2]
    assert unused.portgroup is None
    assert not unused.link_up
    assert unused.rx_bytes is None


def test_parse_pppoe() -> None:
    """PPPoE XML yields sessions keyed by name."""
    sessions = parse_pppoe(load_fixture("pppoe.xml"))

    session = sessions["PPPoE"]
    assert session.is_up
    assert session.port == "WAN"
    assert session.uptime == timedelta(days=5, hours=21, minutes=56, seconds=51)
    assert session.local_ip == "217.169.28.72"
    assert session.graph == "pppoe"


def test_parse_cqm() -> None:
    """CQM JSON yields totals and the newest sample with latency."""
    assert parse_cqm_index(load_fixture("cqm_index.html")) == ["pppoe", "home"]

    graph = parse_cqm("pppoe", load_fixture("cqm_pppoe.json"))
    assert graph.rx_bytes == 419408906059
    assert graph.tx_bytes == 189621470775
    assert graph.latest is not None
    assert graph.latest.ave_latency_ms == pytest.approx(4.605)
    assert graph.latest.packet_loss == 0

    # Interface graphs carry throughput but no latency polls.
    home = parse_cqm("home", load_fixture("cqm_home.json"))
    assert home.rx_bytes == 191082571090
    assert home.latest is None


def test_parse_cqm_packet_loss() -> None:
    """Lost polls are reported as a percentage."""
    graph = parse_cqm(
        "x",
        '{"data": [{"timestamp": "2026-09-28T11:25:00Z", "sent-polls": 10,'
        ' "lost-polls": 1, "ave-latency-ns": 32470000}, {"timestamp":'
        ' "2026-09-28T11:26:40Z", "ave-rx-bps": 1}]}',
    )
    assert graph.latest is not None
    assert graph.latest.packet_loss == 10
    assert graph.latest.min_latency_ms is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5:21:55:43", timedelta(days=5, hours=21, minutes=55, seconds=43)),
        ("0:00:00:08", timedelta(seconds=8)),
        ("01:02:03", timedelta(hours=1, minutes=2, seconds=3)),
        ("", None),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_uptime(value: str | None, expected: timedelta | None) -> None:
    """Uptime strings are parsed as d:hh:mm:ss."""
    assert parse_uptime(value) == expected


def test_invalid_xml() -> None:
    """Non-XML responses raise a connection error."""
    with pytest.raises(FirebrickConnectionError):
        parse_pppoe("<html>login</html")
