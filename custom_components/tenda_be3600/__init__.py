"""Tenda BE3600 Mesh integration."""

from __future__ import annotations

import logging
import socket

import aiohttp
from aiohttp.resolver import ThreadedResolver

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api import TendaApi
from .const import CONF_PASSWORD_DIGEST, DOMAIN, PLATFORMS
from .coordinator import TendaCoordinator

TendaConfigEntry = ConfigEntry[TendaCoordinator]
_LOGGER = logging.getLogger(__name__)


def _enable_integration_disabled_entities(
    hass: HomeAssistant, entry: TendaConfigEntry
) -> None:
    """Enable this entry's entities that the integration disabled."""
    entity_registry = er.async_get(hass)
    enabled = 0
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if (
            entity.platform != DOMAIN
            or entity.disabled_by is not er.RegistryEntryDisabler.INTEGRATION
        ):
            continue
        entity_registry.async_update_entity(entity.entity_id, disabled_by=None)
        enabled += 1
    if enabled:
        _LOGGER.info(
            "Enabled %d Tenda BE3600 entities previously disabled by integration",
            enabled,
        )


async def async_setup_entry(hass: HomeAssistant, entry: TendaConfigEntry) -> bool:
    """Set up Tenda BE3600 from a config entry."""
    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(
            family=socket.AF_INET, resolver=ThreadedResolver()
        )
    )
    api = TendaApi(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_PASSWORD_DIGEST],
    )
    coordinator = TendaCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await session.close()
        raise
    entry.runtime_data = coordinator
    _enable_integration_disabled_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TendaConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.api.async_close()
    return unloaded
