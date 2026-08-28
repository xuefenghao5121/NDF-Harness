#!/usr/bin/env python3
"""Fail-closed check for ndf-genesis-design-map/v1 (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

REQUIRED_HEADER_FIELDS = (
    "schema",
    "track",
    "bootstrap_mode",
    "cycle_id",
    "source_ref",
    "source_content_sha",
    "hop",
    "status",
)
REQUIRED_SECTIONS = [
    "## Product scope (from Idea)",
    "## Module decomposition",
    "## Runtime data flow",
    "## Algorithm and invariants",
    "## Interfaces and ownership",
    "## Verification properties",
    "## Assumptions and open questions",
    "## Trace rows",
    "## Exclusions (Guidance MUST NOT become must)",
    "## Budget",
]
TRACE_ROW_MIN = 3
MODULE_ROW_MIN = 2


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(path: Path, *, repo_root: Path | None = None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    header = "\n".join(text.splitlines()[:40])
    for field in REQUIRED_HEADER_FIELDS:
        if not re.search(rf"(?m)^>\s*{field}:\s*\S+", header):
            errors.append(f"missing_header:{field}")
    if not re.search(r"(?m)^>\s*schema:\s*ndf-genesis-design-map/v1\s*$", text):
        errors.append("schema_mismatch")
    if not re.search(r"(?m)^>\s*hop:\s*genesis_synthesis\s*$", text):
        errors.append("hop_not_synthesis")
    for sec in REQUIRED_SECTIONS:
        if sec not in text:
            errors.append(f"missing_section:{sec}")
    positions = [text.find(s) for s in REQUIRED_SECTIONS]
    if any(p < 0 for p in positions) or positions != sorted(positions):
        errors.append("section_order")
    if "## Module decomposition" in text and "## Runtime data flow" in text:
        mod = text.split("## Module decomposition")[1].split("## Runtime data flow")[0]
        rows = [
            ln
            for ln in mod.splitlines()
            if ln.strip().startswith("|") and "---" not in ln and "Module" not in ln
        ]
        if len(rows) < MODULE_ROW_MIN:
            errors.append("module_decomposition_sparse")
    if "## Trace rows" in text and "## Exclusions" in text:
        trace = text.split("## Trace rows")[1].split("## Exclusions")[0]
        rows = [
            ln
            for ln in trace.splitlines()
            if ln.strip().startswith("|") and "---" not in ln and "source_section" not in ln
        ]
        if len(rows) < TRACE_ROW_MIN:
            errors.append("trace_rows_sparse")
    if "## Budget" in text:
        budget = text.split("## Budget")[1]
        if "guidance_landed_in_must: true" in budget.lower():
            errors.append("guidance_landed_in_must")
        if not re.search(r"clause_budget:\s*≤?\s*20", budget):
            errors.append("clause_budget_missing")
    if repo_root is not None:
        m = re.search(r"(?m)^>\s*source_ref:\s*(\S+)\s*$", text)
        sha_m = re.search(r"(?m)^>\s*source_content_sha:\s*([a-f0-9]{64})\s*$", text)
        if m and sha_m:
            src = repo_root / m.group(1)
            if src.is_file():
                actual = file_sha256(src)
                if actual != sha_m.group(1):
                    errors.append("source_content_sha_stale")
            else:
                errors.append("source_ref_missing")
    if re.search(r"\{#(CHR|BEH|API|CON|VER|DEF|ARCH)-", text):
        errors.append("clause_anchors_in_map")
    return errors


def build_design_evidence(
    path: Path,
    *,
    repo_root: Path,
    architecture_review_approved: bool = False,
) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    source_ref = ""
    m = re.search(r"(?m)^>\s*source_ref:\s*(\S+)\s*$", text)
    if m:
        source_ref = m.group(1)
    bundle_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if architecture_review_approved:
        return {
            "kind": "approved_design_map",
            "ref": str(path.relative_to(repo_root)).replace("\\", "/"),
            "content_sha": bundle_sha,
            "source_tag": "deduced",
            "baseline_policy": "deferred",
        }
    return {
        "kind": "design_map_draft",
        "ref": str(path.relative_to(repo_root)).replace("\\", "/"),
        "content_sha": bundle_sha,
        "source_tag": "deduced",
        "baseline_policy": "deferred",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ndf-genesis-design-map/v1")
    sub = parser.add_subparsers(dest="command")
    check_p = sub.add_parser("check", help="fail-closed structural check")
    check_p.add_argument("path", type=Path)
    check_p.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "check":
        path = args.path
        if not path.is_file():
            print(f"missing_file:{path}", file=sys.stderr)
            return 2
        root = args.repo_root.resolve()
        errs = check(path, repo_root=root)
        if errs:
            print("ILLEGAL", errs)
            return 1
        print("OK", path)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
