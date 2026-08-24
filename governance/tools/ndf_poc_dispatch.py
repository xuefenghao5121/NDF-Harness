#!/usr/bin/env python3
"""Text-first POC dispatch safety kernel (ADR-META-003 / ADR-META-004).

Hard gates only: identity, human bundle license, write-root + isolation,
single write run, context verify, ACP budget, disk completion identity.
No Commander / Episode / ActionSpec / projection requirements on the hot path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

POC_DISPATCH_SOFT_REASONS = frozenset(
    {
        "bindcheck_failed",
        "product_graphcheck_failed",
        "meta_graphcheck_failed",
        "spec_health_stale",
        "runtime_unavailable",
        "runtime_not_probed",
        "missing_active_isolated_lease",
        "lease_stale_vs_head",
        "topic_active_lease",
        "perf_check_failed",
        "baseline_stale",
        "missing_baseline_workspace",
    }
)
POC_DISPATCH_INTENTS = frozenset({"implement", "measure"})


def _workflow():
    """Lazy import to avoid circular load with ndf_workflow_status re-exports."""
    import ndf_workflow_status as workflow

    return workflow


def _poc_dispatch_task(intent: str) -> str:
    if intent == "measure":
        return "poc_measurement"
    return "poc_implementation"


def _concurrent_write_run_blocker(topic: str) -> str | None:
    """Block when another active write lease exists on a different HEAD."""
    wf = _workflow()
    head = wf.git_head()
    foreign = []
    for lease in wf.active_runtime_leases():
        if lease.get("topic") != topic:
            continue
        if str(lease.get("result") or "") != "active":
            continue
        if not str(lease.get("run_id") or "").strip():
            continue
        lease_head = str(lease.get("base_sha") or lease.get("repo_head") or "")
        if lease_head and lease_head != head:
            foreign.append(lease)
    if foreign:
        return "concurrent_write_run"
    return None


def poc_dispatch_hard_blockers(
    *,
    topic: str,
    view: Mapping[str, Any],
    truth: Mapping[str, Any],
    context_valid: bool,
    isolation_passed: bool,
    license_info: Mapping[str, Any],
) -> list[str]:
    """Hard blockers for text-first poc-dispatch (ADR-META-004)."""
    active = view.get("lifecycle") in {"exploring", "blocked", "closing"}
    blockers: list[str] = []
    if not active:
        blockers.append("topic_lifecycle_closed")
    if not license_info.get("ok"):
        blockers.append(
            f"missing_human_dispatch:{license_info.get('state') or 'missing'}"
        )
    if not isolation_passed:
        blockers.append("isolation_check_failed")
    if not truth.get("workspace_bound"):
        blockers.append("workspace_unbound")
    if not context_valid:
        blockers.append("context_verify_failed")
    write_root = f"poc/{topic}/"
    if not write_root.startswith("poc/") or ".." in write_root:
        blockers.append("forbidden_write_root")
    concurrent = _concurrent_write_run_blocker(topic)
    if concurrent:
        blockers.append(concurrent)
    return blockers


def ensure_inline_isolated_lease(
    pack: Mapping[str, Any],
) -> dict[str, Any]:
    """Create or reuse an isolated lease; never a separate human hop."""
    import ndf_dispatch_send as dispatch

    wf = _workflow()
    topic = str(pack.get("topic") or "")
    ok, lease = wf.active_isolated_lease_for_topic(topic)
    if ok and lease:
        return {
            "ok": True,
            "reused": True,
            "lease": lease,
            "run_id": lease.get("run_id"),
            "worktree": lease.get("worktree"),
            "branch": lease.get("branch"),
            "session_id": lease.get("session_id"),
        }
    session_id = (
        str(lease.get("session_id") if lease else "")
        or os.environ.get("NDF_ACP_SESSION_ID")
        or "poc-dispatch-inline"
    )
    result = dispatch._prepare_isolated_lease(pack, session_id=session_id)
    if not result.get("ok"):
        return {
            "ok": False,
            "reused": False,
            "error": result.get("error") or "lease_prepare_failed",
            "lease_result": result,
        }
    return {
        "ok": True,
        "reused": False,
        "lease_result": result,
        "run_id": result.get("run_id"),
        "worktree": result.get("worktree"),
        "branch": result.get("branch"),
        "session_id": result.get("session_id"),
    }


def validate_poc_completion_minimal(
    *,
    pack: Mapping[str, Any],
    completion: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Identity-only completion check; ignore Episode/Replay completeness."""
    errors: list[str] = []
    if not isinstance(completion, Mapping):
        return {"ok": False, "errors": ["missing_disk_completion"], "soft_warnings": []}
    if completion.get("schema") != "ndf-agent-completion/v1":
        errors.append("bad_completion_schema")
    if str(completion.get("topic") or "") != str(pack.get("topic") or ""):
        errors.append("completion_topic_mismatch")
    pack_task = str(pack.get("task") or "")
    comp_task = str(completion.get("task") or "")
    if pack_task and comp_task and pack_task != comp_task:
        errors.append("completion_task_mismatch")
    pack_run = str(pack.get("run_id") or "")
    comp_run = str(completion.get("run_id") or "")
    if pack_run and comp_run and pack_run != comp_run:
        errors.append("completion_run_mismatch")
    result = str(completion.get("result") or "")
    if result not in {"success", "succeeded"}:
        errors.append(f"completion_result:{result or 'missing'}")
    soft: list[str] = []
    for field in ("episode_id", "attempt_id", "action_id", "projection_sha"):
        if not completion.get(field):
            soft.append(f"optional_missing:{field}")
    return {"ok": not errors, "errors": errors, "soft_warnings": soft}


