"""Tests for FireBrick entities."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

PREFIX = "firebrick_fb2900"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_firebrick", "mock_monotonic")
async def test_entities_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Entities reflect the captured router status."""
    await _setup(hass, mock_config_entry)

    assert hass.states.get(f"binary_sensor.{PREFIX}_port_1_link").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_port_2_link").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_pppoe_connected").state == STATE_ON

    assert hass.states.get(f"sensor.{PREFIX}_pppoe_ipv4_address").state == "217.169.28.72"
    assert hass.states.get(f"sensor.{PREFIX}_port_1_link_speed").state == "1G"

    # Counters are known immediately; rates need a second poll.
    received = hass.states.get(f"sensor.{PREFIX}_port_1_data_received")
    assert received.attributes["unit_of_measurement"] == "GB"
    assert float(received.state) == pytest.approx(428.926764214)
    assert hass.states.get(f"sensor.{PREFIX}_port_1_receive_rate").state == STATE_UNKNOWN

    # Unused ports get a link sensor but no counter sensors.
    assert hass.states.get(f"sensor.{PREFIX}_port_2_data_received") is None

    # CQM: the PPPoE graph has latency; the interface graph only throughput.
    assert hass.states.get(f"sensor.{PREFIX}_cqm_pppoe_latency") is not None
    assert hass.states.get(f"sensor.{PREFIX}_cqm_pppoe_packet_loss").state == "0.0"
    assert hass.states.get(f"sensor.{PREFIX}_cqm_home_latency") is None
    assert hass.states.get(f"sensor.{PREFIX}_cqm_home_data_received") is not None

    # IPv6 is disabled by default.
    ipv6 = entity_registry.async_get(f"sensor.{PREFIX}_pppoe_ipv6_address")
    assert ipv6 is not None and ipv6.disabled


async def test_rates_after_second_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_firebrick: Callable[..., None],
    mock_monotonic: list[float],
) -> None:
    """Throughput is computed from counter deltas between polls."""
    await _setup(hass, mock_config_entry)

    mock_firebrick(ports="ports_2.xml")
    mock_monotonic[0] += 10
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    rate = hass.states.get(f"sensor.{PREFIX}_port_1_receive_rate")
    assert rate.attributes["unit_of_measurement"] == "Mbit/s"
    assert float(rate.state) == pytest.approx(
        (428935098887 - 428926764214) * 8 / 10 / 1e6, abs=0.01
    )


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_firebrick: Callable[..., None],
) -> None:
    """A redirect to the login page during setup triggers reauth."""
    mock_firebrick(status=303)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]
