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
    "spec/meta/open/",
    "poc/*/ndf/",
    ".openclaw/state.json",
]
GENESIS_GATES = Path("spec/open/project-genesis/GATES.md")
ROLES_GATE_PHRASE = "角色已配置"
HARNESS_TEMPLATE = Path("packages/ndf-harness/workflow/ndf.workflow.yaml")


def _repo_root(repo: Path | str | None = None) -> Path:
    if repo is None:
        return Path(__file__).resolve().parents[2]
    return Path(repo).resolve()


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
    return {
        "adapter": adapter,
        "fallback": fallback,
        "model": model,
        "command": custom_command or None,
        "writable": list(block.get("writable") or []) if role == "control" else [],
        "raw": dict(block),
    }


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
    if roles_bound(repo):
        return True, []
    blockers = ["roles_unbound"]
    root = _repo_root(repo)
    missing = [r for r in ROLES if not role_config(root, r)["adapter"]]
    if missing:
        blockers.append(f"roles_missing_adapter:{','.join(missing)}")
    if _project_maturity(root) not in {"operational", "operational_legacy"}:
        if not _genesis_roles_gate_valid(root):
            blockers.append("roles_gate_missing:角色已配置")
    return False, blockers


def resolve_pack_provider(
    repo: Path | str | None,
    pack: Mapping[str, Any],
) -> dict[str, Any]:
    """Map pack provider → role resolution (may override transport provider)."""
    provider = str(pack.get("provider") or "")
    role = PACK_PROVIDER_ROLE.get(provider)
    if role is None:
        task = str(pack.get("task") or "")
        if task.startswith("poc_") or task in {"implement", "poc_measurement", "prepare_acp_lease"}:
            role = "implementation"
        elif provider == "openclaw" or "control" in task or "proposal" in task:
            role = "control"
        else:
            role = "implementation" if "poc" in str(pack.get("track") or "") else "control"
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
    return {
        "workflow_yaml": str(wf_path.relative_to(root)) if wf_path.is_file() else None,
        "roles_bound": roles_bound(root),
        "roles_sha": roles_sha(root),
        "project_maturity": maturity,
        "genesis_roles_gate": _genesis_roles_gate_valid(root),
        "roles": {role: resolve_role(root, role) for role in ROLES},
        "normalized_roles": _normalized_roles_block(root),
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

    if not role_indent:
        # Append roles section
        appendix = ["", "roles:"]
        for role in ROLES:
            appendix.append(f"  {role}:")
            appendix.append(f"    label: {ROLE_LABELS[role]}")
            b = bindings.get(role) or {}
            if b.get("adapter"):
                appendix.append(f"    adapter: {b['adapter']}")
            if b.get("fallback"):
                appendix.append(f"    fallback: {b['fallback']}")
            if b.get("model"):
                appendix.append(f"    model: {b['model']}")
        if text and not text.endswith("\n"):
            text += "\n"
        return text + "\n".join(appendix) + "\n"

    # Insert adapter/fallback/model after each role header
    out: list[str] = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        rm = re.match(r"^(\s*)(command|control|implementation):\s*$", lines[i])
        if rm:
            role = rm.group(2)
            indent = len(rm.group(1))
            child = indent + 2
            b = bindings.get(role) or {}
            # Skip existing adapter/fallback/model/command lines
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
                km = re.match(r"^(\s*)(adapter|fallback|model|command):\s*", lines[j])
                if km and cur_indent == child:
                    j += 1
                    continue
                kept.append(lines[j])
                j += 1
            inserts: list[str] = []
            if b.get("adapter"):
                inserts.append(f"{' ' * child}adapter: {b['adapter']}")
            if b.get("fallback"):
                inserts.append(f"{' ' * child}fallback: {b['fallback']}")
            if b.get("model"):
                inserts.append(f"{' ' * child}model: {b['model']}")
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
    return {
        "path": str(path.relative_to(root)),
        "bindings": bindings,
        "roles_sha": roles_sha(root),
        "roles_bound": roles_bound(root),
        "status": status_report(root),
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
    bind_p.add_argument("--json", action="store_true")

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
        return 0 if payload["roles_bound"] else 1

    if args.command == "probe":
        payload = probe_adapters(repo)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("CLI:", payload["cli"])
            print("recommended:", payload["recommended_adapters"])
        return 0

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
        return 0 if payload["roles_bound"] else (0 if args.force else 2)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
