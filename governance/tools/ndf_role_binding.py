#!/usr/bin/env python3
"""Role adapter binding for NDF workflow (stdlib only).

Loads ``ndf.workflow.yaml`` roles.* (adapter / fallback / model), resolves
provider per role, and exposes dispatch safety helpers for
``ndf_workflow_status`` / ``ndf_dispatch_send``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROLES = ("command", "control", "implementation")
ROLE_LABELS = {
    "command": "Command surface",
    "control": "Control agent",
    "implementation": "Implementation agent",
}
DEFAULT_ADAPTERS = {
    "command": "cursor",
    "control": "openclaw",
    "implementation": "claude-code",
}
SESSION_BINDING_VERSION = "ndf-v1"
LEGACY_SHARED_SESSION_KEY = "agent:main:main"
OPENCLAW_SESSION_RE = re.compile(r"OpenClaw 指挥会话 session_key：`([^`]+)`")
PROVIDER_BY_ADAPTER = {
    "openclaw": "openclaw",
    "claude-code": "claude-code-acp",
    "claude-code-acp": "claude-code-acp",
    "cursor": "in-host",
    "in-host": "in-host",
    "dual-session": "dual-session",
    "custom": "custom",
    "generic": "in-host",
    "opencode": "in-host",
    "codex": "in-host",
    "auto": "in-host",
}
PACK_PROVIDER_ROLE = {
    "openclaw": "control",
    "claude-code-acp": "implementation",
    "in-host": None,
    "dual-session": None,
}
CONTROL_WRITABLE = [
    "spec/open/",
    "spec/00-charter/",
    "spec/10-architecture/",
    "spec/20-behavior/",
    "spec/30-interfaces/",
    "spec/40-constraints/",
    "spec/50-verification/",
    "spec/decisions/",
    "spec/INDEX.md",
    "spec/meta/open/",
    "poc/*/ndf/",
    ".openclaw/state.json",
    "ndf.workspace.json",
]
GENESIS_GATES = Path("spec/open/project-genesis/GATES.md")
ROLES_GATE_PHRASE = "角色已配置"
HARNESS_TEMPLATE = Path("packages/ndf-harness/workflow/ndf.workflow.yaml")


def _repo_root(repo: Path | str | None = None) -> Path:
    if repo is not None:
        return Path(repo).resolve()
    here = Path(__file__).resolve().parent
    for cand in (here.parents[2], here.parents[3]):
        if (cand / "ndf.workflow.yaml").is_file() or (cand / "spec" / "meta").is_dir():
            return cand
    return here.parents[2]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    key_re = re.compile(r"^(\s*)([\w-]+):\s*(.*)$")
    list_re = re.compile(r"^(\s*)-\s+(.*)$")

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = list_re.match(raw)
        if m:
            indent, value = len(m.group(1)), m.group(2).strip().strip("'\"")
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if isinstance(parent, dict):
                raise ValueError(f"list item without list parent: {raw}")
            parent.append(value)
            continue
        m = key_re.match(raw)
        if m:
            indent, key, rest = len(m.group(1)), m.group(2), m.group(3).strip()
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if rest == "":
                node: Any
                lines = text.splitlines()
                idx = text.splitlines().index(raw)
                nxt = ""
                for follow in lines[idx + 1 :]:
                    if follow.strip() and not follow.lstrip().startswith("#"):
                        nxt = follow
                        break
                node = [] if list_re.match(nxt or "") else {}
                parent[key] = node
                stack.append((indent, node))
            elif rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1].strip()
                parent[key] = (
                    [x.strip() for x in inner.split(",") if x.strip()] if inner else []
                )
            else:
                val = rest.strip("'\"")
                if val in ("true", "false"):
                    parent[key] = val == "true"
                else:
                    try:
                        parent[key] = int(val)
                    except ValueError:
                        parent[key] = val
            continue
        raise ValueError(f"unparsed yaml line: {raw}")
    return root


def workflow_yaml_path(repo: Path | str | None = None) -> Path:
    return _repo_root(repo) / "ndf.workflow.yaml"


def load_workflow(repo: Path | str | None = None) -> dict[str, Any]:
    path = workflow_yaml_path(repo)
    if not path.is_file():
        return {}
    return _parse_simple_yaml(_read_text(path))


def _normalize_adapter(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "claude": "claude-code",
        "claude-code-acp": "claude-code",
        "inhost": "in-host",
        "in-host": "in-host",
        "dualsession": "dual-session",
        "dual-session": "dual-session",
        "openclaw": "openclaw",
        "cursor": "cursor",
        "opencode": "opencode",
        "codex": "codex",
        "generic": "generic",
        "custom": "custom",
        "auto": "auto",
    }
    return aliases.get(text, text)


def role_config(repo: Path | str | None, role: str) -> dict[str, Any]:
    wf = load_workflow(repo)
    roles = wf.get("roles") if isinstance(wf.get("roles"), Mapping) else {}
    block = roles.get(role) if isinstance(roles, Mapping) else {}
    if not isinstance(block, Mapping):
        block = {}
    adapter = _normalize_adapter(str(block.get("adapter") or ""))
    fallback = _normalize_adapter(str(block.get("fallback") or ""))
    model = str(block.get("model") or "").strip() or None
    custom_command = str(block.get("command") or block.get("custom_command") or "").strip()
    out: dict[str, Any] = {
        "adapter": adapter,
        "fallback": fallback,
        "model": model,
        "command": custom_command or None,
        "writable": list(block.get("writable") or []) if role == "control" else [],
        "raw": dict(block),
    }
    if role in {"control", "implementation"}:
        out["agent_id"] = str(block.get("agent_id") or "").strip() or None
        out["session_key"] = str(block.get("session_key") or "").strip() or None
        out["session_transport"] = (
            str(block.get("session_transport") or "").strip() or None
        )
        out["session_binding_version"] = (
            str(block.get("session_binding_version") or "").strip() or None
        )
    return out


def _sanitize_repo_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return (slug or "repo")[:40]


def _normalize_openclaw_role(role: str | None) -> str:
    r = str(role or "control").strip().lower()
    if r in {"implementation", "impl"}:
        return "implementation"
    return "control"


def openclaw_repo_identity(
    repo: Path | str | None = None,
    *,
    role: str = "control",
) -> dict[str, Any]:
    """Stable per-git-common-dir OpenClaw identity; role may suffix agent (META-022)."""
    root = _repo_root(repo)
    git_common = ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            git_common = str(Path(proc.stdout.strip()).resolve())
    except (OSError, subprocess.TimeoutExpired):
        git_common = ""
    identity_src = git_common or str(root.resolve())
    digest = hashlib.sha256(identity_src.encode("utf-8")).hexdigest()[:12]
    # Prefer main checkout name (parent of .git / common-dir) so worktrees share slug.
    slug_src = root.name
    if git_common:
        common_path = Path(git_common)
        # bare: .../repo.git → repo; normal: .../repo/.git → repo
        if common_path.name == ".git":
            slug_src = common_path.parent.name
        elif common_path.name.endswith(".git"):
            slug_src = common_path.name[: -len(".git")] or common_path.name
        else:
            slug_src = common_path.parent.name or common_path.name
    slug = _sanitize_repo_slug(slug_src)
    base_agent_id = f"ndf-{slug}-{digest}"
    oc_role = _normalize_openclaw_role(role)
    agent_id = f"{base_agent_id}-impl" if oc_role == "implementation" else base_agent_id
    session_key = f"agent:{agent_id}:main"
    # Prefer primary checkout as OpenClaw workspace so main/worktree share one bind.
    workspace = str(root.resolve())
    if git_common:
        common_path = Path(git_common)
        if common_path.name == ".git":
            workspace = str(common_path.parent.resolve())
    return {
        "repo_root": str(root.resolve()),
        "workspace": workspace,
        "git_common_dir": git_common or None,
        "repo_slug": slug,
        "identity_hash": digest,
        "role": oc_role,
        "base_agent_id": base_agent_id,
        "agent_id": agent_id,
        "session_key": session_key,
        "session_transport": "session_key",
        "session_binding_version": SESSION_BINDING_VERSION,
    }


def paired_openclaw_agent_ids(repo: Path | str | None = None) -> set[str]:
    """Control + Implementation managed agent ids for one git-common-dir."""
    base = openclaw_repo_identity(repo, role="control")
    impl = openclaw_repo_identity(repo, role="implementation")
    return {str(base["agent_id"]), str(impl["agent_id"])}


def managed_openclaw_binding(
    repo: Path | str | None = None,
    *,
    role: str = "control",
) -> dict[str, Any]:
    identity = openclaw_repo_identity(repo, role=role)
    return {
        "agent_id": identity["agent_id"],
        "session_key": identity["session_key"],
        "session_transport": identity["session_transport"],
        "session_binding_version": identity["session_binding_version"],
        "identity_hash": identity["identity_hash"],
        "role": identity.get("role") or _normalize_openclaw_role(role),
        "base_agent_id": identity.get("base_agent_id"),
        "repo_root": identity["repo_root"],
        "workspace": identity.get("workspace") or identity["repo_root"],
        "git_common_dir": identity["git_common_dir"],
    }


def _legacy_agents_session_key(repo: Path | str | None = None) -> str | None:
    path = _repo_root(repo) / "AGENTS.md"
    if not path.is_file():
        return None
    match = OPENCLAW_SESSION_RE.search(_read_text(path))
    return match.group(1).strip() if match else None


def configured_openclaw_session(
    repo: Path | str | None = None,
    *,
    role: str = "control",
) -> dict[str, Any]:
    """Resolve OpenClaw session for a role from workflow yaml (preferred) or AGENTS.md."""
    root = _repo_root(repo)
    oc_role = _normalize_openclaw_role(role)
    cfg = role_config(root, oc_role)
    expected = managed_openclaw_binding(root, role=oc_role)
    agent_id = cfg.get("agent_id")
    session_key = cfg.get("session_key")
    transport = cfg.get("session_transport") or "session_key"
    binding_version = cfg.get("session_binding_version")
    source = "workflow"
    if not session_key:
        # Legacy AGENTS.md line only feeds Control (META-020 migration).
        if oc_role == "control":
            legacy = _legacy_agents_session_key(root)
            if legacy:
                session_key = legacy
                source = "agents_md"
            else:
                source = "unconfigured"
        else:
            source = "unconfigured"
    ownership = "unverified"
    blockers: list[str] = []
    if binding_version == SESSION_BINDING_VERSION and session_key and agent_id:
        if (
            session_key == expected["session_key"]
            and agent_id == expected["agent_id"]
        ):
            ownership = "managed"
        else:
            ownership = "stale"
            blockers.append("openclaw_session_collision_or_stale_binding")
    elif session_key in {None, "", LEGACY_SHARED_SESSION_KEY}:
        ownership = "legacy_shared"
        blockers.append("openclaw_session_legacy_shared")
    elif session_key:
        ownership = "custom_unverified"
        blockers.append("openclaw_session_ownership_unverified")
    else:
        ownership = "unconfigured"
        blockers.append("openclaw_session_unconfigured")
    return {
        "role": oc_role,
        "agent_id": agent_id,
        "session_key": session_key,
        "session_transport": transport,
        "session_binding_version": binding_version,
        "source": source,
        "ownership": ownership,
        "expected": expected,
        "multi_project_safe": ownership == "managed",
        "blockers": blockers,
    }


def openclaw_dual_role_required(repo: Path | str | None = None) -> bool:
    """True when Control and Implementation both resolve to OpenClaw transport."""
    root = _repo_root(repo)
    return (
        resolve_role(root, "control").get("provider") == "openclaw"
        and resolve_role(root, "implementation").get("provider") == "openclaw"
    )


def openclaw_role_session_collapse(
    repo: Path | str | None = None,
) -> dict[str, Any]:
    """Detect Implementation reusing Control session_key (META-022)."""
    root = _repo_root(repo)
    if not openclaw_dual_role_required(root):
        return {"collapsed": False, "error": None, "control": None, "implementation": None}
    control = configured_openclaw_session(root, role="control")
    impl = configured_openclaw_session(root, role="implementation")
    c_key = str(control.get("session_key") or "").strip()
    i_key = str(impl.get("session_key") or "").strip()
    if c_key and i_key and c_key == i_key:
        return {
            "collapsed": True,
            "error": "openclaw_role_session_collapsed",
            "control": control,
            "implementation": impl,
        }
    if not i_key:
        return {
            "collapsed": True,
            "error": "openclaw_session_unconfigured",
            "control": control,
            "implementation": impl,
        }
    return {
        "collapsed": False,
        "error": None,
        "control": control,
        "implementation": impl,
    }


def _extract_json_payload(text: str) -> Any:
    raw = text or ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def list_openclaw_agents(
    *,
    executable: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    exe = executable or shutil.which("openclaw")
    if not exe:
        return [], "openclaw_cli_missing"
    try:
        proc = subprocess.run(
            [exe, "agents", "list", "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"openclaw_agents_unavailable:{exc}"
    payload = _extract_json_payload(proc.stdout or "")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], None
    if isinstance(payload, dict):
        agents = payload.get("agents")
        if isinstance(agents, list):
            return [item for item in agents if isinstance(item, dict)], None
    if proc.returncode != 0:
        return [], "openclaw_agents_list_failed"
    return [], "invalid_agents_json"


def _agent_workspace(item: Mapping[str, Any]) -> str | None:
    raw = item.get("workspace") or item.get("workspaceDir") or item.get("workspace_dir")
    if not raw:
        return None
    try:
        return str(Path(str(raw)).resolve())
    except OSError:
        return str(raw)


def _ensure_openclaw_agent(
    *,
    exe: str,
    agents: list[dict[str, Any]],
    agent_id: str,
    workspace: str,
    paired_ids: set[str],
    root: Path,
) -> dict[str, Any]:
    """Add or reuse one OpenClaw agent; allow paired role agents on same workspace."""
    result: dict[str, Any] = {
        "ok": False,
        "provisioned": False,
        "reused": False,
        "error": None,
        "blockers": [],
    }
    match = None
    for item in agents:
        aid = str(item.get("id") or item.get("agentId") or item.get("name") or "")
        if aid == agent_id:
            match = item
            break
    if match is not None:
        existing_ws = _agent_workspace(match)
        if existing_ws and existing_ws != workspace:
            result["error"] = "openclaw_agent_workspace_collision"
            result["blockers"] = ["openclaw_agent_workspace_collision"]
            result["existing_workspace"] = existing_ws
            return result
        result["ok"] = True
        result["reused"] = True
        return result

    for item in agents:
        existing_ws = _agent_workspace(item)
        if existing_ws != workspace:
            continue
        aid = str(item.get("id") or item.get("agentId") or item.get("name") or "")
        # META-022: Control + Implementation may share workspace.
        if aid and aid != agent_id and aid != "main" and aid not in paired_ids:
            result["error"] = "openclaw_workspace_already_bound"
            result["blockers"] = ["openclaw_workspace_already_bound"]
            result["existing_agent_id"] = aid
            return result
    try:
        proc = subprocess.run(
            [
                exe,
                "agents",
                "add",
                agent_id,
                "--non-interactive",
                "--workspace",
                workspace,
                "--json",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["error"] = f"openclaw_agents_add_failed:{exc}"
        result["blockers"] = ["openclaw_agents_add_failed"]
        return result
    if proc.returncode != 0:
        agents2, _ = list_openclaw_agents(executable=exe)
        if not any(
            str(item.get("id") or item.get("agentId") or item.get("name") or "")
            == agent_id
            for item in agents2
        ):
            result["error"] = "openclaw_agents_add_failed"
            result["blockers"] = ["openclaw_agents_add_failed"]
            result["detail"] = (proc.stdout or "")[:800]
            return result
        result["ok"] = True
        result["reused"] = True
        return result
    result["ok"] = True
    result["provisioned"] = True
    return result


def provision_openclaw_role_agent(
    repo: Path | str | None = None,
    *,
    role: str = "control",
    force_rebind: bool = False,
    no_provision: bool = False,
    agents: list[dict[str, Any]] | None = None,
    executable: str | None = None,
) -> dict[str, Any]:
    """Idempotently provision one role's OpenClaw agent + managed session binding."""
    root = _repo_root(repo)
    oc_role = _normalize_openclaw_role(role)
    expected = managed_openclaw_binding(root, role=oc_role)
    current = configured_openclaw_session(root, role=oc_role)
    result: dict[str, Any] = {
        "ok": False,
        "role": oc_role,
        "expected": expected,
        "before": current,
        "provisioned": False,
        "reused": False,
        "binding": None,
        "error": None,
        "blockers": [],
    }
    if no_provision:
        result["error"] = "openclaw_provision_skipped"
        result["blockers"] = ["openclaw_provision_skipped"]
        return result
    if current.get("ownership") == "custom_unverified" and not force_rebind:
        result["error"] = "openclaw_session_ownership_unverified"
        result["blockers"] = list(current.get("blockers") or [])
        return result
    if current.get("ownership") == "stale" and not force_rebind:
        result["error"] = "openclaw_session_collision_or_stale_binding"
        result["blockers"] = list(current.get("blockers") or [])
        return result

    exe = executable or shutil.which("openclaw")
    if not exe:
        result["error"] = "openclaw_cli_missing"
        result["blockers"] = ["openclaw_cli_missing"]
        return result

    agent_list = agents
    list_error = None
    if agent_list is None:
        agent_list, list_error = list_openclaw_agents(executable=exe)
    if list_error and not agent_list:
        result["error"] = list_error
        result["blockers"] = [list_error]
        return result

    agent_id = str(expected["agent_id"])
    workspace = str(expected.get("workspace") or expected["repo_root"])
    paired = paired_openclaw_agent_ids(root)
    ensured = _ensure_openclaw_agent(
        exe=exe,
        agents=list(agent_list or []),
        agent_id=agent_id,
        workspace=workspace,
        paired_ids=paired,
        root=root,
    )
    if not ensured.get("ok"):
        result["error"] = ensured.get("error")
        result["blockers"] = list(ensured.get("blockers") or [])
        if ensured.get("existing_workspace"):
            result["existing_workspace"] = ensured["existing_workspace"]
        if ensured.get("existing_agent_id"):
            result["existing_agent_id"] = ensured["existing_agent_id"]
        if ensured.get("detail"):
            result["detail"] = ensured["detail"]
        return result
    result["provisioned"] = bool(ensured.get("provisioned"))
    result["reused"] = bool(ensured.get("reused"))

    binding: dict[str, Any] = {
        "adapter": "openclaw",
        "agent_id": expected["agent_id"],
        "session_key": expected["session_key"],
        "session_transport": expected["session_transport"],
        "session_binding_version": expected["session_binding_version"],
    }
    cfg = role_config(root, oc_role)
    if cfg.get("fallback"):
        binding["fallback"] = cfg["fallback"]
    if cfg.get("model"):
        binding["model"] = cfg["model"]
    path = _ensure_workflow_file(root)
    updated = _update_roles_in_yaml(_read_text(path), {oc_role: binding})
    path.write_text(updated, encoding="utf-8")
    result["ok"] = True
    result["binding"] = binding
    result["after"] = configured_openclaw_session(root, role=oc_role)
    result["path"] = str(path.relative_to(root))
    return result


