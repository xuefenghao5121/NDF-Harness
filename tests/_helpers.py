"""Shared helpers for ndf-harness package tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PKG_ROOT / "governance" / "tools"
INSTALL_PY = PKG_ROOT / "install.py"


def run_cmd(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    import os

    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        cwd=str(cwd or PKG_ROOT),
        capture_output=True,
        text=True,
        env=merged,
        timeout=120,
    )


def run_install(*install_args: str, repo: Path) -> subprocess.CompletedProcess[str]:
    return run_cmd(
        [sys.executable, str(INSTALL_PY), *install_args, "--repo", str(repo)],
        cwd=PKG_ROOT,
    )


def run_tool_script(name: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return run_cmd([sys.executable, str(TOOLS_DIR / name), *args], cwd=cwd or PKG_ROOT)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
