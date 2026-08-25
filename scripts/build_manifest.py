#!/usr/bin/env python3
"""Build MANIFEST.json for ndf-harness package (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PKG_ROOT / "VERSION"
MANIFEST_PATH = PKG_ROOT / "MANIFEST.json"
SKIP_DIRS = {"__pycache__", ".git"}


def source_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PKG_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_package_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path == MANIFEST_PATH:
            continue
        files.append(path)
    return files


def build_manifest() -> dict:
    version = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.is_file() else "unknown"
    entries = []
    for path in iter_package_files(PKG_ROOT):
        rel = path.relative_to(PKG_ROOT).as_posix()
        data = path.read_bytes()
        entries.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    return {
        "schema": "ndf-harness-manifest/v1",
        "version": version,
        "source_commit": source_commit(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "files": entries,
    }


def main() -> int:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST_PATH} ({len(manifest['files'])} files, version {manifest['version']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