def provision_openclaw_project_agent(
    repo: Path | str | None = None,
    *,
    force_rebind: bool = False,
    no_provision: bool = False,
) -> dict[str, Any]:
    """Provision Control (+ Implementation when both OpenClaw) managed sessions."""
    root = _repo_root(repo)
    control = provision_openclaw_role_agent(
        root,
        role="control",
        force_rebind=force_rebind,
        no_provision=no_provision,
    )
    result: dict[str, Any] = {
        "ok": bool(control.get("ok")),
        "expected": control.get("expected"),
        "before": control.get("before"),
        "provisioned": bool(control.get("provisioned")),
        "reused": bool(control.get("reused")),
        "binding": control.get("binding"),
        "error": control.get("error"),
        "blockers": list(control.get("blockers") or []),
        "control": control,
        "implementation": None,
        "path": control.get("path"),
        "after": control.get("after"),
    }
    if not control.get("ok"):
        return result

    # META-022: second identity when Implementation also uses OpenClaw.
    impl_adapter = _normalize_adapter(
        str(role_config(root, "implementation").get("adapter") or "")
    )
    if impl_adapter == "openclaw" or resolve_role(root, "implementation").get(
        "provider"
    ) == "openclaw":
        impl = provision_openclaw_role_agent(
            root,
            role="implementation",
            force_rebind=force_rebind,
            no_provision=no_provision,
        )
        result["implementation"] = impl
        if not impl.get("ok"):
            result["ok"] = False
            result["error"] = impl.get("error") or "openclaw_impl_provision_failed"
            result["blockers"] = list(impl.get("blockers") or result["blockers"])
            return result
        result["provisioned"] = result["provisioned"] or bool(impl.get("provisioned"))
        result["reused"] = result["reused"] and bool(impl.get("reused"))
        collapse = openclaw_role_session_collapse(root)
        if collapse.get("collapsed"):
            result["ok"] = False
            result["error"] = collapse.get("error") or "openclaw_role_session_collapsed"
            result["blockers"] = [result["error"]]
            return result
    result["after"] = configured_openclaw_session(root, role="control")
    return result


