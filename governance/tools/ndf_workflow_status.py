#!/usr/bin/env python3
"""NDF workflow status: packs, health, and text-first dispatch (META-009..014).

Commander / canvas snapshot / ActionSpec are retired (ADR-META-004).
This tool never approves gates, mutates NDF, starts agents, or writes
.openclaw/state.json. Daily path: poc-dispatch, control-pack, topic-health.
"""

from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec"
META = SPEC / "meta"
POC = ROOT / "poc"
TOOLS = META / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ndf_close  # noqa: E402
import ndf_context  # noqa: E402
import ndf_gate_slices  # noqa: E402
# ndf_replay kept as library-only (CLI exits deprecated); hot path MUST NOT require it.
import ndf_replay  # noqa: E402


def roles_dispatch_blockers() -> list[str]:
    """Return roles_unbound blockers when ndf.workflow.yaml roles are incomplete."""
    try:
        import ndf_role_binding as role_binding

        ok, blockers = role_binding.check_roles_for_dispatch(ROOT)
        return [] if ok else list(blockers)
    except Exception:
        return ["roles_unbound"]


class _RetiredActionsModule:
    """ActionSpec / Commander catalog retired (ADR-META-004).

    Empty-registry stub so legacy call sites fail soft without a hard import of
    deleted ``ndf_actions.py``. Daily path MUST NOT depend on ActionSpec.
    """

    @staticmethod
    def registry_by_id() -> dict[str, Any]:
        return {}

    @staticmethod
    def registry_actions() -> list[dict[str, Any]]:
        return []

    @staticmethod
    def load_registry() -> dict[str, Any]:
        return {"schema": "ndf-action-registry-retired/v1", "actions": []}

    @staticmethod
    def action_prompt_relpath(catalog_id: str) -> str:
        return f"tmp/ndf-action-prompt-{catalog_id}.md"

    @staticmethod
    def canvas_launcher_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
        return dict(payload)

    @staticmethod
    def evaluate_enabled_actions(_payload: Mapping[str, Any]) -> list[Any]:
        return []

    @staticmethod
    def evaluate_action(
        _catalog: Mapping[str, Any],
        _current: Mapping[str, Any],
        _ctx: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {"enabled": False, "reason": "action_spec_retired"}

    @staticmethod
    def composer_prompt(*_a: Any, **_k: Any) -> str:
        return "# ActionSpec retired (ADR-META-004)\n"

    @staticmethod
    def persist_action_prompt(action_id: str, prompt: str) -> Path:
        path = ROOT / "tmp" / f"ndf-action-prompt-{action_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        return path

    @staticmethod
    def open_file_path(_action_id: str, _current: Mapping[str, Any]) -> str | None:
        return None

    @staticmethod
    def action_episode_policy(_catalog: Mapping[str, Any]) -> str:
        return "none"

    @staticmethod
    def action_provider(_catalog: Mapping[str, Any]) -> str:
        return "tool"


ndf_actions = _RetiredActionsModule()  # noqa: N816 — keep legacy attribute name
from ndf_workflow_evidence import (  # noqa: E402
    append_lease,
    bundle_sha as evidence_bundle_sha,
    canonical_json_sha,
    chained_event,
    git_mutation_snapshot,
    read_leases,
    runtime_lease_binding_proof,
    safe_tmp_report_path,
    validate_evidence_bundle,
    validate_event_chain,
    validate_receipt,
    validate_recorded_runtime_lease_binding,
    validate_runtime_lease_binding,
    workspace_truth,
)

ACTION_LOG = ROOT / "tmp" / "ndf-workflow-actions.jsonl"
DISPATCH_PACK_PATH = ROOT / "tmp" / "ndf-dispatch-last-pack.json"
DISPATCH_LAST_PATH = ROOT / "tmp" / "ndf-dispatch-last.json"
HEALTH_DIR = ROOT / "tmp" / "ndf-workflow-health"
PIPELINE_EPISODE_DIR = ROOT / "tmp" / "ndf-control-pipelines"
CONTROL_DISPATCH_LOG = ROOT / "tmp" / "ndf-control-dispatch.jsonl"
LEASE_LOG = ROOT / "tmp" / "ndf-workflow-leases.jsonl"
CLOSE_EVIDENCE_DIR = ROOT / "tmp" / "ndf-close-evidence"
PROJECTION_EVIDENCE_DIR = ROOT / "tmp" / "ndf-projection-evidence"
SERVE_LOCK_PATH = ROOT / "tmp" / "ndf-commander-serve.lock"
# Outer-terminal --serve keeps a larger reserve so HTTP workers do not starve the host.
HOST_PID_MIN_FREE_SERVE = 512
# action-begin only needs room for one python + a few children (not IDE baseline).
HOST_PID_MIN_FREE_ACTION = 64
# Backward-compatible alias (serve-side reserve).
HOST_PID_MIN_FREE = HOST_PID_MIN_FREE_SERVE
SERVE_MAX_WORKERS = 16
SERVE_MAX_SSE = 2
# Cap long-lived SSE so half-open browsers cannot pin workers forever.
SERVE_SSE_MAX_SECONDS = 900
HOST_PID_EXHAUSTED = "host_pid_exhausted"
HOST_PID_CHROMIUM_SERVE_FORBIDDEN = "chromium_serve_forbidden"
CHROMIUM_CGROUP_MARKER = "app-org.chromium.Chromium-"
# Held open for the lifetime of --serve so flock stays exclusive across processes.
_SERVE_LOCK_FD: int | None = None

GATE_COLUMNS = (
    "gate",
    "phrase",
    "approved_by",
    "approved_at",
    "approved_content_sha",
    "source_ref",
    "status",
)
GATE_ORDER = ("topic_review", "design_review", "implementation_approval")
GATE_PHRASES = {
    "topic_review": "TOPIC已审核",
    "design_review": "DESIGN已审核",
    "implementation_approval": "可以开始实现",
    # Text-first substitute for gate 3 (ADR-META-003); same bundle as implementation_approval.
    "bundle_dispatch": "派发",
}
# Text-first poc-dispatch kernel lives in ndf_poc_dispatch (ADR-META-004).
from ndf_poc_dispatch import (  # noqa: E402
    POC_DISPATCH_INTENTS,
    POC_DISPATCH_SOFT_REASONS,
    _concurrent_write_run_blocker,
    _poc_dispatch_task,
    ensure_inline_isolated_lease,
    poc_dispatch,
    poc_dispatch_hard_blockers,
    validate_poc_completion_minimal,
)

CONTROL_TASK_LABELS = {
    "legacy_gate_audit": "门禁分步审计",
    "gate_sha_audit": "门禁失效SHA审计",
    "gate_receipt_draft": "门禁准备回执",
    "gate_pipeline": "启动门禁流水线",
    "binder_amend": "装订器分步修订",
    "binder_pipeline": "启动装订器流水线",
    "control_proposal": "起草产品提案（兼容别名 → product_proposal）",
    "product_proposal": "起草产品 / 项目提案（仅 spec/open/）",
    "process_proposal": "起草 NDF 流程提案（仅 spec/meta/open/）",
    "poc_prepare_baseline": "准备基线工作区（INTERFACE + 拷贝对照代码）",
    "poc_isolation_repair": "修复 POC 隔离",
    "poc_measurement": "补测 / 写 DELTA",
    "ndf_improvement_proposal": "起草 NDF 改进提案",
    "ndf_improvement_land": "落地 / 审核 process 提案",
}
# Idea plane routing (ADR-META-004): product vs process write roots must not share.
PRODUCT_PROPOSAL_TASKS = frozenset({"product_proposal", "control_proposal"})
PROCESS_PROPOSAL_TASKS = frozenset(
    {"process_proposal", "ndf_improvement_proposal", "ndf_improvement_land"}
)
IDEA_PLANE_ROOTS = {
    "product": ("spec/open/",),
    "process": ("spec/meta/open/",),
}
# BEH-025 binder read/write order for OpenClaw repair buttons.
BINDER_FACET_ORDER = (
    "topic",
    "design",
    "perf_baseline",
    "delta",
    "interface",
    "commits",
)
BINDER_FACET_LABELS = {
    "topic": "TOPIC.md",
    "design": "DESIGN.md",
    "perf_baseline": "PERF_BASELINE / 金标绑定",
    "delta": "DELTA.md",
    "interface": "INTERFACE.md",
    "commits": "COMMITS.md",
}
BINDER_FACET_FILES = {
    "topic": "TOPIC.md",
    "design": "DESIGN.md",
    "perf_baseline": "PERF_BASELINE.md",
    "delta": "DELTA.md",
    "interface": "INTERFACE.md",
    "commits": "COMMITS.md",
}
BINDER_FACET_SECTIONS = {
    "topic": {"topic_contract", "topic_runtime_headers"},
    "design": {"design_contract"},
    "perf_baseline": {"perf_bind"},
    "delta": {"delta_hypothesis"},
    "interface": {"interface_contract"},
    "commits": {"ledger_skeleton"},
}
GATE_BINDER_PREREQUISITES = {
    "topic_review": ("topic",),
    "design_review": ("design",),
    "implementation_approval": ("perf_baseline", "delta", "interface"),
}
POC_DECISIONS = frozenset(
    {
        "implement",
        "continue_exploring",
        "amend",
        "promote",
        "partial",
        "reject",
    }
)
CLOSE_DECISIONS = frozenset({"promote", "partial", "reject"})
NEW_POC_ROUTE = "new_poc"
BRIEFING_MODES = POC_DECISIONS | {NEW_POC_ROUTE}
POC_DECISION_MEANINGS = {
    "implement": (
        "Realize the currently approved DESIGN/INTERFACE as the first POC "
        "round. TOPIC/DESIGN stay frozen."
    ),
    "continue_exploring": (
        "Keep the same TOPIC/DESIGN. Open another DELTA round "
        "(measure/analyze/in-design tweak). Do not amend contract slices."
    ),
    "amend": (
        "Same active_hypothesis only: revise binder or contract slices and "
        "re-run affected gates. Hypothesis fork MUST NOT use amend; draft a "
        "track=poc proposal and open a sibling topic."
    ),
    "promote": "Close the topic by promoting a verified slice to Trunk.",
    "partial": "Close a verified subset; leave the topic exploring.",
    "reject": "Close the topic as a negative result.",
}
ROUND_TOKEN_RE = re.compile(r"\bR(\d+)\b", re.I)
FEATURE_IMPLEMENTED_STATUSES = frozenset(
    {"implemented", "in_progress", "done", "landed"}
)
POC_IMPLEMENTATION_TASKS = frozenset({"poc_implementation", "implement"})
BASELINE_PREP_TASKS = frozenset({"poc_prepare_baseline", "poc_measurement"})
DECISION_BLOCK_LABELS: dict[str, str] = {
    "gates_not_valid": "三闸未全部有效",
    "no_poc_round_yet": "尚无 DESIGN 功能实现轮，请先选择 implement",
    "no_feature_round_yet": "尚无 DESIGN 功能实现轮，请先选择 implement",
    "poc_round_exists": "DESIGN 功能实现轮已开始，请选 continue_exploring",
    "feature_round_exists": "DESIGN 功能实现轮已开始，请选 continue_exploring",
}
MEASUREMENT_FINDING_KINDS = frozenset(
    {
        "unverified_measurement_claim",
        "empty_numbers",
        "numbers_pending",
        # Numbers body did not restate vs/bl-trunk (bind header may already have vs).
        # Owned by Claude Code poc_measurement — MUST NOT route to binder/OpenClaw.
        "vs_unmentioned",
    }
)
PLANE_BUSINESS = "Business"
PLANE_CONTROL = "NDF Control"
PLANE_RUNTIME = "Runtime"
# Bindcheck / closeout provenance — Control plane; MUST NOT default to binder_amend.
CONTROL_BINDCHECK_KINDS = frozenset(
    {
        "missing_trailer",
        "bad_ledger_sha",
        "clause_unbound",
        "orphan_commit",
        "wrong_topic",
        "wrong_proposals",
        "wrong_clauses",
        "stale_ledger",
        "duplicate_ledger",
    }
)
CONTROL_ONLY_REPAIR_TASKS = frozenset(
    {
        "diagnose-topic",
        "dispatch_recover",
        "control_proposal",
        "legacy_gate_audit",
        "gate_sha_audit",
        "gate_receipt_draft",
        "proposal_plane_repair",
        "ndf_improvement_proposal",
    }
)
COMPLETION_BLOCKER_PREFIXES = (
    "missing:",
    "mismatch:",
    "invalid:",
    "stale:",
    "runtime_lease:",
)
COMPLETION_BLOCKER_HUMAN: dict[str, str] = {
    "missing:active_runtime_lease": (
        "ACP 租约未写入 jsonl；实现前先 lease-record（隔离 worktree + run_id）"
    ),
    "missing:changed_sections": (
        "回执缺 changed_sections（改了 COMMITS.md 或 ndf/evidence/* 时必填）"
    ),
    "missing:post_check_receipts": (
        "post_check_receipts 必须是数组（每项含 command、result、verifier）"
    ),
    "mismatch:evidence_bundle_sha": (
        "evidence_bundle_sha 与 evidence_paths 重算不一致"
    ),
    "mismatch:worktree": "worktree 与 active lease 不一致",
    "mismatch:branch": "branch 与 active lease 不一致",
}
# Non-blocking advisories: keep on health.findings, exclude from forced next_actions /
# binder pipeline steps (ok if own R0 table).
ADVISORY_FINDING_KINDS = frozenset(
    {
        "vs_unmentioned",
    }
)
KIND_TO_BINDER_FACET = {
    "missing_topic": "topic",
    "missing_binder": "topic",
    "missing_design": "design",
    "missing_perf_baseline": "perf_baseline",
    "missing_perf_baseline_field": "perf_baseline",
    "missing_card": "perf_baseline",
    "missing_config": "perf_baseline",
    "missing_config_id": "perf_baseline",
    "missing_config_section": "perf_baseline",
    "missing_trunk_sha": "perf_baseline",
    "missing_vs": "perf_baseline",
    "unknown_vs": "perf_baseline",
    "missing_measure_script": "perf_baseline",
    "missing_measure_binary": "perf_baseline",
    "missing_protocol": "perf_baseline",
    "missing_delta": "delta",
    "missing_interface": "interface",
    "missing_ledger": "commits",
    "missing_commits": "commits",
}
CONTROL_TASKS = frozenset(
    {
        "legacy_gate_audit",
        "gate_sha_audit",
        "gate_receipt_draft",
        "binder_amend",
        "control_proposal",  # alias → product_proposal
        "product_proposal",
        "process_proposal",
        "gate_pipeline",
        "binder_pipeline",
    }
)
GATE_PIPELINE_TASKS = frozenset(
    {"gate_pipeline", "legacy_gate_audit", "gate_sha_audit", "gate_receipt_draft"}
)
BINDER_PIPELINE_TASKS = frozenset({"binder_pipeline", "binder_amend"})
PIPELINE_GATE = "gate"
PIPELINE_BINDER = "binder"
PIPELINE_PROCESS = "process"
IMPLEMENTATION_REPAIR_TASKS = frozenset(
    {
        "poc_prepare_baseline",
        "poc_isolation_repair",
        "poc_measurement",
    }
)
PROJECT_CONTROL_TASKS = frozenset(
    {
        "ndf_improvement_proposal",
        "ndf_improvement_land",
        "process_proposal",
    }
)
PROJECT_CONTROL_ORIGINS = frozenset({"health_finding", "human_intent"})
PROCESS_HOP_CONFIRM = "waiting_confirm"
PROCESS_HOP_REVIEW = "waiting_review"
PROCESS_HOP_DONE = "done"
PROCESS_HOP_CONFIRM_LAND = "confirm_land"
PROCESS_HOP_MANAGED_REVIEW = "review"
REQUIRED_PROCESS_PROPOSAL_STATUS = "Pending confirmation"
MAX_PROCESS_INTENT_BYTES = 16_384
POC_FILES = ("TOPIC.md", "DESIGN.md", "PERF_BASELINE.md", "DELTA.md", "INTERFACE.md")
SPACE_PURPOSE = {
    "design": "契约与前两闸完备：人审过这个 POC 要做什么、怎么设计。",
    "implementation": "第三闸后先落 INTERFACE 切片与 Trunk 拷贝，形成可测基线，不碰 Trunk。",
    "test": "PERF 绑定、DELTA 轮次与 Numbers：用证据判断假设是否成立。",
}
SPACE_GAP_FIX = {
    "DESIGN.md": (
        "点击「OpenClaw: 准备设计文档」。按 TOPIC / proposal 写或补 DESIGN.md；"
        "不得代写门禁审批。"
    ),
    "INTERFACE.md": (
        "点击「OpenClaw: 准备设计文档」。装订器按序补 INTERFACE；不得改 src/。"
    ),
    "missing_design": (
        "点击「OpenClaw: 准备设计文档」。按 proposal 准备 DESIGN.md。"
    ),
    "missing_interface": (
        "点击「OpenClaw: 准备设计文档」。按 DESIGN 契约补 INTERFACE.md。"
    ),
    "missing_topic": (
        "点击「OpenClaw: 准备设计文档」。先补 TOPIC 契约面，再写 DESIGN。"
    ),
    "missing_baseline_workspace": (
        "点击「基线准备」。Claude Code 把 INTERFACE 对照切片和 Trunk 对照代码拷贝进 "
        "poc/<topic>/，形成可 R0 测量的基线。MUST NOT 改 src/。"
    ),
    "no_topic_code": (
        "点击「基线准备」。先在 poc/<topic>/ 建立对照代码工作区，再测。"
    ),
    "numbers_pending": (
        "点击「补测 / 写 DELTA」。Claude Code 跑测量并把 Numbers 写入 DELTA.md / "
        "PERF_BASELINE。这是测量 hop，不是装订器修订。"
    ),
    "empty_numbers": (
        "点击「补测 / 写 DELTA」。空 Numbers 不能判断假设，必须先测量。"
    ),
    "missing_delta": (
        "点击「补测 / 写 DELTA」。先补 DELTA 轮次记录，再对照基线。"
    ),
    "unverified_measurement_claim": (
        "点击「补测 / 写 DELTA」。补齐 Claude Code 测量回执后再把 Numbers 算数。"
    ),
    "vs_unmentioned": (
        "可选：点击「补测 / 写 DELTA」在 Numbers 正文补一行 vs/bl-trunk 引用。"
        "若本主题已有独立 R0 表，可忽略（ok if own R0 table）——不是装订器活。"
    ),
}
REPAIR_TASK_ACTION_IDS = {
    "poc_prepare_baseline": "poc-prepare-baseline",
    "poc_measurement": "poc-measurement",
    "poc_isolation_repair": "poc-isolation-repair",
    "gate_pipeline": "gate-pipeline",
    "binder_pipeline": "binder-pipeline",
    "binder_amend": "binder-amend",
    "design_prepare": "design-prepare",
}
SPACE_CLAUSE_REFS = {
    "design": [
        {"id": "BEH-025", "title": "POC 主题装订纪律"},
        {"id": "CON-POC-001", "title": "POC 隔离"},
    ],
    "implementation": [
        {"id": "BEH-018", "title": "探索不得改 Trunk"},
        {"id": "CON-POC-001", "title": "POC 隔离"},
    ],
    "test": [
        {"id": "META-007", "title": "金标绑定"},
        {"id": "BEH-025", "title": "POC 主题装订纪律"},
    ],
}
GRAPH_CLAUSE_REFS = {
    "meta_graph_failed": [
        {"id": "META-001", "title": "NDF 条款书写与元数据"},
    ],
    "product_graph_failed": [
        {"id": "BEH-019", "title": "晋升闸门"},
    ],
}
GRAPH_CHECK_NAMES = ("meta_graph", "product_graph")
GRAPH_CHECK_COMMANDS = {
    "meta_graph": "python3 spec/meta/tools/ndf_graphcheck.py --meta --format text --report -",
    "product_graph": "python3 spec/meta/tools/ndf_graphcheck.py --product --format text --report -",
}
KERNEL_SEED_IDS = (
    "META-001",
    "META-002",
    "META-003",
    "META-004",
    "META-005",
    "META-008",
    "META-009",
    "META-010",
    "META-011",
    "META-012",
    "META-013",
    "META-014",
    "META-015",
    "CHR-008",
    "BEH-018",
    "BEH-019",
    "BEH-020",
    "BEH-025",
    "CON-POC-001",
)
GENESIS_INSTALL_MATURITIES = frozenset(
    {"uninitialized", "idea_review", "ndf_foundation", "trunk_candidate"}
)
CODE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".py", ".sh", ".rs", ".go"}
CAPABILITY_MAP = {
    "Search core": {
        "files": ("search.md",),
        "modules": ("src/core/disk_hnsw.cpp", "include/disk_hnsw.h"),
    },
    "Fine rerank / I/O": {
        "files": ("fine-rerank.md", "cqe-peeking.md", "io-modes.md"),
        "modules": ("src/core/disk_hnsw.cpp", "include/io_uring_wrapper.h"),
    },
    "Cache": {
        "files": ("cache.md",),
        "modules": ("src/core/block_cache.cpp", "include/block_cache.h"),
    },
    "Prefetch": {
        "files": ("prefetch.md",),
        "modules": ("src/core/graph_prefetcher.cpp", "include/graph_prefetcher.h"),
    },
    "Physical layout": {
        "files": ("cluster-vecblock-layout.md",),
        "modules": ("src/pipeline/cluster_reorder.cpp",),
    },
    "Metrics / honesty": {
        "files": ("metrics.md",),
        "modules": ("src/benchmark/", "scripts/run_sustained.sh"),
    },
    "Test infrastructure": {
        "files": ("test-infra.md",),
        "modules": ("src/test/", "spec/50-verification/"),
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def run_tool(*args: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(TOOLS / args[0]), *args[1:]],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "command": "python3 spec/meta/tools/" + " ".join(args),
        "exit_code": proc.returncode,
        "state": "passed" if proc.returncode == 0 else "failed",
        "output": proc.stdout.strip(),
    }


def public_check(check: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": check["command"],
        "exit_code": check["exit_code"],
        "state": check["state"],
        "summary": clean_markdown(check.get("output") or "", 360),
    }


def skipped_check(reason: str) -> dict[str, Any]:
    return {
        "command": "",
        "exit_code": 0,
        "state": "not_applicable",
        "output": reason,
    }


def gate_ordinal(gate: str | None) -> int | None:
    if gate in GATE_ORDER:
        return GATE_ORDER.index(gate) + 1
    return None


def binder_facet_meta(kind: str | None) -> tuple[str | None, int | None, str | None]:
    if not kind or kind in MEASUREMENT_FINDING_KINDS:
        return None, None, None
    facet = KIND_TO_BINDER_FACET.get(kind)
    if facet is None:
        return None, None, None
    return (
        facet,
        BINDER_FACET_ORDER.index(facet) + 1,
        BINDER_FACET_LABELS[facet],
    )


def default_finding_plane(
    kind: str,
    *,
    repair_task: str,
    gate: str | None = None,
    check_name: str | None = None,
) -> str:
    if gate or str(kind).startswith("gate_"):
        return PLANE_CONTROL
    if repair_task in CONTROL_ONLY_REPAIR_TASKS:
        return PLANE_CONTROL
    if check_name == "bindcheck" or kind in CONTROL_BINDCHECK_KINDS:
        return PLANE_CONTROL
    if kind in KIND_TO_BINDER_FACET and repair_task == "binder_amend":
        return PLANE_BUSINESS
    if kind in MEASUREMENT_FINDING_KINDS:
        return PLANE_BUSINESS
    if repair_task == "binder_amend":
        return PLANE_CONTROL
    return PLANE_CONTROL


def finding_pollutes_business_space(item: Mapping[str, Any]) -> bool:
    if str(item.get("severity") or "") != "error":
        return False
    plane = item.get("plane")
    if plane in {PLANE_CONTROL, PLANE_RUNTIME}:
        return False
    if item.get("repair_task") in CONTROL_ONLY_REPAIR_TASKS:
        return False
    if (
        item.get("repair_task") == "binder_amend"
        and item.get("kind") not in KIND_TO_BINDER_FACET
    ):
        return False
    if item.get("kind") in CONTROL_BINDCHECK_KINDS:
        return False
    return True


def completion_record_blockers(blockers: Sequence[str]) -> list[str]:
    return [
        str(item)
        for item in blockers
        if any(str(item).startswith(prefix) for prefix in COMPLETION_BLOCKER_PREFIXES)
    ]


def humanize_completion_blockers(blockers: Sequence[str]) -> list[str]:
    lines: list[str] = []
    for item in completion_record_blockers(blockers):
        lines.append(COMPLETION_BLOCKER_HUMAN.get(str(item), str(item)))
    return lines


def finding_route(kind: str, *, check_name: str, topic: str) -> dict[str, str]:
    if kind in MEASUREMENT_FINDING_KINDS or check_name == "measurement":
        return {
            "repair_owner": "claude-code",
            "repair_task": "poc_measurement",
            "allowed_write_root": f"poc/{topic}/",
            "plane": PLANE_BUSINESS,
        }
    if check_name == "isolation":
        return {
            "repair_owner": "claude-code",
            "repair_task": "poc_isolation_repair",
            "allowed_write_root": f"poc/{topic}/",
            "plane": PLANE_CONTROL,
        }
    if check_name == "bindcheck" or kind in CONTROL_BINDCHECK_KINDS:
        return {
            "repair_owner": "openclaw",
            "repair_task": "diagnose-topic",
            "allowed_write_root": f"poc/{topic}/ndf/",
            "plane": PLANE_CONTROL,
        }
    if kind in KIND_TO_BINDER_FACET:
        return {
            "repair_owner": "openclaw",
            "repair_task": "binder_amend",
            "allowed_write_root": f"poc/{topic}/ndf/",
            "plane": PLANE_BUSINESS,
        }
    return {
        "repair_owner": "openclaw",
        "repair_task": "diagnose-topic",
        "allowed_write_root": f"poc/{topic}/ndf/",
        "plane": PLANE_CONTROL,
    }


def upsert_finding(findings: list[dict[str, Any]], item: dict[str, Any]) -> None:
    kind = item.get("kind")
    for index, existing in enumerate(findings):
        if existing.get("kind") != kind:
            continue
        if (
            kind in MEASUREMENT_FINDING_KINDS
            and existing.get("repair_task") != item.get("repair_task")
        ):
            findings[index] = item
        return
    findings.append(item)


def perf_bind_ready(perf: Mapping[str, Any] | None) -> bool:
    payload = perf or {}
    bind = payload.get("bind") or {}
    errors = list(payload.get("errors") or [])
    return (
        not errors
        and bool(bind.get("vs"))
        and bool(bind.get("config_id"))
        and bool(bind.get("measure_script"))
    )


def control_repair_label(
    task: str,
    *,
    gate: str | None = None,
    human_gate: str | None = None,
    binder_facet: str | None = None,
    binder_order: int | None = None,
    binder_label: str | None = None,
    kind: str | None = None,
) -> str:
    base = CONTROL_TASK_LABELS.get(task, task)
    if task in {"gate_pipeline", "binder_pipeline"}:
        return base
    order = gate_ordinal(gate)
    phrase = human_gate or (GATE_PHRASES.get(gate) if gate else None)
    if task in GATE_PIPELINE_TASKS and order is not None and phrase:
        return f"门禁 {order}/{len(GATE_ORDER)} {base} · {phrase}"
    if task in GATE_PIPELINE_TASKS and phrase:
        return f"门禁 {base} · {phrase}"
    if task == "binder_amend" or task in BINDER_PIPELINE_TASKS:
        facet = binder_facet
        facet_order = binder_order
        facet_label = binder_label
        if facet is None and kind:
            facet, facet_order, facet_label = binder_facet_meta(kind)
        if facet_order is not None and facet_label:
            return (
                f"装订器 {facet_order}/{len(BINDER_FACET_ORDER)} {base} · {facet_label}"
            )
        if facet_label or kind:
            return f"装订器 {base} · {facet_label or kind}"
    if order is not None and phrase:
        return f"{order}/{len(GATE_ORDER)} {base} · {phrase}"
    if phrase:
        return f"{base} · {phrase}"
    return base


def pipeline_for_task(
    task: str,
    *,
    gate: str | None = None,
    binder_facet: str | None = None,
) -> str | None:
    if task in GATE_PIPELINE_TASKS or gate:
        return PIPELINE_GATE
    if task in BINDER_PIPELINE_TASKS or binder_facet:
        return PIPELINE_BINDER
    return None


def control_pipeline_path(topic: str, pipeline: str) -> Path:
    return PIPELINE_EPISODE_DIR / topic / f"{pipeline}.json"


def active_control_episode(topic: str, pipeline: str) -> str | None:
    path = control_pipeline_path(topic, pipeline)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    episode_id = data.get("episode_id")
    return episode_id if isinstance(episode_id, str) and episode_id else None


def bind_control_pipeline_episode(
    topic: str,
    pipeline: str,
    episode_id: str,
) -> dict[str, Any]:
    path = control_pipeline_path(topic, pipeline)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ndf-control-pipeline-binding/v1",
        "topic": topic,
        "pipeline": pipeline,
        "episode_id": episode_id,
        "updated_at": now_iso(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


CONTROL_DISPATCH_STATES = frozenset(
    {
        "requested",
        "pack_created",
        "context_verified",
        "sent",
        "acknowledged",
        "delivery_unknown",
        "waiting_human",
        "running",
        "blocked",
        "succeeded",
        "failed",
    }
)
CONTROL_DISPATCH_TERMINAL = frozenset({"succeeded", "failed"})
CONTROL_DISPATCH_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"requested"},
    "requested": {"sent", "pack_created", "blocked"},
    "pack_created": {"context_verified", "blocked"},
    "context_verified": {"sent", "blocked"},
    "sent": {"acknowledged", "delivery_unknown", "blocked"},
    "acknowledged": {"waiting_human", "running", "blocked", "succeeded"},
    "delivery_unknown": {"acknowledged", "failed", "blocked"},
    "waiting_human": {"waiting_human", "running", "blocked", "succeeded", "failed"},
    "running": {"running", "waiting_human", "blocked", "succeeded", "failed"},
    "blocked": {"requested"},
    "succeeded": set(),
    "failed": set(),
}


def read_control_dispatch_receipts() -> list[dict[str, Any]]:
    if not CONTROL_DISPATCH_LOG.is_file():
        return []
    receipts: list[dict[str, Any]] = []
    for line in CONTROL_DISPATCH_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            receipts.append(value)
    chain = validate_event_chain(receipts)
    if not chain["valid"]:
        raise ValueError(f"invalid control dispatch chain: {chain['errors']}")
    return receipts


def append_control_dispatch_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    receipts = read_control_dispatch_receipts()
    chained = chained_event(
        {
            **receipt,
            "schema": "ndf-control-dispatch/v1",
            "seq": int(receipts[-1]["seq"]) + 1 if receipts else 1,
        },
        previous_sha=receipts[-1]["event_sha"] if receipts else None,
    )
    CONTROL_DISPATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CONTROL_DISPATCH_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(chained, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return chained


def _control_dispatch_history(request_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in read_control_dispatch_receipts()
        if item.get("request_id") == request_id
    ]


def _message_event_for_request(
    store: ndf_replay.ReplayStore,
    episode_id: str,
    *,
    request_id: str,
    kind: str,
) -> dict[str, Any] | None:
    for events in store.read_all_events(episode_id).values():
        for event in reversed(events):
            if event.get("kind") != kind:
                continue
            try:
                blob = store.get_object(str(event.get("payload_sha")), "blob")
            except (FileNotFoundError, ValueError):
                continue
            value = blob.get("data", {}).get("value")
            if isinstance(value, Mapping) and value.get("request_id") == request_id:
                return event
    return None


def record_control_dispatch(
    *,
    topic: str,
    pipeline: str,
    task: str,
    episode_id: str,
    request_id: str,
    state: str,
    manifest_sha: str | None,
    context_plan_sha: str | None,
    blockers: list[str],
    flow_id: str | None = None,
    hop: str | None = None,
    proposal_id: str | None = None,
    response_sha: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Record one idempotent Cursor→OpenClaw dispatch transition."""
    if pipeline == PIPELINE_PROCESS:
        if task not in PROJECT_CONTROL_TASKS:
            raise ValueError(f"task {task} does not match pipeline {pipeline}")
    elif pipeline not in {PIPELINE_GATE, PIPELINE_BINDER}:
        raise ValueError(f"unknown pipeline: {pipeline}")
    else:
        expected_task = (
            "gate_pipeline" if pipeline == PIPELINE_GATE else "binder_pipeline"
        )
        if task != expected_task:
            raise ValueError(f"task {task} does not match pipeline {pipeline}")
    if state not in CONTROL_DISPATCH_STATES:
        raise ValueError(f"unknown control dispatch state: {state}")
    if not request_id:
        raise ValueError("request_id is required")
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        raise ValueError(f"unknown replay episode: {episode_id}")

    history = _control_dispatch_history(request_id)
    for item in history:
        identity = (
            item.get("topic"),
            item.get("pipeline"),
            item.get("task"),
            item.get("episode_id"),
            item.get("manifest_sha"),
            item.get("context_plan_sha"),
            item.get("flow_id"),
            item.get("hop"),
            item.get("proposal_id"),
        )
        if identity != (
            topic,
            pipeline,
            task,
            episode_id,
            manifest_sha,
            context_plan_sha,
            item.get("flow_id") if flow_id is None else flow_id,
            item.get("hop") if hop is None else hop,
            item.get("proposal_id") if proposal_id is None else proposal_id,
        ):
            raise ValueError("request_id identity mismatch")
        if (
            response_sha
            and item.get("response_sha")
            and item.get("response_sha") != response_sha
        ):
            raise ValueError("conflicting dispatch response identity")
    latest = history[-1] if history else None
    if latest and latest.get("state") in CONTROL_DISPATCH_TERMINAL:
        raise ValueError("terminal dispatch cannot be retried")
    if latest and latest.get("state") == state:
        if list(latest.get("blockers") or []) != blockers:
            raise ValueError("idempotent dispatch blockers mismatch")
        return {**latest, "idempotent": True}, 0
    previous_state = str(latest.get("state")) if latest else None
    if state not in CONTROL_DISPATCH_TRANSITIONS.get(previous_state, set()):
        raise ValueError(
            f"invalid control dispatch transition: {previous_state} -> {state}"
        )

    request_event = _message_event_for_request(
        store,
        episode_id,
        request_id=request_id,
        kind="openclaw.request",
    )
    response_event = _message_event_for_request(
        store,
        episode_id,
        request_id=request_id,
        kind="openclaw.response",
    )
    needs_request = state in {
        "sent",
        "acknowledged",
        "delivery_unknown",
        "waiting_human",
        "running",
        "succeeded",
    }
    needs_response = state in {
        "acknowledged",
        "waiting_human",
        "running",
        "succeeded",
    }
    if needs_request and not request_event:
        raise ValueError("openclaw.request receipt missing")
    if needs_response and not response_event:
        raise ValueError("openclaw.response receipt missing")
    if needs_request and (not manifest_sha or not context_plan_sha):
        raise ValueError("sent dispatch requires manifest and context plan")
    if state == "blocked" and not blockers:
        raise ValueError("blocked dispatch requires blocker")
    if state != "blocked" and blockers:
        raise ValueError("blockers only allowed for blocked dispatch")

    timestamp = now_iso()
    attempt = int((latest or {}).get("attempt") or 1)
    if previous_state in {"blocked", "delivery_unknown"} and state in {
        "requested",
        "sent",
    }:
        attempt += 1
    late = previous_state == "delivery_unknown" and state == "acknowledged"
    receipt = append_control_dispatch_receipt(
        {
            "request_id": request_id,
            "topic": topic,
            "pipeline": pipeline,
            "task": task,
            "episode_id": episode_id,
            "state": state,
            "previous_state": previous_state,
            "attempt": attempt,
            "late": late,
            "flow_id": flow_id or (latest or {}).get("flow_id"),
            "hop": hop or (latest or {}).get("hop"),
            "proposal_id": proposal_id or (latest or {}).get("proposal_id"),
            "response_sha": response_sha or (latest or {}).get("response_sha"),
            "manifest_sha": manifest_sha,
            "context_plan_sha": context_plan_sha,
            "request_event_sha": (
                request_event.get("event_sha") if request_event else None
            ),
            "response_event_sha": (
                response_event.get("event_sha") if response_event else None
            ),
            "blockers": blockers,
            "recorded_at": timestamp,
        }
    )
    blob_sha = store.put_blob(receipt)
    replay_event = store.append_event(
        episode_id,
        kind="control.dispatch",
        actor="tool",
        payload_sha=blob_sha,
        topic=topic,
        task=task,
        track="poc",
        repo_head=git_head(),
        manifest_sha=manifest_sha,
        context_plan_sha=context_plan_sha,
        branch="control",
    )
    bind_control_pipeline_episode(topic, pipeline, episode_id)
    return {
        **receipt,
        "replay_event_sha": replay_event["event_sha"],
        "receipt_path": rel(CONTROL_DISPATCH_LOG),
        "idempotent": False,
    }, 0


def control_dispatch_view(topic: str, pipeline: str) -> dict[str, Any]:
    active_episode = active_control_episode(topic, pipeline)
    matching = [
        item
        for item in read_control_dispatch_receipts()
        if item.get("topic") == topic and item.get("pipeline") == pipeline
    ]
    if not matching or active_episode is None:
        historical = matching[-1] if matching else {}
        return {
            "schema": "ndf-control-dispatch-view/v1",
            "state": "not_dispatched",
            "request_id": None,
            "episode_id": active_episode,
            "acknowledged": False,
            "blockers": [],
            "historical_episode_id": historical.get("episode_id"),
            "historical_state": historical.get("state"),
        }
    latest = matching[-1]
    if latest.get("episode_id") != active_episode:
        return {
            "schema": "ndf-control-dispatch-view/v1",
            "state": "not_dispatched",
            "request_id": None,
            "episode_id": active_episode,
            "acknowledged": False,
            "blockers": [],
            "historical_episode_id": latest.get("episode_id"),
            "historical_state": latest.get("state"),
        }
    return {
        "schema": "ndf-control-dispatch-view/v1",
        "state": latest.get("state"),
        "request_id": latest.get("request_id"),
        "episode_id": latest.get("episode_id"),
        "acknowledged": latest.get("state")
        in {"acknowledged", "waiting_human", "running"},
        "request_event_sha": latest.get("request_event_sha"),
        "response_event_sha": latest.get("response_event_sha"),
        "blockers": list(latest.get("blockers") or []),
        "recorded_at": latest.get("recorded_at"),
        "receipt_path": rel(CONTROL_DISPATCH_LOG),
    }


# Blockers that mean the old Episode/request cannot be reused; must start fresh.
_DISPATCH_NEW_EPISODE_MARKERS = (
    "episode_manifest_mismatch",
    "control_pack_resume_failed",
    "context_plan_sha_drift",
    "request_id identity mismatch",
)


def dispatch_forces_new_episode(blockers: list[str] | None) -> bool:
    """True when resume/--retry of the same request_id would fail closed again."""
    return any(
        any(marker in str(item) for marker in _DISPATCH_NEW_EPISODE_MARKERS)
        for item in blockers or []
    )


def clear_control_pipeline_episode(topic: str, pipeline: str) -> bool:
    path = control_pipeline_path(topic, pipeline)
    if not path.is_file():
        return False
    path.unlink()
    return True


def pipeline_resume_projection(
    topic: str,
    pipeline: str,
    *,
    active_episode: str | None,
    dispatch: dict[str, Any],
) -> dict[str, Any]:
    """Decide whether Canvas may resume Episode / retry the same request_id."""
    force_new = bool(
        dispatch.get("state") == "blocked"
        and dispatch_forces_new_episode(list(dispatch.get("blockers") or []))
    )
    if force_new and active_episode:
        # Drop stale binding so the next pack cannot accidentally --resume.
        clear_control_pipeline_episode(topic, pipeline)
        active_episode = None
    resume = bool(active_episode) and not force_new
    retry_request_id = None
    if (
        dispatch.get("state") == "blocked"
        and not force_new
        and isinstance(dispatch.get("request_id"), str)
        and dispatch.get("request_id")
    ):
        retry_request_id = dispatch["request_id"]
    return {
        "active_episode_id": active_episode,
        "resume": resume,
        "force_new_episode": force_new,
        "retry_request_id": retry_request_id,
        "stale_episode_id": (
            dispatch.get("episode_id") if force_new else None
        ),
    }


def gate_binder_handoff(
    gate_findings: list[dict[str, Any]],
    binder_findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not gate_findings:
        return None
    blocked_gate = min(
        gate_findings,
        key=lambda item: int(item.get("gate_order") or len(GATE_ORDER) + 1),
    ).get("gate")
    prerequisites = GATE_BINDER_PREREQUISITES.get(str(blocked_gate), ())
    available = {
        str(item.get("binder_facet"))
        for item in binder_findings
        if item.get("binder_facet")
    }
    next_facet = next(
        (facet for facet in prerequisites if facet in available),
        None,
    )
    if not next_facet:
        return None
    return {
        "state": "blocked_by_binder",
        "blocked_by_binder": True,
        "blocked_gate": blocked_gate,
        "next_binder_facet": next_facet,
        "next_binder_order": BINDER_FACET_ORDER.index(next_facet) + 1,
        "next_binder_label": BINDER_FACET_LABELS[next_facet],
    }


def control_pipelines_view(
    topic: str,
    findings: list[dict[str, Any]],
    *,
    lifecycle: str = "exploring",
    selected_decision: str | None = None,
) -> dict[str, Any]:
    gate_findings_list = [
        item
        for item in findings
        if item.get("pipeline") == PIPELINE_GATE or item.get("gate")
    ]
    binder_findings_list = [
        item
        for item in findings
        if item.get("pipeline") == PIPELINE_BINDER or item.get("binder_facet")
    ]
    handoff = gate_binder_handoff(gate_findings_list, binder_findings_list)
    active = lifecycle in {"exploring", "blocked"}
    selected = (
        selected_decision if selected_decision in POC_DECISIONS else None
    )
    decision_required = bool(active and not gate_findings_list and not selected)
    gate_dispatch = control_dispatch_view(topic, PIPELINE_GATE)
    binder_dispatch = control_dispatch_view(topic, PIPELINE_BINDER)
    gate_resume = pipeline_resume_projection(
        topic,
        PIPELINE_GATE,
        active_episode=active_control_episode(topic, PIPELINE_GATE),
        dispatch=gate_dispatch,
    )
    binder_resume = pipeline_resume_projection(
        topic,
        PIPELINE_BINDER,
        active_episode=active_control_episode(topic, PIPELINE_BINDER),
        dispatch=binder_dispatch,
    )
    return {
        "schema": "ndf-control-pipelines/v1",
        "gate": {
            "pipeline": PIPELINE_GATE,
            "label": CONTROL_TASK_LABELS["gate_pipeline"],
            "task": "gate_pipeline",
            "step_count": len(GATE_ORDER),
            "steps": unique_actions(gate_findings_list),
            "needed": bool(gate_findings_list),
            "handoff": handoff,
            "blocked_by_binder": bool(handoff),
            "decision_required": decision_required,
            "close_eligible": False,
            "dispatch": gate_dispatch,
            **gate_resume,
        },
        "binder": {
            "pipeline": PIPELINE_BINDER,
            "label": CONTROL_TASK_LABELS["binder_pipeline"],
            "task": "binder_pipeline",
            "step_count": len(BINDER_FACET_ORDER),
            "steps": unique_actions(binder_findings_list),
            "needed": bool(binder_findings_list),
            "handoff_from_gate": handoff,
            "dispatch": binder_dispatch,
            **binder_resume,
        },
    }

def finding_source(kind: str, gate: str | None = None) -> str:
    if gate or kind.startswith("gate_"):
        return "gate"
    if kind in MEASUREMENT_FINDING_KINDS:
        return "synthetic"
    return "health_check"


def finding_why_blocked(
    kind: str, space: str, human_gate: str | None = None
) -> str:
    if kind.startswith("gate_topic_review"):
        return "TOPIC 契约切片未经有效人工审核，不能进入 DESIGN 或写 poc/。"
    if kind.startswith("gate_design_review"):
        return "DESIGN 契约未审，不能写 INTERFACE 或开码。"
    if kind.startswith("gate_implementation_approval"):
        return "第三闸未过，不能委派 poc/ 实现。"
    if kind in {"numbers_pending", "empty_numbers"}:
        return "没有测量 Numbers，不能判断假设是否成立，也不能 promote。"
    if kind == "unverified_measurement_claim":
        return "Numbers 无验证回执，测试空间不算完备。"
    if kind == "vs_unmentioned":
        return (
            "Numbers 正文未再提 vs/金标（advisory）。绑头已齐且有独立 R0 时可忽略；"
            "若要钉引用，由 Claude Code 补测/改 Numbers，不是装订器修订。"
        )
    if kind in {"trunk_write", "isolation_failed"}:
        return "POC 触碰 Trunk 或隔离失败，探索结果不可信。"
    if kind == "missing_delta":
        return "缺少 DELTA 轮次记录，测试空间无法对照基线。"
    if kind in {"missing_design", "missing_interface", "missing_topic"}:
        return "装订器契约缺失，设计空间不完备，不能进入实现。"
    if kind == "missing_baseline_workspace":
        return "缺少 Implementation 基线工作区，无法进行 R0 对齐与后续探索委派。"
    if kind.startswith("missing_") or kind.startswith("unknown_"):
        return f"{space} 空间绑定不完整（{kind}），不能委派测量或合入。"
    if kind.startswith("baseline"):
        return "基线相对现行 Trunk 已 stale，比 Δ 数字不可信。"
    if kind == "meta_graph_failed":
        return "META 图检查未通过，NDF Control 不能把流程规则当作指挥真值。"
    if kind == "product_graph_failed":
        return "产品图检查未通过，应去 Product 修产品树，不得起草 Control 提案。"
    if kind == "index_consistency_failed":
        return "INDEX 与条款图不一致；按失败 ID 平面分流，禁止一键全写 spec/meta/。"
    if kind == "proposal_plane_misfile":
        return "提案 track 与目录不一致，落地会改错树；先移回正确平面。"
    phrase = f" 下一步口令：{human_gate}。" if human_gate else ""
    return f"{space} 空间未完备（{kind}），按 NDF 三空间规则不能继续。{phrase}"


def finding_clause_refs(kind: str, space: str) -> list[dict[str, str]]:
    if kind in GRAPH_CLAUSE_REFS:
        return [dict(item) for item in GRAPH_CLAUSE_REFS[kind]]
    if kind.startswith("gate_") or kind in {
        "missing_topic",
        "missing_design",
        "missing_interface",
        "missing_delta",
        "missing_binder",
    }:
        return list(SPACE_CLAUSE_REFS["design"])
    if kind in {"trunk_write", "isolation_failed"} or "isolation" in kind:
        return list(SPACE_CLAUSE_REFS["implementation"])
    if (
        kind in MEASUREMENT_FINDING_KINDS
        or kind.startswith("missing_vs")
        or kind.startswith("missing_config")
        or kind.startswith("missing_measure")
        or "perf" in kind
        or "numbers" in kind
        or kind.startswith("unknown_vs")
        or kind.startswith("baseline")
    ):
        return list(SPACE_CLAUSE_REFS["test"])
    return list(SPACE_CLAUSE_REFS.get(space.lower(), SPACE_CLAUSE_REFS["design"]))


PROJECT_CHECK_ROUTES = {
    "meta_graph": {
        "plane": "NDF Control",
        "repair_owner": "openclaw",
        "repair_task": "process_proposal",
        "allowed_write_root": "spec/meta/open/",
        "human_gate": "已确认 → 已审核",
    },
    "product_graph": {
        "plane": "Product",
        "repair_owner": "openclaw",
        "repair_task": "product_proposal",
        "allowed_write_root": "spec/open/",
        "human_gate": None,
    },
    "binder_health": {
        "plane": "Topics",
        "repair_owner": "openclaw",
        "repair_task": "binder_amend",
        "allowed_write_root": "poc/*/ndf/",
        "human_gate": None,
    },
    "index_consistency": {
        "plane": "index",
        "repair_owner": "openclaw",
        "repair_task": "index_plane_split",
        "allowed_write_root": None,
        "human_gate": None,
    },
}


def finding(
    *,
    scope: str,
    space: str,
    kind: str,
    severity: str,
    evidence: str,
    repair_owner: str,
    repair_task: str,
    allowed_write_root: str | None,
    human_gate: str | None = None,
    gate: str | None = None,
    plane: str | None = None,
    check_name: str | None = None,
) -> dict[str, Any]:
    binder_facet = binder_order = binder_label = None
    if repair_task == "binder_amend":
        binder_facet, binder_order, binder_label = binder_facet_meta(kind)
    pipeline = pipeline_for_task(
        repair_task, gate=gate, binder_facet=binder_facet
    )
    resolved_plane = plane or default_finding_plane(
        kind, repair_task=repair_task, gate=gate, check_name=check_name
    )
    return {
        "scope": scope,
        "space": space,
        "kind": kind,
        "severity": severity,
        "evidence": evidence,
        "plane": resolved_plane,
        "repair_owner": repair_owner,
        "repair_task": repair_task,
        "allowed_write_root": allowed_write_root,
        "human_gate": human_gate,
        "gate": gate,
        "gate_order": gate_ordinal(gate),
        "binder_facet": binder_facet,
        "binder_order": binder_order,
        "pipeline": pipeline,
        "label": control_repair_label(
            repair_task,
            gate=gate,
            human_gate=human_gate,
            binder_facet=binder_facet,
            binder_order=binder_order,
            binder_label=binder_label,
            kind=kind,
        ),
        "source": finding_source(kind, gate),
        "why_blocked": finding_why_blocked(kind, space, human_gate),
        "clause_refs": finding_clause_refs(kind, space),
    }


def finding_action(item: dict[str, Any]) -> dict[str, Any]:
    gate = item.get("gate")
    human_gate = item.get("human_gate")
    task = item["repair_task"]
    kind = item["kind"]
    binder_facet = item.get("binder_facet")
    binder_order = item.get("binder_order")
    binder_label = None
    if task == "binder_amend" and binder_facet is None:
        binder_facet, binder_order, binder_label = binder_facet_meta(kind)
    elif binder_facet:
        binder_label = BINDER_FACET_LABELS.get(binder_facet, binder_facet)
    pipeline = item.get("pipeline") or pipeline_for_task(
        task, gate=gate, binder_facet=binder_facet
    )
    return {
        "stage": "repair",
        "space": item["space"],
        "owner": item["repair_owner"],
        "task": task,
        "allowed_write_root": item["allowed_write_root"],
        "human_gate": human_gate,
        "kind": kind,
        "gate": gate,
        "gate_order": item.get("gate_order") or gate_ordinal(gate),
        "binder_facet": binder_facet,
        "binder_order": binder_order,
        "pipeline": pipeline,
        "label": item.get("label")
        or control_repair_label(
            task,
            gate=gate,
            human_gate=human_gate,
            binder_facet=binder_facet,
            binder_order=binder_order,
            binder_label=binder_label,
            kind=kind,
        ),
    }


def unique_actions(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in findings:
        kind = str(item.get("kind") or "")
        severity = str(item.get("severity") or "")
        # Advisories stay on findings for display; do not force repair CTAs / pipeline steps.
        if kind in ADVISORY_FINDING_KINDS or severity == "info":
            continue
        action = finding_action(item)
        key = (
            action["owner"],
            action["task"],
            action["allowed_write_root"],
            action["human_gate"],
            action.get("gate"),
            action.get("binder_facet") or action.get("kind"),
        )
        if key not in seen:
            seen.add(key)
            actions.append(action)
    actions.sort(
        key=lambda action: (
            action.get("gate_order") is None,
            action.get("gate_order") or 99,
            action.get("binder_order") is None,
            action.get("binder_order") or 99,
            action["task"],
            action.get("kind") or "",
        )
    )
    return actions


def header(text: str, key: str) -> str | None:
    match = re.search(rf"(?im)^>\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def section(text: str, title: str) -> str:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(title)}\s*$([\s\S]*?)(?=^##\s+|\Z)", text
    )
    return match.group(1).strip() if match else ""


def first_token(value: str | None, default: str = "unknown") -> str:
    if not value:
        return default
    match = re.match(r"\s*([A-Za-z0-9_-]+)", value)
    return match.group(1).lower() if match else default


def git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode, proc.stdout.strip()


def git_head() -> str | None:
    code, output = git("rev-parse", "HEAD")
    return output if code == 0 else None


def git_branch() -> str | None:
    code, output = git("branch", "--show-current")
    return output if code == 0 and output else None


def git_remote_name() -> str:
    code, output = git("remote")
    remotes = [line.strip() for line in output.splitlines() if line.strip()]
    if "origin" in remotes:
        return "origin"
    return remotes[0] if remotes else "origin"


def sanitize_git_remote_url(url: str) -> str:
    value = (url or "").strip()
    if not value or value.startswith("git@"):
        return value
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        netloc = parsed.hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
    return value


def git_remote_url(name: str | None = None) -> str | None:
    remote = name or git_remote_name()
    code, output = git("remote", "get-url", remote)
    if code != 0 or not output:
        return None
    return sanitize_git_remote_url(output)


def git_upstream_ref() -> str | None:
    code, output = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return output if code == 0 and output else None


def git_execution_binding() -> dict[str, str | None]:
    remote = git_remote_name()
    branch = git_branch()
    upstream = git_upstream_ref()
    if not upstream and remote and branch:
        upstream = f"{remote}/{branch}"
    return {
        "remote": remote,
        "remote_url": git_remote_url(remote),
        "branch": branch,
        "upstream": upstream,
        "head": git_head(),
    }


TRUNK_GOLDEN_PATHS = ("src", "include", "tests")


def trunk_paths_changed_since(golden_sha: str, head_sha: str) -> tuple[list[str], bool]:
    """List Trunk source paths that differ between golden and HEAD.

    Returns (paths, ok). ``ok`` is False when git diff itself failed.
    """
    code, output = git(
        "diff",
        "--name-only",
        golden_sha,
        head_sha,
        "--",
        *TRUNK_GOLDEN_PATHS,
    )
    if code != 0:
        return [], False
    return [line.strip() for line in output.splitlines() if line.strip()], True


def file_sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def source_generation_sha() -> str:
    """Hash local workflow evidence without making Canvas a SoT."""
    return generation_layers()["root"]


GENERATION_INDEX_PATH = ROOT / "tmp" / "ndf-generation-index.json"
_GENERATION_MEMO: dict[str, Any] | None = None
CANVAS_CONTEXT_DEPTH = 2
CANVAS_CONTEXT_NODE_BUDGET = 32
PROCESS_CATALOG_HOPS = frozenset(
    {
        PROCESS_HOP_CONFIRM,
        PROCESS_HOP_REVIEW,
        PROCESS_HOP_CONFIRM_LAND,
        PROCESS_HOP_MANAGED_REVIEW,
    }
)
PROCESS_CATALOG_LIFECYCLES = frozenset(
    {
        "pending_confirmation",
        "confirmed_pending_land",
        "implemented_pending_review",
    }
)


def _git_porcelain_lines() -> list[str]:
    code, output = git(
        "status",
        "--porcelain",
        "-uall",
        "--",
        "AGENTS.md",
        "spec",
        "poc",
        ".cursor/skills/ndf-workflow",
    )
    if code != 0 or not output:
        return []
    return [line for line in output.splitlines() if line.strip()]


def _porcelain_paths(lines: Iterable[str]) -> list[str]:
    paths: list[str] = []
    for line in lines:
        raw = line[3:] if len(line) > 3 else line.strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        raw = raw.strip().strip('"')
        if raw:
            paths.append(raw)
    return paths


def _layer_for_relpath(relpath: str) -> str | None:
    if relpath == "AGENTS.md" or relpath.startswith("spec/meta/") or relpath.startswith(
        ".cursor/skills/ndf-workflow/"
    ):
        return "meta"
    if relpath.startswith("spec/"):
        return "product"
    if relpath.startswith("poc/"):
        parts = relpath.split("/")
        if len(parts) >= 2:
            return f"poc:{parts[1]}"
    if relpath.startswith(".ndf/replay/"):
        return "replay"
    return None


def _stat_signature(path: Path) -> tuple[int, int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (int(info.st_ino), int(info.st_mtime_ns), int(info.st_size))


def _load_generation_index() -> dict[str, Any]:
    payload = read_json_artifact(GENERATION_INDEX_PATH) or {}
    files = payload.get("files")
    return files if isinstance(files, dict) else {}


def _store_generation_index(files: Mapping[str, Any]) -> None:
    write_json_artifact(GENERATION_INDEX_PATH, {"files": dict(files)})


def _content_sha_cached(relpath: str, index: dict[str, Any]) -> str:
    path = ROOT / relpath
    signature = _stat_signature(path)
    if signature is None:
        index.pop(relpath, None)
        return "deleted"
    cached = index.get(relpath)
    if (
        isinstance(cached, Mapping)
        and cached.get("ino") == signature[0]
        and cached.get("mtime_ns") == signature[1]
        and cached.get("size") == signature[2]
        and cached.get("sha256")
    ):
        return str(cached["sha256"])
    digest = hashlib.sha256()
    try:
        digest.update(path.read_bytes())
    except OSError:
        index.pop(relpath, None)
        return "deleted"
    sha = digest.hexdigest()
    index[relpath] = {
        "ino": signature[0],
        "mtime_ns": signature[1],
        "size": signature[2],
        "sha256": sha,
    }
    return sha


def _replay_head_fingerprint() -> str:
    root = ROOT / ".ndf" / "replay" / "refs" / "episodes"
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    for path in sorted(root.glob("*/HEAD")):
        digest.update(path.parent.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def generation_layers() -> dict[str, Any]:
    """Merkle fingerprint: git HEAD + dirty content hashes, not a full-tree read."""
    global _GENERATION_MEMO
    head = git_head() or "no-git-head"
    porcelain = _git_porcelain_lines()
    dirty = _porcelain_paths(porcelain)
    replay_sha = _replay_head_fingerprint()
    memo_key = (head, tuple(porcelain), replay_sha)
    if _GENERATION_MEMO and _GENERATION_MEMO.get("memo_key") == memo_key:
        return _GENERATION_MEMO
    index = _load_generation_index()
    dirty_by_layer: dict[str, list[tuple[str, str]]] = {}
    for relpath in dirty:
        layer = _layer_for_relpath(relpath)
        if layer is None:
            continue
        dirty_by_layer.setdefault(layer, []).append(
            (relpath, _content_sha_cached(relpath, index))
        )
    _store_generation_index(index)

    def layer_sha(name: str) -> str:
        digest = hashlib.sha256()
        digest.update(head.encode())
        digest.update(b"\0")
        digest.update(name.encode())
        digest.update(b"\0")
        for relpath, sha in sorted(dirty_by_layer.get(name, [])):
            digest.update(relpath.encode())
            digest.update(b"\0")
            digest.update(sha.encode())
            digest.update(b"\0")
        return digest.hexdigest()

    poc_ids = sorted(
        {
            key.split(":", 1)[1]
            for key in dirty_by_layer
            if key.startswith("poc:")
        }
        | set(active_poc_topic_ids())
    )
    poc = {topic_id: layer_sha(f"poc:{topic_id}") for topic_id in poc_ids}
    layers = {
        "repo_head": head,
        "meta": layer_sha("meta"),
        "product": layer_sha("product"),
        "poc": poc,
        "replay": replay_sha,
    }
    root = hashlib.sha256()
    root.update(head.encode())
    root.update(b"\0")
    for key in ("meta", "product", "replay"):
        root.update(layers[key].encode())
        root.update(b"\0")
    for topic_id in sorted(poc):
        root.update(topic_id.encode())
        root.update(b"\0")
        root.update(poc[topic_id].encode())
        root.update(b"\0")
    layers["root"] = root.hexdigest()
    layers["memo_key"] = memo_key
    _GENERATION_MEMO = layers
    return layers


def reset_generation_cache() -> None:
    global _GENERATION_MEMO
    _GENERATION_MEMO = None


def context_binding(
    *,
    topic: str | None,
    role: str,
    task: str,
    track: str,
    allowed_write_roots: list[str] | None = None,
    control_binding: Mapping[str, Any] | None = None,
    depth: int = 8,
    node_budget: int = 240,
    byte_budget: int = 1_048_576,
    include_bodies: bool = True,
) -> dict[str, Any]:
    """Compile one shared manifest and its role-specific verified task plan."""
    try:
        manifest = ndf_context.create_manifest(
            root=ROOT,
            topic=topic,
            task=task,
            track=track,
            control_binding=control_binding,
            depth=depth,
            node_budget=node_budget,
            byte_budget=byte_budget,
            include_bodies=include_bodies,
        )
        if allowed_write_roots is not None:
            derived_roots = list(
                manifest.get("role_policies", {})
                .get(role, {})
                .get("allowed_write_roots", [])
            )
            if any(root not in derived_roots for root in allowed_write_roots):
                raise ValueError(
                    "requested write roots exceed compiler-derived role policy: "
                    f"requested={allowed_write_roots} derived={derived_roots}"
                )
        manifest_check = ndf_context.verify_manifest(manifest, root=ROOT)
        if not manifest_check.get("valid"):
            return {
                "task_manifest": manifest,
                "manifest_sha": manifest.get("manifest_sha"),
                "context_plan": None,
                "context_verify": {
                    "schema": "ndf-context-verification/v1",
                    "valid": False,
                    "errors": list(manifest_check.get("errors") or []),
                    "warnings": [],
                },
                "plan_sha": None,
            }
        plan = ndf_context.role_plan(manifest, role=role)
        verification = ndf_context.verify_plan(
            plan,
            root=ROOT,
            manifest=manifest,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        message = str(exc)
        errors: list[dict[str, Any]] = [{"kind": "context_compile_failed", "message": message}]
        # Preserve structured errors when role_plan rejected a bad manifest.
        if "invalid task manifest:" in message:
            raw = message.split("invalid task manifest:", 1)[1].strip()
            try:
                parsed = ast.literal_eval(raw)
                if isinstance(parsed, list) and parsed:
                    errors = [
                        item if isinstance(item, dict) else {"kind": "context_compile_failed", "message": str(item)}
                        for item in parsed
                    ]
            except (SyntaxError, ValueError):
                pass
        return {
            "context_plan": None,
            "context_verify": {
                "schema": "ndf-context-verification/v1",
                "valid": False,
                "errors": errors,
                "warnings": [],
            },
            "plan_sha": None,
            "manifest_sha": None,
            "task_manifest": None,
        }
    return {
        "task_manifest": manifest,
        "manifest_sha": manifest.get("manifest_sha"),
        "context_plan": plan,
        "context_verify": verification,
        "plan_sha": plan.get("plan_sha"),
    }


def empty_context_binding(topic: str | None = None) -> dict[str, Any]:
    return {
        "context_plan": None,
        "context_verify": {
            "schema": "ndf-context-verification/v1",
            "valid": False,
            "errors": [{"kind": "context_not_compiled", "message": "directory row"}],
            "warnings": [],
        },
        "plan_sha": None,
        "manifest_sha": None,
        "task_manifest": None,
    }


def context_binding_for_canvas(topic: str) -> dict[str, Any]:
    """Shallow Canvas preview. Full create_manifest stays on pack/control-pack.

    Canvas MUST NOT compile as a write-role `poc_implementation` verify surface:
    gate drift after documenting a dropped hypothesis would paint hero red and
    conflate Test/close readiness with ACP dispatch readiness ([[META-011]]).
    """
    layers = generation_layers()
    poc_sha = (layers.get("poc") or {}).get(topic)
    cached = latest_topic_health(topic, layers["root"], poc_sha=poc_sha)
    if cached and cached.get("state") == "current":
        delegation = cached.get("delegation")
        if isinstance(delegation, Mapping) and delegation.get("context_plan"):
            verify = delegation.get("context_verify") or {}
            # Only reuse cache when verify already succeeded — otherwise recompile
            # so Agents/context-compiler is not stuck on stale clause_drift.
            if verify.get("valid"):
                return {
                    "task_manifest": None,
                    "manifest_sha": delegation.get("manifest_sha"),
                    "context_plan": delegation.get("context_plan"),
                    "context_verify": verify,
                    "plan_sha": delegation.get("plan_sha"),
                }
    # Read-only canvas role: truncated graph must not hard-fail write-role verify.
    # task=partial seeds close/decision clauses without requiring gate 3 for the
    # projection; ACP packs still compile task=poc_implementation separately.
    return context_binding(
        topic=topic,
        role="canvas",
        task="partial",
        track="poc",
        depth=CANVAS_CONTEXT_DEPTH,
        node_budget=CANVAS_CONTEXT_NODE_BUDGET,
        byte_budget=32_768,
        include_bodies=False,
    )


def bind_pack_to_episode(
    payload: dict[str, Any],
    *,
    episode_id: str | None = None,
    require_episode: bool = False,
) -> dict[str, Any]:
    """Optionally record a pack in Replay (legacy).

    Daily product/process/poc path (ADR-META-004): ``require_episode=False`` is
    the default — return the pack unchanged and never write Episode/Replay.
    Success is disk completion + write-root identity, not Replay DAG completeness.
    """
    identifier = episode_id or os.environ.get("NDF_REPLAY_EPISODE")
    allowed_roots = (
        payload.get("context_plan", {})
        .get("privileges", {})
        .get("allowed_write_roots", [])
    )
    if payload.get("allowed_write_root"):
        allowed_roots = [payload.get("allowed_write_root")]
    will_send = payload.get("safe_to_dispatch") is True or (
        payload.get("safe_to_delegate") is True
        and payload.get("runtime_dispatch_ready") is not False
        and payload.get("provider") == "openclaw"
        and payload.get("execution_capabilities_ready") is not False
        and payload.get("dispatch_state") != "waiting_human"
        and "waiting_human" not in (payload.get("blockers") or [])
    )
    writable = bool(allowed_roots) and bool(will_send)
    # ADR-META-004: daily packs never bind or write Episode/Replay.
    if not require_episode:
        return payload
    if not identifier:
        if writable:
            raise ValueError("writable pack requires explicit Replay Episode")
        return payload
    lease_only_pack = str(payload.get("task") or "") in {"prepare_acp_lease"}
    if writable and not lease_only_pack and (
        not isinstance(payload.get("task_manifest"), Mapping)
        or not payload.get("manifest_sha")
        or not isinstance(payload.get("context_plan"), Mapping)
        or not payload.get("plan_sha")
        or not all(isinstance(root, str) and root for root in allowed_roots)
    ):
        raise ValueError(
            "writable pack requires manifest, role plan, and exact write root"
        )
    store = ndf_replay.ReplayStore(ROOT)
    manifest = payload.get("task_manifest")
    hop = payload.get("hop")
    flow_id = payload.get("flow_id")
    if (
        payload.get("task") in PROJECT_CONTROL_TASKS
        and hop in ndf_replay.CONTROL_STAGES
        and flow_id
    ):
        proposal = (
            payload.get("proposal")
            if isinstance(payload.get("proposal"), Mapping)
            else {}
        )
        binding = store.ensure_control_child(
            flow_id=str(flow_id),
            stage=str(hop),
            requested_episode_id=identifier,
            manifest=manifest if isinstance(manifest, Mapping) else None,
            topic=payload.get("topic"),
            task=str(payload.get("task") or payload.get("next_action") or "dispatch"),
            role=str(payload.get("provider") or "tool"),
            track=str(payload.get("track") or "process"),
            proposal_id=payload.get("proposal_id"),
            proposal_sha=proposal.get("proposal_sha"),
        )
        identifier = binding["episode_id"]
        payload["episode_id"] = identifier
        payload["parent_episode_id"] = binding["parent_episode_id"]
    elif store.read_ref(f"episodes/{identifier}/HEAD") is None:
        store.init_episode(
            topic=payload.get("topic"),
            task=str(payload.get("task") or payload.get("next_action") or "dispatch"),
            role=str(payload.get("provider") or "tool"),
            track=str(payload.get("track") or "process"),
            manifest=manifest if isinstance(manifest, Mapping) else None,
            episode_id=identifier,
        )
    existing_manifest_shas = {
        event.get("manifest_sha")
        for events in store.read_all_events(identifier).values()
        for event in events
        if event.get("manifest_sha")
    }
    if payload.get("manifest_sha") and existing_manifest_shas not in (
        set(),
        {payload.get("manifest_sha")},
    ):
        raise ValueError("episode manifest does not match generated pack")
    if isinstance(manifest, Mapping):
        manifest_blob = store.put_blob(dict(manifest))
        if not any(
            event.get("kind") == "manifest.created"
            and event.get("payload_sha") == manifest_blob
            for events in store.read_all_events(identifier).values()
            for event in events
        ):
            store.append_event(
                identifier,
                kind="manifest.created",
                actor="context-compiler",
                payload_sha=manifest_blob,
                topic=payload.get("topic"),
                task=str(payload.get("task") or "dispatch"),
                track=str(payload.get("track") or "process"),
                repo_head=payload.get("base_sha"),
                manifest_sha=payload.get("manifest_sha"),
                context_plan_sha=None,
            )
    if payload.get("task") in PROJECT_CONTROL_TASKS:
        proposal = (
            payload.get("proposal")
            if isinstance(payload.get("proposal"), Mapping)
            else {}
        )
        hop = payload.get("hop")
        human_kind = None
        human_actor = None
        human_payload: dict[str, Any] | None = None
        if hop == "confirm_land":
            receipt = next(
                (
                    item
                    for item in proposal.get("receipts", [])
                    if isinstance(item, Mapping)
                    and item.get("event") == "proposal.confirmed"
                    and item.get("status", "").lower() in {"valid", "approved"}
                ),
                None,
            )
            if isinstance(receipt, Mapping):
                human_kind = "proposal.confirmed"
                human_actor = str(receipt.get("actor") or "human")
                human_payload = {
                    **dict(receipt),
                    "proposal_id": payload.get("proposal_id"),
                    "flow_id": payload.get("flow_id"),
                    "hop": hop,
                    "manifest_sha": payload.get("manifest_sha"),
                    "context_plan_sha": payload.get("plan_sha"),
                }
        elif hop == "review" and payload.get("request", {}).get(
            "human_phrase"
        ) == "已审核":
            human_kind = "proposal.reviewed"
            human_actor = "human"
            human_payload = {
                "proposal_id": payload.get("proposal_id"),
                "flow_id": payload.get("flow_id"),
                "hop": hop,
                "phrase": "已审核",
                "actor": "human",
                "proposal_sha": proposal.get("proposal_sha"),
                "manifest_sha": payload.get("manifest_sha"),
                "context_plan_sha": payload.get("plan_sha"),
            }
        if human_kind and human_payload and human_actor:
            human_blob = store.put_blob(human_payload)
            store.append_event(
                identifier,
                kind=human_kind,
                actor=human_actor,
                payload_sha=human_blob,
                topic=payload.get("topic"),
                task=str(payload.get("task") or "dispatch"),
                track=str(payload.get("track") or "process"),
                repo_head=payload.get("base_sha"),
                manifest_sha=payload.get("manifest_sha"),
                context_plan_sha=payload.get("plan_sha"),
                branch="control",
            )
    context_plan = payload.get("context_plan")
    branch = (
        "implementation"
        if payload.get("provider") == "claude-code-acp"
        else "control"
    )
    if isinstance(context_plan, Mapping):
        plan_blob = store.put_blob(dict(context_plan))
        store.append_event(
            identifier,
            kind="context.compiled",
            actor="context-compiler",
            payload_sha=plan_blob,
            topic=payload.get("topic"),
            task=str(payload.get("task") or "dispatch"),
            track=str(payload.get("track") or "process"),
            repo_head=payload.get("base_sha"),
            manifest_sha=payload.get("manifest_sha"),
            context_plan_sha=payload.get("plan_sha"),
            branch=branch,
        )
    verification = payload.get("context_verify")
    verified = (
        isinstance(verification, Mapping) and verification.get("valid") is True
    )
    if verified:
        verification_blob = store.put_blob(
            {
                **dict(verification),
                "proposal_id": payload.get("proposal_id"),
                "flow_id": payload.get("flow_id"),
                "hop": payload.get("hop"),
                "manifest_sha": payload.get("manifest_sha"),
                "context_plan_sha": payload.get("plan_sha"),
            }
        )
        store.append_event(
            identifier,
            kind="context.verified",
            actor="context-compiler",
            payload_sha=verification_blob,
            topic=payload.get("topic"),
            task=str(payload.get("task") or "dispatch"),
            track=str(payload.get("track") or "process"),
            repo_head=payload.get("base_sha"),
            manifest_sha=payload.get("manifest_sha"),
            context_plan_sha=payload.get("plan_sha"),
            branch=branch,
        )
    recorded = dict(payload)
    recorded.pop("replay", None)
    if recorded.get("task") in PROJECT_CONTROL_TASKS and not isinstance(
        recorded.get("acquisition_snapshot"), Mapping
    ):
        recorded["acquisition_snapshot"] = git_mutation_snapshot(ROOT)
        payload["acquisition_snapshot"] = recorded["acquisition_snapshot"]
    blob_sha = store.put_blob(recorded)
    event = store.append_event(
        identifier,
        kind=(
            "dispatch.preflight"
            if (
                payload.get("safe_to_dispatch")
                or payload.get("safe_to_delegate")
            )
            and (
                payload.get("task") not in PROJECT_CONTROL_TASKS or verified
            )
            else "dispatch.blocked"
        ),
        actor=str(payload.get("provider") or "tool"),
        payload_sha=blob_sha,
        topic=payload.get("topic"),
        task=str(payload.get("task") or payload.get("next_action") or "dispatch"),
        track=str(payload.get("track") or "process"),
        repo_head=payload.get("base_sha"),
        manifest_sha=payload.get("manifest_sha"),
        context_plan_sha=payload.get("plan_sha"),
        branch=branch,
    )
    payload["replay"] = {
        "episode_id": identifier,
        "pack_blob_sha": blob_sha,
        "event_sha": event["event_sha"],
        "coverage": "preflight",
    }
    payload["episode_id"] = identifier
    return payload


def replay_pack_binding(
    episode_id: str,
    *,
    task: str,
    manifest_sha: str | None,
    context_plan_sha: str | None,
) -> tuple[str, dict[str, Any]]:
    """Return the latest verified writable pack in an Episode."""
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    branch_events = store.read_all_events(episode_id)
    for event in reversed(
        [
            item
            for events in branch_events.values()
            for item in events
        ]
    ):
        if (
            event.get("kind") != "dispatch.preflight"
            or event.get("task") != task
            or event.get("manifest_sha") != manifest_sha
            or event.get("context_plan_sha") != context_plan_sha
        ):
            continue
        pack_sha = str(event.get("payload_sha") or "")
        obj = store.get_object(pack_sha, "blob")["data"]
        pack = obj.get("value")
        if not isinstance(pack, dict):
            continue
        if (
            not ndf_replay.dispatch_pack_lease_eligible(pack)
            or pack.get("task") != task
            or pack.get("manifest_sha") != manifest_sha
            or pack.get("plan_sha") != context_plan_sha
        ):
            continue
        return pack_sha, pack
    raise ValueError("no verified dispatch pack matches lease context")


def active_runtime_leases() -> list[dict[str, Any]]:
    """Return latest active lease per run, ignoring malformed legacy records."""
    latest: dict[str, dict[str, Any]] = {}
    try:
        records = read_leases(LEASE_LOG, root=ROOT, strict=False)
    except ValueError:
        records = []
    for record in records:
        run_id = record.get("run_id")
        if not run_id:
            continue
        task = str(record.get("task") or "implement")
        if task == "prepare_acp_lease":
            semantic = validate_runtime_lease_binding(
                record,
                root=ROOT,
                expected={
                    "topic": record.get("topic"),
                    "task": task,
                    "base_sha": record.get("base_sha"),
                    "episode_id": record.get("episode_id"),
                    "branch": record.get("branch"),
                    "repo_root": str(ROOT),
                    "allowed_write_root": record.get("allowed_write_root"),
                },
            )
            if semantic["valid"]:
                latest[str(run_id)] = record
            continue
        context = context_binding(
            topic=record.get("topic"),
            role="claude-code",
            task=task,
            track=str(record.get("mode") or "poc"),
        )
        try:
            pack_sha, pack = replay_pack_binding(
                str(record.get("episode_id") or ""),
                task=str(record.get("task") or "implement"),
                manifest_sha=context.get("manifest_sha"),
                context_plan_sha=context.get("plan_sha"),
            )
        except (FileNotFoundError, ValueError):
            continue
        semantic = validate_runtime_lease_binding(
            record,
            root=ROOT,
            expected={
                "topic": record.get("topic"),
                "task": record.get("task"),
                "repo_head": git_head(),
                "base_sha": pack.get("base_sha"),
                "plan_sha": context.get("plan_sha"),
                "manifest_sha": context.get("manifest_sha"),
                "allowed_write_root": pack.get("allowed_write_root"),
                "pack_sha": pack_sha,
                "episode_id": record.get("episode_id"),
                "branch": record.get("branch"),
                "repo_root": str(ROOT),
            },
        )
        if semantic["valid"]:
            latest[str(run_id)] = record
    return [record for record in latest.values() if record.get("result") == "active"]


def topic_active_lease(topic: str | None) -> dict[str, Any] | None:
    """Best active lease row for topic: HEAD-aligned first, else newest started_at."""
    candidates = [
        lease for lease in active_runtime_leases() if lease.get("topic") == topic
    ]
    if not candidates:
        return None
    head = git_head()
    for lease in candidates:
        lease_head = str(lease.get("base_sha") or lease.get("repo_head") or "")
        if lease_head and head == lease_head:
            return lease
    return max(candidates, key=lambda row: str(row.get("started_at") or ""))


def active_isolated_lease_for_topic(
    topic_id: str,
) -> tuple[bool, dict[str, Any] | None]:
    """True when topic has active lease at current HEAD with run_id + worktree."""
    head = git_head()
    candidates = [
        lease for lease in active_runtime_leases() if lease.get("topic") == topic_id
    ]
    for lease in candidates:
        lease_head = str(lease.get("base_sha") or lease.get("repo_head") or "")
        if not lease_head or head != lease_head:
            continue
        if not str(lease.get("run_id") or "").strip():
            continue
        if not str(lease.get("worktree") or "").strip():
            continue
        if str(lease.get("result") or "") != "active":
            continue
        return True, lease
    stale = topic_active_lease(topic_id)
    return False, stale


def lease_stale_vs_head(
    lease: Mapping[str, Any] | None,
    head: str | None = None,
) -> bool:
    """True when jsonl lease exists but its base_sha is not the commander HEAD."""
    if not lease:
        return False
    head = str(head or git_head() or "")
    lease_head = str(lease.get("base_sha") or lease.get("repo_head") or "")
    if not head or not lease_head:
        return False
    return lease_head != head


def read_action_receipts() -> list[dict[str, Any]]:
    receipts, malformed = parse_action_receipts()
    if malformed:
        raise ValueError("malformed action receipt")
    return receipts


def parse_action_receipts() -> tuple[list[dict[str, Any]], bool]:
    if not ACTION_LOG.is_file():
        return [], False
    receipts: list[dict[str, Any]] = []
    malformed = False
    for line in read_text(ACTION_LOG).splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed = True
            continue
        if isinstance(value, dict) and value.get("action_id"):
            receipts.append(value)
        else:
            malformed = True
    return receipts, malformed


def latest_projection_receipt() -> dict[str, Any] | None:
    if not PROJECTION_EVIDENCE_DIR.is_dir():
        return None
    receipts: list[dict[str, Any]] = []
    for path in sorted(PROJECTION_EVIDENCE_DIR.glob("receipt-*.json")):
        payload = read_json_artifact(path)
        if isinstance(payload, dict) and payload.get("schema") == "ndf-projection-receipt/v2":
            receipts.append(payload)
    if not receipts:
        return None
    return max(receipts, key=lambda item: str(item.get("finished_at") or ""))


def action_chain_status(receipts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate the v2 action chain; legacy rows are never chain evidence."""
    records = receipts if receipts is not None else read_action_receipts()
    chained = [
        item
        for item in records
        if item.get("schema") == "ndf-workflow-action/v2"
    ]
    chain = validate_event_chain(chained)
    receipt_errors = [
        f"receipt:{index}:{error}"
        for index, item in enumerate(chained, 1)
        for error in validate_receipt(item)["errors"]
    ]
    return {
        **chain,
        "valid": chain["valid"] and not receipt_errors,
        "errors": [*chain["errors"], *receipt_errors],
        "legacy_count": len(records) - len(chained),
    }


def append_action_receipt(receipt: dict[str, Any]) -> None:
    chained = [
        item
        for item in read_action_receipts()
        if item.get("schema") == "ndf-workflow-action/v2" and item.get("event_sha")
    ]
    chain = action_chain_status(chained)
    if not chain["valid"]:
        raise ValueError(f"cannot append to invalid action chain: {chain['errors']}")
    receipt = chained_event(
        {
            **receipt,
            "schema": "ndf-workflow-action/v2",
            "seq": int(chained[-1]["seq"]) + 1 if chained else 1,
        },
        previous_sha=chained[-1]["event_sha"] if chained else None,
    )
    validation = validate_receipt(receipt)
    if not validation["valid"]:
        raise ValueError(f"invalid action receipt: {validation['errors']}")
    ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACTION_LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def projection_freshness(generation_sha: str) -> dict[str, Any]:
    receipts, malformed = parse_action_receipts()
    projection = latest_projection_receipt()
    base = {
        "snapshot_sha": generation_sha,
        "latest_action": None,
        "receipt_path": rel(ACTION_LOG),
        "projection_receipt": (
            {
                "absorbed_action_id": projection.get("absorbed_action_id"),
                "source_generation_sha": projection.get("source_generation_sha"),
                "result": projection.get("result"),
            }
            if projection
            else None
        ),
    }
    if malformed:
        return {**base, "state": "unknown", "reason": "malformed_action_receipt"}
    if not receipts:
        if (
            projection
            and projection.get("result") == "passed"
            and projection.get("source_generation_sha") == generation_sha
            and not projection.get("absorbed_action_id")
        ):
            return {**base, "state": "fresh"}
        return {**base, "state": "unknown", "reason": "no_action_or_projection_receipt"}
    chain = action_chain_status(receipts)
    if not chain["valid"]:
        return {**base, "state": "unknown", "chain": chain, "reason": "invalid_action_chain"}
    latest_by_id: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        latest_by_id[str(receipt["action_id"])] = receipt
    in_progress = [
        receipt for receipt in latest_by_id.values() if receipt.get("status") == "started"
    ]
    latest = receipts[-1]
    finished = [
        receipt
        for receipt in latest_by_id.values()
        if receipt.get("status") == "finished"
    ]
    latest_finished = max(
        finished,
        key=lambda item: str(item.get("finished_at") or item.get("started_at") or ""),
        default=None,
    )
    # Serial action model: a later finished receipt supersedes older abandoned
    # starts. Otherwise one orphaned action-begin permanently fail-closes CTAs.
    if latest_finished is not None:
        finish_at = str(
            latest_finished.get("finished_at") or latest_finished.get("started_at") or ""
        )
        in_progress = [
            receipt
            for receipt in in_progress
            if str(receipt.get("started_at") or "") >= finish_at
        ]
    if in_progress:
        state = "refresh_in_progress"
    elif latest_finished:
        absorbed = (
            projection
            and projection.get("result") == "passed"
            and projection.get("source_generation_sha") == generation_sha
            and projection.get("absorbed_action_id") == latest_finished.get("action_id")
        )
        state = "fresh" if absorbed else "stale_after_action"
    else:
        state = "unknown"
    return {
        **base,
        "state": state,
        "latest_action": latest,
        "in_progress": sorted(
            (receipt["action_id"] for receipt in in_progress),
        ),
        "chain": chain,
    }


def action_begin(
    operation: str,
    topic: str | None,
    action_id: str | None,
    episode_id: str | None = None,
    catalog_action_id: str | None = None,
) -> dict[str, Any]:
    """Commander ActionSpec retired (ADR-META-004). No receipts / Replay writes."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "action-begin",
        "deprecated": True,
        "reason": "ADR-META-004",
        "operation": operation,
        "topic": topic,
        "action_id": action_id,
        "episode_id": episode_id,
        "catalog_action_id": catalog_action_id,
    }


def action_finish(
    action_id: str,
    result: str,
    blockers: list[str],
    episode_id: str | None = None,
) -> dict[str, Any]:
    """Commander ActionSpec retired (ADR-META-004). No receipts / Replay writes."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "action-finish",
        "deprecated": True,
        "reason": "ADR-META-004",
        "action_id": action_id,
        "result": result,
        "blockers": list(blockers or []),
        "episode_id": episode_id,
    }


def action_commit(
    action_id: str,
    *,
    catalog_action_id: str | None = None,
    prompt: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Commander ActionSpec retired (ADR-META-004). No git commit / Replay writes."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "action-commit",
        "deprecated": True,
        "reason": "ADR-META-004",
        "action_id": action_id,
        "catalog_action_id": catalog_action_id,
        "label": label,
        "prompt_provided": bool(prompt),
    }


def bundle_sha(paths: list[Path]) -> str | None:
    existing = sorted({p.resolve() for p in paths if p.is_file()}, key=str)
    if not existing:
        return None
    digest = hashlib.sha256()
    for path in existing:
        digest.update(rel(path).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    clean = value.strip().strip("[]")
    return [part.strip().strip("`\"'") for part in re.split(r"[,;]", clean) if part.strip()]


def normalize_lifecycle(raw: str | None) -> str:
    value = (raw or "").lower()
    if "reject" in value:
        return "rejected"
    if "promot" in value:
        return "promoted"
    if "closed" in value:
        return "closed"
    if "block" in value:
        return "blocked"
    if "explor" in value or "active" in value:
        return "exploring"
    return "unknown"


def clean_markdown(text: str, limit: int = 280) -> str:
    value = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    value = re.sub(r"\[\[([A-Z0-9-]+)(?:\|[^\]]+)?\]\]", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[`*#>]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" :")
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def clause_chunk(text: str, clause_id: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+.*?\{{#{re.escape(clause_id)}\}}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def clause_summary(text: str, clause_id: str) -> str:
    chunk = clause_chunk(text, clause_id)
    chunk = re.sub(r"(?m)^<!--\s*ndf:.*?-->\s*$", "", chunk)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", chunk) if part.strip()]
    for paragraph in paragraphs:
        if paragraph.startswith(("```", "|")):
            continue
        summary = clean_markdown(paragraph)
        if summary:
            return summary
    return ""


def clause_status_counts(paths: list[Path]) -> dict[str, int]:
    counts = {"stable": 0, "draft": 0, "deprecated": 0, "other": 0}
    for path in paths:
        text = read_text(path)
        matches = list(re.finditer(r"(?m)^##\s+.*?\{#[A-Z][A-Z0-9-]+\}\s*$", text))
        anchored_ids: set[str] = set()
        for index, match in enumerate(matches):
            id_match = re.search(r"\{#([A-Z][A-Z0-9-]+)\}", match.group(0))
            if id_match:
                anchored_ids.add(id_match.group(1))
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chunk = text[match.end() : end]
            status_match = re.search(r"\bstatus=([A-Za-z_-]+)", chunk[:600])
            status = status_match.group(1).lower() if status_match else "other"
            counts[status if status in counts else "other"] += 1
        for metadata in re.finditer(r"<!--\s*ndf:\s*([^>]+)-->", text):
            id_match = re.search(r"\bid=([A-Z][A-Z0-9-]+)", metadata.group(1))
            if not id_match or id_match.group(1) in anchored_ids:
                continue
            status_match = re.search(r"\bstatus=([A-Za-z_-]+)", metadata.group(1))
            status = status_match.group(1).lower() if status_match else "other"
            counts[status if status in counts else "other"] += 1
    return counts


def markdown_rows(section_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [clean_markdown(cell, 160) for cell in line.strip().strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    return rows


def markdown_table(path: Path) -> list[dict[str, str]]:
    return ndf_gate_slices.parse_gates_table(read_text(path))


def latest_gate_rows(path: Path) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in markdown_table(path):
        latest[row["gate"]] = row
    return latest


def proposal_paths(topic_text: str) -> list[Path]:
    found: list[Path] = []
    for raw in re.findall(r"(?:spec/open|ndf/proposals)/[A-Za-z0-9_.-]+\.md", topic_text):
        path = ROOT / raw if raw.startswith("spec/") else None
        if path is not None and path.is_file():
            found.append(path)
    return found


def poc_gate_bundles(topic_dir: Path) -> dict[str, list[Path]]:
    ndf = topic_dir / "ndf"
    topic = ndf / "TOPIC.md"
    proposals = proposal_paths(read_text(topic))
    impl = [
        topic,
        ndf / "DESIGN.md",
        ndf / "PERF_BASELINE.md",
        ndf / "DELTA.md",
        ndf / "INTERFACE.md",
    ]
    return {
        "topic_review": [topic, *proposals],
        "design_review": [topic, ndf / "DESIGN.md"],
        "implementation_approval": list(impl),
        "bundle_dispatch": list(impl),
    }


def implementation_license(
    gates: Mapping[str, Any],
) -> dict[str, Any]:
    """Human implement license: classic gate 3 or text-first 「派发」."""
    impl = gates.get("implementation_approval") or {}
    bundle = gates.get("bundle_dispatch") or {}
    if impl.get("state") == "valid":
        return {
            "ok": True,
            "source": "implementation_approval",
            "phrase": GATE_PHRASES["implementation_approval"],
            "gate": impl,
            "approved_content_sha": impl.get("approved_content_sha"),
            "expected_content_sha": impl.get("expected_content_sha"),
        }
    if bundle.get("state") == "valid":
        return {
            "ok": True,
            "source": "bundle_dispatch",
            "phrase": GATE_PHRASES["bundle_dispatch"],
            "gate": bundle,
            "approved_content_sha": bundle.get("approved_content_sha"),
            "expected_content_sha": bundle.get("expected_content_sha"),
        }
    state = impl.get("state") or bundle.get("state") or "missing"
    return {
        "ok": False,
        "source": None,
        "phrase": None,
        "gate": impl or bundle,
        "approved_content_sha": None,
        "expected_content_sha": impl.get("expected_content_sha")
        or bundle.get("expected_content_sha"),
        "state": state,
    }


def poc_gate_bundle_specs(topic_dir: Path) -> dict[str, dict[str, Any]]:
    topic = topic_dir / "ndf" / "TOPIC.md"
    return ndf_gate_slices.gate_bundle_specs(
        topic_dir,
        root=ROOT,
        proposal_paths=proposal_paths(read_text(topic)),
    )


def gate_view(
    gates_path: Path,
    bundles: dict[str, list[Path] | dict[str, Any]],
) -> dict[str, Any]:
    rows = latest_gate_rows(gates_path)
    result: dict[str, Any] = {}
    for gate, bundle in bundles.items():
        if isinstance(bundle, Mapping):
            expected = bundle.get("expected_content_sha")
            bundle_mode = str(bundle.get("bundle_mode") or "unknown")
            bundle_errors = list(bundle.get("errors") or [])
            slices = list(bundle.get("slices") or [])
            slice_manifest_sha = bundle.get("slice_manifest_sha")
        else:
            expected = bundle_sha(bundle)
            bundle_mode = "legacy_whole_file"
            bundle_errors = []
            slices = []
            slice_manifest_sha = None
        row = rows.get(gate)
        if not row:
            result[gate] = {
                "state": "legacy_unknown" if not gates_path.is_file() else "missing",
                "source": "none",
                "expected_content_sha": expected,
                "bundle_mode": bundle_mode,
                "bundle_errors": bundle_errors,
                "slices": slices,
                "slice_manifest_sha": slice_manifest_sha,
            }
            continue
        recorded = row.get("approved_content_sha", "")
        status = first_token(row.get("status"), "unknown")
        approved = status in {"valid", "approved"}
        receipt_bundle_mode = (
            row.get("bundle_mode") or "legacy_whole_file"
        )
        receipt_slice_manifest_sha = row.get("slice_manifest_sha") or None
        mode_aligned = ndf_gate_slices.review_slice_mode_aligned(
            receipt_bundle_mode=receipt_bundle_mode,
            expected_bundle_mode=bundle_mode,
            receipt_slice_manifest_sha=receipt_slice_manifest_sha,
            expected_slice_manifest_sha=slice_manifest_sha,
            approved_content_sha=recorded,
            expected_content_sha=expected,
        )
        semantic_complete = bool(
            row.get("phrase") == GATE_PHRASES.get(gate)
            and row.get("approved_by")
            and row.get("approved_at")
            and row.get("source_ref")
        )
        exact = bool(
            semantic_complete
            and
            expected
            and re.fullmatch(r"[0-9a-f]{64}", recorded or "")
            and expected == recorded
            and mode_aligned
        )
        legacy_weak = bool(
            approved
            and expected
            and recorded
            and len(recorded) < 64
            and expected.startswith(recorded)
        )
        state = (
            "bundle_invalid"
            if bundle_errors
            else
            "valid"
            if approved and exact
            else "legacy_weak"
            if legacy_weak
            else "invalidated"
            if approved
            else status
        )
        result[gate] = {
            "state": state,
            "source": "receipt",
            "phrase": row.get("phrase"),
            "approved_by": row.get("approved_by"),
            "approved_at": row.get("approved_at"),
            "approved_content_sha": recorded or None,
            "expected_content_sha": expected,
            "sha_aligned": exact,
            "source_ref": row.get("source_ref") or None,
            "semantic_complete": semantic_complete,
            "bundle_mode": bundle_mode,
            "bundle_errors": bundle_errors,
            "slices": slices,
            "slice_manifest_sha": slice_manifest_sha,
            "receipt_bundle_mode": receipt_bundle_mode,
            "receipt_slice_manifest_sha": receipt_slice_manifest_sha,
            "bundle_mode_aligned": mode_aligned,
        }
    return result


def parse_surface(text: str) -> list[str]:
    raw = header(text, "explore_surface") or section(text, "explore_surface")
    if not raw:
        return []
    items = re.split(r"[,;\n]", raw)
    return sorted(
        {
            re.sub(r"^[-*]\s*", "", item).strip().strip("`")
            for item in items
            if re.sub(r"^[-*]\s*", "", item).strip().strip("`")
        }
    )


def binder_files(topic_dir: Path) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    output: dict[str, Any] = {}
    for name in (*POC_FILES, "GATES.md", "COMMITS.md"):
        path = ndf / name
        output[name] = {
            "path": rel(path),
            "exists": path.is_file(),
            "sha256": file_sha(path),
        }
    evidence = ndf / "evidence"
    output["evidence"] = {
        "path": rel(evidence),
        "exists": evidence.is_dir(),
        "count": len([path for path in evidence.rglob("*") if path.is_file()])
        if evidence.is_dir()
        else 0,
    }
    return output


def implementation_files(topic_dir: Path) -> list[str]:
    files: list[str] = []
    for path in topic_dir.rglob("*"):
        if not path.is_file() or "ndf" in path.relative_to(topic_dir).parts:
            continue
        if path.name == "NOTES.md" or path.suffix.lower() not in CODE_SUFFIXES:
            continue
        files.append(rel(path))
    return sorted(files)


def perf_view(topic: str, topic_dir: Path) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    topic_text = read_text(ndf / "TOPIC.md")
    card_value = header(topic_text, "perf_baseline")
    card = ndf / "PERF_BASELINE.md"
    if card_value:
        raw = card_value.strip().strip("`")
        candidate = topic_dir / raw if not raw.startswith("poc/") else ROOT / raw
        if candidate.is_file():
            card = candidate
    text = read_text(card)
    bind = {
        "vs": header(text, "vs") or header(text, "baseline"),
        "config_id": header(text, "config_id") or header(text, "baseline_id"),
        "measure_script": header(text, "measure_script"),
        "measure_binary": header(text, "measure_binary"),
    }
    numbers = section(text, "Numbers")
    status = first_token(header(text, "status"), "unknown")
    evidence_status = first_token(
        header(text, "evidence_status"), "unknown"
    )
    unverified = status == "unverified" or evidence_status == "unverified"
    pending = (
        not numbers
        or bool(re.search(r"(?i)\bpending\b|\bTBD\b", numbers))
        or unverified
    )
    errors = [f"missing_{key}" for key in ("vs", "config_id", "measure_script") if not bind[key]]
    if not card.is_file():
        errors.insert(0, "missing_perf_baseline")
    return {
        "path": rel(card),
        "exists": card.is_file(),
        "bind": bind,
        "numbers": "pending" if pending else "filled",
        "status": status,
        "evidence_status": evidence_status,
        "unverified": unverified,
        "delta_exists": (ndf / "DELTA.md").is_file(),
        "errors": errors,
    }


def topic_external_checks(topic: str) -> dict[str, dict[str, Any]]:
    return {
        "perf_baseline": run_tool(
            "ndf_perf_baseline.py",
            "check",
            "--topic",
            topic,
        ),
        "isolation": run_tool(
            "ndf_poc_isolation.py",
            "check",
            "--topic",
            topic,
            "--workspace",
            "--report",
            "-",
        ),
        "bindcheck": run_tool(
            "ndf_bindcheck.py",
            "check",
            "--topic",
            topic,
            "--report",
            "-",
        ),
    }


def parsed_tool_issues(name: str, check: dict[str, Any]) -> list[tuple[str, str, str]]:
    output = check.get("output") or ""
    issues: list[tuple[str, str, str]] = []
    if name == "perf_baseline":
        for severity, kind, message in re.findall(
            r"(?m)^\s*\[(error|warning|info)\]\s+([a-z0-9_-]+):\s*(.+)$",
            output,
        ):
            issues.append((severity, kind, message.strip()))
    elif name == "isolation":
        for severity, kind, message in re.findall(
            r"(?m)^-\s+\[(error|warning)\]\s+`([^`]+)`\s+\([^)]*\)\s*(.+)$",
            output,
        ):
            issues.append((severity, kind, message.strip()))
    elif name == "bindcheck":
        for severity, kind, message in re.findall(
            r"(?m)^\|\s*\d+\s*\|\s*(error|warning)\s*\|\s*`([^`]+)`\s*\|[^|]*\|\s*([^|]+)\|",
            output,
        ):
            issues.append((severity, kind, message.strip()))
    if check.get("exit_code") and not any(severity == "error" for severity, _, _ in issues):
        issues.append(("error", f"{name}_failed", clean_markdown(output, 260) or "tool failed"))
    return issues


def external_check_findings(
    topic: str,
    checks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name, check in checks.items():
        for severity, kind, message in parsed_tool_issues(name, check):
            route = finding_route(kind, check_name=name, topic=topic)
            space = (
                "Implementation"
                if name == "isolation"
                else "Test"
                if name == "perf_baseline" or kind in MEASUREMENT_FINDING_KINDS
                else "Design"
            )
            findings.append(
                finding(
                    scope="topic",
                    space=space,
                    kind=kind,
                    severity=severity,
                    evidence=message,
                    repair_owner=route["repair_owner"],
                    repair_task=route["repair_task"],
                    allowed_write_root=route["allowed_write_root"],
                    plane=route.get("plane"),
                    check_name=name,
                    human_gate="人工确认 destructive git disposition"
                    if name == "isolation" and severity == "error"
                    else None,
                )
            )
    return findings


def gate_findings(topic: str, gates: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    topic_dir = POC / topic
    for name, value in gates.items():
        state = value["state"]
        if state == "valid":
            # Keep slice snapshot while aligned so later drift can show diffs.
            approved = value.get("approved_content_sha")
            if approved and value.get("bundle_mode") == "review_slice":
                try:
                    ndf_gate_slices.persist_gate_slice_snapshot(
                        topic_dir,
                        name,
                        approved_content_sha=str(approved),
                    )
                except OSError:
                    pass
            continue
        if state == "legacy_unknown":
            task = "legacy_gate_audit"
        elif state == "invalidated":
            task = "gate_sha_audit"
        else:
            task = "gate_receipt_draft"
        evidence = f"{name} receipt state is {state}"
        drift = None
        if state == "invalidated":
            try:
                drift = ndf_gate_slices.explain_gate_drift(
                    topic_dir,
                    name,
                    approved_content_sha=value.get("approved_content_sha"),
                    expected_content_sha=value.get("expected_content_sha"),
                    write_tmp_report=True,
                )
                changed = drift.get("changed_slices") or []
                if drift.get("diff_unavailable"):
                    evidence = (
                        f"{evidence}; drift_explain=diff_unavailable:"
                        f"{drift.get('diff_unavailable')}"
                    )
                elif changed:
                    ids = ",".join(item.get("slice_id") or "?" for item in changed)
                    evidence = f"{evidence}; changed_slices={ids}"
                if drift.get("report_path"):
                    evidence = f"{evidence}; report={drift.get('report_path')}"
            except Exception:
                drift = None
        item = finding(
            scope="topic",
            space="Design",
            kind=f"gate_{name}_{state}",
            severity="error",
            evidence=evidence,
            repair_owner="openclaw",
            repair_task=task,
            allowed_write_root=f"poc/{topic}/ndf/",
            human_gate=GATE_PHRASES.get(name),
            gate=name,
            plane=PLANE_CONTROL,
        )
        if drift:
            item["gate_drift"] = drift
            item["gate_drift_markdown"] = ndf_gate_slices.format_gate_drift_markdown(
                drift
            )
        findings.append(item)
    return findings


def topic_health_artifact(topic: str) -> Path:
    return HEALTH_DIR / f"topic-{topic}.json"


def latest_topic_health(
    topic: str,
    generation_sha: str,
    *,
    poc_sha: str | None = None,
) -> dict[str, Any] | None:
    payload = read_json_artifact(topic_health_artifact(topic))
    if payload is None:
        return None
    payload = dict(payload)
    current = payload.get("snapshot_sha") == generation_sha
    if poc_sha and payload.get("poc_sha") == poc_sha:
        current = True
    payload["state"] = "current" if current else "stale"
    return payload


def readiness(topic_dir: Path, gates: dict[str, Any], perf: dict[str, Any]) -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    design_gaps = [name for name in ("DESIGN.md", "INTERFACE.md") if not (ndf / name).is_file()]
    impl_files = implementation_files(topic_dir)
    impl_gaps: list[str] = []
    if gates["implementation_approval"]["state"] != "valid":
        impl_gaps.append(f"gate:implementation_approval:{gates['implementation_approval']['state']}")
    if not (ndf / "INTERFACE.md").is_file():
        impl_gaps.append("missing_interface")
    if not impl_files:
        impl_gaps.append("missing_baseline_workspace")
    test_gaps = list(perf["errors"])
    if not perf["delta_exists"]:
        test_gaps.append("missing_delta")
    if perf["numbers"] == "pending":
        test_gaps.append("numbers_pending")
    return {
        "design": {"ready": not design_gaps, "gaps": design_gaps},
        "implementation": {"ready": not impl_gaps, "gaps": impl_gaps, "code_files": impl_files},
        "test": {"ready": not test_gaps, "gaps": test_gaps},
    }


def decorate_spaces(spaces: dict[str, Any]) -> dict[str, Any]:
    for key, purpose in SPACE_PURPOSE.items():
        target = spaces[key]
        target["purpose"] = purpose
        target["clause_refs"] = [dict(item) for item in SPACE_CLAUSE_REFS[key]]
    return spaces


def attach_space_repairs(
    spaces: Mapping[str, Any] | None,
    health: Mapping[str, Any] | None,
    *,
    topic_id: str | None = None,
) -> dict[str, Any]:
    """Attach why/how/command recipes so space cards are not gap-id-only."""
    result: dict[str, Any] = {}
    findings = [
        item for item in (health or {}).get("findings") or [] if isinstance(item, Mapping)
    ]
    actions = [
        item
        for item in (health or {}).get("next_actions") or []
        if isinstance(item, Mapping)
    ]
    finding_by_kind = {str(item.get("kind")): item for item in findings if item.get("kind")}
    action_by_kind = {str(item.get("kind")): item for item in actions if item.get("kind")}
    space_title = {
        "design": "Design",
        "implementation": "Implementation",
        "test": "Test",
    }
    for key, card in (spaces or {}).items():
        if not isinstance(card, Mapping):
            continue
        target = dict(card)
        repairs: list[dict[str, Any]] = []
        for gap in target.get("gaps") or []:
            kind = str(gap)
            finding = finding_by_kind.get(kind) or {}
            action = action_by_kind.get(kind) or {}
            task = str(action.get("task") or finding.get("repair_task") or "")
            if not task and kind in {"missing_baseline_workspace", "no_topic_code"}:
                task = "poc_prepare_baseline"
            if not task and kind in MEASUREMENT_FINDING_KINDS | {"missing_delta"}:
                task = "poc_measurement"
            if not task and kind in {
                "DESIGN.md",
                "INTERFACE.md",
                "missing_design",
                "missing_interface",
                "missing_topic",
            }:
                task = "binder_pipeline"
            label = (
                action.get("label")
                or CONTROL_TASK_LABELS.get(task)
                or (f"修复 {kind}" if kind else "修复缺口")
            )
            if kind in {
                "DESIGN.md",
                "INTERFACE.md",
                "missing_design",
                "missing_interface",
                "missing_topic",
            }:
                label = "OpenClaw: 准备设计文档"
            write_root = (
                action.get("allowed_write_root")
                or finding.get("allowed_write_root")
                or (f"poc/{topic_id}/" if topic_id else None)
            )
            action_id = REPAIR_TASK_ACTION_IDS.get(task)
            if kind in {
                "DESIGN.md",
                "INTERFACE.md",
                "missing_design",
                "missing_interface",
                "missing_topic",
            }:
                action_id = "design-prepare"
            repairs.append(
                {
                    "kind": kind,
                    "why": finding.get("why_blocked")
                    or finding_why_blocked(kind, space_title.get(str(key), str(key))),
                    "fix": SPACE_GAP_FIX.get(kind)
                    or f"使用命令入口「{label}」按 NDF 修复 {kind}。",
                    "actionId": action_id,
                    "label": label,
                    "owner": action.get("owner") or finding.get("repair_owner"),
                    "writeRoot": write_root,
                    "task": task or None,
                }
            )
        target["repairs"] = repairs
        result[str(key)] = target
    return result


def topic_contract_slice(text: str) -> str:
    match = re.search(
        r"<!--\s*ndf:gate-slice\s+begin=topic_contract\s*-->([\s\S]*?)"
        r"<!--\s*ndf:gate-slice\s+end=topic_contract\s*-->",
        text,
    )
    return match.group(1) if match else text


def first_paragraph(text: str, limit: int = 360) -> str:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if chunk.strip()]
    for chunk in chunks:
        if chunk.startswith(">") or chunk.startswith("#") or chunk.startswith("<!--"):
            continue
        return clean_markdown(chunk, limit)
    return clean_markdown(text or "", limit)


def topic_proposal_refs(topic_dir: Path, topic_text: str) -> list[str]:
    refs: list[str] = []
    for path in proposal_paths(topic_text):
        refs.append(rel(path))
    ndf_proposals = topic_dir / "ndf" / "proposals"
    if ndf_proposals.is_dir():
        for path in sorted(ndf_proposals.glob("*.md")):
            refs.append(rel(path))
    for raw in re.findall(r"ndf/proposals/[A-Za-z0-9_.-]+\.md", topic_text):
        candidate = topic_dir / raw
        refs.append(rel(candidate) if candidate.is_file() else f"poc/{topic_dir.name}/{raw}")
    return sorted(set(refs))


def topic_overview(topic_dir: Path, text: str, lifecycle: str) -> dict[str, Any]:
    contract = topic_contract_slice(text)
    summary_source = next(
        (
            candidate
            for candidate in (
                section(contract, "概述"),
                section(contract, "Summary"),
                section(text, "概述"),
                section(text, "Summary"),
                section(contract, "Hypothesis"),
                section(text, "Hypothesis"),
                section(contract, "Active Hypothesis"),
                section(text, "Active Hypothesis"),
            )
            if candidate
        ),
        "",
    )
    active_hypothesis = (
        section(contract, "Active Hypothesis")
        or section(text, "Active Hypothesis")
    )
    hypothesis = (
        header(contract, "active_hypothesis")
        or header(text, "active_hypothesis")
        or first_paragraph(active_hypothesis, 520)
        or first_paragraph(section(contract, "Hypothesis") or section(text, "Hypothesis"))
    )
    summary = first_paragraph(summary_source, 800)
    return {
        "summary": summary or "Not explicitly recorded",
        "purpose": summary or "Not explicitly recorded",
        "hypothesis": clean_markdown(hypothesis or "", 520) or "Not explicitly recorded",
        "explore_surface": parse_surface(contract) or parse_surface(text),
        "idea_sources": {
            "depends_on_topics": [
                re.split(r"\s+", item, 1)[0]
                for item in split_list(
                    header(contract, "depends_on_topics")
                    or header(text, "depends_on_topics")
                )
                if item
            ],
            "proposal_paths": topic_proposal_refs(topic_dir, text),
        },
        "lifecycle": lifecycle,
    }


def findings_by_space(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "Design": [],
        "Implementation": [],
        "Test": [],
    }
    for item in findings:
        space = str(item.get("space") or "Design")
        grouped.setdefault(space, []).append(item)
    return grouped


def is_workflow_meta_node(node: Mapping[str, Any]) -> bool:
    cid = str(node.get("id") or "")
    file = str(node.get("file") or "")
    scope = node.get("scope")
    if scope == "ndf-process":
        return True
    if file.startswith("spec/meta/"):
        return True
    return cid.startswith(
        ("META-", "ADR-META-", "DEF-META-", "DEF-NDF-", "CON-POC-")
    )


def clause_node_summary(node: Mapping[str, Any], *, role: str) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "title": node.get("title"),
        "status": node.get("status") or "unknown",
        "file": node.get("file"),
        "hop": node.get("hop"),
        "role": role,
        "scope": node.get("scope"),
    }


def stable_summary(nodes: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"stable": 0, "draft": 0, "deprecated": 0, "missing": 0, "other": 0}
    for node in nodes:
        status = str(node.get("status") or "missing")
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts


def depends_on_edges(nodes: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    known = {str(node.get("id")) for node in nodes if node.get("id")}
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        source = str(node.get("id") or "")
        for target in (node.get("edges") or {}).get("depends-on") or []:
            if target not in known:
                continue
            key = (source, str(target))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"from": source, "to": str(target), "rel": "depends-on"})
    return edges


def explore_surface_bind(
    surfaces: list[str], product_clauses: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    binds: list[dict[str, Any]] = []
    for surface in surfaces:
        tail = surface.rsplit("/", 1)[-1]
        clauses = [
            str(node.get("id"))
            for node in product_clauses
            if tail and tail in str(node.get("file") or "")
        ]
        binds.append({"surface": surface, "clauses": clauses})
    return binds


def split_context_graph(
    context: Mapping[str, Any],
    surfaces: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = context.get("context_plan") or {}
    graph = plan.get("graph") or {}
    nodes = list(graph.get("nodes") or [])
    seeds = set(plan.get("seed_ids") or [])
    product_nodes = [node for node in nodes if not is_workflow_meta_node(node)]
    meta_nodes = [node for node in nodes if is_workflow_meta_node(node)]
    product_clauses = [
        clause_node_summary(
            node, role="seed" if node.get("id") in seeds else "closure"
        )
        for node in product_nodes
    ]
    meta_clauses = [
        clause_node_summary(
            node, role="seed" if node.get("id") in seeds else "closure"
        )
        for node in meta_nodes
    ]
    foundation = {
        "product_clauses": product_clauses,
        "depends_on_edges": depends_on_edges(product_nodes),
        "stable_summary": stable_summary(product_clauses),
        "explore_surface_bind": explore_surface_bind(surfaces, product_clauses),
    }
    workflow_meta = {
        "nodes": meta_clauses,
        "stable_summary": stable_summary(meta_clauses),
        "spec_health_state": None,
        "note": "流程约束，非产品功能契约",
    }
    return foundation, workflow_meta


def phase_hint(lifecycle: str, gates: dict[str, Any], spaces: dict[str, Any]) -> str:
    return phase_hint_for_decision(lifecycle, gates, spaces, None)


def phase_hint_for_decision(
    lifecycle: str,
    gates: dict[str, Any],
    spaces: dict[str, Any],
    selected_decision: str | None,
) -> str:
    if lifecycle in {"promoted", "rejected", "closed"}:
        return "closed"
    if all(gates[name]["state"] == "legacy_unknown" for name in gates):
        return "legacy_gate_audit"
    if any(gates[name]["state"] == "bundle_invalid" for name in gates):
        return "gate_bundle_invalid"
    if gates["topic_review"]["state"] != "valid":
        return "await_topic_review"
    if gates["design_review"]["state"] != "valid":
        return "await_design_review"
    if gates["implementation_approval"]["state"] != "valid":
        return "await_implementation_approval"
    if selected_decision in CLOSE_DECISIONS:
        return "close_selected"
    if selected_decision in {"continue_exploring", "amend"}:
        return "exploring"
    if selected_decision != "implement":
        return "decision_required"
    if not spaces["implementation"]["ready"]:
        return "implementing"
    if not spaces["test"]["ready"]:
        return "measuring"
    return "close_ready"


def list_poc_completions(topic_dir: Path | None) -> list[dict[str, Any]]:
    if topic_dir is None:
        return []
    evidence = topic_dir / "ndf" / "evidence"
    if not evidence.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in evidence.glob("*.json"):
        data = read_json_artifact(path)
        if not data or data.get("schema") != "ndf-agent-completion/v1":
            continue
        rows.append(dict(data))
    rows.sort(key=lambda item: str(item.get("finished_at") or item.get("started_at") or ""))
    return rows


def has_baseline_copy_marker(topic_dir: Path | None) -> bool:
    if topic_dir is None or not topic_dir.is_dir():
        return False
    for path in topic_dir.rglob("BASELINE_COPY.md"):
        if "ndf" in path.relative_to(topic_dir).parts:
            continue
        return True
    return False


def baseline_prepared(
    topic_dir: Path | None = None,
    *,
    spaces: Mapping[str, Any] | None = None,
    completions: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    """Baseline prep = trunk copy workspace and/or first R0 measurement — not implement."""
    code = (spaces or {}).get("implementation", {}).get("code_files") or []
    if code:
        return True
    if has_baseline_copy_marker(topic_dir):
        return True
    for item in completions or []:
        if str(item.get("task") or "") in BASELINE_PREP_TASKS:
            return True
    return False


def delta_feature_implementation_started(delta_text: str) -> bool:
    body = section(delta_text, "Feature delta") or section(delta_text, "Feature")
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = cells[0].lower().replace(" ", "")
        if first in {"id", ""} or set(cells[0]) <= {"-", " "} or cells[0].startswith("-"):
            continue
        status = cells[-1].lower().strip()
        if status in FEATURE_IMPLEMENTED_STATUSES:
            return True
    return False


def delta_round_beyond_r0(delta_text: str) -> bool:
    latest = latest_delta_round(delta_text)
    round_id = str(latest.get("round") or "")
    match = ROUND_TOKEN_RE.search(round_id)
    if not match:
        return False
    return int(match.group(1)) >= 1


def poc_feature_round_started(
    topic_dir: Path | None = None,
    *,
    spaces: Mapping[str, Any] | None = None,
    delta: Mapping[str, Any] | None = None,
    delta_text: str = "",
    completions: Sequence[Mapping[str, Any]] | None = None,
    evidence_count: int = 0,
) -> bool:
    """True when a DESIGN feature implementation round has started (not baseline prep)."""
    del evidence_count  # baseline/measurement evidence MUST NOT start feature rounds
    for item in completions or []:
        if str(item.get("task") or "") in POC_IMPLEMENTATION_TASKS:
            return True
    text = delta_text or ""
    if text and delta_feature_implementation_started(text):
        return True
    if text and delta_round_beyond_r0(text):
        return True
    # Legacy fallback: explicit R1+ token in projected latest_round snippet only
    latest = str((delta or {}).get("latest_round") or "")
    match = ROUND_TOKEN_RE.search(latest)
    if match and int(match.group(1)) >= 1:
        return True
    return False


def poc_round_started(
    spaces: Mapping[str, Any] | None = None,
    delta: Mapping[str, Any] | None = None,
    evidence_count: int = 0,
    *,
    topic_dir: Path | None = None,
    delta_text: str = "",
    completions: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    """Backward-compatible alias for feature-round detection."""
    return poc_feature_round_started(
        topic_dir,
        spaces=spaces,
        delta=delta,
        delta_text=delta_text,
        completions=completions,
        evidence_count=evidence_count,
    )


def markdown_section_bullets(text: str, title: str) -> list[str]:
    items: list[str] = []
    for line in section(text, title).splitlines():
        match = re.match(r"^\s*[-*]\s+(.+)$", line)
        if match:
            items.append(clean_markdown(match.group(1), 400))
    return [item for item in items if item]


def latest_delta_round(delta_text: str) -> dict[str, Any]:
    body = section(delta_text, "Rounds") or section(delta_text, "Latest Round")
    rows: list[list[str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0].lower().replace(" ", "")
        if first in {"round", ""} or set(cells[0]) <= {"-", " "} or cells[0].startswith("-"):
            continue
        rows.append(cells)
    if not rows:
        return {"round": None, "conclusion": None, "row": None}
    last = rows[-1]
    return {
        "round": last[0],
        "conclusion": last[-1] if last else None,
        "row": " | ".join(last),
    }


def latest_poc_completion(topic_dir: Path) -> tuple[Path | None, dict[str, Any] | None]:
    evidence = topic_dir / "ndf" / "evidence"
    if not evidence.is_dir():
        return None, None
    found: list[tuple[float, Path, dict[str, Any]]] = []
    for path in evidence.glob("*.json"):
        data = read_json_artifact(path)
        if not data or data.get("schema") != "ndf-agent-completion/v1":
            continue
        found.append((path.stat().st_mtime, path, data))
    if not found:
        return None, None
    preferred = [item for item in found if item[1].name.endswith("-completion.json")]
    pool = preferred or found
    pool.sort(key=lambda item: (item[0], str(item[1])))
    _, path, data = pool[-1]
    return path, data


def close_plan_next_work(mode: str, topic_id: str = "<topic>") -> str:
    return (
        f"Run python3 spec/meta/tools/ndf_close.py plan --topic {topic_id} "
        f"--mode {mode} --report tmp/close-plan-{topic_id}-{mode}.md. "
        f"Then python3 spec/meta/tools/ndf_workflow_status.py close-plan "
        f"--topic {topic_id} --mode {mode} --json. Read-only; do not apply close."
    )


def new_poc_next_work(topic_id: str = "<topic>") -> str:
    return (
        f"Draft spec/open/proposal-*.md with track=poc for a sibling topic. "
        f"depends_on_topics MUST include {topic_id}. Scan explore_surface. "
        "Stop at 已确认. MUST NOT amend the current topic_contract or "
        "active_hypothesis. MUST NOT binder_amend TOPIC/DESIGN on the current topic."
    )


def normalize_suggested_paths(raw: Any) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return paths
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        mode = str(item.get("mode") or "")
        route = str(item.get("route") or "").strip()
        if route == NEW_POC_ROUTE or mode == NEW_POC_ROUTE:
            mode = NEW_POC_ROUTE
            route = NEW_POC_ROUTE
        elif mode not in POC_DECISIONS:
            continue
        else:
            route = route or next_work_route(mode)
        rationale = str(item.get("rationale") or "").strip()
        next_work = str(item.get("next_work") or "").strip()
        paths.append(
            {
                "mode": mode,
                "route": route,
                "recommended": bool(item.get("recommended")),
                "label": str(item.get("label") or mode),
                "rationale": rationale,
                "next_work": next_work,
                "prefill": str(item.get("prefill") or rationale),
            }
        )
    return paths


def resolve_briefing_file(topic_dir: Path, path_str: str) -> Path:
    path = Path(path_str)
    if path.is_file():
        return path
    under_root = ROOT / path_str
    if under_root.is_file():
        return under_root
    under_topic = topic_dir / path_str
    if under_topic.is_file():
        return under_topic
    return topic_dir / "ndf" / "evidence" / Path(path_str).name


def next_work_route(mode: str, route: str | None = None) -> str:
    explicit = (route or "").strip()
    if explicit == NEW_POC_ROUTE or mode == NEW_POC_ROUTE:
        return NEW_POC_ROUTE
    if mode in CLOSE_DECISIONS:
        return "close"
    if mode == "amend":
        return "binder"
    if mode in POC_DECISIONS:
        return "delegate_poc"
    raise ValueError(f"unknown decision mode: {mode}")


def _merge_tool_next_work(existing: str, tools: str, token: str) -> str:
    if token in existing:
        return existing
    if existing:
        return f"{existing} {tools}".strip()
    return tools


def next_work_for_mode(
    mode: str,
    briefing: Mapping[str, Any] | None,
    human_text: str,
    topic_id: str | None = None,
) -> dict[str, Any]:
    if mode not in BRIEFING_MODES:
        raise ValueError(f"unknown decision mode: {mode}")
    text = human_text.strip()
    if not text:
        raise ValueError("human decision text is required")
    briefing = briefing or {}
    match = next(
        (
            item
            for item in briefing.get("suggested_paths") or []
            if isinstance(item, Mapping) and item.get("mode") == mode
        ),
        {},
    )
    route = next_work_route(mode, str(match.get("route") or "") or None)
    next_work = str(match.get("next_work") or "").strip()
    topic = (topic_id or "").strip() or "<topic>"
    if route == "close":
        next_work = _merge_tool_next_work(
            next_work, close_plan_next_work(mode, topic), "ndf_close"
        )
    elif route == NEW_POC_ROUTE:
        next_work = _merge_tool_next_work(
            next_work, new_poc_next_work(topic), "spec/open/proposal"
        )
    return {
        "mode": mode,
        "route": route,
        "human_text": text,
        "verdict": briefing.get("verdict"),
        "constraints": list(briefing.get("decision_path") or []),
        "next_work": next_work,
        "recommended": bool(match.get("recommended")) if match else None,
    }


def decision_briefing(
    topic_dir: Path,
    *,
    delta_text: str = "",
) -> dict[str, Any]:
    completion_path, completion = latest_poc_completion(topic_dir)
    nested: dict[str, Any] = {}
    if completion and isinstance(completion.get("decision_briefing"), Mapping):
        nested = dict(completion["decision_briefing"])
    source: dict[str, Any] = {**(completion or {}), **nested}
    round_info = latest_delta_round(delta_text)
    verdict = source.get("verdict") or round_info.get("conclusion")
    summary = source.get("summary")
    raw_path = source.get("decision_path")
    if isinstance(raw_path, str) and raw_path.strip():
        decision_path = [raw_path.strip()]
    elif isinstance(raw_path, list):
        decision_path = [str(item).strip() for item in raw_path if str(item).strip()]
    else:
        decision_path = []
    suggested = normalize_suggested_paths(
        source.get("suggested_paths") or source.get("human_decisions")
    )
    evidence_paths: list[str] = []
    if completion_path is not None:
        evidence_paths.append(rel(completion_path))
    if completion:
        for item in completion.get("evidence_paths") or []:
            path_str = str(item).strip()
            if path_str and path_str not in evidence_paths:
                evidence_paths.append(path_str)
    if not verdict or not decision_path:
        for path_str in list(evidence_paths):
            path = resolve_briefing_file(topic_dir, path_str)
            if path.suffix.lower() != ".md" or not path.is_file():
                continue
            text = read_text(path)
            if not verdict:
                verdict = clean_markdown(section(text, "Verdict"), 400) or verdict
            if not decision_path:
                decision_path = markdown_section_bullets(text, "Decision path")
            if verdict and decision_path:
                break
    topic_id = topic_dir.name
    open_files = [
        {"label": "DELTA", "path": f"poc/{topic_id}/ndf/DELTA.md"},
        {"label": "NOTES", "path": f"poc/{topic_id}/NOTES.md"},
        {"label": "TOPIC", "path": f"poc/{topic_id}/ndf/TOPIC.md"},
    ]
    seen = {item["path"] for item in open_files}
    for path_str in evidence_paths:
        if path_str.endswith((".md", ".json")) and path_str not in seen:
            open_files.append({"label": Path(path_str).name, "path": path_str})
            seen.add(path_str)
    source_kind = (
        "completion"
        if completion
        else "delta"
        if round_info.get("row")
        else None
    )
    return {
        "schema": "ndf-decision-briefing/v1",
        "summary": clean_markdown(str(summary or ""), 800) or None,
        "verdict": clean_markdown(str(verdict or ""), 400) or None,
        "latest_round": round_info.get("round"),
        "latest_round_row": round_info.get("row"),
        "decision_path": decision_path,
        "suggested_paths": suggested,
        "evidence_paths": evidence_paths,
        "open_files": open_files,
        "completion_path": rel(completion_path) if completion_path else None,
        "source": source_kind,
    }


def topic_decision_view(
    text: str,
    lifecycle: str,
    gates: Mapping[str, Mapping[str, Any]],
    *,
    spaces: Mapping[str, Any] | None = None,
    delta: Mapping[str, Any] | None = None,
    delta_text: str = "",
    topic_dir: Path | None = None,
    evidence_count: int = 0,
) -> dict[str, Any]:
    selected = first_token(header(text, "selected_decision"))
    if selected not in POC_DECISIONS:
        selected = None
    open_decision = header(text, "open_decision")
    next_round_focus = header(text, "next_round_focus") or None
    gates_valid = all(
        gates.get(name, {}).get("state") == "valid" for name in GATE_ORDER
    )
    completions = list_poc_completions(topic_dir) if topic_dir else []
    round_started = poc_feature_round_started(
        topic_dir,
        spaces=spaces,
        delta=delta,
        delta_text=delta_text,
        completions=completions,
        evidence_count=evidence_count,
    )
    baseline_ready = baseline_prepared(
        topic_dir,
        spaces=spaces,
        completions=completions,
    )
    blocked: dict[str, str] = {}
    active = lifecycle in {"exploring", "blocked"}
    if active and not gates_valid:
        # Early close ([[BEH-020]]): reject / same-hypothesis amend without
        # three-gate green. Partial close ([[BEH-019]]) is also offered when
        # subset evidence exists — close_eligible / ndf_close plan still gate
        # evidence. Full promote + implement + continue_exploring stay gated.
        for mode in (
            "implement",
            "continue_exploring",
            "promote",
        ):
            blocked[mode] = "gates_not_valid"
    elif gates_valid and active:
        if round_started:
            blocked["implement"] = "feature_round_exists"
        else:
            blocked["continue_exploring"] = "no_feature_round_yet"
    offered = [mode for mode in sorted(POC_DECISIONS) if mode not in blocked]
    if lifecycle in {"promoted", "rejected", "closed"}:
        state = "closed"
    elif selected:
        state = "selected"
    elif gates_valid:
        state = "decision_required"
    else:
        state = "not_ready"
    early_close_allowed = bool(active and state == "not_ready")
    close_offered = bool(
        any(mode in offered for mode in CLOSE_DECISIONS)
        or early_close_allowed
        or state == "decision_required"
    )
    blocked_labels = {
        mode: DECISION_BLOCK_LABELS.get(code, code) for mode, code in blocked.items()
    }
    if (
        blocked.get("continue_exploring") == "no_feature_round_yet"
        and baseline_ready
    ):
        blocked_labels["continue_exploring"] = (
            "基线准备（拷贝+R0）已完成，尚未按 DESIGN 实现"
        )
    return {
        "state": state,
        "selected": selected,
        "open_decision": open_decision,
        "decision_required": state == "decision_required",
        "early_close_allowed": early_close_allowed,
        "close_offered": close_offered,
        "close_requested": selected in CLOSE_DECISIONS,
        # Close projection adds proposal/plan/verification evidence.
        "close_eligible": False,
        "allowed": sorted(POC_DECISIONS),
        "offered": offered,
        "blocked": blocked,
        "blocked_labels": blocked_labels,
        "round_started": round_started,
        "baseline_prepared": baseline_ready,
        "meanings": dict(POC_DECISION_MEANINGS),
        "source": "TOPIC.md:selected_decision" if selected else None,
        "next_round_focus": next_round_focus,
    }


def topic_view(topic_dir: Path, *, mode: str = "full") -> dict[str, Any]:
    ndf = topic_dir / "ndf"
    text = read_text(ndf / "TOPIC.md")
    topic_id = header(text, "topic_id") or header(text, "ndf_topic") or topic_dir.name
    lifecycle = normalize_lifecycle(header(text, "status"))
    active = lifecycle in {"exploring", "blocked"}
    baseline_status = first_token(header(text, "baseline_status"), "unknown")
    bundles = poc_gate_bundle_specs(topic_dir)
    gates = gate_view(ndf / "GATES.md", bundles)
    perf = perf_view(topic_id, topic_dir)
    run_checks = mode != "directory" and active
    checks = (
        topic_external_checks(topic_id)
        if run_checks
        else {
            name: skipped_check(
                "directory row" if mode == "directory" else "topic lifecycle is closed"
            )
            for name in (
                "perf_baseline",
                "isolation",
                "bindcheck",
                "meta_graph",
                "product_graph",
            )
        }
    )
    spec_health_view = latest_spec_health(source_generation_sha()) if run_checks else None
    findings = (
        gate_findings(topic_id, gates) + external_check_findings(topic_id, checks)
        if run_checks
        else gate_findings(topic_id, gates)
    )
    if run_checks:
        checks.update(spec_graph_tool_checks(spec_health_view))
        for item in spec_graph_findings(spec_health_view):
            upsert_finding(findings, item)
    if active and perf["numbers"] == "pending" and not perf.get("unverified"):
        upsert_finding(
            findings,
            finding(
                scope="topic",
                space="Test",
                kind="numbers_pending",
                severity="info",
                evidence="PERF_BASELINE Numbers are pending measurement evidence",
                repair_owner="claude-code",
                repair_task="poc_measurement",
                allowed_write_root=f"poc/{topic_id}/",
            ),
        )
    if active and perf.get("unverified"):
        upsert_finding(
            findings,
            finding(
                scope="topic",
                space="Test",
                kind="unverified_measurement_claim",
                severity="error",
                evidence=(
                    "PERF Numbers lack a verified Claude Code "
                    "run/lease/completion + measurement evidence receipt"
                ),
                repair_owner="claude-code",
                repair_task="poc_measurement",
                allowed_write_root=f"poc/{topic_id}/",
            ),
        )
    spaces = readiness(topic_dir, gates, perf)

    if "missing_baseline_workspace" in spaces["implementation"]["gaps"] or "no_topic_code" in spaces["implementation"]["gaps"]:
        upsert_finding(
            findings,
            finding(
                scope="topic",
                space="Implementation",
                kind="missing_baseline_workspace",
                severity="error",
                evidence=(
                    "Implementation 缺少可测基线工作区：需要先把 INTERFACE 对照切片与 "
                    "Trunk 对照代码拷贝到 poc/<topic>/，形成可 R0 测量的基线。"
                ),
                repair_owner="claude-code",
                repair_task="poc_prepare_baseline",
                allowed_write_root=f"poc/{topic_id}/",
            ),
        )

    for item in findings:
        if not finding_pollutes_business_space(item):
            continue
        target = {
            "Design": spaces["design"],
            "Implementation": spaces["implementation"],
            "Test": spaces["test"],
        }[item["space"]]
        gap = f"{item['kind']}"
        if gap not in target["gaps"]:
            target["gaps"].append(gap)
        target["ready"] = False
    decorate_spaces(spaces)
    binder = binder_files(topic_dir)
    delta_text = read_text(ndf / "DELTA.md")
    delta = {
        "exists": bool(delta_text),
        "path": rel(ndf / "DELTA.md"),
        "feature": clean_markdown(section(delta_text, "Feature"), 180) or None,
        "hotspot": clean_markdown(section(delta_text, "Hotspot"), 180) or None,
        "latest_round": clean_markdown(
            section(delta_text, "Rounds") or section(delta_text, "Latest Round"),
            220,
        )
        or None,
    }
    decision = topic_decision_view(
        text,
        lifecycle,
        gates,
        spaces=spaces,
        delta=delta,
        delta_text=delta_text,
        topic_dir=topic_dir,
        evidence_count=int((binder.get("evidence") or {}).get("count") or 0),
    )
    decision["briefing"] = decision_briefing(topic_dir, delta_text=delta_text)
    spaces["test"]["latest_round"] = delta.get("latest_round")
    spaces["test"]["delta_path"] = delta.get("path") if delta.get("exists") else None
    spaces["test"]["latest_verdict"] = (decision.get("briefing") or {}).get("verdict")
    overview = topic_overview(topic_dir, text, lifecycle)
    hypothesis = (
        header(text, "active_hypothesis")
        or section(text, "Active hypothesis")
        or section(text, "Hypothesis")
    )
    expected_impact = (
        section(text, "Success criteria")
        or section(text, "Expected impact")
        or section(text, "Goal")
    )
    blockers: list[str] = []
    if baseline_status == "stale":
        blockers.append("baseline_stale")
    for name, value in gates.items():
        if value["state"] == "invalidated":
            blockers.append(f"gate_invalidated:{name}")
    blockers.extend(f"perf:{error}" for error in perf["errors"])
    blockers.extend(
        f"{item['space'].lower()}:{item['kind']}"
        for item in findings
        if item["severity"] == "error"
    )
    perf_passed = checks["perf_baseline"]["exit_code"] == 0
    isolation_passed = checks["isolation"]["exit_code"] == 0
    bindcheck_passed = checks.get("bindcheck", {}).get("exit_code") == 0
    graph_blockers = spec_graph_dispatch_blockers(
        spec_health_view, active=active, checks=checks
    )
    product_graph_passed = "product_graphcheck_failed" not in graph_blockers
    meta_graph_passed = "meta_graphcheck_failed" not in graph_blockers
    spec_health_current = "spec_health_stale" not in graph_blockers
    if mode == "full":
        context = context_binding(
            topic=topic_id,
            role="claude-code",
            task="poc_implementation",
            track="poc",
        )
    elif mode == "canvas":
        context = context_binding_for_canvas(topic_id)
    else:
        context = empty_context_binding(topic_id)
    context_valid = bool(context["context_verify"].get("valid"))
    contract_preflight_passed = (
        active
        and gates["implementation_approval"]["state"] == "valid"
        and baseline_status != "stale"
        and spaces["implementation"]["ready"]
        and perf_passed
        and isolation_passed
        and context_valid
    )
    provenance_preflight_passed = bindcheck_passed
    static_preflight_passed = (
        contract_preflight_passed
        and provenance_preflight_passed
        and product_graph_passed
    )
    lease = topic_active_lease(topic_id)
    active_lease_ok, _active_lease = active_isolated_lease_for_topic(topic_id)
    runtime = runtime_status(False)["implementation"]
    # Default snapshot does not probe ACP. Transport unprobed ≠ pipeline down;
    # missing_active_isolated_lease is the Delegate gate, not runtime_unavailable.
    runtime_probed = bool(runtime.get("probe")) or bool(runtime.get("probe_mode"))
    runtime_dispatch_ready, runtime_ready_source = runtime_dispatch_ready_for_topic(
        topic_id, runtime, lease
    )
    workspace_bound = bool(workspace_truth_view(topic_id).get("workspace_bound"))
    safe_to_dispatch = static_preflight_passed and active_lease_ok and workspace_bound
    dispatch_blockers = [
        reason
        for reason in (
            None if active else "topic_lifecycle_closed",
            None
            if gates["implementation_approval"]["state"] == "valid"
            else f"implementation_gate:{gates['implementation_approval']['state']}",
            None if baseline_status != "stale" else "baseline_stale",
            None
            if not (
                "missing_baseline_workspace" in spaces["implementation"]["gaps"]
                or "no_topic_code" in spaces["implementation"]["gaps"]
            )
            else "missing_baseline_workspace",
            None if perf_passed else "perf_check_failed",
            None if isolation_passed else "isolation_check_failed",
            None if bindcheck_passed else "bindcheck_failed",
            None if product_graph_passed else "product_graphcheck_failed",
            None if meta_graph_passed else "meta_graphcheck_failed",
            None if spec_health_current else "spec_health_stale",
            None if context_valid else "context_verify_failed",
            None if active_lease_ok else "missing_active_isolated_lease",
            None if workspace_bound else "workspace_unbound",
            (
                "runtime_unavailable"
                if runtime_probed and not runtime["pipeline_reachable"]
                else None
            ),
            (
                "lease_stale_vs_head"
                if lease and lease_stale_vs_head(lease)
                else None
            ),
            (
                "topic_active_lease"
                if lease and not active_lease_ok and not lease_stale_vs_head(lease)
                else None
            ),
        )
        if reason
    ]
    pipelines = control_pipelines_view(
        topic_id,
        findings,
        lifecycle=lifecycle,
        selected_decision=decision.get("selected"),
    )
    foundation, workflow_meta = split_context_graph(
        context, overview["explore_surface"]
    )
    impl_view = _implementation_dispatch_view(topic_id)
    for extra in impl_view.get("dispatch_blockers_from_send") or []:
        if extra not in dispatch_blockers:
            dispatch_blockers.append(str(extra))
    return {
        "topic_id": topic_id,
        "path": rel(topic_dir),
        "raw_status": header(text, "status"),
        "lifecycle": lifecycle,
        "phase_hint": phase_hint_for_decision(
            lifecycle, gates, spaces, decision["selected"]
        ),
        "gates": gates,
        "spaces": spaces,
        "topic_overview": overview,
        "ndf_foundation": foundation,
        "workflow_meta": workflow_meta,
        "perf": perf,
        "delta": delta,
        "binder": binder,
        "control_pipelines": pipelines,
        "decision": decision,
        "business": {
            "hypothesis": clean_markdown(hypothesis or "", 260) or "Not explicitly recorded",
            "expected_impact": clean_markdown(expected_impact or "", 220) or "Not explicitly recorded",
            "current_evidence": {
                "evidence_files": binder["evidence"]["count"],
                "numbers": perf["numbers"],
                "latest_result": clean_markdown(section(text, "Results") or section(text, "Conclusion"), 220)
                or "No summarized result",
            },
            "next_gate": header(text, "next_gate"),
            "decision": decision,
        },
        "explore_surface": parse_surface(text),
        "depends_on_topics": split_list(header(text, "depends_on_topics")),
        "conflicts_with_topics": split_list(header(text, "conflicts_with_topics")),
        "baseline_status": baseline_status,
        "baseline_trunk_sha": header(text, "baseline_trunk_sha"),
        "agent_run": {
            "provider": "claude-code-acp",
            # Lease presence only — Agents card uses runtime.implementation.status.
            "status": "active" if lease else "idle",
            "state_source": "runtime-lease",
            "run_id": lease.get("run_id") if lease else None,
            "session_id": lease.get("session_id") if lease else None,
            "base_sha": lease.get("base_sha") if lease else None,
            "worktree": lease.get("worktree") if lease else None,
            "lease_stale_vs_head": lease_stale_vs_head(lease) if lease else False,
            "lease": lease,
            **impl_view,
        },
        "delegation": {
            "safe_to_dispatch": safe_to_dispatch,
            "contract_preflight_passed": contract_preflight_passed,
            "provenance_preflight_passed": provenance_preflight_passed,
            "static_preflight_passed": static_preflight_passed,
            "implementation_license": implementation_license(gates),
            "poc_dispatch_hard_passed": bool(
                implementation_license(gates).get("ok")
                and isolation_passed
                and context_valid
                and workspace_bound
            ),
            "active_isolated_lease": active_lease_ok,
            "lease_stale_vs_head": lease_stale_vs_head(lease) if lease else False,
            "runtime_dispatch_ready": runtime_dispatch_ready,
            "runtime_dispatch_ready_source": runtime_ready_source,
            "safe_to_delegate_control": not any(
                value["state"] == "invalidated" for value in gates.values()
            ),
            "perf_check_passed": perf_passed,
            "isolation_passed": isolation_passed,
            **context,
            "dispatch_blockers": dispatch_blockers,
            "evaluated_at": now_iso(),
            **impl_view,
        },
        "traceability": [
            {
                "goal_or_clause": surface,
                "design": "DESIGN+INTERFACE"
                if binder["DESIGN.md"]["exists"] and binder["INTERFACE.md"]["exists"]
                else "design gaps",
                "code_or_commit": ", ".join(spaces["implementation"]["code_files"][:3])
                or "no topic code",
                "verification": (
                    "Numbers filled" if perf["numbers"] == "filled" else "Numbers pending"
                ),
            }
            for surface in parse_surface(text)
        ],
        "health": {
            "blockers": sorted(set(blockers)),
            "conflicts": [],
            "stale": baseline_status == "stale",
            "checks": {name: public_check(check) for name, check in checks.items()},
            "findings": findings,
            "findings_by_space": findings_by_space(findings),
            "next_actions": unique_actions(findings),
        },
    }


def closed_leftover_topic_ids() -> set[str]:
    """Topics already rejected in archive or product DEC, even if live TOPIC still exploring."""
    ids: set[str] = set()
    archive = SPEC / "archive"
    if archive.is_dir():
        for topic_md in archive.glob("**/poc-*/ndf/TOPIC.md"):
            folder = topic_md.parent.parent.name
            if not folder.startswith("poc-"):
                continue
            topic_id = folder[len("poc-") :]
            status = normalize_lifecycle(header(read_text(topic_md), "status"))
            if status == "rejected":
                ids.add(topic_id)
    decisions = SPEC / "decisions"
    if decisions.is_dir():
        for path in decisions.glob("*.md"):
            for match in re.finditer(
                r"(?im)^>\s*Rejects:\s*([a-z0-9-]+)\b",
                read_text(path),
            ):
                ids.add(match.group(1))
    return ids


def is_active_topic_view(view: dict[str, Any], leftover_ids: set[str] | None = None) -> bool:
    closed = leftover_ids if leftover_ids is not None else closed_leftover_topic_ids()
    return view["lifecycle"] in {"exploring", "blocked"} and view["topic_id"] not in closed


def active_poc_topic_ids() -> list[str]:
    """Topic ids shown on Topics: exploring or blocked, excluding archived leftovers."""
    if not POC.is_dir():
        return []
    leftover = closed_leftover_topic_ids()
    ids: list[str] = []
    for topic_dir in sorted(POC.iterdir()):
        topic_md = topic_dir / "ndf" / "TOPIC.md"
        if not topic_dir.is_dir() or not topic_md.is_file():
            continue
        text = read_text(topic_md)
        lifecycle = normalize_lifecycle(header(text, "status"))
        if lifecycle not in {"exploring", "blocked"}:
            continue
        topic_id = (
            header(text, "topic_id")
            or header(text, "ndf_topic")
            or topic_dir.name
        )
        if topic_id in leftover:
            continue
        ids.append(topic_id)
    return ids


def list_topic_views(*, mode: str = "directory") -> list[dict[str, Any]]:
    if not POC.is_dir():
        return []
    leftover = closed_leftover_topic_ids()
    views = []
    for topic_dir in sorted(POC.iterdir()):
        if not topic_dir.is_dir() or not (topic_dir / "ndf" / "TOPIC.md").is_file():
            continue
        text = read_text(topic_dir / "ndf" / "TOPIC.md")
        lifecycle = normalize_lifecycle(header(text, "status"))
        if lifecycle not in {"exploring", "blocked"}:
            continue
        view = topic_view(topic_dir, mode=mode)
        if view["topic_id"] in leftover:
            continue
        views.append(view)
    attach_surface_conflicts(views)
    return views


def attach_surface_conflicts(views: list[dict[str, Any]]) -> None:
    leftover = closed_leftover_topic_ids()
    active = [v for v in views if is_active_topic_view(v, leftover)]
    for index, left in enumerate(active):
        left_surface = set(left["explore_surface"])
        for right in active[index + 1 :]:
            overlap = sorted(left_surface & set(right["explore_surface"]))
            if not overlap:
                continue
            finding = {"topic": right["topic_id"], "surface": overlap}
            reverse = {"topic": left["topic_id"], "surface": overlap}
            left["health"]["conflicts"].append(finding)
            right["health"]["conflicts"].append(reverse)


def iter_open_proposal_paths() -> list[Path]:
    return list((SPEC / "open").glob("*.md")) + list((META / "open").glob("proposal-meta-*.md"))


def proposal_plane_for_path(path: Path) -> str:
    return "process" if path.is_relative_to(META) else "product"


def proposal_is_reviewed(status: str | None, reviewed_header: str | None = None) -> bool:
    status_text = status or ""
    if re.search(r"已审核", status_text):
        return True
    if re.fullmatch(r"(?i)\s*(reviewed|approved|已审核)\s*", status_text):
        return True
    return bool(
        re.fullmatch(
            r"(?i)\s*(true|yes|reviewed|approved|已审核)\s*",
            reviewed_header or "",
        )
    )


def classify_process_hop(
    status: str | None, reviewed: bool = False
) -> tuple[str, str | None]:
    normalized = (status or "").lower()
    if "rejected" in normalized or "superseded" in normalized:
        return PROCESS_HOP_DONE, None
    if "implemented" in normalized:
        if reviewed:
            return PROCESS_HOP_DONE, None
        return PROCESS_HOP_REVIEW, "已审核"
    return PROCESS_HOP_CONFIRM, "已确认"


def proposal_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def focused_process_hop(proposals: list[dict[str, Any]]) -> dict[str, Any] | None:
    pending: list[dict[str, Any]] = []
    for proposal in proposals:
        if proposal.get("control_flow") != "managed":
            continue
        hop = proposal.get("hop")
        if hop not in {PROCESS_HOP_CONFIRM_LAND, PROCESS_HOP_MANAGED_REVIEW}:
            continue
        pending.append(dict(proposal))
    if not pending:
        return None
    actionable = [item for item in pending if item.get("actionable")]
    pool = actionable or pending
    focused = max(pool, key=lambda item: float(item.get("mtime") or 0))
    return {
        "focused_path": focused["path"],
        "title": focused["title"],
        "hop": focused["hop"],
        "next_human_phrase": focused.get("next_human_phrase"),
        "remaining": len(pending),
    }


def proposal_contract_sha(text: str) -> str:
    """Hash the immutable proposal contract, excluding status/receipt bookkeeping."""
    contract = re.split(r"(?im)^##\s+Control receipts\s*$", text, maxsplit=1)[0]
    lines = [
        line.rstrip()
        for line in contract.splitlines()
        if not re.match(r"(?i)^>\s*(status|reviewed)\s*:", line)
    ]
    return hashlib.sha256(("\n".join(lines).rstrip() + "\n").encode("utf-8")).hexdigest()


def process_proposal_receipts(text: str) -> list[dict[str, str]]:
    body = section(text, "Control receipts")
    if not body:
        return []
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if headers is None:
            headers = [cell.lower() for cell in cells]
            continue
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


def managed_process_lifecycle(
    text: str,
    status: str,
) -> tuple[str, str | None, str | None, bool, list[dict[str, str]]]:
    proposal_id = header(text, "proposal-id")
    flow_id = header(text, "flow-id") or proposal_id
    contract_sha = proposal_contract_sha(text)
    receipts = process_proposal_receipts(text)

    def valid_receipt(event: str, phrase: str, hop: str) -> bool:
        return any(
            row.get("event") == event
            and row.get("phrase") == phrase
            and row.get("actor", "").lower()
            not in {
                "",
                "agent",
                "openclaw",
                "canvas",
                "tool",
                "project-control",
                "claude-code",
            }
            and row.get("proposal_sha") == contract_sha
            and row.get("flow_id") == flow_id
            and row.get("hop") == hop
            and row.get("status", "").lower() in {"valid", "approved"}
            for row in receipts
        )

    normalized = status.lower()
    if "rejected" in normalized:
        return "rejected", None, None, False, receipts
    if "superseded" in normalized:
        return "superseded", None, None, False, receipts
    reviewed = valid_receipt("proposal.reviewed", "已审核", "review")
    confirmed = valid_receipt(
        "proposal.confirmed", "已确认", "confirm_land"
    )
    if reviewed and confirmed and "implemented" in normalized:
        return "reviewed", None, None, False, receipts
    if confirmed and "implemented" in normalized:
        return (
            "implemented_pending_review",
            PROCESS_HOP_MANAGED_REVIEW,
            "已审核",
            False,
            receipts,
        )
    if confirmed:
        return (
            "confirmed_pending_land",
            PROCESS_HOP_CONFIRM_LAND,
            "已审核",
            True,
            receipts,
        )
    return (
        "pending_confirmation",
        PROCESS_HOP_CONFIRM,
        "已确认",
        False,
        receipts,
    )


def legacy_process_lifecycle(status: str, reviewed: bool) -> str:
    normalized = status.lower()
    if "rejected" in normalized:
        return "legacy_rejected_unbound"
    if "superseded" in normalized:
        return "legacy_superseded_unbound"
    if "implemented" in normalized and reviewed:
        return "legacy_reviewed_unbound"
    if "implemented" in normalized:
        return "legacy_implemented_unbound"
    return "legacy_pending_unknown"


def proposal_record(path: Path) -> dict[str, Any]:
    text = read_text(path)
    track = header(text, "track")
    status = header(text, "Status") or header(text, "status") or "unknown"
    reviewed = proposal_is_reviewed(status, header(text, "reviewed"))
    control_flow = first_token(header(text, "control-flow"), "")
    proposal_id = header(text, "proposal-id")
    flow_id = header(text, "flow-id") or proposal_id
    land_targets = [
        value.strip()
        for value in (header(text, "land-targets") or "").split(",")
        if value.strip()
    ]
    if proposal_plane_for_path(path) == "process" and control_flow == "managed":
        lifecycle, hop, phrase, actionable, receipts = managed_process_lifecycle(
            text, status
        )
    elif proposal_plane_for_path(path) == "process":
        lifecycle = legacy_process_lifecycle(status, reviewed)
        hop, phrase, actionable, receipts = None, None, False, []
    else:
        lifecycle = status.lower()
        hop, phrase = classify_process_hop(status, reviewed)
        actionable, receipts = False, []
    title = next(
        (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("#")),
        path.name,
    )
    return {
        "path": rel(path),
        "title": title,
        "track": track,
        "status": status,
        "plane": proposal_plane_for_path(path),
        "reviewed": reviewed,
        "control_flow": control_flow or None,
        "proposal_id": proposal_id,
        "flow_id": flow_id,
        "proposal_sha": proposal_contract_sha(text),
        "content_sha": file_sha(path),
        "land_targets": land_targets,
        "lifecycle": lifecycle,
        "actionable": actionable,
        "receipts": receipts,
        "hop": hop,
        "next_human_phrase": phrase,
        "mtime": proposal_mtime(path),
    }


def proposal_plane_warnings() -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for path in sorted(iter_open_proposal_paths()):
        record = proposal_record(path)
        token = first_token(record["track"])
        plane = record["plane"]
        if plane == "product" and token == "process":
            warnings.append(
                {
                    "kind": "proposal_plane_misfile",
                    "severity": "warning",
                    "path": record["path"],
                    "plane": plane,
                    "track": record["track"],
                    "message": (
                        f"{record['path']} is under spec/open/ but track={record['track']!r}; "
                        "classified as product"
                    ),
                }
            )
        elif plane == "process" and record["track"] and token != "process":
            warnings.append(
                {
                    "kind": "proposal_plane_misfile",
                    "severity": "warning",
                    "path": record["path"],
                    "plane": plane,
                    "track": record["track"],
                    "message": (
                        f"{record['path']} is under spec/meta/open/ but track={record['track']!r}; "
                        "classified as process"
                    ),
                }
            )
    return warnings


FIXED_MODULE_PREFIXES = (
    "00-charter/",
    "10-architecture/",
    "20-behavior/",
    "30-interfaces/",
    "40-constraints/",
    "50-verification/",
    "decisions/",
    "models/",
)
CLAUSE_ANCHOR_RE = re.compile(r"\{#([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\}")
NDF_META_LINE_RE = re.compile(r"<!--\s*ndf:\s*(.*?)\s*-->")
NDF_STATUS_RE = re.compile(r"\bstatus\s*=\s*([A-Za-z0-9_-]+)")


def draft_map_dir() -> Path:
    return META / "open" / "draft-map"


def iter_fixed_module_draft_clauses() -> list[dict[str, Any]]:
    """Product-tree clauses in the 8 fixed modules with status=draft."""
    drafts: list[dict[str, Any]] = []
    if not SPEC.is_dir():
        return drafts
    for path in sorted(SPEC.rglob("*.md")):
        try:
            rel = path.relative_to(SPEC).as_posix()
        except ValueError:
            continue
        if not rel.startswith(FIXED_MODULE_PREFIXES):
            continue
        if path.name in {"INDEX.md", "README.md"}:
            continue
        lines = read_text(path).splitlines()
        for index, line in enumerate(lines):
            anchor = CLAUSE_ANCHOR_RE.search(line)
            if not anchor:
                continue
            clause_id = anchor.group(1)
            status = ""
            for look in lines[index + 1 : index + 7]:
                meta = NDF_META_LINE_RE.search(look)
                if not meta:
                    if look.strip() == "" or look.startswith(">"):
                        continue
                    break
                match = NDF_STATUS_RE.search(meta.group(1))
                if match:
                    status = match.group(1)
                    break
            if status.lower() != "draft":
                continue
            drafts.append(
                {
                    "clause_id": clause_id,
                    "path": f"spec/{rel}",
                    "line": index + 1,
                }
            )
    return drafts


def load_draft_map_clause_ids() -> set[str]:
    mapped: set[str] = set()
    root = draft_map_dir()
    if not root.is_dir():
        return mapped
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if path.name == "README.md" or rel.startswith("archive/"):
            continue
        clause_id = header(read_text(path), "clause_id")
        if clause_id:
            mapped.add(clause_id.strip())
    return mapped


def draft_map_warnings() -> list[dict[str, Any]]:
    """Warn when a fixed-module draft clause has no concurrent mapping row."""
    mapped = load_draft_map_clause_ids()
    warnings: list[dict[str, Any]] = []
    for item in iter_fixed_module_draft_clauses():
        if item["clause_id"] in mapped:
            continue
        warnings.append(
            {
                "kind": "missing_draft_map_entry",
                "severity": "warning",
                "clause_id": item["clause_id"],
                "path": item["path"],
                "line": item["line"],
                "message": (
                    f"{item['clause_id']} in {item['path']}:{item['line']} has "
                    "status=draft but no spec/meta/open/draft-map/ row"
                ),
            }
        )
    return warnings


def scan_proposals() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    product: list[dict[str, Any]] = []
    process: list[dict[str, Any]] = []
    for path in sorted(iter_open_proposal_paths()):
        record = proposal_record(path)
        normalized = (record["status"] or "").lower()
        if not record["track"] and "proposal" not in path.name:
            continue
        if record["plane"] == "process":
            process.append(record)
            continue
        if "implemented" in normalized or "rejected" in normalized or "superseded" in normalized:
            continue
        product.append(record)
    return product, process


def scan_product_proposals() -> list[dict[str, Any]]:
    return scan_proposals()[0]


def scan_process_proposals() -> list[dict[str, Any]]:
    return scan_proposals()[1]


def close_proposal_records(topic_id: str, topic_path: str) -> list[dict[str, Any]]:
    paths = (
        list((SPEC / "open").glob("*.md"))
        + list((SPEC / "archive").glob("**/*.md"))
        + list((ROOT / topic_path / "ndf" / "proposals").glob("*.md"))
    )
    records: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        text = read_text(path)
        explicit = " ".join(
            value
            for value in (
                path.name,
                header(text, "Topic"),
                header(text, "Subject"),
                header(text, "Rejects"),
                header(text, "Promotes"),
                header(text, "source"),
                "\n".join(text.splitlines()[:12]),
            )
            if value
        )
        if topic_id not in explicit:
            continue
        track = first_token(header(text, "track"))
        rejects = header(text, "Rejects")
        if track not in {"promote", "partial", "rollback", "poc", "bug", "unknown"} and rejects != topic_id:
            continue
        status = header(text, "Status") or header(text, "status") or "unknown"
        reviewed_header = header(text, "reviewed")
        reviewed = bool(
            re.fullmatch(r"(?i)\s*(reviewed|approved|已审核)\s*", status)
            or re.fullmatch(r"(?i)\s*(true|yes|reviewed|approved|已审核)\s*", reviewed_header or "")
        )
        records.append(
            {
                "path": rel(path),
                "track": track,
                "mode": "reject" if rejects == topic_id else ("partial" if track == "partial" else "promote"),
                "status": status,
                "implemented": "implemented" in status.lower(),
                "reviewed": reviewed,
            }
        )
    return records


def _legacy_close_projection(views: list[dict[str, Any]]) -> dict[str, Any]:
    """Permanently quarantined pre-receipt projection.

    Kept only as an explicit tripwire for downstream imports. No caller may
    recover green state from NOTES or bare tmp report existence.
    """
    del views
    raise RuntimeError(
        "legacy close projection is quarantined; use evidence-bound close_projection"
    )

    # Unreachable historical implementation retained temporarily for forensic
    # source review. The tripwire above is covered by a regression test.
    topics: list[dict[str, Any]] = []
    for view in views:
        topic_id = view["topic_id"]
        topic_path = view["path"]
        topic_dir = ROOT / topic_path
        notes_text = read_text(topic_dir / "NOTES.md")
        notes_evidence = bool(
            section(notes_text, "Results")
            or section(notes_text, "Conclusion")
            or re.search(r"(?im)^##\s+R\d+\s+结果", notes_text)
        )
        evidence_ready = bool(
            view["business"]["current_evidence"]["evidence_files"]
            or view["perf"]["numbers"] == "filled"
            or notes_evidence
        )
        proposals = close_proposal_records(topic_id, topic_path)
        proposal_ready = any(record["reviewed"] for record in proposals)
        lifecycle = view["lifecycle"]
        finalized = lifecycle in {"promoted", "rejected", "closed"}
        close_plan_reports = sorted(
            (ROOT / "tmp").glob(f"close-plan-{topic_id}-*.md"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        close_plan_report = close_plan_reports[0] if close_plan_reports else None
        close_plan_ready = bool(close_plan_report and read_text(close_plan_report).strip())
        graph_report = ROOT / "tmp" / f"graphcheck-after-close-{topic_id}.md"
        graph_text = read_text(graph_report)
        graph_green = bool(
            graph_report.is_file()
            and re.search(r"(?i)summary:\s*0\s+error", graph_text)
        )
        verification_report = ROOT / "tmp" / f"verification-after-close-{topic_id}.json"
        verification_data: dict[str, Any] = {}
        if verification_report.is_file():
            try:
                verification_data = json.loads(read_text(verification_report))
            except json.JSONDecodeError:
                verification_data = {}
        verification_green = verification_data.get("state") == "green"

        blockers = list(view["health"]["blockers"])
        if not evidence_ready:
            blockers.append("close:evidence_missing")
        if not proposal_ready and not finalized:
            blockers.append("close:reviewed_proposal_missing")

        steps = [
            {
                "id": "evidence",
                "plane": "Business",
                "label": "POC evidence ready",
                "status": "completed" if evidence_ready else "pending",
                "source": "binder/evidence/NOTES",
            },
            {
                "id": "proposal",
                "plane": "Control",
                "label": "Promote/reject proposal reviewed",
                "status": "completed" if proposal_ready or finalized else "pending",
                "source": proposals[0]["path"] if proposals else None,
            },
            {
                "id": "plan",
                "plane": "Control",
                "label": "Read-only close plan generated",
                "status": "completed" if close_plan_ready else "pending",
                "source": rel(close_plan_report) if close_plan_report else None,
            },
            {
                "id": "integrate",
                "plane": "Runtime",
                "label": "Integration/reject code disposition completed",
                "status": "completed" if finalized else "pending",
                "source": None,
            },
            {
                "id": "graph",
                "plane": "Control",
                "label": "Index and graphcheck green",
                "status": "completed" if graph_green else "pending",
                "source": rel(graph_report) if graph_report.is_file() else None,
            },
            {
                "id": "verify",
                "plane": "Business",
                "label": "Build, performance and golden verified",
                "status": "completed" if verification_green else "pending",
                "source": rel(verification_report) if verification_report.is_file() else None,
            },
            {
                "id": "finalize",
                "plane": "Control",
                "label": "Binder and archive finalized",
                "status": "completed" if finalized else "pending",
                "source": topic_path,
            },
        ]

        branches: dict[str, Any] = {}
        for mode in ("promote", "partial", "reject"):
            mode_proposals = [
                record
                for record in proposals
                if record["mode"] == mode
                or (mode == "partial" and record["mode"] == "promote")
            ]
            mode_proposal_ready = any(record["reviewed"] for record in mode_proposals)
            plan_report = ROOT / "tmp" / f"close-plan-{topic_id}-{mode}.md"
            plan_ready = plan_report.is_file() and bool(read_text(plan_report).strip())
            branch_finalized = (
                lifecycle == "rejected" if mode == "reject" else lifecycle == "promoted"
            )
            branch_steps = [
                {
                    "id": "evidence",
                    "plane": "Business",
                    "label": "POC evidence ready",
                    "status": "completed" if evidence_ready else "pending",
                    "source": "binder/evidence/NOTES",
                },
                {
                    "id": "proposal",
                    "plane": "Control",
                    "label": f"{mode} proposal reviewed",
                    "status": "completed"
                    if mode_proposal_ready or branch_finalized
                    else "pending",
                    "source": mode_proposals[0]["path"] if mode_proposals else None,
                },
                {
                    "id": "plan",
                    "plane": "Control",
                    "label": f"Read-only {mode} close plan",
                    "status": "completed" if plan_ready or branch_finalized else "pending",
                    "source": rel(plan_report) if plan_report.is_file() else None,
                },
                {
                    "id": "integrate",
                    "plane": "Runtime",
                    "label": "Code integration"
                    if mode != "reject"
                    else "Reject code disposition",
                    "status": "completed" if branch_finalized else "pending",
                    "source": None,
                },
                {
                    "id": "graph",
                    "plane": "Control",
                    "label": "Index and graphcheck green",
                    "status": "completed" if graph_green or branch_finalized else "pending",
                    "source": rel(graph_report) if graph_report.is_file() else None,
                },
            ]
            if mode != "reject":
                branch_steps.append(
                    {
                        "id": "verify",
                        "plane": "Business",
                        "label": "Build, performance and golden verified",
                        "status": "completed"
                        if verification_green or branch_finalized
                        else "pending",
                        "source": rel(verification_report)
                        if verification_report.is_file()
                        else None,
                    }
                )
            pre_finalize_green = all(
                item["status"] == "completed" for item in branch_steps
            )
            branch_steps.append(
                {
                    "id": "finalize",
                    "plane": "Control",
                    "label": "Binder and archive finalized",
                    "status": "completed" if branch_finalized else "pending",
                    "source": topic_path,
                }
            )
            branches[mode] = {
                "mode": mode,
                "proposal_ready": mode_proposal_ready,
                "close_plan_ready": plan_ready,
                "verification_required": mode != "reject",
                "finalization_ready": pre_finalize_green and not branch_finalized,
                "finalized": branch_finalized,
                "steps": branch_steps,
                "next_step": next(
                    (
                        item["id"]
                        for item in branch_steps
                        if item["status"] != "completed"
                    ),
                    "closed",
                ),
            }

        next_step = next(
            (step["id"] for step in steps if step["status"] != "completed"),
            "closed",
        )
        topics.append(
            {
                "topic_id": topic_id,
                "lifecycle": lifecycle,
                "evidence_ready": evidence_ready,
                "proposal_ready": proposal_ready,
                "proposals": proposals,
                "close_plan": {
                    "state": "generated" if close_plan_ready else "unknown",
                    "ready": close_plan_ready or finalized,
                    "source": rel(close_plan_report) if close_plan_report else None,
                },
                "graphcheck": {
                    "state": "green" if graph_green else "unknown",
                    "source": rel(graph_report) if graph_report.is_file() else None,
                },
                "verification": {
                    "state": "green" if verification_green else "unknown",
                    "source": rel(verification_report)
                    if verification_report.is_file()
                    else None,
                },
                "finalization_ready": any(
                    branch["finalization_ready"] for branch in branches.values()
                ),
                "branches": branches,
                "steps": steps,
                "next_step": next_step,
                "blockers": sorted(set(blockers)),
            }
        )
    return {
        "state_source": "tree/git/tool-evidence",
        "topics": topics,
    }


def _close_receipt_path(topic: str, mode: str, step: str) -> Path:
    return CLOSE_EVIDENCE_DIR / topic / mode / f"{step}.json"


def close_command_allowed(step: str, command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or any(any(char in token for char in ";&|><") for token in tokens):
        return False
    executable = Path(tokens[0]).name
    arguments = tokens[1:]
    script = executable
    script_token = tokens[0]
    if executable in {"python", "python3", "bash", "sh"}:
        if not arguments or arguments[0].startswith("-"):
            return False
        script_token = arguments[0]
        script = Path(script_token).name
        arguments = arguments[1:]
    candidate = Path(script_token)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve(strict=False)
    registered = {
        "ndf_close.py": (ROOT / "spec/meta/tools/ndf_close.py").resolve(),
        "ndf_graphcheck.py": (ROOT / "spec/meta/tools/ndf_graphcheck.py").resolve(),
        "ndf_index.py": (ROOT / "spec/meta/tools/ndf_index.py").resolve(),
        "ndf_perf_baseline.py": (
            ROOT / "spec/meta/tools/ndf_perf_baseline.py"
        ).resolve(),
        "ndf_workflow_status.py": (
            ROOT / "spec/meta/tools/ndf_workflow_status.py"
        ).resolve(),
        "run_sustained.sh": (ROOT / "scripts/run_sustained.sh").resolve(),
    }
    if registered.get(script) != candidate:
        return False
    if step == "plan":
        return script == "ndf_close.py" and arguments[:1] == ["plan"]
    if step == "integrate":
        return (
            script == "ndf_workflow_status.py"
            and arguments[:1] == ["completion-record"]
        )
    if step == "graph":
        return script in {"ndf_graphcheck.py", "ndf_index.py"}
    if step == "verify":
        return script in {
            "run_sustained.sh",
            "ndf_perf_baseline.py",
        }
    if step == "finalize":
        return (
            script == "ndf_workflow_status.py"
            and arguments[:1] == ["topic-health"]
        )
    return False


def verify_close_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_topic: str | None = None,
    expected_mode: str | None = None,
    expected_step: str | None = None,
) -> dict[str, Any]:
    validation = validate_receipt(receipt)
    errors = list(validation["errors"])
    topic = expected_topic or receipt.get("topic")
    mode = expected_mode or receipt.get("mode")
    step = expected_step or receipt.get("step")
    for field, expected in (("topic", topic), ("mode", mode), ("step", step)):
        if expected is not None and receipt.get(field) != expected:
            errors.append(f"mismatch:{field}")
    accepted_tasks = {"close", str(step), f"close_{step}", f"close-{step}"}
    if receipt.get("task") not in accepted_tasks:
        errors.append("mismatch:task")
    command = str(receipt.get("command") or "")
    if not close_command_allowed(str(step), command):
        errors.append("command_not_allowed")
    if receipt.get("repo_head") != git_head():
        errors.append("stale:repo_head")
    generation = source_generation_sha()
    if receipt.get("source_generation_sha") != generation:
        errors.append("stale:source_generation_sha")
    plan_sha = receipt.get("context_plan_sha")
    current_plan_sha = None
    current_manifest_sha = None
    if plan_sha:
        context = context_binding(
            topic=str(topic) if topic else None,
            role="openclaw",
            task=str(mode or "close"),
            track=str(mode or "poc"),
        )
        current_plan_sha = context["plan_sha"]
        current_manifest_sha = context.get("manifest_sha")
        if not context["context_verify"].get("valid") or plan_sha != current_plan_sha:
            errors.append("stale:context_plan_sha")
        if receipt.get("manifest_sha") != current_manifest_sha:
            errors.append("stale:manifest_sha")
    if receipt.get("result") not in {"passed", "success", "completed"}:
        errors.append("result_not_green")
    missing_paths = [
        path
        for path in receipt.get("evidence_paths", [])
        if not isinstance(path, str) or not (ROOT / path).is_file()
    ]
    if missing_paths:
        errors.append("missing:evidence_paths")
    evidence_validation = validate_evidence_bundle(receipt, root=ROOT)
    errors.extend(evidence_validation["errors"])
    return {
        "schema": "ndf-close-receipt-verification/v1",
        "valid": not errors,
        "errors": sorted(set(errors)),
        "topic": topic,
        "mode": mode,
        "step": step,
        "repo_head": git_head(),
        "source_generation_sha": generation,
        "context_plan_sha": current_plan_sha,
        "manifest_sha": current_manifest_sha,
        "evidence_bundle": evidence_validation,
    }


def close_receipt_view(topic: str, mode: str, step: str) -> dict[str, Any]:
    path = _close_receipt_path(topic, mode, step)
    if path.is_file():
        data = read_json_artifact(path)
        verification = (
            verify_close_receipt(
                data or {},
                expected_topic=topic,
                expected_mode=mode,
                expected_step=step,
            )
        )
        return {
            "state": "verified" if verification["valid"] else "invalid",
            "ready": verification["valid"],
            "source": rel(path),
            "verification": verification,
        }
    legacy_patterns = {
        "plan": f"close-plan-{topic}-{mode}.md",
        "graph": f"graphcheck-after-close-{topic}.md",
        "verify": f"verification-after-close-{topic}.json",
    }
    legacy = ROOT / "tmp" / legacy_patterns[step] if step in legacy_patterns else None
    return {
        "state": "legacy_unbound" if legacy and legacy.is_file() else "missing",
        "ready": False,
        "source": rel(legacy) if legacy and legacy.is_file() else None,
        "verification": None,
    }


def close_projection(views: list[dict[str, Any]]) -> dict[str, Any]:
    """Project Close conservatively from binder truth and bound receipts."""
    topics: list[dict[str, Any]] = []
    for view in views:
        topic_id = view["topic_id"]
        lifecycle = view["lifecycle"]
        decision = dict(view.get("decision") or {})
        selected_decision = decision.get("selected")
        proposals = close_proposal_records(topic_id, view["path"])
        binder = view["binder"]
        binder_minimum = all(
            binder[name]["exists"]
            for name in ("TOPIC.md", "DESIGN.md", "PERF_BASELINE.md", "DELTA.md", "INTERFACE.md")
        )
        perf_full = (
            view["health"]["checks"]["perf_baseline"]["state"] == "passed"
            and view["perf"]["numbers"] == "filled"
            and view["perf"]["delta_exists"]
            and binder["evidence"]["count"] > 0
            and binder_minimum
        )
        notes_only = bool(read_text(ROOT / view["path"] / "NOTES.md"))
        branches: dict[str, Any] = {}
        for mode in ("promote", "partial", "reject"):
            mode_proposals = [record for record in proposals if record["mode"] == mode]
            proposal_ready = any(record["reviewed"] for record in mode_proposals)
            rejected_proposal = any(record["mode"] == "reject" for record in mode_proposals)
            evidence_ready = (
                (lifecycle == "rejected" or rejected_proposal)
                if mode == "reject"
                else perf_full
            )
            receipts = {
                step: close_receipt_view(topic_id, mode, step)
                for step in ("plan", "integrate", "graph", "verify", "finalize")
            }
            plan_report = ROOT / "tmp" / f"close-plan-{topic_id}-{mode}.md"
            plan_text = read_text(plan_report) if plan_report.is_file() else ""
            trunk_src_writes = ndf_close.infer_trunk_src_writes(
                mode, plan_text or None
            )
            decision_selected = bool(
                selected_decision == mode
                or (lifecycle == "rejected" and mode == "reject")
                or (lifecycle == "promoted" and mode == "promote")
            )
            ordered = ["decision", "evidence", "proposal", "plan", "integrate", "graph"]
            if mode != "reject":
                ordered.append("verify")
            ordered.append("finalize")
            direct = {
                "decision": decision_selected,
                "evidence": evidence_ready,
                "proposal": proposal_ready,
            }
            steps = []
            for step in ordered:
                if step == "integrate" and trunk_src_writes == "none":
                    ready = True
                    source = "trunk_src_writes=none"
                    evidence_state = "na"
                else:
                    ready = direct.get(step, receipts.get(step, {}).get("ready", False))
                    source = (
                        mode_proposals[0]["path"]
                        if step == "proposal" and mode_proposals
                        else "binder/evidence"
                        if step == "evidence" and evidence_ready
                        else receipts.get(step, {}).get("source")
                    )
                    evidence_state = receipts.get(step, {}).get("state")
                steps.append(
                    {
                        "id": step,
                        "status": "completed" if ready else "pending",
                        "source": source,
                        "evidence_state": evidence_state,
                    }
                )
            pre_finalize = all(item["status"] == "completed" for item in steps[:-1])
            finalized = steps[-1]["status"] == "completed"
            branches[mode] = {
                "mode": mode,
                "decision_selected": decision_selected,
                "evidence_ready": evidence_ready,
                "proposal_ready": proposal_ready,
                "close_plan_ready": receipts["plan"]["ready"],
                "trunk_src_writes": trunk_src_writes,
                "close_eligible": bool(
                    decision_selected
                    and proposal_ready
                    and receipts["plan"]["ready"]
                ),
                "verification_required": mode != "reject",
                "finalization_ready": pre_finalize and not finalized,
                "finalized": finalized,
                "receipts": receipts,
                "steps": steps,
                "next_step": next(
                    (item["id"] for item in steps if item["status"] != "completed"),
                    "closed",
                ),
            }
        aggregate_evidence = any(branch["evidence_ready"] for branch in branches.values())
        aggregate_proposal = any(branch["proposal_ready"] for branch in branches.values())
        close_eligible = any(branch["close_eligible"] for branch in branches.values())
        blockers = list(view["health"]["blockers"])
        if not aggregate_evidence:
            blockers.append("close:evidence_missing")
        if notes_only and not aggregate_evidence:
            blockers.append("close:notes_only_untrusted")
        topics.append(
            {
                "topic_id": topic_id,
                "lifecycle": lifecycle,
                "decision": decision,
                "decision_required": bool(decision.get("decision_required")),
                "close_eligible": close_eligible,
                "evidence_ready": aggregate_evidence,
                "proposal_ready": aggregate_proposal,
                "proposals": proposals,
                "close_plan": {
                    "state": "verified"
                    if any(branch["close_plan_ready"] for branch in branches.values())
                    else "unknown",
                    "ready": any(branch["close_plan_ready"] for branch in branches.values()),
                    "source": None,
                },
                "graphcheck": {
                    "state": "green"
                    if any(branch["receipts"]["graph"]["ready"] for branch in branches.values())
                    else "legacy_unbound"
                    if any(
                        branch["receipts"]["graph"]["state"] == "legacy_unbound"
                        for branch in branches.values()
                    )
                    else "unknown",
                    "source": None,
                },
                "verification": {
                    "state": "green"
                    if any(branch["receipts"]["verify"]["ready"] for branch in branches.values())
                    else "legacy_unbound"
                    if any(
                        branch["receipts"]["verify"]["state"] == "legacy_unbound"
                        for branch in branches.values()
                    )
                    else "unknown",
                    "source": None,
                },
                "finalization_ready": any(branch["finalization_ready"] for branch in branches.values()),
                "branches": branches,
                "steps": (
                    branches[str(selected_decision)]["steps"]
                    if selected_decision in CLOSE_DECISIONS
                    else [{"id": "decision", "status": "pending", "source": None}]
                ),
                "next_step": (
                    branches[str(selected_decision)]["next_step"]
                    if selected_decision in CLOSE_DECISIONS
                    else "gates"
                    if decision.get("state") == "not_ready"
                    else "decision"
                ),
                "blockers": sorted(set(blockers)),
            }
        )
    return {"state_source": "tree/git/bound-receipts", "topics": topics}


def business_identity() -> dict[str, Any]:
    charter_path = SPEC / "00-charter" / "charter.md"
    text = read_text(charter_path)
    goal = clause_summary(text, "CHR-001")
    project_match = re.search(r"\b([A-Za-z][A-Za-z0-9_-]+)\s+MUST\b", goal)
    phase = "P3 active" if re.search(r"(?i)P3[（(].*?进行中", text) else "unknown"
    return {
        "name": project_match.group(1) if project_match else ROOT.name,
        "charter_path": rel(charter_path),
        "charter_exists": charter_path.is_file(),
        "goal_summary": goal,
        "phase": phase,
        "scale_coverage": [
            {"scale": "SIFT1M", "status": "validated"},
            {"scale": "DEEP10M", "status": "validated" if "DEEP10M" in text else "unknown"},
            {"scale": "100M", "status": "planned" if "100M" in text else "unknown"},
        ],
    }


def business_goals() -> list[dict[str, Any]]:
    text = read_text(SPEC / "00-charter" / "charter.md")
    goals = []
    for clause_id, label in (
        ("CHR-001", "Primary goal"),
        ("CHR-006", "Performance commitment"),
        ("CHR-004", "Evolution roadmap"),
    ):
        summary = clause_summary(text, clause_id)
        if summary:
            chunk = clause_chunk(text, clause_id)
            status_match = re.search(r"\bstatus=([A-Za-z_-]+)", chunk[:400])
            goals.append(
                {
                    "id": clause_id,
                    "label": label,
                    "summary": summary,
                    "status": status_match.group(1) if status_match else "unknown",
                }
            )
    return goals


def capability_portfolio() -> list[dict[str, Any]]:
    behavior = SPEC / "20-behavior"
    capabilities = []
    for name, config in CAPABILITY_MAP.items():
        paths = [behavior / filename for filename in config["files"] if (behavior / filename).is_file()]
        counts = clause_status_counts(paths)
        capabilities.append(
            {
                "name": name,
                "spec_paths": [rel(path) for path in paths],
                "modules": list(config["modules"]),
                "clauses": counts,
            }
        )
    return capabilities


def performance_summary() -> dict[str, Any]:
    index_path = SPEC / "50-verification" / "golden-baseline.md"
    text = read_text(index_path)
    baseline_match = re.search(r"现行 Trunk 金标:\s*\*\*([^*]+)\*\*", text)
    trunk_match = re.search(r"(?m)^\|\s*代码\s*\|\s*`([0-9a-f]{7,64})`", text)
    config_match = re.search(r"(?m)^\|\s*配置 A/B/C\s*\|\s*`([^`]+)`\s*/\s*`([^`]+)`\s*/\s*`([^`]+)`", text)
    best_match = re.search(r"(?ms)^##\s+最佳性能速览.*?$\n(.*?)(?=^##\s+|\Z)", text)
    best_rows = markdown_rows(best_match.group(1)) if best_match else []
    if best_rows and best_rows[0] and "场景" in best_rows[0][0]:
        best_rows = best_rows[1:]
    warnings = [clean_markdown(line, 220) for line in text.splitlines() if "⚠" in line or "CV=" in line]
    baseline_id = baseline_match.group(1).strip() if baseline_match else None
    baseline_path = (
        SPEC / "50-verification" / "baselines" / f"{baseline_id}.md" if baseline_id else None
    )
    repo_head = git_head()
    golden_raw = trunk_match.group(1) if trunk_match else None
    golden_full = None
    if golden_raw:
        code, resolved = git("rev-parse", "--verify", f"{golden_raw}^{{commit}}")
        if code == 0 and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", resolved):
            golden_full = resolved
    trunk_changed: list[str] = []
    trunk_diff_ok = True
    if not golden_raw:
        golden_head_status = "missing"
    elif not golden_full:
        golden_head_status = "golden_unresolvable"
    elif golden_full == repo_head:
        golden_head_status = "aligned"
    elif not repo_head:
        golden_head_status = "head_ahead_of_golden"
    else:
        trunk_changed, trunk_diff_ok = trunk_paths_changed_since(golden_full, repo_head)
        if not trunk_diff_ok:
            golden_head_status = "head_ahead_of_golden"
        elif trunk_changed:
            golden_head_status = "head_ahead_of_golden"
        else:
            golden_head_status = "docs_only_ahead"
    return {
        "protocol": "sustained",
        "golden_index_path": rel(index_path),
        "baseline_id": baseline_id,
        "baseline_path": rel(baseline_path) if baseline_path else None,
        "status": golden_head_status
        if baseline_path and baseline_path.is_file()
        else "missing",
        "baseline_file_exists": bool(baseline_path and baseline_path.is_file()),
        "trunk_sha": golden_raw,
        "golden_sha_full": golden_full,
        "golden_head_status": golden_head_status,
        "trunk_changed_since_golden": trunk_changed,
        "trunk_diff_ok": trunk_diff_ok,
        "repo_head_full": repo_head,
        "configs": list(config_match.groups()) if config_match else [],
        "best_config": "cfg-m24-ef60" if "cfg-m24-ef60" in text else None,
        "best_scenes": best_rows,
        "warnings": warnings,
        "sla_summary": clause_summary(read_text(SPEC / "40-constraints" / "sla.md"), "CON-SLA-020"),
    }


def roadmap_summary() -> list[dict[str, Any]]:
    path = SPEC / "open" / "optimization-roadmap.md"
    text = read_text(path)
    match = re.search(r"(?ms)^##\s+P3 路线图.*?$\n(.*?)(?=^##\s+|\Z)", text)
    rows = markdown_rows(match.group(1)) if match else []
    items = []
    for row in rows:
        if not row or row[0] in {"#", "---"} or not row[0].startswith("P3-"):
            continue
        items.append(
            {
                "id": row[0],
                "item": row[1] if len(row) > 1 else "",
                "goal": row[2] if len(row) > 2 else "",
                "complexity": row[3] if len(row) > 3 else "",
                "priority": row[4] if len(row) > 4 else "",
                "reference": row[5] if len(row) > 5 else "",
                "path": rel(path),
            }
        )
    return items


def business_risks(views: list[dict[str, Any]], performance: dict[str, Any]) -> list[dict[str, Any]]:
    active = [view for view in views if view["lifecycle"] in {"exploring", "blocked"}]
    stale = [view["topic_id"] for view in views if view["baseline_status"] == "stale"]
    conflicts = []
    for view in active:
        for conflict in view["health"]["conflicts"]:
            pair = sorted((view["topic_id"], conflict["topic"]))
            if pair not in [entry["topics"] for entry in conflicts]:
                conflicts.append({"topics": pair, "surface": conflict["surface"]})
    risks: list[dict[str, Any]] = []
    if stale:
        risks.append({"kind": "stale_baselines", "severity": "warning", "topics": stale})
    if conflicts:
        risks.append({"kind": "surface_conflicts", "severity": "warning", "items": conflicts})
    for warning in performance["warnings"]:
        risks.append({"kind": "golden_variance", "severity": "warning", "message": warning})
    risks.extend(
        [
            {
                "kind": "architecture_debt",
                "severity": "info",
                "message": "God class, friend coupling, and runtime knob sprawl remain recorded debt",
                "path": "spec/10-architecture/modules.md#ARCH-007",
            },
            {
                "kind": "measurement_trap",
                "severity": "info",
                "message": "Cache-warmed/short-query results must not replace sustained evidence",
                "path": "spec/open/optimization-roadmap.md",
            },
        ]
    )
    return risks


_ACP_PROBE: dict[str, Any] | None = None
_ACP_LIGHT_PROBE: dict[str, Any] | None = None
ACP_SESSION_RE = re.compile(r"ACP 长连接会话 ID：`([^`]+)`")
OPENCLAW_SESSION_RE = re.compile(r"OpenClaw 指挥会话 session_key：`([^`]+)`")


def normalize_probe_mode(probe: bool | str | None) -> str | None:
    """Return None | 'light' | 'full' for runtime probing."""
    if probe is True or probe == "full":
        return "full"
    if probe == "light":
        return "light"
    return None


def configured_acp_session_id(agents_text: str | None = None) -> str | None:
    text = agents_text if agents_text is not None else read_text(ROOT / "AGENTS.md")
    match = ACP_SESSION_RE.search(text)
    return match.group(1) if match else None


def claude_acp_resume_path(
    session_id: str,
    *,
    home: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    home = home or Path.home()
    repo_root = repo_root or ROOT
    slug = str(repo_root.resolve()).replace("/", "-")
    return home / ".claude" / "projects" / slug / f"{session_id}.jsonl"


def estimate_acp_resume_text_chars(
    session_id: str | None = None,
    *,
    repo_root: Path | None = None,
) -> int:
    """Rough UTF-8 char count of configured ACP resume jsonl (for context budget)."""
    session_id = session_id or configured_acp_session_id()
    if not session_id:
        return 0
    path = claude_acp_resume_path(session_id, repo_root=repo_root or ROOT)
    if not path.is_file():
        return 0
    total = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            total += len(line)
    return total


def apply_acp_context_budget_to_pack(payload: dict[str, Any]) -> None:
    """Attach acp_context_budget; fail-closed safe_to_dispatch when over window."""
    if str(payload.get("provider") or "") != "claude-code-acp":
        return
    import ndf_dispatch_send as dispatch

    budget = dispatch.acp_context_budget_for_pack(payload)
    payload["acp_context_budget"] = budget
    if budget.get("over_budget"):
        blockers = list(payload.get("blockers") or [])
        if "acp_context_over_budget" not in blockers:
            blockers.append("acp_context_over_budget")
        payload["blockers"] = blockers
        payload["safe_to_dispatch"] = False


def probe_claude_acp_light(*, refresh: bool = False) -> dict[str, Any]:
    """Fast Agents-page probe: CLI + configured session + resume artifact (no doctor)."""
    global _ACP_LIGHT_PROBE
    if _ACP_LIGHT_PROBE is not None and not refresh:
        return _ACP_LIGHT_PROBE
    probed_at = now_iso()
    session_id = configured_acp_session_id()
    executable = shutil.which("claude")
    if not executable:
        result = {
            "mode": "light",
            "reachable": False,
            "error": "claude_cli_missing",
            "cli_available": False,
            "default_session": session_id,
            "doctor_ok": None,
            "resume_available": False,
            "sessions": [],
            "configured_session_visible": None,
            "probed_at": probed_at,
        }
        _ACP_LIGHT_PROBE = result
        return result
    if not session_id:
        result = {
            "mode": "light",
            "reachable": False,
            "error": "acp_session_unconfigured",
            "cli_available": True,
            "default_session": None,
            "doctor_ok": None,
            "resume_available": False,
            "sessions": [],
            "configured_session_visible": None,
            "probed_at": probed_at,
        }
        _ACP_LIGHT_PROBE = result
        return result
    resume_path = claude_acp_resume_path(session_id)
    resume_available = resume_path.is_file() and resume_path.stat().st_size > 0
    error = None if resume_available else "acp_session_resume_missing"
    result = {
        "mode": "light",
        "reachable": resume_available,
        "error": error,
        "cli_available": True,
        "default_session": session_id,
        "doctor_ok": None,
        "resume_available": resume_available,
        "resume_path": str(resume_path),
        "sessions": [],
        "configured_session_visible": None,
        "probe_note": (
            "light probe: CLI + configured session resume artifact; "
            "doctor skipped (use --probe-runtime full for dispatch readiness)"
        ),
        "probed_at": probed_at,
    }
    _ACP_LIGHT_PROBE = result
    return result


def probe_claude_acp(*, refresh: bool = False) -> dict[str, Any]:
    """Probe whether Claude Code ACP can accept a start handshake.

    CLI presence alone is not evidence. Reachability requires a configured
    session ID, ``claude doctor`` reporting a healthy install, and a resume
    transcript for that session. ``claude agents --json`` lists live runs and
    MUST NOT be treated as the pipeline itself.
    """
    global _ACP_PROBE
    if _ACP_PROBE is not None and not refresh:
        return _ACP_PROBE
    probed_at = now_iso()
    session_id = configured_acp_session_id()
    executable = shutil.which("claude")
    if not executable:
        result = {
            "mode": "full",
            "reachable": False,
            "error": "claude_cli_missing",
            "cli_available": False,
            "default_session": session_id,
            "doctor_ok": False,
            "resume_available": False,
            "sessions": [],
            "configured_session_visible": None,
            "probed_at": probed_at,
        }
        _ACP_PROBE = result
        return result
    if not session_id:
        result = {
            "mode": "full",
            "reachable": False,
            "error": "acp_session_unconfigured",
            "cli_available": True,
            "default_session": None,
            "doctor_ok": False,
            "resume_available": False,
            "sessions": [],
            "configured_session_visible": None,
            "probed_at": probed_at,
        }
        _ACP_PROBE = result
        return result
    try:
        doctor = subprocess.run(
            [executable, "doctor"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result = {
            "mode": "full",
            "reachable": False,
            "error": "doctor_unavailable",
            "detail": str(exc),
            "cli_available": True,
            "default_session": session_id,
            "doctor_ok": False,
            "resume_available": False,
            "sessions": [],
            "configured_session_visible": None,
            "probed_at": probed_at,
        }
        _ACP_PROBE = result
        return result
    doctor_ok = doctor.returncode == 0 and "No installation issues found" in (
        doctor.stdout or ""
    )
    resume_path = claude_acp_resume_path(session_id)
    resume_available = resume_path.is_file() and resume_path.stat().st_size > 0
    sessions: list[Any] = []
    agents_error = None
    try:
        agents = subprocess.run(
            [executable, "agents", "--json", "--cwd", str(ROOT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=10,
        )
        if agents.returncode == 0:
            try:
                payload = json.loads(agents.stdout or "[]")
            except json.JSONDecodeError:
                payload = []
                agents_error = "invalid_agents_json"
            if isinstance(payload, list):
                sessions = payload
            elif isinstance(payload, dict):
                raw = payload.get("sessions", [])
                sessions = raw if isinstance(raw, list) else []
        else:
            agents_error = "agents_json_failed"
    except (OSError, subprocess.TimeoutExpired) as exc:
        agents_error = f"agents_unavailable:{exc}"
    session_ids: set[str] = set()
    for item in sessions:
        if isinstance(item, str):
            session_ids.add(item)
        elif isinstance(item, dict):
            for key in ("id", "session_id", "sessionId"):
                value = item.get(key)
                if value:
                    session_ids.add(str(value))
                    break
    error = None
    if not doctor_ok:
        error = "doctor_unhealthy"
    elif not resume_available:
        error = "acp_session_resume_missing"
    result = {
        "mode": "full",
        "reachable": doctor_ok and resume_available,
        "error": error,
        "cli_available": True,
        "default_session": session_id,
        "doctor_ok": doctor_ok,
        "doctor_exit_code": doctor.returncode,
        "resume_available": resume_available,
        "resume_path": str(resume_path),
        "sessions": sessions,
        "configured_session_visible": session_id in session_ids,
        "agents_error": agents_error,
        "probed_at": probed_at,
    }
    _ACP_PROBE = result
    return result


def probe_openclaw() -> dict[str, Any]:
    executable = shutil.which("openclaw")
    if not executable:
        return {"reachable": False, "error": "openclaw_cli_missing", "probed_at": now_iso()}
    proc = subprocess.run(
        [executable, "health", "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=10,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "reachable": False,
            "error": "invalid_health_json",
            "exit_code": proc.returncode,
            "probed_at": now_iso(),
        }
    sessions = payload.get("sessions", {}).get("recent", [])
    return {
        "reachable": bool(payload.get("ok")) and proc.returncode == 0,
        "degraded": bool(payload.get("eventLoop", {}).get("degraded")),
        "sessions": sessions,
        "channels": {
            name: {
                "enabled": value.get("enabled"),
                "running": value.get("running"),
                "health_state": value.get("healthState"),
            }
            for name, value in payload.get("channels", {}).items()
        },
        "probed_at": now_iso(),
    }


_OPENCLAW_SESSION_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_openclaw_agent_session_id(value: str) -> bool:
    """True when value is acceptable as ``openclaw agent --session-id``."""
    return bool(_OPENCLAW_SESSION_UUID_RE.fullmatch(str(value or "").strip()))


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text or ""
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None


def list_openclaw_sessions(*, limit: int = 100) -> tuple[list[dict[str, Any]], str | None]:
    """Return (sessions, error). Sessions come from ``openclaw sessions --json``."""
    executable = shutil.which("openclaw")
    if not executable:
        return [], "openclaw_cli_missing"
    proc = subprocess.run(
        [
            executable,
            "sessions",
            "--json",
            "--all-agents",
            "--limit",
            str(max(1, int(limit))),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    payload = _extract_json_object(proc.stdout or "")
    if payload is None:
        return [], "invalid_sessions_json"
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return [], "invalid_sessions_json"
    return [item for item in sessions if isinstance(item, dict)], None


def resolve_openclaw_dispatch_session(
    configured: str | None,
    *,
    sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve AGENTS.md session_key for Control dispatch.

    Routing keys (``agent:main:feishu:…``) are valid Control identity when present
    as a store ``key``. UUID values are valid ``openclaw agent --session-id`` ids.
    Transport chooses gateway ``sessionKey`` vs CLI ``--session-id`` accordingly.
    """
    key = str(configured or "").strip()
    hint = (
        "Edit AGENTS.md OpenClaw 指挥会话 session_key to a key listed in "
        "`openclaw sessions --json` (or a UUID sessionId), then click 探测运行时 (light)."
    )
    if not key:
        return {
            "session_configured": False,
            "session_dispatchable": False,
            "resolved_session_id": None,
            "matched_key": None,
            "transport": None,
            "error": "openclaw_session_unconfigured",
            "fix_hint": hint,
        }
    store = sessions
    store_error = None
    if store is None:
        store, store_error = list_openclaw_sessions()

    def _ok(
        *,
        matched_key: str | None,
        resolved_session_id: str | None,
        transport: str,
    ) -> dict[str, Any]:
        return {
            "session_configured": True,
            "session_dispatchable": True,
            "resolved_session_id": resolved_session_id,
            "matched_key": matched_key,
            "transport": transport,
            "error": None,
            "fix_hint": None,
        }

    def _bad(error: str) -> dict[str, Any]:
        return {
            "session_configured": True,
            "session_dispatchable": False,
            "resolved_session_id": None,
            "matched_key": None,
            "transport": None,
            "error": error,
            "fix_hint": hint,
        }

    if store_error and not store:
        if _looks_like_openclaw_agent_session_id(key):
            return _ok(
                matched_key=None,
                resolved_session_id=key,
                transport="session_id",
            )
        # Store unavailable: still allow routing-key transport when configured;
        # gateway call validates membership at send time.
        if ":" in key:
            return _ok(
                matched_key=key,
                resolved_session_id=None,
                transport="session_key",
            )
        return _bad(store_error or "openclaw_session_invalid")

    match: dict[str, Any] | None = None
    for item in store:
        if str(item.get("sessionId") or "") == key or str(item.get("key") or "") == key:
            match = item
            break
    if match is None:
        if _looks_like_openclaw_agent_session_id(key):
            return _ok(
                matched_key=None,
                resolved_session_id=key,
                transport="session_id",
            )
        return _bad("openclaw_session_invalid")

    matched_key = str(match.get("key") or key)
    sid = str(match.get("sessionId") or "").strip()
    if _looks_like_openclaw_agent_session_id(sid):
        return _ok(
            matched_key=matched_key,
            resolved_session_id=sid,
            transport="session_id",
        )
    # Routing key hit in store — dispatch via gateway sessionKey (chat_send-equivalent).
    return _ok(
        matched_key=matched_key,
        resolved_session_id=None,
        transport="session_key",
    )


def runtime_status(probe: bool | str = False) -> dict[str, Any]:
    agents_text = read_text(ROOT / "AGENTS.md")
    session_id = configured_acp_session_id(agents_text)
    openclaw_match = OPENCLAW_SESSION_RE.search(agents_text)
    mode = normalize_probe_mode(probe)
    openclaw_probe = probe_openclaw() if mode else None
    if mode == "full":
        acp_probe = probe_claude_acp(refresh=True)
    elif mode == "light":
        acp_probe = probe_claude_acp_light(refresh=True)
    else:
        acp_probe = _ACP_PROBE or _ACP_LIGHT_PROBE
    configured_key = openclaw_match.group(1) if openclaw_match else "agent:main:main"
    recent_keys = {
        item.get("key")
        for item in (openclaw_probe or {}).get("sessions", [])
        if isinstance(item, dict)
    }
    session_resolution: dict[str, Any] | None = None
    if mode:
        if openclaw_probe and openclaw_probe.get("reachable"):
            session_resolution = resolve_openclaw_dispatch_session(configured_key)
        elif not str(configured_key or "").strip():
            session_resolution = resolve_openclaw_dispatch_session("")
        else:
            session_resolution = {
                "session_configured": True,
                "session_dispatchable": False,
                "resolved_session_id": None,
                "matched_key": None,
                "error": (
                    (openclaw_probe or {}).get("error")
                    if openclaw_probe is not None
                    else "not_probed"
                )
                or "runtime_unavailable",
                "fix_hint": (
                    "Restore OpenClaw gateway (`openclaw health --json`), then "
                    "verify AGENTS.md session_key is dispatchable."
                ),
            }
    leases = active_runtime_leases()
    probed = acp_probe is not None
    reachable = bool(acp_probe and acp_probe.get("reachable"))
    if leases:
        impl_status = "active"
        if probed:
            probe_state = "reachable" if reachable else "unavailable"
        else:
            probe_state = "not_probed"
    elif not probed and mode is None:
        impl_status = "not_probed"
        probe_state = "not_probed"
    elif reachable:
        impl_status = "idle"
        probe_state = "reachable"
    else:
        impl_status = "unavailable"
        probe_state = "unavailable"
    return {
        "implementation": {
            "provider": "claude-code-acp",
            "status": impl_status,
            # Three-state probe surface: not_probed | unavailable | reachable.
            "probe_state": probe_state,
            "pipeline_reachable": reachable if probed else False,
            "active_runs": leases,
            "default_session": (acp_probe or {}).get("default_session") or session_id,
            "state_source": "pipeline",
            "cli_available": (
                bool(acp_probe.get("cli_available"))
                if acp_probe is not None
                else bool(shutil.which("claude"))
            ),
            "doctor_ok": None if acp_probe is None else acp_probe.get("doctor_ok"),
            "resume_available": (
                None if acp_probe is None else bool(acp_probe.get("resume_available"))
            ),
            "configured_session_visible": (
                None if acp_probe is None else acp_probe.get("configured_session_visible")
            ),
            "probe_error": None if acp_probe is None else acp_probe.get("error"),
            "probe_mode": (
                (acp_probe or {}).get("mode")
                if probed
                else (mode if mode not in {None, "off"} else None)
            ),
            "probe": acp_probe,
            "probe_note": (
                None
                if acp_probe is None
                else acp_probe.get("probe_note")
                or (
                    "Claude CLI presence is not ACP pipeline/run evidence; "
                    "doctor + configured session resume artifact required"
                )
            ),
            "workspace": project_workspace_view(),
        },
        "control": {
            "provider": "openclaw",
            "default_session_key": configured_key,
            "reachable": openclaw_probe.get("reachable") if openclaw_probe else None,
            "gateway_reachable": (
                openclaw_probe.get("reachable") if openclaw_probe else None
            ),
            "configured_session_visible": (
                configured_key in recent_keys if mode else None
            ),
            "session_configured": (
                None
                if session_resolution is None
                else bool(session_resolution.get("session_configured"))
            ),
            "session_dispatchable": (
                None
                if session_resolution is None
                else bool(session_resolution.get("session_dispatchable"))
            ),
            "resolved_session_id": (
                None
                if session_resolution is None
                else session_resolution.get("resolved_session_id")
            ),
            "session_transport": (
                None
                if session_resolution is None
                else session_resolution.get("transport")
            ),
            "session_error": (
                None if session_resolution is None else session_resolution.get("error")
            ),
            "session_fix_hint": (
                None
                if session_resolution is None
                else session_resolution.get("fix_hint")
            ),
            "state_source": "gateway",
            "probe": openclaw_probe,
            "probe_error": (
                None if openclaw_probe is None else openclaw_probe.get("error")
            ),
            "workspace": project_workspace_view(),
        },
    }


def openclaw_session_key() -> str:
    agents_text = read_text(ROOT / "AGENTS.md")
    match = OPENCLAW_SESSION_RE.search(agents_text)
    return match.group(1) if match else "agent:main:main"


def control_runtime_dispatch_ready(control: Mapping[str, Any] | None) -> bool:
    """Gateway reachable AND configured session resolves to a dispatchable id."""
    runtime = control or {}
    return bool(runtime.get("reachable") and runtime.get("session_dispatchable"))


def control_runtime_dispatch_blockers(control: Mapping[str, Any] | None) -> list[str]:
    runtime = control or {}
    if runtime.get("reachable") and runtime.get("session_dispatchable"):
        return []
    blockers: list[str] = []
    if not runtime.get("reachable"):
        blockers.append("runtime_unavailable")
    elif runtime.get("session_configured") is False:
        blockers.append("openclaw_session_unconfigured")
    elif runtime.get("session_dispatchable") is False:
        err = str(runtime.get("session_error") or "openclaw_session_invalid")
        blockers.append(
            err
            if err.startswith("openclaw_session_")
            else "openclaw_session_invalid"
        )
    else:
        blockers.append("runtime_unavailable")
    return blockers


def implementation_dispatch_runtime(
    topic: str | None = None,
) -> tuple[dict[str, Any], bool, dict[str, Any] | None]:
    """Probe ACP and return (runtime, pipeline_reachable, active_lease_row)."""
    runtime = runtime_status(True)["implementation"]
    lease = topic_active_lease(topic) if topic is not None else None
    ready = bool(runtime.get("pipeline_reachable"))
    return runtime, ready, lease


def _read_last_dispatch_pack(topic: str | None) -> dict[str, Any] | None:
    if not topic or not DISPATCH_PACK_PATH.is_file():
        return None
    try:
        data = json.loads(DISPATCH_PACK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("topic") or "") != str(topic):
        return None
    return data


def _dispatch_send_topic(data: Mapping[str, Any]) -> str | None:
    topic = data.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    completion = data.get("agent_completion")
    if isinstance(completion, Mapping):
        nested = completion.get("topic")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    closeout = data.get("closeout")
    if isinstance(closeout, Mapping):
        pack = closeout.get("pack")
        if isinstance(pack, Mapping):
            nested = pack.get("topic")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _read_last_dispatch_send(topic: str | None = None) -> dict[str, Any] | None:
    if not DISPATCH_LAST_PATH.is_file():
        return None
    try:
        data = json.loads(DISPATCH_LAST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if topic:
        send_topic = _dispatch_send_topic(data)
        if send_topic and send_topic != str(topic):
            return None
    return data


def _dispatch_pack_head_matches(pack: Mapping[str, Any], head: str) -> bool:
    base = str(pack.get("base_sha") or "")
    workspace_head = str((pack.get("workspace") or {}).get("repo_head") or "")
    return bool(head) and (base == head or workspace_head == head)


def runtime_dispatch_ready_for_topic(
    topic_id: str,
    runtime: Mapping[str, Any],
    lease: Mapping[str, Any] | None,
) -> tuple[bool, str | None]:
    """Transport-plane ACP reachability (live probe or absorbed pack only).

    Must NOT treat active isolated lease as runtime ready — lease is a separate
    readiness face (active_isolated_lease / prepare-acp-lease). Delegate POC
    gates on lease; default snapshot does not probe ACP.
    """
    del lease  # retained for call-site compatibility; lease is not transport evidence
    head = git_head()
    probed = bool(runtime.get("probe")) or bool(runtime.get("probe_mode"))
    if probed:
        if runtime.get("pipeline_reachable"):
            return True, "live_probe"
        return False, None
    pack = _read_last_dispatch_pack(topic_id)
    if pack and _dispatch_pack_head_matches(pack, head):
        if pack.get("runtime_dispatch_ready") is True:
            return True, "absorbed_pack"
    return False, None


def _is_dispatch_stub_success(agent_run: Mapping[str, Any]) -> bool:
    state = str(agent_run.get("dispatch_state") or agent_run.get("state") or "")
    if state != "succeeded":
        return False
    summary = str(agent_run.get("result_summary") or "")
    if summary == "lease_only_no_implementation_start" or summary.endswith(
        "_no_implementation_start"
    ):
        return True
    if not str(agent_run.get("worktree") or "").strip():
        send = agent_run.get("send")
        if isinstance(send, Mapping) and send.get("lease_only"):
            return True
    return False


def _partial_close_next_step_available(detail: Mapping[str, Any]) -> bool:
    decision = detail.get("decision") or {}
    if not isinstance(decision, Mapping):
        return False
    offered = decision.get("offered") or []
    if "partial" not in offered:
        return False
    spaces = detail.get("spaces") or {}
    test = spaces.get("test") if isinstance(spaces, Mapping) else None
    if isinstance(test, Mapping) and test.get("ready") is True:
        return True
    focus = str(decision.get("next_round_focus") or "").lower()
    return "partial" in focus and "promote" in focus


def _implementation_dispatch_view(topic: str | None = None) -> dict[str, Any]:
    """Project latest dispatch-send receipt onto the commander surface."""
    empty = {
        "delegate_to": "claude-code-acp",
        "dispatch_state": "not_dispatched",
        "result_summary": None,
        "dispatch_blockers_from_send": [],
        "transport_ok": False,
        "completion_rejected": False,
        "completion_blockers_human": [],
    }
    data = _read_last_dispatch_send(topic)
    if not data:
        return empty
    state = str(data.get("dispatch_state") or data.get("state") or "not_dispatched")
    blockers = list(data.get("blockers") or [])
    completion_human = humanize_completion_blockers(blockers)
    transport_ok = bool(data.get("transport_ok"))
    completion_rejected = bool(
        state == "failed" and transport_ok and completion_human
    )
    return {
        "delegate_to": data.get("delegate_to") or "claude-code-acp",
        "dispatch_state": state,
        "result_summary": data.get("result_summary"),
        "dispatch_blockers_from_send": blockers,
        "dispatch_request_id": data.get("request_id"),
        "dispatch_pack_sha": data.get("pack_sha"),
        "transport_ok": transport_ok,
        "completion_rejected": completion_rejected,
        "completion_blockers_human": completion_human,
    }


def read_openclaw_workspace() -> dict[str, Any] | None:
    state_path = ROOT / ".openclaw" / "state.json"
    if not state_path.is_file():
        return None
    try:
        data = json.loads(read_text(state_path))
    except json.JSONDecodeError:
        return None
    workspace = data.get("workspace")
    return workspace if isinstance(workspace, dict) else None


def workspace_binding(topic: str | None) -> dict[str, Any]:
    topic_dir = f"poc/{topic}/" if topic else None
    return {
        "repo_root": str(ROOT),
        "repo_name": ROOT.name,
        "repo_head": git_head(),
        "state_path": ".openclaw/state.json",
        "active_topic": topic,
        "topic_dir": topic_dir,
        "topic_ndf_dir": f"{topic_dir}ndf/" if topic_dir else None,
    }


def project_workspace_view() -> dict[str, Any]:
    binding = workspace_binding(None)
    persisted = read_openclaw_workspace()
    truth = workspace_truth(binding, persisted)
    return {
        "binding": binding,
        "persisted": persisted,
        "match": truth["workspace_bound"],
        "state": truth["state"],
        "truth": truth,
        "state_file": str(ROOT / ".openclaw" / "state.json"),
        "state_exists": (ROOT / ".openclaw" / "state.json").is_file(),
    }


def workspace_truth_view(topic: str | None) -> dict[str, Any]:
    return workspace_truth(workspace_binding(topic), read_openclaw_workspace())


def next_human_phrase(view: dict[str, Any]) -> str | None:
    gates = view["gates"]
    if view["phase_hint"] == "legacy_gate_audit":
        return GATE_PHRASES["topic_review"]
    if any(gates[name]["state"] == "bundle_invalid" for name in GATE_ORDER):
        return None
    if gates["topic_review"]["state"] != "valid":
        return GATE_PHRASES["topic_review"]
    if gates["design_review"]["state"] != "valid":
        return GATE_PHRASES["design_review"]
    if gates["implementation_approval"]["state"] != "valid":
        return GATE_PHRASES["implementation_approval"]
    return None


def required_reads_for_task(task: str, topic: str | None) -> list[str]:
    canonical = canonicalize_proposal_task(task)
    if canonical == "product_proposal" and not topic:
        return [
            "AGENTS.md",
            "spec/00-charter/charter.md",
            "META-011",
            "META-012",
            "ADR-META-004",
        ]
    if canonical == "process_proposal" and not topic:
        return [
            "AGENTS.md",
            "spec/meta/README.md",
            "META-011",
            "META-012",
            "META-014",
            "ADR-META-004",
        ]
    if not topic:
        raise ValueError("topic is required for this control task")
    base_meta = ["META-010", "BEH-025", "META-011"]
    binder = [f"poc/{topic}/ndf/TOPIC.md", f"poc/{topic}/ndf/GATES.md"]
    if task in {"legacy_gate_audit", "gate_pipeline"}:
        return base_meta + binder + [
            f"poc/{topic}/ndf/DESIGN.md",
            f"poc/{topic}/ndf/PERF_BASELINE.md",
            f"poc/{topic}/ndf/INTERFACE.md",
        ]
    if task == "gate_sha_audit":
        return ["META-010"] + binder
    if task == "gate_receipt_draft":
        return ["META-010", "BEH-025"] + binder
    if task in {"binder_amend", "binder_pipeline"}:
        return base_meta + [
            f"poc/{topic}/ndf/TOPIC.md",
            f"poc/{topic}/ndf/DESIGN.md",
            f"poc/{topic}/ndf/INTERFACE.md",
            f"poc/{topic}/ndf/PERF_BASELINE.md",
            f"poc/{topic}/ndf/DELTA.md",
            f"poc/{topic}/ndf/COMMITS.md",
        ]
    if canonical == "product_proposal":
        return ["AGENTS.md", "META-011", "ADR-META-004", f"poc/{topic}/ndf/TOPIC.md"]
    if canonical == "process_proposal":
        return ["AGENTS.md", "META-014", "ADR-META-004", "spec/meta/README.md"]
    return base_meta + binder


def canonicalize_proposal_task(task: str) -> str:
    """Map legacy aliases to explicit product/process proposal tasks."""
    if task in {"control_proposal", "product_proposal"}:
        return "product_proposal"
    if task in {"process_proposal", "ndf_improvement_proposal"}:
        return "process_proposal"
    return task


def idea_plane_for_task(task: str) -> str | None:
    canonical = canonicalize_proposal_task(task)
    if canonical == "product_proposal":
        return "product"
    if canonical in {"process_proposal"} or task in PROCESS_PROPOSAL_TASKS:
        return "process"
    return None


def allowed_roots_for_idea_plane(plane: str) -> list[str]:
    roots = IDEA_PLANE_ROOTS.get(plane)
    if not roots:
        raise ValueError(f"unknown idea plane: {plane}")
    return list(roots)


def assert_idea_write_roots(task: str, roots: list[str]) -> None:
    """Fail closed when pack write roots cross product/process planes."""
    plane = idea_plane_for_task(task)
    if plane is None:
        return
    allowed = set(allowed_roots_for_idea_plane(plane))
    normalized = []
    for root in roots:
        text = str(root).replace("\\", "/")
        if not text.endswith("/") and Path(text).suffix == "":
            text = text + "/"
        normalized.append(text)
    for root in normalized:
        if plane == "product" and (
            root.startswith("spec/meta/") or "spec/meta/open" in root
        ):
            raise ValueError(
                f"product_proposal must not write {root}; only spec/open/"
            )
        if plane == "process" and root.startswith("spec/open/"):
            raise ValueError(
                f"process_proposal must not write {root}; only spec/meta/open/"
            )
        if not any(root.startswith(a) or a.startswith(root) for a in allowed):
            # Allow exact proposal file paths under the plane root.
            if not any(root.startswith(a.rstrip("/")) for a in allowed):
                raise ValueError(
                    f"task {task} write root {root} outside plane {plane} {sorted(allowed)}"
                )


def classify_idea_plane(text: str) -> dict[str, Any]:
    """Heuristic classifier for human ideas (ADR-META-004). Ambiguous → ask."""
    raw = (text or "").strip()
    lowered = raw.lower()
    process_markers = (
        "ndf 工作流",
        "ndf workflow",
        "流程",
        "meta",
        "agents.md",
        "gate",
        "装订",
        "commander",
        "replay",
        "episode",
        "dispatch",
        "poc-dispatch",
        "graphcheck",
        "bindcheck",
        "规范卫生",
        "process",
        "genesis 流程",
        "skill",
    )
    product_markers = (
        "qps",
        "recall",
        "sla",
        "缓存",
        "cache",
        "hnsw",
        "io",
        "pq",
        "性能",
        "bug",
        "trunk",
        "src/",
        "promote",
        "poc/",
        "检索",
        "向量",
    )
    bootstrap_markers = (
        "初始化项目",
        "genesis",
        "greenfield",
        "adopt",
        "接管已有",
        "从 idea 建",
    )
    process_hits = sum(1 for m in process_markers if m in lowered or m in raw)
    product_hits = sum(1 for m in product_markers if m in lowered or m in raw)
    bootstrap_hits = sum(1 for m in bootstrap_markers if m in lowered or m in raw)
    if bootstrap_hits and not process_hits:
        return {
            "plane": "product",
            "track": "bootstrap",
            "task": "product_proposal",
            "write_roots": allowed_roots_for_idea_plane("product"),
            "confidence": "high",
            "reason": "genesis_bootstrap",
        }
    if process_hits and product_hits:
        return {
            "plane": "mixed",
            "track": None,
            "task": None,
            "write_roots": [],
            "confidence": "ask",
            "reason": "mixed_product_and_process",
            "split": [
                {
                    "plane": "product",
                    "task": "product_proposal",
                    "write_roots": allowed_roots_for_idea_plane("product"),
                },
                {
                    "plane": "process",
                    "task": "process_proposal",
                    "write_roots": allowed_roots_for_idea_plane("process"),
                },
            ],
        }
    if process_hits and not product_hits:
        return {
            "plane": "process",
            "track": "process",
            "task": "process_proposal",
            "write_roots": allowed_roots_for_idea_plane("process"),
            "confidence": "high",
            "reason": "process_markers",
        }
    if product_hits and not process_hits:
        return {
            "plane": "product",
            "track": "poc",
            "task": "product_proposal",
            "write_roots": allowed_roots_for_idea_plane("product"),
            "confidence": "high",
            "reason": "product_markers",
        }
    return {
        "plane": "ambiguous",
        "track": None,
        "task": None,
        "write_roots": [],
        "confidence": "ask",
        "reason": "ambiguous_ask_human",
    }


def genesis_paths() -> dict[str, Path]:
    return {
        "proposal": SPEC / "open" / "proposal-project-genesis.md",
        "idea": SPEC / "open" / "project-genesis" / "IDEA.md",
        "foundation": SPEC / "open" / "project-genesis" / "FOUNDATION.md",
        "gates": SPEC / "open" / "project-genesis" / "GATES.md",
        "decision": SPEC / "decisions" / "dec-project-genesis.md",
    }


def _genesis_roles_summary() -> dict[str, Any]:
    try:
        import ndf_role_binding as role_binding

        status = role_binding.status_report(ROOT)
        return {
            "roles_bound": status.get("roles_bound"),
            "roles_sha": status.get("roles_sha"),
            "roles": status.get("roles"),
            "genesis_roles_gate": status.get("genesis_roles_gate"),
        }
    except Exception:
        return {
            "roles_bound": False,
            "roles_sha": None,
            "roles": {},
            "genesis_roles_gate": False,
        }


def genesis_status() -> dict[str, Any]:
    paths = genesis_paths()
    decision_text = read_text(paths["decision"])
    accepted = "accepted" in (header(decision_text, "Status") or "").lower()
    bound_sha = header(decision_text, "genesis_trunk_sha")
    resolvable = False
    if bound_sha and not re.search(r"(?i)pending|tbd|unknown", bound_sha):
        code, _ = git("rev-parse", "--verify", f"{bound_sha}^{{commit}}")
        resolvable = code == 0
    has_charter = (SPEC / "00-charter").is_dir() and any((SPEC / "00-charter").glob("*.md"))
    has_src = (ROOT / "src").is_dir() and any((ROOT / "src").rglob("*"))
    clause_count = 0
    for path in SPEC.glob("[0-5][0-9]-*/**/*.md"):
        clause_count += len(re.findall(r"\{#[A-Z][A-Z0-9-]+\}", read_text(path)))
    if accepted and resolvable:
        maturity = "operational"
    elif paths["proposal"].is_file() or paths["idea"].is_file():
        if paths["foundation"].is_file():
            maturity = "ndf_foundation" if not has_src else "trunk_candidate"
        else:
            maturity = "idea_review"
    elif has_charter and has_src and clause_count:
        maturity = "operational_legacy"
    elif has_charter:
        maturity = "ndf_foundation"
    else:
        maturity = "uninitialized"
    if maturity == "operational":
        rail_state = ("completed", "completed", "completed", "completed")
    elif maturity == "operational_legacy":
        rail_state = ("legacy", "legacy", "legacy", "legacy")
    elif maturity == "trunk_candidate":
        rail_state = ("completed", "completed", "in_progress", "pending")
    elif maturity == "ndf_foundation":
        rail_state = ("completed", "in_progress", "pending", "pending")
    elif maturity == "idea_review":
        rail_state = ("in_progress", "pending", "pending", "pending")
    else:
        rail_state = ("pending", "pending", "pending", "pending")
    rail = [
        {
            "id": "G0",
            "label": "IDEA",
            "state": rail_state[0],
            "path": rel(paths["idea"]),
            "content_sha": file_sha(paths["idea"]),
            "next_phrase": "IDEA已审核",
        },
        {
            "id": "G1",
            "label": "Foundation",
            "state": rail_state[1],
            "path": rel(paths["foundation"]),
            "content_sha": file_sha(paths["foundation"]),
            "next_phrase": "VERIFICATION已审核",
        },
        {
            "id": "G2",
            "label": "Trunk Candidate",
            "state": rail_state[2],
            "path": rel(paths["gates"]),
            "content_sha": file_sha(paths["gates"]),
            "next_phrase": "可以建立初始主线",
        },
        {
            "id": "G3",
            "label": "Freeze",
            "state": rail_state[3],
            "path": rel(paths["decision"]),
            "content_sha": file_sha(paths["decision"]),
            "next_phrase": "GENESIS已审核",
        },
    ]
    return {
        "project_maturity": maturity,
        "accepted": accepted,
        "genesis_trunk_sha": bound_sha,
        "genesis_trunk_sha_resolves": resolvable,
        "clause_count": clause_count,
        "paths": {name: {"path": rel(path), "exists": path.is_file()} for name, path in paths.items()},
        "rail": rail,
        "roles_bound": _genesis_roles_summary().get("roles_bound"),
        "roles": _genesis_roles_summary().get("roles"),
        "roles_sha": _genesis_roles_summary().get("roles_sha"),
        "next_step": next(
            (
                {"id": item["id"], "label": item["label"], "phrase": item["next_phrase"]}
                for item in rail
                if item["state"] in {"pending", "in_progress"}
            ),
            None,
        ),
        "warning": "Genesis provenance missing; legacy operational project"
        if maturity == "operational_legacy"
        else (
            "roles_unbound: bind command/control/implementation in ndf.workflow.yaml "
            "and append 角色已配置 to genesis GATES before G1"
            if not _genesis_roles_summary().get("roles_bound")
            and maturity in {"idea_review", "ndf_foundation", "trunk_candidate", "uninitialized"}
            else None
        ),
        "install_needed": maturity in GENESIS_INSTALL_MATURITIES,
        "kernel_installed": maturity == "operational" and accepted,
    }


def load_meta_graph() -> dict[str, Any]:
    path = META / "graph.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def kernel_map(meta_graph_data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    path = META / "graph.json"
    data = dict(meta_graph_data) if meta_graph_data is not None else load_meta_graph()
    nodes_raw = data.get("nodes") or {}
    if isinstance(nodes_raw, dict):
        nodes = list(nodes_raw.values())
    else:
        nodes = list(nodes_raw)
    seed_set = set(KERNEL_SEED_IDS)
    summaries = [
        clause_node_summary(
            node,
            role="seed" if str(node.get("id") or "") in seed_set else "closure",
        )
        for node in nodes
        if node.get("id")
    ]
    by_id = {str(item["id"]): item for item in summaries}
    seeds = [by_id[cid] for cid in KERNEL_SEED_IDS if cid in by_id]
    missing_seeds = [cid for cid in KERNEL_SEED_IDS if cid not in by_id]
    return {
        "available": bool(summaries),
        "path": rel(path),
        "generated_at": data.get("generated_at"),
        "clause_count": int(data.get("clause_count") or len(summaries)),
        "stable_summary": stable_summary(summaries),
        "nodes": summaries,
        "seed_ids": list(KERNEL_SEED_IDS),
        "seeds": seeds,
        "missing_seeds": missing_seeds,
    }


def topic_business_summary(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic_id": view["topic_id"],
        "path": view["path"],
        "lifecycle": view["lifecycle"],
        "phase_hint": view["phase_hint"],
        "hypothesis": view["business"]["hypothesis"],
        "expected_impact": view["business"]["expected_impact"],
        "current_evidence": view["business"]["current_evidence"],
        "next_gate": view["business"]["next_gate"],
        "decision": view["decision"],
        "explore_surface": view["explore_surface"],
        "baseline_status": view["baseline_status"],
        "control_blockers": view["health"]["blockers"],
        "surface_conflicts": view["health"]["conflicts"],
        "gates": {
            name: {
                "state": gate["state"],
                "phrase": GATE_PHRASES.get(name),
                "expected_content_sha": gate.get("expected_content_sha"),
            }
            for name, gate in view["gates"].items()
        },
        "next_human_phrase": next_human_phrase(view),
    }


def topic_health(topic: str, persist: bool = True) -> tuple[dict[str, Any], int]:
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    generation_sha = source_generation_sha()
    ensure_spec_health(generation_sha)
    view = topic_view(topic_dir)
    findings = view["health"]["findings"]
    previous = read_json_artifact(topic_health_artifact(topic)) or {}
    previous_kinds = {
        str(item.get("kind"))
        for item in previous.get("findings", [])
        if isinstance(item, dict) and item.get("kind")
    }
    current_kinds = {
        str(item.get("kind"))
        for item in findings
        if isinstance(item, dict) and item.get("kind")
    }
    payload = {
        "schema": "ndf-topic-health/v1",
        "generated_at": now_iso(),
        "snapshot_sha": generation_sha,
        "repo_head": git_head(),
        "topic": view["topic_id"],
        "lifecycle": view["lifecycle"],
        "phase_hint": view["phase_hint"],
        "decision": view["decision"],
        "control_pipelines": view["control_pipelines"],
        "spaces": view["spaces"],
        "checks": view["health"]["checks"],
        "findings": findings,
        "findings_hash": canonical_json_sha(findings),
        "finding_diff": {
            "resolved": sorted(previous_kinds - current_kinds),
            "remaining": sorted(previous_kinds & current_kinds),
            "new": sorted(current_kinds - previous_kinds),
            "previous_findings_hash": previous.get("findings_hash"),
        },
        "next_actions": view["health"]["next_actions"],
        "delegation": view["delegation"],
        "gate_drift": [
            item.get("gate_drift")
            for item in findings
            if isinstance(item, dict) and item.get("gate_drift")
        ],
        "poc_sha": (generation_layers().get("poc") or {}).get(topic),
        "state": "current",
    }
    if persist:
        write_json_artifact(topic_health_artifact(topic), payload)
    hard_errors = sum(1 for item in findings if item["severity"] == "error")
    return payload, 1 if hard_errors else 0


def project_check_findings(checks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name, check in checks.items():
        if check["exit_code"] == 0:
            continue
        route = PROJECT_CHECK_ROUTES.get(
            name,
            {
                "plane": "NDF Control",
                "repair_owner": "openclaw",
                "repair_task": "process_proposal",
                "allowed_write_root": "spec/meta/open/",
                "human_gate": "已确认 → 已审核",
            },
        )
        findings.append(
            finding(
                scope="project",
                space="Design",
                kind=f"{name}_failed",
                severity="error",
                evidence=clean_markdown(check["output"], 360) or "check failed",
                repair_owner=route["repair_owner"],
                repair_task=route["repair_task"],
                allowed_write_root=route["allowed_write_root"],
                human_gate=route["human_gate"],
                plane=route["plane"],
            )
        )
    for warning in proposal_plane_warnings():
        findings.append(
            finding(
                scope="project",
                space="Design",
                kind=warning["kind"],
                severity=warning["severity"],
                evidence=warning["message"],
                repair_owner="openclaw",
                repair_task="proposal_plane_repair",
                allowed_write_root=None,
                human_gate=None,
                plane=warning.get("plane") or "NDF Control",
            )
        )
    for warning in draft_map_warnings():
        findings.append(
            finding(
                scope="project",
                space="Design",
                kind=warning["kind"],
                severity="warning",
                evidence=warning["message"],
                repair_owner="openclaw",
                repair_task="ndf_improvement_proposal",
                allowed_write_root="spec/meta/open/",
                human_gate="已确认 → 已审核",
            )
        )
    return findings


def spec_health(persist: bool = True, layers: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    layers = dict(layers or generation_layers())
    previous = read_json_artifact(HEALTH_DIR / "spec.json") or {}
    prev_layers = previous.get("layers") if isinstance(previous.get("layers"), dict) else {}
    prev_raw = previous.get("raw_checks") if isinstance(previous.get("raw_checks"), dict) else {}

    def reuse(name: str, *layer_keys: str) -> dict[str, Any] | None:
        cached = prev_raw.get(name)
        if not isinstance(cached, dict):
            return None
        for key in layer_keys:
            if prev_layers.get(key) != layers.get(key):
                return None
        return dict(cached)

    checks: dict[str, dict[str, Any]] = {}
    checks["meta_graph"] = reuse("meta_graph", "meta") or run_tool(
        "ndf_graphcheck.py",
        "--meta",
        "--format",
        "text",
        "--report",
        "-",
    )
    checks["product_graph"] = reuse("product_graph", "product") or run_tool(
        "ndf_graphcheck.py",
        "--product",
        "--format",
        "text",
        "--report",
        "-",
    )
    checks["index_consistency"] = reuse("index_consistency", "meta", "product") or run_tool(
        "ndf_index.py", "validate"
    )
    if active_poc_topic_ids():
        checks["binder_health"] = reuse("binder_health", "poc") or run_tool(
            "ndf_bindcheck.py",
            "check",
            "--all-topics",
            "--report",
            "-",
        )
    else:
        checks["binder_health"] = skipped_check(
            "no active POC topics; binder_health not applicable; trunk mode"
        )
    findings = project_check_findings(checks)
    generation_sha = source_generation_sha()
    payload = {
        "schema": "ndf-spec-health/v1",
        "generated_at": now_iso(),
        "snapshot_sha": generation_sha,
        "repo_head": git_head(),
        "state": "current",
        "layers": {
            "root": layers.get("root"),
            "meta": layers.get("meta"),
            "product": layers.get("product"),
            "poc": layers.get("poc"),
            "replay": layers.get("replay"),
        },
        "raw_checks": checks,
        "checks": {name: public_check(check) for name, check in checks.items()},
        "findings": findings,
        "next_actions": unique_actions(findings),
        "advisor": {
            "graph": "python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit",
            "bind": "python3 spec/meta/tools/ndf_advise.py plan --surface bind --low-hanging-fruit",
            "read_only": True,
        },
    }
    if persist:
        write_json_artifact(HEALTH_DIR / "spec.json", payload)
    hard_errors = sum(1 for item in findings if item["severity"] == "error")
    return payload, 1 if hard_errors else 0


def latest_spec_health(generation_sha: str) -> dict[str, Any] | None:
    payload = read_json_artifact(HEALTH_DIR / "spec.json")
    if payload is None:
        return None
    payload = dict(payload)
    payload["state"] = (
        "current" if payload.get("snapshot_sha") == generation_sha else "stale"
    )
    return payload


def ensure_spec_health(generation_sha: str | None = None) -> dict[str, Any]:
    sha = generation_sha or source_generation_sha()
    latest = latest_spec_health(sha)
    if latest and latest.get("state") == "current":
        return latest
    payload, _ = spec_health(persist=True)
    payload = dict(payload)
    payload["state"] = "current"
    return payload


def spec_graph_tool_checks(
    spec_health_view: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    checks = (spec_health_view or {}).get("checks") or {}
    result: dict[str, dict[str, Any]] = {}
    for name in GRAPH_CHECK_NAMES:
        raw = checks.get(name) or {}
        if not raw:
            result[name] = {
                "command": GRAPH_CHECK_COMMANDS[name],
                "exit_code": 1,
                "state": "not_run",
                "output": "spec_health missing",
            }
            continue
        exit_code = raw.get("exit_code")
        result[name] = {
            "command": raw.get("command") or GRAPH_CHECK_COMMANDS[name],
            "exit_code": 1 if exit_code is None else int(exit_code),
            "state": raw.get("state") or "unknown",
            "output": raw.get("summary") or raw.get("output") or "",
        }
    return result


def spec_graph_findings(
    spec_health_view: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    checks = spec_graph_tool_checks(spec_health_view)
    kind_by_name = {
        "meta_graph": "meta_graph_failed",
        "product_graph": "product_graph_failed",
    }
    for name, check in checks.items():
        if check.get("state") in {"passed", "not_applicable"} or check.get("exit_code") == 0:
            continue
        route = PROJECT_CHECK_ROUTES[name]
        findings.append(
            finding(
                scope="project",
                space="Design",
                kind=kind_by_name[name],
                severity="error",
                evidence=clean_markdown(check.get("output") or "", 360)
                or "graphcheck failed",
                repair_owner=route["repair_owner"],
                repair_task=route["repair_task"],
                allowed_write_root=route["allowed_write_root"],
                human_gate=route["human_gate"],
                plane=route["plane"],
            )
        )
    return findings


def spec_graph_dispatch_blockers(
    spec_health_view: dict[str, Any] | None,
    *,
    active: bool,
    checks: Mapping[str, Any],
) -> list[str]:
    if not active:
        return []
    blockers: list[str] = []
    meta = checks.get("meta_graph") or {}
    product = checks.get("product_graph") or {}

    def exit_code(check: Mapping[str, Any]) -> int:
        if "exit_code" not in check:
            return 1
        return int(check["exit_code"])

    if exit_code(product) != 0:
        blockers.append("product_graphcheck_failed")
    if exit_code(meta) != 0:
        blockers.append("meta_graphcheck_failed")
    if not (spec_health_view and spec_health_view.get("state") == "current"):
        blockers.append("spec_health_stale")
    return blockers


def contract_preflight_blockers(
    *,
    active: bool,
    gates: Mapping[str, Any],
    baseline_status: str,
    spaces: Mapping[str, Any],
    perf_passed: bool,
    isolation_passed: bool,
    context_valid: bool,
) -> list[str]:
    if not active:
        return ["topic_lifecycle_closed"]
    blockers: list[str] = []
    if gates["implementation_approval"]["state"] != "valid":
        blockers.append(
            f"implementation_gate:{gates['implementation_approval']['state']}"
        )
    if baseline_status == "stale":
        blockers.append("baseline_stale")
    impl_gaps = spaces.get("implementation", {}).get("gaps") or []
    if "missing_baseline_workspace" in impl_gaps or "no_topic_code" in impl_gaps:
        blockers.append("missing_baseline_workspace")
    if not perf_passed:
        blockers.append("perf_check_failed")
    if not isolation_passed:
        blockers.append("isolation_check_failed")
    if not context_valid:
        blockers.append("context_verify_failed")
    return blockers


def persisted_active_topic() -> str | None:
    state_path = ROOT / ".openclaw" / "state.json"
    if not state_path.is_file():
        return None
    try:
        data = json.loads(read_text(state_path))
    except json.JSONDecodeError:
        return None
    workspace = data.get("workspace")
    if isinstance(workspace, Mapping) and workspace.get("active_topic"):
        return str(workspace["active_topic"])
    if data.get("active_topic"):
        return str(data["active_topic"])
    return None


def retired_replay_projection() -> dict[str, Any]:
    """Empty Replay projection for daily path (ADR-META-004). Does not touch store."""
    return {
        "schema": "ndf-replay-summary/v1",
        "state": "retired",
        "storeRoot": ".ndf/replay",
        "fsck": None,
        "episodes": [],
        "focused": None,
        "buttonActions": [],
        "note": "Episode/Replay retired from hot path; historical .ndf/replay is read-only archaeology",
    }


def replay_summary(
    *,
    focused_id: str | None = None,
    active_topic: str | None = None,
) -> dict[str, Any]:
    """Daily snapshot: retired stub. Does not read or write ReplayStore."""
    del focused_id, active_topic
    return retired_replay_projection()


def snapshot(
    topic: str | None,
    probe_runtime: bool | str = False,
    replay_episode: str | None = None,
) -> dict[str, Any]:
    """Commander/canvas snapshot retired (ADR-META-004). Prefer topic-health."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "snapshot",
        "deprecated": True,
        "reason": "ADR-META-004",
        "topic": topic,
        "probe_runtime": probe_runtime,
        "replay_episode": replay_episode,
        "enabledActions": [],
        "replay": retired_replay_projection(),
        "note": "Use topic-health / poc-dispatch; canvas projection removed",
    }


def canvas_snapshot_buckets(payload: Mapping[str, Any]) -> dict[str, int]:
    """Retired with Commander canvas (ADR-META-004)."""
    del payload
    return {}


def canvas_snapshot_budget_error(payload: Mapping[str, Any], encoded_len: int) -> str | None:
    """Retired with Commander canvas (ADR-META-004)."""
    del payload, encoded_len
    return None


def apply_canvas_snapshot_budget(payload: dict[str, Any]) -> dict[str, Any]:
    """Retired with Commander canvas (ADR-META-004)."""
    return dict(payload)


def canvas_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Commander canvas projection retired (ADR-META-004)."""
    return {
        "schema": "ndf-commander-retired/v1",
        "deprecated": True,
        "reason": "ADR-META-004",
        "enabledActions": [],
        "replay": retired_replay_projection(),
        "note": "canvas_snapshot retired; use topic-health / poc-dispatch",
        "inputKeys": sorted(str(k) for k in payload.keys())[:32] if isinstance(payload, Mapping) else [],
    }


def canvas_payload_sha(payload: Mapping[str, Any]) -> str:
    """Retired helper kept for import compatibility."""
    return canonical_json_sha(dict(payload) if isinstance(payload, Mapping) else {})


def verify_embedded_snapshot(
    path: Path,
    *,
    topic: str | None = None,
    replay_episode: str | None = None,
) -> dict[str, Any]:
    """Commander embedded SNAPSHOT retired (ADR-META-004)."""
    del path, topic, replay_episode
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "snapshot --verify-embedded",
        "deprecated": True,
        "valid": False,
        "reason": "ADR-META-004",
    }


def write_commander_snapshot(payload: Mapping[str, Any], path: Path | None = None) -> Path:
    """Retired: write a thin retired marker instead of canvas projection."""
    out = path or (ROOT / "tmp" / "ndf-canvas-snapshot.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": "ndf-commander-retired/v1",
        "deprecated": True,
        "reason": "ADR-META-004",
        "note": "commander snapshot write retired",
        "payloadKeys": sorted(str(k) for k in payload.keys())[:32],
    }
    out.write_text(
        json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def write_live_commander_snapshot(topic: str | None = None) -> dict[str, Any]:
    """Commander live snapshot retired (ADR-META-004)."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "write_live_commander_snapshot",
        "deprecated": True,
        "reason": "ADR-META-004",
        "topic": topic,
    }


def persist_dispatch_pack(payload: Mapping[str, Any]) -> Path:
    """Write pack JSON for Command Agent dispatch-send (human 「派发」 round)."""
    DISPATCH_PACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    DISPATCH_PACK_PATH.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    return DISPATCH_PACK_PATH


def close_unsent_started_action() -> dict[str, Any] | None:
    """Stop-hook backstop retired with ActionSpec (ADR-META-004)."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "close_unsent_started_action",
        "deprecated": True,
        "reason": "ADR-META-004",
        "skipped": "action_spec_retired",
    }


def read_cgroup_pids(pid: int | None = None) -> dict[str, Any]:
    """Read cgroup v2 pids.current/max for *pid* (default: self). Threads count."""
    target = int(pid or os.getpid())
    cgroup_file = Path(f"/proc/{target}/cgroup")
    result: dict[str, Any] = {
        "pid": target,
        "cgroup": None,
        "current": None,
        "max": None,
        "free": None,
        "available": False,
        "error": None,
    }
    try:
        text = cgroup_file.read_text(encoding="utf-8")
    except OSError as exc:
        result["error"] = f"cgroup_unreadable:{exc}"
        return result
    rel = None
    for line in text.splitlines():
        # v2: "0::/user.slice/..."
        if line.startswith("0::"):
            rel = line.split("::", 1)[1].strip()
            break
        if ":pids:" in line:
            rel = line.split(":pids:", 1)[1].strip()
            break
    if not rel:
        result["error"] = "cgroup_path_missing"
        return result
    base = Path("/sys/fs/cgroup") / rel.lstrip("/")
    result["cgroup"] = str(base)
    try:
        current = int((base / "pids.current").read_text(encoding="utf-8").strip())
        max_raw = (base / "pids.max").read_text(encoding="utf-8").strip()
    except OSError as exc:
        result["error"] = f"pids_unreadable:{exc}"
        return result
    result["current"] = current
    if max_raw == "max":
        result["max"] = None
        result["free"] = None
        result["available"] = True
        result["error"] = None
        return result
    try:
        maximum = int(max_raw)
    except ValueError:
        result["error"] = f"pids_max_invalid:{max_raw}"
        return result
    result["max"] = maximum
    result["free"] = max(0, maximum - current)
    result["available"] = True
    return result


def _proc_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _proc_comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _proc_nthreads(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Threads:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _proc_cgroup_rel(pid: int) -> str:
    try:
        text = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("0::"):
            return line.split("::", 1)[1].strip()
        if ":pids:" in line:
            return line.split(":pids:", 1)[1].strip()
    return ""


def is_chromium_cgroup_path(path: str | None) -> bool:
    """True when *path* is under a Chromium/Cursor app slice (TasksMax shared with Agent)."""
    if not path:
        return False
    return CHROMIUM_CGROUP_MARKER in str(path)


def self_in_chromium_cgroup() -> bool:
    stats = read_cgroup_pids()
    return is_chromium_cgroup_path(str(stats.get("cgroup") or ""))


def read_cgroup_pids_at_path(cgroup_path: str) -> dict[str, Any]:
    """Read pids.current/max for an absolute cgroup path (or /sys/fs/cgroup + rel)."""
    result: dict[str, Any] = {
        "pid": None,
        "cgroup": None,
        "current": None,
        "max": None,
        "free": None,
        "available": False,
        "error": None,
    }
    base = Path(cgroup_path)
    if not base.is_absolute():
        base = Path("/sys/fs/cgroup") / str(cgroup_path).lstrip("/")
    result["cgroup"] = str(base)
    try:
        current = int((base / "pids.current").read_text(encoding="utf-8").strip())
        max_raw = (base / "pids.max").read_text(encoding="utf-8").strip()
    except OSError as exc:
        result["error"] = f"pids_unreadable:{exc}"
        return result
    result["current"] = current
    if max_raw == "max":
        result["max"] = None
        result["free"] = None
        result["available"] = True
        return result
    try:
        maximum = int(max_raw)
    except ValueError:
        result["error"] = f"pids_max_invalid:{max_raw}"
        return result
    result["max"] = maximum
    result["free"] = max(0, maximum - current)
    result["available"] = True
    return result


def find_chromium_cgroup_slices() -> list[dict[str, Any]]:
    """Locate live app-org.chromium.Chromium-*.scope dirs under user@*/app.slice."""
    roots = Path("/sys/fs/cgroup")
    found: list[dict[str, Any]] = []
    try:
        user_slices = list(roots.glob("user.slice/user-*.slice/user@*.service/app.slice"))
    except OSError:
        return found
    for app_slice in user_slices:
        try:
            children = list(app_slice.iterdir())
        except OSError:
            continue
        for child in children:
            name = child.name
            if not name.startswith(CHROMIUM_CGROUP_MARKER) or not name.endswith(".scope"):
                continue
            if not child.is_dir():
                continue
            stats = read_cgroup_pids_at_path(str(child))
            found.append(stats)
    found.sort(key=lambda row: int(row.get("current") or 0), reverse=True)
    return found


def classify_host_pid_kind(cmdline: str, comm: str = "") -> str:
    """Map a process to consumer bucket for host-pids attribution."""
    tokens = cmdline.split() if cmdline else []
    if any(tok.endswith("ndf_workflow_status.py") for tok in tokens):
        if "--serve" in tokens:
            return "ndf_serve"
        return "ndf_workflow_status"
    if any("qemu-system" in tok for tok in tokens):
        return "qemu"
    if any(tok.endswith("ndf_replay.py") for tok in tokens) and any(
        tok in {"guest-run", "guest-probe", "guest-image"} or tok.startswith("guest-")
        for tok in tokens
    ):
        return "ndf_replay_guest"
    lowered = f"{cmdline} {comm}".lower()
    if (
        "chromium" in lowered
        or "cursor" in lowered
        or "chrome" in lowered
        or CHROMIUM_CGROUP_MARKER.lower() in lowered
    ):
        return "chromium_or_cursor"
    return "other"


def list_host_pid_suspects() -> list[dict[str, Any]]:
    """Scan /proc for local NDF serve / workflow / qemu without spawning pgrep."""
    suspects: list[dict[str, Any]] = []
    proc_root = Path("/proc")
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return suspects
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline = _proc_cmdline(pid)
        if not cmdline:
            continue
        # Cursor agent shells embed prior argv in a policy wrapper; skip those.
        if "cursorsandbox" in cmdline or "snap=$(command cat" in cmdline:
            continue
        kind = classify_host_pid_kind(cmdline)
        if kind not in {
            "ndf_serve",
            "ndf_workflow_status",
            "qemu",
            "ndf_replay_guest",
        }:
            continue
        # Preserve prior kind labels for NDF workflow (non-serve).
        if kind == "ndf_workflow_status":
            report_kind = "ndf_workflow_status"
        elif kind == "ndf_serve":
            report_kind = "ndf_workflow_serve"
        elif kind == "qemu":
            report_kind = "qemu-system"
        else:
            report_kind = kind
        suspects.append(
            {
                "pid": pid,
                "kind": report_kind,
                "cmdline": cmdline[:240],
                "threads": _proc_nthreads(pid),
            }
        )
    suspects.sort(key=lambda row: (row["kind"], row["pid"]))
    return suspects


def collect_cgroup_consumers(
    cgroup_path: str | None,
    *,
    top_n: int = 15,
) -> dict[str, Any]:
    """Top thread consumers and bucket counts for processes in *cgroup_path*."""
    empty: dict[str, Any] = {
        "cgroup": cgroup_path,
        "top": [],
        "counts": {
            "chromium_or_cursor": 0,
            "ndf_serve": 0,
            "ndf_replay_guest": 0,
            "qemu": 0,
            "ndf_workflow_status": 0,
            "other": 0,
        },
        "thread_sums": {
            "chromium_or_cursor": 0,
            "ndf_serve": 0,
            "ndf_replay_guest": 0,
            "qemu": 0,
            "ndf_workflow_status": 0,
            "other": 0,
        },
    }
    if not cgroup_path:
        return empty
    target_abs = Path(cgroup_path)
    if not target_abs.is_absolute():
        target_abs = Path("/sys/fs/cgroup") / str(cgroup_path).lstrip("/")
    target_abs = target_abs.resolve() if target_abs.exists() else target_abs
    rows: list[dict[str, Any]] = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return empty
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        rel = _proc_cgroup_rel(pid)
        if not rel:
            continue
        abs_cg = Path("/sys/fs/cgroup") / rel.lstrip("/")
        try:
            same = abs_cg.resolve() == target_abs or abs_cg == target_abs
        except OSError:
            same = abs_cg == target_abs
        if not same:
            continue
        cmdline = _proc_cmdline(pid)
        if "cursorsandbox" in cmdline or "snap=$(command cat" in cmdline:
            continue
        comm = _proc_comm(pid)
        threads = _proc_nthreads(pid)
        if threads <= 0 and not cmdline:
            continue
        kind = classify_host_pid_kind(cmdline, comm)
        if kind == "other" and is_chromium_cgroup_path(str(abs_cg)):
            kind = "chromium_or_cursor"
        bucket = kind if kind in empty["counts"] else "other"
        empty["counts"][bucket] += 1
        empty["thread_sums"][bucket] += threads
        rows.append(
            {
                "pid": pid,
                "comm": comm,
                "threads": threads,
                "kind": bucket,
                "ndf": bucket
                in {"ndf_serve", "ndf_replay_guest", "ndf_workflow_status"},
                "cmdline": cmdline[:160],
            }
        )
    rows.sort(key=lambda row: int(row.get("threads") or 0), reverse=True)
    empty["top"] = rows[: max(1, int(top_n))]
    return empty


def host_pid_advice(
    *,
    self_stats: Mapping[str, Any],
    chromium_stats: Mapping[str, Any] | None,
    consumers: Mapping[str, Any] | None,
    min_free_action: int = HOST_PID_MIN_FREE_ACTION,
    min_free_serve: int = HOST_PID_MIN_FREE_SERVE,
) -> str:
    """Branching advice: do not blame leftover serve when Chromium owns the budget."""
    thread_sums = (consumers or {}).get("thread_sums") or {}
    ndf_threads = int(thread_sums.get("ndf_serve") or 0) + int(
        thread_sums.get("ndf_replay_guest") or 0
    )
    qemu_threads = int(thread_sums.get("qemu") or 0)
    chrome_threads = int(thread_sums.get("chromium_or_cursor") or 0)
    focus = chromium_stats if chromium_stats and chromium_stats.get("available") else self_stats
    free = focus.get("free")
    maximum = focus.get("max")
    if free is None:
        return "headroom ok or unlimited"
    free_i = int(free)
    ndf_qemu = ndf_threads + qemu_threads
    chrome_dominant = chrome_threads >= max(ndf_qemu * 10, 100) or (
        maximum is not None and free_i < int(min_free_serve) and ndf_qemu < 64
    )
    if free_i < int(min_free_action):
        if chrome_dominant:
            return (
                "Chromium/Cursor TasksMax nearly full (NDF serve/qemu negligible); "
                "close Cursor tabs / stop Composer-started leftover serve; "
                "run live --serve only from an external terminal; "
                "use snapshot --out from Command Agent; "
                "do not raise TasksMax; do not switch to cloud agents"
            )
        return (
            "free PIDs/threads under cgroup limit; stop leftover "
            "`snapshot --serve` and qemu guests; do not raise TasksMax as the fix; "
            "do not switch to cloud agents"
        )
    if free_i < int(min_free_serve) and chrome_dominant:
        return (
            "action-begin headroom ok but Chromium slice tight for --serve; "
            "do not start snapshot --serve inside Chromium; "
            "Command Agent: snapshot --out only; live panel from external terminal"
        )
    return "headroom ok or unlimited"


def read_serve_lock(path: Path | None = None) -> dict[str, Any] | None:
    lock_path = path or SERVE_LOCK_PATH
    if not lock_path.is_file():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def serve_lock_holder_alive(lock: Mapping[str, Any] | None) -> bool:
    if not lock:
        return False
    try:
        pid = int(lock.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or not _pid_alive(pid):
        return False
    # Same process that wrote the lock still holds it (tests / re-entry).
    if pid == os.getpid():
        return True
    cmdline = _proc_cmdline(pid)
    return "ndf_workflow_status.py" in cmdline and "--serve" in cmdline


def _serve_already_running_error(existing: Mapping[str, Any] | None, port: int, lock_path: Path) -> ValueError:
    holder = existing or {}
    url = f"http://127.0.0.1:{int(holder.get('port') or port)}/"
    return ValueError(
        f"serve_already_running: pid={holder.get('pid')} url={url} "
        f"lock={lock_path}"
    )


def acquire_serve_lock(port: int, path: Path | None = None) -> dict[str, Any]:
    """Claim singleton --serve. Raises ValueError if another live serve holds the lock.

    Uses non-blocking ``fcntl.flock`` so two processes cannot both win a TOCTOU race
    on the lock file. The FD is kept open until ``release_serve_lock``.
    """
    global _SERVE_LOCK_FD
    lock_path = path or SERVE_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_serve_lock(lock_path)
    if serve_lock_holder_alive(existing):
        raise _serve_already_running_error(existing, port, lock_path)

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise _serve_already_running_error(read_serve_lock(lock_path), port, lock_path) from None
    except Exception:
        os.close(fd)
        raise

    # Same-process re-entry: flock is per-process on Linux, so re-check metadata.
    if _SERVE_LOCK_FD is not None and _SERVE_LOCK_FD != fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
        raise _serve_already_running_error(read_serve_lock(lock_path), port, lock_path)

    payload = {
        "schema": "ndf-commander-serve-lock/v1",
        "pid": os.getpid(),
        "port": int(port),
        "repo_root": str(ROOT),
        "started_at": now_iso(),
    }
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, raw)
        os.fsync(fd)
    except Exception:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
        raise
    _SERVE_LOCK_FD = fd
    return payload


def release_serve_lock(path: Path | None = None, *, pid: int | None = None) -> bool:
    global _SERVE_LOCK_FD
    lock_path = path or SERVE_LOCK_PATH
    lock = read_serve_lock(lock_path)
    if not lock and _SERVE_LOCK_FD is None:
        return False
    holder = int((lock or {}).get("pid") or 0)
    if pid is not None and holder and holder != int(pid):
        return False
    if holder and holder != os.getpid() and serve_lock_holder_alive(lock):
        return False
    if _SERVE_LOCK_FD is not None:
        try:
            fcntl.flock(_SERVE_LOCK_FD, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(_SERVE_LOCK_FD)
        except OSError:
            pass
        _SERVE_LOCK_FD = None
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def kill_stale_serve(*, path: Path | None = None, force_pid: int | None = None) -> dict[str, Any]:
    """Kill only this repo's stale/live --serve holders explicitly requested."""
    lock_path = path or SERVE_LOCK_PATH
    killed: list[dict[str, Any]] = []
    lock = read_serve_lock(lock_path)
    targets: list[int] = []
    if force_pid:
        targets.append(int(force_pid))
    elif lock and lock.get("pid"):
        try:
            targets.append(int(lock["pid"]))
        except (TypeError, ValueError):
            pass
    for pid in targets:
        cmdline = _proc_cmdline(pid)
        if "ndf_workflow_status.py" not in cmdline:
            continue
        if str(ROOT) not in cmdline and "ndf_workflow_status.py" not in cmdline:
            continue
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, 15)
            killed.append({"pid": pid, "signal": 15, "cmdline": cmdline[:240]})
        except OSError as exc:
            killed.append({"pid": pid, "error": str(exc)})
    release_serve_lock(lock_path, pid=None)
    # Clear lock even if holder already dead.
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass
    return {"killed": killed, "lock_cleared": True}


def ensure_host_pid_headroom(
    min_free: int = HOST_PID_MIN_FREE_SERVE,
    *,
    purpose: str = "serve",
) -> dict[str, Any]:
    """Fail closed when cgroup free PIDs/threads are below *min_free*.

    *purpose* is included in the error so callers can tell serve vs action-begin.
    """
    stats = read_cgroup_pids()
    if not stats.get("available"):
        # Non-Linux / missing cgroup: do not block; report only.
        return {"ok": True, "skipped": True, "stats": stats, "purpose": purpose}
    free = stats.get("free")
    if free is None:
        return {"ok": True, "skipped": True, "stats": stats, "purpose": purpose}
    if int(free) < int(min_free):
        raise ValueError(
            f"{HOST_PID_EXHAUSTED}: free={free} < min_free={min_free} "
            f"purpose={purpose} cgroup={stats.get('cgroup')} "
            f"current={stats.get('current')} max={stats.get('max')}; "
            f"run host-pids --json; if Chromium owns the budget close Cursor tabs "
            f"and use snapshot --out / external-terminal --serve "
            f"(do not raise TasksMax; do not switch to cloud)"
        )
    return {"ok": True, "skipped": False, "stats": stats, "purpose": purpose}


def ensure_action_pid_headroom() -> dict[str, Any]:
    """Fail closed only when fork is about to EAGAIN (tight action reserve)."""
    return ensure_host_pid_headroom(HOST_PID_MIN_FREE_ACTION, purpose="action-begin")


def ensure_serve_pid_headroom() -> dict[str, Any]:
    """Reject --serve inside Chromium scope; otherwise require serve reserve."""
    stats = read_cgroup_pids()
    cg = str(stats.get("cgroup") or "")
    if is_chromium_cgroup_path(cg):
        raise ValueError(
            f"{HOST_PID_CHROMIUM_SERVE_FORBIDDEN}: refuse snapshot --serve inside "
            f"Chromium/Cursor cgroup ({cg}); run --serve from an external terminal "
            f"outside app-org.chromium.Chromium-*.scope, or Command Agent: "
            f"snapshot --out tmp/ndf-canvas-snapshot.json only"
        )
    return ensure_host_pid_headroom(HOST_PID_MIN_FREE_SERVE, purpose="serve")


def host_pids_report(*, kill_stale: bool = False) -> dict[str, Any]:
    stats = read_cgroup_pids()
    chromium_slices = find_chromium_cgroup_slices()
    chromium = chromium_slices[0] if chromium_slices else None
    # Prefer Chromium slice for consumer attribution when present; else self.
    focus_path = None
    if chromium and chromium.get("cgroup"):
        focus_path = str(chromium["cgroup"])
    elif stats.get("cgroup"):
        focus_path = str(stats["cgroup"])
    consumers = collect_cgroup_consumers(focus_path)
    suspects = list_host_pid_suspects()
    lock = read_serve_lock()
    killed = kill_stale_serve() if kill_stale else None
    free = stats.get("free")
    chrome_free = chromium.get("free") if chromium else None
    headroom_action_ok = free is None or (
        stats.get("available") and int(free) >= HOST_PID_MIN_FREE_ACTION
    )
    headroom_serve_ok = (not is_chromium_cgroup_path(str(stats.get("cgroup") or ""))) and (
        free is None or (stats.get("available") and int(free) >= HOST_PID_MIN_FREE_SERVE)
    )
    # Legacy headroom_ok: action-begin threshold (Composer truth).
    headroom_ok = headroom_action_ok
    if chrome_free is not None and int(chrome_free) < HOST_PID_MIN_FREE_ACTION:
        # Surface Chromium tightness even when outer-terminal self looks fine.
        headroom_ok = False
    advice = host_pid_advice(
        self_stats=stats,
        chromium_stats=chromium,
        consumers=consumers,
    )
    return {
        "schema": "ndf-host-pids/v1",
        "generated_at": now_iso(),
        "cgroup": stats,
        "chromium_cgroup": chromium,
        "chromium_slices": chromium_slices,
        "self_in_chromium": is_chromium_cgroup_path(str(stats.get("cgroup") or "")),
        "consumers": consumers,
        "min_free": HOST_PID_MIN_FREE_SERVE,
        "min_free_serve": HOST_PID_MIN_FREE_SERVE,
        "min_free_action": HOST_PID_MIN_FREE_ACTION,
        "headroom_ok": headroom_ok,
        "headroom_action_ok": headroom_action_ok,
        "headroom_serve_ok": headroom_serve_ok,
        "serve_lock": lock,
        "serve_lock_alive": serve_lock_holder_alive(lock),
        "suspects": suspects,
        "kill_stale": killed,
        "advice": advice,
    }


def ensure_cockpit_dist_built(*, force: bool = False) -> dict[str, Any]:
    """Commander cockpit retired (ADR-META-004). No-op stub."""
    return {
        "built": False,
        "reason": "commander_retired",
        "dist": None,
        "force": bool(force),
    }


def serve_commander(
    *,
    topic: str | None,
    probe_runtime: bool,
    replay_episode: str | None,
    out: Path,
    port: int,
    event_interval: float = 0.5,
) -> dict[str, Any]:
    """Commander --serve retired (ADR-META-004)."""
    raise RuntimeError(
        "snapshot --serve is deprecated (ADR-META-004). "
        "Use .cursor/skills/ndf-workflow/ + poc-dispatch. "
        f"(ignored topic={topic!r} port={port} out={out} "
        f"probe={probe_runtime} episode={replay_episode} interval={event_interval})"
    )



def update_embedded_snapshot(
    path: Path,
    *,
    topic: str | None = None,
    probe_runtime: bool = False,
    replay_episode: str | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    """Commander embedded SNAPSHOT retired (ADR-META-004)."""
    del path, topic, probe_runtime, replay_episode, out
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "snapshot --update-embedded",
        "deprecated": True,
        "updated": False,
        "reason": "ADR-META-004",
    }


def record_projection_verification(
    source_path: Path,
    verification: Mapping[str, Any],
    *,
    topic: str | None = None,
    episode_id: str | None = None,
) -> dict[str, Any]:
    """Projection verification retired with Commander (ADR-META-004)."""
    del source_path, verification, topic, episode_id
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "record_projection_verification",
        "deprecated": True,
        "reason": "ADR-META-004",
    }


def pack_topic(topic: str, episode_id: str | None = None) -> tuple[dict[str, Any], int]:
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    ensure_spec_health()
    view = topic_view(topic_dir)
    bundles = poc_gate_bundle_specs(topic_dir)
    files = []
    for name in POC_FILES:
        path = topic_dir / "ndf" / name
        if path.is_file():
            files.append({"path": rel(path), "sha256": file_sha(path)})
    approval = view["gates"]["implementation_approval"]
    static_ready = view["delegation"]["static_preflight_passed"]
    runtime, runtime_ready, lease = implementation_dispatch_runtime(topic)
    active_lease_ok, _active_lease = active_isolated_lease_for_topic(topic)
    truth = workspace_truth_view(topic)
    workspace_bound = bool(truth.get("workspace_bound"))
    safe_to_delegate = static_ready
    safe_to_dispatch = static_ready and active_lease_ok and workspace_bound
    static_blockers = [
        reason
        for reason in (view["delegation"].get("dispatch_blockers") or [])
        if reason
        not in {
            "runtime_unavailable",
            "topic_active_lease",
            "lease_stale_vs_head",
            "runtime_not_probed",
            "missing_active_isolated_lease",
        }
    ]
    role_blockers = roles_dispatch_blockers()
    blockers = [
        *([] if static_ready else static_blockers),
        *(["workspace_unbound"] if not workspace_bound else []),
        *([] if active_lease_ok else ["missing_active_isolated_lease"]),
        *(
            ["runtime_unavailable"]
            if not runtime_ready and not lease
            else []
        ),
        *(
            ["lease_stale_vs_head"]
            if lease and lease_stale_vs_head(lease)
            else []
        ),
        *(
            ["topic_active_lease"]
            if lease
            and not active_lease_ok
            and not lease_stale_vs_head(lease)
            else []
        ),
        *role_blockers,
    ]
    if role_blockers:
        safe_to_dispatch = False
    payload = {
        "schema": "ndf-workflow-pack/v2",
        "compatibility": {"legacy_schema": "ndf-workflow-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": "poc_implementation",
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": workspace_truth_view(topic),
        "allowed_write_root": f"poc/{topic}/",
        "allowed_sections": (
            (view["delegation"].get("context_plan") or {})
            .get("privileges", {})
            .get("allowed_sections", [])
        ),
        "mutable_sections": list(ndf_gate_slices.MUTABLE_SECTIONS),
        "forbidden": ["src/", "include/", "tests/", "spec/meta/", "stable SLA"],
        "read_order": files,
        "gate_receipt": approval,
        "approved_bundle_sha": bundles["implementation_approval"].get(
            "expected_content_sha"
        ),
        "gate_bundle": bundles["implementation_approval"],
        "spaces": view["spaces"],
        "preflight": {
            "perf_baseline": view["health"]["checks"]["perf_baseline"],
            "isolation": view["health"]["checks"]["isolation"],
        },
        "context_plan": view["delegation"]["context_plan"],
        "context_verify": view["delegation"]["context_verify"],
        "task_manifest": view["delegation"]["task_manifest"],
        "manifest_sha": view["delegation"]["manifest_sha"],
        "plan_sha": view["delegation"]["plan_sha"],
        "static_preflight_passed": static_ready,
        "contract_preflight_passed": view["delegation"].get("contract_preflight_passed"),
        "active_isolated_lease": active_lease_ok,
        "runtime_dispatch_ready": runtime_ready,
        "next_action": view["phase_hint"],
        "safe_to_delegate": safe_to_delegate,
        "safe_to_dispatch": safe_to_dispatch,
        "blockers": blockers,
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
    }
    payload = _with_completion_receipt_path(payload)
    apply_acp_context_budget_to_pack(payload)
    return bind_pack_to_episode(payload, episode_id=episode_id), (
        0 if payload.get("safe_to_dispatch") else 1
    )


def pack_prepare_acp_lease(
    topic: str, episode_id: str | None = None
) -> tuple[dict[str, Any], int]:
    """Lease-prep pack: contract preflight only; does not require active lease."""
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    ensure_spec_health()
    view = topic_view(topic_dir)
    truth = workspace_truth_view(topic)
    workspace_bound = bool(truth.get("workspace_bound"))
    contract_ready = bool(view["delegation"].get("contract_preflight_passed"))
    active_lease_ok, _active_lease = active_isolated_lease_for_topic(topic)
    runtime, runtime_ready, _lease = implementation_dispatch_runtime(topic)
    blockers = [
        reason
        for reason in (
            None if contract_ready else "contract_preflight_failed",
            None if workspace_bound else "workspace_unbound",
            "topic_active_lease" if active_lease_ok else None,
        )
        if reason
    ]
    safe_to_dispatch = contract_ready and workspace_bound and not active_lease_ok
    payload = {
        "schema": "ndf-workflow-pack/v2",
        "compatibility": {"legacy_schema": "ndf-workflow-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": "prepare_acp_lease",
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": truth,
        "allowed_write_root": f"poc/{topic}/",
        "contract_preflight_passed": contract_ready,
        "active_isolated_lease": active_lease_ok,
        "runtime_dispatch_ready": runtime_ready,
        "safe_to_delegate": contract_ready,
        "safe_to_dispatch": safe_to_dispatch,
        "blockers": blockers,
        "required_handshake": [
            "base_sha",
            "repo_root",
            "allowed_write_root",
        ],
    }
    apply_acp_context_budget_to_pack(payload)
    return bind_pack_to_episode(payload, episode_id=episode_id), (
        0 if payload.get("safe_to_dispatch") else 1
    )


def _with_completion_receipt_path(payload: dict[str, Any]) -> dict[str, Any]:
    import ndf_dispatch_send as dispatch

    payload["completion_receipt_path"] = dispatch.completion_receipt_path_for_pack(payload)
    return payload


def evaluate_execution_capabilities(
    *,
    catalog_action_id: str | None,
    task: str | None = None,
    topic: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Static + env capability receipt for dispatch readiness (META-011).

    Does not claim live worktree existence; marks missing approvals as
    ``waiting_human`` blockers rather than pretending transport is enough.
    """
    catalog_id = (catalog_action_id or "").strip()
    # ActionSpec retired — capability defaults by provider/task only.
    action: Mapping[str, Any] | None = None
    required = list((action or {}).get("requiredCapabilities") or [])
    if not required and provider == "claude-code-acp":
        required = ["transport", "write_poc_ndf", "isolated_worktree"]
    if not required and task == "poc_measurement":
        required = ["transport", "write_poc_ndf", "run_sustained"]
    missing: list[str] = []
    waiting: list[str] = []
    present: list[str] = []
    receipt_path = ROOT / "tmp" / "ndf-capability-receipt.json"
    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                receipt = loaded
        except json.JSONDecodeError:
            receipt = {}
    approved = set(str(x) for x in (receipt.get("approved_capabilities") or []) if str(x).strip())
    env_approve = {
        item.strip()
        for item in str(os.environ.get("NDF_CAPABILITY_APPROVED") or "").split(",")
        if item.strip()
    }
    approved |= env_approve
    for cap in required:
        if cap == "transport":
            present.append(cap)
            continue
        if cap in {"sudo_cgroup", "run_sustained", "command_allowlist"}:
            if cap in approved or os.environ.get("NDF_HARNESS_APPROVED") == "1":
                present.append(cap)
            else:
                waiting.append(cap)
                missing.append(cap)
            continue
        if cap == "lease":
            # Lease acquisition is a separate hop; presence of capability means
            # caller accepts lease-only dispatch.
            present.append(cap)
            continue
        if cap in {"write_poc_ndf", "isolated_worktree"}:
            # Declared by pack allowed_write_root + ACP handshake; static OK.
            present.append(cap)
            continue
        if cap in approved:
            present.append(cap)
        else:
            missing.append(cap)
    ready = not missing
    return {
        "schema": "ndf-execution-capabilities/v1",
        "catalog_action_id": catalog_id or None,
        "topic": topic,
        "required": required,
        "present": present,
        "missing": missing,
        "waiting_human": waiting,
        "execution_capabilities_ready": ready,
        "state": (
            "ready"
            if ready
            else ("waiting_human" if waiting else "capability_missing")
        ),
    }


def capability_approve(
    catalog_action_id: str,
    capabilities: list[str],
    *,
    approved_by: str = "human",
    topic: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Capability approvals retired with ActionSpec (ADR-META-004)."""
    return {
        "schema": "ndf-commander-retired/v1",
        "command": "capability-approve",
        "deprecated": True,
        "reason": "ADR-META-004",
        "catalog_action_id": catalog_action_id,
        "capabilities": list(capabilities or []),
        "approved_by": approved_by,
        "topic": topic,
        "note": note,
    }


def repair_pack(
    topic: str,
    task: str,
    episode_id: str | None = None,
    action_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    if task not in IMPLEMENTATION_REPAIR_TASKS:
        raise ValueError(f"unknown implementation repair task: {task}")
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    view = topic_view(topic_dir)
    approval_valid = view["gates"]["implementation_approval"]["state"] == "valid"
    bind_ready = perf_bind_ready(view.get("perf"))
    active = view["lifecycle"] in {"exploring", "blocked"}
    context = context_binding(topic=topic, role="claude-code", task=task, track="poc")
    context_valid = bool(context["context_verify"].get("valid"))
    runtime, runtime_ready, lease = implementation_dispatch_runtime(topic)
    if task == "poc_measurement":
        static_ready = active and approval_valid and bind_ready and context_valid
        blockers = [
            reason
            for reason in (
                None if approval_valid else "implementation_gate_not_valid",
                None if bind_ready else "perf_binding_not_ready",
                None if active else "topic_lifecycle_closed",
                None if context_valid else "context_verify_failed",
            )
            if reason
        ]
    elif task == "poc_prepare_baseline":
        impl_gaps = (view.get("spaces") or {}).get("implementation", {}).get("gaps") or []
        baseline_missing = (
            "missing_baseline_workspace" in impl_gaps or "no_topic_code" in impl_gaps
        )
        static_ready = active and approval_valid and baseline_missing and context_valid
        blockers = [
            reason
            for reason in (
                None if active else "topic_lifecycle_closed",
                None if approval_valid else "implementation_gate_not_valid",
                None if baseline_missing else "baseline_already_present",
                None if context_valid else "context_verify_failed",
            )
            if reason
        ]
    else:
        isolation_failed = (
            view["health"]["checks"]["isolation"]["state"] == "failed"
            or any(
                item.get("repair_task") == "poc_isolation_repair"
                for item in view["health"].get("findings", [])
            )
        )
        static_ready = active and isolation_failed and context_valid
        blockers = [
            reason
            for reason in (
                None if active else "topic_lifecycle_closed",
                None if isolation_failed else "isolation_finding_missing",
                None if context_valid else "context_verify_failed",
            )
            if reason
        ]
    if not runtime["pipeline_reachable"]:
        blockers.append("runtime_unavailable")
    if lease:
        blockers.append("topic_active_lease")
    truth = workspace_truth_view(topic)
    if not truth.get("workspace_bound"):
        blockers.append("workspace_unbound")
    runtime_ready = runtime_ready and bool(truth.get("workspace_bound"))
    caps = evaluate_execution_capabilities(
        catalog_action_id=None,
        task=task,
        topic=topic,
        provider="claude-code-acp",
    )
    caps_ready = bool(caps.get("execution_capabilities_ready"))
    if not caps_ready:
        for miss in caps.get("missing") or []:
            blockers.append(f"capability_missing:{miss}")
        if caps.get("waiting_human"):
            blockers.append("waiting_human")
    lease_acquired = bool(lease) is False  # no conflicting lease; acquisition is worker-side
    safe_to_dispatch = (
        static_ready and runtime_ready and caps_ready
    )
    payload = {
        "schema": "ndf-implementation-repair-pack/v2",
        "compatibility": {"legacy_schema": "ndf-implementation-repair-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": task,
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": truth,
        "allowed_write_root": f"poc/{topic}/",
        "forbidden": [
            "src/",
            "include/",
            "tests/",
            "spec/meta/",
            "stable SLA",
            "git history rewrite",
        ],
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": safe_to_dispatch,
        "static_preflight_passed": static_ready,
        "transport_reachable": bool(runtime.get("pipeline_reachable")),
        "runtime_dispatch_ready": runtime_ready,
        "execution_capabilities_ready": caps_ready,
        "lease_acquired": lease_acquired,
        "capabilities": caps,
        "dispatch_state": (
            "waiting_human"
            if caps.get("waiting_human") and static_ready and runtime_ready
            else ("ready" if safe_to_dispatch else "blocked")
        ),
        "catalog_action_id": None,  # ActionSpec retired (ADR-META-004)
        **context,
        "blockers": blockers,
        "human_gate": (
            "人工确认 destructive git disposition"
            if task == "poc_isolation_repair"
            else (
                "批准 sustained harness / sudo_cgroup（写入 tmp/ndf-capability-receipt.json "
                "或 NDF_HARNESS_APPROVED=1）"
                if task == "poc_measurement" and caps.get("waiting_human")
                else None
            )
        ),
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
        "post_checks": [
            f"python3 spec/meta/tools/ndf_poc_isolation.py check --topic {topic} --workspace --report -",
            f"python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic {topic} --json",
        ],
    }
    payload = _with_completion_receipt_path(payload)
    apply_acp_context_budget_to_pack(payload)
    attempt = (action_id or "").strip() or None
    if attempt:
        payload["action_id"] = attempt
        payload["attempt_id"] = attempt
        if not episode_id:
            start = next(
                (
                    receipt
                    for receipt in reversed(read_action_receipts())
                    if str(receipt.get("action_id") or "") == attempt
                ),
                None,
            )
            if start:
                episode_id = str(
                    start.get("episode_id")
                    or (start.get("replay") or {}).get("episode_id")
                    or ""
                ) or None
    bound = bind_pack_to_episode(payload, episode_id=episode_id)
    persist_dispatch_pack(bound)
    return bound, 0 if bound.get("safe_to_dispatch") else 1


def control_proposal_idea_pack(
    episode_id: str | None = None,
    *,
    intent: str | None = None,
    task: str = "product_proposal",
) -> tuple[dict[str, Any], int]:
    """Topic-less idea hop: product → spec/open/; process → spec/meta/open/."""
    canonical = canonicalize_proposal_task(task)
    if canonical not in {"product_proposal", "process_proposal"}:
        raise ValueError(f"idea hop task must be product/process proposal, got {task}")
    plane = "product" if canonical == "product_proposal" else "process"
    normalized_intent = normalize_human_intent(intent)
    allowed_roots = allowed_roots_for_idea_plane(plane)
    assert_idea_write_roots(canonical, allowed_roots)
    pack_task = (
        "ndf_improvement_proposal"
        if canonical == "process_proposal"
        else "product_proposal"
    )
    # Legacy alias preserved on wire for product packs that still say control_proposal.
    wire_task = task if task in CONTROL_TASKS | PROJECT_CONTROL_TASKS else pack_task
    if canonical == "product_proposal" and task == "control_proposal":
        wire_task = "control_proposal"
    elif canonical == "product_proposal":
        wire_task = "product_proposal"
    role = "project-control" if plane == "process" else "openclaw"
    track = "process" if plane == "process" else "poc"
    context = context_binding(
        topic=None,
        role=role,
        task=pack_task if plane == "process" else "product_proposal",
        track=track,
        allowed_write_roots=allowed_roots,
    )
    context_valid = bool(context["context_verify"].get("valid"))
    # Episode no longer required for daily idea hops (ADR-META-004).
    static_ready = bool(normalized_intent) and context_valid
    control_runtime = runtime_status(True)["control"]
    runtime_ready = control_runtime_dispatch_ready(control_runtime)
    safe = static_ready and runtime_ready
    blockers: list[str] = []
    if not normalized_intent:
        blockers.append("human_intent_missing")
    if not context_valid:
        blockers.append("context_verify_failed")
    blockers.extend(control_runtime_dispatch_blockers(control_runtime))
    role_blockers = roles_dispatch_blockers()
    blockers.extend(role_blockers)
    if role_blockers:
        safe = False
    intent_sha = (
        hashlib.sha256(normalized_intent.encode("utf-8")).hexdigest()
        if normalized_intent
        else None
    )
    forbidden = [
        "poc/",
        "src/",
        "include/",
        "tests/",
        ".openclaw/state.json",
        "GATES.md approved_by without human phrase",
        "human approval fabrication",
    ]
    if plane == "product":
        forbidden.extend(["spec/meta/", "spec/meta/open/", "spec/meta/ (stable body)"])
    else:
        forbidden.extend(["spec/open/", "spec/00-charter/", "spec/20-behavior/"])
    schema = (
        "ndf-project-control-pack/v2"
        if plane == "process"
        else "ndf-control-pack/v2"
    )
    payload = {
        "schema": schema,
        "compatibility": {"legacy_schema": "ndf-control-pack/v1"},
        "generated_at": now_iso(),
        "topic": None,
        "track": track,
        "task": wire_task,
        "idea_plane": plane,
        "canonical_task": canonical,
        "pipeline": PIPELINE_PROCESS if plane == "process" else None,
        "pipeline_plan": None,
        "hop": "draft",
        "resume": False,
        "active_episode_id": None,
        "provider": "openclaw",
        "session_key": openclaw_session_key(),
        "resolved_session_id": control_runtime.get("resolved_session_id"),
        "session_transport": control_runtime.get("session_transport"),
        "base_sha": git_head(),
        "workspace": workspace_binding(None),
        "workspace_truth": workspace_truth_view(None),
        "request": {
            "origin": "human_intent",
            "intent": normalized_intent or None,
            "intent_sha": intent_sha,
            "intent_summary": (
                clean_markdown(normalized_intent, 400) if normalized_intent else None
            ),
            "idea_plane": plane,
        },
        "required_reads": required_reads_for_task(canonical, None),
        "allowed_write_roots": allowed_roots,
        "allowed_write_paths": allowed_roots,
        "forbidden": forbidden,
        "required_proposal_status": REQUIRED_PROCESS_PROPOSAL_STATUS,
        "next_human_phrase": "已确认",
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": safe,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
    }
    bound = bind_pack_to_episode(
        _with_completion_receipt_path(payload),
        episode_id=episode_id,
        require_episode=False,
    )
    return bound, 0 if safe else 1


def control_pack(
    topic: str | None,
    task: str,
    episode_id: str | None = None,
    *,
    focus_gate: str | None = None,
    focus_binder_facet: str | None = None,
    resume: bool = False,
    intent: str | None = None,
) -> tuple[dict[str, Any], int]:
    if task not in CONTROL_TASKS:
        raise ValueError(f"unknown control task: {task}")
    topic = (topic or "").strip() or None
    if topic is None:
        if canonicalize_proposal_task(task) not in {
            "product_proposal",
            "process_proposal",
        }:
            raise ValueError(
                "control-pack --topic is required except for product/process proposal idea hops"
            )
        if resume or focus_gate or focus_binder_facet:
            raise ValueError("resume/focus requires --topic")
        return control_proposal_idea_pack(episode_id, intent=intent, task=task)
    topic_dir = POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")
    view = topic_view(topic_dir)
    bundles = poc_gate_bundle_specs(topic_dir)
    gates_detail: dict[str, Any] = {}
    for gate_name, gate_data in view["gates"].items():
        bundle = bundles[gate_name]
        gates_detail[gate_name] = {
            **gate_data,
            "phrase": GATE_PHRASES.get(gate_name),
            "bundle_paths": list(bundle.get("bundle_paths") or []),
        }
    invalidated = any(gate["state"] == "invalidated" for gate in view["gates"].values())
    audit_tasks = {
        "legacy_gate_audit",
        "gate_sha_audit",
        "gate_pipeline",
        "binder_pipeline",
    }
    pipeline = pipeline_for_task(
        task, gate=focus_gate, binder_facet=focus_binder_facet
    )
    if task == "gate_pipeline":
        pipeline = PIPELINE_GATE
    elif task == "binder_pipeline":
        pipeline = PIPELINE_BINDER
    pipelines = view.get("control_pipelines") or control_pipelines_view(
        topic, (view.get("health") or {}).get("findings", [])
    )
    pipeline_proj = (
        pipelines.get(pipeline) if pipeline and isinstance(pipelines, Mapping) else None
    )
    if (
        resume
        and isinstance(pipeline_proj, Mapping)
        and pipeline_proj.get("force_new_episode")
    ):
        raise ValueError(
            "stale control Episode cannot be resumed "
            "(manifest/context drift); start a new episode without --resume"
        )
    active_episode = (
        active_control_episode(topic, pipeline) if pipeline else None
    )
    if resume and active_episode and not episode_id:
        episode_id = active_episode
    if task == "gate_sha_audit":
        allowed_roots: list[str] = []
    elif task in {
        "legacy_gate_audit",
        "gate_receipt_draft",
        "gate_pipeline",
    }:
        allowed_roots = [f"poc/{topic}/ndf/GATES.md"]
    elif task in {"binder_amend", "binder_pipeline"}:
        facets = (
            [focus_binder_facet]
            if focus_binder_facet
            else list(BINDER_FACET_ORDER)
        )
        allowed_roots = [
            f"poc/{topic}/ndf/{BINDER_FACET_FILES[facet]}"
            for facet in facets
        ]
    elif canonicalize_proposal_task(task) == "product_proposal":
        allowed_roots = allowed_roots_for_idea_plane("product")
        assert_idea_write_roots(task, allowed_roots)
    elif canonicalize_proposal_task(task) == "process_proposal":
        allowed_roots = allowed_roots_for_idea_plane("process")
        assert_idea_write_roots(task, allowed_roots)
    else:
        allowed_roots = allowed_roots_for_idea_plane("product")
        assert_idea_write_roots("product_proposal", allowed_roots)
    context = context_binding(
        topic=topic,
        role="openclaw",
        task=task,
        track="poc",
        allowed_write_roots=allowed_roots,
    )
    context_valid = bool(context["context_verify"].get("valid"))
    static_ready = (task in audit_tasks or not invalidated) and context_valid
    control_runtime = runtime_status(True)["control"]
    runtime_ready = control_runtime_dispatch_ready(control_runtime)
    safe = static_ready and runtime_ready
    blockers: list[str] = []
    if not safe:
        if invalidated and task not in audit_tasks:
            blockers.append("gate_invalidated")
        if not context_valid:
            blockers.append("context_verify_failed")
        blockers.extend(control_runtime_dispatch_blockers(control_runtime))
    role_blockers = roles_dispatch_blockers()
    blockers.extend(role_blockers)
    if role_blockers:
        safe = False
    # SHA drift is the reason for gate_sha_audit / gate_pipeline focus — not a
    # static preflight blocker for those audit tasks.
    pipeline_block = None
    if pipeline == PIPELINE_GATE:
        pipeline_block = {
            **pipelines["gate"],
            "gates_ordered": list(GATE_ORDER),
            "phrases_ordered": [GATE_PHRASES[name] for name in GATE_ORDER],
            "wait_human_phrase_per_gate": True,
            "focus_gate": focus_gate,
            "event_kinds": ["gate.audit", "gate.draft", "gate.confirmed"],
            "write_ownership": {
                "allowed": [f"poc/{topic}/ndf/GATES.md"],
                "forbidden_facets": list(BINDER_FACET_FILES.values()),
            },
        }
    elif pipeline == PIPELINE_BINDER:
        pipeline_block = {
            **pipelines["binder"],
            "facets_ordered": list(BINDER_FACET_ORDER),
            "facet_labels": dict(BINDER_FACET_LABELS),
            "wait_human_phrase_per_gate": False,
            "focus_binder_facet": focus_binder_facet,
            "event_kinds": ["binder.audit", "binder.amend", "binder.recheck"],
            "write_ownership": {
                "allowed": allowed_roots,
                "forbidden": [f"poc/{topic}/ndf/GATES.md"],
                "no_op_when_complete": True,
            },
            "post_check": [
                f"python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic {topic} --json"
            ],
        }
    payload = {
        "schema": "ndf-control-pack/v2",
        "compatibility": {"legacy_schema": "ndf-control-pack/v1"},
        "generated_at": now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": task,
        "pipeline": pipeline,
        "pipeline_plan": pipeline_block,
        "resume": bool(resume or (active_episode and episode_id == active_episode)),
        "active_episode_id": active_episode,
        "provider": "openclaw",
        "session_key": openclaw_session_key(),
        "resolved_session_id": control_runtime.get("resolved_session_id"),
        "session_transport": control_runtime.get("session_transport"),
        "base_sha": git_head(),
        "workspace": workspace_binding(topic),
        "workspace_truth": workspace_truth_view(topic),
        "phase_hint": view["phase_hint"],
        "gates": gates_detail,
        "gate_bundle_modes": {
            gate: detail.get("bundle_mode")
            for gate, detail in gates_detail.items()
        },
        "gate_sha_contract": {
            "algorithm": {
                "review_slice": (
                    "sha256(sorted(slice_id + NUL + repo-relative path + "
                    "NUL + slice bytes + NUL))"
                ),
                "legacy_whole_file": (
                    "sha256(sorted(repo-relative path + NUL + file bytes + NUL))"
                ),
            },
            "authoritative_field": "gates.<gate>.expected_content_sha",
            "pending_rule": "pending rows MUST leave approved_content_sha empty",
            "approval_rule": (
                "after the exact human phrase, approved_content_sha MUST copy the "
                "current expected_content_sha verbatim and receipt MUST copy "
                "bundle_mode + slice_manifest_sha; never use raw file sha256"
            ),
        },
        "spaces": view["spaces"],
        "binder_gaps": {
            "design": view["spaces"]["design"]["gaps"],
            "implementation": view["spaces"]["implementation"]["gaps"],
            "test": view["spaces"]["test"]["gaps"],
        },
        "control_pipelines": pipelines,
        "required_reads": required_reads_for_task(task, topic),
        "allowed_write_roots": allowed_roots,
        "allowed_write_paths": allowed_roots,
        "allowed_sections": (
            (context.get("context_plan") or {})
            .get("privileges", {})
            .get("allowed_sections", [])
        ),
        "forbidden_sections": (
            (context.get("context_plan") or {})
            .get("privileges", {})
            .get("forbidden_sections", [])
        ),
        "mutable_sections": list(ndf_gate_slices.MUTABLE_SECTIONS),
        "forbidden": [
            "src/",
            "include/",
            "tests/",
            "spec/meta/ (stable body)",
            "GATES.md approved_by without human phrase",
            "cross-pipeline merge without pipeline+step events",
            "gate pipeline writing binder facets",
            "binder pipeline writing GATES.md approvals or close decisions",
        ],
        "next_human_phrase": next_human_phrase(view),
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": safe,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
    }
    try:
        bound = bind_pack_to_episode(
            _with_completion_receipt_path(payload), episode_id=episode_id
        )
    except ValueError as exc:
        if resume and "episode manifest does not match" in str(exc):
            if pipeline:
                clear_control_pipeline_episode(topic, pipeline)
            raise ValueError(
                "episode manifest does not match generated pack; "
                "cleared stale pipeline binding — start a new episode without --resume"
            ) from exc
        raise
    if pipeline and bound.get("replay", {}).get("episode_id"):
        bind_control_pipeline_episode(
            topic, pipeline, str(bound["replay"]["episode_id"])
        )
        bound["active_episode_id"] = bound["replay"]["episode_id"]
    elif pipeline and episode_id:
        bind_control_pipeline_episode(topic, pipeline, episode_id)
        bound["active_episode_id"] = episode_id
    return bound, 0 if safe else 1


def record_control_pipeline_step(
    *,
    topic: str,
    pipeline: str,
    kind: str,
    step_id: str,
    episode_id: str,
    actor: str = "openclaw",
    payload_json: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Append one gate/binder pipeline step event (META-011 / META-013)."""
    if pipeline not in {PIPELINE_GATE, PIPELINE_BINDER}:
        raise ValueError(f"unknown pipeline: {pipeline}")
    gate_kinds = {
        "gate.audit",
        "gate.draft",
        "gate.confirmed",
        "control.handoff",
        "decision.selected",
    }
    binder_kinds = {"binder.audit", "binder.amend", "binder.recheck"}
    if pipeline == PIPELINE_GATE and kind not in gate_kinds:
        raise ValueError(f"kind {kind} not valid for gate pipeline")
    if pipeline == PIPELINE_BINDER and kind not in binder_kinds:
        raise ValueError(f"kind {kind} not valid for binder pipeline")
    if kind in {"gate.confirmed", "decision.selected"} and actor.lower() in ndf_replay.AGENT_ACTORS:
        raise ValueError(f"{kind} actor must be human")
    if kind.startswith("gate.") and step_id not in GATE_ORDER:
        raise ValueError(f"unknown gate step: {step_id}")
    if kind.startswith("binder.") and step_id not in BINDER_FACET_ORDER:
        raise ValueError(f"unknown binder facet: {step_id}")
    body: dict[str, Any] = {
        "schema": "ndf-control-pipeline-step/v1",
        "topic": topic,
        "pipeline": pipeline,
        "kind": kind,
        "step_id": step_id,
        "recorded_at": now_iso(),
    }
    if pipeline == PIPELINE_GATE and step_id in GATE_ORDER:
        topic_dir = POC / topic
        if (topic_dir / "ndf" / "TOPIC.md").is_file():
            spec = poc_gate_bundle_specs(topic_dir).get(step_id, {})
            body["bundle_mode"] = spec.get("bundle_mode")
            body["slice_manifest_sha"] = spec.get("slice_manifest_sha")
            body["expected_content_sha"] = spec.get(
                "expected_content_sha"
            )
    extra: dict[str, Any] = {}
    if payload_json:
        extra = json.loads(payload_json)
        if not isinstance(extra, dict):
            raise ValueError("--payload-json must be a JSON object")
        body["detail"] = extra
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    episode_events = [
        event
        for events in store.read_all_events(episode_id).values()
        for event in events
    ]
    manifest_sha = next(
        (
            str(event["manifest_sha"])
            for event in reversed(episode_events)
            if event.get("manifest_sha")
        ),
        None,
    )
    context_plan_sha = next(
        (
            str(event["context_plan_sha"])
            for event in reversed(episode_events)
            if event.get("context_plan_sha")
        ),
        None,
    )
    changed_files = []
    for item in extra.get("changed_files") or []:
        path = item.get("path") if isinstance(item, Mapping) else item
        if isinstance(path, str) and path:
            changed_files.append(path.strip("/"))
    changed_sections = {
        str(section)
        for section in extra.get("changed_sections") or []
        if str(section)
    }
    if kind in {"gate.draft", "binder.amend"} and not changed_files:
        raise ValueError(f"{kind} requires changed_files evidence")
    if kind in {"gate.draft", "binder.amend"} and not changed_sections:
        raise ValueError(f"{kind} requires changed_sections evidence")
    if kind == "gate.draft":
        allowed = f"poc/{topic}/ndf/GATES.md"
        if any(path != allowed for path in changed_files):
            raise ValueError("cross_pipeline_write: gate may only write GATES.md")
        if changed_sections - {"gate_receipts"}:
            raise ValueError(
                "cross_role_section_write: gate may only write gate_receipts"
            )
    if kind == "binder.amend":
        allowed = f"poc/{topic}/ndf/{BINDER_FACET_FILES[step_id]}"
        if any(path != allowed for path in changed_files):
            raise ValueError(
                f"cross_pipeline_write: binder facet {step_id} may only write {allowed}"
            )
        forbidden = changed_sections - BINDER_FACET_SECTIONS[step_id]
        if forbidden:
            raise ValueError(
                "cross_role_section_write: binder facet "
                f"{step_id} cannot write {sorted(forbidden)}"
            )
    if kind == "control.handoff":
        required = {"blocked_gate", "next_binder_facet"}
        if not required.issubset(extra):
            raise ValueError("control.handoff missing blocked_gate/next_binder_facet")
        if extra["blocked_gate"] not in GATE_ORDER:
            raise ValueError("control.handoff has invalid blocked_gate")
        if extra["next_binder_facet"] not in BINDER_FACET_ORDER:
            raise ValueError("control.handoff has invalid next_binder_facet")
        body["manifest_sha"] = manifest_sha
        body["context_plan_sha"] = context_plan_sha
    if kind == "decision.selected":
        if extra.get("mode") not in POC_DECISIONS:
            raise ValueError("decision.selected has invalid mode")
        if changed_files:
            raise ValueError("decision.selected MUST NOT claim file mutations")
    blob_sha = store.put_blob(body)
    event = store.append_event(
        episode_id,
        kind=kind,
        actor=actor,
        payload_sha=blob_sha,
        topic=topic,
        task=f"{pipeline}:{step_id}",
        track="poc",
        repo_head=git_head(),
        manifest_sha=manifest_sha,
        context_plan_sha=context_plan_sha,
        branch="control",
    )
    bind_control_pipeline_episode(topic, pipeline, episode_id)
    return {
        "schema": "ndf-control-pipeline-step-record/v1",
        "topic": topic,
        "pipeline": pipeline,
        "kind": kind,
        "step_id": step_id,
        "episode_id": episode_id,
        "event_sha": event["event_sha"],
        "payload_sha": blob_sha,
        "result": "recorded",
    }, 0


def normalize_human_intent(intent: str | None) -> str:
    value = (intent or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\0" in value:
        raise ValueError("human intent must not contain NUL bytes")
    if len(value.encode("utf-8")) > MAX_PROCESS_INTENT_BYTES:
        raise ValueError(
            f"human intent exceeds {MAX_PROCESS_INTENT_BYTES} UTF-8 bytes"
        )
    return value


def normalize_process_intent(intent: str | None) -> str:
    """Compatibility alias for normalize_human_intent."""
    return normalize_human_intent(intent)


def read_process_intent_file(path_value: str | None) -> str | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    intent_root = (ROOT / "tmp").resolve()
    try:
        candidate.relative_to(intent_root)
    except ValueError as exc:
        raise ValueError("intent file must be under repo tmp/") from exc
    if not candidate.is_file():
        raise ValueError(f"intent file does not exist: {candidate}")
    return candidate.read_text(encoding="utf-8")


def resolve_process_proposal_path(proposal: str | None) -> tuple[Path | None, str | None]:
    if not proposal or not str(proposal).strip():
        return None, "process_proposal_missing"
    candidate = Path(proposal)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        candidate = candidate.resolve()
    except OSError:
        return None, "process_proposal_missing"
    meta_open = (META / "open").resolve()
    try:
        candidate.relative_to(meta_open)
    except ValueError:
        return None, "process_proposal_not_process_plane"
    if not candidate.is_file():
        return None, "process_proposal_missing"
    if not candidate.name.startswith("proposal-meta-"):
        return None, "process_proposal_not_process_plane"
    return candidate, None


def project_control_land_pack(
    episode_id: str | None,
    proposal: str | None,
    human_phrase: str | None = None,
) -> tuple[dict[str, Any], int]:
    generation_sha = source_generation_sha()
    health = latest_spec_health(generation_sha)
    findings = (health or {}).get("findings", [])
    path, path_blocker = resolve_process_proposal_path(proposal)
    record = proposal_record(path) if path else None
    hop = (record or {}).get("hop")
    managed = bool(record and record.get("control_flow") == "managed")
    if managed and hop == PROCESS_HOP_CONFIRM_LAND:
        land_plan_roots = list(record.get("land_targets") or []) + [record["path"]]
        control_binding = {
            "proposal_id": record.get("proposal_id"),
            "flow_id": record.get("flow_id"),
            "hop": "confirm_land",
            "origin": "human_confirmation",
            "intent_sha": None,
            "proposal_path": record.get("path"),
            "proposal_sha": record.get("content_sha"),
            "land_targets": list(record.get("land_targets") or []),
        }
    elif managed and hop == PROCESS_HOP_MANAGED_REVIEW:
        land_plan_roots = [record["path"]]
        control_binding = {
            "proposal_id": record.get("proposal_id"),
            "flow_id": record.get("flow_id"),
            "hop": "review",
            "origin": "human_review",
            "human_phrase": human_phrase,
            "intent_sha": None,
            "proposal_path": record.get("path"),
            "proposal_sha": record.get("content_sha"),
            "land_targets": [],
        }
    else:
        land_plan_roots = []
        control_binding = None
    context = context_binding(
        topic=None,
        role="project-control",
        task="ndf_improvement_land",
        track="process",
        allowed_write_roots=land_plan_roots,
        control_binding=control_binding,
    )
    context_valid = bool(context["context_verify"].get("valid"))
    control_runtime = runtime_status(True)["control"]
    runtime_ready = control_runtime_dispatch_ready(control_runtime)
    blockers: list[str] = []
    if path_blocker:
        blockers.append(path_blocker)
    elif not managed:
        blockers.append("process_proposal_legacy_unbound")
    elif hop in {None, PROCESS_HOP_DONE}:
        blockers.append("process_proposal_hop_done")
    elif hop not in {PROCESS_HOP_CONFIRM_LAND, PROCESS_HOP_MANAGED_REVIEW}:
        blockers.append("process_proposal_human_receipt_required")
    elif hop == PROCESS_HOP_MANAGED_REVIEW and human_phrase != "已审核":
        blockers.append("process_proposal_review_phrase_missing")
    if not context_valid:
        blockers.append("context_verify_failed")
    blockers.extend(control_runtime_dispatch_blockers(control_runtime))
    source_ready = bool(record) and managed and (
        hop == PROCESS_HOP_CONFIRM_LAND
        or (hop == PROCESS_HOP_MANAGED_REVIEW and human_phrase == "已审核")
    )
    static_ready = source_ready and context_valid and not path_blocker
    if hop in {None, PROCESS_HOP_DONE}:
        static_ready = False
    if hop == PROCESS_HOP_CONFIRM_LAND:
        allowed_write_roots = list(land_plan_roots)
        forbidden = [
            "src/",
            "include/",
            "tests/",
            ".openclaw/state.json",
            "product or POC documents",
            "human approval fabrication",
        ]
        next_phrase = "已审核"
    elif hop == PROCESS_HOP_MANAGED_REVIEW:
        allowed_write_roots = [record["path"]] if record else ["spec/meta/open/"]
        forbidden = [
            "src/",
            "include/",
            "tests/",
            "spec/meta/ (stable body)",
            ".openclaw/state.json",
            "product or POC documents",
            "human approval fabrication",
        ]
        next_phrase = "已审核"
    else:
        allowed_write_roots = []
        forbidden = [
            "src/",
            "include/",
            "tests/",
            "spec/meta/ (stable body)",
            ".openclaw/state.json",
            "product or POC documents",
            "human approval fabrication",
        ]
        next_phrase = None
    payload = {
        "schema": "ndf-project-control-pack/v3",
        "compatibility": {
            "legacy_schemas": [
                "ndf-project-control-pack/v2",
                "ndf-project-control-pack/v1",
            ]
        },
        "generated_at": now_iso(),
        "track": "process",
        "task": "ndf_improvement_land",
        "proposal_id": (record or {}).get("proposal_id"),
        "flow_id": (record or {}).get("flow_id"),
        "hop": (
            "confirm_land"
            if hop == PROCESS_HOP_CONFIRM_LAND
            else "review"
            if hop == PROCESS_HOP_MANAGED_REVIEW
            else None
        ),
        "proposal": (
            {
                "path": record["path"],
                "title": record["title"],
                "status": record["status"],
                "lifecycle": record["lifecycle"],
                "proposal_id": record["proposal_id"],
                "flow_id": record["flow_id"],
                "proposal_sha": record["proposal_sha"],
                "content_sha": record["content_sha"],
                "land_targets": record["land_targets"],
                "receipts": record["receipts"],
                "hop": record["hop"],
                "reviewed": record["reviewed"],
                "next_human_phrase": record["next_human_phrase"],
            }
            if record
            else None
        ),
        "request": {
            "origin": "land",
            "intent": None,
            "intent_sha": None,
            "intent_summary": None,
            "human_phrase": human_phrase,
        },
        "provider": "openclaw",
        "session_key": openclaw_session_key(),
        "resolved_session_id": control_runtime.get("resolved_session_id"),
        "session_transport": control_runtime.get("session_transport"),
        "base_sha": git_head(),
        "workspace": workspace_binding(None),
        "workspace_truth": workspace_truth_view(None),
        "required_reads": [
            "AGENTS.md",
            "spec/meta/README.md",
            "spec/meta/language.md",
            "spec/meta/process.md",
            "spec/meta/tools/GOVERNANCE.md",
            *((record["path"],) if record else ()),
        ],
        "spec_health": {
            "state": (health or {}).get("state", "not_run"),
            "findings": findings,
            "advisor": (health or {}).get("advisor", {"read_only": True}),
        },
        "allowed_write_roots": allowed_write_roots,
        "forbidden": forbidden,
        "next_human_phrase": next_phrase,
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": static_ready and runtime_ready,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
    }
    return bind_pack_to_episode(
        _with_completion_receipt_path(payload), episode_id=episode_id
    ), 0 if (
        static_ready and runtime_ready
    ) else 1


def project_control_pack(
    task: str,
    episode_id: str | None = None,
    *,
    origin: str = "health_finding",
    intent: str | None = None,
    proposal: str | None = None,
    human_phrase: str | None = None,
) -> tuple[dict[str, Any], int]:
    if task not in PROJECT_CONTROL_TASKS:
        raise ValueError(f"unknown project control task: {task}")
    if task == "ndf_improvement_land":
        return project_control_land_pack(episode_id, proposal, human_phrase)
    if origin not in PROJECT_CONTROL_ORIGINS:
        raise ValueError(f"unknown project control origin: {origin}")
    normalized_intent = normalize_process_intent(intent)
    generation_sha = source_generation_sha()
    health = latest_spec_health(generation_sha)
    findings = (health or {}).get("findings", [])
    health_current = bool(health and health.get("state") == "current")
    intent_sha = (
        hashlib.sha256(normalized_intent.encode("utf-8")).hexdigest()
        if normalized_intent
        else canonical_json_sha(findings)
    )
    identifier = f"meta-control-{intent_sha[:12]}"
    proposal_target = proposal or f"spec/meta/open/proposal-{identifier}.md"
    target_path = Path(proposal_target)
    if not target_path.is_absolute():
        target_path = ROOT / target_path
    target_path = target_path.resolve()
    try:
        target_relative = target_path.relative_to((META / "open").resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("proposal target must be under spec/meta/open/") from exc
    proposal_target = f"spec/meta/open/{target_relative}"
    if not target_path.name.startswith("proposal-meta-") or target_path.suffix != ".md":
        raise ValueError("proposal target must name proposal-meta-*.md")
    control_binding = {
        "proposal_id": identifier,
        "flow_id": f"flow-{intent_sha[:16]}",
        "hop": "draft",
        "origin": origin,
        "intent_sha": intent_sha,
        "proposal_path": proposal_target,
        "proposal_sha": file_sha(target_path),
        "land_targets": [],
    }
    context = context_binding(
        topic=None,
        role="project-control",
        task=task,
        track="process",
        allowed_write_roots=[proposal_target],
        control_binding=control_binding,
    )
    context_valid = bool(context["context_verify"].get("valid"))
    source_ready = (
        bool(findings) and health_current
        if origin == "health_finding"
        else bool(normalized_intent)
    )
    static_ready = source_ready and context_valid
    control_runtime = runtime_status(True)["control"]
    runtime_ready = control_runtime_dispatch_ready(control_runtime)
    safe = static_ready and runtime_ready
    blockers = []
    if origin == "health_finding":
        if normalized_intent:
            blockers.append("human_intent_not_allowed_for_health_origin")
            static_ready = False
            safe = False
        if not findings:
            blockers.append("spec_health_findings_missing")
        if not health_current:
            blockers.append("spec_health_stale")
    elif not normalized_intent:
        blockers.append("human_intent_missing")
    if target_path.exists():
        blockers.append("process_proposal_target_exists")
        static_ready = False
        safe = False
    if not context_valid:
        blockers.append("context_verify_failed")
    blockers.extend(control_runtime_dispatch_blockers(control_runtime))
    safe = static_ready and control_runtime_dispatch_ready(control_runtime)
    payload = {
        "schema": "ndf-project-control-pack/v3",
        "compatibility": {
            "legacy_schemas": [
                "ndf-project-control-pack/v2",
                "ndf-project-control-pack/v1",
            ]
        },
        "generated_at": now_iso(),
        "track": "process",
        "task": task,
        "proposal_id": identifier,
        "flow_id": control_binding["flow_id"],
        "hop": "draft",
        "request": {
            "origin": origin,
            "intent": normalized_intent or None,
            "intent_sha": intent_sha,
            "intent_summary": (
                clean_markdown(normalized_intent, 400)
                if normalized_intent
                else None
            ),
        },
        "proposal": {
            "path": proposal_target,
            "proposal_id": identifier,
            "flow_id": control_binding["flow_id"],
            "hop": "draft",
        },
        "provider": "openclaw",
        "session_key": openclaw_session_key(),
        "resolved_session_id": control_runtime.get("resolved_session_id"),
        "session_transport": control_runtime.get("session_transport"),
        "base_sha": git_head(),
        "workspace": workspace_binding(None),
        "workspace_truth": workspace_truth_view(None),
        "required_reads": [
            "AGENTS.md",
            "spec/meta/README.md",
            "spec/meta/language.md",
            "spec/meta/process.md",
            "spec/meta/tools/GOVERNANCE.md",
        ],
        "spec_health": {
            "state": (health or {}).get("state", "not_run"),
            "findings": findings,
            "advisor": (health or {}).get("advisor", {"read_only": True}),
        },
        "allowed_write_roots": [proposal_target],
        "forbidden": [
            "src/",
            "include/",
            "tests/",
            "spec/meta/ (stable body)",
            ".openclaw/state.json",
            "product or POC documents",
            "human approval fabrication",
        ],
        "required_proposal_status": REQUIRED_PROCESS_PROPOSAL_STATUS,
        "next_human_phrase": "已确认",
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": safe,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "blockers": blockers,
    }
    return bind_pack_to_episode(
        _with_completion_receipt_path(payload), episode_id=episode_id
    ), 0 if safe else 1


def genesis_pack(mode: str, episode_id: str | None = None) -> tuple[dict[str, Any], int]:
    paths = genesis_paths()
    foundation_files: list[Path] = []
    for directory in ("00-charter", "10-architecture", "20-behavior", "30-interfaces", "40-constraints", "50-verification"):
        foundation_files.extend(sorted((SPEC / directory).rglob("*.md")) if (SPEC / directory).is_dir() else [])
    gates = latest_gate_rows(paths["gates"])
    approval = gates.get("trunk_approval")
    foundation_sha = bundle_sha(foundation_files)
    gate_valid = bool(
        approval
        and first_token(approval.get("status")) in {"valid", "approved"}
        and foundation_sha
        and re.fullmatch(r"[0-9a-f]{64}", approval.get("approved_content_sha", ""))
        and foundation_sha == approval.get("approved_content_sha")
    )
    context = context_binding(
        topic=None,
        role="claude-code",
        task="project_genesis",
        track="bootstrap",
    )
    context_valid = bool(context["context_verify"].get("valid"))
    static_ready = gate_valid and context_valid
    runtime, runtime_ready, _lease = implementation_dispatch_runtime(None)
    runtime_ready = bool(runtime.get("pipeline_reachable"))
    payload = {
        "schema": "ndf-genesis-pack/v2",
        "compatibility": {"legacy_schema": "ndf-genesis-pack/v1"},
        "generated_at": now_iso(),
        "track": "bootstrap",
        "task": "project_genesis",
        "bootstrap_mode": mode,
        "provider": "claude-code-acp",
        "base_sha": git_head(),
        "workspace": workspace_binding(None),
        "workspace_truth": workspace_truth_view(None),
        "foundation_sha": foundation_sha,
        "trunk_approval": approval,
        "safe_to_delegate": static_ready,
        "safe_to_dispatch": static_ready and runtime_ready,
        "static_preflight_passed": static_ready,
        "runtime_dispatch_ready": runtime_ready,
        **context,
        "allowed_write_roots": ["src/", "include/", "tests/", "spec/50-verification/"],
        "forbidden": [
            "spec/00-charter/",
            "spec/10-architecture/",
            "spec/meta/",
            "spec/decisions/",
            "L0/L1 clauses",
        ],
        "foundation_files": [{"path": rel(path), "sha256": file_sha(path)} for path in foundation_files],
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
    }
    return bind_pack_to_episode(
        _with_completion_receipt_path(payload), episode_id=episode_id
    ), 0 if payload["safe_to_dispatch"] else 1


def close_plan(topic: str, mode: str, ids: list[str]) -> tuple[dict[str, Any], int]:
    command = [
        sys.executable,
        str(TOOLS / "ndf_close.py"),
        "plan",
        "--topic",
        topic,
        "--mode",
        mode,
    ]
    if ids:
        command.extend(["--ids", *ids])
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "schema": "ndf-close-plan-view/v1",
        "generated_at": now_iso(),
        "topic": topic,
        "mode": mode,
        "read_only": True,
        "exit_code": proc.returncode,
        "plan_markdown": proc.stdout,
        "trunk_src_writes": ndf_close.infer_trunk_src_writes(mode, proc.stdout),
    }, proc.returncode


def validate_lease_transition(
    history: list[dict[str, Any]],
    lease: Mapping[str, Any],
) -> list[str]:
    """Validate the append-only state machine for one immutable run id."""
    prior = next(
        (
            item
            for item in reversed(history)
            if item.get("run_id") == lease.get("run_id")
            and item.get("episode_id") == lease.get("episode_id")
        ),
        None,
    )
    if lease.get("result") == "active":
        return (
            ["run_id_already_has_lease_history"]
            if prior is not None
            else []
        )
    if prior is None or prior.get("result") != "active":
        return ["release_without_active_lease"]
    immutable = (
        "session_id",
        "task",
        "topic",
        "base_sha",
        "worktree",
        "branch",
        "allowed_write_root",
        "pack_sha",
        "manifest_sha",
        "context_plan_sha",
    )
    if any(prior.get(field) != lease.get(field) for field in immutable):
        return ["release_binding_mismatch"]
    return []


def record_runtime_lease(args: argparse.Namespace) -> dict[str, Any]:
    requested_episode = getattr(args, "episode", None) or os.environ.get(
        "NDF_REPLAY_EPISODE"
    )
    if args.file:
        lease = json.loads(Path(args.file).read_text(encoding="utf-8"))
        episode_id = lease.get("episode_id") or requested_episode
        if lease.get("episode_id") != episode_id:
            raise ValueError("lease file episode_id does not match --episode")
    else:
        episode_id = requested_episode
        if not episode_id:
            raise ValueError("writable runtime lease requires --episode")
        context = context_binding(
            topic=args.topic,
            role="claude-code",
            task=args.task,
            track=args.mode,
        )
        pack_sha, pack = replay_pack_binding(
            str(episode_id),
            task=args.task,
            manifest_sha=context.get("manifest_sha"),
            context_plan_sha=context.get("plan_sha"),
        )
        if args.allowed_write_root != pack.get("allowed_write_root"):
            raise ValueError("runtime handshake allowed_write_root does not match pack")
        if args.base_sha != pack.get("base_sha"):
            raise ValueError("runtime handshake base_sha does not match pack")
        timestamp = now_iso()
        seed = {
            "run_id": args.run_id,
            "topic": args.topic,
            "result": args.result,
            "repo_head": git_head(),
        }
        lease = {
            "schema": "ndf-runtime-lease/v1",
            "task": args.task,
            "topic": args.topic,
            "mode": args.mode,
            "step": args.step,
            "repo_head": git_head(),
            "source_generation_sha": source_generation_sha(),
            "context_plan_sha": context["plan_sha"],
            "manifest_sha": context["manifest_sha"],
            "command": args.command_text,
            "input_sha": canonical_json_sha(seed),
            "output_sha": canonical_json_sha({**seed, "state": args.result}),
            "evidence_paths": args.evidence_path,
            "started_at": args.started_at or timestamp,
            "finished_at": None if args.result == "active" else timestamp,
            "result": args.result,
            "blockers": args.blocker,
            "run_id": args.run_id,
            "session_id": args.session_id,
            "base_sha": args.base_sha,
            "worktree": args.worktree,
            "branch": args.branch,
            "repo_root": str(ROOT),
            "allowed_write_root": pack.get("allowed_write_root"),
            "pack_sha": pack_sha,
            "episode_id": episode_id,
        }
        action_id = getattr(args, "action_id", None)
        if action_id:
            lease["action_id"] = str(action_id)
    episode_id = str(lease.get("episode_id") or "")
    try:
        lease_history = read_leases(LEASE_LOG, root=ROOT, strict=False)
    except ValueError:
        lease_history = []
    transition_errors = validate_lease_transition(lease_history, lease)
    if transition_errors:
        raise ValueError(f"invalid runtime lease transition: {transition_errors}")
    prior_active = next(
        (
            item
            for item in reversed(lease_history)
            if item.get("run_id") == lease.get("run_id")
            and item.get("episode_id") == lease.get("episode_id")
            and item.get("result") == "active"
        ),
        None,
    )
    if lease.get("result") == "active":
        expected_context = context_binding(
            topic=lease.get("topic"),
            role="claude-code",
            task=str(lease.get("task") or "implement"),
            track=str(lease.get("mode") or "poc"),
        )
        pack_sha, pack = replay_pack_binding(
            episode_id,
            task=str(lease.get("task") or "implement"),
            manifest_sha=expected_context.get("manifest_sha"),
            context_plan_sha=expected_context.get("plan_sha"),
        )
        semantic = validate_runtime_lease_binding(
            lease,
            root=ROOT,
            expected={
                "topic": lease.get("topic"),
                "task": lease.get("task"),
                "repo_head": git_head(),
                "base_sha": pack.get("base_sha"),
                "plan_sha": expected_context.get("plan_sha"),
                "allowed_write_root": pack.get("allowed_write_root"),
                "manifest_sha": expected_context.get("manifest_sha"),
                "pack_sha": pack_sha,
                "episode_id": episode_id,
                "branch": lease.get("branch"),
                "repo_root": str(ROOT),
            },
        )
        if not semantic["valid"]:
            raise ValueError(
                f"invalid runtime lease binding: {semantic['errors']}"
            )
        lease["binding_proof"] = runtime_lease_binding_proof(lease, root=ROOT)
    else:
        if prior_active is None or not prior_active.get("binding_proof"):
            raise ValueError("release requires recorded acquisition binding proof")
        expected_context = {
            "manifest_sha": prior_active.get("manifest_sha"),
            "plan_sha": prior_active.get("context_plan_sha"),
        }
        pack_sha = str(prior_active.get("pack_sha") or "")
        pack_object = ndf_replay.ReplayStore(ROOT).get_object(pack_sha, "blob")[
            "data"
        ]
        pack = pack_object.get("value")
        if not isinstance(pack, dict):
            raise ValueError("recorded runtime pack is not an object")
        lease["binding_proof"] = prior_active["binding_proof"]
    recorded_binding = validate_recorded_runtime_lease_binding(
        lease,
        expected={
            "topic": lease.get("topic"),
            "task": lease.get("task"),
            "base_sha": pack.get("base_sha"),
            "plan_sha": expected_context.get("plan_sha"),
            "manifest_sha": expected_context.get("manifest_sha"),
            "allowed_write_root": pack.get("allowed_write_root"),
            "pack_sha": pack_sha,
            "episode_id": episode_id,
            "branch": lease.get("branch"),
            "repo_root": str(ROOT),
        },
    )
    if not recorded_binding["valid"]:
        raise ValueError(
            f"invalid recorded runtime binding: {recorded_binding['errors']}"
        )
    append_lease(LEASE_LOG, lease, root=ROOT)
    if episode_id:
        store = ndf_replay.ReplayStore(ROOT)
        lease_blob = store.put_blob(dict(lease))
        if lease.get("result") == "active":
            store.append_event(
                episode_id,
                kind="acp.start",
                actor="claude-code",
                payload_sha=lease_blob,
                topic=lease.get("topic"),
                task=str(lease.get("task") or "implement"),
                track=str(lease.get("mode") or "poc"),
                repo_head=lease.get("repo_head"),
                manifest_sha=lease.get("manifest_sha"),
                context_plan_sha=lease.get("context_plan_sha"),
                session_id=lease.get("session_id"),
                run_id=lease.get("run_id"),
                branch="implementation",
            )
        event = store.append_event(
            episode_id,
            kind="lease.acquired" if lease.get("result") == "active" else "lease.released",
            actor="claude-code",
            payload_sha=lease_blob,
            topic=lease.get("topic"),
            task=str(lease.get("task") or "implement"),
            track=str(lease.get("mode") or "poc"),
            repo_head=lease.get("repo_head"),
            manifest_sha=lease.get("manifest_sha"),
            context_plan_sha=lease.get("context_plan_sha"),
            session_id=lease.get("session_id"),
            run_id=lease.get("run_id"),
            branch="implementation",
        )
        run_commit = store.commit_events(
            episode_id,
            message=f"runtime lease {lease.get('result')}",
            actor="claude-code",
            branch="implementation",
            coverage={"runtime_lease": lease_blob},
        )
        store.update_ref(f"runs/{lease.get('run_id')}", run_commit)
        lease = {
            **lease,
            "replay": {
                "episode_id": episode_id,
                "blob_sha": lease_blob,
                "event_sha": event["event_sha"],
            },
        }
    return lease


def record_agent_message(
    path: Path,
    *,
    episode_id: str,
    role: str,
    direction: str,
    coverage: str,
) -> tuple[dict[str, Any], int]:
    """Capture an OpenClaw/Claude visible request or response."""
    message = json.loads(path.read_text(encoding="utf-8"))
    expected_schema = "ndf-agent-message/v1"
    errors: list[str] = []
    if message.get("schema") != expected_schema:
        errors.append("unsupported_schema")
    for field in (
        "task",
        "track",
        "manifest_sha",
        "context_plan_sha",
        "session_id",
        "run_id",
        "message",
    ):
        if field not in message:
            errors.append(f"missing:{field}")
    if direction not in {"request", "response"}:
        errors.append("invalid_direction")
    allowed_coverage = (
        {"full_stream", "messages_only"}
        if role == "openclaw"
        else {"full_stream", "completion_only"}
    )
    if coverage not in allowed_coverage:
        errors.append("invalid_runtime_coverage")
    pipeline_task = str(message.get("task") or "") in {
        "gate_pipeline",
        "binder_pipeline",
    }
    if role == "openclaw" and pipeline_task:
        if not message.get("request_id"):
            errors.append("missing:request_id")
        if message.get("pipeline") not in {PIPELINE_GATE, PIPELINE_BINDER}:
            errors.append("invalid_pipeline")
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        errors.append("unknown_episode")
    historical_pack: dict[str, Any] | None = None
    historical_pack_sha: str | None = None
    if not errors:
        try:
            _, historical_pack = replay_pack_binding(
                episode_id,
                task=str(message.get("task")),
                manifest_sha=message.get("manifest_sha"),
                context_plan_sha=message.get("context_plan_sha"),
            )
        except (FileNotFoundError, ValueError):
            errors.append("missing:historical_pack")
    expected_provider = (
        "openclaw" if role == "openclaw" else "claude-code-acp"
    )
    if historical_pack and historical_pack.get("provider") != expected_provider:
        errors.append("provider_mismatch")
    if historical_pack and pipeline_task:
        if historical_pack.get("pipeline") != message.get("pipeline"):
            errors.append("pipeline_mismatch")
        if historical_pack.get("topic") != message.get("topic"):
            errors.append("topic_mismatch")
    if (
        role == "openclaw"
        and pipeline_task
        and direction == "response"
        and message.get("request_id")
        and _message_event_for_request(
            store,
            episode_id,
            request_id=str(message.get("request_id")),
            kind="openclaw.request",
        )
        is None
    ):
        errors.append("missing:matching_request")
    if errors:
        return {
            "schema": "ndf-agent-message-verification/v1",
            "valid": False,
            "errors": sorted(set(errors)),
        }, 1
    payload = dict(message)
    session_key = payload.pop("session_key", None)
    provenance_sha = None
    if session_key is not None:
        provenance_sha = store.put_blob(
            {
                "schema": "ndf-encrypted-session-provenance/v1",
                "session_key": session_key,
                "session_id": message.get("session_id"),
                "run_id": message.get("run_id"),
            },
            sensitivity="secret",
        )
    payload["direction"] = direction
    payload["stream_coverage"] = coverage
    payload["session_provenance_sha"] = provenance_sha
    blob_sha = store.put_blob(payload, sensitivity="sensitive")
    branch = "control" if role == "openclaw" else "implementation"
    kind = (
        f"openclaw.{direction}"
        if role == "openclaw"
        else f"model.{direction}"
    )
    event = store.append_event(
        episode_id,
        kind=kind,
        actor=role,
        payload_sha=blob_sha,
        topic=message.get("topic"),
        task=str(message.get("task")),
        track=str(message.get("track")),
        repo_head=message.get("repo_head"),
        manifest_sha=message.get("manifest_sha"),
        context_plan_sha=message.get("context_plan_sha"),
        session_id=message.get("session_id"),
        run_id=message.get("run_id"),
        branch=branch,
    )
    commit_sha = store.commit_events(
        episode_id,
        message=f"{role} {direction} ({coverage})",
        actor=role,
        branch=branch,
        coverage={"runtime_stream": coverage},
    )
    return {
        "schema": "ndf-agent-message-verification/v1",
        "valid": True,
        "episode_id": episode_id,
        "coverage": coverage,
        "blob_sha": blob_sha,
        "event_sha": event["event_sha"],
        "commit_sha": commit_sha,
    }, 0


def record_close_receipt(path: Path) -> tuple[dict[str, Any], int]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    verification = verify_close_receipt(receipt)
    if not verification["valid"]:
        return verification, 1
    episode_id = receipt.get("episode_id")
    store = ndf_replay.ReplayStore(ROOT) if episode_id else None
    if store and store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        return {
            **verification,
            "valid": False,
            "errors": [*verification["errors"], "unknown_episode"],
        }, 1
    target = _close_receipt_path(
        str(receipt["topic"]),
        str(receipt["mode"]),
        str(receipt["step"]),
    )
    write_json_artifact(target, dict(receipt))
    result = {
        **verification,
        "written": rel(target),
    }
    if episode_id and store:
        blob_sha = store.put_blob(dict(receipt))
        event = store.append_event(
            str(episode_id),
            kind="close.receipt",
            actor=str(receipt.get("actor") or "tool"),
            payload_sha=blob_sha,
            topic=receipt.get("topic"),
            task=str(receipt.get("task") or "close"),
            track=str(receipt.get("mode") or "process"),
            repo_head=receipt.get("repo_head"),
            manifest_sha=receipt.get("manifest_sha"),
            context_plan_sha=receipt.get("context_plan_sha"),
            branch="control",
        )
        commit_sha = store.commit_events(
            str(episode_id),
            message=f"close receipt {receipt.get('step')}",
            actor=str(receipt.get("actor") or "tool"),
            branch="control",
            coverage={"close_receipt": blob_sha},
        )
        result["replay"] = {
            "episode_id": episode_id,
            "blob_sha": blob_sha,
            "event_sha": event["event_sha"],
            "commit_sha": commit_sha,
        }
        if (
            receipt.get("step") == "finalize"
            and receipt.get("mode") in {"promote", "partial"}
        ):
            control_ref = f"branches/{episode_id}/control"
            implementation_ref = f"branches/{episode_id}/implementation"
            if store.read_ref(control_ref) and store.read_ref(implementation_ref):
                result["replay"]["merge_commit_sha"] = store.merge(
                    str(episode_id),
                    control_ref,
                    implementation_ref,
                    message=f"verified {receipt.get('mode')} episode merge",
                    actor="close",
                )
                result["replay"]["ledger"] = store.ledger_entry(
                    str(episode_id),
                    write=True,
                )
    return result, 0


def project_control_acquisition_of(
    store: Any,
    episode_id: str,
    pack: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Prefer pack snapshot; else the latest filesystem.acquired event."""
    snapshot = pack.get("acquisition_snapshot")
    if isinstance(snapshot, Mapping):
        return dict(snapshot)
    for event in reversed(
        [
            item
            for events in store.read_all_events(episode_id).values()
            for item in events
        ]
    ):
        if event.get("kind") != "filesystem.acquired":
            continue
        try:
            blob = store.get_object(str(event["payload_sha"]), "blob")["data"]
        except (FileNotFoundError, ValueError, KeyError):
            continue
        value = blob.get("value") if blob.get("encoding") == "json" else None
        if isinstance(value, Mapping):
            return dict(value)
    return None


def record_project_control_acquisition(episode_id: str) -> dict[str, Any]:
    """Pin the hop's starting dirty set before land writes."""
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        raise ValueError(f"unknown replay episode: {episode_id}")
    snapshot = git_mutation_snapshot(ROOT)
    blob_sha = store.put_blob(snapshot)
    event = store.append_event(
        episode_id,
        kind="filesystem.acquired",
        actor="project-control",
        payload_sha=blob_sha,
        topic=None,
        task="ndf_improvement_land",
        track="process",
        repo_head=git_head(),
        manifest_sha=None,
        context_plan_sha=None,
        branch="control",
    )
    return {
        "schema": "ndf-project-control-acquisition/v1",
        "episode_id": episode_id,
        "event_sha": event["event_sha"],
        "snapshot_sha": snapshot.get("snapshot_sha"),
        "paths": snapshot.get("paths"),
    }


def project_control_declared_files(pack: Mapping[str, Any]) -> list[str]:
    """Exact stage write set from a project-control pack."""
    roots = pack.get("allowed_write_roots")
    if isinstance(roots, list) and all(isinstance(item, str) and item for item in roots):
        return list(dict.fromkeys(item.rstrip("/") for item in roots))
    proposal = (
        pack.get("proposal") if isinstance(pack.get("proposal"), Mapping) else {}
    )
    declared = [
        str(item).rstrip("/")
        for item in (proposal.get("land_targets") or [])
        if str(item).strip()
    ]
    path = proposal.get("path")
    if isinstance(path, str) and path.strip():
        declared.append(path.rstrip("/"))
    return list(dict.fromkeys(declared))


def project_control_git_extras(
    root: Path,
    declared: list[str],
    acquisition: Mapping[str, Any] | None = None,
) -> list[str]:
    """Dirty paths that changed during this hop and are not the stage write set."""
    snapshot = git_mutation_snapshot(root)
    extras: list[str] = []
    declared_set = set(declared)
    before_paths = set()
    before_shas: dict[str, Any] = {}
    if isinstance(acquisition, Mapping):
        before_paths = {str(path) for path in (acquisition.get("paths") or [])}
        raw_shas = acquisition.get("path_shas")
        if isinstance(raw_shas, Mapping):
            before_shas = {str(path): raw_shas[path] for path in raw_shas}
    after_shas = snapshot.get("path_shas")
    if not isinstance(after_shas, Mapping):
        after_shas = {}
    for path in snapshot.get("paths") or []:
        if path in declared_set:
            continue
        if path == ".ndf" or path.startswith(".ndf/"):
            continue
        if path == "tmp" or path.startswith("tmp/"):
            continue
        if isinstance(acquisition, Mapping):
            if path in before_paths and after_shas.get(path) == before_shas.get(path):
                continue
        extras.append(str(path))
    return extras


def attach_project_control_mutation_proof(
    completion: dict[str, Any],
    *,
    declared: list[str],
    root: Path,
    base_sha: str,
    acquisition: Mapping[str, Any] | None = None,
) -> list[str]:
    """Fail closed unless declared, reported, and actual writes match."""
    if not declared:
        return ["project_control_stage_write_violation"]
    errors = ndf_replay.validate_project_control_mutation(
        {
            "changed_files": completion.get("changed_files", []),
            "declared_files": declared,
            "allowed_write_roots": declared,
        }
    )
    try:
        extras = project_control_git_extras(root, declared, acquisition)
        if extras:
            errors.append("project_control_mutation_mismatch")
        proof = completion.get("mutation_proof")
        if isinstance(proof, Mapping):
            actual = {str(path) for path in (proof.get("actual_mutations") or [])}
            if actual != set(declared):
                errors.append("project_control_mutation_mismatch")
        else:
            proof = {
                "schema": "ndf-runtime-mutation-proof/v1",
                "declared_mutations": sorted(declared),
                "actual_mutations": sorted(declared),
                "committed_paths": [],
                "git_extras": extras,
                "base_sha": base_sha,
            }
            proof["proof_sha"] = canonical_json_sha(proof)
            completion["mutation_proof"] = proof
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(f"mutation_proof_failed:{type(exc).__name__}")
    return list(dict.fromkeys(errors))


LEASE_HOSTED_IMPLEMENTATION_TASKS = POC_IMPLEMENTATION_TASKS | BASELINE_PREP_TASKS


def find_runtime_lease_for_completion(
    leases: list[dict[str, Any]],
    completion: Mapping[str, Any],
    *,
    episode_id: str,
    role: str,
) -> dict[str, Any] | None:
    """Match an active runtime lease to a Worker completion receipt."""
    if role != "claude-code":
        return None
    comp_task = str(completion.get("task") or "")
    comp_topic = str(completion.get("topic") or "")
    comp_wt = str(completion.get("worktree") or "").strip()
    comp_sid = str(completion.get("session_id") or "").strip()
    comp_run = str(completion.get("run_id") or "").strip()

    for lease in reversed(leases):
        if str(lease.get("result") or "") != "active":
            continue
        if (
            lease.get("run_id") == comp_run
            and lease.get("session_id") == completion.get("session_id")
            and lease.get("episode_id") == episode_id
            and lease.get("task") == comp_task
        ):
            return lease

    if comp_task in LEASE_HOSTED_IMPLEMENTATION_TASKS:
        for lease in reversed(leases):
            if str(lease.get("result") or "") != "active":
                continue
            if str(lease.get("topic") or "") != comp_topic:
                continue
            lease_wt = str(lease.get("worktree") or "").strip()
            lease_sid = str(lease.get("session_id") or "").strip()
            if comp_sid and lease_sid and comp_sid != lease_sid:
                continue
            if comp_wt and lease_wt:
                try:
                    comp_resolved = Path(comp_wt).resolve()
                    lease_resolved = Path(lease_wt).resolve()
                except OSError:
                    continue
                if comp_resolved == lease_resolved:
                    return lease
                # Worker may fall back to main repo when lease worktree lacks
                # gitignored deps; still bind to the active topic lease.
                if comp_resolved == ROOT.resolve():
                    return lease
                continue
            return lease
    return None


def record_agent_completion(
    path: Path,
    *,
    episode_id: str,
    role: str,
    coverage: str,
) -> tuple[dict[str, Any], int]:
    """Bind an Agent completion to its manifest/plan and Episode history."""
    completion = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if completion.get("schema") != "ndf-agent-completion/v1":
        errors.append("unsupported_schema")
    for field in (
        "task",
        "track",
        "base_sha",
        "repo_head",
        "manifest_sha",
        "context_plan_sha",
        "changed_files",
        "changed_file_shas",
        "reproduce_commands",
        "evidence_paths",
        "evidence_bundle_sha",
        "git_commit",
        "post_check_receipts",
        "result",
    ):
        if field not in completion:
            errors.append(f"missing:{field}")
    if role == "claude-code":
        for field in ("worktree", "branch", "run_id", "session_id"):
            if field not in completion:
                errors.append(f"missing:{field}")
    store = ndf_replay.ReplayStore(ROOT)
    if store.read_ref(f"episodes/{episode_id}/HEAD") is None:
        return {
            "schema": "ndf-agent-completion-verification/v1",
            "valid": False,
            "errors": ["unknown_episode"],
        }, 1
    historical_pack: dict[str, Any] | None = None
    for replay_event in reversed(
        [
            item
            for events in store.read_all_events(episode_id).values()
            for item in events
        ]
    ):
        if (
            replay_event.get("kind") != "dispatch.preflight"
            or replay_event.get("task") != completion.get("task")
        ):
            continue
        try:
            blob = store.get_object(str(replay_event["payload_sha"]), "blob")["data"]
        except (FileNotFoundError, ValueError, KeyError):
            continue
        if blob.get("encoding") == "json" and isinstance(blob.get("value"), dict):
            candidate = blob["value"]
            expected_provider = (
                "claude-code-acp" if role == "claude-code" else "openclaw"
            )
            pack_ready = candidate.get("safe_to_dispatch") is True
            if completion.get("task") in PROJECT_CONTROL_TASKS:
                pack_ready = pack_ready or (
                    candidate.get("static_preflight_passed") is True
                    or candidate.get("safe_to_delegate") is True
                )
            if (
                candidate.get("provider") == expected_provider
                and pack_ready
            ):
                historical_pack = candidate
                historical_pack_sha = str(replay_event["payload_sha"])
                break
    if historical_pack is None:
        errors.append("missing:historical_pack")
        historical_pack = {}
    if completion.get("manifest_sha") != historical_pack.get("manifest_sha"):
        errors.append("stale:manifest_sha")
    if completion.get("context_plan_sha") != historical_pack.get("plan_sha"):
        errors.append("stale:context_plan_sha")
    if completion.get("base_sha") != historical_pack.get("base_sha"):
        errors.append("stale:base_sha")
    completion_root = ROOT
    matching_lease: dict[str, Any] | None = None
    main_repo_fallback = False
    if role == "claude-code":
        try:
            leases = read_leases(LEASE_LOG, root=ROOT, strict=False)
        except ValueError:
            leases = []
        matching_lease = find_runtime_lease_for_completion(
            leases,
            completion,
            episode_id=episode_id,
            role=role,
        )
        if matching_lease is None or matching_lease.get("result") != "active":
            errors.append("missing:active_runtime_lease")
        else:
            lease_wt = Path(str(matching_lease.get("worktree"))).resolve()
            claimed_wt = Path(str(completion.get("worktree") or "")).resolve()
            main_repo_fallback = (
                claimed_wt == ROOT.resolve() and claimed_wt != lease_wt
            )
            if main_repo_fallback:
                # Evidence and mayWrite landed on the commander tree.
                completion_root = claimed_wt
            else:
                completion_root = lease_wt
                if claimed_wt != completion_root:
                    errors.append("mismatch:worktree")
                if completion.get("branch") != matching_lease.get("branch"):
                    errors.append("mismatch:branch")
            lease_task = str(matching_lease.get("task") or "")
            comp_task = str(completion.get("task") or "")
            implementation_on_prep_lease = (
                comp_task in LEASE_HOSTED_IMPLEMENTATION_TASKS
                and lease_task == "prepare_acp_lease"
            )
            if implementation_on_prep_lease:
                proof = matching_lease.get("binding_proof")
                if not isinstance(proof, Mapping):
                    errors.append("missing:binding_proof")
                else:
                    unhashed = {
                        key: value
                        for key, value in proof.items()
                        if key != "proof_sha"
                    }
                    if proof.get("proof_sha") != canonical_json_sha(unhashed):
                        errors.append("mismatch:binding_proof_sha")
            else:
                lease_check = validate_recorded_runtime_lease_binding(
                    matching_lease,
                    expected={
                        "topic": completion.get("topic"),
                        "task": lease_task,
                        "repo_head": matching_lease.get("repo_head"),
                        "base_sha": historical_pack.get("base_sha"),
                        "plan_sha": completion.get("context_plan_sha"),
                        "manifest_sha": completion.get("manifest_sha"),
                        "allowed_write_root": historical_pack.get("allowed_write_root"),
                        "pack_sha": historical_pack_sha,
                        "episode_id": episode_id,
                        "branch": matching_lease.get("branch"),
                        "repo_root": str(ROOT),
                    },
                )
                if not lease_check["valid"]:
                    errors.extend(
                        f"runtime_lease:{item}" for item in lease_check["errors"]
                    )
                live_lease_check = validate_runtime_lease_binding(
                    matching_lease,
                    root=ROOT,
                    expected={
                        "topic": completion.get("topic"),
                        "task": lease_task,
                        "base_sha": historical_pack.get("base_sha"),
                        "plan_sha": completion.get("context_plan_sha"),
                        "manifest_sha": completion.get("manifest_sha"),
                        "allowed_write_root": historical_pack.get("allowed_write_root"),
                        "pack_sha": historical_pack_sha,
                        "episode_id": episode_id,
                        "branch": matching_lease.get("branch"),
                        "repo_root": str(ROOT),
                    },
                )
                if not live_lease_check["valid"]:
                    errors.extend(
                        f"runtime_lease_current:{item}"
                        for item in live_lease_check["errors"]
                    )
            current_head = subprocess.run(
                ["git", "-C", str(completion_root), "rev-parse", "HEAD"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if (
                current_head.returncode != 0
                or current_head.stdout.strip() != completion.get("repo_head")
            ):
                errors.append("stale:completion_repo_head")
    for field in ("changed_files", "reproduce_commands", "evidence_paths"):
        if not isinstance(completion.get(field), list):
            errors.append(f"not_list:{field}")
    changed_sections = completion.get("changed_sections")
    section_sensitive = any(
        isinstance(item, str)
        and (
            item.endswith("/ndf/PERF_BASELINE.md")
            or item.endswith("/ndf/DELTA.md")
            or item.endswith("/ndf/TOPIC.md")
            or item.endswith("/ndf/COMMITS.md")
            or "/ndf/evidence/" in item
        )
        for item in completion.get("changed_files", [])
    )
    if section_sensitive and not isinstance(changed_sections, list):
        errors.append("missing:changed_sections")
        changed_sections = []
    elif not isinstance(changed_sections, list):
        changed_sections = []
    allowed_sections = set(
        historical_pack.get("context_plan", {})
        .get("privileges", {})
        .get("allowed_sections", [])
    )
    section_violations = {
        str(section)
        for section in changed_sections
        if str(section) not in allowed_sections
    }
    if section_violations:
        errors.append("cross_role_section_write")
    missing_evidence = [
        item
        for item in completion.get("evidence_paths", [])
        if not isinstance(item, str) or not (completion_root / item).is_file()
    ]
    if missing_evidence:
        errors.append("missing:evidence_paths")
    if not missing_evidence and completion.get("evidence_paths"):
        actual_evidence_sha = evidence_bundle_sha(
            completion["evidence_paths"],
            root=completion_root,
        )
        if completion.get("evidence_bundle_sha") != actual_evidence_sha:
            errors.append("mismatch:evidence_bundle_sha")
    changed_file_shas = completion.get("changed_file_shas")
    if not isinstance(changed_file_shas, dict):
        errors.append("not_object:changed_file_shas")
        changed_file_shas = {}
    for changed_path in completion.get("changed_files", []):
        target = completion_root / str(changed_path)
        if (
            not target.is_file()
            or changed_file_shas.get(changed_path) != file_sha(target)
        ):
            errors.append(f"changed_file_drift:{changed_path}")
    if (
        role == "claude-code"
        and matching_lease is not None
        and not main_repo_fallback
    ):
        try:
            completion_snapshot = git_mutation_snapshot(completion_root)
            acquisition_snapshot = matching_lease.get("binding_proof", {}).get(
                "acquisition_snapshot", {}
            )
            acquisition_head = str(acquisition_snapshot.get("head") or "")
            committed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(completion_root),
                    "diff",
                    "--name-only",
                    "-z",
                    f"{acquisition_head}..{completion_snapshot['head']}",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if committed.returncode != 0:
                errors.append("mutation_diff_unavailable")
                committed_paths: set[str] = set()
            else:
                committed_paths = {
                    item.decode("utf-8", errors="surrogateescape")
                    for item in committed.stdout.split(b"\0")
                    if item
                }
            before_shas = acquisition_snapshot.get("path_shas", {})
            after_shas = completion_snapshot.get("path_shas", {})
            worktree_paths = {
                path
                for path in set(before_shas) | set(after_shas)
                if before_shas.get(path) != after_shas.get(path)
            }
            actual_mutations = committed_paths | worktree_paths
            # The disk completion receipt is attestation, not a product
            # mutation. record_agent_completion often validates a tmp/ copy,
            # so exclude by evidence naming convention + optional pack path.
            receipt_candidates: set[str] = set()
            for item in actual_mutations:
                norm = str(item).replace("\\", "/")
                if "/ndf/evidence/" in norm and norm.endswith("-completion.json"):
                    receipt_candidates.add(item)
            topic = str(completion.get("topic") or "").strip()
            task = str(completion.get("task") or "").strip()
            if topic and task:
                receipt_candidates.add(
                    f"poc/{topic}/ndf/evidence/{task}-completion.json"
                )
            excluded = sorted(actual_mutations & receipt_candidates)
            actual_mutations -= receipt_candidates
            declared_mutations = {
                str(item) for item in completion.get("changed_files", [])
            }
            if actual_mutations != declared_mutations:
                errors.append("changed_files_do_not_match_actual_mutations")
            completion["mutation_proof"] = {
                "schema": "ndf-runtime-mutation-proof/v1",
                "acquisition_snapshot_sha": acquisition_snapshot.get(
                    "snapshot_sha"
                ),
                "completion_snapshot": completion_snapshot,
                "committed_paths": sorted(committed_paths),
                "actual_mutations": sorted(actual_mutations),
                "declared_mutations": sorted(declared_mutations),
                "excluded_receipts": excluded,
            }
            completion["mutation_proof"]["proof_sha"] = canonical_json_sha(
                completion["mutation_proof"]
            )
        except (OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"mutation_proof_failed:{type(exc).__name__}")
    git_commit = str(completion.get("git_commit") or "")
    if git_commit:
        resolved = subprocess.run(
            ["git", "-C", str(completion_root), "rev-parse", f"{git_commit}^{{commit}}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if resolved.returncode != 0:
            errors.append("git_commit_unresolvable")
    expected_coverage = (
        {"full_stream", "completion_only"}
        if role == "claude-code"
        else {"full_stream", "messages_only"}
    )
    if coverage not in expected_coverage:
        errors.append("invalid_runtime_coverage")
    allowed_roots = (
        historical_pack.get("context_plan", {})
        .get("privileges", {})
        .get("allowed_write_roots", [])
    )
    write_violations = [
        item
        for item in completion.get("changed_files", [])
        if not isinstance(item, str)
        or item.startswith("/")
        or ".." in Path(item).parts
        or not any(
            item == root.rstrip("/") or item.startswith(root.rstrip("/") + "/")
            for root in allowed_roots
        )
    ]
    if write_violations:
        errors.append("write_root_violation")
    declared_write_set: list[str] = []
    if completion.get("task") in PROJECT_CONTROL_TASKS:
        declared_write_set = project_control_declared_files(historical_pack)
        errors.extend(
            attach_project_control_mutation_proof(
                completion,
                declared=declared_write_set,
                root=completion_root,
                base_sha=str(
                    completion.get("base_sha")
                    or historical_pack.get("base_sha")
                    or ""
                ),
                acquisition=project_control_acquisition_of(
                    store,
                    episode_id,
                    historical_pack,
                ),
            )
        )
    if completion.get("result") not in {"success", "passed", "completed"}:
        errors.append("result_not_green")
    post_checks = completion.get("post_check_receipts")
    if not isinstance(post_checks, list) or not post_checks:
        errors.append("missing:post_check_receipts")
    else:
        allowed_post_checks = {
            "ndf_poc_isolation.py",
            "ndf_workflow_status.py",
            "ndf_perf_baseline.py",
            "ndf_bindcheck.py",
            "ndf_graphcheck.py",
        }
        for index, receipt in enumerate(post_checks):
            if not isinstance(receipt, Mapping):
                errors.append(f"invalid:post_check:{index}")
                continue
            try:
                tokens = shlex.split(str(receipt.get("command") or ""))
            except ValueError:
                tokens = []
            safe_tokens = bool(tokens) and not any(
                any(char in token for char in ";&|><") for token in tokens
            )
            executable = Path(tokens[0]).name if tokens else ""
            arguments = tokens[1:]
            script = executable
            if executable in {"python", "python3", "bash", "sh"}:
                if not arguments or arguments[0].startswith("-"):
                    safe_tokens = False
                else:
                    script = Path(arguments[0]).name
            if (
                receipt.get("result") not in {"passed", "success", "completed"}
                or not safe_tokens
                or script not in allowed_post_checks
            ):
                errors.append(f"invalid:post_check:{index}")
            verifier = receipt.get("verifier")
            if not isinstance(verifier, Mapping):
                errors.append(f"missing:post_check_verifier:{index}")
            else:
                verifier_path = Path(str(verifier.get("path") or ""))
                if (
                    not verifier_path.is_absolute()
                    or not verifier_path.is_file()
                    or verifier_path.name != script
                    or verifier.get("argv") != tokens
                    or verifier.get("version_sha") != file_sha(verifier_path)
                    or verifier.get("exit_code") != 0
                    or not verifier.get("output_schema")
                ):
                    errors.append(f"invalid:post_check_verifier:{index}")
            post_evidence = validate_evidence_bundle(receipt, root=completion_root)
            if not post_evidence["valid"]:
                errors.append(f"invalid:post_check_evidence:{index}")
    if errors:
        return {
            "schema": "ndf-agent-completion-verification/v1",
            "valid": False,
            "errors": sorted(set(errors)),
            "write_violations": write_violations,
        }, 1
    blob_sha = store.put_blob(completion)
    branch = "implementation" if role == "claude-code" else "control"
    event = store.append_event(
        episode_id,
        kind="acp.complete" if role == "claude-code" else "openclaw.response",
        actor=role,
        payload_sha=blob_sha,
        topic=completion.get("topic"),
        task=str(completion["task"]),
        track=str(completion["track"]),
        repo_head=completion.get("repo_head"),
        manifest_sha=completion.get("manifest_sha"),
        context_plan_sha=completion.get("context_plan_sha"),
        session_id=completion.get("session_id"),
        run_id=completion.get("run_id"),
        branch=branch,
    )
    if completion.get("task") in PROJECT_CONTROL_TASKS:
        mutation_blob = store.put_blob(
            {
                "changed_files": list(completion.get("changed_files") or []),
                "declared_files": declared_write_set,
                "allowed_write_roots": declared_write_set,
                "changed_file_shas": completion.get("changed_file_shas"),
                "proposal_id": historical_pack.get("proposal_id"),
                "flow_id": historical_pack.get("flow_id"),
                "hop": historical_pack.get("hop"),
                "manifest_sha": completion.get("manifest_sha"),
                "context_plan_sha": completion.get("context_plan_sha"),
            }
        )
        store.append_event(
            episode_id,
            kind="filesystem.changed",
            actor="project-control",
            payload_sha=mutation_blob,
            topic=completion.get("topic"),
            task=str(completion["task"]),
            track=str(completion["track"]),
            repo_head=completion.get("repo_head"),
            manifest_sha=completion.get("manifest_sha"),
            context_plan_sha=completion.get("context_plan_sha"),
            session_id=completion.get("session_id"),
            run_id=completion.get("run_id"),
            branch=branch,
        )
    commit_sha = store.commit_events(
        episode_id,
        message=f"{role} completion ({coverage})",
        actor=role,
        branch=branch,
        coverage={"runtime_stream": coverage},
    )
    return {
        "schema": "ndf-agent-completion-verification/v1",
        "valid": True,
        "episode_id": episode_id,
        "coverage": coverage,
        "blob_sha": blob_sha,
        "event_sha": event["event_sha"],
        "commit_sha": commit_sha,
        "write_violations": [],
    }, 0


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    genesis_status_parser = sub.add_parser("genesis-status")
    genesis_status_parser.add_argument("--json", action="store_true")

    genesis_pack_parser = sub.add_parser("genesis-pack")
    genesis_pack_parser.add_argument("--mode", choices=("greenfield", "adopt"), required=True)
    genesis_pack_parser.add_argument("--episode")
    genesis_pack_parser.add_argument("--json", action="store_true")

    host_pids_parser = sub.add_parser(
        "host-pids",
        help="Report cgroup PID/thread headroom and local suspects on EAGAIN",
    )
    host_pids_parser.add_argument("--json", action="store_true")
    host_pids_parser.add_argument(
        "--kill-stale-serve",
        action="store_true",
        help="Explicitly SIGTERM this repo's lock-held --serve and clear the lock",
    )

    topic_health_parser = sub.add_parser("topic-health")
    topic_health_parser.add_argument("--topic", required=True)
    topic_health_parser.add_argument("--json", action="store_true")

    spec_health_parser = sub.add_parser("spec-health")
    spec_health_parser.add_argument("--json", action="store_true")

    dispatch_send_parser = sub.add_parser(
        "dispatch-send",
        help="Send a safe pack to OpenClaw/ACP and wait for disk completion",
    )
    dispatch_send_parser.add_argument(
        "--pack-file",
        required=True,
        help="JSON pack from control-pack / project-control-pack / genesis-pack / repair-pack",
    )
    dispatch_send_parser.add_argument("--catalog-action-id")
    dispatch_send_parser.add_argument("--action-id")
    dispatch_send_parser.add_argument("--timeout-sec", type=int)
    dispatch_send_parser.add_argument("--dry-run", action="store_true")
    dispatch_send_parser.add_argument("--json", action="store_true")

    dispatch_probe_parser = sub.add_parser(
        "dispatch-probe",
        help="Human 「进展如何」: probe ACP/OpenClaw liveness without a second send",
    )
    dispatch_probe_parser.add_argument("--json", action="store_true")

    dispatch_closeout_replay_parser = sub.add_parser(
        "dispatch-closeout-replay",
        help="Re-run closeout from tmp/ndf-dispatch-last.json without resending ACP/OpenClaw",
    )
    dispatch_closeout_replay_parser.add_argument(
        "--pack-file",
        required=True,
        help="JSON pack (same as the failed dispatch-send)",
    )
    dispatch_closeout_replay_parser.add_argument("--catalog-action-id")
    dispatch_closeout_replay_parser.add_argument("--action-id")
    dispatch_closeout_replay_parser.add_argument(
        "--force",
        action="store_true",
        help="Replay even when prior dispatch-last already succeeded",
    )
    dispatch_closeout_replay_parser.add_argument("--json", action="store_true")

    pack_parser = sub.add_parser("pack")
    pack_parser.add_argument("--topic", required=True)
    pack_parser.add_argument("--episode")
    pack_parser.add_argument(
        "--task",
        choices=["poc_implementation", "prepare_acp_lease"],
        default="poc_implementation",
    )
    pack_parser.add_argument("--json", action="store_true")

    poc_dispatch_parser = sub.add_parser(
        "poc-dispatch",
        help="Text-first POC dispatch: hard gates only, inline lease (ADR-META-004)",
    )
    poc_dispatch_parser.add_argument("--topic", required=True)
    poc_dispatch_parser.add_argument(
        "--intent",
        choices=sorted(POC_DISPATCH_INTENTS),
        default="implement",
    )
    poc_dispatch_parser.add_argument(
        "--send",
        action="store_true",
        help="After pack+lease, call dispatch-send",
    )
    poc_dispatch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --send, prepare transport without invoking ACP",
    )
    poc_dispatch_parser.add_argument("--episode")
    poc_dispatch_parser.add_argument("--json", action="store_true")

    repair_pack_parser = sub.add_parser("repair-pack")
    repair_pack_parser.add_argument("--topic", required=True)
    repair_pack_parser.add_argument(
        "--task",
        choices=sorted(IMPLEMENTATION_REPAIR_TASKS),
        required=True,
    )
    repair_pack_parser.add_argument("--episode")
    repair_pack_parser.add_argument(
        "--action-id",
        help="UUID from action-begin; stamped on pack for hook closeout",
    )
    repair_pack_parser.add_argument("--json", action="store_true")

    control_pack_parser = sub.add_parser("control-pack")
    control_pack_parser.add_argument(
        "--topic",
        help="Required except for topic-less product_proposal/process_proposal idea hops",
    )
    control_pack_parser.add_argument(
        "--task",
        choices=sorted(CONTROL_TASKS),
        required=True,
    )
    control_pack_parser.add_argument("--episode")
    control_pack_parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse active control pipeline Episode for this topic",
    )
    control_pack_parser.add_argument(
        "--focus-gate",
        choices=list(GATE_ORDER),
        help="Focus one human gate step inside gate_pipeline / legacy_gate_audit",
    )
    control_pack_parser.add_argument(
        "--focus-binder-facet",
        choices=list(BINDER_FACET_ORDER),
        help="Focus one binder facet inside binder_pipeline / binder_amend",
    )
    control_pack_parser.add_argument(
        "--intent-file",
        help="UTF-8 human product intent under repo tmp/; required for topic-less control_proposal",
    )
    control_pack_parser.add_argument("--json", action="store_true")

    project_control_parser = sub.add_parser("project-control-pack")
    project_control_parser.add_argument(
        "--task",
        choices=sorted(PROJECT_CONTROL_TASKS),
        required=True,
    )
    project_control_parser.add_argument("--episode", required=True)
    project_control_parser.add_argument(
        "--origin",
        choices=sorted(PROJECT_CONTROL_ORIGINS),
        default="health_finding",
    )
    project_control_parser.add_argument(
        "--intent-file",
        help="UTF-8 human intent artifact under repo tmp/; requires --origin human_intent",
    )
    project_control_parser.add_argument(
        "--proposal",
        help="spec/meta/open/proposal-meta-*.md path; requires --task ndf_improvement_land",
    )
    project_control_parser.add_argument("--json", action="store_true")

    close_parser = sub.add_parser("close-plan")
    close_parser.add_argument("--topic", required=True)
    close_parser.add_argument("--mode", choices=("promote", "reject", "partial"), required=True)
    close_parser.add_argument("--ids", nargs="*", default=[])
    close_parser.add_argument("--json", action="store_true")

    lease_parser = sub.add_parser("lease-record")
    lease_parser.add_argument("--file")
    lease_parser.add_argument("--task", default="implement")
    lease_parser.add_argument("--topic")
    lease_parser.add_argument("--mode", default="poc")
    lease_parser.add_argument("--step", default="start")
    lease_parser.add_argument("--run-id")
    lease_parser.add_argument("--session-id")
    lease_parser.add_argument("--base-sha")
    lease_parser.add_argument("--worktree")
    lease_parser.add_argument("--branch")
    lease_parser.add_argument("--allowed-write-root")
    lease_parser.add_argument(
        "--result",
        choices=("active", "released", "expired", "failed"),
        default="active",
    )
    lease_parser.add_argument("--command-text", default="runtime lease")
    lease_parser.add_argument("--started-at")
    lease_parser.add_argument("--evidence-path", action="append", default=[])
    lease_parser.add_argument("--blocker", action="append", default=[])
    lease_parser.add_argument("--episode")
    lease_parser.add_argument("--action-id")
    lease_parser.add_argument("--json", action="store_true")

    close_verify_parser = sub.add_parser("close-receipt-verify")
    close_verify_parser.add_argument("--receipt", required=True)
    close_verify_parser.add_argument("--json", action="store_true")
    close_record_parser = sub.add_parser("close-receipt-record")
    close_record_parser.add_argument("--receipt", required=True)
    close_record_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "genesis-status":
            emit({"schema": "ndf-genesis-status/v1", "generated_at": now_iso(), **genesis_status()})
            return 0
        if args.command == "genesis-pack":
            payload, code = genesis_pack(args.mode, args.episode)
            persist_dispatch_pack(payload)
            emit(payload)
            return code
        if args.command == "host-pids":
            report = host_pids_report(kill_stale=args.kill_stale_serve)
            emit(report)
            return 0 if report.get("headroom_ok") else 1
        if args.command == "topic-health":
            payload, code = topic_health(args.topic)
            emit(payload)
            return code
        if args.command == "spec-health":
            payload, code = spec_health()
            emit(payload)
            return code
        if args.command == "dispatch-send":
            import ndf_dispatch_send

            pack = ndf_dispatch_send.load_pack_from_file(Path(args.pack_file))
            payload, code = ndf_dispatch_send.dispatch_send(
                pack,
                catalog_action_id=args.catalog_action_id,
                action_id=args.action_id,
                timeout_sec=args.timeout_sec,
                dry_run=args.dry_run,
            )
            emit(payload)
            return code
        if args.command == "dispatch-probe":
            import ndf_dispatch_send

            payload, code = ndf_dispatch_send.dispatch_probe()
            emit(payload)
            return code
        if args.command == "dispatch-closeout-replay":
            import ndf_dispatch_send

            pack = ndf_dispatch_send.load_pack_from_file(Path(args.pack_file))
            payload, code = ndf_dispatch_send.dispatch_closeout_replay(
                pack,
                catalog_action_id=args.catalog_action_id,
                action_id=args.action_id,
                force=args.force,
            )
            emit(payload)
            return code
        if args.command == "pack":
            if getattr(args, "task", "poc_implementation") == "prepare_acp_lease":
                payload, code = pack_prepare_acp_lease(args.topic, args.episode)
            else:
                payload, code = pack_topic(args.topic, args.episode)
            persist_dispatch_pack(payload)
            emit(payload)
            return code
        if args.command == "poc-dispatch":
            import ndf_poc_dispatch as poc_dispatch_mod

            payload, code = poc_dispatch_mod.poc_dispatch(
                args.topic,
                intent=args.intent,
                send=bool(args.send),
                episode_id=args.episode,
                dry_run=bool(args.dry_run),
            )
            emit(payload)
            return code
        if args.command == "repair-pack":
            payload, code = repair_pack(
                args.topic, args.task, args.episode, args.action_id
            )
            # repair_pack already persist_dispatch_pack
            emit(payload)
            return code
        if args.command == "control-pack":
            idea_tasks = PRODUCT_PROPOSAL_TASKS | {"process_proposal"}
            if args.task not in idea_tasks and not args.topic:
                raise ValueError(
                    "--topic is required except for product/process proposal idea hops"
                )
            if args.intent_file and args.task not in idea_tasks:
                raise ValueError(
                    "--intent-file is only valid for product/process proposal tasks"
                )
            payload, code = control_pack(
                args.topic,
                args.task,
                args.episode,
                focus_gate=args.focus_gate,
                focus_binder_facet=args.focus_binder_facet,
                resume=args.resume,
                intent=(
                    read_process_intent_file(args.intent_file)
                    if args.intent_file
                    else None
                ),
            )
            persist_dispatch_pack(payload)
            emit(payload)
            return code
        if args.command == "project-control-pack":
            if args.task == "ndf_improvement_land":
                if args.intent_file:
                    raise ValueError("--intent-file is not valid for ndf_improvement_land")
                payload, code = project_control_pack(
                    args.task,
                    args.episode,
                    proposal=args.proposal,
                )
            else:
                if args.proposal:
                    raise ValueError("--proposal requires --task ndf_improvement_land")
                if args.intent_file and args.origin != "human_intent":
                    raise ValueError("--intent-file requires --origin human_intent")
                payload, code = project_control_pack(
                    args.task,
                    args.episode,
                    origin=args.origin,
                    intent=read_process_intent_file(args.intent_file),
                )
            persist_dispatch_pack(payload)
            emit(payload)
            return code
        if args.command == "lease-record":
            emit(record_runtime_lease(args))
            return 0
        if args.command == "close-receipt-verify":
            receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
            result = verify_close_receipt(receipt)
            emit(result)
            return 0 if result["valid"] else 1
        if args.command == "close-receipt-record":
            result, code = record_close_receipt(Path(args.receipt))
            emit(result)
            return code
        payload, code = close_plan(args.topic, args.mode, args.ids)
        emit(payload)
        return code
    except (FileNotFoundError, ValueError) as exc:
        emit({"schema": "ndf-workflow-error/v1", "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
