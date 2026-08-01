"""Data coordinator for Tenda BE3600."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    TendaApi,
    TendaAuthError,
    TendaConnectionError,
    TendaLockedError,
    TendaProtocolError,
)
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class TendaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep one current snapshot for every Tenda entity."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: TendaApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
            always_update=False,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_snapshot()
        except TendaAuthError as err:
            raise ConfigEntryAuthFailed("Tenda authentication failed") from err
        except (TendaConnectionError, TendaLockedError, TendaProtocolError) as err:
            raise UpdateFailed(str(err)) from err


def controller_sn(snapshot: dict[str, Any]) -> str:
    """Return the controller serial number."""
    nodes = snapshot.get("nodes", [])
    controller = next(
        (node for node in nodes if node.get("node_type") == "controller"),
        nodes[0] if nodes else {},
    )
    return str(controller.get("sn", ""))


def node_by_sn(snapshot: dict[str, Any], sn: str) -> dict[str, Any] | None:
    """Look up a node without relying on response order."""
    return next(
        (node for node in snapshot.get("nodes", []) if node.get("sn") == sn), None
    )


def node_device_info(
    snapshot: dict[str, Any], node: dict[str, Any], host: str
) -> DeviceInfo:
    """Build stable Home Assistant device metadata for one physical node."""
    sn = str(node["sn"])
    primary_sn = controller_sn(snapshot)
    info: DeviceInfo = {
        "identifiers": {(DOMAIN, sn)},
        "manufacturer": "Tenda",
        "model": node.get("model") or "BE3600",
        "name": node.get("name") or f"Tenda {sn[-4:]}",
        "sw_version": node.get("firmware"),
        "hw_version": node.get("hardware_version"),
    }
    if sn == primary_sn:
        info["configuration_url"] = f"http://{host}"
    elif primary_sn:
        info["via_device"] = (DOMAIN, primary_sn)
    return info
