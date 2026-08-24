#!/usr/bin/env python3
"""Compile Task Manifests and bounded role-specific NDF contexts.

Compilation is read-only with respect to project truth. Reports may only be
written below ``<repo>/tmp``; explicit ``--episode`` additionally records
content-addressed Replay evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any, Iterable, Mapping

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ndf_index as ndx  # noqa: E402
import ndf_gate_slices  # noqa: E402
from ndf_workflow_evidence import (  # noqa: E402
    canonical_json_sha,
    file_sha,
    safe_tmp_report_path,
)

ROOT = Path(__file__).resolve().parents[3]
ID_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\b")
WIKI_RE = re.compile(r"\[\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?:\s*\|\s*[^\]]+)?\]\]")
PATH_RE = re.compile(
    r"(?:`|\()((?:poc|spec|src|include|tests)/[A-Za-z0-9_./-]+)(?:`|\))"
)
HEADER_RE = re.compile(r"(?im)^>\s*([a-z][a-z0-9_-]*)\s*:\s*(.+?)\s*$")
BINDER_NAMES = (
    "TOPIC.md",
    "DESIGN.md",
    "PERF_BASELINE.md",
    "DELTA.md",
    "INTERFACE.md",
    "GATES.md",
)
GATE_PHRASES = {
    "topic_review": "TOPIC已审核",
    "design_review": "DESIGN已审核",
    "implementation_approval": "可以开始实现",
}
PROCESS_TASKS = frozenset(
    {
        "ndf_improvement_proposal",
        "ndf_improvement_land",
        "process_proposal",
        "spec_health",
        "project_control",
        "process",
    }
)
PRODUCT_PROPOSAL_TASKS = frozenset({"product_proposal", "control_proposal"})
PROJECT_CONTROL_STAGE_TASKS = {
    "ndf_improvement_proposal": frozenset({"draft"}),
    "ndf_improvement_land": frozenset({"confirm_land", "review"}),
}
# Control tasks whose job includes inspecting/fixing gate SHA drift — mismatch
# must not fail context-verify closed (that would prevent OpenClaw dispatch).
GATE_AUDIT_TASKS = frozenset(
    {
        "gate_sha_audit",
        "gate_pipeline",
        "legacy_gate_audit",
        "gate_receipt_draft",
    }
)
CONTROL_REPAIR_TASKS = GATE_AUDIT_TASKS | frozenset(
    {"binder_amend", "binder_pipeline"}
)
MEASUREMENT_TASKS = frozenset({"poc_measurement", "measurement", "verify", "verification"})
MEASUREMENT_REPAIR_TASKS = frozenset({"poc_measurement", "measurement"})
SEMANTIC_TASKS = frozenset({"promote", "partial", "semantic_core", "semantic-core"})
TASK_DEFAULT_SEEDS = {
    "poc_measurement": ("META-007", "META-012", "BEH-025"),
    "measurement": ("META-007", "META-012"),
    "verify": ("META-012",),
    "verification": ("META-012",),
    "poc_prepare_baseline": ("META-012", "BEH-018", "CON-POC-001", "BEH-025"),
    "promote": ("BEH-019", "META-004", "META-005", "META-012"),
    "partial": ("BEH-019", "META-004", "META-012"),
    "binder_amend": ("BEH-025", "META-010", "META-012"),
    "gate_sha_audit": ("META-010", "META-012"),
    "control_proposal": ("META-011", "META-012", "ADR-META-004"),
    "product_proposal": ("META-011", "META-012", "ADR-META-004"),
    "process_proposal": ("META-011", "META-012", "META-014", "ADR-META-004"),
    "ndf_improvement_proposal": ("META-011", "META-012", "META-014", "ADR-META-004"),
    "ndf_improvement_land": ("META-011", "META-012", "META-014"),
    "episode_replay": ("META-012", "META-013", "META-015"),
    "replay_audit": ("META-012", "META-013", "META-015"),
    "replay_sandbox": ("META-012", "META-013", "META-015"),
}
PRIVILEGES = {
    "canvas": {
        "allowed_write_roots": [],
        "forbidden_write_paths": ["*"],
        "summary_only": True,
    },
    "human": {
        "allowed_write_roots": [],
        "forbidden_write_paths": ["*"],
        "summary_only": True,
    },
    "openclaw": {
        # Default empty; task-specific privileges narrow to one plane (ADR-META-004).
        "allowed_write_roots": [],
        "forbidden_write_paths": ["src/", "include/", "tests/", "spec/meta/process.md"],
        "summary_only": False,
    },
    "claude-code": {
        "allowed_write_roots": [],
        "forbidden_write_paths": ["spec/meta/", "spec/00-charter/", "spec/10-architecture/"],
        "summary_only": False,
    },
    "project-control": {
        "allowed_write_roots": ["spec/meta/open/"],
        "forbidden_write_paths": ["src/", "include/", "tests/", "spec/00-charter/", "spec/20-behavior/"],
        "summary_only": False,
    },
}

COMPILER_ID = "ndf-context-compiler/v1"
MANIFEST_DERIVED_FIELDS = (
    "source_generation_sha",
    "binder_roots",
    "clause_seeds",
    "seed_sources",
    "shared_graph_closure",
    "implementation_surface",
    "ledger_joins",
    "baseline",
    "human_gates",
    "evidence_refs",
    "trunk_ref_joins",
    "conflicts",
    "role_policies",
)


def _manifest_derivation_digest(manifest: Mapping[str, Any]) -> str:
    return canonical_json_sha(
        {
            field: manifest.get(field)
            for field in MANIFEST_DERIVED_FIELDS
        }
    )


def _role_task_compatible(role: str, task: str, track: str) -> bool:
    if role in {"canvas", "human"}:
        return True
    if role == "project-control":
        return track == "process" or task in PROCESS_TASKS
    if role == "openclaw":
        return track == "process" or task in PROCESS_TASKS or task in {
            "legacy_gate_audit",
            "gate_sha_audit",
            "gate_receipt_draft",
            "binder_amend",
            "gate_pipeline",
            "binder_pipeline",
            "control_proposal",
            "product_proposal",
            "process_proposal",
            "close",
            "promote",
            "partial",
            "reject",
        }
    if role == "claude-code":
        return track in {"bootstrap", "poc", "promote", "bug", "refactor", "rollback"} and (
            task in {
                "project_genesis",
                "implement",
                "poc_implementation",
                "poc_prepare_baseline",
                "poc_measurement",
                "measurement",
                "verify",
                "verification",
                "repair",
                "promote",
                "partial",
            }
            or task.endswith("_repair")
        )
    return False


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _rel(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {path}") from exc


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _header(text: str, key: str) -> str | None:
    for name, value in HEADER_RE.findall(text):
        if name.replace("-", "_") == key.replace("-", "_"):
            return value.strip()
    return None


def _section(text: str, title: str) -> str:
    match = re.search(
        rf"(?is)^##+\s+{re.escape(title)}[^\n]*\n(.*?)(?=^##+\s|\Z)",
        text,
    )
    return match.group(1) if match else ""


def _ids(text: str) -> list[str]:
    return _unique(match.group(1) for match in ID_RE.finditer(text))


def _proposal_paths(topic_text: str, ndf_dir: Path, root: Path) -> list[Path]:
    candidates: list[Path] = []
    proposal_dir = ndf_dir / "proposals"
    if proposal_dir.is_dir():
        candidates.extend(sorted(proposal_dir.glob("*.md")))
    for match in re.finditer(r"(?P<path>(?:spec/|poc/)[A-Za-z0-9_./-]*proposal[A-Za-z0-9_./-]*\.md)", topic_text):
        path = root / match.group("path")
        if path.is_file():
            candidates.append(path)
    # Markdown links may be relative to the binder directory.
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+proposal[^)]*\.md)\)", topic_text, re.I):
        raw = match.group(1)
        for base in (root, ndf_dir):
            path = (base / raw).resolve()
            if path.is_file():
                candidates.append(path)
                break
    unique = sorted({path.resolve() for path in candidates}, key=lambda p: _rel(p, root))
    # Stub pointers under ndf/proposals/ without proposal_contract markers must
    # not enter gate_bundle_specs: a single missing_gate_slice error nulls
    # expected_content_sha for every gate (breaks repair-pack / context-verify
    # while topic_view, which only hashes spec/open/, still looks valid).
    with_contract: list[Path] = []
    for path in unique:
        text = _read(path)
        if (
            "ndf:gate-slice begin=proposal_contract" in text
            or "ndf:gate-slice:start id=proposal_contract" in text
            or 'id="proposal_contract"' in text
            or re.search(r"gate-slice[^>\n]*proposal_contract", text)
        ):
            with_contract.append(path)
    # Prefer contract-bearing paths only. Falling back to marker-less stubs
    # would reintroduce gate_sha expected=null via missing_gate_slice.
    return with_contract


def binder_paths(root: Path, topic: str | None) -> list[Path]:
    """Return existing binder artifacts in authoritative read order."""
    if not topic:
        return []
    ndf_dir = root / "poc" / topic / "ndf"
    topic_path = ndf_dir / "TOPIC.md"
    topic_text = _read(topic_path) if topic_path.is_file() else ""
    paths = [ndf_dir / name for name in BINDER_NAMES if (ndf_dir / name).is_file()]
    paths.extend(_proposal_paths(topic_text, ndf_dir, root))
    evidence = ndf_dir / "evidence"
    if evidence.is_dir():
        paths.extend(sorted(path for path in evidence.rglob("*") if path.is_file()))
    commits = ndf_dir / "COMMITS.md"
    if commits.is_file():
        paths.append(commits)
    return paths


def extract_seeds(
    root: Path,
    topic: str | None,
    task: str,
    explicit: Iterable[str] = (),
) -> tuple[list[str], dict[str, list[str]]]:
    """Extract traceable clause seeds from binder/proposals/ledger/defaults."""
    sources: dict[str, list[str]] = {
        "topic": [],
        "proposals": [],
        "commits": [],
        "task_defaults": list(TASK_DEFAULT_SEEDS.get(task, ("META-012",))),
        "explicit": list(explicit),
    }
    if topic:
        ndf_dir = root / "poc" / topic / "ndf"
        topic_path = ndf_dir / "TOPIC.md"
        topic_text = _read(topic_path) if topic_path.is_file() else ""
        draft = _section(topic_text, "Draft clauses")
        header_drafts = _header(topic_text, "draft_clauses") or ""
        sources["topic"] = _ids(draft + "\n" + header_drafts)
        for path in _proposal_paths(topic_text, ndf_dir, root):
            # Anchors and wiki references in explicitly linked proposals are seeds.
            sources["proposals"].extend(_ids(_read(path)))
        commits = ndf_dir / "COMMITS.md"
        if commits.is_file():
            text = _read(commits)
            clauses_section = "\n".join(
                line for line in text.splitlines() if "clause" in line.lower() or ID_RE.search(line)
            )
            sources["commits"] = _ids(clauses_section)
    for key in sources:
        sources[key] = _unique(sources[key])
    seeds = _unique(value for key in sources for value in sources[key])
    return seeds, sources


def _load_graph(root: Path, meta_only: bool) -> dict[str, ndx.Clause]:
    # ndf_index keeps module-level paths; patching them makes reuse explicit and local.
    old_root, old_spec = ndx.ROOT, ndx.SPEC
    try:
        ndx.ROOT = root
        ndx.SPEC = root / "spec"
        return ndx.load_graph(False, False, meta_only=meta_only)
    finally:
        ndx.ROOT, ndx.SPEC = old_root, old_spec


def _clause_text(clause: ndx.Clause, root: Path) -> str:
    path = root / "spec" / clause.file
    lines = _read(path).splitlines()
    start = max(0, clause.line - 1)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if ndx.HEADING_RE.match(lines[index]) and ndx.ANCHOR_RE.search(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]).rstrip() + "\n"


def graph_closure(
    graph: Mapping[str, ndx.Clause],
    seeds: Iterable[str],
    *,
    task: str,
    depth: int,
    node_budget: int,
    byte_budget: int,
    root: Path,
    include_bodies: bool = True,
) -> dict[str, Any]:
    """Compute deterministic, bounded task-specific graph closure."""
    relations = ["depends-on", "refines"]
    verify_mode = task in MEASUREMENT_TASKS or "verify" in task
    semantic_mode = task in SEMANTIC_TASKS or "semantic" in task
    if verify_mode:
        relations.append("verifies")
    if semantic_mode:
        relations.append("model")
    reverse_verifies: dict[str, list[str]] = {}
    if verify_mode:
        for cid, clause in graph.items():
            for target in clause.edges.get("verifies", []):
                reverse_verifies.setdefault(target, []).append(cid)
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in _unique(seeds))
    seen: set[str] = set()
    nodes: list[dict[str, Any]] = []
    missing: list[str] = []
    blockers: list[dict[str, str]] = []
    bytes_used = 0
    truncated: list[str] = []
    while queue:
        cid, hop = queue.popleft()
        if cid in seen:
            continue
        if len(nodes) >= node_budget:
            truncated.append("node_budget")
            break
        seen.add(cid)
        clause = graph.get(cid)
        if clause is None:
            missing.append(cid)
            continue
        # clause_sha always fingerprints clause body so shallow Canvas
        # previews (include_bodies=False) do not fake-drift against verify.
        text_for_sha = _clause_text(clause, root)
        clause_sha = canonical_json_sha(text_for_sha)
        if include_bodies:
            text = text_for_sha
            size = len(text.encode("utf-8"))
        else:
            text = ""
            size = 0
        if include_bodies and bytes_used + size > byte_budget:
            truncated.append("byte_budget")
            continue
        bytes_used += size
        node = {
            "id": cid,
            "title": clause.title,
            "file": f"spec/{clause.file}",
            "line": clause.line,
            "kind": clause.kind,
            "level": clause.level,
            "status": clause.status,
            "scope": clause.meta.get("scope"),
            "trunk_ref": clause.meta.get("trunk-ref"),
            "hop": hop,
            "clause_sha": clause_sha,
            "bytes": size,
            "edges": {key: list(value) for key, value in sorted(clause.edges.items())},
        }
        nodes.append(node)
        conflicts = clause.edges.get("conflicts-with", [])
        for target in conflicts:
            blockers.append({"kind": "clause_conflict", "source": cid, "target": target})
        if hop >= depth:
            if any(clause.edges.get(rel) for rel in relations):
                truncated.append("depth")
            continue
        neighbors: list[str] = []
        for relation in relations:
            neighbors.extend(clause.edges.get(relation, []))
        if semantic_mode and hop == 0:
            neighbors.extend(clause.edges.get("affects", []))
            neighbors.extend(clause.edges.get("couples-with", []))
        if clause.status == "deprecated":
            neighbors.extend(clause.edges.get("superseded-by", []))
        if verify_mode:
            neighbors.extend(sorted(reverse_verifies.get(cid, [])))
        for target in _unique(neighbors):
            if target not in seen:
                queue.append((target, hop + 1))
    return {
        "relations": relations,
        "direction": "upstream; verifies also reverse",
        "depth": depth,
        "node_budget": node_budget,
        "byte_budget": byte_budget,
        "bytes_used": bytes_used,
        "nodes": nodes,
        "missing_seeds": _unique(missing),
        "truncated": sorted(set(truncated)),
        "blockers": blockers,
    }


def _file_records(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    records = []
    for index, path in enumerate(paths):
        if "/proposals/" in path.as_posix():
            phase = "proposal"
        elif "/evidence/" in path.as_posix():
            phase = "evidence"
        elif path.name == "COMMITS.md":
            phase = "git"
        else:
            phase = "binder"
        slices = (
            ndf_gate_slices.slice_content_fingerprints(path, root=root)
            if path.is_file()
            else []
        )
        records.append(
            {
                "order": index,
                "path": _rel(path, root),
                "sha256": file_sha(path),
                "bytes": path.stat().st_size,
                "phase": phase,
                "reason": f"{phase}_root",
                **({"slices": slices} if slices else {}),
            }
        )
    return records


def _perf_info(root: Path, topic: str | None) -> dict[str, Any]:
    if not topic:
        return {"path": None, "baseline_status": "n/a", "bind": {}, "bind_sha": None}
    topic_path = root / "poc" / topic / "ndf" / "TOPIC.md"
    perf_path = root / "poc" / topic / "ndf" / "PERF_BASELINE.md"
    topic_text = _read(topic_path) if topic_path.is_file() else ""
    perf_text = _read(perf_path) if perf_path.is_file() else ""
    fields = dict(HEADER_RE.findall(perf_text))
    normalized = {key.replace("-", "_"): value.strip() for key, value in fields.items()}
    bind = {
        key: normalized.get(key)
        for key in ("vs", "baseline", "config_id", "config", "measure_script", "measure_binary", "trunk_sha")
        if normalized.get(key)
    }
    return {
        "path": _rel(perf_path, root) if perf_path.is_file() else None,
        "baseline_status": (_header(topic_text, "baseline_status") or "unknown").split()[0],
        "baseline_trunk_sha": _header(topic_text, "baseline_trunk_sha"),
        "baseline_protocol": _header(topic_text, "baseline_protocol"),
        "bind": bind,
        "bind_sha": canonical_json_sha(bind) if bind else None,
    }


def _gate_info(root: Path, topic: str | None) -> dict[str, Any]:
    if not topic:
        return {"path": None, "path_sha": None, "receipts": []}
    ndf = root / "poc" / topic / "ndf"
    gates = ndf / "GATES.md"
    receipts: list[dict[str, Any]] = []
    if gates.is_file():
        receipts = [
            dict(row) for row in ndf_gate_slices.parse_gates_table(_read(gates))
        ]
    proposal_paths = _proposal_paths(_read(ndf / "TOPIC.md") if (ndf / "TOPIC.md").is_file() else "", ndf, root)
    specs = ndf_gate_slices.gate_bundle_specs(
        root / "poc" / topic,
        root=root,
        proposal_paths=proposal_paths,
    )
    expected = {
        gate: spec.get("expected_content_sha") for gate, spec in specs.items()
    }
    history = list(receipts)
    latest_by_gate: dict[str, dict[str, Any]] = {}
    for receipt in history:
        latest_by_gate[str(receipt.get("gate"))] = receipt
    receipts = [
        latest_by_gate[gate]
        for gate in ("topic_review", "design_review", "implementation_approval")
        if gate in latest_by_gate
    ]
    for receipt in receipts:
        spec = specs.get(receipt["gate"], {})
        receipt["expected_content_sha"] = spec.get("expected_content_sha")
        receipt["expected_phrase"] = GATE_PHRASES.get(receipt["gate"])
        receipt["receipt_bundle_mode"] = (
            receipt.get("bundle_mode") or "legacy_whole_file"
        )
        receipt["receipt_slice_manifest_sha"] = (
            receipt.get("slice_manifest_sha") or None
        )
        receipt["expected_bundle_mode"] = spec.get("bundle_mode")
        receipt["expected_slice_manifest_sha"] = spec.get(
            "slice_manifest_sha"
        )
    return {
        "path": _rel(gates, root) if gates.is_file() else None,
        "path_sha": file_sha(gates) if gates.is_file() else None,
        "expected": expected,
        "bundle_specs": specs,
        "bundle_mode": (
            "review_slice"
            if specs
            and all(
                spec.get("bundle_mode") == "review_slice"
                for spec in specs.values()
            )
            else "legacy_whole_file"
        ),
        "mutable_sections": list(ndf_gate_slices.MUTABLE_SECTIONS),
        "receipts": receipts,
        "receipt_history_count": len(history),
    }


def _implementation_surface(paths: Iterable[Path], root: Path, topic: str | None) -> list[str]:
    found: list[str] = []
    for path in paths:
        for match in PATH_RE.finditer(_read(path)):
            candidate = match.group(1).rstrip(".,:;")
            if (root / candidate).exists():
                found.append(candidate)
    if topic:
        found.append(f"poc/{topic}/")
    return _unique(found)


def _ledger_joins(root: Path, topic: str | None) -> list[dict[str, Any]]:
    if not topic:
        return []
    path = root / "poc" / topic / "ndf" / "COMMITS.md"
    if not path.is_file():
        return []
    joins: list[dict[str, Any]] = []
    for line_no, line in enumerate(_read(path).splitlines(), 1):
        commits = _unique(re.findall(r"(?<![0-9a-f])([0-9a-f]{7,64})(?![0-9a-f])", line))
        clauses = _ids(line)
        paths = _unique(match.group(1) for match in PATH_RE.finditer(line))
        proposals = [value for value in paths if "proposal" in value.lower()]
        if commits or clauses or paths:
            joins.append(
                {
                    "source": _rel(path, root),
                    "line": line_no,
                    "commits": commits,
                    "clauses": clauses,
                    "paths": paths,
                    "proposals": proposals,
                }
            )
    return joins


def _normalize_control_binding(
    root: Path,
    task: str,
    binding: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    stages = PROJECT_CONTROL_STAGE_TASKS.get(task)
    if stages is None:
        if binding is not None:
            raise ValueError(f"control binding is not valid for task {task}")
        return None
    if not isinstance(binding, Mapping):
        raise ValueError(f"{task} requires a control binding")
    value = json.loads(json.dumps(dict(binding)))
    required = ("proposal_id", "flow_id", "hop", "origin")
    if any(not isinstance(value.get(field), str) or not value[field].strip() for field in required):
        raise ValueError("control binding missing proposal_id/flow_id/hop/origin")
    if value["hop"] not in stages:
        raise ValueError(
            f"incompatible project-control stage: {task}/{value['hop']}"
        )
    proposal_path = value.get("proposal_path")
    if not isinstance(proposal_path, str) or not proposal_path:
        raise ValueError("control binding requires proposal_path")
    resolved = (root / proposal_path).resolve()
    meta_open = (root / "spec" / "meta" / "open").resolve()
    try:
        resolved.relative_to(meta_open)
    except ValueError as exc:
        raise ValueError("control proposal_path must be under spec/meta/open/") from exc
    if not resolved.name.startswith("proposal-meta-") or resolved.suffix != ".md":
        raise ValueError("control proposal_path must name proposal-meta-*.md")
    value["proposal_path"] = _rel(resolved, root)
    proposal_sha = value.get("proposal_sha")
    if value["hop"] in {"confirm_land", "review"}:
        if not resolved.is_file() or not isinstance(proposal_sha, str):
            raise ValueError("land/review control binding requires existing proposal_sha")
        if file_sha(resolved) != proposal_sha:
            raise ValueError("control proposal_sha does not match proposal bytes")
    elif proposal_sha is not None and (
        not isinstance(proposal_sha, str)
        or (resolved.is_file() and file_sha(resolved) != proposal_sha)
    ):
        raise ValueError("draft proposal_sha does not match proposal bytes")
    intent_sha = value.get("intent_sha")
    if value["hop"] == "draft" and not (
        isinstance(intent_sha, str) and re.fullmatch(r"[0-9a-f]{64}", intent_sha)
    ):
        raise ValueError("draft control binding requires intent_sha")
    targets = value.get("land_targets") or []
    if not isinstance(targets, list) or not all(
        isinstance(item, str) and item and not Path(item).is_absolute()
        for item in targets
    ):
        raise ValueError("control land_targets must be relative path strings")
    normalized_targets: list[str] = []
    for item in targets:
        target = (root / item).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"control land target escapes repository: {item}") from exc
        normalized_targets.append(_rel(target, root))
    value["land_targets"] = _unique(normalized_targets)
    return value


def _privileges(
    role: str,
    task: str,
    track: str,
    topic: str | None,
    control: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if role not in PRIVILEGES:
        raise ValueError(f"unknown role: {role}")
    value = json.loads(json.dumps(PRIVILEGES[role]))
    value["allowed_sections"] = []
    value["forbidden_sections"] = []
    value["mutable_sections"] = list(ndf_gate_slices.MUTABLE_SECTIONS)
    if role == "claude-code":
        if track == "poc":
            value["allowed_write_roots"] = [f"poc/{topic}/"] if topic else []
            value["forbidden_write_paths"].extend(["src/", "include/", "tests/"])
        elif track in {"promote", "bug", "refactor", "rollback"}:
            value["allowed_write_roots"] = ["src/", "include/", "tests/", "spec/50-verification/"]
        if track == "poc":
            value["allowed_sections"] = [
                "poc_code",
                "perf_numbers",
                "delta_rounds",
                "evidence",
                "commits_append",
                "topic_runtime_headers",
            ]
            value["forbidden_sections"] = [
                "topic_contract",
                "design_contract",
                "perf_bind",
                "delta_hypothesis",
                "interface_contract",
                "gate_receipts",
            ]
    if task == "poc_measurement" and topic and f"poc/{topic}/" not in value["allowed_write_roots"]:
        value["allowed_write_roots"].append(f"poc/{topic}/")
    if role == "openclaw":
        if task == "gate_sha_audit":
            value["allowed_write_roots"] = []
        elif task in {
            "legacy_gate_audit",
            "gate_receipt_draft",
            "gate_pipeline",
        }:
            value["allowed_write_roots"] = (
                [f"poc/{topic}/ndf/GATES.md"] if topic else []
            )
            value["allowed_sections"] = ["gate_receipts"]
            value["forbidden_sections"] = [
                "topic_contract",
                "design_contract",
                "perf_bind",
                "perf_numbers",
                "delta_hypothesis",
                "delta_rounds",
                "interface_contract",
                "evidence",
                "commits_append",
            ]
        elif task in {"binder_amend", "binder_pipeline"}:
            value["allowed_write_roots"] = (
                [
                    f"poc/{topic}/ndf/{name}"
                    for name in (
                        "TOPIC.md",
                        "DESIGN.md",
                        "PERF_BASELINE.md",
                        "DELTA.md",
                        "INTERFACE.md",
                        "COMMITS.md",
                    )
                ]
                if topic
                else []
            )
            value["allowed_sections"] = [
                "topic_contract",
                "design_contract",
                "perf_bind",
                "delta_hypothesis",
                "interface_contract",
                "ledger_skeleton",
                "topic_runtime_headers",
            ]
            value["forbidden_sections"] = [
                "gate_receipts",
                "perf_numbers",
                "delta_rounds",
                "evidence",
                "commits_append",
                "decision_selected",
            ]
        elif task in {"control_proposal", "product_proposal"}:
            value["allowed_write_roots"] = ["spec/open/"]
            value["forbidden_write_paths"] = _unique(
                [
                    *value.get("forbidden_write_paths", []),
                    "spec/meta/",
                    "spec/meta/open/",
                ]
            )
        elif task == "process_proposal":
            value["allowed_write_roots"] = ["spec/meta/open/"]
            value["forbidden_write_paths"] = _unique(
                [
                    *value.get("forbidden_write_paths", []),
                    "spec/open/",
                    "src/",
                    "include/",
                    "tests/",
                ]
            )
    if role == "project-control":
        hop = str((control or {}).get("hop") or "")
        proposal_path = (control or {}).get("proposal_path")
        if task == "ndf_improvement_land" and hop == "confirm_land":
            value["allowed_write_roots"] = [
                *list((control or {}).get("land_targets") or []),
                *([str(proposal_path)] if proposal_path else []),
            ]
        elif task == "ndf_improvement_land" and hop == "review":
            value["allowed_write_roots"] = (
                [str(proposal_path)] if proposal_path else []
            )
        elif task == "ndf_improvement_land":
            value["allowed_write_roots"] = ["spec/meta/", "spec/meta/open/"]
        elif task == "ndf_improvement_proposal" and proposal_path:
            value["allowed_write_roots"] = [str(proposal_path)]
        else:
            value["allowed_write_roots"] = ["spec/meta/open/"]
    value["allowed_write_roots"] = _unique(value["allowed_write_roots"])
    value["forbidden_write_paths"] = _unique(value["forbidden_write_paths"])
    return value


def compile_plan(
    *,
    root: Path = ROOT,
    topic: str | None,
    role: str,
    task: str,
    track: str,
    seed_ids: Iterable[str] = (),
    depth: int = 2,
    node_budget: int = 80,
    byte_budget: int = 256_000,
    include_bodies: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    repo_head = _git(root, "rev-parse", "HEAD")
    paths = binder_paths(root, topic)
    records = _file_records(paths, root)
    seeds, seed_sources = extract_seeds(root, topic, task, seed_ids)
    meta_only = role == "project-control" or task in PROCESS_TASKS or track == "process"
    graph = _load_graph(root, meta_only)
    closure = graph_closure(
        graph,
        seeds,
        task=task,
        depth=max(0, depth),
        node_budget=max(1, node_budget),
        byte_budget=max(1, byte_budget),
        root=root,
        include_bodies=include_bodies,
    )
    plan: dict[str, Any] = {
        "schema": "ndf-context-plan/v1",
        "workspace": {
            "repo_root": str(root),
            "repo_head": repo_head,
            "topic": topic,
        },
        "role": role,
        "task": task,
        "track": track,
        "topic": topic,
        "source_generation_sha": canonical_json_sha(
            {
                "repo_head": repo_head,
                "files": [{"path": item["path"], "sha256": item["sha256"]} for item in records],
                "clauses": [
                    {"id": item["id"], "clause_sha": item["clause_sha"]}
                    for item in closure["nodes"]
                ],
            }
        ),
        "ordered_reads": records,
        "seed_ids": seeds,
        "seed_sources": seed_sources,
        "graph": closure,
        "implementation_surface": _implementation_surface(paths, root, topic),
        "ledger_joins": _ledger_joins(root, topic),
        "baseline": _perf_info(root, topic),
        "gates": _gate_info(root, topic),
        "evidence_refs": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in records
            if "/evidence/" in item["path"]
        ],
        "trunk_ref_joins": [
            {"id": item["id"], "trunk_ref": item["trunk_ref"]}
            for item in closure["nodes"]
            if item.get("trunk_ref")
        ],
        "privileges": _privileges(role, task, track, topic),
        "human_phrase": None,
    }
    approved = {
        item["gate"]: item
        for item in plan["gates"]["receipts"]
        if item.get("status", "").lower() in {"approved", "valid"}
    }
    if task in {"poc_measurement", "implement", "poc_implementation", "poc_prepare_baseline"} and "implementation_approval" not in approved:
        plan["human_phrase"] = "可以开始实现"
    plan["plan_sha"] = canonical_json_sha(plan)
    return plan


def create_manifest(
    *,
    root: Path = ROOT,
    topic: str | None,
    task: str,
    track: str,
    business_goal: str = "",
    control_binding: Mapping[str, Any] | None = None,
    seed_ids: Iterable[str] = (),
    depth: int = 2,
    node_budget: int = 80,
    byte_budget: int = 256_000,
    include_bodies: bool = True,
) -> dict[str, Any]:
    """Compile the role-neutral parent shared by all task views."""
    root = root.resolve()
    control = _normalize_control_binding(root, task, control_binding)
    requested_seeds = tuple(seed_ids)
    source = compile_plan(
        root=root,
        topic=topic,
        role="canvas",
        task=task,
        track=track,
        seed_ids=requested_seeds,
        depth=depth,
        node_budget=node_budget,
        byte_budget=byte_budget,
        include_bodies=include_bodies,
    )
    manifest: dict[str, Any] = {
        "schema": "ndf-task-manifest/v1",
        "intent": business_goal or task,
        "business_goal": business_goal or task,
        "topic": topic,
        "task": task,
        "track": track,
        "control": control,
        "compiler_policy": {
            "depth": depth,
            "node_budget": node_budget,
            "byte_budget": byte_budget,
            "include_bodies": include_bodies,
            "requested_seed_ids": list(requested_seeds),
        },
        "workspace": source["workspace"],
        "source_generation_sha": source["source_generation_sha"],
        "binder_roots": source["ordered_reads"],
        "clause_seeds": source["seed_ids"],
        "seed_sources": source["seed_sources"],
        "shared_graph_closure": source["graph"],
        "implementation_surface": source["implementation_surface"],
        "ledger_joins": source["ledger_joins"],
        "baseline": source["baseline"],
        "human_gates": source["gates"],
        "evidence_refs": source["evidence_refs"],
        "trunk_ref_joins": source["trunk_ref_joins"],
        "conflicts": source["graph"].get("blockers", []),
        "role_policies": {
            role: _privileges(role, task, track, topic, control)
            for role in PRIVILEGES
        },
    }
    manifest["compiler_derivation"] = {
        "schema": "ndf-context-compiler-derivation/v1",
        "compiler_id": COMPILER_ID,
        "compiler_sha": file_sha(Path(__file__)),
        "policy_sha": canonical_json_sha(manifest["compiler_policy"]),
        "input_sha": canonical_json_sha(
            {
                "workspace": manifest["workspace"],
                "topic": topic,
                "task": task,
                "track": track,
                "business_goal": manifest["business_goal"],
                "control": control,
                "requested_seed_ids": list(requested_seeds),
                "binder_roots": manifest["binder_roots"],
                "evidence_refs": manifest["evidence_refs"],
            }
        ),
        "derived_sha": _manifest_derivation_digest(manifest),
    }
    manifest["manifest_sha"] = canonical_json_sha(manifest)
    return manifest


def verify_manifest_recorded(
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    expected = canonical_json_sha(
        {key: value for key, value in manifest.items() if key != "manifest_sha"}
    )
    if manifest.get("manifest_sha") != expected:
        errors.append(
            {
                "kind": "manifest_sha_mismatch",
                "expected": expected,
                "actual": manifest.get("manifest_sha"),
            }
        )
    derivation = manifest.get("compiler_derivation")
    if not isinstance(derivation, Mapping):
        errors.append({"kind": "manifest_derivation_missing"})
    else:
        if derivation.get("schema") != "ndf-context-compiler-derivation/v1":
            errors.append({"kind": "manifest_derivation_schema_invalid"})
        if derivation.get("compiler_id") != COMPILER_ID:
            errors.append({"kind": "manifest_compiler_id_mismatch"})
        if derivation.get("policy_sha") != canonical_json_sha(
            manifest.get("compiler_policy", {})
        ):
            errors.append({"kind": "manifest_policy_derivation_mismatch"})
        expected_input = canonical_json_sha(
            {
                "workspace": manifest.get("workspace"),
                "topic": manifest.get("topic"),
                "task": manifest.get("task"),
                "track": manifest.get("track"),
                "business_goal": manifest.get("business_goal"),
                "control": manifest.get("control"),
                "requested_seed_ids": manifest.get("compiler_policy", {}).get(
                    "requested_seed_ids", []
                ),
                "binder_roots": manifest.get("binder_roots"),
                "evidence_refs": manifest.get("evidence_refs"),
            }
        )
        if derivation.get("input_sha") != expected_input:
            errors.append({"kind": "manifest_input_derivation_mismatch"})
        if derivation.get("derived_sha") != _manifest_derivation_digest(manifest):
            errors.append({"kind": "manifest_output_derivation_mismatch"})
    expected_role_policies = {
        role: _privileges(
            role,
            str(manifest.get("task") or ""),
            str(manifest.get("track") or ""),
            manifest.get("topic"),
            manifest.get("control"),
        )
        for role in PRIVILEGES
    }
    if manifest.get("role_policies") != expected_role_policies:
        errors.append({"kind": "manifest_role_policy_mismatch"})
    return {
        "schema": "ndf-task-manifest-recorded-verification/v1",
        "valid": not errors,
        "manifest_sha": manifest.get("manifest_sha"),
        "errors": errors,
    }


def verify_manifest_current(
    manifest: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    recorded = verify_manifest_recorded(manifest)
    errors: list[dict[str, Any]] = list(recorded["errors"])
    try:
        repo = (root or Path(manifest["workspace"]["repo_root"])).resolve()
    except (KeyError, TypeError, ValueError):
        errors.append({"kind": "manifest_workspace_invalid"})
        return {
            "schema": "ndf-task-manifest-current-verification/v1",
            "valid": False,
            "manifest_sha": manifest.get("manifest_sha"),
            "errors": errors,
        }
    current_head = _git(repo, "rev-parse", "HEAD")
    if manifest.get("workspace", {}).get("repo_head") != current_head:
        errors.append(
            {
                "kind": "repo_head_drift",
                "expected": manifest.get("workspace", {}).get("repo_head"),
                "actual": current_head,
            }
        )
    for record in manifest.get("binder_roots", []):
        path = repo / record["path"]
        if not path.is_file():
            errors.append({"kind": "missing_file", "path": record["path"]})
        elif file_sha(path) != record.get("sha256"):
            errors.append({"kind": "file_drift", "path": record["path"]})
    meta_only = (
        manifest.get("track") == "process"
        or manifest.get("task") in PROCESS_TASKS
    )
    graph = _load_graph(repo, meta_only)
    current_clause_bindings: list[dict[str, Any]] = []
    for node in manifest.get("shared_graph_closure", {}).get("nodes", []):
        clause = graph.get(node.get("id"))
        if clause is None:
            errors.append({"kind": "clause_missing", "id": node.get("id")})
            continue
        actual = canonical_json_sha(_clause_text(clause, repo))
        current_clause_bindings.append({"id": node.get("id"), "clause_sha": actual})
        if actual != node.get("clause_sha"):
            errors.append({"kind": "clause_drift", "id": node.get("id")})
    for record in manifest.get("evidence_refs", []):
        path = repo / str(record.get("path") or "")
        if not path.is_file() or file_sha(path) != record.get("sha256"):
            errors.append({"kind": "evidence_drift", "path": record.get("path")})
    control = manifest.get("control")
    if isinstance(control, Mapping) and control.get("proposal_sha"):
        proposal_path = repo / str(control.get("proposal_path") or "")
        if (
            not proposal_path.is_file()
            or file_sha(proposal_path) != control.get("proposal_sha")
        ):
            errors.append(
                {
                    "kind": "proposal_drift",
                    "path": control.get("proposal_path"),
                }
            )
    expected_generation = canonical_json_sha(
        {
            "repo_head": current_head,
            "files": [
                {"path": item["path"], "sha256": item["sha256"]}
                for item in manifest.get("binder_roots", [])
            ],
            "clauses": current_clause_bindings,
        }
    )
    if manifest.get("source_generation_sha") != expected_generation:
        errors.append(
            {
                "kind": "source_generation_drift",
                "expected": expected_generation,
                "actual": manifest.get("source_generation_sha"),
            }
        )
    current_gates = _gate_info(repo, manifest.get("topic"))
    if manifest.get("human_gates") != current_gates:
        errors.append({"kind": "gate_drift"})
    for join in manifest.get("trunk_ref_joins", []):
        reference = join.get("trunk_ref")
        if reference and not _git(repo, "rev-parse", f"{reference}^{{commit}}"):
            errors.append(
                {
                    "kind": "trunk_ref_unresolvable",
                    "id": join.get("id"),
                    "trunk_ref": reference,
                }
            )
    policy = manifest.get("compiler_policy", {})
    try:
        rederived = create_manifest(
            root=repo,
            topic=manifest.get("topic"),
            task=str(manifest.get("task") or ""),
            track=str(manifest.get("track") or ""),
            business_goal=str(manifest.get("business_goal") or ""),
            control_binding=(
                manifest.get("control")
                if isinstance(manifest.get("control"), Mapping)
                else None
            ),
            seed_ids=policy.get("requested_seed_ids", []),
            depth=int(policy.get("depth", 2)),
            node_budget=int(policy.get("node_budget", 80)),
            byte_budget=int(policy.get("byte_budget", 256_000)),
            include_bodies=bool(policy.get("include_bodies", True)),
        )
        drifted = [
            field
            for field in MANIFEST_DERIVED_FIELDS
            if manifest.get(field) != rederived.get(field)
        ]
        if drifted:
            errors.append(
                {
                    "kind": "manifest_compiler_derivation_mismatch",
                    "fields": drifted,
                }
            )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(
            {
                "kind": "manifest_compiler_rederive_failed",
                "message": str(exc),
            }
        )
    return {
        "schema": "ndf-task-manifest-current-verification/v1",
        "valid": not errors,
        "manifest_sha": manifest.get("manifest_sha"),
        "errors": errors,
    }


def verify_manifest(
    manifest: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Compatibility alias for live dispatch/readiness verification."""
    return verify_manifest_current(manifest, root=root)


