#!/usr/bin/env python3
"""Shared, read-mostly evidence primitives for NDF workflow tools.

The only write helper in this module appends runtime leases to a caller-selected
path below ``<repo>/tmp``.  It never writes NDF or project state.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping


RECEIPT_SCHEMAS = frozenset(
    {
        "ndf-projection-receipt/v2",
        "ndf-close-evidence/v1",
        "ndf-runtime-lease/v1",
        "ndf-workflow-action/v2",
        "ndf-gate-receipt/v1",
    }
)
COMMON_RECEIPT_FIELDS = (
    "schema",
    "task",
    "topic",
    "mode",
    "step",
    "repo_head",
    "source_generation_sha",
    "manifest_sha",
    "context_plan_sha",
    "command",
    "input_sha",
    "output_sha",
    "evidence_paths",
    "started_at",
    "finished_at",
    "result",
    "blockers",
)
SHA256_LEN = 64


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 representation used by workflow hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha(value: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys, compact, UTF-8, no NaN)."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha(path: str | os.PathLike[str]) -> str:
    """SHA-256 of exact file bytes. Missing/non-files are errors."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _relative_path(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    if not _inside(resolved, resolved_root):
        raise ValueError(f"path escapes workspace: {path}")
    return resolved.relative_to(resolved_root).as_posix()


def bundle_sha(
    paths: Iterable[str | os.PathLike[str]],
    *,
    root: str | os.PathLike[str],
) -> str:
    """Hash an exact, path-bound file bundle.

    Files are deduplicated and sorted by workspace-relative POSIX path.  Every
    file is required.  The byte stream is ``path NUL content NUL`` per file,
    matching the established gate-bundle convention.
    """
    repo = Path(root)
    entries: dict[str, Path] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = repo / path
        rel = _relative_path(path, repo)
        if rel in entries and entries[rel].read_bytes() != path.read_bytes():
            raise ValueError(f"duplicate bundle path has different content: {rel}")
        entries[rel] = path
    if not entries:
        raise ValueError("bundle must contain at least one file")
    digest = hashlib.sha256()
    for rel, path in sorted(entries.items()):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def safe_tmp_report_path(
    path: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str],
) -> Path:
    """Resolve a report path and require it to remain below ``root/tmp``."""
    repo = Path(root).resolve()
    tmp = (repo / "tmp").resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo / candidate
    candidate = candidate.resolve(strict=False)
    if candidate == tmp or not _inside(candidate, tmp):
        raise ValueError(f"report path must be below {tmp}: {candidate}")
    # Existing symlinked parents must not redirect writes outside tmp.
    parent = candidate.parent
    while parent != tmp and not parent.exists():
        parent = parent.parent
    if parent.exists() and not _inside(parent.resolve(), tmp):
        raise ValueError(f"report parent escapes tmp: {parent}")
    return candidate


