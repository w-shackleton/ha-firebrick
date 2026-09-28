"""Diagnostics for the FireBrick integration."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import FirebrickConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "local_ip",
    "local_ip6",
    "remote_ip",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FirebrickConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        # Round-trip through JSON so timedeltas and datetimes become strings.
        "status": async_redact_data(
            json.loads(json.dumps(asdict(data.status), default=str)), TO_REDACT
        ),
        "rates": data.rates,
        "connected_since": data.connected_since,
    }
