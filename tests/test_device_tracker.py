"""Regression check for client tracker device ownership."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class DeviceTrackerTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            Path(__file__).parents[1]
            / "custom_components"
            / "tenda_be3600"
            / "device_tracker.py"
        )
        cls.tree = ast.parse(cls.path.read_text(encoding="utf-8"))

    def test_client_tracker_does_not_inherit_mac_merging_scanner(self) -> None:
        tracker = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "TendaClientTracker"
        )
        bases = {ast.unparse(base) for base in tracker.bases}
        self.assertIn("BaseScannerEntity", bases)
        self.assertNotIn("ScannerEntity", bases)

        init = next(
            node
            for node in tracker.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        unique_id = next(
            node
            for node in ast.walk(init)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Attribute)
                and target.attr == "_attr_unique_id"
                for target in node.targets
            )
        )
        self.assertEqual(ast.unparse(unique_id.value), "client['mac']")

    def test_client_trackers_are_enabled_by_default(self) -> None:
        tracker = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "TendaClientTracker"
        )
        defaults = {
            target.id: node.value
            for node in tracker.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
            and target.id == "_attr_entity_registry_enabled_default"
        }
        self.assertNotIn("_attr_entity_registry_enabled_default", defaults)

    async def test_repeated_updates_do_not_create_duplicate_trackers(self) -> None:
        functions = [
            node
            for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"_mac", "async_setup_entry"}
        ]
        module = ast.Module(
            body=[ast.parse("from __future__ import annotations").body[0], *functions],
            type_ignores=[],
        )
        added = []

        class Tracker:
            def __init__(self, coordinator, client) -> None:
                self.key = client["mac"]

        namespace = {"callback": lambda function: function, "TendaClientTracker": Tracker}
        exec(compile(module, str(self.path), "exec"), namespace)

        coordinator = SimpleNamespace(data={"clients": [{"mac": "client-key"}]})
        coordinator.async_add_listener = lambda listener: setattr(
            coordinator, "listener", listener
        )
        entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=lambda _: None)
        await namespace["async_setup_entry"](None, entry, added.extend)
        coordinator.listener()

        self.assertEqual([tracker.key for tracker in added], ["client-key"])


if __name__ == "__main__":
    unittest.main()
