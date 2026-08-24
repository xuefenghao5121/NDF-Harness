#!/usr/bin/env python3
"""Detect NDF Harness 0.2 / legacy patterns in a consumer repository.

Always exits 0 on successful scan; exits 2 only on I/O errors.
Prints a single JSON object to stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

VERSION_0_2_RE = re.compile(r"^0\.2(?:\.|$)")
LEGACY_GATE_PHRASES = ("TOPIC已审核", "DESIGN已审核", "可以开始实现")
RESIDUE_TERMS = ("Commander", "Episode", "Replay", "ActionSpec")
DEPRECATED_MARKERS = (
    "retired",
    "deprecated",
    "ADR-META-004",
    "tombstone",
    "已退役",
    "已废弃",
)
WHOLE_FILE_GATE_MARKERS = (
    "bundle_mode: whole_file",
    "whole_file_sha",
    "approved_whole_file",
)
OLD_SKILL_MENU_MARKERS = (
    "Skill modes: read `skill/SKILL.md`",
    "pick init or adopt",
    "MODE: init",
    "MODE: adopt",
    "init / adopt / govern / sync",
    "See also `skill/MODES.md`",
)
CANONICAL_WORKFLOW_MARKERS = (
    "ndf-workflow",
    "五句口令",
    "five phrases",
    "初始化项目",
)
HARNESS_NORM_FILES = (
    "meta/README.md",
    "meta/language.md",
    "meta/process.md",
    "meta/glossary.md",
    "meta/architecture.md",
    "meta/constraints.md",
    "CLAUSE-FORMAT.md",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _find_harness_roots(repo: Path) -> list[Path]:
    roots: list[Path] = []
    candidates = [
        repo / "packages" / "ndf-harness",
        repo / "vendor" / "ndf-harness",
        repo / "ndf-harness",
    ]
    for cand in candidates:
        if (cand / "VERSION").is_file() or (cand / "install.py").is_file():
            roots.append(cand)
    return roots


def _detect_version_0_2(repo: Path, harness_roots: list[Path]) -> dict[str, Any]:
    hits: list[str] = []
    version_value: str | None = None

    for root in harness_roots:
        version_file = root / "VERSION"
        if version_file.is_file():
            version_value = _read_text(version_file).strip()
            if VERSION_0_2_RE.match(version_value):
                hits.append(_rel(version_file, repo))

    skill_candidates: list[Path] = list(repo.glob(".cursor/skills/**/SKILL.md"))
    skill_candidates.extend(
        p
        for p in (
            repo / "skills" / "ndf-harness" / "SKILL.md",
            repo / ".claude" / "skills" / "ndf-harness" / "SKILL.md",
            repo / ".opencode" / "skills" / "ndf-harness" / "SKILL.md",
        )
        if p.is_file()
    )
    # Legacy top-level skill without ndf-workflow redirect
    legacy_skill = repo / "skill" / "SKILL.md"
    if legacy_skill.is_file():
        text = _read_text(legacy_skill)
        if any(m in text for m in OLD_SKILL_MENU_MARKERS) and not any(
            m in text for m in CANONICAL_WORKFLOW_MARKERS
        ):
            hits.append(_rel(legacy_skill, repo))

    for skill_path in skill_candidates:
        text = _read_text(skill_path)
        if any(m.lower() in text.lower() for m in OLD_SKILL_MENU_MARKERS) and not any(
            m in text for m in CANONICAL_WORKFLOW_MARKERS
        ):
            hits.append(_rel(skill_path, repo))

    return {
        "detected": bool(hits),
        "version": version_value,
        "hits": sorted(set(hits)),
    }


def _iter_gates_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("poc/*/ndf/GATES.md", "spec/**/GATES.md"):
        files.extend(repo.glob(pattern))
    return sorted({p for p in files if p.is_file()})


def _detect_legacy_three_gates(repo: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _iter_gates_files(repo):
        text = _read_text(path)
        found = [p for p in LEGACY_GATE_PHRASES if p in text]
        if found:
            hits.append({"path": _rel(path, repo), "phrases": found})
    return {"detected": bool(hits), "hits": hits}


def _line_is_deprecated_context(line: str) -> bool:
    lower = line.lower()
    return any(marker.lower() in lower for marker in DEPRECATED_MARKERS)


def _detect_commander_or_replay_residue(repo: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    scan_suffixes = {".md", ".py", ".yaml", ".yml", ".json", ".tsx", ".ts", ".js"}

    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in scan_suffixes:
            continue
        if "packages/ndf-harness/migration/" in _rel(path, repo):
            continue
        try:
            text = _read_text(path)
        except OSError:
            continue
        for term in RESIDUE_TERMS:
            for idx, line in enumerate(text.splitlines(), start=1):
                if term not in line:
                    continue
                if _line_is_deprecated_context(line):
                    continue
                # Allow ndf_replay tombstone and explicit retirement docs
                rel = _rel(path, repo)
                if term == "Replay" and "ndf_replay" in rel:
                    continue
                if "adr-meta-control-retirement" in rel.lower():
                    continue
                hits.append(
                    {
                        "path": rel,
                        "line": idx,
                        "term": term,
                        "excerpt": line.strip()[:160],
                    }
                )
    return {"detected": bool(hits), "hits": hits}


def _detect_whole_file_sha_gates(repo: Path) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in _iter_gates_files(repo):
        text = _read_text(path)
        reasons: list[str] = []
        if "review_slice" not in text and "slice_manifest_sha" not in text:
            if any(p in text for p in LEGACY_GATE_PHRASES):
                reasons.append("missing_review_slice_columns")
        if any(marker in text for marker in WHOLE_FILE_GATE_MARKERS):
            reasons.append("whole_file_marker")
        if "| approved_content_sha |" in text and "slice_manifest_sha" not in text:
            # Legacy table without slice manifest column
            if "bundle_mode" not in text:
                reasons.append("legacy_gate_table")
        if reasons:
            hits.append({"path": _rel(path, repo), "reasons": reasons})
    return {"detected": bool(hits), "hits": hits}


def _load_harness_norm_hashes(harness_root: Path | None) -> dict[str, str]:
    if harness_root is None:
        return {}
    out: dict[str, str] = {}
    for rel in HARNESS_NORM_FILES:
        path = harness_root / "norms" / rel
        if path.is_file():
            out[rel] = _sha256_file(path)
    return out


def _detect_custom_local_meta(repo: Path, harness_roots: list[Path]) -> dict[str, Any]:
    harness_root = harness_roots[0] if harness_roots else None
    seed_hashes = _load_harness_norm_hashes(harness_root)
    hits: list[dict[str, str]] = []
    meta_dir = repo / "spec" / "meta"
    if not meta_dir.is_dir():
        return {"detected": False, "hits": [], "note": "no spec/meta directory"}

    for rel, seed_sha in seed_hashes.items():
        local = meta_dir / rel.replace("meta/", "meta/") if rel.startswith("meta/") else meta_dir / rel
        if rel.startswith("meta/"):
            local = meta_dir / rel[len("meta/") :]
        elif rel == "CLAUSE-FORMAT.md":
            local = meta_dir / "CLAUSE-FORMAT.md"
        else:
            local = meta_dir / rel
        if not local.is_file():
            continue
        local_sha = _sha256_file(local)
        if local_sha != seed_sha:
            hits.append(
                {
                    "path": _rel(local, repo),
                    "reason": "differs_from_harness_seed",
                    "local_sha256": local_sha[:12],
                    "seed_sha256": seed_sha[:12],
                }
            )

    # Local-only meta files not in harness seed
    for path in sorted(meta_dir.rglob("*.md")):
        rel = _rel(path, repo)
        rel_from_meta = str(path.relative_to(meta_dir))
        seeded = any(
            rel_from_meta == h.replace("meta/", "") or rel_from_meta == h
            for h in seed_hashes
        )
        if not seeded and "decisions/" in rel_from_meta:
            hits.append({"path": rel, "reason": "local_decision_or_extension"})
        elif not seeded and rel_from_meta.startswith("open/"):
            hits.append({"path": rel, "reason": "local_open_proposal"})

    return {"detected": bool(hits), "hits": hits}


def _recommended_actions(report: dict[str, Any]) -> list[str]:
    actions: list[str] = []

    if report["has_version_0_2"]["detected"]:
        actions.append(
            "Run harness install.py adopt --repo <repo> --profile dual-track "
            "--runtime cursor,openclaw,claude-code; review plan JSON before install."
        )

    if report["legacy_three_gates"]["detected"]:
        actions.append(
            "Migrate GATES.md to review-slice bundle SHA (bundle_mode=review_slice, "
            "slice_manifest_sha); re-obtain human phrase 派发 after slice diff review."
        )

    if report["whole_file_sha_gates"]["detected"]:
        actions.append(
            "Replace whole-file gate snapshots with ndf_gate_slices review bundles; "
            "append invalidated rows — do not rewrite historical receipts."
        )

    if report["commander_or_replay_residue"]["detected"]:
        actions.append(
            "Remove or quarantine Commander/Episode/Replay/ActionSpec references; "
            "retire replay skills; use ndf_workflow_status + disk completion only."
        )

    if report["custom_local_meta"]["detected"]:
        actions.append(
            "Preserve settled spec/meta/ locally — install MUST NOT silent-overwrite "
            "protected meta clauses; merge harness seed diffs via process proposal."
        )

    if not actions:
        actions.append(
            "Greenfield or already on 1.0 patterns: run install.py install + verify."
        )

    actions.append(
        "Never silent-overwrite AGENTS.md or finalized spec/meta/*.md without --force "
        "and explicit human review."
    )
    return actions


def scan_repo(repo: Path) -> dict[str, Any]:
    harness_roots = _find_harness_roots(repo)
    report: dict[str, Any] = {
        "repo": str(repo.resolve()),
        "harness_roots": [_rel(p, repo) for p in harness_roots],
        "has_version_0_2": _detect_version_0_2(repo, harness_roots),
        "legacy_three_gates": _detect_legacy_three_gates(repo),
        "commander_or_replay_residue": _detect_commander_or_replay_residue(repo),
        "whole_file_sha_gates": _detect_whole_file_sha_gates(repo),
        "custom_local_meta": _detect_custom_local_meta(repo, harness_roots),
    }
    report["recommended_actions"] = _recommended_actions(report)
    report["needs_migration"] = any(
        report[key]["detected"]
        for key in (
            "has_version_0_2",
            "legacy_three_gates",
            "commander_or_replay_residue",
            "whole_file_sha_gates",
        )
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="consumer repository root (default: cwd)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print JSON",
    )
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    if not repo.is_dir():
        print(json.dumps({"error": f"repo not found: {repo}"}), file=sys.stderr)
        return 2

    try:
        report = scan_repo(repo)
    except OSError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    indent = 2 if args.pretty else None
    try:
        print(json.dumps(report, indent=indent, ensure_ascii=False))
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
