"""Sensors for Tenda BE3600."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_HOST, EntityCategory, UnitOfDataRate, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TendaConfigEntry
from .coordinator import (
    TendaCoordinator,
    controller_sn,
    node_by_sn,
    node_device_info,
)


@dataclass(frozen=True, kw_only=True)
class TendaSensorDescription(SensorEntityDescription):
    """Describe a value in the shared snapshot."""

    value_fn: Callable[[dict[str, Any]], int | float | None]


SYSTEM_SENSORS = (
    TendaSensorDescription(
        key="system_uptime",
        translation_key="system_uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("system", {}).get("uptime"),
    ),
    TendaSensorDescription(
        key="wan_download",
        translation_key="wan_download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("wan", {}).get("download_mbps"),
    ),
    TendaSensorDescription(
        key="wan_upload",
        translation_key="wan_upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("wan", {}).get("upload_mbps"),
    ),
    TendaSensorDescription(
        key="wan_connection_duration",
        translation_key="wan_connection_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("wan", {}).get("connection_duration"),
    ),
    TendaSensorDescription(
        key="mesh_nodes",
        translation_key="mesh_nodes",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:access-point-network",
        value_fn=lambda data: len(data.get("nodes", [])),
    ),
    TendaSensorDescription(
        key="total_connected_clients",
        translation_key="total_connected_clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:devices",
        value_fn=lambda data: sum(
            bool(client.get("connected")) for client in data.get("clients", [])
        ),
    ),
)

NODE_SENSORS = (
    TendaSensorDescription(
        key="connected_clients",
        translation_key="connected_clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:devices",
        value_fn=lambda node: node.get("client_count"),
    ),
    TendaSensorDescription(
        key="connection_duration",
        translation_key="connection_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda node: node.get("connection_duration"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TendaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all sensors from the first snapshot."""
    coordinator = entry.runtime_data
    nodes = coordinator.data.get("nodes", [])
    primary_sn = controller_sn(coordinator.data)
    entities: list[SensorEntity] = []
    if primary := next((node for node in nodes if node.get("sn") == primary_sn), None):
        entities.extend(
            TendaSystemSensor(coordinator, entry, primary, description)
            for description in SYSTEM_SENSORS
        )
    entities.extend(
        TendaNodeSensor(coordinator, entry, node, description)
        for node in nodes
        if node.get("sn")
        for description in NODE_SENSORS
    )
    async_add_entities(entities)


class TendaSystemSensor(CoordinatorEntity[TendaCoordinator], SensorEntity):
    """A controller-wide Tenda sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TendaCoordinator,
        entry: TendaConfigEntry,
        node: dict[str, Any],
        description: TendaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._node = node
        self._attr_unique_id = f"{node['sn']}_{description.key}"

    @property
    def native_value(self) -> int | float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def device_info(self):
        node = node_by_sn(self.coordinator.data, str(self._node["sn"])) or self._node
        return node_device_info(
            self.coordinator.data, node, self._entry.data[CONF_HOST]
        )


class TendaNodeSensor(CoordinatorEntity[TendaCoordinator], SensorEntity):
    """A sensor belonging to one mesh node."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TendaCoordinator,
        entry: TendaConfigEntry,
        node: dict[str, Any],
        description: TendaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._node = node
        self._sn = str(node["sn"])
        self._attr_unique_id = f"{self._sn}_{description.key}"

    @property
    def native_value(self) -> int | float | None:
        if node := node_by_sn(self.coordinator.data, self._sn):
            return self.entity_description.value_fn(node)
        return None

    @property
    def available(self) -> bool:
        return (
            super().available
            and node_by_sn(self.coordinator.data, self._sn) is not None
        )

    @property
    def device_info(self):
        node = node_by_sn(self.coordinator.data, self._sn) or self._node
        return node_device_info(
            self.coordinator.data, node, self._entry.data[CONF_HOST]
        )