def cfg_get_fallback(repo: Path | str | None) -> str | None:
    return role_config(repo, "control").get("fallback")

def _cli_available(adapter: str) -> bool:
    norm = _normalize_adapter(adapter)
    if norm == "openclaw":
        return bool(shutil.which("openclaw"))
    if norm in {"claude-code", "claude-code-acp"}:
        return bool(shutil.which("claude"))
    if norm in {"cursor", "in-host", "dual-session", "custom", "generic", "opencode", "codex", "auto"}:
        return True
    return False


def _provider_for_adapter(adapter: str) -> str:
    norm = _normalize_adapter(adapter)
    return PROVIDER_BY_ADAPTER.get(norm, "unsupported")


def _human_next(provider: str, role: str, *, adapter: str, fallback: str) -> str:
    if provider == "openclaw":
        return "OpenClaw CLI 可用；使用 control-pack / dispatch-send 正常派发。"
    if provider == "claude-code-acp":
        return "Claude Code CLI 可用；使用 poc-dispatch --send 正常派发。"
    if provider == "in-host":
        return (
            f"在指挥面宿主内 spawn {ROLE_LABELS.get(role, role)} 子 agent；"
            f"读 tmp/ndf-role-spawn-{role}.json，完成后写磁盘 ndf-agent-completion/v1。"
        )
    if provider == "dual-session":
        return (
            f"打开第二聊天会话承载 {ROLE_LABELS.get(role, role)}；"
            f"粘贴 spawn 文件中的 prompt；仍等待磁盘 completion，不得伪造 ACK。"
        )
    if provider == "custom":
        return "运行 ndf.workflow.yaml 中为该角色配置的 custom command；等待磁盘 completion。"
    return (
        f"角色 {role} 的 adapter={adapter or '?'} fallback={fallback or '?'} "
        "均不可用；运行: python3 spec/meta/tools/ndf_role_binding.py bind --repo ."
    )


