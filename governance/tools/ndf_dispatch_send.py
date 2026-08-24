#!/usr/bin/env python3
"""Trusted pack → OpenClaw / Claude Code ACP dispatch.

Command Agent builds pack JSON, waits for human 「派发」, then runs this module:
  1. sends when safe_to_dispatch (or lease-only prepare)
  2. waits for worker stdout notify (ndf-dispatch-notify/v1)
  3. reads pack.completion_receipt_path from disk
  4. records disk completion → optional best-effort action-commit/finish →
     write last.json → snapshot

stdout completion JSON and transport acknowledgement MUST NOT count as
validated success. Episode/Replay/action closeout MUST NOT gate success
(ADR-META-004). Must not rely on Cursor afterShellExecution to auto-send.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[2]
DISPATCH_LAST = ROOT / "tmp" / "ndf-dispatch-last.json"
DEFAULT_TIMEOUT_SEC = 900
DEFAULT_OPENCLAW_PING_SEC = 60
DEFAULT_OPENCLAW_STALL_SEC = 900
DEFAULT_OPENCLAW_MAX_SEC = 14400
DEFAULT_ACP_PING_SEC = 60
DEFAULT_ACP_STALL_SEC = 900
DEFAULT_ACP_MAX_SEC = 14400
DEFAULT_ACP_CONTEXT_MAX_TOKENS = 800000
DEFAULT_ACP_COMPLETION_RESERVE = 32000
DEFAULT_ACP_CHARS_PER_TOKEN = 4.0
LEASE_STUB_SUMMARIES = frozenset()
LEASE_SUCCESS_SUMMARIES = frozenset(
    {
        "lease_only_no_implementation_start",
        "lease_recorded_no_implementation_start",
    }
)


def _is_lease_stub_summary(summary: str) -> bool:
    text = str(summary or "").strip()
    if text in LEASE_SUCCESS_SUMMARIES:
        return False
    return text in LEASE_STUB_SUMMARIES


def _verify_lease_only_outcome(
    pack: Mapping[str, Any],
    send_result: Mapping[str, Any],
) -> tuple[bool, list[str], str]:
    """Fail closed unless an active isolated lease row exists for this pack."""
    import ndf_workflow_status as workflow

    blockers: list[str] = []
    run_id = str(send_result.get("run_id") or "").strip()
    worktree = str(send_result.get("worktree") or "").strip()
    topic = str(pack.get("topic") or "").strip()
    episode_id = str(pack.get("episode_id") or "").strip()
    base_sha = str(pack.get("base_sha") or "").strip()
    summary = str(send_result.get("response_text") or "")

    if _is_lease_stub_summary(summary):
        blockers.append("lease_stub_summary")
    if not run_id:
        blockers.append("missing_lease_run_id")
    if not worktree:
        blockers.append("missing_lease_worktree")
    lease = workflow.topic_active_lease(topic) if topic else None
    if not lease:
        blockers.append("missing:active_runtime_lease")
    else:
        if run_id and str(lease.get("run_id") or "") != run_id:
            blockers.append("lease_run_id_mismatch")
        if worktree and str(lease.get("worktree") or "") != worktree:
            blockers.append("lease_worktree_mismatch")
        if episode_id and str(lease.get("episode_id") or "") != episode_id:
            blockers.append("lease_episode_mismatch")
        if base_sha and str(lease.get("base_sha") or "") != base_sha:
            blockers.append("lease_base_sha_mismatch")
        if str(lease.get("result") or "") != "active":
            blockers.append("lease_not_active")
    ok = not blockers
    out_summary = (
        summary if ok else ("lease_verification_failed:" + ",".join(blockers[:6]))
    )[:240]
    return ok, blockers, out_summary


def _verify_lease_only_artifact(pack: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Closeout gate: active lease row must exist on disk for this pack."""
    import ndf_workflow_status as workflow

    blockers: list[str] = []
    topic = str(pack.get("topic") or "").strip()
    episode_id = str(pack.get("episode_id") or "").strip()
    base_sha = str(pack.get("base_sha") or "").strip()
    lease = workflow.topic_active_lease(topic) if topic else None
    if not lease:
        blockers.append("missing:active_runtime_lease")
    else:
        if episode_id and str(lease.get("episode_id") or "") != episode_id:
            blockers.append("lease_episode_mismatch")
        if base_sha and str(lease.get("base_sha") or "") != base_sha:
            blockers.append("lease_base_sha_mismatch")
        if str(lease.get("result") or "") != "active":
            blockers.append("lease_not_active")
        if not str(lease.get("worktree") or "").strip():
            blockers.append("missing_lease_worktree")
        if not str(lease.get("run_id") or "").strip():
            blockers.append("missing_lease_run_id")
    return not blockers, blockers


