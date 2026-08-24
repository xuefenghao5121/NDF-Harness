#!/usr/bin/env python3
"""Canonical POC gate review slices (META-010).

Review slices bind human-approved contract content while leaving mutable
measurement/evidence sections outside gate SHA churn.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[3]

GATE_SNAPSHOT_SCHEMA = "ndf-gate-slice-snapshot/v1"
GATE_DRIFT_SCHEMA = "ndf-gate-drift-explain/v1"

BEGIN_RE = re.compile(
    r"^\s*<!--\s*ndf:gate-slice\s+begin=([a-z][a-z0-9_-]*)\s*-->\s*$"
)
END_RE = re.compile(
    r"^\s*<!--\s*ndf:gate-slice\s+end=([a-z][a-z0-9_-]*)\s*-->\s*$"
)

CORE_SLICES = {
    "topic_contract": "TOPIC.md",
    "design_contract": "DESIGN.md",
    "perf_bind": "PERF_BASELINE.md",
    "delta_hypothesis": "DELTA.md",
    "interface_contract": "INTERFACE.md",
}
GATE_SLICE_IDS = {
    "topic_review": ("topic_contract",),
    "design_review": ("topic_contract", "design_contract"),
    "implementation_approval": (
        "topic_contract",
        "design_contract",
        "perf_bind",
        "delta_hypothesis",
        "interface_contract",
    ),
    # Text-first POC hot path (ADR-META-003): same contract bundle as gate 3.
    "bundle_dispatch": (
        "topic_contract",
        "design_contract",
        "perf_bind",
        "delta_hypothesis",
        "interface_contract",
    ),
}
MUTABLE_SECTIONS = (
    "topic_runtime_headers",
    "perf_numbers",
    "delta_rounds",
    "evidence",
    "commits",
    "gates",
)
REQUIRED_GATE_COLUMNS = (
    "gate",
    "phrase",
    "approved_by",
    "approved_at",
    "approved_content_sha",
    "source_ref",
    "status",
)


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _canonical_json_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def parse_gates_table(text: str) -> list[dict[str, str]]:
    """Parse append-only GATES.md tables by header name (7-col or 9-col)."""
    lines = text.splitlines()
    rows: list[dict[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.lstrip().startswith("|"):
            index += 1
            continue
        cols = [cell.strip() for cell in line.strip().strip("|").split("|")]
        normalized = [
            re.sub(r"[^a-z_]", "", cell.lower().replace(" ", "_")) for cell in cols
        ]
        if not all(name in normalized for name in REQUIRED_GATE_COLUMNS):
            index += 1
            continue
        if index + 1 >= len(lines):
            break
        cursor = index + 2
        while cursor < len(lines):
            row_line = lines[cursor]
            if not row_line.lstrip().startswith("|"):
                break
            values = [
                cell.strip().strip("`")
                for cell in row_line.strip().strip("|").split("|")
            ]
            if len(values) < len(cols):
                values.extend([""] * (len(cols) - len(values)))
            row = dict(zip(normalized, values))
            if row.get("gate") and set(row["gate"]) - {"-", ":"}:
                rows.append(row)
            cursor += 1
        index = max(cursor, index + 1)
    return rows


def legacy_bundle_sha(paths: Iterable[Path], *, root: Path = ROOT) -> str | None:
    existing = sorted({path.resolve() for path in paths if path.is_file()}, key=str)
    if not existing:
        return None
    digest = hashlib.sha256()
    for path in existing:
        digest.update(_rel(path, root).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def parse_review_slices(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": _rel(path, root),
            "has_markers": False,
            "slices": {},
            "errors": [{"kind": "missing_file", "path": _rel(path, root)}],
        }
    slices: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    active_id: str | None = None
    active_start = 0
    content: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    marker_count = 0
    for line_no, line in enumerate(lines, start=1):
        begin = BEGIN_RE.match(line.rstrip("\r\n"))
        end = END_RE.match(line.rstrip("\r\n"))
        if begin:
            marker_count += 1
            slice_id = begin.group(1)
            if active_id is not None:
                errors.append(
                    {
                        "kind": "nested_gate_slice",
                        "path": _rel(path, root),
                        "line": line_no,
                        "active": active_id,
                        "nested": slice_id,
                    }
                )
                continue
            if slice_id in slices:
                errors.append(
                    {
                        "kind": "duplicate_gate_slice",
                        "path": _rel(path, root),
                        "line": line_no,
                        "slice_id": slice_id,
                    }
                )
            active_id = slice_id
            active_start = line_no
            content = []
            continue
        if end:
            marker_count += 1
            slice_id = end.group(1)
            if active_id is None:
                errors.append(
                    {
                        "kind": "unmatched_gate_slice_end",
                        "path": _rel(path, root),
                        "line": line_no,
                        "slice_id": slice_id,
                    }
                )
                continue
            if slice_id != active_id:
                errors.append(
                    {
                        "kind": "mismatched_gate_slice_end",
                        "path": _rel(path, root),
                        "line": line_no,
                        "expected": active_id,
                        "actual": slice_id,
                    }
                )
                active_id = None
                content = []
                continue
            raw = "".join(content).encode("utf-8")
            if slice_id not in slices:
                slices[slice_id] = {
                    "slice_id": slice_id,
                    "path": _rel(path, root),
                    "content_sha": hashlib.sha256(raw).hexdigest(),
                    "content_bytes": raw,
                    "start_line": active_start + 1,
                    "end_line": line_no - 1,
                }
            active_id = None
            content = []
            continue
        if active_id is not None:
            content.append(line)
    if active_id is not None:
        errors.append(
            {
                "kind": "unterminated_gate_slice",
                "path": _rel(path, root),
                "slice_id": active_id,
                "line": active_start,
            }
        )
    return {
        "path": _rel(path, root),
        "has_markers": marker_count > 0,
        "slices": slices,
        "errors": errors,
    }


def review_bundle_sha(records: Iterable[dict[str, Any]]) -> str | None:
    ordered = sorted(records, key=lambda item: (item["slice_id"], item["path"]))
    if not ordered:
        return None
    digest = hashlib.sha256()
    for item in ordered:
        digest.update(str(item["slice_id"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes(item["content_bytes"]))
        digest.update(b"\0")
    return digest.hexdigest()


def slice_content_fingerprints(path: Path, *, root: Path = ROOT) -> list[dict[str, str]]:
    """Contract-slice identity for a binder file, excluding mutable sections."""
    parsed = parse_review_slices(path, root=root)
    if not parsed.get("has_markers"):
        return []
    return [
        {"slice_id": str(record["slice_id"]), "content_sha": str(record["content_sha"])}
        for record in sorted(
            parsed.get("slices", {}).values(),
            key=lambda item: str(item.get("slice_id") or ""),
        )
    ]


def gate_spec_content_identity(spec: Mapping[str, Any] | None) -> tuple[Any, ...]:
    """Identity used to decide whether a gate *contract* changed.

    expected_content_sha + bundle_mode + slice content_sha. slice_manifest_sha
    is diagnostic and MUST NOT enter this tuple.
    """
    spec = spec or {}
    slices = []
    for item in spec.get("slices") or []:
        if not isinstance(item, Mapping):
            continue
        slices.append(
            (item.get("slice_id"), item.get("path"), item.get("content_sha"))
        )
    return (spec.get("expected_content_sha"), spec.get("bundle_mode"), tuple(slices))


def review_slice_mode_aligned(
    *,
    receipt_bundle_mode: str | None,
    expected_bundle_mode: str | None,
    receipt_slice_manifest_sha: str | None,
    expected_slice_manifest_sha: str | None,
    approved_content_sha: str | None,
    expected_content_sha: str | None,
) -> bool:
    """True when receipt bundle mode matches expected.

    review_slice identity is expected_content_sha. Manifest SHA may drift
    after line-number-only edits or semantic-manifest migration; tolerate
    that when content SHAs already match and both sides are review_slice.
    """
    receipt_mode = receipt_bundle_mode or "legacy_whole_file"
    expected_mode = expected_bundle_mode or "legacy_whole_file"
    if receipt_mode != expected_mode:
        return False
    if expected_mode != "review_slice":
        return True
    if receipt_slice_manifest_sha == expected_slice_manifest_sha:
        return True
    return bool(
        expected_content_sha
        and approved_content_sha
        and expected_content_sha == approved_content_sha
        and receipt_mode == "review_slice"
    )


def receipt_mode_aligned(receipt: Mapping[str, Any]) -> bool:
    return review_slice_mode_aligned(
        receipt_bundle_mode=receipt.get("receipt_bundle_mode")
        or receipt.get("bundle_mode"),
        expected_bundle_mode=receipt.get("expected_bundle_mode"),
        receipt_slice_manifest_sha=receipt.get("receipt_slice_manifest_sha")
        or receipt.get("slice_manifest_sha"),
        expected_slice_manifest_sha=receipt.get("expected_slice_manifest_sha"),
        approved_content_sha=receipt.get("approved_content_sha"),
        expected_content_sha=receipt.get("expected_content_sha"),
    )


def gate_bundle_specs(
    topic_dir: Path,
    *,
    root: Path = ROOT,
    proposal_paths: Iterable[Path] = (),
) -> dict[str, dict[str, Any]]:
    ndf = topic_dir / "ndf"
    impl_paths = [
        ndf / "TOPIC.md",
        ndf / "DESIGN.md",
        ndf / "PERF_BASELINE.md",
        ndf / "DELTA.md",
        ndf / "INTERFACE.md",
    ]
    legacy_paths = {
        "topic_review": [ndf / "TOPIC.md", *proposal_paths],
        "design_review": [ndf / "TOPIC.md", ndf / "DESIGN.md"],
        "implementation_approval": list(impl_paths),
        "bundle_dispatch": list(impl_paths),
    }
    parsed = {
        name: parse_review_slices(ndf / filename, root=root)
        for name, filename in CORE_SLICES.items()
    }
    proposal_records = [
        parse_review_slices(path, root=root) for path in proposal_paths
    ]
    has_markers = any(item["has_markers"] for item in parsed.values()) or any(
        item["has_markers"] for item in proposal_records
    )
    if not has_markers:
        return {
            gate: {
                "bundle_mode": "legacy_whole_file",
                "expected_content_sha": (
                    legacy_bundle_sha(paths, root=root)
                    if paths and all(path.is_file() for path in paths)
                    else None
                ),
                "bundle_paths": [_rel(path, root) for path in paths if path.is_file()],
                "slices": [],
                "slice_manifest_sha": None,
                "errors": [
                    {"kind": "missing_file", "path": _rel(path, root)}
                    for path in paths
                    if not path.is_file()
                ],
                "mutable_sections": list(MUTABLE_SECTIONS),
            }
            for gate, paths in legacy_paths.items()
        }

    global_errors: list[dict[str, Any]] = []
    for item in [*parsed.values(), *proposal_records]:
        global_errors.extend(
            error
            for error in item["errors"]
            if error.get("kind") != "missing_file"
        )

    core_by_id = {
        slice_id: parsed[slice_id]["slices"].get(slice_id)
        for slice_id in CORE_SLICES
    }
    proposal_slices: list[dict[str, Any]] = []
    proposal_errors: list[dict[str, Any]] = []
    for item in proposal_records:
        record = item["slices"].get("proposal_contract")
        if record:
            proposal_slices.append(record)
        elif item.get("has_markers"):
            # File has gate-slice markers but no proposal_contract — real defect.
            proposal_errors.append(
                {
                    "kind": "missing_gate_slice",
                    "path": item["path"],
                    "slice_id": "proposal_contract",
                }
            )
        # else: marker-less binder pointer stub (e.g. "Canonical text: spec/open/…").
        # Skip silently so it cannot null expected_content_sha for all gates.

    specs: dict[str, dict[str, Any]] = {}
    for gate, required_ids in GATE_SLICE_IDS.items():
        records = [core_by_id[slice_id] for slice_id in required_ids if core_by_id[slice_id]]
        if gate == "topic_review":
            records.extend(proposal_slices)
        missing = [
            {
                "kind": "missing_gate_slice",
                "path": _rel(ndf / CORE_SLICES[slice_id], root),
                "slice_id": slice_id,
            }
            for slice_id in required_ids
            if not core_by_id[slice_id]
        ]
        # Proposal-contract errors belong only to topic_review (the gate that
        # includes proposal slices). Do not poison design/impl expected SHAs.
        errors = [*global_errors, *missing]
        if gate == "topic_review":
            errors = [*errors, *proposal_errors]
        public_records = [
            {
                key: value
                for key, value in record.items()
                if key != "content_bytes"
            }
            for record in records
        ]
        # Manifest identity is semantic only. start_line/end_line stay on
        # public_records for UI/diagnostics but MUST NOT enter the hash —
        # inserting runtime headers (e.g. selected_decision) shifts lines
        # without changing contract bytes and must not invalidate gates.
        semantic_records = [
            {
                "slice_id": record["slice_id"],
                "path": record["path"],
                "content_sha": record["content_sha"],
            }
            for record in records
        ]
        slice_manifest = {
            "schema": "ndf-gate-slice-manifest/v1",
            "bundle_mode": "review_slice",
            "gate": gate,
            "slices": semantic_records,
        }
        specs[gate] = {
            "bundle_mode": "review_slice",
            "expected_content_sha": review_bundle_sha(records) if not errors else None,
            "bundle_paths": sorted({record["path"] for record in records}),
            "slices": public_records,
            "slice_manifest_sha": _canonical_json_sha(slice_manifest),
            "errors": errors,
            "mutable_sections": list(MUTABLE_SECTIONS),
        }
    return specs


def gate_snapshot_path(
    topic_dir: Path,
    approved_content_sha: str,
    *,
    root: Path = ROOT,
) -> Path:
    """Per-approval slice baseline for human-readable drift diffs (META-010)."""
    sha = (approved_content_sha or "").strip().lower()
    return topic_dir / "ndf" / "evidence" / "gate-snapshots" / f"{sha}.json"


def _slice_public_record(record: Mapping[str, Any]) -> dict[str, Any]:
    raw = record.get("content_bytes")
    if isinstance(raw, (bytes, bytearray)):
        text = bytes(raw).decode("utf-8", errors="replace")
    else:
        text = str(record.get("content_text") or "")
    return {
        "slice_id": str(record.get("slice_id") or ""),
        "path": str(record.get("path") or ""),
        "content_sha": str(record.get("content_sha") or ""),
        "content_text": text,
    }


def persist_gate_slice_snapshot(
    topic_dir: Path,
    gate: str,
    *,
    approved_content_sha: str,
    root: Path = ROOT,
    force: bool = False,
) -> dict[str, Any]:
    """Write review-slice baseline keyed by approved_content_sha."""
    sha = (approved_content_sha or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return {"ok": False, "error": "bad_approved_content_sha", "path": None}
    path = gate_snapshot_path(topic_dir, sha, root=root)
    if path.is_file() and not force:
        return {"ok": True, "reused": True, "path": _rel(path, root)}
    specs = gate_bundle_specs(topic_dir, root=root)
    spec = specs.get(gate) or {}
    if spec.get("bundle_mode") != "review_slice":
        return {
            "ok": False,
            "error": "legacy_whole_file_no_slice_snapshot",
            "path": None,
        }
    expected = str(spec.get("expected_content_sha") or "")
    if expected and expected != sha:
        return {
            "ok": False,
            "error": "snapshot_sha_not_current_bundle",
            "expected_content_sha": expected,
            "path": None,
        }
    # Re-parse to obtain content_bytes (public records strip them).
    records: list[dict[str, Any]] = []
    required = GATE_SLICE_IDS.get(gate) or ()
    ndf = topic_dir / "ndf"
    for slice_id in required:
        filename = CORE_SLICES.get(slice_id)
        if not filename:
            continue
        parsed = parse_review_slices(ndf / filename, root=root)
        record = (parsed.get("slices") or {}).get(slice_id)
        if record:
            records.append(_slice_public_record(record))
    payload = {
        "schema": GATE_SNAPSHOT_SCHEMA,
        "gate": gate,
        "approved_content_sha": sha,
        "bundle_mode": "review_slice",
        "slices": records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"ok": True, "reused": False, "path": _rel(path, root), "slices": len(records)}


def load_gate_slice_snapshot(
    topic_dir: Path,
    approved_content_sha: str,
    *,
    root: Path = ROOT,
) -> dict[str, Any] | None:
    sha = (approved_content_sha or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None
    path = gate_snapshot_path(topic_dir, sha, root=root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _unified_diff(path: str, before: str, after: str, *, max_lines: int = 200) -> str:
    left = before.splitlines(keepends=True)
    right = after.splitlines(keepends=True)
    lines = list(
        difflib.unified_diff(
            left,
            right,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
    )
    if len(lines) > max_lines:
        omitted = len(lines) - max_lines
        lines = lines[:max_lines] + [f"\n... ({omitted} more lines truncated)\n"]
    return "".join(lines)


def explain_gate_drift(
    topic_dir: Path,
    gate: str,
    *,
    approved_content_sha: str | None,
    expected_content_sha: str | None = None,
    root: Path = ROOT,
    write_tmp_report: bool = False,
) -> dict[str, Any]:
    """Human-readable review-slice drift vs last approved receipt (META-010)."""
    specs = gate_bundle_specs(topic_dir, root=root)
    spec = specs.get(gate) or {}
    expected = expected_content_sha or spec.get("expected_content_sha")
    approved = (approved_content_sha or "").strip().lower() or None
    current_expected = str(spec.get("expected_content_sha") or "") or None

    # Current slice texts.
    current_by_id: dict[str, dict[str, Any]] = {}
    required = GATE_SLICE_IDS.get(gate) or ()
    ndf = topic_dir / "ndf"
    for slice_id in required:
        filename = CORE_SLICES.get(slice_id)
        if not filename:
            continue
        parsed = parse_review_slices(ndf / filename, root=root)
        record = (parsed.get("slices") or {}).get(slice_id)
        if record:
            current_by_id[slice_id] = _slice_public_record(record)

    baseline = load_gate_slice_snapshot(topic_dir, approved, root=root) if approved else None
    human_next = (
        "重审契约切片后回复「派发」；或先改回契约再派发。"
    )
    if not approved or not current_expected or approved == current_expected:
        result = {
            "schema": GATE_DRIFT_SCHEMA,
            "gate": gate,
            "approved_content_sha": approved,
            "expected_content_sha": current_expected or expected,
            "drift": False,
            "changed_slices": [],
            "slice_diffs": [],
            "diff_unavailable": None,
            "human_next": "闸 SHA 已对齐；无需因漂移重审。",
            "current_slice_fingerprints": [
                {"slice_id": s, "path": r["path"], "content_sha": r["content_sha"]}
                for s, r in sorted(current_by_id.items())
            ],
        }
        return result

    if spec.get("bundle_mode") != "review_slice":
        result = {
            "schema": GATE_DRIFT_SCHEMA,
            "gate": gate,
            "approved_content_sha": approved,
            "expected_content_sha": current_expected,
            "drift": True,
            "changed_slices": [],
            "slice_diffs": [],
            "diff_unavailable": "legacy_whole_file",
            "human_next": human_next,
            "current_slice_fingerprints": [
                {"slice_id": s, "path": r["path"], "content_sha": r["content_sha"]}
                for s, r in sorted(current_by_id.items())
            ],
        }
        return result

    if baseline is None or not isinstance(baseline.get("slices"), list):
        result = {
            "schema": GATE_DRIFT_SCHEMA,
            "gate": gate,
            "approved_content_sha": approved,
            "expected_content_sha": current_expected,
            "drift": True,
            "changed_slices": [],
            "slice_diffs": [],
            "diff_unavailable": "missing_gate_snapshot",
            "human_next": human_next,
            "hint": (
                "写入「派发」回执时应用 persist_gate_slice_snapshot；"
                "或迁移为 review_slice 后重审。"
            ),
            "current_slice_fingerprints": [
                {"slice_id": s, "path": r["path"], "content_sha": r["content_sha"]}
                for s, r in sorted(current_by_id.items())
            ],
        }
        return result

    before_by_id = {
        str(item.get("slice_id")): item
        for item in baseline["slices"]
        if isinstance(item, Mapping) and item.get("slice_id")
    }
    changed: list[dict[str, str]] = []
    diffs: list[dict[str, str]] = []
    all_ids = sorted(set(before_by_id) | set(current_by_id))
    for slice_id in all_ids:
        before = before_by_id.get(slice_id) or {}
        after = current_by_id.get(slice_id) or {}
        before_sha = str(before.get("content_sha") or "")
        after_sha = str(after.get("content_sha") or "")
        if before_sha == after_sha and before_sha:
            continue
        path = str(after.get("path") or before.get("path") or slice_id)
        changed.append({"slice_id": slice_id, "path": path})
        diffs.append(
            {
                "slice_id": slice_id,
                "path": path,
                "diff": _unified_diff(
                    path,
                    str(before.get("content_text") or ""),
                    str(after.get("content_text") or ""),
                ),
            }
        )

    result: dict[str, Any] = {
        "schema": GATE_DRIFT_SCHEMA,
        "gate": gate,
        "approved_content_sha": approved,
        "expected_content_sha": current_expected,
        "drift": True,
        "changed_slices": changed,
        "slice_diffs": diffs,
        "diff_unavailable": None,
        "human_next": human_next,
        "snapshot_path": _rel(
            gate_snapshot_path(topic_dir, approved, root=root), root
        ),
    }
    if write_tmp_report:
        topic = topic_dir.name
        report = ROOT / "tmp" / f"ndf-gate-drift-{topic}.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(format_gate_drift_markdown(result), encoding="utf-8")
        result["report_path"] = _rel(report, root)
    return result


def format_gate_drift_markdown(explain: Mapping[str, Any]) -> str:
    """Chat / tmp friendly summary of explain_gate_drift."""
    lines = [
        f"# Gate drift: `{explain.get('gate')}`",
        "",
        f"- approved: `{explain.get('approved_content_sha')}`",
        f"- current:  `{explain.get('expected_content_sha')}`",
        f"- drift: {explain.get('drift')}",
    ]
    if explain.get("diff_unavailable"):
        lines.append(f"- diff_unavailable: `{explain.get('diff_unavailable')}`")
        if explain.get("hint"):
            lines.append(f"- hint: {explain.get('hint')}")
    changed = explain.get("changed_slices") or []
    if changed:
        lines.append("")
        lines.append("## Changed slices")
        for item in changed:
            lines.append(f"- `{item.get('slice_id')}` @ `{item.get('path')}`")
    for item in explain.get("slice_diffs") or []:
        lines.append("")
        lines.append(f"## Diff `{item.get('slice_id')}`")
        lines.append("```diff")
        lines.append(str(item.get("diff") or "").rstrip() or "(empty)")
        lines.append("```")
    lines.append("")
    lines.append(f"**Next:** {explain.get('human_next')}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    argparse.ArgumentParser(
        description="Canonical POC gate review slices (META-010)."
    ).parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

