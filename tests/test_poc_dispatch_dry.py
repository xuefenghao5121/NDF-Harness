"""ndf_poc_dispatch CLI help and fail-closed without topic."""
from __future__ import annotations

import unittest

from tests._helpers import run_tool_script


class TestPocDispatchDry(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        proc = run_tool_script("ndf_poc_dispatch.py", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("poc dispatch", (proc.stdout + proc.stderr).lower())

    def test_dry_run_without_topic_fails_closed(self) -> None:
        proc = run_tool_script("ndf_poc_dispatch.py", "--dry-run")
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("topic", combined.lower())


if __name__ == "__main__":
    unittest.main()
