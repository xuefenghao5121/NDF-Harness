"""ndf_gate_slices import and compute smoke."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from tests._helpers import PKG_ROOT, run_tool_script


def _load_gate_slices():
    path = PKG_ROOT / "governance" / "tools" / "ndf_gate_slices.py"
    spec = importlib.util.spec_from_file_location("ndf_gate_slices_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestGateSlicesImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tools = PKG_ROOT / "governance" / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))

    def test_help_exits_zero(self) -> None:
        proc = run_tool_script("ndf_gate_slices.py", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("gate review slices", proc.stdout.lower() + proc.stderr.lower())

    def test_parse_gates_table_smoke(self) -> None:
        mod = _load_gate_slices()
        sample = """
| gate | phrase | approved_by | approved_at | approved_content_sha | source_ref | status |
| --- | --- | --- | --- | --- | --- | --- |
| bundle_dispatch | 派发 | human | 2026-01-01T00:00:00Z | abc123 | binder | approved |
"""
        rows = mod.parse_gates_table(sample)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["gate"], "bundle_dispatch")
        self.assertEqual(rows[0]["phrase"], "派发")


if __name__ == "__main__":
    unittest.main()
