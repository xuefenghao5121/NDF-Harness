#!/usr/bin/env python3
"""Build MANIFEST.json for ndf-harness package (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PKG_ROOT / "VERSION"
MANIFEST_PATH = PKG_ROOT / "MANIFEST.json"
SOURCE_COMMIT = "783163a3f6eac26a871c71c1cf7492e11a987e58"
SKIP_DIRS = {"__pycache__", ".git"}


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
        "source_commit": SOURCE_COMMIT,
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