def role_plan(
    manifest: Mapping[str, Any],
    *,
    role: str,
) -> dict[str, Any]:
    """Derive one role-specific plan without rebuilding shared task truth."""
    if role not in PRIVILEGES:
        raise ValueError(f"unknown role: {role}")
    if not _role_task_compatible(
        role,
        str(manifest.get("task") or ""),
        str(manifest.get("track") or ""),
    ):
        raise ValueError(
            "incompatible role/task/track: "
            f"{role}/{manifest.get('task')}/{manifest.get('track')}"
        )
    manifest_check = verify_manifest(manifest)
    if not manifest_check["valid"]:
        raise ValueError(f"invalid task manifest: {manifest_check['errors']}")
    task = str(manifest["task"])
    track = str(manifest["track"])
    topic = manifest.get("topic")
    plan: dict[str, Any] = {
        "schema": f"ndf-context-plan/{role}/v1",
        "manifest_sha": manifest["manifest_sha"],
        "workspace": manifest["workspace"],
        "role": role,
        "task": task,
        "track": track,
        "topic": topic,
        "control": manifest.get("control"),
        "source_generation_sha": manifest["source_generation_sha"],
        "ordered_reads": manifest["binder_roots"],
        "seed_ids": manifest["clause_seeds"],
        "seed_sources": manifest["seed_sources"],
        "graph": manifest["shared_graph_closure"],
        "implementation_surface": manifest["implementation_surface"],
        "ledger_joins": manifest.get("ledger_joins", []),
        "baseline": manifest["baseline"],
        "gates": manifest["human_gates"],
        "evidence_refs": manifest["evidence_refs"],
        "trunk_ref_joins": manifest.get("trunk_ref_joins", []),
        "privileges": json.loads(
            json.dumps(
                manifest.get("role_policies", {}).get(role)
                or _privileges(role, task, track, topic, manifest.get("control"))
            )
        ),
        "human_phrase": None,
    }
    approved = {
        item["gate"]: item
        for item in plan["gates"].get("receipts", [])
        if item.get("status", "").lower() in {"approved", "valid"}
    }
    if task in {"poc_measurement", "implement", "poc_implementation", "poc_prepare_baseline"} and "implementation_approval" not in approved:
        plan["human_phrase"] = "可以开始实现"
    plan["plan_sha"] = canonical_json_sha(plan)
    return plan


