"""Role binding / fallback smoke tests (package-local)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests._helpers import PKG_ROOT, run_tool_script


class TestRoleBinding(unittest.TestCase):
    def test_help_status_probe(self) -> None:
        for cmd in ("status", "probe"):
            proc = run_tool_script("ndf_role_binding.py", cmd, "--help")
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_bind_in_host_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "spec" / "00-charter").mkdir(parents=True)
            (repo / "src").mkdir()
            # Copy minimal workflow template
            src = PKG_ROOT / "workflow" / "ndf.workflow.yaml"
            if src.is_file():
                (repo / "ndf.workflow.yaml").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            proc = run_tool_script(
                "ndf_role_binding.py",
                "bind",
                "--repo",
                str(repo),
                "--command",
                "cursor",
                "--control",
                "in-host",
                "--implementation",
                "in-host",
                "--json",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload.get("roles_bound"))
            status = run_tool_script(
                "ndf_role_binding.py", "status", "--repo", str(repo), "--json"
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            data = json.loads(status.stdout)
            self.assertEqual(data["roles"]["control"]["provider"], "in-host")
            self.assertEqual(data["roles"]["implementation"]["provider"], "in-host")


if __name__ == "__main__":
    unittest.main()
