#!/usr/bin/env python3
"""Repo-root detection for harness package and installed consumer layouts."""
from __future__ import annotations

from pathlib import Path


def detect_repo_root(start: Path | None = None) -> Path:
    """Return NDF project root (harness package or installed repo).

    Supports:
    - ``governance/tools/`` (harness package; ``norms/meta`` at parents[1])
    - ``spec/meta/tools/`` (installed consumer; ``spec/meta`` at parents[2])
    - ``ndf.workflow.yaml`` at root or under ``workflow/``
    """
    here = start or Path(__file__).resolve().parent

    def _is_root(cand: Path) -> bool:
        if (cand / "norms" / "meta").is_dir():
            return True
        if (cand / "spec" / "meta").is_dir():
            return True
        if (cand / "ndf.workflow.yaml").is_file():
            return True
        return (cand / "workflow" / "ndf.workflow.yaml").is_file()

    for cand in here.parents[:6]:
        if _is_root(cand):
            return cand
    return here.parents[2]
