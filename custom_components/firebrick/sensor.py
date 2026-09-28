"""Sensors for the FireBrick integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CqmGraph, Port, PppoeSession
from .coordinator import FirebrickConfigEntry, FirebrickCoordinator, FirebrickData
from .entity import FirebrickEntity

PARALLEL_UPDATES = 0

type Value = str | int | float | datetime | None


@dataclass(frozen=True, kw_only=True)
class FirebrickSensorDescription(SensorEntityDescription):
    """Describes a sensor for one port, PPPoE session or CQM graph."""

    # (data, object id) -> value
    value_fn: Callable[[FirebrickData, Any], Value]
    # (data, object id) -> should the entity exist for this object
    exists_fn: Callable[[FirebrickData, Any], bool] = lambda data, object_id: True


def _rate(prefix: str, direction: str) -> Callable[[FirebrickData, Any], Value]:
    return lambda data, oid: data.rates.get(f"{prefix}_{oid}_{direction}")


def _always(data: FirebrickData, object_id: Any) -> bool:
    return True


def _rate_description(
    key: str,
    prefix: str,
    direction: str,
    exists_fn: Callable[[FirebrickData, Any], bool] = _always,
) -> FirebrickSensorDescription:
    return FirebrickSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=exists_fn,
        value_fn=_rate(prefix, direction),
    )


def _total_description(
    key: str,
    value_fn: Callable[[FirebrickData, Any], Value],
    exists_fn: Callable[[FirebrickData, Any], bool] = _always,
) -> FirebrickSensorDescription:
    return FirebrickSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        exists_fn=exists_fn,
        value_fn=value_fn,
    )


def _port(data: FirebrickData, number: int) -> Port | None:
    return data.status.ports.get(number)


def _port_has_counters(data: FirebrickData, number: int) -> bool:
    return (port := _port(data, number)) is not None and port.rx_bytes is not None


PORT_SENSORS: tuple[FirebrickSensorDescription, ...] = (
    _rate_description("port_rx_rate", "port", "rx", _port_has_counters),
    _rate_description("port_tx_rate", "port", "tx", _port_has_counters),
    _total_description(
        "port_rx_total",
        lambda d, n: (p := _port(d, n)) and p.rx_bytes,
        _port_has_counters,
    ),
    _total_description(
        "port_tx_total",
        lambda d, n: (p := _port(d, n)) and p.tx_bytes,
        _port_has_counters,
    ),
    FirebrickSensorDescription(
        key="port_speed",
        translation_key="port_speed",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d, n: (p := _port(d, n)) and p.link_up and p.speed or None,
    ),
)


def _session(data: FirebrickData, name: str) -> PppoeSession | None:
    return data.status.pppoe.get(name)


PPPOE_SENSORS: tuple[FirebrickSensorDescription, ...] = (
    FirebrickSensorDescription(
        key="pppoe_connected_since",
        translation_key="pppoe_connected_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d, name: d.connected_since.get(name),
    ),
    FirebrickSensorDescription(
        key="pppoe_ipv4",
        translation_key="pppoe_ipv4",
        value_fn=lambda d, name: (s := _session(d, name)) and s.is_up and s.local_ip or None,
    ),
    FirebrickSensorDescription(
        key="pppoe_ipv6",
        translation_key="pppoe_ipv6",
        entity_registry_enabled_default=False,
        value_fn=lambda d, name: (s := _session(d, name)) and s.is_up and s.local_ip6 or None,
    ),
)


def _graph(data: FirebrickData, name: str) -> CqmGraph | None:
    return data.status.cqm.get(name)


def _has_latency(data: FirebrickData, name: str) -> bool:
    return (graph := _graph(data, name)) is not None and graph.latest is not None


def _latency_description(key: str, attr: str) -> FirebrickSensorDescription:
    return FirebrickSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=_has_latency,
        value_fn=lambda d, name: (
            (g := _graph(d, name)) and g.latest and getattr(g.latest, attr)
        ),
    )


CQM_SENSORS: tuple[FirebrickSensorDescription, ...] = (
    _rate_description("cqm_rx_rate", "cqm", "rx"),
    _rate_description("cqm_tx_rate", "cqm", "tx"),
    _total_description("cqm_rx_total", lambda d, n: (g := _graph(d, n)) and g.rx_bytes),
    _total_description("cqm_tx_total", lambda d, n: (g := _graph(d, n)) and g.tx_bytes),
    _latency_description("cqm_latency_min", "min_latency_ms"),
    _latency_description("cqm_latency_avg", "ave_latency_ms"),
    _latency_description("cqm_latency_max", "max_latency_ms"),
    FirebrickSensorDescription(
        key="cqm_packet_loss",
        translation_key="cqm_packet_loss",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        exists_fn=_has_latency,
        value_fn=lambda d, name: (g := _graph(d, name)) and g.latest and g.latest.packet_loss,
    ),
)


class FirebrickSensor(FirebrickEntity, SensorEntity):
    """A sensor bound to one port, PPPoE session or CQM graph."""

    entity_description: FirebrickSensorDescription

    def __init__(
        self,
        coordinator: FirebrickCoordinator,
        description: FirebrickSensorDescription,
        kind: str,
        object_id: Any,
        label: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, f"{kind}_{object_id}_{description.key}")
        self.entity_description = description
        self._object_id = object_id
        self._attr_translation_placeholders = {"name": label}

    @property
    def native_value(self) -> Value:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data, self._object_id)


def _targets(data: FirebrickData) -> list[tuple[str, Any, str, tuple[FirebrickSensorDescription, ...]]]:
    """Every (kind, object id, label, descriptions) the current poll reports."""
    return [
        *(("port", n, f"Port {n}", PORT_SENSORS) for n in data.status.ports),
        *(("pppoe", name, name, PPPOE_SENSORS) for name in data.status.pppoe),
        *(("cqm", name, f"CQM {name}", CQM_SENSORS) for name in data.status.cqm),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FirebrickConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, adding more as new ports/sessions/graphs appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[FirebrickSensor] = []
        for kind, object_id, label, descriptions in _targets(coordinator.data):
            for description in descriptions:
                key = f"{kind}_{object_id}_{description.key}"
                if key in known or not description.exists_fn(coordinator.data, object_id):
                    continue
                known.add(key)
                new.append(FirebrickSensor(coordinator, description, kind, object_id, label))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