def resolve_role(repo: Path | str | None, role: str) -> dict[str, Any]:
    """Resolve adapter → provider for a logical role."""
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    cfg = role_config(repo, role)
    adapter = cfg["adapter"] or _normalize_adapter(DEFAULT_ADAPTERS[role])
    fallback = cfg["fallback"]
    model = cfg["model"]
    custom_command = cfg["command"]

    provider = "unsupported"
    available = False
    chosen = adapter

    if adapter and _cli_available(adapter) and _provider_for_adapter(adapter) not in {
        "unsupported",
        "in-host",
    }:
        provider = _provider_for_adapter(adapter)
        available = provider in {"openclaw", "claude-code-acp"}
        chosen = adapter
    elif adapter in {"in-host", "cursor", "generic", "opencode", "codex", "auto"} or fallback == "in-host":
        provider = "in-host"
        available = True
        chosen = adapter if adapter in {"in-host", "cursor", "auto"} else "in-host"
    elif fallback == "dual-session" or adapter == "dual-session":
        provider = "dual-session"
        available = True
        chosen = "dual-session"
    elif (adapter == "custom" or fallback == "custom") and custom_command:
        provider = "custom"
        available = True
        chosen = "custom"
    elif adapter and _provider_for_adapter(adapter) == "in-host":
        provider = "in-host"
        available = True
        chosen = adapter
    else:
        provider = "unsupported"
        available = False
        chosen = adapter or fallback or ""

    writable = list(CONTROL_WRITABLE)
    if cfg["writable"]:
        writable = list(cfg["writable"])

    return {
        "role": role,
        "adapter": chosen,
        "fallback": fallback or None,
        "model": model,
        "provider": provider,
        "available": available,
        "human_next": _human_next(
            provider, role, adapter=adapter, fallback=fallback or ""
        ),
        "writable": writable if role == "control" else [],
        "custom_command": custom_command,
    }