def _write_last(payload: Mapping[str, Any]) -> None:
    DISPATCH_LAST.parent.mkdir(parents=True, exist_ok=True)
    DISPATCH_LAST.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _pack_sha(pack: Mapping[str, Any]) -> str:
    raw = pack.get("pack_sha") or pack.get("replay", {}).get("pack_sha")
    if isinstance(raw, str) and raw:
        return raw
    # Fallback identity for idempotency when pack was not yet bound.
    import hashlib

    blob = json.dumps(pack, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _safe_to_send(
    pack: Mapping[str, Any],
    *,
    skip_roles_check: bool = False,
) -> tuple[bool, list[str]]:
    blockers = [str(item) for item in (pack.get("blockers") or []) if str(item).strip()]
    preflight_blockers = _pack_preflight_blockers(
        pack, skip_roles_check=skip_roles_check
    )
    for item in preflight_blockers:
        if item not in blockers:
            blockers.append(item)
    if preflight_blockers:
        return False, blockers
    if pack.get("safe_to_dispatch") is True:
        return True, blockers
    # Control packs may expose safe_to_delegate + runtime separately.
    if (
        pack.get("safe_to_delegate") is True
        and pack.get("runtime_dispatch_ready") is not False
        and pack.get("provider") == "openclaw"
    ):
        return True, blockers
    return False, blockers or ["not_safe_to_dispatch"]


def _pack_preflight_blockers(
    pack: Mapping[str, Any],
    *,
    skip_roles_check: bool = False,
) -> list[str]:
    """Verify pack-side fields that MUST exist before transport (not Worker-minted)."""
    blockers: list[str] = []
    if not skip_roles_check:
        try:
            import ndf_role_binding as role_binding

            ok, role_blockers = role_binding.check_roles_for_dispatch(ROOT)
            if not ok:
                for item in role_blockers:
                    if item not in blockers:
                        blockers.append(item)
        except Exception:
            blockers.append("roles_unbound")
    truth = pack.get("workspace_truth")
    if isinstance(truth, Mapping) and truth.get("workspace_bound") is False:
        blockers.append("workspace_unbound")
    workspace = pack.get("workspace") if isinstance(pack.get("workspace"), Mapping) else {}
    if not str(pack.get("base_sha") or "").strip():
        blockers.append("missing_handshake:base_sha")
    if not str(workspace.get("repo_root") or "").strip():
        blockers.append("missing_handshake:repo_root")
    write_root = pack.get("allowed_write_root") or pack.get("allowed_write_roots")
    if isinstance(write_root, list):
        write_root = write_root[0] if write_root else ""
    if not str(write_root or "").strip():
        blockers.append("missing_handshake:allowed_write_root")
    # Capability readiness: fail closed unless lease-only prepare.
    if pack.get("execution_capabilities_ready") is False:
        for item in (pack.get("blockers") or []):
            text = str(item)
            if text.startswith("capability_missing:") or text == "waiting_human":
                if text not in blockers:
                    blockers.append(text)
        if "waiting_human" not in blockers and not any(
            str(b).startswith("capability_missing:") for b in blockers
        ):
            blockers.append("execution_capabilities_not_ready")
    provider = str(pack.get("provider") or "")
    if provider == "claude-code-acp":
        budget = pack.get("acp_context_budget")
        if not isinstance(budget, Mapping):
            budget = acp_context_budget_for_pack(pack)
        if budget.get("over_budget"):
            if "acp_context_over_budget" not in blockers:
                blockers.append("acp_context_over_budget")
    return blockers


def _command_flag(command: str, name: str) -> str:
    match = re.search(rf"--{re.escape(name)}(?:\s+|=)(\S+)", command or "")
    return match.group(1).strip() if match else ""


def correlate_started_action(
    pack: Mapping[str, Any],
    *,
    command: str = "",
    receipts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Match a started action receipt to a pack or pack CLI. Never 'latest started' alone."""
    import ndf_workflow_status as workflow

    if receipts is None:
        try:
            receipts = workflow.read_action_receipts()
        except Exception:
            receipts = []
    action_id = str(pack.get("action_id") or pack.get("attempt_id") or "").strip()
    catalog = str(pack.get("catalog_action_id") or "").strip()
    episode = _pack_episode_id(pack)
    task = str(pack.get("task") or "").strip()
    if command:
        action_id = action_id or _command_flag(command, "action-id")
        episode = episode or _command_flag(command, "episode")
        task = task or _command_flag(command, "task")
    # ActionSpec registry retired (ADR-META-004) — no task→catalog mapping.
    started = [
        receipt
        for receipt in receipts
        if receipt.get("status") == "started" and receipt.get("action_id")
    ]
    if action_id:
        match = next(
            (
                receipt
                for receipt in reversed(started)
                if str(receipt.get("action_id") or "") == action_id
            ),
            None,
        )
        if match:
            return dict(match)
    for receipt in reversed(started):
        rec_catalog = str(receipt.get("catalog_action_id") or "")
        rec_episode = str(
            receipt.get("episode_id")
            or (receipt.get("replay") or {}).get("episode_id")
            or ""
        )
        rec_task = str(receipt.get("operation") or receipt.get("task") or "")
        if catalog and rec_catalog and rec_catalog != catalog:
            continue
        if episode and rec_episode and rec_episode != episode:
            continue
        if catalog and rec_catalog == catalog:
            return dict(receipt)
        if task and rec_task in {task, catalog}:
            return dict(receipt)
    return None


def _finish_result(result: str, blockers: list[str]) -> str:
    if result == "succeeded":
        return "success"
    if result in {"cancelled", "blocked"} or "waiting_human" in blockers:
        return "cancelled"
    return "failed"


def _pack_episode_id(pack: Mapping[str, Any]) -> str:
    episode = pack.get("episode_id")
    if isinstance(episode, str) and episode.strip():
        return episode.strip()
    replay = pack.get("replay") if isinstance(pack.get("replay"), Mapping) else {}
    nested = replay.get("episode_id") if isinstance(replay, Mapping) else None
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return ""


def _acp_context_limits() -> tuple[int, int, float]:
    max_tokens = int(
        os.environ.get("NDF_ACP_CONTEXT_MAX_TOKENS") or DEFAULT_ACP_CONTEXT_MAX_TOKENS
    )
    reserve = int(
        os.environ.get("NDF_ACP_COMPLETION_RESERVE") or DEFAULT_ACP_COMPLETION_RESERVE
    )
    chars_per = float(os.environ.get("NDF_ACP_CHARS_PER_TOKEN") or DEFAULT_ACP_CHARS_PER_TOKEN)
    return max_tokens, reserve, chars_per


def _slim_pack_for_acp_worker(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Worker prompt JSON: SHA + read paths only; omit duplicate graph/manifest blobs."""
    slim: dict[str, Any] = {}
    for key in (
        "schema",
        "topic",
        "track",
        "task",
        "provider",
        "episode_id",
        "action_id",
        "attempt_id",
        "catalog_action_id",
        "base_sha",
        "manifest_sha",
        "plan_sha",
        "allowed_write_root",
        "completion_receipt_path",
        "approved_bundle_sha",
        "active_isolated_lease",
        "runtime_dispatch_ready",
        "safe_to_dispatch",
        "execution_capabilities_ready",
        "replay",
        "required_handshake",
        "forbidden",
        "allowed_sections",
        "mutable_sections",
        "next_action",
        "generated_at",
        "contract_preflight_passed",
        "static_preflight_passed",
    ):
        if key in pack:
            slim[key] = pack[key]
    workspace = pack.get("workspace")
    if isinstance(workspace, Mapping):
        slim["workspace"] = {
            k: workspace.get(k)
            for k in (
                "repo_root",
                "repo_name",
                "repo_head",
                "active_topic",
                "topic_dir",
                "topic_ndf_dir",
                "state_path",
            )
            if workspace.get(k)
        }
    cp = pack.get("context_plan")
    if isinstance(cp, Mapping):
        slim_reads: list[dict[str, Any]] = []
        for item in cp.get("ordered_reads") or []:
            if not isinstance(item, Mapping):
                continue
            slim_reads.append(
                {
                    k: item[k]
                    for k in ("order", "path", "phase", "reason", "sha256")
                    if k in item
                }
            )
        slim_cp: dict[str, Any] = {
            k: cp.get(k)
            for k in (
                "schema",
                "manifest_sha",
                "plan_sha",
                "topic",
                "task",
                "track",
                "role",
                "evidence_refs",
                "seed_ids",
            )
            if k in cp
        }
        slim_cp["ordered_reads"] = slim_reads
        baseline = cp.get("baseline")
        if isinstance(baseline, Mapping):
            slim_cp["baseline"] = {
                k: baseline.get(k)
                for k in (
                    "path",
                    "bind_sha",
                    "baseline_trunk_sha",
                    "baseline_status",
                    "bind",
                )
                if k in baseline
            }
        gates = cp.get("gates")
        if isinstance(gates, Mapping):
            slim_cp["gates"] = {
                k: gates.get(k)
                for k in (
                    "bundle_mode",
                    "expected_content_sha",
                    "slice_manifest_sha",
                )
                if k in gates
            }
        slim["context_plan"] = slim_cp
    cv = pack.get("context_verify")
    if isinstance(cv, Mapping):
        slim["context_verify"] = {
            k: cv.get(k) for k in ("valid", "plan_sha", "manifest_sha", "errors") if k in cv
        }
    slim["task_manifest_ref"] = {
        "manifest_sha": pack.get("manifest_sha"),
        "plan_sha": pack.get("plan_sha"),
    }
    return slim


def acp_context_budget_for_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate resume history + worker message vs model window (fail-closed before API 400)."""
    import ndf_workflow_status as workflow

    session_id = workflow.configured_acp_session_id()
    resume_chars = workflow.estimate_acp_resume_text_chars(session_id)
    worker_message = _build_worker_message(pack)
    message_chars = len(worker_message)
    max_tokens, reserve, chars_per = _acp_context_limits()
    estimated_tokens = int((resume_chars + message_chars) / chars_per) + reserve
    over_budget = estimated_tokens > max_tokens
    resume_path = (
        str(workflow.claude_acp_resume_path(session_id)) if session_id else None
    )
    return {
        "session_id": session_id,
        "resume_path": resume_path,
        "resume_chars": resume_chars,
        "worker_message_chars": message_chars,
        "estimated_tokens": estimated_tokens,
        "max_tokens": max_tokens,
        "completion_reserve": reserve,
        "chars_per_token": chars_per,
        "over_budget": over_budget,
        "fork_session": _acp_fork_session_enabled(),
    }


def _acp_fork_session_enabled() -> bool:
    raw = str(os.environ.get("NDF_ACP_FORK_SESSION") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _build_worker_message(pack: Mapping[str, Any]) -> str:
    provider = str(pack.get("provider") or "")
    topic = pack.get("topic") or ""
    task = pack.get("task") or ""
    episode = _pack_episode_id(pack)
    attempt = (
        pack.get("attempt_id")
        or pack.get("action_id")
        or (pack.get("replay") or {}).get("attempt_id")
        or ""
    )
    catalog = pack.get("catalog_action_id") or ""
    manifest = pack.get("manifest_sha") or ""
    plan = pack.get("plan_sha") or (pack.get("context_plan") or {}).get("plan_sha") or ""
    lines = [
        f"【NDF dispatch-send】provider={provider} task={task} topic={topic}",
        f"episode_id={episode}",
        f"attempt_id={attempt}",
        f"catalog_action_id={catalog}",
        f"action_id={pack.get('action_id') or ''}",
        f"manifest_sha={manifest}",
        f"context_plan_sha={plan}",
        f"allowed_write_root={pack.get('allowed_write_root') or pack.get('allowed_write_roots')}",
        f"completion_receipt_path={pack.get('completion_receipt_path') or ''}",
        "Follow the pack JSON binding.",
        "Write the full ndf-agent-completion/v1 to pack.completion_receipt_path "
        "(changed_files, changed_file_shas, evidence_paths, evidence_bundle_sha, "
        "reproduce_commands — not 'reproduce', git_commit, post_check_receipts).",
        "Stdout MUST be exactly one ndf-dispatch-notify/v1 object "
        "(result, receipt_path, topic, task, episode_id, attempt_id). "
        "MUST NOT treat a thin stdout ndf-agent-completion/v1 as the validated receipt.",
        "Commander (Cursor) is the only human capability surface. This pack is already "
        "capability-approved; run the bound measure/write. MUST NOT wait for a Claude Code "
        "Bash permission prompt. MUST NOT treat execution_binding_stale as a blocker. "
        "Host sudo is passwordless.",
    ]
    if provider == "claude-code-acp":
        lines.extend([
            "ACP steps (strict order):",
            "1) lease-record — isolated worktree under repo_root, same run_id/session_id/episode_id; "
            "lease-prep auto-symlinks gitignored local deps (hnswlib/output/ignored data/*) "
            "from the main repo and ensures build/ + results/ exist;",
            "2) implement only under allowed_write_root;",
            "3) run post_checks (ndf_poc_isolation.py, ndf_perf_baseline.py as required);",
            "4) write full disk receipt to completion_receipt_path;",
            "5) stdout ONLY ndf-dispatch-notify/v1.",
            "Disk receipt MUST include worktree, branch, run_id, session_id "
            "(session_id MUST equal this resume id).",
            "If COMMITS.md or ndf/evidence/* changed: changed_sections[] required "
            "(e.g. commits_append, evidence).",
            "post_check_receipts MUST be an array of objects with command, result, verifier "
            "(see tmp/cluster-gbdt-completion.json). MUST NOT use a summary object.",
            "evidence_bundle_sha MUST match evidence_paths hashed at completion worktree root.",
        ])
    slim = _slim_pack_for_acp_worker(pack)
    lines.extend([
        "BEGIN NDF_PACK_JSON",
        json.dumps(slim, ensure_ascii=False, sort_keys=True, default=str),
        "END NDF_PACK_JSON",
    ])
    return "\n".join(lines)


def _extract_schema_objects(text: str | None, schema: str) -> list[dict[str, Any]]:
    raw = text or ""
    candidates: list[dict[str, Any]] = []

    def _consider(blob: str) -> None:
        try:
            value = json.loads(blob)
        except json.JSONDecodeError:
            return
        if isinstance(value, dict) and value.get("schema") == schema:
            candidates.append(value)

    fence = "```"
    parts = raw.split(fence)
    for idx in range(1, len(parts), 2):
        body = parts[idx]
        if body.lstrip().startswith("json"):
            body = body.lstrip()[4:]
        _consider(body.strip())

    if not candidates:
        try:
            value = json.loads(raw.strip())
            if isinstance(value, dict) and value.get("schema") == schema:
                candidates.append(value)
        except json.JSONDecodeError:
            end = raw.rfind("}")
            if end >= 0:
                depth = 0
                start = None
                for idx in range(end, -1, -1):
                    ch = raw[idx]
                    if ch == "}":
                        depth += 1
                    elif ch == "{":
                        depth -= 1
                        if depth == 0:
                            start = idx
                            break
                if start is not None:
                    _consider(raw[start : end + 1])
    return candidates


def extract_agent_completion(text: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract ndf-agent-completion/v1 from text (tests / leftover stdout).

    dispatch-send MUST NOT use this for completion-record. Validated receipts
    come from disk via extract_dispatch_notify + load_disk_agent_completion.
    """
    candidates = _extract_schema_objects(text, "ndf-agent-completion/v1")
    errors: list[str] = []
    if not candidates:
        return None, ["missing_agent_completion"]
    if len(candidates) > 1:
        completion = candidates[-1]
        errors.append("multiple_agent_completions")
    else:
        completion = candidates[0]
    result = str(completion.get("result") or completion.get("status") or "").lower()
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        errors.append("invalid_agent_completion_result")
    return completion, errors


def extract_dispatch_notify(text: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract exactly one ndf-dispatch-notify/v1 from worker stdout."""
    candidates = _extract_schema_objects(text, "ndf-dispatch-notify/v1")
    errors: list[str] = []
    if not candidates:
        return None, ["missing_dispatch_notify"]
    if len(candidates) > 1:
        notify = candidates[-1]
        errors.append("multiple_dispatch_notifies")
    else:
        notify = candidates[0]
    for field in ("result", "receipt_path", "topic", "task", "episode_id", "attempt_id"):
        if field not in notify:
            errors.append(f"missing_notify:{field}")
        elif field != "topic" and not str(notify.get(field) or "").strip():
            errors.append(f"missing_notify:{field}")
        elif field == "topic" and notify.get("topic") is None:
            errors.append("missing_notify:topic")
    result = str(notify.get("result") or "").lower()
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        errors.append("invalid_dispatch_notify_result")
    return notify, errors


def _normalize_relpath(path: str) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    return text


def _is_safe_relpath(path: str) -> bool:
    text = _normalize_relpath(path)
    if not text or text.startswith("/") or text.startswith("~"):
        return False
    try:
        parts = Path(text).parts
    except (ValueError, OSError):
        return False
    if not parts or parts[0] in {"/", ".."}:
        return False
    return all(part not in {"..", ""} for part in parts)


def _first_write_root(pack: Mapping[str, Any]) -> str:
    write_root = pack.get("allowed_write_root") or pack.get("allowed_write_roots")
    if write_root is None:
        write_root = pack.get("allowed_write_paths")
    if isinstance(write_root, list):
        write_root = write_root[0] if write_root else ""
    return _normalize_relpath(str(write_root or ""))


def _under_write_root(path: str, write_root: str) -> bool:
    rel = _normalize_relpath(path).rstrip("/")
    root = _normalize_relpath(write_root).rstrip("/")
    if not root:
        return False
    return rel == root or rel.startswith(root + "/")


def _pack_repo_root(pack: Mapping[str, Any]) -> Path:
    workspace = pack.get("workspace") if isinstance(pack.get("workspace"), Mapping) else {}
    raw = str(workspace.get("repo_root") or ROOT)
    return Path(raw)


LEASE_HOSTED_IMPLEMENTATION_TASKS = frozenset(
    {
        "poc_implementation",
        "implement",
        "poc_measurement",
        "poc_prepare_baseline",
    }
)


def _pack_evidence_roots(pack: Mapping[str, Any]) -> list[Path]:
    """Repo roots where Worker may write completion_receipt_path (main + lease worktree)."""
    roots: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            return
        seen.add(key)
        roots.append(path)

    _add(_pack_repo_root(pack))
    topic = str(pack.get("topic") or "").strip()
    if topic:
        try:
            import ndf_workflow_status as workflow

            ok, lease = workflow.active_isolated_lease_for_topic(topic)
            if ok and lease:
                wt = str(lease.get("worktree") or "").strip()
                if wt:
                    _add(Path(wt))
        except Exception:
            pass
    return roots


def completion_receipt_path_for_pack(pack: Mapping[str, Any]) -> str:
    """Pack-pinned relative path for the disk ndf-agent-completion/v1."""
    declared = _normalize_relpath(str(pack.get("completion_receipt_path") or ""))
    if declared:
        return declared
    topic = str(pack.get("topic") or "").strip()
    task = str(pack.get("task") or "task").strip().replace(" ", "_") or "task"
    attempt = str(
        pack.get("attempt_id")
        or pack.get("action_id")
        or (pack.get("replay") or {}).get("attempt_id")
        or "attempt"
    ).strip() or "attempt"
    workspace = pack.get("workspace") if isinstance(pack.get("workspace"), Mapping) else {}
    topic_ndf = _normalize_relpath(str(workspace.get("topic_ndf_dir") or ""))
    if not topic_ndf and topic:
        topic_ndf = f"poc/{topic}/ndf"
    write_root = _first_write_root(pack)
    if topic_ndf:
        candidate = _normalize_relpath(f"{topic_ndf.rstrip('/')}/evidence/{task}-completion.json")
        if not write_root or _under_write_root(candidate, write_root):
            return candidate
    tmp_candidate = _normalize_relpath(f"tmp/ndf-completion/{attempt}.json")
    if write_root and _under_write_root(tmp_candidate, write_root):
        return tmp_candidate
    if write_root:
        return _normalize_relpath(
            f"{write_root.rstrip('/')}/.ndf-completion/{task}-{attempt}.json"
        )
    return tmp_candidate


def _resolve_disk_receipt_path(
    pack: Mapping[str, Any],
    receipt_path: str,
) -> tuple[Path | None, list[str]]:
    expected = completion_receipt_path_for_pack(pack)
    rel = _normalize_relpath(receipt_path)
    if not _is_safe_relpath(rel):
        return None, ["illegal_receipt_path"]
    if _normalize_relpath(expected) != rel:
        return None, ["receipt_path_mismatch"]
    write_root = _first_write_root(pack)
    if write_root and not _under_write_root(rel, write_root):
        return None, ["receipt_path_outside_write_root"]
    for root in _pack_evidence_roots(pack):
        full = root / rel
        try:
            full.resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            continue
        if full.is_file():
            return full, []
    return None, ["missing_disk_receipt"]


def _mirror_disk_receipt_to_repo_root(
    pack: Mapping[str, Any],
    source: Path,
    rel: str,
) -> None:
    """Copy a worktree-only completion receipt beside the main repo for projection."""
    repo = _pack_repo_root(pack)
    dest = repo / rel
    try:
        if source.resolve() == dest.resolve():
            return
    except OSError:
        return
    if dest.is_file():
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    except OSError:
        return


def _completion_identity_errors(
    pack: Mapping[str, Any],
    data: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    pack_topic = str(pack.get("topic") or "")
    data_topic = str(data.get("topic") or "")
    if pack_topic and data_topic and data_topic != pack_topic:
        errors.append("completion_topic_mismatch")
    pack_task = str(pack.get("task") or "")
    data_task = str(data.get("task") or "")
    if pack_task and data_task and pack_task != data_task:
        errors.append("completion_task_mismatch")
    pack_episode = _pack_episode_id(pack)
    data_episode = str(data.get("episode_id") or "")
    if pack_episode and data_episode and pack_episode != data_episode:
        errors.append("completion_episode_mismatch")
    pack_attempt = str(
        pack.get("attempt_id") or pack.get("action_id") or ""
    ).strip()
    data_attempt = str(data.get("attempt_id") or "").strip()
    if pack_attempt and data_attempt and pack_attempt != data_attempt:
        errors.append("completion_attempt_mismatch")
    pack_base = str(pack.get("base_sha") or "").strip()
    data_base = str(data.get("base_sha") or "").strip()
    if pack_base and data_base and pack_base != data_base:
        errors.append("completion_base_sha_mismatch")
    return errors


def load_disk_agent_completion(
    pack: Mapping[str, Any],
    notify: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read ndf-agent-completion/v1 from notify.receipt_path under the write root."""
    receipt_path = str(notify.get("receipt_path") or "")
    path, errors = _resolve_disk_receipt_path(pack, receipt_path)
    if path is None:
        return None, errors or ["illegal_receipt_path"]
    rel = _normalize_relpath(receipt_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ["invalid_disk_receipt_json"]
    if not isinstance(data, dict) or data.get("schema") != "ndf-agent-completion/v1":
        return None, ["invalid_disk_receipt_schema"]
    result = str(data.get("result") or data.get("status") or "").lower()
    extra: list[str] = list(errors)
    for item in _completion_identity_errors(pack, data):
        if item not in extra:
            extra.append(item)
    if result not in {"success", "succeeded", "failed", "cancelled", "blocked"}:
        extra.append("invalid_agent_completion_result")
    if not extra:
        _mirror_disk_receipt_to_repo_root(pack, path, rel)
    return data, extra


def _notify_identity_errors(pack: Mapping[str, Any], notify: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    pack_topic = str(pack.get("topic") or "")
    notify_topic = str(notify.get("topic") or "")
    if pack_topic != notify_topic:
        errors.append("notify_topic_mismatch")
    pack_task = str(pack.get("task") or "")
    notify_task = str(notify.get("task") or "")
    if pack_task and notify_task and pack_task != notify_task:
        errors.append("notify_task_mismatch")
    pack_episode = _pack_episode_id(pack)
    notify_episode = str(notify.get("episode_id") or "")
    if pack_episode and notify_episode and pack_episode != notify_episode:
        errors.append("notify_episode_mismatch")
    pack_attempt = str(
        pack.get("attempt_id") or pack.get("action_id") or ""
    ).strip()
    notify_attempt = str(notify.get("attempt_id") or "").strip()
    if pack_attempt and notify_attempt and pack_attempt != notify_attempt:
        errors.append("notify_attempt_mismatch")
    return errors


def _task_outcome_from_transport(
    send_result: Mapping[str, Any],
    *,
    pack: Mapping[str, Any],
    lease_only: bool,
) -> tuple[str, list[str], str, dict[str, Any] | None]:
    """Map transport notify + disk receipt → task result.

    stdout ndf-agent-completion/v1 is ignored. Returns
    (result, blockers, summary, completion_or_None).
    """
    transport_ok = bool(send_result.get("transport_ok") or send_result.get("ok"))
    text = send_result.get("response_text")
    if not transport_ok:
        err = str(send_result.get("error") or send_result.get("state") or "transport_failed")
        return "failed", [err], err, None
    if lease_only:
        ok, blockers, summary = _verify_lease_only_outcome(pack, send_result)
        if ok:
            return "succeeded", [], summary, None
        return "failed", blockers, summary, None
    notify, parse_errors = extract_dispatch_notify(
        text if isinstance(text, str) else None
    )
    if notify is None:
        blockers = parse_errors or ["missing_dispatch_notify"]
        return (
            "failed",
            blockers,
            "transport_acknowledged but no ndf-dispatch-notify/v1",
            None,
        )
    identity_errors = _notify_identity_errors(pack, notify)
    path_ok = not any(
        item.startswith("missing_notify:") or item == "illegal_receipt_path"
        for item in parse_errors
    )
    completion = None
    disk_errors: list[str] = []
    if path_ok and "missing_notify:receipt_path" not in parse_errors:
        completion, disk_errors = load_disk_agent_completion(pack, notify)
    all_errors = list(parse_errors)
    for item in identity_errors + disk_errors:
        if item not in all_errors:
            all_errors.append(item)
    if completion is None:
        blockers = all_errors or ["missing_disk_receipt"]
        return (
            "failed",
            blockers,
            "notify present but disk ndf-agent-completion/v1 unusable",
            None,
        )
    provider = str(pack.get("provider") or "")
    if provider == "claude-code-acp":
        resume_id = str(send_result.get("session_id") or "").strip()
        receipt_sid = str(completion.get("session_id") or "").strip()
        if resume_id and receipt_sid and resume_id != receipt_sid:
            all_errors.append("session_id_mismatch")
    notify_result = str(notify.get("result") or "").lower()
    result_raw = str(completion.get("result") or completion.get("status") or "").lower()
    if (
        notify_result
        and result_raw
        and notify_result not in {result_raw, "success" if result_raw == "succeeded" else result_raw}
        and not (
            {notify_result, result_raw} <= {"success", "succeeded"}
            or {notify_result, result_raw} <= {"failed", "cancelled", "blocked"}
        )
    ):
        all_errors.append("notify_result_mismatch")
    worker_blockers = [
        str(item) for item in (completion.get("blockers") or []) if str(item).strip()
    ]
    summary = str(
        completion.get("summary")
        or completion.get("result_summary")
        or notify.get("summary")
        or (text or "")[:240]
    )
    if result_raw in {"success", "succeeded"} and not worker_blockers and not all_errors:
        return "succeeded", [], summary[:800], completion
    blockers = list(worker_blockers)
    for item in all_errors:
        if item not in blockers:
            blockers.append(item)
    if result_raw not in {"success", "succeeded"} and "agent_completion_failed" not in blockers:
        blockers.insert(0, "agent_completion_failed")
    if not blockers:
        blockers = ["agent_completion_failed"]
    return "failed", blockers, summary[:800], completion


def _already_sent(pack_sha: str, request_id: str | None) -> dict[str, Any] | None:
    if not DISPATCH_LAST.is_file():
        return None
    try:
        prior = json.loads(DISPATCH_LAST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(prior, dict):
        return None
    if prior.get("pack_sha") == pack_sha and prior.get("state") in {
        "sent",
        "acknowledged",
        "running",
        "waiting_human",
        "succeeded",
        "failed",
        "delivery_unknown",
        "blocked",
    }:
        if request_id and prior.get("request_id") and prior.get("request_id") != request_id:
            return None
        send = prior.get("send")
        lease_hop = isinstance(send, Mapping) and send.get("lease_only")
        if prior.get("state") == "succeeded" and (
            _is_lease_stub_summary(str(prior.get("result_summary") or ""))
            or (lease_hop and not str(prior.get("run_id") or send.get("run_id") or "").strip())
        ):
            return None
        return {**prior, "idempotent": True}
    return None


_OPENCLAW_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_openclaw_uuid(value: str) -> bool:
    return bool(_OPENCLAW_UUID_RE.fullmatch(str(value or "").strip()))


def _openclaw_wait_budgets(
    timeout_sec: int | None = None,
) -> tuple[float, float, float]:
    """Return (ping_sec, stall_sec, max_sec) for OpenClaw heartbeat wait."""
    ping = float(
        os.environ.get("NDF_OPENCLAW_PING_SEC") or DEFAULT_OPENCLAW_PING_SEC
    )
    stall = float(
        os.environ.get("NDF_OPENCLAW_STALL_SEC") or DEFAULT_OPENCLAW_STALL_SEC
    )
    # Absolute ceiling: explicit MAX, else at least legacy timeout, else default max.
    legacy = float(timeout_sec or DEFAULT_TIMEOUT_SEC)
    max_sec = float(
        os.environ.get("NDF_OPENCLAW_MAX_SEC")
        or max(DEFAULT_OPENCLAW_MAX_SEC, legacy)
    )
    ping = max(5.0, ping)
    stall = max(ping, stall)
    max_sec = max(stall, max_sec)
    return ping, stall, max_sec


def _acp_wait_budgets(timeout_sec: int | None = None) -> tuple[float, float, float]:
    """Return (ping_sec, stall_sec, max_sec) for ACP heartbeat wait."""
    ping = float(os.environ.get("NDF_ACP_PING_SEC") or DEFAULT_ACP_PING_SEC)
    stall = float(os.environ.get("NDF_ACP_STALL_SEC") or DEFAULT_ACP_STALL_SEC)
    legacy = float(timeout_sec or DEFAULT_TIMEOUT_SEC)
    max_sec = float(
        os.environ.get("NDF_ACP_MAX_SEC") or max(DEFAULT_ACP_MAX_SEC, legacy)
    )
    ping = max(5.0, ping)
    stall = max(ping, stall)
    max_sec = max(stall, max_sec)
    return ping, stall, max_sec


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


def _openclaw_session_progress(
    session_key: str,
    *,
    executable: str | None = None,
) -> dict[str, Any] | None:
    """Read sessions store row for configured key; used as heartbeat progress."""
    key = str(session_key or "").strip()
    if not key:
        return None
    exe = executable or shutil.which("openclaw")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "sessions", "--json", "--all-agents", "--limit", "100"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    payload = _extract_json_object(proc.stdout or "")
    if not payload:
        return None
    for item in payload.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "") == key or str(item.get("sessionId") or "") == key:
            return {
                "key": item.get("key"),
                "sessionId": item.get("sessionId"),
                "updatedAt": item.get("updatedAt"),
                "totalTokens": item.get("totalTokens"),
                "abortedLastRun": item.get("abortedLastRun"),
                "model": item.get("model"),
            }
    return None


def _progress_signature(row: Mapping[str, Any] | None) -> tuple[Any, Any]:
    if not row:
        return (None, None)
    return (row.get("updatedAt"), row.get("totalTokens"))


def _disk_completion_present(pack: Mapping[str, Any]) -> bool:
    rel = str(pack.get("completion_receipt_path") or "").strip()
    if not rel:
        rel = completion_receipt_path_for_pack(pack)
    if not rel:
        return False
    for root in _pack_evidence_roots(pack):
        path = root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema") != "ndf-agent-completion/v1":
            continue
        if _completion_identity_errors(pack, data):
            continue
        return True
    return False


def _acp_resume_signature(session_id: str | None) -> tuple[Any, Any]:
    if not session_id:
        return (None, None)
    try:
        import ndf_workflow_status as workflow

        path = workflow.claude_acp_resume_path(session_id)
        if not path.is_file():
            return (None, None)
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except Exception:
        return (None, None)


def _write_heartbeat(
    *,
    pack_sha: str,
    request_id: str,
    provider: str,
    started_at: float,
    heartbeat: Mapping[str, Any],
    key: str,
    summary: str,
) -> None:
    prior: dict[str, Any] = {}
    if DISPATCH_LAST.is_file():
        try:
            loaded = json.loads(DISPATCH_LAST.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prior = loaded
        except json.JSONDecodeError:
            prior = {}
    payload = {
        **prior,
        "schema": "ndf-dispatch-send/v1",
        "state": "sent",
        "dispatch_state": "awaiting_result",
        "delegate_to": provider or prior.get("delegate_to") or "claude-code-acp",
        "pack_sha": pack_sha or prior.get("pack_sha"),
        "request_id": request_id or prior.get("request_id"),
        "sent": True,
        "started_at": started_at or prior.get("started_at"),
        "result_summary": summary,
        key: dict(heartbeat),
        "heartbeat_at": time.time(),
    }
    _write_last(payload)


def _effective_dispatch_provider(pack: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Resolve pack provider via ndf.workflow.yaml role adapters (CLI or fallback)."""
    import ndf_role_binding as role_binding

    declared = str(pack.get("provider") or "")
    resolved = role_binding.resolve_pack_provider(ROOT, pack)
    provider = str(resolved.get("provider") or "unsupported")
    if provider == "unsupported":
        return declared or "unsupported", resolved
    if declared in {"openclaw", "claude-code-acp"} and provider in {
        "openclaw",
        "claude-code-acp",
    }:
        return provider, resolved
    if provider in {"in-host", "dual-session", "custom"}:
        return provider, resolved
    return declared or provider, resolved


def _wait_spawn_provider_with_heartbeat(
    pack: Mapping[str, Any],
    *,
    provider: str,
    role: str,
    spawn_path: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    """Write spawn file and heartbeat-wait for disk completion (no transport ACK)."""
    ping_sec, stall_sec, max_sec = _acp_wait_budgets(timeout_sec)
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    started = time.time()
    hard_deadline = started + max_sec
    last_progress_at = started
    ping_count = 0
    last_ping_at = 0.0
    summary = (
        f"spawn 文件已写 {spawn_path.name}；等待磁盘 completion"
        if provider == "in-host"
        else f"dual-session spawn 已写 {spawn_path.name}；等待磁盘 completion"
    )
    _write_heartbeat(
        pack_sha=pack_sha,
        request_id=request_id,
        provider=provider,
        started_at=started,
        heartbeat={
            "spawn_path": str(spawn_path),
            "role": role,
            "pings": 0,
            "elapsed_sec": 0.0,
        },
        key="spawn_heartbeat",
        summary=summary,
    )
    while True:
        now = time.time()
        disk_done = _disk_completion_present(pack)
        if disk_done:
            receipt_rel = completion_receipt_path_for_pack(pack)
            notify = {
                "schema": "ndf-dispatch-notify/v1",
                "result": "success",
                "receipt_path": receipt_rel,
                "topic": pack.get("topic") or "",
                "task": pack.get("task") or "",
                "episode_id": _pack_episode_id(pack),
                "attempt_id": str(
                    pack.get("attempt_id") or pack.get("action_id") or ""
                ),
            }
            return {
                "ok": True,
                "transport_ok": True,
                "state": "transport_acknowledged",
                "response_text": json.dumps(notify, ensure_ascii=False),
                "spawn_path": str(spawn_path),
                "provider": provider,
                "spawn_heartbeat": {
                    "pings": ping_count,
                    "elapsed_sec": round(now - started, 1),
                    "disk_completion_present": True,
                },
            }
        if now - last_ping_at >= ping_sec:
            last_ping_at = now
            ping_count += 1
            heartbeat = {
                "pings": ping_count,
                "elapsed_sec": round(now - started, 1),
                "seconds_since_progress": round(now - last_progress_at, 1),
                "stall_sec": stall_sec,
                "max_sec": max_sec,
                "spawn_path": str(spawn_path),
                "role": role,
                "disk_completion_present": False,
            }
            _write_heartbeat(
                pack_sha=pack_sha,
                request_id=request_id,
                provider=provider,
                started_at=started,
                heartbeat=heartbeat,
                key="spawn_heartbeat",
                summary=summary,
            )
            if now - last_progress_at >= stall_sec:
                return {
                    "ok": False,
                    "transport_ok": False,
                    "state": "failed",
                    "error": f"{provider.replace('-', '_')}_stalled",
                    "detail": f"no disk completion for {stall_sec:.0f}s",
                    "response_text": None,
                    "spawn_path": str(spawn_path),
                    "spawn_heartbeat": heartbeat,
                }
        if now >= hard_deadline:
            return {
                "ok": False,
                "transport_ok": False,
                "state": "failed",
                "error": f"{provider.replace('-', '_')}_timeout",
                "detail": f"absolute max_sec={max_sec:.0f} exceeded",
                "response_text": None,
                "spawn_path": str(spawn_path),
            }
        time.sleep(min(ping_sec, 1.0))


def _send_spawn_provider(
    pack: Mapping[str, Any],
    *,
    provider: str,
    role_resolution: Mapping[str, Any],
    timeout_sec: int,
) -> dict[str, Any]:
    import ndf_role_binding as role_binding

    role = str(role_resolution.get("mapped_role") or role_resolution.get("role") or "implementation")
    pack_path = ROOT / "tmp" / "ndf-dispatch-last-pack.json"
    spawn_path = role_binding.write_spawn_file(
        ROOT,
        role,
        pack_path,
        provider=provider,
        completion_receipt_path=pack.get("completion_receipt_path"),
        write_roots=pack.get("allowed_write_root") or pack.get("allowed_write_roots"),
        topic=pack.get("topic"),
        task=pack.get("task"),
        episode_id=_pack_episode_id(pack),
        attempt_id=pack.get("attempt_id") or pack.get("action_id"),
        base_sha=pack.get("base_sha"),
        model=role_resolution.get("model"),
    )
    if provider == "custom":
        cmd = str(role_resolution.get("custom_command") or "").strip()
        if not cmd:
            return {
                "ok": False,
                "transport_ok": False,
                "state": "failed",
                "error": "custom_command_missing",
                "response_text": None,
            }
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=float(timeout_sec),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "ok": False,
                "transport_ok": False,
                "state": "failed",
                "error": "custom_command_failed",
                "detail": str(exc),
                "response_text": None,
            }
    return _wait_spawn_provider_with_heartbeat(
        pack,
        provider=provider,
        role=role,
        spawn_path=spawn_path,
        timeout_sec=timeout_sec,
    )


def _write_openclaw_heartbeat(
    *,
    pack_sha: str,
    request_id: str,
    provider: str,
    started_at: float,
    heartbeat: Mapping[str, Any],
) -> None:
    _write_heartbeat(
        pack_sha=pack_sha,
        request_id=request_id,
        provider=provider,
        started_at=started_at,
        heartbeat=heartbeat,
        key="openclaw_heartbeat",
        summary="已发出，心跳等待 OpenClaw",
    )


def _send_openclaw(
    pack: Mapping[str, Any],
    *,
    message: str,
    timeout_sec: int,
) -> dict[str, Any]:
    session_key = str(pack.get("session_key") or "").strip()
    resolved = str(pack.get("resolved_session_id") or "").strip()
    transport = str(pack.get("session_transport") or "").strip()
    if not transport and not resolved and session_key:
        try:
            import ndf_workflow_status as workflow

            resolution = workflow.resolve_openclaw_dispatch_session(session_key)
            resolved = str(resolution.get("resolved_session_id") or "").strip()
            transport = str(resolution.get("transport") or "").strip()
        except Exception:
            resolved = ""
            transport = ""
    if not transport:
        if resolved and _looks_like_openclaw_uuid(resolved):
            transport = "session_id"
        elif session_key and ":" in session_key and not _looks_like_openclaw_uuid(
            session_key
        ):
            transport = "session_key"
        elif session_key and _looks_like_openclaw_uuid(session_key):
            transport = "session_id"
            resolved = session_key
        else:
            transport = "session_key" if session_key else "session_id"
    override = os.environ.get("NDF_OPENCLAW_DISPATCH_CMD")
    executable = shutil.which("openclaw")
    if override:
        cmd = override.split()
        use_heartbeat = False
    elif not executable:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_cli_missing",
            "response_text": None,
        }
    elif transport == "session_id":
        session_id = resolved or session_key
        cmd = [executable, "agent", "--agent", "main", "--message", message]
        if session_id:
            cmd.extend(["--session-id", session_id])
        use_heartbeat = True
    else:
        import uuid as _uuid

        ping_sec, stall_sec, max_sec = _openclaw_wait_budgets(timeout_sec)
        timeout_ms = int(max_sec * 1000) + 60_000
        params = {
            "message": message,
            "agentId": "main",
            "sessionKey": session_key,
            "timeout": int(max_sec),
            "idempotencyKey": str(_uuid.uuid4()),
        }
        cmd = [
            executable,
            "gateway",
            "call",
            "agent",
            "--expect-final",
            "--json",
            "--timeout",
            str(timeout_ms),
            "--params",
            json.dumps(params, ensure_ascii=False),
        ]
        use_heartbeat = True

    if not use_heartbeat:
        # Test / override path: single blocking run with legacy timeout.
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=float(timeout_sec),
                env={**os.environ, "NDF_PACK_SHA": _pack_sha(pack)},
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "state": "delivery_unknown",
                "error": "openclaw_timeout",
                "detail": str(exc),
                "response_text": None,
            }
        except OSError as exc:
            return {
                "ok": False,
                "state": "delivery_unknown",
                "error": "openclaw_spawn_failed",
                "detail": str(exc),
                "response_text": None,
            }
        text = proc.stdout or ""
        if proc.returncode != 0:
            return {
                "ok": False,
                "transport_ok": False,
                "state": "failed",
                "error": "openclaw_nonzero_exit",
                "exit_code": proc.returncode,
                "response_text": text[-8000:],
            }
        return {
            "ok": True,
            "transport_ok": True,
            "state": "transport_acknowledged",
            "exit_code": 0,
            "response_text": text[-8000:],
        }

    return _wait_openclaw_with_heartbeat(
        pack,
        cmd=cmd,
        session_key=session_key,
        executable=executable,
        timeout_sec=timeout_sec,
    )


def _wait_openclaw_with_heartbeat(
    pack: Mapping[str, Any],
    *,
    cmd: list[str],
    session_key: str,
    executable: str | None,
    timeout_sec: int,
) -> dict[str, Any]:
    ping_sec, stall_sec, max_sec = _openclaw_wait_budgets(timeout_sec)
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    provider = str(pack.get("provider") or "openclaw")
    started = time.time()
    hard_deadline = started + max_sec
    last_progress_at = started
    last_sig = _progress_signature(
        _openclaw_session_progress(session_key, executable=executable)
    )
    ping_count = 0
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "NDF_PACK_SHA": pack_sha},
        )
    except OSError as exc:
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_spawn_failed",
            "detail": str(exc),
            "response_text": None,
        }

    chunks: list[str] = []
    assert proc.stdout is not None
    last_ping_at = 0.0
    try:
        while True:
            # Non-blocking read of available stdout.
            ready, _, _ = select.select([proc.stdout], [], [], min(ping_sec, 1.0))
            if ready:
                line = proc.stdout.readline()
                if line:
                    chunks.append(line)
            rc = proc.poll()
            now = time.time()
            if rc is not None:
                # Drain remainder.
                rest = proc.stdout.read() or ""
                if rest:
                    chunks.append(rest)
                text = "".join(chunks)
                if rc != 0:
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "openclaw_nonzero_exit",
                        "exit_code": rc,
                        "response_text": text[-8000:],
                        "openclaw_heartbeat": {
                            "pings": ping_count,
                            "elapsed_sec": round(now - started, 1),
                            "stall_sec": stall_sec,
                            "max_sec": max_sec,
                        },
                    }
                return {
                    "ok": True,
                    "transport_ok": True,
                    "state": "transport_acknowledged",
                    "exit_code": 0,
                    "response_text": text[-8000:],
                    "openclaw_heartbeat": {
                        "pings": ping_count,
                        "elapsed_sec": round(now - started, 1),
                        "stall_sec": stall_sec,
                        "max_sec": max_sec,
                        "finished": "gateway_final",
                    },
                }

            if now - last_ping_at >= ping_sec:
                last_ping_at = now
                ping_count += 1
                row = _openclaw_session_progress(session_key, executable=executable)
                sig = _progress_signature(row)
                progressed = sig != last_sig and sig != (None, None)
                disk_done = _disk_completion_present(pack)
                if progressed:
                    last_sig = sig
                    last_progress_at = now
                if disk_done:
                    last_progress_at = now
                heartbeat = {
                    "pings": ping_count,
                    "elapsed_sec": round(now - started, 1),
                    "seconds_since_progress": round(now - last_progress_at, 1),
                    "stall_sec": stall_sec,
                    "max_sec": max_sec,
                    "session": row,
                    "progressed": progressed,
                    "disk_completion_present": disk_done,
                }
                _write_openclaw_heartbeat(
                    pack_sha=pack_sha,
                    request_id=request_id,
                    provider=provider,
                    started_at=started,
                    heartbeat=heartbeat,
                )
                if now - last_progress_at >= stall_sec:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "openclaw_stalled",
                        "detail": (
                            f"no session/disk progress for {stall_sec:.0f}s "
                            f"(pings={ping_count})"
                        ),
                        "response_text": "".join(chunks)[-8000:],
                        "openclaw_heartbeat": heartbeat,
                    }
                if now >= hard_deadline:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "openclaw_timeout",
                        "detail": f"absolute max_sec={max_sec:.0f} exceeded",
                        "response_text": "".join(chunks)[-8000:],
                        "openclaw_heartbeat": heartbeat,
                    }
    except Exception as exc:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "ok": False,
            "state": "delivery_unknown",
            "error": "openclaw_heartbeat_error",
            "detail": str(exc),
            "response_text": "".join(chunks)[-8000:],
        }


def _acp_inherit_commander_permissions(pack: Mapping[str, Any]) -> bool:
    """True when the commander already approved capabilities / 派发."""
    if pack.get("execution_capabilities_ready") is True:
        return True
    caps = pack.get("capabilities")
    if isinstance(caps, Mapping) and caps.get("execution_capabilities_ready") is True:
        return True
    return pack.get("safe_to_dispatch") is True


def _acp_argv(
    pack: Mapping[str, Any],
    *,
    session_id: str,
    message: str,
    executable: str | None = None,
) -> list[str] | None:
    """Build ``claude --resume`` argv. None means the CLI is missing.

    Commander-approved packs inherit permission bypass so the ACP session is
    not a second human gate. ``NDF_ACP_DISPATCH_CMD`` replaces the argv as-is.
    """
    override = os.environ.get("NDF_ACP_DISPATCH_CMD")
    if override:
        return override.split()
    exe = executable if executable is not None else shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "--resume", session_id]
    if _acp_fork_session_enabled():
        cmd.append("--fork-session")
    if _acp_inherit_commander_permissions(pack):
        cmd.extend(
            [
                "--permission-mode",
                "bypassPermissions",
                "--dangerously-skip-permissions",
            ]
        )
    cmd.extend(["-p", message, "--output-format", "text"])
    return cmd


# Top-level paths that measurement/build need but are usually gitignored
# (or only partially tracked). Processed after `git worktree add`.
DEFAULT_LEASE_LOCAL_DEPS: tuple[str, ...] = (
    "hnswlib",
    "output",
    "data",
)


def _lease_local_dep_roots() -> tuple[str, ...]:
    raw = str(os.environ.get("NDF_LEASE_LOCAL_DEPS") or "").strip()
    if not raw:
        return DEFAULT_LEASE_LOCAL_DEPS
    parts = [item.strip().strip("/") for item in raw.split(",") if item.strip()]
    return tuple(parts) or DEFAULT_LEASE_LOCAL_DEPS


def _path_is_gitignored(repo_root: Path, rel: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "check-ignore", "-q", "--", rel],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _symlink_lease_path(src: Path, dst: Path) -> str | None:
    """Create absolute symlink dst → src. Returns rel note or None if skipped."""
    if not src.exists():
        return None
    if dst.is_symlink():
        try:
            if dst.resolve() == src.resolve():
                return None
        except OSError:
            pass
        dst.unlink()
    elif dst.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(src.resolve(), dst)
    return str(dst)


def link_lease_worktree_local_deps(
    repo_root: Path,
    worktree: Path,
    *,
    roots: tuple[str, ...] | None = None,
) -> list[str]:
    """Symlink gitignored (or missing) local deps from main repo into a lease worktree.

    - Top-level roots such as ``hnswlib`` / ``output``: symlink the whole tree when
      absent in the worktree.
    - Partially tracked roots such as ``data/``: keep tracked files, symlink only
      missing children that are gitignored on the main tree.
    - Always ensure empty writable ``build/`` and ``results/`` directories exist.
    """
    linked: list[str] = []
    repo_root = repo_root.resolve()
    worktree = worktree.resolve()
    for root_name in roots or _lease_local_dep_roots():
        src_root = repo_root / root_name
        dst_root = worktree / root_name
        if not src_root.exists():
            continue
        if not dst_root.exists() and not dst_root.is_symlink():
            # Whole-tree link when the worktree has no entry yet.
            if _path_is_gitignored(repo_root, root_name) or root_name in {
                "hnswlib",
                "output",
            }:
                note = _symlink_lease_path(src_root, dst_root)
                if note:
                    linked.append(f"{root_name}->{root_name}")
                continue
        if src_root.is_dir() and (dst_root.is_dir() or not dst_root.exists()):
            dst_root.mkdir(parents=True, exist_ok=True)
            for child in sorted(src_root.iterdir()):
                rel = f"{root_name}/{child.name}"
                if not _path_is_gitignored(repo_root, rel):
                    # Tracked (or unignored) — leave worktree git checkout alone.
                    continue
                dst_child = dst_root / child.name
                note = _symlink_lease_path(child, dst_child)
                if note:
                    linked.append(rel)
    for writable in ("build", "results"):
        target = worktree / writable
        if not target.exists() and not target.is_symlink():
            target.mkdir(parents=True, exist_ok=True)
            linked.append(f"{writable}/")
    return linked


def _prepare_isolated_lease(
    pack: Mapping[str, Any],
    *,
    session_id: str,
) -> dict[str, Any]:
    """Create an isolated worktree and record the runtime lease. No implementation."""
    from types import SimpleNamespace

    import ndf_workflow_status as workflow

    topic = str(pack.get("topic") or "").strip()
    episode_id = str(pack.get("episode_id") or "").strip()
    base_sha = str(pack.get("base_sha") or "").strip()
    allowed = str(pack.get("allowed_write_root") or "").strip()
    repo_root = Path(str((pack.get("workspace") or {}).get("repo_root") or ROOT))
    missing = [
        name
        for name, value in (
            ("topic", topic),
            ("episode_id", episode_id),
            ("base_sha", base_sha),
            ("allowed_write_root", allowed),
        )
        if not value
    ]
    if missing:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": "lease_pack_incomplete:" + ",".join(missing),
            "session_id": session_id,
            "response_text": None,
        }
    command_branch = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    branch = f"poc/{topic}-lease-{stamp}"
    worktree = repo_root / ".worktrees" / f"{topic}-lease-{stamp}"
    run_id = f"run-lease-prep-{topic}-{stamp}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    added = False
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "worktree",
                "add",
                "-q",
                "-b",
                branch,
                str(worktree),
                base_sha,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "transport_ok": False,
                "state": "failed",
                "error": f"worktree_add_failed:{(proc.stderr or proc.stdout or '').strip()[:240]}",
                "session_id": session_id,
                "response_text": None,
            }
        added = True
        after = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if after != command_branch:
            raise RuntimeError(f"command_branch_replaced:{after}")
        local_links = link_lease_worktree_local_deps(repo_root, worktree)
        args = SimpleNamespace(
            file=None,
            task=str(pack.get("task") or "poc_implementation"),
            topic=topic,
            mode=str(pack.get("track") or "poc"),
            step="start",
            run_id=run_id,
            session_id=session_id,
            base_sha=base_sha,
            worktree=str(worktree),
            branch=branch,
            allowed_write_root=allowed,
            result="active",
            command_text="runtime lease",
            started_at=None,
            evidence_path=[],
            blocker=[],
            episode=episode_id,
            action_id=str(pack.get("action_id") or pack.get("attempt_id") or "") or None,
        )
        lease = workflow.record_runtime_lease(args)
        return {
            "ok": True,
            "transport_ok": True,
            "state": "succeeded",
            "lease_only": True,
            "session_id": session_id,
            "run_id": run_id,
            "worktree": str(worktree),
            "branch": branch,
            "episode_id": episode_id,
            "action_id": args.action_id,
            "lease_result": lease.get("result"),
            "local_deps_linked": local_links,
            "response_text": "lease_recorded_no_implementation_start",
        }
    except Exception as exc:  # noqa: BLE001 — lease-prep must fail closed
        if added:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["git", "-C", str(repo_root), "branch", "-D", branch],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": f"lease_record_failed:{type(exc).__name__}:{exc}",
            "session_id": session_id,
            "response_text": None,
        }


def _send_acp(
    pack: Mapping[str, Any],
    *,
    message: str,
    timeout_sec: int,
    lease_only: bool,
) -> dict[str, Any]:
    """Resume the configured Claude Code ACP session with the pack.

    Exit 0 means transport acknowledgement only. Task success requires a
    disk ``ndf-agent-completion/v1`` at ``pack.completion_receipt_path``
    after stdout ``ndf-dispatch-notify/v1`` (see ``dispatch_send``).
    """
    import ndf_workflow_status as workflow

    session_id = workflow.configured_acp_session_id()
    if not session_id:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": "acp_session_unconfigured",
            "response_text": None,
        }
    if lease_only:
        return _prepare_isolated_lease(pack, session_id=session_id)
    cmd = _acp_argv(pack, session_id=session_id, message=message)
    if not cmd:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "delivery_unknown",
            "error": "claude_cli_missing",
            "response_text": None,
        }
    return _wait_acp_with_heartbeat(
        pack,
        cmd=cmd,
        session_id=session_id,
        timeout_sec=timeout_sec,
    )


def _wait_acp_with_heartbeat(
    pack: Mapping[str, Any],
    *,
    cmd: list[str],
    session_id: str,
    timeout_sec: int,
) -> dict[str, Any]:
    """Wait for ACP without a hard wall-clock subprocess timeout."""
    ping_sec, stall_sec, max_sec = _acp_wait_budgets(timeout_sec)
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    provider = str(pack.get("provider") or "claude-code-acp")
    started = time.time()
    hard_deadline = started + max_sec
    last_progress_at = started
    last_sig = _acp_resume_signature(session_id)
    ping_count = 0
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "NDF_PACK_SHA": pack_sha},
        )
    except OSError as exc:
        return {
            "ok": False,
            "transport_ok": False,
            "state": "delivery_unknown",
            "error": "acp_spawn_failed",
            "detail": str(exc),
            "response_text": None,
            "session_id": session_id,
        }

    chunks: list[str] = []
    assert proc.stdout is not None
    last_ping_at = 0.0
    try:
        while True:
            ready, _, _ = select.select([proc.stdout], [], [], min(ping_sec, 1.0))
            if ready:
                line = proc.stdout.readline()
                if line:
                    chunks.append(line)
                    last_progress_at = time.time()
            rc = proc.poll()
            now = time.time()
            text = "".join(chunks)
            if rc is not None:
                rest = proc.stdout.read() or ""
                if rest:
                    chunks.append(rest)
                text = "".join(chunks)
                heartbeat = {
                    "pings": ping_count,
                    "elapsed_sec": round(now - started, 1),
                    "stall_sec": stall_sec,
                    "max_sec": max_sec,
                    "session_id": session_id,
                }
                if rc != 0:
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "acp_nonzero_exit",
                        "exit_code": rc,
                        "session_id": session_id,
                        "response_text": text[-8000:],
                        "acp_heartbeat": heartbeat,
                    }
                return {
                    "ok": True,
                    "transport_ok": True,
                    "state": "transport_acknowledged",
                    "exit_code": 0,
                    "session_id": session_id,
                    "response_text": text[-8000:],
                    "acp_heartbeat": {**heartbeat, "finished": "cli_exit"},
                }

            if now - last_ping_at >= ping_sec:
                last_ping_at = now
                ping_count += 1
                sig = _acp_resume_signature(session_id)
                progressed = sig != last_sig and sig != (None, None)
                disk_done = _disk_completion_present(pack)
                notify, _ = extract_dispatch_notify(text if text else None)
                if progressed:
                    last_sig = sig
                    last_progress_at = now
                if disk_done or notify is not None:
                    last_progress_at = now
                heartbeat = {
                    "pings": ping_count,
                    "elapsed_sec": round(now - started, 1),
                    "seconds_since_progress": round(now - last_progress_at, 1),
                    "stall_sec": stall_sec,
                    "max_sec": max_sec,
                    "session_id": session_id,
                    "progressed": progressed,
                    "disk_completion_present": disk_done,
                    "notify_present": notify is not None,
                }
                _write_heartbeat(
                    pack_sha=pack_sha,
                    request_id=request_id,
                    provider=provider,
                    started_at=started,
                    heartbeat=heartbeat,
                    key="acp_heartbeat",
                    summary="已发出，心跳等待 Claude Code ACP",
                )
                if disk_done or notify is not None:
                    if rc is None:
                        try:
                            proc.wait(timeout=5)
                        except Exception:
                            proc.kill()
                            try:
                                proc.wait(timeout=5)
                            except Exception:
                                pass
                        rest = proc.stdout.read() or ""
                        if rest:
                            chunks.append(rest)
                    return {
                        "ok": True,
                        "transport_ok": True,
                        "state": "transport_acknowledged",
                        "session_id": session_id,
                        "response_text": "".join(chunks)[-8000:],
                        "acp_heartbeat": {**heartbeat, "finished": "disk_or_notify"},
                    }
                if now - last_progress_at >= stall_sec:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "acp_stalled",
                        "detail": (
                            f"no resume/disk/stdout progress for {stall_sec:.0f}s "
                            f"(pings={ping_count})"
                        ),
                        "session_id": session_id,
                        "response_text": "".join(chunks)[-8000:],
                        "acp_heartbeat": heartbeat,
                    }
                if now >= hard_deadline:
                    proc.kill()
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        pass
                    return {
                        "ok": False,
                        "transport_ok": False,
                        "state": "failed",
                        "error": "acp_max_exceeded",
                        "detail": f"absolute max_sec={max_sec:.0f} exceeded",
                        "session_id": session_id,
                        "response_text": "".join(chunks)[-8000:],
                        "acp_heartbeat": heartbeat,
                    }
    except Exception as exc:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "ok": False,
            "transport_ok": False,
            "state": "delivery_unknown",
            "error": "acp_heartbeat_error",
            "detail": str(exc),
            "session_id": session_id,
            "response_text": "".join(chunks)[-8000:] if chunks else None,
        }


def _closeout(
    *,
    catalog_action_id: str | None,
    action_id: str | None,
    result: str,
    blockers: list[str],
    result_summary: str,
    agent_completion: Mapping[str, Any] | None = None,
    pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist dispatch receipt; optional best-effort action closeout.

    Task success MUST NOT be inferred from transport alone. When a Worker
    ``ndf-agent-completion/v1`` is present it is written beside the thin
    dispatch receipt. Episode/Replay recording and action-finish are optional
    and MUST NOT flip a validated disk success to failed (ADR-META-004).
    """
    import ndf_workflow_status as workflow

    steps: dict[str, Any] = {}
    completion_path = ROOT / "tmp" / "ndf-dispatch-completion.json"
    completion = {
        "schema": "ndf-dispatch-completion/v1",
        "result": result,
        "blockers": blockers,
        "result_summary": result_summary,
        "finished_at": workflow.now_iso(),
        "transport_only": agent_completion is None and result != "succeeded",
    }
    if agent_completion is not None:
        completion["agent_completion"] = dict(agent_completion)
        agent_path = ROOT / "tmp" / "ndf-agent-completion.json"
        agent_path.write_text(
            json.dumps(dict(agent_completion), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        steps["agent_completion_path"] = "tmp/ndf-agent-completion.json"
        # Optional legacy Episode bind — never fail success for missing/failed Episode.
        episode_id = None
        if isinstance(pack, Mapping):
            episode_id = _pack_episode_id(pack)
        if episode_id and agent_completion is not None:
            try:
                verify, verify_code = workflow.record_agent_completion(
                    agent_path,
                    episode_id=str(episode_id),
                    role="claude-code"
                    if str((pack or {}).get("provider") or "").startswith("claude")
                    else "openclaw",
                    coverage="completion_only",
                )
                steps["completion_record"] = {
                    "exit_code": verify_code,
                    "valid": bool(verify.get("valid")),
                    "errors": verify.get("errors") or [],
                    "optional": True,
                }
            except Exception as exc:  # noqa: BLE001 — closeout must not crash dispatch
                steps["completion_record"] = {
                    "exit_code": 1,
                    "valid": False,
                    "optional": True,
                    "errors": [f"completion_record_exception:{type(exc).__name__}"],
                }
    completion_path.write_text(
        json.dumps(completion, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    steps["completion"] = {"path": "tmp/ndf-dispatch-completion.json", **completion}

    lease_only = False
    if isinstance(pack, Mapping):
        lease_only = str(pack.get("task") or "") in {"prepare_acp_lease"}
    if catalog_action_id == "prepare-acp-lease":
        lease_only = True
    if result == "succeeded" and lease_only:
        if _is_lease_stub_summary(result_summary):
            result = "failed"
            if "lease_stub_summary" not in blockers:
                blockers.append("lease_stub_summary")
            completion["result"] = result
            completion["blockers"] = blockers
        elif isinstance(pack, Mapping):
            ok, lease_blockers = _verify_lease_only_artifact(pack)
            if not ok:
                result = "failed"
                for item in lease_blockers:
                    if item not in blockers:
                        blockers.append(item)
                completion["result"] = result
                completion["blockers"] = blockers
    validated = (
        isinstance(agent_completion, Mapping)
        and agent_completion.get("schema") == "ndf-agent-completion/v1"
    )
    # Action commit/finish optional; ActionSpec retired — skip without failing success.
    if (
        result == "succeeded"
        and action_id
        and catalog_action_id
        and (lease_only or validated)
    ):
        steps["action_closeout"] = {
            "skipped": True,
            "reason": "action_spec_retired",
            "action_id": action_id,
            "catalog_action_id": catalog_action_id,
        }
    elif False and result == "succeeded" and action_id and catalog_action_id and (lease_only or validated):
        prompt_rel = "tmp/ndf-action-prompts/retired.md"
        commit_cmd = [
            "python3",
            "spec/meta/tools/ndf_workflow_status.py",
            "action-commit",
            "--action-id",
            action_id,
            "--catalog-action-id",
            catalog_action_id,
            "--prompt-file",
            prompt_rel,
            "--json",
        ]
        commit = subprocess.run(
            commit_cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        steps["action_commit"] = {
            "exit_code": commit.returncode,
            "stdout": (commit.stdout or "")[-4000:],
            "stderr": (commit.stderr or "")[-2000:],
            "optional": True,
        }
    elif action_id and catalog_action_id:
        steps["action_commit"] = {
            "skipped": True,
            "skip_reason": (
                "dispatch_not_succeeded"
                if result != "succeeded"
                else "missing_validated_completion"
            ),
            "result": result,
        }
    else:
        steps["action_commit"] = {
            "skipped": True,
            "skip_reason": "no_action_id",
            "optional": True,
        }
    if action_id:
        steps["action_finish"] = {
            "skipped": True,
            "skip_reason": "action_spec_retired",
            "action_id": action_id,
            "optional": True,
        }
    else:
        steps["action_finish"] = {
            "skipped": True,
            "skip_reason": "no_action_id",
            "optional": True,
        }
    steps["final_result"] = result
    return steps


def _action_has_started(action_id: str) -> bool:
    try:
        import ndf_workflow_status as workflow

        receipts = workflow.read_action_receipts()
    except Exception:
        return False
    return any(
        receipt.get("action_id") == action_id and receipt.get("status") == "started"
        for receipt in receipts
    )


def _run_snapshot(pack: Mapping[str, Any] | None) -> dict[str, Any]:
    """Commander snapshot retired — no-op (ADR-META-004)."""
    _ = pack
    return {
        "exit_code": 0,
        "skipped": True,
        "reason": "commander_retired",
        "stdout": "",
        "stderr": "",
    }


def dispatch_send(
    pack: Mapping[str, Any],
    *,
    catalog_action_id: str | None = None,
    action_id: str | None = None,
    timeout_sec: int | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    """Send a verified pack and close out the commander surface."""
    timeout = int(timeout_sec or os.environ.get("NDF_DISPATCH_TIMEOUT_SEC") or DEFAULT_TIMEOUT_SEC)
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    provider = str(pack.get("provider") or "")
    task = str(pack.get("task") or "")
    lease_only = task in {"prepare_acp_lease"} or (
        catalog_action_id == "prepare-acp-lease"
    )

    prior = _already_sent(pack_sha, request_id)
    if prior and prior.get("state") in {"succeeded", "failed", "blocked"}:
        return {**prior, "schema": "ndf-dispatch-send/v1"}, 0 if prior.get("state") == "succeeded" else 1

    ok_to_send, blockers = _safe_to_send(pack, skip_roles_check=lease_only)
    if not ok_to_send and not lease_only:
        payload = {
            "schema": "ndf-dispatch-send/v1",
            "state": "blocked",
            "dispatch_state": "blocked",
            "delegate_to": provider or "unknown",
            "pack_sha": pack_sha,
            "request_id": request_id,
            "blockers": blockers,
            "result_summary": "pack not safe_to_dispatch; not sent",
            "sent": False,
        }
        _write_last(payload)
        # waiting_human / blocked still MUST finish the started attempt and
        # snapshot --out so requireFresh CTAs are not stuck in refresh_in_progress.
        close_result = (
            "cancelled"
            if "waiting_human" in blockers or pack.get("dispatch_state") == "waiting_human"
            else "failed"
        )
        close = _closeout(
            catalog_action_id=catalog_action_id,
            action_id=action_id,
            result=close_result,
            blockers=blockers,
            result_summary=payload["result_summary"],
            pack=pack,
        )
        payload["closeout"] = close
        _write_last(payload)
        close["snapshot"] = _run_snapshot(pack)
        payload["closeout"] = close
        _write_last(payload)
        return payload, 1

    if dry_run:
        payload = {
            "schema": "ndf-dispatch-send/v1",
            "state": "sent",
            "dispatch_state": "awaiting_result",
            "delegate_to": provider,
            "pack_sha": pack_sha,
            "request_id": request_id,
            "blockers": [],
            "result_summary": "dry_run: would send",
            "sent": False,
            "dry_run": True,
        }
        _write_last(payload)
        return payload, 0

    working = dict(pack)
    if action_id:
        working.setdefault("action_id", action_id)
        working.setdefault("attempt_id", action_id)
    working["completion_receipt_path"] = completion_receipt_path_for_pack(working)
    pack = working

    message = _build_worker_message(pack)
    # Mark sent before waiting — commander may show awaiting_result.
    sent_receipt = {
        "schema": "ndf-dispatch-send/v1",
        "state": "sent",
        "dispatch_state": "awaiting_result",
        "delegate_to": provider,
        "pack_sha": pack_sha,
        "request_id": request_id,
        "blockers": [],
        "result_summary": "已发出，等待结果",
        "sent": True,
        "started_at": time.time(),
    }
    _write_last(sent_receipt)

    effective_provider, role_resolution = _effective_dispatch_provider(pack)
    if effective_provider != provider:
        provider = effective_provider
        sent_receipt["delegate_to"] = provider
        _write_last(sent_receipt)

    if provider == "openclaw":
        send_result = _send_openclaw(pack, message=message, timeout_sec=timeout)
        if (
            not send_result.get("transport_ok")
            and send_result.get("error") == "openclaw_cli_missing"
        ):
            fb = role_resolution.get("provider")
            if fb in {"in-host", "dual-session", "custom"}:
                send_result = _send_spawn_provider(
                    pack,
                    provider=str(fb),
                    role_resolution=role_resolution,
                    timeout_sec=timeout,
                )
    elif provider == "claude-code-acp":
        send_result = _send_acp(
            pack, message=message, timeout_sec=timeout, lease_only=lease_only
        )
        if (
            not send_result.get("transport_ok")
            and send_result.get("error") in {"claude_cli_missing", "acp_session_unconfigured"}
        ):
            fb = role_resolution.get("provider")
            if fb in {"in-host", "dual-session", "custom"}:
                send_result = _send_spawn_provider(
                    pack,
                    provider=str(fb),
                    role_resolution=role_resolution,
                    timeout_sec=timeout,
                )
    elif provider in {"in-host", "dual-session", "custom"}:
        send_result = _send_spawn_provider(
            pack,
            provider=provider,
            role_resolution=role_resolution,
            timeout_sec=timeout,
        )
    else:
        send_result = {
            "ok": False,
            "transport_ok": False,
            "state": "failed",
            "error": f"unknown_provider:{provider}",
            "response_text": None,
        }

    task_result, final_blockers, summary, agent_completion = _task_outcome_from_transport(
        send_result, pack=pack, lease_only=lease_only
    )
    # Prefer Worker-minted run_id; never invent one for a failed/missing receipt.
    run_id = None
    if isinstance(agent_completion, Mapping):
        run_id = agent_completion.get("run_id")
    if run_id is None and lease_only:
        run_id = send_result.get("run_id")
    payload = {
        **sent_receipt,
        "state": task_result,
        "dispatch_state": task_result,
        "result_summary": summary or task_result,
        "blockers": final_blockers,
        "transport_ok": bool(send_result.get("transport_ok") or send_result.get("ok")),
        "send": {k: v for k, v in send_result.items() if k != "response_text"},
        "response_excerpt": (send_result.get("response_text") or "")[:2000],
        "agent_completion": agent_completion,
        "finished_at": time.time(),
    }
    if run_id:
        payload["run_id"] = run_id
    if send_result.get("session_id"):
        payload["session_id"] = send_result.get("session_id")
    # Closeout: completion → optional action-commit → action-finish.
    # Write the final dispatch state before snapshot so the projection is not
    # stuck on awaiting_result.
    payload["closeout"] = _closeout(
        catalog_action_id=catalog_action_id,
        action_id=action_id,
        result=task_result,
        blockers=final_blockers,
        result_summary=payload["result_summary"],
        agent_completion=agent_completion,
        pack=pack,
    )
    # completion_record may have downgraded success → failed / projection_stale.
    close_final = (payload["closeout"] or {}).get("final_result")
    if close_final in {"succeeded", "failed", "succeeded_projection_stale"} and close_final != task_result:
        payload["state"] = close_final
        payload["dispatch_state"] = close_final
        payload["blockers"] = list(
            (payload["closeout"].get("completion") or {}).get("blockers") or final_blockers
        )
        task_result = close_final
    _write_last(payload)
    snap = _run_snapshot(pack)
    payload["closeout"]["snapshot"] = snap
    if task_result == "succeeded" and snap.get("exit_code") != 0:
        task_result = "succeeded_projection_stale"
        payload["state"] = task_result
        payload["dispatch_state"] = task_result
        payload["blockers"] = list(payload.get("blockers") or []) + [
            "projection_publish_failed"
        ]
        payload["closeout"]["final_result"] = task_result
    _write_last(payload)
    code = 0 if task_result == "succeeded" else 1
    return payload, code


def dispatch_probe(*, probed_by: str = "human_progress") -> tuple[dict[str, Any], int]:
    """Human 「进展如何」: probe ACP / OpenClaw liveness without a second send."""
    last: dict[str, Any] = {}
    if DISPATCH_LAST.is_file():
        try:
            loaded = json.loads(DISPATCH_LAST.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                last = loaded
        except json.JSONDecodeError:
            last = {}
    pack: dict[str, Any] | None = None
    pack_path = ROOT / "tmp" / "ndf-dispatch-last-pack.json"
    if pack_path.is_file():
        try:
            loaded = json.loads(pack_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                pack = loaded
        except json.JSONDecodeError:
            pack = None
    state = str(last.get("dispatch_state") or last.get("state") or "")
    in_flight = state in {"sent", "awaiting_result", "running"}

    import ndf_workflow_status as workflow

    session_id = workflow.configured_acp_session_id()
    acp_probe = workflow.probe_claude_acp_light(refresh=True)
    resume_sig = _acp_resume_signature(session_id)
    acp = {
        "session_id": session_id,
        "alive": bool(acp_probe.get("reachable")),
        "resume_available": bool(acp_probe.get("resume_available")),
        "error": acp_probe.get("error"),
        "resume_signature": list(resume_sig),
    }
    oc_key = ""
    try:
        oc_key = workflow.openclaw_session_key()
    except Exception:
        oc_key = ""
    oc_row = _openclaw_session_progress(oc_key) if oc_key else None
    openclaw = {
        "session_key": oc_key or None,
        "alive": bool(oc_row and oc_row.get("updatedAt")),
        "session": oc_row,
    }
    disk_done = _disk_completion_present(pack) if pack else False
    now = time.time()
    heartbeat = {
        "probed_by": probed_by,
        "probed_at": now,
        "in_flight": in_flight,
        "disk_completion_present": disk_done,
        "acp": acp,
        "openclaw": openclaw,
    }
    if in_flight and (acp["alive"] or openclaw["alive"] or disk_done):
        last["last_progress_at"] = now
        last["result_summary"] = "在途；人探活：worker 仍可达。回执齐后才会 closeout。"
    last["acp_heartbeat"] = {**(last.get("acp_heartbeat") or {}), **heartbeat}
    last["openclaw_heartbeat"] = {**(last.get("openclaw_heartbeat") or {}), **heartbeat}
    last["probed_by"] = probed_by
    last["heartbeat_at"] = now
    if not last.get("schema"):
        last["schema"] = "ndf-dispatch-send/v1"
    if not last.get("dispatch_state"):
        last["dispatch_state"] = state or "not_dispatched"
    _write_last(last)

    payload = {
        "schema": "ndf-dispatch-probe/v1",
        "dispatch_state": last.get("dispatch_state"),
        "in_flight": in_flight,
        "disk_completion_present": disk_done,
        "acp": acp,
        "openclaw": openclaw,
        "probed_by": probed_by,
        "hint": (
            "回执已齐：可 closeout"
            if disk_done
            else (
                "在途且可达；继续等待，不要对同一 pack 再 dispatch-send"
                if in_flight and (acp["alive"] or openclaw["alive"])
                else (
                    "尚未发出；「继续」才是 dispatch-send"
                    if not in_flight and state not in {"failed", "succeeded", "blocked"}
                    else "已终态；「进展如何」只报告，不对同一 pack 再 send"
                )
            )
        ),
    }
    code = 0 if (disk_done or acp["alive"] or openclaw["alive"] or not in_flight) else 1
    return payload, code


def dispatch_closeout_replay(
    pack: Mapping[str, Any],
    *,
    catalog_action_id: str | None = None,
    action_id: str | None = None,
    force: bool = False,
) -> tuple[dict[str, Any], int]:
    """Re-run transport outcome + closeout from tmp/ndf-dispatch-last.json without resending."""
    pack_sha = _pack_sha(pack)
    request_id = str(pack.get("request_id") or f"req-{pack_sha[:16]}")
    prior: dict[str, Any] = {}
    if DISPATCH_LAST.is_file():
        try:
            loaded = json.loads(DISPATCH_LAST.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prior = loaded
        except json.JSONDecodeError:
            prior = {}
    if (
        not force
        and prior.get("pack_sha") == pack_sha
        and prior.get("state") == "succeeded"
    ):
        return {**prior, "schema": "ndf-dispatch-send/v1", "replay": True}, 0
    send = prior.get("send") if isinstance(prior.get("send"), Mapping) else {}
    send_result: dict[str, Any] = {
        "transport_ok": bool(
            prior.get("transport_ok")
            or send.get("transport_ok")
            or send.get("ok")
        ),
        "ok": bool(send.get("ok") or prior.get("transport_ok")),
        "state": str(send.get("state") or prior.get("state") or "transport_acknowledged"),
        "session_id": str(
            prior.get("session_id") or send.get("session_id") or ""
        ).strip()
        or None,
        "response_text": str(
            prior.get("response_excerpt")
            or send.get("response_text")
            or ""
        ),
    }
    task = str(pack.get("task") or "")
    lease_only = task in {"prepare_acp_lease"} or catalog_action_id == "prepare-acp-lease"
    working = dict(pack)
    if action_id:
        working.setdefault("action_id", action_id)
        working.setdefault("attempt_id", action_id)
    working["completion_receipt_path"] = completion_receipt_path_for_pack(working)
    pack = working
    task_result, blockers, summary, agent_completion = _task_outcome_from_transport(
        send_result, pack=pack, lease_only=lease_only
    )
    close = _closeout(
        catalog_action_id=catalog_action_id,
        action_id=action_id or str(pack.get("action_id") or ""),
        result=task_result,
        blockers=blockers,
        result_summary=summary,
        agent_completion=agent_completion,
        pack=pack,
    )
    final_result = str(close.get("final_result") or task_result)
    close["snapshot"] = _run_snapshot(pack)
    payload = {
        "schema": "ndf-dispatch-send/v1",
        "state": final_result,
        "dispatch_state": final_result,
        "delegate_to": str(pack.get("provider") or ""),
        "pack_sha": pack_sha,
        "request_id": request_id,
        "blockers": blockers,
        "result_summary": summary,
        "sent": bool(prior.get("sent")),
        "transport_ok": send_result.get("transport_ok"),
        "send": send,
        "session_id": send_result.get("session_id"),
        "response_excerpt": send_result.get("response_text"),
        "agent_completion": agent_completion,
        "closeout": close,
        "replay": True,
        "finished_at": time.time(),
    }
    _write_last(payload)
    code = 0 if final_result == "succeeded" else 1
    return payload, code


def load_pack_from_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pack file must be a JSON object")
    return data


def extract_pack_from_shell_output(stdout: str) -> dict[str, Any] | None:
    """Parse the last JSON object from pack CLI stdout."""
    text = (stdout or "").strip()
    if not text:
        return None
    # Prefer whole stdout as JSON.
    try:
        value = json.loads(text)
        if isinstance(value, dict) and (
            value.get("schema")
            or value.get("safe_to_dispatch") is not None
            or value.get("provider")
        ):
            return value
    except json.JSONDecodeError:
        pass
    # Scan for the last {...} block.
    end = text.rfind("}")
    if end < 0:
        return None
    depth = 0
    start = None
    for idx in range(end, -1, -1):
        ch = text[idx]
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                start = idx
                break
    if start is None:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
