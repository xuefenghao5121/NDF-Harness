"""ndf_context CLI smoke."""
from __future__ import annotations

import unittest

from tests._helpers import run_tool_script


class TestContextSmoke(unittest.TestCase):
    def test_help_exits_zero(self) -> None:
        proc = run_tool_script("ndf_context.py", "--help")
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        combined = (proc.stdout + proc.stderr).lower()
        self.assertTrue("context" in combined or "usage" in combined)


if __name__ == "__main__":
    unittest.main()
