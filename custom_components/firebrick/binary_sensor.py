"""Binary sensors for the FireBrick integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FirebrickConfigEntry, FirebrickCoordinator
from .entity import FirebrickEntity

PARALLEL_UPDATES = 0


class FirebrickPortLink(FirebrickEntity, BinarySensorEntity):
    """Ethernet link state of a physical port."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "port_link"

    def __init__(self, coordinator: FirebrickCoordinator, number: int) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, f"port_{number}_link")
        self._number = number
        self._attr_translation_placeholders = {"name": f"Port {number}"}

    @property
    def is_on(self) -> bool | None:
        """Return True if the port has link."""
        port = self.coordinator.data.status.ports.get(self._number)
        return port.link_up if port else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None] | None:
        """Return port details."""
        if (port := self.coordinator.data.status.ports.get(self._number)) is None:
            return None
        return {"port_group": port.portgroup, "duplex": port.duplex}


class FirebrickPppoeConnected(FirebrickEntity, BinarySensorEntity):
    """Whether a PPPoE session is established."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "pppoe_connected"

    def __init__(self, coordinator: FirebrickCoordinator, name: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator, f"pppoe_{name}_connected")
        self._name = name
        self._attr_translation_placeholders = {"name": name}

    @property
    def is_on(self) -> bool:
        """Return True if the session is up; a vanished session counts as down."""
        session = self.coordinator.data.status.pppoe.get(self._name)
        return session is not None and session.is_up

    @property
    def extra_state_attributes(self) -> dict[str, str | None] | None:
        """Return session details."""
        if (session := self.coordinator.data.status.pppoe.get(self._name)) is None:
            return None
        return {
            "state": session.state,
            "status": session.status,
            "port": session.port,
            "remote_ip": session.remote_ip,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FirebrickConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors, adding more as new ports/sessions appear."""
    coordinator = entry.runtime_data
    known_ports: set[int] = set()
    known_sessions: set[str] = set()

    @callback
    def _add_new() -> None:
        status = coordinator.data.status
        new: list[BinarySensorEntity] = [
            FirebrickPortLink(coordinator, number)
            for number in status.ports.keys() - known_ports
        ]
        new += [
            FirebrickPppoeConnected(coordinator, name)
            for name in status.pppoe.keys() - known_sessions
        ]
        known_ports.update(status.ports)
        known_sessions.update(status.pppoe)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
