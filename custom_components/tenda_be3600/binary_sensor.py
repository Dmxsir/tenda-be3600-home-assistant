"""Binary sensors for Tenda BE3600."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import CONF_HOST, EntityCategory
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
class TendaBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a binary value in the shared snapshot."""

    value_fn: Callable[[dict[str, Any]], bool | None]


SYSTEM_BINARY_SENSORS = (
    TendaBinarySensorDescription(
        key="wan_connected",
        translation_key="wan_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.get("wan", {}).get("connected"),
    ),
    TendaBinarySensorDescription(
        key="internet",
        translation_key="internet",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.get("wan", {}).get("internet"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TendaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up connectivity sensors from the first snapshot."""
    coordinator = entry.runtime_data
    nodes = coordinator.data.get("nodes", [])
    primary_sn = controller_sn(coordinator.data)
    primary = next((node for node in nodes if node.get("sn") == primary_sn), None)
    entities: list[BinarySensorEntity] = []
    if primary:
        entities.extend(
            TendaSystemBinarySensor(coordinator, entry, primary, description)
            for description in SYSTEM_BINARY_SENSORS
        )
    for node in nodes:
        if not node.get("sn"):
            continue
        entities.append(TendaNodeOnlineBinarySensor(coordinator, entry, node))
        if node.get("sn") != primary_sn:
            entities.append(TendaWiredBackhaulBinarySensor(coordinator, entry, node))
    async_add_entities(entities)


class _TendaNodeBinarySensor(
    CoordinatorEntity[TendaCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TendaCoordinator,
        entry: TendaConfigEntry,
        node: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._node = node
        self._sn = str(node["sn"])

    @property
    def current_node(self) -> dict[str, Any] | None:
        return node_by_sn(self.coordinator.data, self._sn)

    @property
    def device_info(self):
        return node_device_info(
            self.coordinator.data,
            self.current_node or self._node,
            self._entry.data[CONF_HOST],
        )


class TendaSystemBinarySensor(_TendaNodeBinarySensor):
    """A controller-wide connectivity sensor."""

    def __init__(
        self,
        coordinator: TendaCoordinator,
        entry: TendaConfigEntry,
        node: dict[str, Any],
        description: TendaBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, node)
        self.entity_description = description
        self._attr_unique_id = f"{self._sn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


class TendaNodeOnlineBinarySensor(_TendaNodeBinarySensor):
    """Whether one mesh node is online."""

    _attr_translation_key = "node_online"

    def __init__(
        self,
        coordinator: TendaCoordinator,
        entry: TendaConfigEntry,
        node: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, entry, node)
        self._attr_unique_id = f"{self._sn}_online"

    @property
    def is_on(self) -> bool:
        return bool(self.current_node and self.current_node.get("online"))


class TendaWiredBackhaulBinarySensor(_TendaNodeBinarySensor):
    """Whether a satellite is using Ethernet backhaul."""

    _attr_translation_key = "wired_backhaul"

    def __init__(
        self,
        coordinator: TendaCoordinator,
        entry: TendaConfigEntry,
        node: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, entry, node)
        self._attr_unique_id = f"{self._sn}_wired_backhaul"

    @property
    def is_on(self) -> bool | None:
        if not (node := self.current_node):
            return None
        return bool(node.get("online") and node.get("connection_type") == "wire")

    @property
    def available(self) -> bool:
        return super().available and self.current_node is not None
