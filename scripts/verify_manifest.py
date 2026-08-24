#!/usr/bin/env python3
"""Verify MANIFEST.json matches current package file hashes."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PKG_ROOT / "MANIFEST.json"
SKIP_DIRS = {"__pycache__", ".git"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current_files() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(PKG_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(PKG_ROOT).as_posix()
        if rel == "MANIFEST.json":
            continue
        data = path.read_bytes()
        out[rel] = {"sha256": sha256_bytes(data), "bytes": len(data)}
    return out


def main() -> int:
    if not MANIFEST_PATH.is_file():
        print("error: MANIFEST.json missing; run scripts/build_manifest.py first", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded = {item["path"]: item for item in manifest.get("files") or []}
    live = current_files()

    errors: list[str] = []
    for path, meta in recorded.items():
        if path not in live:
            errors.append(f"missing file listed in manifest: {path}")
            continue
        if live[path]["sha256"] != meta.get("sha256"):
            errors.append(f"hash mismatch: {path}")
        if live[path]["bytes"] != meta.get("bytes"):
            errors.append(f"size mismatch: {path}")

    for path in sorted(set(live) - set(recorded)):
        errors.append(f"unlisted file: {path}")

    if errors:
        print("MANIFEST verification failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"MANIFEST ok: version={manifest.get('version')} "
        f"source_commit={manifest.get('source_commit')} files={len(recorded)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
