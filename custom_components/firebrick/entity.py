"""Base entity for the FireBrick integration."""

from __future__ import annotations

from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import FirebrickCoordinator


class FirebrickEntity(CoordinatorEntity[FirebrickCoordinator]):
    """An entity belonging to the FireBrick device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FirebrickCoordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        firmware = coordinator.data.status.firmware or ""
        model, _, sw_version = firmware.partition(" ")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            manufacturer=MANUFACTURER,
            model=model or None,
            name=f"FireBrick {model}".strip(),
            serial_number=coordinator.serial,
            sw_version=sw_version or None,
            configuration_url=coordinator.config_entry.data[CONF_URL],
        )
