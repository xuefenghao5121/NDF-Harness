#!/usr/bin/env python3
"""Discover and run all ndf-harness package tests; exit non-zero on failure."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(PKG_ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
