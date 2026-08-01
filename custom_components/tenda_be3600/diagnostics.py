"""Privacy-preserving diagnostics for Tenda BE3600."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import TendaConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TendaConfigEntry
) -> dict[str, Any]:
    """Return only explicitly safe, non-identifying fields."""
    coordinator = entry.runtime_data
    data = coordinator.data
    clients = data.get("clients", [])
    return {
        "entry_version": entry.version,
        "last_update_success": coordinator.last_update_success,
        "system": {
            key: data.get("system", {}).get(key)
            for key in ("model", "software_version", "hardware_version", "work_mode")
        },
        "wan": {
            key: data.get("wan", {}).get(key)
            for key in ("connected", "internet", "type")
        },
        "mesh": {
            "node_count": len(data.get("nodes", [])),
            "nodes": [
                {
                    key: node.get(key)
                    for key in (
                        "node_type",
                        "model",
                        "firmware",
                        "hardware_version",
                        "online",
                        "connection_type",
                        "client_count",
                    )
                }
                for node in data.get("nodes", [])
            ],
        },
        "clients": {
            "known": len(clients),
            "connected": sum(bool(client.get("connected")) for client in clients),
            "guest": sum(bool(client.get("guest")) for client in clients),
        },
    }
