"""Regression check for client tracker device ownership."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


class DeviceTrackerTests(unittest.TestCase):
    def test_client_tracker_does_not_inherit_mac_merging_scanner(self) -> None:
        path = (
            Path(__file__).parents[1]
            / "custom_components"
            / "tenda_be3600"
            / "device_tracker.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tracker = next(
            node
            for node in tree.body
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


if __name__ == "__main__":
    unittest.main()
