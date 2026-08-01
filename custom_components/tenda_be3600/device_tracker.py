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
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TendaConfigEntry
from .coordinator import TendaCoordinator


def _mac(value: str) -> str:
    return value.lower().replace(":", "").replace("-", "")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TendaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create trackers now and when a new client first appears."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_add_new_clients() -> None:
        entities: list[TendaClientTracker] = []
        for client in coordinator.data.get("clients", []):
            if not (mac := client.get("mac")) or (key := _mac(mac)) in known:
                continue
            known.add(key)
            entities.append(TendaClientTracker(coordinator, client))
        if entities:
            async_add_entities(entities)

    async_add_new_clients()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_clients))


class TendaClientTracker(CoordinatorEntity[TendaCoordinator], BaseScannerEntity):
    """A client observed by the mesh."""

    _attr_entity_registry_enabled_default = False
    _attr_source_type = SourceType.ROUTER

    def __init__(self, coordinator: TendaCoordinator, client: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._client = client
        self._key = _mac(client["mac"])
        # Preserve the unique IDs created by ScannerEntity in versions <= 0.1.1.
        self._attr_unique_id = client["mac"]

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
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Preserve the useful scanner attributes without MAC-based merging."""
        return {
            ATTR_HOST_NAME: self.hostname,
            ATTR_IP: self.ip_address,
            ATTR_MAC: self.mac_address,
        }
