"""Polling coordinator for the FireBrick integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FirebrickAuthError, FirebrickClient, FirebrickError, FirebrickStatus
from .const import (
    CONF_SCAN_INTERVAL,
    CONNECTED_SINCE_TOLERANCE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type FirebrickConfigEntry = ConfigEntry[FirebrickCoordinator]


@dataclass(slots=True)
class FirebrickData:
    """Coordinator payload: raw status plus values derived across polls."""

    status: FirebrickStatus
    # Bits per second keyed by counter id, e.g. "port_1_rx" or "cqm_pppoe_tx".
    rates: dict[str, float] = field(default_factory=dict)
    # PPPoE session name -> time the session came up.
    connected_since: dict[str, datetime] = field(default_factory=dict)


def byte_counters(status: FirebrickStatus) -> dict[str, int]:
    """Flatten every cumulative byte counter in a poll, keyed by counter id."""
    counters: dict[str, int | None] = {}
    for number, port in status.ports.items():
        counters[f"port_{number}_rx"] = port.rx_bytes
        counters[f"port_{number}_tx"] = port.tx_bytes
    for name, graph in status.cqm.items():
        counters[f"cqm_{name}_rx"] = graph.rx_bytes
        counters[f"cqm_{name}_tx"] = graph.tx_bytes
    return {key: value for key, value in counters.items() if value is not None}


def compute_rates(
    previous: dict[str, int], current: dict[str, int], elapsed: float
) -> dict[str, float]:
    """Return bits/s for counters present in both samples.

    A counter that went backwards (reboot or reset) yields no rate for this poll.
    """
    if elapsed <= 0:
        return {}
    return {
        key: (value - previous[key]) * 8 / elapsed
        for key, value in current.items()
        if key in previous and value >= previous[key]
    }


class FirebrickCoordinator(DataUpdateCoordinator[FirebrickData]):
    """Fetch FireBrick status and derive throughput rates."""

    config_entry: FirebrickConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FirebrickConfigEntry,
        client: FirebrickClient,
        serial: str,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.serial = serial
        self._last_counters: dict[str, int] = {}
        self._last_poll: float | None = None

    async def _async_update_data(self) -> FirebrickData:
        try:
            status = await self.client.async_get_status()
        except FirebrickAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FirebrickError as err:
            raise UpdateFailed(str(err)) from err

        now = monotonic()
        counters = byte_counters(status)
        rates = (
            compute_rates(self._last_counters, counters, now - self._last_poll)
            if self._last_poll is not None
            else {}
        )
        self._last_counters = counters
        self._last_poll = now

        return FirebrickData(
            status=status,
            rates=rates,
            connected_since=self._connected_since(status),
        )

    def _connected_since(self, status: FirebrickStatus) -> dict[str, datetime]:
        """Turn session uptimes into stable start timestamps."""
        previous = self.data.connected_since if self.data else {}
        utcnow = dt_util.utcnow()
        result: dict[str, datetime] = {}
        for name, session in status.pppoe.items():
            if not session.is_up or session.uptime is None:
                continue
            since = utcnow - session.uptime
            old = previous.get(name)
            if old is not None and abs(since - old) < CONNECTED_SINCE_TOLERANCE:
                since = old
            result[name] = since.replace(microsecond=0)
        return result