def poc_dispatch(
    topic: str,
    *,
    intent: str = "implement",
    send: bool = False,
    episode_id: str | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], int]:
    """Text-first single-entry POC dispatch (ADR-META-004).

    Hard gates only. Inline lease. Soft-audit reasons become warnings.
    Does not require Episode, ActionSpec, or projection freshness.
    """
    import ndf_gate_slices

    wf = _workflow()
    if intent not in POC_DISPATCH_INTENTS:
        raise ValueError(f"unknown poc-dispatch intent: {intent}")
    topic_dir = wf.POC / topic
    if not (topic_dir / "ndf" / "TOPIC.md").is_file():
        raise FileNotFoundError(f"unknown topic: {topic}")

    # Do not force ensure_spec_health — meta graph / stale health are soft.
    view = wf.topic_view(topic_dir, mode="full")
    task = _poc_dispatch_task(intent)
    # Recompile context for the concrete task (measure vs implement).
    context = wf.context_binding(
        topic=topic,
        role="claude-code",
        task=task,
        track="poc",
    )
    context_valid = bool(context["context_verify"].get("valid"))
    truth = wf.workspace_truth_view(topic)
    isolation_passed = view["health"]["checks"]["isolation"].get("exit_code") == 0
    license_info = wf.implementation_license(view["gates"])
    hard = poc_dispatch_hard_blockers(
        topic=topic,
        view=view,
        truth=truth,
        context_valid=context_valid,
        isolation_passed=isolation_passed,
        license_info=license_info,
    )
    try:
        import ndf_role_binding as role_binding

        ok_roles, role_blockers = role_binding.check_roles_for_dispatch(wf.ROOT)
        if not ok_roles:
            hard.extend(item for item in role_blockers if item not in hard)
    except Exception:
        if "roles_unbound" not in hard:
            hard.append("roles_unbound")
    soft_warnings = [
        reason
        for reason in (view["delegation"].get("dispatch_blockers") or [])
        if reason in POC_DISPATCH_SOFT_REASONS
    ]
    bundles = wf.poc_gate_bundle_specs(topic_dir)
    gate_key = license_info.get("source") or "implementation_approval"
    # Prefer the gate that actually failed license when explaining drift.
    if not license_info.get("ok"):
        for candidate in ("bundle_dispatch", "implementation_approval"):
            g = (view.get("gates") or {}).get(candidate) or {}
            if g.get("state") == "invalidated":
                gate_key = candidate
                break
        else:
            gate_key = "bundle_dispatch"
    gate_bundle = bundles.get(gate_key) or bundles["implementation_approval"]
    gate_drift: dict[str, Any] | None = None
    if any(str(b).startswith("missing_human_dispatch") for b in hard):
        gate_state = (view.get("gates") or {}).get(gate_key) or {}
        approved = gate_state.get("approved_content_sha") or license_info.get(
            "approved_content_sha"
        )
        if gate_state.get("state") == "invalidated" or (
            approved
            and gate_bundle.get("expected_content_sha")
            and approved != gate_bundle.get("expected_content_sha")
        ):
            gate_drift = ndf_gate_slices.explain_gate_drift(
                topic_dir,
                gate_key,
                approved_content_sha=approved,
                expected_content_sha=gate_bundle.get("expected_content_sha"),
                root=wf.ROOT,
                write_tmp_report=True,
            )
    elif license_info.get("ok") and license_info.get("approved_content_sha"):
        # Backfill baseline while aligned so the next amend can produce slice diffs.
        ndf_gate_slices.persist_gate_slice_snapshot(
            topic_dir,
            str(license_info.get("source") or gate_key),
            approved_content_sha=str(license_info["approved_content_sha"]),
            root=wf.ROOT,
        )
    files = []
    for name in wf.POC_FILES:
        path = topic_dir / "ndf" / name
        if path.is_file():
            files.append({"path": wf.rel(path), "sha256": wf.file_sha(path)})

    hard_ok = not hard
    payload: dict[str, Any] = {
        "schema": "ndf-workflow-pack/v2",
        "compatibility": {
            "legacy_schema": "ndf-workflow-pack/v1",
            "path": "poc-dispatch",
            "adr": "ADR-META-004",
        },
        "generated_at": wf.now_iso(),
        "topic": view["topic_id"],
        "track": "poc",
        "task": task,
        "intent": intent,
        "provider": "claude-code-acp",
        "base_sha": wf.git_head(),
        "workspace": wf.workspace_binding(topic),
        "workspace_truth": truth,
        "allowed_write_root": f"poc/{topic}/",
        "allowed_sections": (
            (context.get("context_plan") or {})
            .get("privileges", {})
            .get("allowed_sections", [])
        ),
        "mutable_sections": list(ndf_gate_slices.MUTABLE_SECTIONS),
        "forbidden": ["src/", "include/", "tests/", "spec/meta/", "stable SLA"],
        "read_order": files,
        "gate_receipt": license_info.get("gate"),
        "implementation_license": license_info,
        "approved_bundle_sha": gate_bundle.get("expected_content_sha"),
        "gate_bundle": gate_bundle,
        "gate_drift": gate_drift,
        "gate_drift_markdown": (
            ndf_gate_slices.format_gate_drift_markdown(gate_drift)
            if gate_drift
            else None
        ),
        "spaces": view["spaces"],
        "preflight": {
            "mode": "poc_dispatch_hard",
            "isolation": view["health"]["checks"]["isolation"],
            "hard_blockers": hard,
            "soft_warnings": soft_warnings,
        },
        "context_plan": context.get("context_plan"),
        "context_verify": context.get("context_verify"),
        "task_manifest": context.get("task_manifest"),
        "manifest_sha": context.get("manifest_sha"),
        "plan_sha": context.get("plan_sha"),
        "static_preflight_passed": hard_ok,
        "poc_dispatch_hard_passed": hard_ok,
        "contract_preflight_passed": bool(license_info.get("ok")),
        "active_isolated_lease": False,
        "runtime_dispatch_ready": True,
        "next_action": "poc_dispatch",
        "safe_to_delegate": hard_ok,
        "safe_to_dispatch": hard_ok,
        "blockers": list(hard),
        "soft_warnings": soft_warnings,
        "required_handshake": [
            "run_id",
            "session_id",
            "base_sha",
            "repo_root",
            "worktree",
            "allowed_write_root",
        ],
        "text_first": True,
    }
    payload = wf._with_completion_receipt_path(payload)
    wf.apply_acp_context_budget_to_pack(payload)
    if "acp_context_over_budget" in (payload.get("blockers") or []):
        hard.append("acp_context_over_budget")
        payload["blockers"] = list(dict.fromkeys([*hard, *(payload.get("blockers") or [])]))
        payload["safe_to_dispatch"] = False
        payload["safe_to_delegate"] = False
        payload["poc_dispatch_hard_passed"] = False
        hard_ok = False

    lease_info: dict[str, Any] | None = None
    if hard_ok:
        # Optional Episode bind only; never require Replay DAG (ADR-META-004).
        payload = wf.bind_pack_to_episode(
            payload, episode_id=episode_id, require_episode=False
        )
        lease_info = ensure_inline_isolated_lease(payload)
        if not lease_info.get("ok"):
            hard.append("inline_lease_failed")
            soft_detail = lease_info.get("error") or "lease_prepare_failed"
            payload["blockers"] = [*hard]
            payload["lease_error"] = soft_detail
            payload["safe_to_dispatch"] = False
            payload["safe_to_delegate"] = False
            payload["poc_dispatch_hard_passed"] = False
            hard_ok = False
        else:
            payload["active_isolated_lease"] = True
            payload["inline_lease"] = {
                "reused": lease_info.get("reused"),
                "run_id": lease_info.get("run_id"),
                "worktree": lease_info.get("worktree"),
                "branch": lease_info.get("branch"),
                "session_id": lease_info.get("session_id"),
            }
            if lease_info.get("run_id"):
                payload["run_id"] = lease_info["run_id"]
            if lease_info.get("session_id"):
                payload["session_id"] = lease_info["session_id"]
            # Refresh completion path after run_id known.
            payload = wf._with_completion_receipt_path(payload)
    else:
        payload = wf.bind_pack_to_episode(
            payload, episode_id=episode_id, require_episode=False
        )

    wf.persist_dispatch_pack(payload)
    result: dict[str, Any] = {
        "schema": "ndf-poc-dispatch/v1",
        "ok": hard_ok,
        "topic": topic,
        "intent": intent,
        "task": task,
        "pack": payload,
        "hard_blockers": payload.get("blockers") or [],
        "soft_warnings": soft_warnings,
        "implementation_license": license_info,
        "inline_lease": lease_info,
        "sent": False,
        "dispatch": None,
        "completion_validation": None,
    }
    if not hard_ok:
        return result, 1
    if not send:
        return result, 0

    import ndf_dispatch_send as dispatch

    # No ActionSpec / catalog dependency on the text-first kernel path.
    dispatch_payload, code = dispatch.dispatch_send(
        payload,
        catalog_action_id=None,
        action_id=None,
        dry_run=dry_run,
    )
    result["sent"] = True
    result["dispatch"] = dispatch_payload
    # Prefer disk completion when present; do not fail on Episode soft fields.
    completion = None
    receipt_path = payload.get("completion_receipt_path")
    if receipt_path:
        path = Path(str(receipt_path))
        if not path.is_absolute():
            path = wf.ROOT / path
        if path.is_file():
            try:
                completion = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                completion = None
    if completion is None and isinstance(dispatch_payload, Mapping):
        maybe = dispatch_payload.get("completion") or dispatch_payload.get(
            "validated_completion"
        )
        if isinstance(maybe, Mapping):
            completion = maybe
    validation = validate_poc_completion_minimal(pack=payload, completion=completion)
    result["completion_validation"] = validation
    # Transport failure is hard; soft Episode gaps are warnings only.
    if code != 0 and not dry_run:
        result["ok"] = False
        return result, code
    if (
        not dry_run
        and dispatch_payload.get("state") in {"succeeded", "success"}
        and completion is not None
        and not validation["ok"]
    ):
        # Real work finished but identity mismatch → hard fail.
        result["ok"] = False
        result["hard_blockers"] = [
            *result["hard_blockers"],
            *validation["errors"],
        ]
        return result, 1
    if validation.get("soft_warnings"):
        result["soft_warnings"] = [
            *result["soft_warnings"],
            *validation["soft_warnings"],
        ]
    result["ok"] = True
    return result, 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Text-first POC dispatch safety kernel (ADR-META-003 / ADR-META-004)."
    )
    parser.add_argument("--topic", help="POC topic id (required unless --help)")
    parser.add_argument(
        "--intent",
        choices=sorted(POC_DISPATCH_INTENTS),
        default="implement",
        help="dispatch intent",
    )
    parser.add_argument("--send", action="store_true", help="send pack after hard gates pass")
    parser.add_argument("--dry-run", action="store_true", help="validate without transport send")
    parser.add_argument("--episode", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    if not args.topic:
        print("error: --topic is required for poc dispatch", file=sys.stderr)
        return 2

    payload, code = poc_dispatch(
        args.topic,
        intent=args.intent,
        send=args.send,
        episode_id=args.episode,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif not payload.get("ok"):
        blockers = payload.get("hard_blockers") or payload.get("blockers") or []
        print(
            f"poc-dispatch blocked: {', '.join(blockers) or 'unknown'}",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
