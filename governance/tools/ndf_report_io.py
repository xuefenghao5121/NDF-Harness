#!/usr/bin/env python3
"""Shared report path policy for NDF check tools.

Reports are disposable derived artifacts (GOVERNANCE: tmp/*-report.md).
MUST NOT write under spec/ (proposal inbox / SoT).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = (ROOT / "spec").resolve()


class ReportPathError(ValueError):
    """Raised when --report targets a forbidden path."""


def resolve_report_path(raw: str | None, default_rel: str) -> Path | None:
    """Resolve report destination.

    Returns:
      Path to write, or None when raw == '-' (stdout only).
    If raw is None, uses default_rel relative to repo root.
    Absolute /tmp/... is allowed; any path under repo spec/ is rejected.
    """
    if raw is None:
        raw = default_rel
    if raw == "-":
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    try:
        p.relative_to(SPEC)
    except ValueError:
        return p
    raise ReportPathError(
        f"report path must not be under spec/ (got {p}); "
        f"use tmp/... (repo) or /tmp/... (OS temp)"
    )


def write_report(path: Path | None, text: str) -> str | None:
    """Write Markdown report; if path is None, print to stdout.

    Returns the written path as str, or None when printed to stdout.
    """
    if path is None:
        print(text, end="" if text.endswith("\n") else "\n")
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)
