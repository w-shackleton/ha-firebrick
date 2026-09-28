"""The FireBrick integration."""

from __future__ import annotations

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FirebrickClient
from .coordinator import FirebrickConfigEntry, FirebrickCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FirebrickConfigEntry) -> bool:
    """Set up FireBrick from a config entry."""
    client = FirebrickClient(
        async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL]),
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = FirebrickCoordinator(hass, entry, client, entry.unique_id)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FirebrickConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