def _normalized_roles_block(repo: Path | str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for role in ROLES:
        cfg = role_config(repo, role)
        entry: dict[str, Any] = {}
        if cfg["adapter"]:
            entry["adapter"] = cfg["adapter"]
        if cfg["fallback"]:
            entry["fallback"] = cfg["fallback"]
        if cfg["model"]:
            entry["model"] = cfg["model"]
        if cfg["command"]:
            entry["command"] = cfg["command"]
        out[role] = entry
    return out


def roles_sha(repo: Path | str | None = None) -> str:
    """SHA256 of normalized roles block for gate receipts."""
    blob = json.dumps(_normalized_roles_block(repo), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _genesis_roles_gate_valid(repo: Path) -> bool:
    gates = repo / GENESIS_GATES
    if not gates.is_file():
        return False
    for line in _read_text(gates).splitlines():
        if ROLES_GATE_PHRASE not in line:
            continue
        if "|" not in line or line.strip().startswith("|--"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            continue
        phrase = parts[2] if len(parts) > 2 else ""
        status = parts[7] if len(parts) > 7 else ""
        if phrase == ROLES_GATE_PHRASE and status.lower() in {"approved", "valid"}:
            return True
    return False


def _project_maturity(repo: Path) -> str:
    """Lightweight maturity probe without importing ndf_workflow_status."""
    decision = repo / "spec/decisions/dec-project-genesis.md"
    if decision.is_file():
        text = _read_text(decision)
        status_m = re.search(r"(?mi)^status:\s*(.+)$", text)
        if status_m and "accepted" in status_m.group(1).lower():
            trunk = ""
            m = re.search(r"(?mi)^genesis_trunk_sha:\s*(\S+)", text)
            if m:
                trunk = m.group(1)
            if trunk and not re.search(r"(?i)pending|tbd|unknown", trunk):
                return "operational"
    has_charter = (repo / "spec/00-charter").is_dir()
    has_src = (repo / "src").is_dir()
    # Prefer operational_legacy for healthy brownfield even if genesis stubs exist.
    if has_charter and has_src:
        return "operational_legacy"
    idea = repo / "spec/open/project-genesis/IDEA.md"
    foundation = repo / "spec/open/project-genesis/FOUNDATION.md"
    if idea.is_file() or (repo / "spec/open/proposal-project-genesis.md").is_file():
        if foundation.is_file():
            return "trunk_candidate" if has_src else "ndf_foundation"
        return "idea_review"
    if has_charter:
        return "ndf_foundation"
    return "uninitialized"


def roles_bound(repo: Path | str | None = None) -> bool:
    """True when command/control/implementation each have a non-empty adapter."""
    root = _repo_root(repo)
    for role in ROLES:
        cfg = role_config(root, role)
        if not cfg["adapter"]:
            return False
    maturity = _project_maturity(root)
    if maturity in {"operational", "operational_legacy"}:
        return True
    # Greenfield: require genesis gate receipt when progressing past G0.
    return _genesis_roles_gate_valid(root)


def check_roles_for_dispatch(repo: Path | str | None = None) -> tuple[bool, list[str]]:
    """Integration helper for pack construction / dispatch safety."""
    blockers: list[str] = []
    if not roles_bound(repo):
        blockers.append("roles_unbound")
        root = _repo_root(repo)
        missing = [r for r in ROLES if not role_config(root, r)["adapter"]]
        if missing:
            blockers.append(f"roles_missing_adapter:{','.join(missing)}")
        if _project_maturity(root) not in {"operational", "operational_legacy"}:
            if not _genesis_roles_gate_valid(root):
                blockers.append("roles_gate_missing:角色已配置")
    collapse = openclaw_role_session_collapse(repo)
    if collapse.get("collapsed") and collapse.get("error"):
        err = str(collapse["error"])
        if err not in blockers:
            blockers.append(err)
    return (not blockers), blockers


def resolve_pack_provider(
    repo: Path | str | None,
    pack: Mapping[str, Any],
) -> dict[str, Any]:
    """Map pack → role resolution (task first; META-021 / META-022)."""
    provider = str(pack.get("provider") or "")
    task = str(pack.get("task") or "")
    hop = str(pack.get("hop") or "")
    # Task / hop beat PACK_PROVIDER_ROLE so openclaw+poc_* maps Implementation.
    if task == "project_genesis" or hop.startswith("genesis_"):
        role = "implementation"
    elif task.startswith("poc_") or task in {
        "implement",
        "poc_measurement",
        "prepare_acp_lease",
    }:
        role = "implementation"
    elif (
        task.startswith("binder_")
        or task.startswith("gate_")
        or "proposal" in task
        or task.startswith("ndf_improvement")
    ):
        role = "control"
    else:
        role = PACK_PROVIDER_ROLE.get(provider)
        if role is None:
            if provider == "openclaw" or "control" in task:
                role = "control"
            else:
                role = (
                    "implementation"
                    if "poc" in str(pack.get("track") or "")
                    else "control"
                )
    resolved = resolve_role(repo, role)
    return {**resolved, "pack_provider": provider, "mapped_role": role}


def write_spawn_file(
    repo: Path | str | None,
    role: str,
    pack_path: str | Path,
    **meta: Any,
) -> Path:
    """Write tmp/ndf-role-spawn-<role>.json — does NOT fake transport ACK."""
    root = _repo_root(repo)
    resolved = resolve_role(root, role)
    provider = str(meta.get("provider") or resolved["provider"])
    if provider not in {"in-host", "dual-session"}:
        provider = resolved["provider"]
    pack = Path(pack_path)
    if not pack.is_absolute():
        pack = root / pack
    payload: dict[str, Any] = {
        "schema": "ndf-role-spawn/v1",
        "role": role,
        "provider": provider,
        "adapter": resolved["adapter"],
        "fallback": resolved["fallback"],
        "model_hint": meta.get("model") or resolved.get("model"),
        "pack_path": str(pack.relative_to(root)) if pack.is_relative_to(root) else str(pack),
        "write_roots": meta.get("write_roots")
        or meta.get("allowed_write_root")
        or meta.get("allowed_write_roots")
        or (resolved["writable"] if role == "control" else []),
        "completion_receipt_path": meta.get("completion_receipt_path"),
        "human_next": resolved["human_next"],
        "spawned_at": meta.get("spawned_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Disk ndf-agent-completion/v1 is the only success signal; no transport ACK.",
    }
    for key in ("topic", "task", "episode_id", "attempt_id", "base_sha"):
        if key in meta and meta[key]:
            payload[key] = meta[key]
    out = root / "tmp" / f"ndf-role-spawn-{role}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def probe_adapters(repo: Path | str | None = None) -> dict[str, Any]:
    root = _repo_root(repo)
    cli = {
        "openclaw": bool(shutil.which("openclaw")),
        "claude": bool(shutil.which("claude")),
        "cursor": True,
    }
    recommended: dict[str, str] = {}
    for role in ROLES:
        if role == "command":
            recommended[role] = "cursor"
        elif role == "control":
            recommended[role] = "openclaw" if cli["openclaw"] else "in_host"
        elif role == "implementation":
            recommended[role] = "claude-code" if cli["claude"] else "in_host"
    roles_summary = {role: resolve_role(root, role) for role in ROLES}
    return {
        "cli": cli,
        "recommended_adapters": recommended,
        "roles": roles_summary,
        "roles_bound": roles_bound(root),
        "roles_sha": roles_sha(root),
    }


def status_report(repo: Path | str | None = None) -> dict[str, Any]:
    root = _repo_root(repo)
    wf_path = workflow_yaml_path(root)
    maturity = _project_maturity(root)
    control_session = configured_openclaw_session(root, role="control")
    impl_session = configured_openclaw_session(root, role="implementation")
    collapse = openclaw_role_session_collapse(root)
    return {
        "workflow_yaml": str(wf_path.relative_to(root)) if wf_path.is_file() else None,
        "roles_bound": roles_bound(root),
        "roles_sha": roles_sha(root),
        "project_maturity": maturity,
        "genesis_roles_gate": _genesis_roles_gate_valid(root),
        "roles": {role: resolve_role(root, role) for role in ROLES},
        "normalized_roles": _normalized_roles_block(root),
        "openclaw_session": control_session,
        "openclaw_session_implementation": impl_session,
        "openclaw_identity": openclaw_repo_identity(root, role="control"),
        "openclaw_identity_implementation": openclaw_repo_identity(
            root, role="implementation"
        ),
        "openclaw_role_session_collapse": collapse,
    }


def _ensure_workflow_file(repo: Path) -> Path:
    path = workflow_yaml_path(repo)
    if path.is_file():
        return path
    tpl = repo / HARNESS_TEMPLATE
    if not tpl.is_file():
        tpl = Path(__file__).resolve().parents[2] / HARNESS_TEMPLATE
    if tpl.is_file():
        path.write_text(_read_text(tpl), encoding="utf-8")
        return path
    path.write_text(
        "\n".join(
            [
                'version: "1"',
                "project: unknown",
                "roles:",
                "  command:",
                "    label: Command surface",
                "  control:",
                "    label: Control agent",
                "  implementation:",
                "    label: Implementation agent",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _update_roles_in_yaml(text: str, bindings: Mapping[str, Mapping[str, Any]]) -> str:
    lines = text.splitlines()
    role_indent: dict[str, int] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)roles:\s*$", lines[i])
        if m:
            base = len(m.group(1))
            i += 1
            while i < len(lines):
                rm = re.match(r"^(\s*)([\w-]+):\s*$", lines[i])
                if rm and len(rm.group(1)) == base + 2 and rm.group(2) in ROLES:
                    role = rm.group(2)
                    role_indent[role] = len(rm.group(1))
                    i += 1
                    while i < len(lines) and (
                        not lines[i].strip()
                        or lines[i].lstrip().startswith("#")
                        or len(re.match(r"^(\s*)", lines[i]).group(1)) > role_indent[role]
                    ):
                        i += 1
                    continue
                if rm and len(rm.group(1)) <= base:
                    break
                i += 1
            break
        i += 1

    managed_keys = (
        "adapter",
        "fallback",
        "model",
        "command",
        "agent_id",
        "session_key",
        "session_transport",
        "session_binding_version",
    )

    if not role_indent:
        # Append roles section
        appendix = ["", "roles:"]
        for role in ROLES:
            appendix.append(f"  {role}:")
            appendix.append(f"    label: {ROLE_LABELS[role]}")
            b = bindings.get(role) or {}
            for key in managed_keys:
                if b.get(key):
                    appendix.append(f"    {key}: {b[key]}")
        if text and not text.endswith("\n"):
            text += "\n"
        return text + "\n".join(appendix) + "\n"

    # Insert adapter/fallback/model/session fields after each role header
    out: list[str] = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        rm = re.match(r"^(\s*)(command|control|implementation):\s*$", lines[i])
        if rm:
            role = rm.group(2)
            indent = len(rm.group(1))
            child = indent + 2
            # META-022: only rewrite roles present in bindings; leave others intact.
            if role not in bindings:
                j = i + 1
                while j < len(lines):
                    if not lines[j].strip() or lines[j].lstrip().startswith("#"):
                        j += 1
                        continue
                    cur_indent = len(re.match(r"^(\s*)", lines[j]).group(1))
                    if cur_indent <= indent:
                        break
                    j += 1
                out.extend(lines[i + 1 : j])
                i = j
                continue
            b = bindings.get(role) or {}
            # Skip existing managed key lines
            j = i + 1
            kept: list[str] = []
            while j < len(lines):
                if not lines[j].strip() or lines[j].lstrip().startswith("#"):
                    kept.append(lines[j])
                    j += 1
                    continue
                cur_indent = len(re.match(r"^(\s*)", lines[j]).group(1))
                if cur_indent <= indent:
                    break
                km = re.match(
                    r"^(\s*)(" + "|".join(managed_keys) + r"):\s*",
                    lines[j],
                )
                if km and cur_indent == child:
                    j += 1
                    continue
                kept.append(lines[j])
                j += 1
            inserts: list[str] = []
            for key in managed_keys:
                if b.get(key):
                    inserts.append(f"{' ' * child}{key}: {b[key]}")
            out.extend(inserts)
            out.extend(kept)
            i = j
            continue
        i += 1
    return "\n".join(out) + ("\n" if out and not out[-1].endswith("\n") else "")


def bind_roles(
    repo: Path | str | None,
    *,
    command: str | None = None,
    control: str | None = None,
    implementation: str | None = None,
    control_model: str | None = None,
    implementation_model: str | None = None,
    control_fallback: str | None = None,
    implementation_fallback: str | None = None,
    command_fallback: str | None = None,
    force: bool = False,
    no_provision: bool = False,
    rebind_openclaw_session: bool = False,
) -> dict[str, Any]:
    root = _repo_root(repo)
    bindings: dict[str, dict[str, Any]] = {}
    provided = {
        "command": command,
        "control": control,
        "implementation": implementation,
    }
    missing = [r for r, v in provided.items() if not str(v or "").strip()]
    if missing and not force:
        raise SystemExit(f"missing role adapters: {', '.join(missing)} (use --force to partial-bind)")

    fallbacks = {
        "command": command_fallback,
        "control": control_fallback,
        "implementation": implementation_fallback,
    }
    for role, adapter in provided.items():
        if not str(adapter or "").strip():
            continue
        entry: dict[str, Any] = {"adapter": _normalize_adapter(adapter)}
        if role == "control" and control_model:
            entry["model"] = control_model
        if role == "implementation" and implementation_model:
            entry["model"] = implementation_model
        fb = fallbacks.get(role)
        if fb:
            entry["fallback"] = _normalize_adapter(fb)
        bindings[role] = entry

    path = _ensure_workflow_file(root)
    updated = _update_roles_in_yaml(_read_text(path), bindings)
    path.write_text(updated, encoding="utf-8")

    openclaw_session: dict[str, Any] | None = None
    control_adapter = _normalize_adapter(
        str((bindings.get("control") or {}).get("adapter") or role_config(root, "control")["adapter"] or "")
    )
    if control_adapter == "openclaw":
        openclaw_session = provision_openclaw_project_agent(
            root,
            force_rebind=rebind_openclaw_session,
            no_provision=no_provision,
        )
        if not openclaw_session.get("ok") and not no_provision:
            raise SystemExit(
                openclaw_session.get("error")
                or ",".join(openclaw_session.get("blockers") or ["openclaw_provision_failed"])
            )

    return {
        "path": str(path.relative_to(root)),
        "bindings": bindings,
        "roles_sha": roles_sha(root),
        "roles_bound": roles_bound(root),
        "status": status_report(root),
        "openclaw_session": openclaw_session,
    }


def apply_roles_blockers(blockers: list[str]) -> list[str]:
    """Append roles_unbound blockers if needed (mutates and returns list)."""
    ok, role_blockers = check_roles_for_dispatch(None)
    if not ok:
        for item in role_blockers:
            if item not in blockers:
                blockers.append(item)
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NDF role adapter binding")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--repo", type=Path, default=Path.cwd())
        p.add_argument("--json", action="store_true")

    bind_p = sub.add_parser("bind")
    bind_p.add_argument("--repo", type=Path, default=Path.cwd())
    bind_p.add_argument("--command", dest="command_adapter", default=None)
    bind_p.add_argument("--control", default=None)
    bind_p.add_argument("--implementation", default=None)
    bind_p.add_argument("--control-model", default=None)
    bind_p.add_argument("--implementation-model", default=None)
    bind_p.add_argument("--command-fallback", default=None)
    bind_p.add_argument("--control-fallback", default=None)
    bind_p.add_argument("--implementation-fallback", default=None)
    bind_p.add_argument("--force", action="store_true")
    bind_p.add_argument(
        "--no-provision",
        action="store_true",
        help="Skip OpenClaw agent provision (offline); session binding not written",
    )
    bind_p.add_argument(
        "--rebind-openclaw-session",
        action="store_true",
        help="Replace custom/legacy OpenClaw session with managed per-project agent",
    )
    bind_p.add_argument("--json", action="store_true")

    provision_p = sub.add_parser(
        "provision-openclaw-session",
        help="Provision/validate per-project OpenClaw agent + session binding",
    )
    provision_p.add_argument("--repo", type=Path, default=Path.cwd())
    provision_p.add_argument("--rebind", action="store_true")
    provision_p.add_argument("--no-provision", action="store_true")
    provision_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    repo = args.repo

    if args.command == "status":
        payload = status_report(repo)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"roles_bound: {payload['roles_bound']}")
            print(f"roles_sha:   {payload['roles_sha']}")
            for role, info in payload["roles"].items():
                print(f"  {role}: adapter={info['adapter']} provider={info['provider']} available={info['available']}")
            oc = payload.get("openclaw_session") or {}
            print(
                f"openclaw: ownership={oc.get('ownership')} "
                f"agent={oc.get('agent_id')} key={oc.get('session_key')} "
                f"multi_project_safe={oc.get('multi_project_safe')}"
            )
        return 0 if payload["roles_bound"] else 1

    if args.command == "probe":
        payload = probe_adapters(repo)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("CLI:", payload["cli"])
            print("recommended:", payload["recommended_adapters"])
        return 0

    if args.command == "provision-openclaw-session":
        payload = provision_openclaw_project_agent(
            repo,
            force_rebind=args.rebind,
            no_provision=args.no_provision,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"ok: {payload.get('ok')}")
            print(f"error: {payload.get('error')}")
            binding = payload.get("binding") or {}
            print(f"agent_id: {binding.get('agent_id')}")
            print(f"session_key: {binding.get('session_key')}")
        return 0 if payload.get("ok") else 2

    if args.command == "bind":
        try:
            payload = bind_roles(
                repo,
                command=args.command_adapter,
                control=args.control,
                implementation=args.implementation,
                control_model=args.control_model,
                implementation_model=args.implementation_model,
                command_fallback=args.command_fallback,
                control_fallback=args.control_fallback,
                implementation_fallback=args.implementation_fallback,
                force=args.force,
                no_provision=args.no_provision,
                rebind_openclaw_session=args.rebind_openclaw_session,
            )
        except SystemExit as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Updated {payload['path']}")
            print(f"roles_sha: {payload['roles_sha']}")
            print(f"roles_bound: {payload['roles_bound']}")
            for role in ROLES:
                info = payload["status"]["roles"][role]
                print(f"  {role}: {info['adapter']} → {info['provider']}")
            oc = payload.get("openclaw_session")
            if oc:
                print(
                    f"openclaw_session: ok={oc.get('ok')} "
                    f"agent={(oc.get('binding') or {}).get('agent_id')} "
                    f"error={oc.get('error')}"
                )
        return 0 if payload["roles_bound"] else (0 if args.force else 2)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
