"""Regression checks for client tracker mesh-node associations."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class CoordinatorEntity:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator


class BaseScannerEntity:
    pass


class EntityRegistry:
    def __init__(self, entries=()) -> None:
        self.entries = {entry.entity_id: entry for entry in entries}
        self.writes = []

    def async_get_entity_id(self, domain, platform, unique_id):
        return next(
            (
                entry.entity_id
                for entry in self.entries.values()
                if entry.unique_id == unique_id and entry.platform == platform
            ),
            None,
        )

    def async_get(self, entity_id):
        return self.entries.get(entity_id)

    def async_update_entity(self, *args, **kwargs):
        self.writes.append((args, kwargs))


class DeviceRegistry:
    def __init__(self, devices=()) -> None:
        self.devices = {device.id: device for device in devices}

    def async_get(self, device_id):
        return self.devices.get(device_id)


class DeviceTrackerAssociationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            Path(__file__).parents[1]
            / "custom_components"
            / "tenda_be3600"
            / "device_tracker.py"
        )
        tree = ast.parse(cls.path.read_text(encoding="utf-8"))
        selected = {
            "_mac",
            "_client_node",
            "_friendly_node_name",
            "_existing_node_sn",
            "async_setup_entry",
            "TendaClientTracker",
        }
        body = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name in selected
        ]
        cls.namespace = {
            "Any": object,
            "ATTR_HOST_NAME": "host_name",
            "ATTR_IP": "ip",
            "ATTR_MAC": "mac",
            "BaseScannerEntity": BaseScannerEntity,
            "CoordinatorEntity": CoordinatorEntity,
            "DOMAIN": "tenda_be3600",
            "SourceType": SimpleNamespace(ROUTER="router"),
            "TendaCoordinator": object,
            "callback": lambda function: function,
            "dr": SimpleNamespace(DeviceInfo=lambda **values: values),
            "er": SimpleNamespace(),
            "node_by_sn": lambda snapshot, sn: next(
                (node for node in snapshot.get("nodes", []) if node.get("sn") == sn),
                None,
            ),
        }
        module = ast.Module(
            body=[ast.parse("from __future__ import annotations").body[0], *body],
            type_ignores=[],
        )
        exec(compile(module, str(cls.path), "exec"), cls.namespace)

    def snapshot(self):
        return {
            "nodes": [
                {
                    "sn": "controller-node-test",
                    "name": "Controller",
                    "node_type": "controller",
                },
                {
                    "sn": "agent-node-test",
                    "name": "Warehouse",
                    "node_type": "agent",
                },
            ],
            "clients": [],
        }

    def tracker(self, client_key: str, node_sn: str | None):
        snapshot = self.snapshot()
        client = {"mac": client_key, "node_sn": node_sn, "connected": True}
        snapshot["clients"] = [client]
        coordinator = SimpleNamespace(data=snapshot)
        tracker = self.namespace["TendaClientTracker"](coordinator, client, node_sn)
        return tracker, coordinator

    def test_controller_and_agent_use_existing_node_identifier_format(self) -> None:
        controller, _ = self.tracker("client-controller", "controller-node-test")
        agent, _ = self.tracker("client-agent", "agent-node-test")
        self.assertEqual(
            controller.device_info["identifiers"],
            {("tenda_be3600", "controller-node-test")},
        )
        self.assertEqual(
            agent.device_info["identifiers"],
            {("tenda_be3600", "agent-node-test")},
        )

    def test_clients_share_node_device_without_client_identifiers(self) -> None:
        first, _ = self.tracker("client-first", "agent-node-test")
        second, _ = self.tracker("client-second", "agent-node-test")
        self.assertEqual(first.device_info, second.device_info)
        self.assertNotIn("client-first", str(first.device_info))
        self.assertNotIn("connections", first.device_info)

    def test_unknown_node_is_unassociated(self) -> None:
        tracker, _ = self.tracker("client-unknown", None)
        self.assertIsNone(tracker.device_info)

    def test_unique_id_and_entity_identity_inputs_are_preserved(self) -> None:
        tracker, _ = self.tracker("stable-client-key", "agent-node-test")
        self.assertEqual(tracker._attr_unique_id, "stable-client-key")

    def test_roaming_updates_attribute_without_registry_churn(self) -> None:
        tracker, coordinator = self.tracker(
            "client-roaming", "controller-node-test"
        )
        original_device_info = tracker.device_info
        coordinator.data["clients"][0]["node_sn"] = "agent-node-test"
        self.assertEqual(tracker.mesh_node, "Warehouse")
        self.assertEqual(tracker.device_info, original_device_info)
        self.assertNotIn("agent-node-test", tracker.mesh_node)

    async def test_setup_is_scoped_idempotent_and_preserves_user_state(self) -> None:
        entry_record = SimpleNamespace(
            entity_id="device_tracker.existing",
            unique_id="client-existing",
            platform="tenda_be3600",
            config_entry_id="current",
            device_id=None,
            disabled_by="user",
        )
        other_record = SimpleNamespace(
            entity_id="device_tracker.other",
            unique_id="client-other-entry",
            platform="tenda_be3600",
            config_entry_id="other",
            device_id=None,
            disabled_by=None,
        )
        entity_registry = EntityRegistry([entry_record, other_record])
        device_registry = DeviceRegistry()
        self.namespace["er"] = SimpleNamespace(async_get=lambda hass: entity_registry)
        self.namespace["dr"] = SimpleNamespace(
            DeviceInfo=lambda **values: values,
            async_get=lambda hass: device_registry,
        )
        snapshot = self.snapshot()
        snapshot["clients"] = [
            {
                "mac": "client-existing",
                "node_sn": "controller-node-test",
                "connected": True,
            },
            {
                "mac": "client-other-entry",
                "node_sn": "agent-node-test",
                "connected": True,
            },
        ]
        coordinator = SimpleNamespace(data=snapshot)
        coordinator.async_add_listener = lambda listener: setattr(
            coordinator, "listener", listener
        )
        entry = SimpleNamespace(
            entry_id="current", runtime_data=coordinator, async_on_unload=lambda _: None
        )
        added = []
        await self.namespace["async_setup_entry"](None, entry, added.extend)
        coordinator.listener()

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._attr_unique_id, "client-existing")
        self.assertEqual(entry_record.entity_id, "device_tracker.existing")
        self.assertEqual(entry_record.disabled_by, "user")
        self.assertEqual(other_record.config_entry_id, "other")
        self.assertEqual(entity_registry.writes, [])

    def test_previous_association_requires_current_tenda_entry_device(self) -> None:
        entity = SimpleNamespace(
            config_entry_id="current", device_id="node-device"
        )
        tenda_device = SimpleNamespace(
            id="node-device",
            config_entries={"current"},
            identifiers={("tenda_be3600", "agent-node-test")},
        )
        foreign_device = SimpleNamespace(
            id="foreign-device",
            config_entries={"current", "foreign"},
            identifiers={("other_integration", "camera-test")},
        )
        helper = self.namespace["_existing_node_sn"]
        self.namespace["DOMAIN"] = "tenda_be3600"
        self.assertEqual(
            helper(entity, DeviceRegistry([tenda_device]), "current"),
            "agent-node-test",
        )
        entity.device_id = "foreign-device"
        self.assertIsNone(helper(entity, DeviceRegistry([foreign_device]), "current"))


if __name__ == "__main__":
    unittest.main()