def workspace_truth(
    binding: Mapping[str, Any] | None,
    persisted: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare current workspace identity with persisted project state.

    Workspace **identity** is ``repo_root`` + ``active_topic`` (and required
    presence of a persisted head field for audit).  Expected commits that
    advance HEAD must NOT unbound identity; they only mark
    ``execution_binding_stale``.  File existence alone is not binding.
    """
    expected = dict(binding or {})
    raw = dict(persisted or {})
    actual = raw.get("workspace") if isinstance(raw.get("workspace"), Mapping) else raw
    actual = dict(actual or {})
    identity_mismatches: list[dict[str, Any]] = []
    for field in ("repo_root", "active_topic"):
        want = expected.get(field)
        got = actual.get(field)
        if want is not None and want != got:
            identity_mismatches.append({"field": field, "expected": want, "actual": got})
    want_head = expected.get("repo_head") or expected.get("bound_sha")
    got_head = actual.get("repo_head") or actual.get("bound_sha")
    head_mismatch: list[dict[str, Any]] = []
    if want_head is not None and got_head is not None and want_head != got_head:
        head_mismatch.append({"field": "repo_head", "expected": want_head, "actual": got_head})
    identity_required = ("repo_root", "active_topic")
    missing = [name for name in identity_required if not actual.get(name)]
    # Audit: persisted should record some head; absence is missing identity evidence.
    if not (actual.get("repo_head") or actual.get("bound_sha")):
        missing.append("repo_head")
    identity_bound = bool(expected and actual and not identity_mismatches and not missing)
    execution_current = identity_bound and not head_mismatch
    return {
        "workspace_bound": identity_bound,
        "state": "bound" if identity_bound else "unbound",
        "execution_binding_current": execution_current,
        "execution_binding_stale": bool(identity_bound and head_mismatch),
        "mismatches": identity_mismatches + head_mismatch,
        "identity_mismatches": identity_mismatches,
        "execution_mismatches": head_mismatch,
        "missing": missing,
        "binding": expected,
        "persisted_workspace": actual,
    }


def _is_full_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LEN
        and all(char in "0123456789abcdef" for char in value)
    )


def _is_git_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) in {40, 64}
        and all(char in "0123456789abcdef" for char in value)
    )


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one supported workflow receipt without trusting its claims."""
    errors: list[str] = []
    schema = receipt.get("schema")
    if schema not in RECEIPT_SCHEMAS:
        errors.append(f"unsupported_schema:{schema}")
    for field in COMMON_RECEIPT_FIELDS:
        if field not in receipt:
            errors.append(f"missing:{field}")
    if receipt.get("repo_head") is not None and not _is_git_sha(receipt.get("repo_head")):
        errors.append("invalid_git_sha:repo_head")
    for field in (
        "source_generation_sha",
        "manifest_sha",
        "context_plan_sha",
        "input_sha",
        "output_sha",
    ):
        value = receipt.get(field)
        if value is not None and not _is_full_sha(value):
            errors.append(f"invalid_sha256:{field}")
    for field in ("evidence_paths", "blockers"):
        value = receipt.get(field)
        if value is not None and not isinstance(value, list):
            errors.append(f"not_list:{field}")
    if schema == "ndf-runtime-lease/v1":
        for field in (
            "run_id",
            "session_id",
            "base_sha",
            "worktree",
            "branch",
            "repo_root",
            "allowed_write_root",
            "pack_sha",
            "episode_id",
        ):
            if not receipt.get(field):
                errors.append(f"missing:{field}")
        for field in ("base_sha",):
            if receipt.get(field) is not None and not _is_git_sha(receipt.get(field)):
                errors.append(f"invalid_git_sha:{field}")
        if receipt.get("pack_sha") is not None and not _is_full_sha(receipt.get("pack_sha")):
            errors.append("invalid_sha256:pack_sha")
        state = receipt.get("result")
        if state not in {"active", "released", "expired", "failed"}:
            errors.append(f"invalid_lease_result:{state}")
    elif schema == "ndf-close-evidence/v1":
        if receipt.get("mode") not in {"promote", "partial", "reject", "bug", "refactor", "rollback"}:
            errors.append(f"invalid_close_mode:{receipt.get('mode')}")
    elif schema == "ndf-projection-receipt/v2":
        if not receipt.get("projection_sha") and not receipt.get("snapshot_sha_after"):
            errors.append("missing:projection_sha")
        if receipt.get("projection_sha") is not None and not _is_full_sha(receipt.get("projection_sha")):
            errors.append("invalid_sha256:projection_sha")
        if "absorbed_action_id" not in receipt:
            errors.append("missing:absorbed_action_id")
    elif schema == "ndf-workflow-action/v2":
        for field in ("action_id", "operation", "status", "seq", "prev_event_sha", "event_sha"):
            if field not in receipt:
                errors.append(f"missing:{field}")
        if receipt.get("status") not in {"started", "finished"}:
            errors.append(f"invalid_action_status:{receipt.get('status')}")
    elif schema == "ndf-gate-receipt/v1":
        for field in (
            "phrase",
            "approved_by",
            "approved_at",
            "source_ref",
            "approved_content_sha",
        ):
            if not receipt.get(field):
                errors.append(f"missing:{field}")
        if receipt.get("approved_content_sha") is not None and not _is_full_sha(
            receipt.get("approved_content_sha")
        ):
            errors.append("invalid_sha256:approved_content_sha")
        actor = str(receipt.get("approved_by") or "").lower()
        if actor in {"agent", "openclaw", "claude-code", "canvas", "tool"}:
            errors.append("approval_actor_not_human")
    return {"valid": not errors, "schema": schema, "errors": errors}


def validate_evidence_bundle(
    receipt: Mapping[str, Any],
    *,
    root: str | os.PathLike[str],
) -> dict[str, Any]:
    """Verify that receipt output_sha names its exact evidence file bundle."""
    errors: list[str] = []
    paths = receipt.get("evidence_paths")
    if not isinstance(paths, list) or not paths:
        errors.append("missing:evidence_paths")
        actual = None
    else:
        try:
            actual = bundle_sha(paths, root=root)
        except (FileNotFoundError, ValueError, OSError):
            actual = None
            errors.append("invalid:evidence_paths")
    if actual is not None and receipt.get("output_sha") != actual:
        errors.append("mismatch:output_sha")
    return {
        "valid": not errors,
        "expected_output_sha": actual,
        "actual_output_sha": receipt.get("output_sha"),
        "errors": errors,
    }


def validate_runtime_lease_binding(
    lease: Mapping[str, Any],
    *,
    root: str | os.PathLike[str],
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate lease paths and optional exact pack/context bindings."""
    errors = list(validate_receipt(lease)["errors"])
    repo = Path(root).resolve()
    worktree: Path | None = None
    try:
        worktree = Path(str(lease.get("worktree", ""))).resolve(strict=False)
        if not _inside(worktree, repo):
            errors.append("worktree_outside_repo")
        elif not worktree.is_dir():
            errors.append("worktree_missing")
        elif worktree == repo:
            errors.append("worktree_not_isolated")
        else:
            top = subprocess.run(
                ["git", "-C", str(worktree), "rev-parse", "--show-toplevel"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if top.returncode != 0 or Path(top.stdout.strip()).resolve() != worktree:
                errors.append("worktree_not_git_root")
            head = subprocess.run(
                ["git", "-C", str(worktree), "rev-parse", "HEAD"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            actual_head = head.stdout.strip() if head.returncode == 0 else None
            base_sha = str(lease.get("base_sha") or "")
            ancestry = subprocess.run(
                ["git", "-C", str(worktree), "merge-base", "--is-ancestor", base_sha, "HEAD"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if not actual_head or ancestry.returncode != 0:
                errors.append("worktree_base_not_ancestor")
            branch = subprocess.run(
                ["git", "-C", str(worktree), "symbolic-ref", "--short", "HEAD"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if branch.returncode != 0 or branch.stdout.strip() != lease.get("branch"):
                errors.append("worktree_branch_mismatch")
    except (OSError, ValueError):
        errors.append("invalid:worktree")
    if Path(str(lease.get("repo_root") or "")).resolve(strict=False) != repo:
        errors.append("repo_root_mismatch")
    allowed_raw = lease.get("allowed_write_root")
    if isinstance(allowed_raw, str) and allowed_raw:
        allowed = Path(allowed_raw)
        if not allowed.is_absolute():
            allowed = (worktree or repo) / allowed
        try:
            if not worktree or not _inside(allowed.resolve(strict=False), worktree):
                errors.append("allowed_write_root_outside_worktree")
        except (OSError, ValueError):
            errors.append("invalid:allowed_write_root")
    else:
        errors.append("invalid:allowed_write_root")
    binding = dict(expected or {})
    aliases = {
        "plan_sha": "context_plan_sha",
        "repo_head": "repo_head",
        "base_sha": "base_sha",
        "topic": "topic",
        "task": "task",
        "manifest_sha": "manifest_sha",
        "allowed_write_root": "allowed_write_root",
        "pack_sha": "pack_sha",
        "episode_id": "episode_id",
        "branch": "branch",
        "repo_root": "repo_root",
    }
    for source, target in aliases.items():
        value = binding.get(source)
        if value is not None and lease.get(target) != value:
            errors.append(f"mismatch:{target}")
    return {"valid": not errors, "errors": sorted(set(errors))}


def runtime_lease_binding_proof(
    lease: Mapping[str, Any],
    *,
    root: str | os.PathLike[str],
) -> dict[str, Any]:
    """Capture durable facts after live worktree validation succeeds."""
    live = validate_runtime_lease_binding(lease, root=root)
    if not live["valid"]:
        raise ValueError(f"cannot prove invalid runtime lease: {live['errors']}")
    worktree = Path(str(lease["worktree"])).resolve()
    observed_head = subprocess.check_output(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
    proof: dict[str, Any] = {
        "schema": "ndf-runtime-worktree-proof/v1",
        "repo_root": str(Path(root).resolve()),
        "worktree": str(worktree),
        "branch": lease.get("branch"),
        "base_sha": lease.get("base_sha"),
        "observed_head": observed_head,
        "allowed_write_root": lease.get("allowed_write_root"),
        "run_id": lease.get("run_id"),
        "session_id": lease.get("session_id"),
        "acquisition_snapshot": git_mutation_snapshot(worktree),
    }
    proof["proof_sha"] = canonical_json_sha(proof)
    return proof


def git_mutation_snapshot(worktree: Path) -> dict[str, Any]:
    """Capture tracked, staged and untracked mutation state deterministically."""
    status = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "status",
            "--porcelain=v2",
            "--untracked-files=all",
            "-z",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if status.returncode != 0:
        raise ValueError("cannot capture git mutation snapshot")
    records = [
        item.decode("utf-8", errors="surrogateescape")
        for item in status.stdout.split(b"\0")
        if item
    ]
    paths: set[str] = set()
    for record in records:
        if record.startswith("? "):
            paths.add(record[2:])
        elif record.startswith(("1 ", "u ")):
            paths.add(record.split(" ", 8)[-1])
        elif record.startswith("2 "):
            payload = record.split(" ", 9)[-1]
            paths.add(payload.split("\t", 1)[0])
    snapshot = {
        "schema": "ndf-git-mutation-snapshot/v1",
        "head": subprocess.check_output(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip(),
        "status_porcelain_v2_sha": hashlib.sha256(status.stdout).hexdigest(),
        "paths": sorted(paths),
        "path_shas": {
            path: (
                hashlib.sha256((worktree / path).read_bytes()).hexdigest()
                if (worktree / path).is_file()
                else "[deleted-or-nonfile]"
            )
            for path in sorted(paths)
        },
    }
    snapshot["snapshot_sha"] = canonical_json_sha(snapshot)
    return snapshot


def validate_recorded_runtime_lease_binding(
    lease: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify content-bound lease facts without requiring a live worktree."""
    errors = list(validate_receipt(lease)["errors"])
    proof = lease.get("binding_proof")
    if not isinstance(proof, Mapping):
        errors.append("missing:binding_proof")
        return {"valid": False, "errors": sorted(set(errors))}
    unhashed = {key: value for key, value in proof.items() if key != "proof_sha"}
    if proof.get("proof_sha") != canonical_json_sha(unhashed):
        errors.append("mismatch:binding_proof_sha")
    for field in (
        "repo_root",
        "worktree",
        "branch",
        "base_sha",
        "allowed_write_root",
        "run_id",
        "session_id",
    ):
        if proof.get(field) != lease.get(field):
            errors.append(f"mismatch:binding_proof:{field}")
    binding = dict(expected or {})
    aliases = {
        "plan_sha": "context_plan_sha",
        "repo_head": "repo_head",
        "base_sha": "base_sha",
        "topic": "topic",
        "task": "task",
        "manifest_sha": "manifest_sha",
        "allowed_write_root": "allowed_write_root",
        "pack_sha": "pack_sha",
        "episode_id": "episode_id",
        "branch": "branch",
        "repo_root": "repo_root",
    }
    for source, target in aliases.items():
        value = binding.get(source)
        if value is not None and lease.get(target) != value:
            errors.append(f"mismatch:{target}")
    return {"valid": not errors, "errors": sorted(set(errors))}


def chained_event(
    payload: Mapping[str, Any],
    *,
    previous_sha: str | None,
) -> dict[str, Any]:
    """Return an immutable hash-linked event envelope."""
    event = dict(payload)
    event["prev_event_sha"] = previous_sha
    event.pop("event_sha", None)
    event["event_sha"] = canonical_json_sha(event)
    return event


def validate_event_chain(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate sequence, previous hash and canonical event hashes."""
    errors: list[str] = []
    previous: str | None = None
    expected_seq = 1
    count = 0
    for count, raw in enumerate(events, 1):
        event = dict(raw)
        if event.get("seq") != expected_seq:
            errors.append(f"seq:{count}")
        if event.get("prev_event_sha") != previous:
            errors.append(f"prev_event_sha:{count}")
        claimed = event.pop("event_sha", None)
        actual = canonical_json_sha(event)
        if claimed != actual:
            errors.append(f"event_sha:{count}")
        previous = claimed if isinstance(claimed, str) else None
        expected_seq += 1
    return {
        "valid": not errors,
        "count": count,
        "tip_sha": previous,
        "errors": errors,
    }


def read_lease_jsonl(
    path: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str],
    strict: bool = True,
) -> list[dict[str, Any]]:
    """Read validated runtime leases from a guarded tmp JSONL file."""
    target = safe_tmp_report_path(path, root=root)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            if strict:
                raise ValueError(f"invalid JSONL at line {line_no}: {exc}") from exc
            continue
        validation = validate_receipt(value) if isinstance(value, Mapping) else {"valid": False}
        if not validation["valid"] or value.get("schema") != "ndf-runtime-lease/v1":
            if strict:
                raise ValueError(
                    f"invalid runtime lease at line {line_no}: {validation.get('errors', [])}"
                )
            continue
        records.append(dict(value))
    return records


def append_runtime_lease(
    path: str | os.PathLike[str],
    lease: Mapping[str, Any],
    *,
    root: str | os.PathLike[str],
) -> Path:
    """Append one validated lease as canonical JSON below ``root/tmp``."""
    validation = validate_receipt(lease)
    if lease.get("schema") != "ndf-runtime-lease/v1" or not validation["valid"]:
        raise ValueError(f"invalid runtime lease: {validation['errors']}")
    target = safe_tmp_report_path(path, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("ab") as stream:
        stream.write(canonical_json_bytes(dict(lease)) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    return target


# Concise aliases for callers that use lease terminology.
read_leases = read_lease_jsonl
append_lease = append_runtime_lease
