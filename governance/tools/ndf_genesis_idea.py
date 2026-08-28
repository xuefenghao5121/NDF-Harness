#!/usr/bin/env python3
"""Fail-closed check for ndf-genesis-idea/v1 filled cycle files (stdlib only)."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_HEADER_FIELDS = (
    "schema",
    "track",
    "bootstrap_mode",
    "cycle_id",
    "maps_to",
    "status",
)
REQUIRED_SECTIONS = [
    "## Verbatim intent",
    "## Problem and user",
    "## In-scope (this cycle)",
    "## Out-of-scope (this cycle)",
    "## Success (not SLA)",
    "## Hard constraints",
    "## Guidance (non-normative)",
    "## Mapping",
]
GUIDANCE_LEAD = "本栏不是契约。Control MUST NOT 将本栏写入 BEH/API/CON-SLA must。"
HEADER_CYCLE = re.compile(r"(?m)^>\s*cycle_id:\s*`?([a-z0-9][a-z0-9-]*)`?\s*$")
ANY_CYCLE = re.compile(r"cycle_id:\s*`?([a-z0-9][a-z0-9-]*)`?", re.I)
IN_SCOPE_NEXT_PHASE = re.compile(
    r"(?i)(then\s+(do\s+)?(phase|cycle)|phase\s*[2-9]|同时做|下一阶段)"
)


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    header = "\n".join(text.splitlines()[:30])
    for field in REQUIRED_HEADER_FIELDS:
        if not re.search(rf"(?m)^>\s*{field}:\s*\S+", header):
            errors.append(f"missing_header:{field}")
    if "maps_to: product_contract" in text:
        errors.append("maps_to_product_contract")
    if not re.search(r"(?m)^>\s*maps_to:\s*skeleton\s*$", text):
        errors.append("maps_to_not_skeleton")
    if not re.search(r"(?m)^>\s*schema:\s*ndf-genesis-idea/v1\s*$", text):
        errors.append("schema_mismatch")
    header_ids = HEADER_CYCLE.findall(header)
    if len(set(header_ids)) > 1:
        errors.append("multiple_header_cycle_id")
    this_cycle = header_ids[0] if header_ids else ""
    for sec in REQUIRED_SECTIONS:
        if sec not in text:
            errors.append(f"missing_section:{sec}")
    positions = [text.find(s) for s in REQUIRED_SECTIONS]
    if any(p < 0 for p in positions) or positions != sorted(positions):
        errors.append("section_order")
    if "## Guidance (non-normative)" in text and "## Mapping" in text:
        guidance = text.split("## Guidance (non-normative)")[1].split("## Mapping")[0]
        if GUIDANCE_LEAD not in guidance:
            errors.append("guidance_lead_missing")
    if "## Out-of-scope (this cycle)" in text and "## Success" in text:
        out = text.split("## Out-of-scope (this cycle)")[1].split("## Success")[0]
        if not re.search(r"(?m)^\s*\d+\.", out):
            errors.append("out_of_scope_empty")
    if re.search(r"\{#(CHR|BEH|API|CON|VER|DEF|ARCH)-", text):
        errors.append("clause_anchors")
    for block in re.findall(r"```[\s\S]*?```", text):
        if block.count("\n") > 16:
            errors.append("code_fence_too_long")
    if "## In-scope (this cycle)" in text and "## Out-of-scope" in text:
        in_scope = text.split("## In-scope (this cycle)")[1].split("## Out-of-scope")[0]
        if IN_SCOPE_NEXT_PHASE.search(in_scope):
            errors.append("in_scope_multi_cycle")
        for cid in ANY_CYCLE.findall(in_scope):
            if this_cycle and cid != this_cycle:
                errors.append(f"in_scope_foreign_cycle:{cid}")
    if "## Success (not SLA)" in text and "## Hard constraints" in text:
        success = text.split("## Success (not SLA)")[1].split("## Hard constraints")[0]
        for match in re.finditer(r"^\|([^|]+)\|([^|]+)\|([^|]+)\|$", success, re.M):
            status = match.group(3).strip().lower()
            if status in {"status"} or set(status.replace(" ", "")) <= {"-"}:
                continue
            if status not in {"draft", "tbd"}:
                errors.append(f"success_status_illegal:{status}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate ndf-genesis-idea/v1 filled cycle files"
    )
    sub = parser.add_subparsers(dest="command")
    check_p = sub.add_parser("check", help="fail-closed structural check")
    check_p.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "check":
        path = args.path
        if not path.is_file():
            print(f"missing_file:{path}", file=sys.stderr)
            return 2
        errs = check(path)
        if errs:
            print("ILLEGAL", errs)
            return 1
        print("OK", path)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
