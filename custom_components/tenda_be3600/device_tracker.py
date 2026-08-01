"""Client presence tracking for Tenda BE3600."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import (
    ATTR_HOST_NAME,
    ATTR_IP,
    ATTR_MAC,
    BaseScannerEntity,
    SourceType,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TendaConfigEntry
from .const import DOMAIN
from .coordinator import TendaCoordinator, node_by_sn


def _mac(value: str) -> str:
    return value.lower().replace(":", "").replace("-", "")


def _client_node(
    snapshot: dict[str, Any], client: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve a client's normalized node reference to a known mesh node."""
    return node_by_sn(snapshot, str(client.get("node_sn") or ""))


def _friendly_node_name(node: dict[str, Any]) -> str:
    """Return a node label without exposing its internal identifier."""
    return str(
        node.get("name")
        or ("Controller" if node.get("node_type") == "controller" else "Mesh node")
    )


def _existing_node_sn(
    entity: er.RegistryEntry | None,
    device_registry: dr.DeviceRegistry,
    entry_id: str,
) -> str | None:
    """Return a previous node association only when it is this Tenda entry's device."""
    if (
        not entity
        or entity.config_entry_id != entry_id
        or not entity.device_id
        or not (device := device_registry.async_get(entity.device_id))
        or entry_id not in device.config_entries
    ):
        return None
    return next(
        (identifier for domain, identifier in device.identifiers if domain == DOMAIN),
        None,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TendaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create trackers now and when a new client first appears."""
    coordinator = entry.runtime_data
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    known: set[str] = set()

    @callback
    def async_add_new_clients() -> None:
        entities: list[TendaClientTracker] = []
        for client in coordinator.data.get("clients", []):
            if not (mac := client.get("mac")) or (key := _mac(mac)) in known:
                continue
            entity_id = entity_registry.async_get_entity_id(
                "device_tracker", DOMAIN, mac
            )
            registry_entry = entity_registry.async_get(entity_id) if entity_id else None
            if registry_entry and registry_entry.config_entry_id not in (
                None,
                entry.entry_id,
            ):
                continue
            node = _client_node(coordinator.data, client)
            node_sn = (
                str(node["sn"])
                if node
                else _existing_node_sn(registry_entry, device_registry, entry.entry_id)
            )
            known.add(key)
            entities.append(TendaClientTracker(coordinator, client, node_sn))
        if entities:
            async_add_entities(entities)

    async_add_new_clients()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_clients))


class TendaClientTracker(CoordinatorEntity[TendaCoordinator], BaseScannerEntity):
    """A client observed by the mesh."""

    _attr_source_type = SourceType.ROUTER

    def __init__(
        self,
        coordinator: TendaCoordinator,
        client: dict[str, Any],
        node_sn: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._key = _mac(client["mac"])
        self._node_sn = node_sn
        node = _client_node(coordinator.data, client)
        self._last_node_name = _friendly_node_name(node) if node else None
        # Preserve the unique IDs created by ScannerEntity in versions <= 0.1.1.
        self._attr_unique_id = client["mac"]

    @property
    def device_info(self) -> dr.DeviceInfo | None:
        """Associate the tracker with an existing mesh-node identifier."""
        if not self._node_sn:
            return None
        return dr.DeviceInfo(identifiers={(DOMAIN, self._node_sn)})

    @property
    def current_client(self) -> dict[str, Any] | None:
        return next(
            (
                client
                for client in self.coordinator.data.get("clients", [])
                if _mac(client.get("mac", "")) == self._key
            ),
            None,
        )

    @property
    def name(self) -> str:
        client = self.current_client or self._client
        return client.get("hostname") or client["mac"]

    @property
    def is_connected(self) -> bool:
        return bool(self.current_client and self.current_client.get("connected"))

    @property
    def hostname(self) -> str | None:
        return (self.current_client or self._client).get("hostname")

    @property
    def ip_address(self) -> str | None:
        return (self.current_client or self._client).get("ip")

    @property
    def mac_address(self) -> str:
        return (self.current_client or self._client)["mac"]

    @property
    def mesh_node(self) -> str | None:
        """Return the current friendly node name, retaining the last valid value."""
        if self.current_client and (
            node := _client_node(self.coordinator.data, self.current_client)
        ):
            self._last_node_name = _friendly_node_name(node)
        return self._last_node_name

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Preserve the useful scanner attributes without MAC-based merging."""
        return {
            ATTR_HOST_NAME: self.hostname,
            ATTR_IP: self.ip_address,
            ATTR_MAC: self.mac_address,
            "mesh_node": self.mesh_node,
        }