def _sanitize_perf(text: str) -> str:
    """Remove PERF Numbers sections while retaining binding and Measure."""
    lines = text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        heading = re.match(r"^##+\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1).strip().lower()
            skipping = title == "numbers" or title.startswith("golden") or title.startswith("results")
            if skipping:
                continue
        if not skipping:
            output.append(line)
    return "\n".join(output).rstrip() + "\n"


def expand_plan(plan: Mapping[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    repo = (root or Path(plan["workspace"]["repo_root"])).resolve()
    measurement = plan.get("task") == "poc_measurement"
    files: list[dict[str, Any]] = []
    for record in plan.get("ordered_reads", []):
        path = repo / record["path"]
        content = _read(path)
        if path.name == "PERF_BASELINE.md" and not measurement:
            content = _sanitize_perf(content)
        files.append(
            {
                "path": record["path"],
                "source_sha256": record["sha256"],
                "content_sha": canonical_json_sha(content),
                "content": content,
            }
        )
    graph = _load_graph(
        repo,
        plan.get("role") == "project-control"
        or plan.get("task") in PROCESS_TASKS
        or plan.get("track") == "process",
    )
    clauses = []
    for node in plan.get("graph", {}).get("nodes", []):
        clause = graph.get(node["id"])
        if clause is None:
            continue
        content = _clause_text(clause, repo)
        clauses.append(
            {
                "id": node["id"],
                "path": node["file"],
                "line": node["line"],
                "clause_sha": canonical_json_sha(content),
                "content": content,
            }
        )
    bundle = {
        "schema": "ndf-context-bundle/v1",
        "manifest_sha": plan.get("manifest_sha"),
        "plan_sha": plan["plan_sha"],
        "repo_head": plan["workspace"]["repo_head"],
        "role": plan["role"],
        "task": plan["task"],
        "topic": plan.get("topic"),
        "files": files,
        "clauses": clauses,
        "joins": {
            "baseline": plan.get("baseline"),
            "gates": plan.get("gates"),
            "evidence_refs": plan.get("evidence_refs"),
            "trunk_ref_joins": plan.get("trunk_ref_joins"),
            "implementation_surface": plan.get("implementation_surface"),
            "ledger_joins": plan.get("ledger_joins"),
            "privileges": plan.get("privileges"),
        },
    }
    bundle["bundle_sha"] = canonical_json_sha(bundle)
    return bundle


def render_markdown(bundle: Mapping[str, Any]) -> str:
    lines = [
        "# NDF Context Bundle",
        "",
        f"- plan_sha: `{bundle['plan_sha']}`",
        f"- repo_head: `{bundle.get('repo_head')}`",
        f"- role/task: `{bundle.get('role')}` / `{bundle.get('task')}`",
        f"- topic: `{bundle.get('topic')}`",
        "",
        "## Files",
        "",
    ]
    for item in bundle.get("files", []):
        lines.extend(
            [
                f"### `{item['path']}`",
                "",
                f"> source_sha256: `{item['source_sha256']}`",
                "",
                item["content"].rstrip(),
                "",
            ]
        )
    lines.extend(["## Clauses", ""])
    for item in bundle.get("clauses", []):
        lines.extend(
            [
                f"### `{item['id']}` — `{item['path']}:{item['line']}`",
                "",
                f"> clause_sha: `{item['clause_sha']}`",
                "",
                item["content"].rstrip(),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def compile_prompt_surface(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Record the visible compiled surface and its exact source lineage."""
    visible_prompt = render_markdown(bundle)
    surface = {
        "schema": "ndf-visible-prompt-surface/v1",
        "manifest_sha": bundle.get("manifest_sha"),
        "plan_sha": bundle.get("plan_sha"),
        "bundle_sha": bundle.get("bundle_sha"),
        "compiler": {
            "path": "spec/meta/tools/ndf_context.py",
            "sha256": file_sha(Path(__file__)),
        },
        "source_refs": {
            "files": [
                {
                    "path": item.get("path"),
                    "source_sha256": item.get("source_sha256"),
                    "content_sha": item.get("content_sha"),
                }
                for item in bundle.get("files", [])
            ],
            "clauses": [
                {
                    "id": item.get("id"),
                    "path": item.get("path"),
                    "clause_sha": item.get("clause_sha"),
                }
                for item in bundle.get("clauses", [])
            ],
        },
        "visible_prompt_sha": canonical_json_sha(visible_prompt),
        "visible_prompt": visible_prompt,
    }
    surface["surface_sha"] = canonical_json_sha(surface)
    return surface


def _overlap(path: str, forbidden: str) -> bool:
    if forbidden == "*":
        return True
    left, right = path.rstrip("/") + "/", forbidden.rstrip("/") + "/"
    return left.startswith(right) or right.startswith(left)


def verify_plan(
    plan: Mapping[str, Any],
    *,
    root: Path | None = None,
    bundle: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
    require_manifest: bool = False,
) -> dict[str, Any]:
    repo = (root or Path(plan["workspace"]["repo_root"])).resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    unhashed = {key: value for key, value in plan.items() if key != "plan_sha"}
    expected_plan_sha = canonical_json_sha(unhashed)
    if plan.get("plan_sha") != expected_plan_sha:
        errors.append({"kind": "plan_sha_mismatch", "expected": expected_plan_sha, "actual": plan.get("plan_sha")})
    role_schema = str(plan.get("schema") or "")
    is_role_plan = role_schema.startswith("ndf-context-plan/") and role_schema != "ndf-context-plan/v1"
    if manifest is not None:
        manifest_check = verify_manifest(manifest, root=repo)
        errors.extend(manifest_check["errors"])
        if plan.get("manifest_sha") != manifest.get("manifest_sha"):
            errors.append(
                {
                    "kind": "plan_manifest_sha_mismatch",
                    "expected": manifest.get("manifest_sha"),
                    "actual": plan.get("manifest_sha"),
                }
            )
        role = str(plan.get("role") or "")
        expected_schema = f"ndf-context-plan/{role}/v1"
        if require_manifest and (
            not is_role_plan
            or role not in PRIVILEGES
            or role_schema != expected_schema
        ):
            errors.append({"kind": "role_plan_schema_required"})
        if is_role_plan and role in PRIVILEGES:
            manifest_fields = {
                "manifest_sha": manifest.get("manifest_sha"),
                "workspace": manifest.get("workspace"),
                "task": manifest.get("task"),
                "track": manifest.get("track"),
                "topic": manifest.get("topic"),
                "control": manifest.get("control"),
                "source_generation_sha": manifest.get("source_generation_sha"),
                "ordered_reads": manifest.get("binder_roots"),
                "seed_ids": manifest.get("clause_seeds"),
                "seed_sources": manifest.get("seed_sources"),
                "graph": manifest.get("shared_graph_closure"),
                "implementation_surface": manifest.get("implementation_surface"),
                "ledger_joins": manifest.get("ledger_joins", []),
                "baseline": manifest.get("baseline"),
                "gates": manifest.get("human_gates"),
                "evidence_refs": manifest.get("evidence_refs"),
                "trunk_ref_joins": manifest.get("trunk_ref_joins", []),
                "privileges": manifest.get("role_policies", {}).get(role)
                or _privileges(
                    role,
                    str(manifest.get("task") or ""),
                    str(manifest.get("track") or ""),
                    manifest.get("topic"),
                    manifest.get("control"),
                ),
            }
            drifted = sorted(
                field
                for field, expected in manifest_fields.items()
                if plan.get(field) != expected
            )
            if drifted:
                errors.append(
                    {
                        "kind": "role_plan_derivation_mismatch",
                        "fields": drifted,
                    }
                )
    elif require_manifest:
        errors.append({"kind": "manifest_required_for_role_plan"})
    current_head = _git(repo, "rev-parse", "HEAD")
    if plan.get("workspace", {}).get("repo_head") != current_head:
        errors.append(
            {
                "kind": "repo_head_drift",
                "expected": plan.get("workspace", {}).get("repo_head"),
                "actual": current_head,
            }
        )
    for record in plan.get("ordered_reads", []):
        path = repo / record["path"]
        if not path.is_file():
            errors.append({"kind": "missing_file", "path": record["path"]})
            continue
        actual = file_sha(path)
        if actual == record.get("sha256"):
            continue
        recorded_slices = [
            (item.get("slice_id"), item.get("content_sha"))
            for item in (record.get("slices") or [])
            if isinstance(item, Mapping)
        ]
        if recorded_slices:
            current_slices = [
                (item.get("slice_id"), item.get("content_sha"))
                for item in ndf_gate_slices.slice_content_fingerprints(path, root=repo)
            ]
            finding = {
                "kind": "file_drift",
                "path": record["path"],
                "expected": record.get("sha256"),
                "actual": actual,
            }
            if recorded_slices == current_slices:
                finding["kind"] = "mutable_section_drift"
                warnings.append(finding)
            else:
                errors.append(finding)
        else:
            errors.append(
                {
                    "kind": "file_drift",
                    "path": record["path"],
                    "expected": record.get("sha256"),
                    "actual": actual,
                }
            )
    privileges = plan.get("privileges", {})
    for allowed in privileges.get("allowed_write_roots", []):
        for forbidden in privileges.get("forbidden_write_paths", []):
            if _overlap(allowed, forbidden):
                errors.append({"kind": "forbidden_path", "path": allowed, "forbidden": forbidden})
    if plan.get("baseline", {}).get("baseline_status") == "stale":
        finding = {
            "kind": "baseline_stale",
            "path": plan.get("baseline", {}).get("path"),
        }
        if plan.get("task") in CONTROL_REPAIR_TASKS or plan.get("task") in MEASUREMENT_REPAIR_TASKS:
            warnings.append(finding)
        else:
            errors.append(finding)
    for receipt in plan.get("gates", {}).get("receipts", []):
        if receipt.get("status", "").lower() not in {"approved", "valid"}:
            continue
        recorded = receipt.get("approved_content_sha")
        expected = receipt.get("expected_content_sha")
        semantic_complete = bool(
            receipt.get("phrase") == receipt.get("expected_phrase")
            and receipt.get("approved_by")
            and receipt.get("approved_at")
            and receipt.get("source_ref")
        )
        mode_aligned = ndf_gate_slices.receipt_mode_aligned(receipt)
        if (
            not semantic_complete
            or not expected
            or not recorded
            or len(recorded) != 64
            or recorded != expected
            or not mode_aligned
        ):
            finding = {
                "kind": "gate_sha_mismatch",
                "gate": receipt.get("gate"),
                "expected": expected,
                "actual": recorded,
            }
            # Canvas is read-only projection: gate drift must not paint the whole
            # topic red. ACP write packs still use role=claude-code +
            # task=poc_implementation and fail closed on mismatch.
            if (
                plan.get("task") in CONTROL_REPAIR_TASKS
                or plan.get("role") == "canvas"
            ):
                warnings.append(finding)
            else:
                errors.append(finding)
    required_gate = (
        plan.get("task")
        in {"poc_measurement", "implement", "poc_implementation", "poc_prepare_baseline"}
        and plan.get("role") != "canvas"
    )
    if required_gate:
        implementation = [
            item
            for item in plan.get("gates", {}).get("receipts", [])
            if item.get("gate") == "implementation_approval"
            and item.get("status", "").lower() in {"approved", "valid"}
            and item.get("approved_content_sha") == item.get("expected_content_sha")
            and len(item.get("approved_content_sha") or "") == 64
            and ndf_gate_slices.receipt_mode_aligned(item)
        ]
        if not implementation:
            errors.append({"kind": "required_gate_not_valid", "gate": "implementation_approval"})
    graph = _load_graph(
        repo,
        plan.get("role") == "project-control"
        or plan.get("task") in PROCESS_TASKS
        or plan.get("track") == "process",
    )
    for node in plan.get("graph", {}).get("nodes", []):
        clause = graph.get(node["id"])
        if clause is None:
            errors.append({"kind": "clause_missing", "id": node["id"]})
            continue
        actual = canonical_json_sha(_clause_text(clause, repo))
        if actual != node.get("clause_sha"):
            errors.append({"kind": "clause_drift", "id": node["id"], "expected": node.get("clause_sha"), "actual": actual})
    for join in plan.get("trunk_ref_joins", []):
        reference = join.get("trunk_ref")
        resolved = _git(repo, "rev-parse", f"{reference}^{{commit}}") if reference else None
        if not resolved:
            finding = {
                "kind": "trunk_ref_unresolvable",
                "id": join.get("id"),
                "trunk_ref": reference,
            }
            if plan.get("task") in SEMANTIC_TASKS:
                errors.append(finding)
            else:
                warnings.append(finding)
    for join in plan.get("ledger_joins", []):
        for commit in join.get("commits", []):
            if not _git(repo, "rev-parse", f"{commit}^{{commit}}"):
                warnings.append(
                    {
                        "kind": "ledger_commit_unresolvable",
                        "source": join.get("source"),
                        "line": join.get("line"),
                        "commit": commit,
                    }
                )
    if plan.get("graph", {}).get("truncated"):
        truncated = {"kind": "graph_truncated", "reasons": plan["graph"]["truncated"]}
        if plan.get("privileges", {}).get("allowed_write_roots") and plan.get("role") not in {"canvas", "human"}:
            errors.append(truncated)
        else:
            warnings.append(truncated)
    if bundle is not None:
        if bundle.get("plan_sha") != plan.get("plan_sha"):
            errors.append({"kind": "bundle_plan_sha_mismatch"})
        expected_bundle_sha = canonical_json_sha(
            {key: value for key, value in bundle.items() if key != "bundle_sha"}
        )
        if bundle.get("bundle_sha") != expected_bundle_sha:
            errors.append(
                {
                    "kind": "bundle_sha_mismatch",
                    "expected": expected_bundle_sha,
                    "actual": bundle.get("bundle_sha"),
                }
            )
        for item in bundle.get("files", []):
            source = next((record for record in plan.get("ordered_reads", []) if record["path"] == item.get("path")), None)
            if source is None or item.get("source_sha256") != source.get("sha256"):
                errors.append({"kind": "bundle_file_unbound", "path": item.get("path")})
            if item.get("content_sha") != canonical_json_sha(item.get("content", "")):
                errors.append({"kind": "bundle_content_sha_mismatch", "path": item.get("path")})
        planned_clauses = {
            item["id"]: item.get("clause_sha")
            for item in plan.get("graph", {}).get("nodes", [])
        }
        for item in bundle.get("clauses", []):
            actual = canonical_json_sha(item.get("content", ""))
            if item.get("clause_sha") != actual or planned_clauses.get(item.get("id")) != actual:
                errors.append({"kind": "bundle_clause_sha_mismatch", "id": item.get("id")})
    return {
        "schema": "ndf-context-verification/v1",
        "valid": not errors,
        "plan_sha": plan.get("plan_sha"),
        "manifest_sha": plan.get("manifest_sha"),
        "repo_head": current_head,
        "errors": errors,
        "warnings": warnings,
    }


def verify_plan_recorded(
    plan: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a recorded role plan without consulting the current checkout."""
    errors: list[dict[str, Any]] = list(
        verify_manifest_recorded(manifest)["errors"]
    )
    expected_sha = canonical_json_sha(
        {key: value for key, value in plan.items() if key != "plan_sha"}
    )
    if plan.get("plan_sha") != expected_sha:
        errors.append({"kind": "plan_sha_mismatch"})
    role = str(plan.get("role") or "")
    task = str(plan.get("task") or "")
    track = str(plan.get("track") or "")
    if (
        role not in PRIVILEGES
        or plan.get("schema") != f"ndf-context-plan/{role}/v1"
    ):
        errors.append({"kind": "role_plan_schema_required"})
    elif not _role_task_compatible(role, task, track):
        errors.append({"kind": "role_task_track_incompatible"})
    expected_fields = {
        "manifest_sha": manifest.get("manifest_sha"),
        "workspace": manifest.get("workspace"),
        "task": manifest.get("task"),
        "track": manifest.get("track"),
        "topic": manifest.get("topic"),
        "source_generation_sha": manifest.get("source_generation_sha"),
        "ordered_reads": manifest.get("binder_roots"),
        "seed_ids": manifest.get("clause_seeds"),
        "seed_sources": manifest.get("seed_sources"),
        "graph": manifest.get("shared_graph_closure"),
        "implementation_surface": manifest.get("implementation_surface"),
        "ledger_joins": manifest.get("ledger_joins", []),
        "baseline": manifest.get("baseline"),
        "gates": manifest.get("human_gates"),
        "evidence_refs": manifest.get("evidence_refs"),
        "trunk_ref_joins": manifest.get("trunk_ref_joins", []),
        "privileges": manifest.get("role_policies", {}).get(role),
    }
    drifted = sorted(
        field
        for field, expected in expected_fields.items()
        if plan.get(field) != expected
    )
    if drifted:
        errors.append(
            {"kind": "role_plan_derivation_mismatch", "fields": drifted}
        )
    return {
        "schema": "ndf-context-recorded-verification/v1",
        "valid": not errors,
        "plan_sha": plan.get("plan_sha"),
        "manifest_sha": plan.get("manifest_sha"),
        "errors": errors,
        "warnings": [],
    }


def _load_json(path: str | None, *, root: Path = ROOT) -> dict[str, Any]:
    if not path or path == "-":
        return json.load(sys.stdin)
    if re.fullmatch(r"[0-9a-f]{64}", path):
        import ndf_replay

        obj = ndf_replay.ReplayStore(root).get_object(path, "blob")["data"]
        value = obj.get("value")
        if not isinstance(value, dict):
            raise ValueError(f"Replay object is not a JSON object: {path}")
        return value
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return json.loads(candidate.read_text(encoding="utf-8"))


def _record_replay(
    root: Path,
    episode_id: str | None,
    *,
    kind: str,
    actor: str,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not episode_id:
        return None
    import ndf_replay

    store = ndf_replay.ReplayStore(root)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    blob_sha = store.put_blob(dict(payload))
    event = store.append_event(
        episode_id,
        kind=kind,
        actor=actor,
        payload_sha=blob_sha,
        topic=payload.get("topic"),
        task=str(payload.get("task") or kind),
        track=str(payload.get("track") or "process"),
        repo_head=(payload.get("workspace") or {}).get("repo_head")
        or payload.get("repo_head"),
        manifest_sha=payload.get("manifest_sha"),
        context_plan_sha=payload.get("plan_sha"),
    )
    return {"episode_id": episode_id, "blob_sha": blob_sha, "event_sha": event["event_sha"]}


def _emit(value: Any, report: str | None, root: Path) -> None:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if report:
        path = safe_tmp_report_path(report, root=root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="" if text.endswith("\n") else "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    manifest_parser = sub.add_parser("manifest-create")
    manifest_parser.add_argument("--topic")
    manifest_parser.add_argument("--task", required=True)
    manifest_parser.add_argument("--track", required=True)
    manifest_parser.add_argument("--business-goal", default="")
    manifest_parser.add_argument("--seed-ids", nargs="*", default=[])
    manifest_parser.add_argument("--depth", type=int, default=2)
    manifest_parser.add_argument("--node-budget", type=int, default=80)
    manifest_parser.add_argument("--byte-budget", type=int, default=256_000)
    manifest_parser.add_argument("--episode")
    manifest_parser.add_argument("--report")
    manifest_parser.add_argument("--json", action="store_true")
    role_parser = sub.add_parser("role-plan")
    role_parser.add_argument("--manifest", required=True)
    role_parser.add_argument("--role", required=True, choices=tuple(PRIVILEGES))
    role_parser.add_argument("--episode")
    role_parser.add_argument("--report")
    role_parser.add_argument("--json", action="store_true")
    plan_parser = sub.add_parser("context-plan")
    plan_parser.add_argument("--topic")
    plan_parser.add_argument("--role", required=True, choices=tuple(PRIVILEGES))
    plan_parser.add_argument("--task", required=True)
    plan_parser.add_argument("--track", required=True)
    plan_parser.add_argument("--seed-ids", nargs="*", default=[])
    plan_parser.add_argument("--depth", type=int, default=2)
    plan_parser.add_argument("--node-budget", type=int, default=80)
    plan_parser.add_argument("--byte-budget", type=int, default=256_000)
    plan_parser.add_argument("--episode")
    plan_parser.add_argument("--report")
    plan_parser.add_argument("--json", action="store_true")
    expand_parser = sub.add_parser("context-expand")
    expand_parser.add_argument("--plan", required=True)
    expand_parser.add_argument("--format", choices=("json", "markdown"), default="json")
    expand_parser.add_argument("--episode")
    expand_parser.add_argument("--report")
    expand_parser.add_argument("--json", action="store_true")
    verify_parser = sub.add_parser("context-verify")
    verify_parser.add_argument("--plan", required=True)
    verify_parser.add_argument("--manifest")
    verify_parser.add_argument("--bundle")
    verify_parser.add_argument("--report")
    verify_parser.add_argument("--strict", action="store_true")
    verify_parser.add_argument("--episode")
    verify_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "manifest-create":
            payload = create_manifest(
                root=root,
                topic=args.topic,
                task=args.task,
                track=args.track,
                business_goal=args.business_goal,
                seed_ids=args.seed_ids,
                depth=args.depth,
                node_budget=args.node_budget,
                byte_budget=args.byte_budget,
            )
            _record_replay(
                root,
                args.episode,
                kind="manifest.created",
                actor="context-compiler",
                payload=payload,
            )
            _emit(payload, args.report, root)
            return 0
        if args.command == "role-plan":
            payload = role_plan(
                _load_json(args.manifest, root=root),
                role=args.role,
            )
            _record_replay(
                root,
                args.episode,
                kind="context.compiled",
                actor="context-compiler",
                payload=payload,
            )
            _emit(payload, args.report, root)
            return 0
        if args.command == "context-plan":
            payload = compile_plan(
                root=root,
                topic=args.topic,
                role=args.role,
                task=args.task,
                track=args.track,
                seed_ids=args.seed_ids,
                depth=args.depth,
                node_budget=args.node_budget,
                byte_budget=args.byte_budget,
            )
            _record_replay(
                root,
                args.episode,
                kind="context.compiled",
                actor="context-compiler",
                payload=payload,
            )
            _emit(payload, args.report, root)
            return 0
        plan = _load_json(args.plan, root=root)
        if args.command == "context-expand":
            verification = verify_plan(plan, root=root)
            if not verification["valid"]:
                _emit(verification, args.report, root)
                return 1
            bundle = expand_plan(plan, root=root)
            if args.episode:
                import ndf_replay

                store = ndf_replay.ReplayStore(root)
                bundle_object_sha = store.put_blob(bundle)
                surface = {
                    **compile_prompt_surface(bundle),
                    "topic": plan.get("topic"),
                    "task": plan.get("task"),
                    "track": plan.get("track"),
                    "workspace": plan.get("workspace"),
                    "bundle_object_sha": bundle_object_sha,
                }
                _record_replay(
                    root,
                    args.episode,
                    kind="context.expanded",
                    actor="context-compiler",
                    payload=surface,
                )
            _emit(render_markdown(bundle) if args.format == "markdown" else bundle, args.report, root)
            return 0
        bundle = _load_json(args.bundle, root=root) if args.bundle else None
        manifest = _load_json(args.manifest, root=root) if args.manifest else None
        verification = verify_plan(
            plan,
            root=root,
            bundle=bundle,
            manifest=manifest,
            require_manifest=args.strict,
        )
        _record_replay(
            root,
            args.episode,
            kind="context.verified",
            actor="context-compiler",
            payload={
                **verification,
                "topic": plan.get("topic"),
                "task": plan.get("task"),
                "track": plan.get("track"),
                "workspace": plan.get("workspace"),
            },
        )
        _emit(verification, args.report, root)
        return 0 if verification["valid"] and not (args.strict and verification["warnings"]) else 1
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        payload = {"schema": "ndf-context-error/v1", "error": str(exc)}
        _emit(payload, getattr(args, "report", None), root)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
