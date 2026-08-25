#!/usr/bin/env python3
"""Discover and run all ndf-harness package tests; exit non-zero on failure."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from tests._helpers import TOOLS_DIR, run_cmd  # noqa: E402


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(PKG_ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    for script in sorted(TOOLS_DIR.glob("test_*.py")):
        proc = run_cmd([sys.executable, str(script)])
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            print(f"{script.name} ... FAIL", file=sys.stderr)
            return 1
        print(f"{script.name} ... ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
