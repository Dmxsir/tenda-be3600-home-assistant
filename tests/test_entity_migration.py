"""Regression checks for entity registry enablement migration."""

from __future__ import annotations

import ast
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
import unittest


class Disabler(Enum):
    INTEGRATION = "integration"
    USER = "user"


class Registry:
    def __init__(self, entries) -> None:
        self.entries = entries
        self.updates: list[str] = []

    def async_update_entity(self, entity_id: str, *, disabled_by) -> None:
        self.updates.append(entity_id)
        next(entry for entry in self.entries if entry.entity_id == entity_id).disabled_by = (
            disabled_by
        )


class EntityMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            Path(__file__).parents[1]
            / "custom_components"
            / "tenda_be3600"
            / "__init__.py"
        )
        tree = ast.parse(cls.path.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_enable_integration_disabled_entities"
        )
        module = ast.Module(
            body=[ast.parse("from __future__ import annotations").body[0], function],
            type_ignores=[],
        )
        cls.namespace = {}
        exec(compile(module, str(cls.path), "exec"), cls.namespace)

    def entry(
        self,
        entity_id: str,
        *,
        disabled_by=Disabler.INTEGRATION,
        platform: str = "tenda_be3600",
        config_entry_id: str = "current",
        unique_id: str = "stable-unique-id",
    ):
        return SimpleNamespace(
            entity_id=entity_id,
            disabled_by=disabled_by,
            platform=platform,
            config_entry_id=config_entry_id,
            unique_id=unique_id,
        )

    def migrate(self, entries, times: int = 1) -> Registry:
        registry = Registry(entries)
        registry.logs = []
        entity_registry = SimpleNamespace(
            RegistryEntryDisabler=Disabler,
            async_get=lambda hass: registry,
            async_entries_for_config_entry=lambda registry, entry_id: [
                entity for entity in registry.entries if entity.config_entry_id == entry_id
            ],
        )
        logger = SimpleNamespace(info=lambda *args: registry.logs.append(args))
        function = self.namespace["_enable_integration_disabled_entities"]
        function.__globals__.update(
            er=entity_registry, DOMAIN="tenda_be3600", _LOGGER=logger
        )
        for _ in range(times):
            function(None, SimpleNamespace(entry_id="current"))
        return registry

    def test_enables_entity_disabled_by_integration_and_preserves_unique_id(self) -> None:
        entities = [
            self.entry("sensor.synthetic", unique_id="sensor-stable"),
            self.entry("binary_sensor.synthetic", unique_id="binary-stable"),
            self.entry("device_tracker.synthetic", unique_id="tracker-stable"),
        ]
        registry = self.migrate(entities)
        self.assertTrue(all(entity.disabled_by is None for entity in entities))
        self.assertEqual(
            [entity.unique_id for entity in entities],
            ["sensor-stable", "binary-stable", "tracker-stable"],
        )
        self.assertEqual(registry.updates, [entity.entity_id for entity in entities])
        self.assertEqual(
            registry.logs,
            [
                (
                    "Enabled %d Tenda BE3600 entities previously disabled by integration",
                    3,
                )
            ],
        )

    def test_leaves_user_disabled_entity_untouched(self) -> None:
        entity = self.entry("sensor.user_disabled", disabled_by=Disabler.USER)
        self.assertEqual(self.migrate([entity]).updates, [])
        self.assertIs(entity.disabled_by, Disabler.USER)

    def test_leaves_other_integration_untouched(self) -> None:
        entity = self.entry("sensor.other", platform="other_integration")
        self.assertEqual(self.migrate([entity]).updates, [])
        self.assertIs(entity.disabled_by, Disabler.INTEGRATION)

    def test_leaves_other_config_entry_untouched(self) -> None:
        entity = self.entry("sensor.other_entry", config_entry_id="other")
        self.assertEqual(self.migrate([entity]).updates, [])
        self.assertIs(entity.disabled_by, Disabler.INTEGRATION)

    def test_migration_is_idempotent(self) -> None:
        entity = self.entry("sensor.once")
        registry = self.migrate([entity], times=2)
        self.assertEqual(registry.updates, ["sensor.once"])


if __name__ == "__main__":
    unittest.main()
