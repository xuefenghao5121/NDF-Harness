#!/usr/bin/env python3
"""NDF Harness installer — stdlib only.

CLI:
  python3 install.py plan|install|adopt|verify [--repo PATH] [--profile ...] [--runtime ...] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

PKG_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PKG_ROOT / "VERSION"

VALID_PROFILES = ("dual-track", "minimal", "linter-only")
VALID_RUNTIMES = ("cursor", "openclaw", "claude-code", "opencode", "generic")
DEFAULT_RUNTIMES = ("generic",)

# Harness → target layout
META_MD_PROTECTED = True  # never overwrite spec/meta/*.md without --force
AGENTS_PROTECTED = True  # never overwrite AGENTS.md without --force

DEFAULT_SLIM_NORM_REL_PATHS = (
    "meta/README.md",
    "meta/language.md",
    "meta/process.md",
    "meta/glossary.md",
    "meta/architecture.md",
    "meta/constraints.md",
    "CLAUSE-FORMAT.md",
)

FULL_TOOL_SCRIPTS = (
    "ndf_index.py",
    "ndf_graphcheck.py",
    "ndf_bindcheck.py",
    "ndf_advise.py",
    "ndf_advise_bind.py",
    "ndf_close.py",
    "ndf_poc_isolation.py",
    "ndf_perf_baseline.py",
    "ndf_report_io.py",
    "ndf_gate_slices.py",
    "ndf_context.py",
    "ndf_workflow_evidence.py",
    "ndf_poc_dispatch.py",
    "ndf_workflow_status.py",
    "ndf_dispatch_send.py",
    "ndf_acp_session_bootstrap.py",
    "ndf_replay.py",
)

MINIMAL_TOOL_SCRIPTS = ("ndf_index.py", "ndf_graphcheck.py")

TOOL_DOCS = ("GOVERNANCE.md", "README.md", "VENDOR.md")

SMOKE_TOOLS = (
    "ndf_index.py",
    "ndf_graphcheck.py",
    "ndf_bindcheck.py",
    "ndf_close.py",
    "ndf_gate_slices.py",
    "ndf_context.py",
    "ndf_poc_dispatch.py",
    "ndf_workflow_status.py",
)

RUNTIME_SKILL_DIRS: dict[str, str | None] = {
    "cursor": ".cursor/skills/ndf-workflow",
    "openclaw": "skills/ndf-harness",
    "claude-code": ".claude/skills/ndf-harness",
    "opencode": ".opencode/skills/ndf-harness",
    "generic": None,
}

RUNTIME_EXTRA_FILES: dict[str, list[tuple[str, str]]] = {
    "claude-code": [
        ("templates/implementer-boundaries.md", ".claude/CLAUDE.md"),
    ],
    "openclaw": [
        ("templates/openclaw/state.json.example", "spec/meta/templates/openclaw/state.json.example"),
    ],
}


@dataclass
class PlanItem:
    action: str  # create | update | skip | conflict
    category: str
    src: str | None
    dst: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstallPlan:
    repo: str
    profile: str
    runtimes: list[str]
    force: bool
    mode: str
    harness_version: str
    items: list[PlanItem] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.action] = counts.get(item.action, 0) + 1
        return {
            "repo": self.repo,
            "profile": self.profile,
            "runtimes": self.runtimes,
            "force": self.force,
            "mode": self.mode,
            "harness_version": self.harness_version,
            "counts": counts,
            "items": [i.to_dict() for i in self.items],
        }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_profile_config() -> dict[str, Any]:
    """Minimal YAML loader for ndf.profile.yaml (no PyYAML)."""
    path = PKG_ROOT / "ndf.profile.yaml"
    if not path.is_file():
        return _default_profile_config()
    text = _read_text(path)
    return _parse_simple_yaml(text)


def _default_profile_config() -> dict[str, Any]:
    return {
        "default_profile": "dual-track",
        "profiles": {
            "dual-track": {
                "requires_poc": True,
                "requires_agents_md": True,
                "install_norms": "full",
                "install_tools": "full",
            },
            "minimal": {
                "requires_poc": False,
                "requires_agents_md": True,
                "install_norms": "slim",
                "install_tools": ["index", "graphcheck"],
            },
            "linter-only": {
                "requires_poc": False,
                "requires_agents_md": False,
                "install_norms": False,
                "install_tools": "full",
            },
        },
        "runtimes": list(VALID_RUNTIMES),
    }


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
                # peek next non-comment line to decide dict vs list
                node: Any
                lines = text.splitlines()
                idx = text.splitlines().index(raw)
                nxt = ""
                for follow in lines[idx + 1 :]:
                    if follow.strip() and not follow.lstrip().startswith("#"):
                        nxt = follow
                        break
                if list_re.match(nxt or ""):
                    node = []
                else:
                    node = {}
                parent[key] = node
                stack.append((indent, node))
            elif rest.startswith("[") and rest.endswith("]"):
                inner = rest[1:-1].strip()
                parent[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
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


def _profile_spec(cfg: dict[str, Any], profile: str) -> dict[str, Any]:
    profiles = cfg.get("profiles") or {}
    if profile not in profiles:
        raise SystemExit(f"unknown profile {profile!r}; choose from {', '.join(VALID_PROFILES)}")
    return profiles[profile]


def _tool_scripts_for_profile(spec: dict[str, Any]) -> tuple[str, ...]:
    tools = spec.get("install_tools", "full")
    if tools == "full":
        out = list(FULL_TOOL_SCRIPTS)
    elif tools == "slim":
        out = list(MINIMAL_TOOL_SCRIPTS)
    elif isinstance(tools, list):
        mapping = {
            "index": "ndf_index.py",
            "graphcheck": "ndf_graphcheck.py",
            "bindcheck": "ndf_bindcheck.py",
            "advise": "ndf_advise.py",
            "close": "ndf_close.py",
            "isolation": "ndf_poc_isolation.py",
            "perf_baseline": "ndf_perf_baseline.py",
        }
        out = []
        for t in tools:
            if t in mapping:
                out.append(mapping[t])
            elif t.endswith(".py"):
                out.append(t)
        if not out:
            out = list(MINIMAL_TOOL_SCRIPTS)
    else:
        out = list(MINIMAL_TOOL_SCRIPTS)
    # Shared helper imported by most entrypoints
    if out and "ndf_report_io.py" not in out:
        out.append("ndf_report_io.py")
    return tuple(dict.fromkeys(out))


def _norm_mode(spec: dict[str, Any]) -> str | bool:
    return spec.get("install_norms", "full")


def _should_install(path: Path, force: bool, protected_md: bool = False) -> tuple[str, str]:
    if not path.exists():
        return "create", "missing"
    if force:
        return "update", "force"
    if protected_md and path.suffix == ".md":
        return "skip", "existing_md_protected"
    if protected_md and path.name == "AGENTS.md":
        return "skip", "existing_agents_protected"
    return "skip", "exists"


def _add_copy(
    plan: InstallPlan,
    *,
    category: str,
    src: Path,
    dst: Path,
    protected_md: bool = False,
    adopt_only: bool = False,
) -> None:
    rel_dst = str(dst)
    if adopt_only and dst.exists():
        return
    action, reason = _should_install(dst, plan.force, protected_md)
    if action == "skip" and src.is_file() and dst.is_file():
        try:
            if _sha256(src) == _sha256(dst):
                reason = "identical"
        except OSError:
            pass
    plan.items.append(
        PlanItem(
            action=action,
            category=category,
            src=str(src.relative_to(PKG_ROOT)) if src.is_relative_to(PKG_ROOT) else str(src),
            dst=rel_dst,
            reason=reason,
        )
    )


def _slim_norm_paths(cfg: dict[str, Any]) -> tuple[str, ...]:
    raw = cfg.get("slim_norms_files")
    if isinstance(raw, list) and raw:
        return tuple(str(x) for x in raw)
    return DEFAULT_SLIM_NORM_REL_PATHS


def _iter_norm_files(mode: str | bool, cfg: dict[str, Any]) -> Iterable[tuple[Path, Path]]:
    norms = PKG_ROOT / "norms"
    if not mode:
        return
    if mode == "slim":
        for rel in _slim_norm_paths(cfg):
            src = norms / rel
            if not src.is_file():
                continue
            if rel == "CLAUSE-FORMAT.md":
                yield src, Path("spec/meta/CLAUSE-FORMAT.md")
            else:
                yield src, Path("spec") / rel
        return
    # full
    for src in sorted(norms.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(norms)
        if rel.parts[0] == "product-tree":
            yield src, Path("spec") / Path(*rel.parts[1:])
        elif rel.name == "ndf.yaml.stub":
            yield src, Path("spec/ndf.yaml")
        elif rel.name == "README.md" and rel.parent == Path("."):
            yield src, Path("spec/README.md")
        elif rel.name == "CLAUSE-FORMAT.md":
            yield src, Path("spec/meta/CLAUSE-FORMAT.md")
        elif rel.parts[0] == "meta":
            yield src, Path("spec") / rel
        # skip ndf.yaml.stub handled above; skip duplicate README at norms root if needed


def _iter_template_files() -> Iterable[tuple[Path, Path]]:
    templates = PKG_ROOT / "templates"
    if not templates.is_dir():
        return
    for src in sorted(templates.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(templates)
        yield src, Path("spec/meta/templates") / rel


def _iter_skill_files() -> Iterable[tuple[Path, Path]]:
    """Yield (src, rel) for the canonical ndf-workflow skill tree.

    Installs ``skill/ndf-workflow/*`` flat into the runtime skill directory
    (e.g. ``.cursor/skills/ndf-workflow/SKILL.md``), not a nested
    ``…/ndf-workflow/ndf-workflow/`` path. The thin root ``skill/SKILL.md``
    pointer is not installed into consumer skill dirs.
    """
    skill = PKG_ROOT / "skill" / "ndf-workflow"
    if not skill.is_dir():
        return
    for src in sorted(skill.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(skill)
        yield src, rel


def build_plan(
    repo: Path,
    profile: str,
    runtimes: Sequence[str],
    force: bool,
    mode: str,
) -> InstallPlan:
    cfg = load_profile_config()
    pspec = _profile_spec(cfg, profile)
    version = _read_text(VERSION_FILE).strip() if VERSION_FILE.is_file() else "unknown"
    plan = InstallPlan(
        repo=str(repo.resolve()),
        profile=profile,
        runtimes=list(runtimes),
        force=force,
        mode=mode,
        harness_version=version,
    )
    adopt_only = mode == "adopt"
    norm_mode = _norm_mode(pspec)

    # norms → spec/
    for src, rel_dst in _iter_norm_files(norm_mode, cfg):
        _add_copy(plan, category="norms", src=src, dst=repo / rel_dst, protected_md=META_MD_PROTECTED, adopt_only=adopt_only)

    # tools → spec/meta/tools/
    tool_scripts = _tool_scripts_for_profile(pspec)
    tools_src = PKG_ROOT / "governance" / "tools"
    for name in tool_scripts:
        src = tools_src / name
        if src.is_file():
            _add_copy(plan, category="tools", src=src, dst=repo / "spec/meta/tools" / name, adopt_only=adopt_only)
    for doc in TOOL_DOCS:
        src = tools_src / doc
        if src.is_file() and tool_scripts:
            _add_copy(plan, category="tools", src=src, dst=repo / "spec/meta/tools" / doc, protected_md=True, adopt_only=adopt_only)

    # AGENTS.md
    if pspec.get("requires_agents_md", True) or profile != "linter-only":
        agents_src = PKG_ROOT / "workflow" / "AGENTS.md"
        agents_dst = repo / "AGENTS.md"
        if agents_src.is_file():
            action, reason = _should_install(agents_dst, force, AGENTS_PROTECTED)
            if adopt_only and agents_dst.exists():
                pass
            else:
                plan.items.append(
                    PlanItem(
                        action=action,
                        category="workflow",
                        src=str(agents_src.relative_to(PKG_ROOT)),
                        dst=str(agents_dst),
                        reason=reason,
                    )
                )

    # ndf.workflow.yaml
    wf_src = PKG_ROOT / "workflow" / "ndf.workflow.yaml"
    wf_dst = repo / "ndf.workflow.yaml"
    if wf_src.is_file():
        _add_copy(plan, category="workflow", src=wf_src, dst=wf_dst, adopt_only=adopt_only)

    # templates → spec/meta/templates/
    for src, rel in _iter_template_files():
        _add_copy(plan, category="templates", src=src, dst=repo / rel, protected_md=False, adopt_only=adopt_only)

    # poc scaffold for dual-track
    if pspec.get("requires_poc") and norm_mode:
        poc_readme = repo / "poc" / "README.md"
        if not adopt_only or not poc_readme.exists():
            plan.items.append(
                PlanItem(
                    action="create" if not poc_readme.exists() else ("update" if force else "skip"),
                    category="poc",
                    src=None,
                    dst=str(poc_readme),
                    reason="dual-track scaffold" if not poc_readme.exists() else "exists",
                )
            )

    # runtime skill adapters
    for runtime in runtimes:
        skill_rel = RUNTIME_SKILL_DIRS.get(runtime)
        if not skill_rel:
            continue
        for src, rel in _iter_skill_files():
            dst = repo / skill_rel / rel
            _add_copy(plan, category=f"skill:{runtime}", src=src, dst=dst, adopt_only=adopt_only)
        for src_rel, dst_rel in RUNTIME_EXTRA_FILES.get(runtime, []):
            src = PKG_ROOT / src_rel
            if src.is_file():
                dst = repo / dst_rel
                prot = dst.name in ("CLAUDE.md", "AGENTS.md") or "meta" in dst.parts
                _add_copy(plan, category=f"adapter:{runtime}", src=src, dst=dst, protected_md=prot, adopt_only=adopt_only)

    # openclaw state template lives under templates/ — ensure path from harness templates if missing
    oclaw_tpl = PKG_ROOT / "templates" / "openclaw" / "state.json.example"
    if "openclaw" in runtimes and oclaw_tpl.is_file():
        dst = repo / "spec/meta/templates/openclaw/state.json.example"
        _add_copy(plan, category="adapter:openclaw", src=oclaw_tpl, dst=dst, adopt_only=adopt_only)

    if adopt_only:
        filtered: list[PlanItem] = []
        for item in plan.items:
            dst = Path(item.dst)
            if not dst.is_absolute():
                dst = repo / dst
            if dst.exists():
                continue
            gap = PlanItem(
                action="create",
                category=item.category,
                src=item.src,
                dst=item.dst,
                reason="gap",
            )
            filtered.append(gap)
        plan.items = filtered

    return plan


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def execute_plan(plan: InstallPlan, *, dry_run: bool = False) -> dict[str, Any]:
    repo = Path(plan.repo)
    results = {"created": 0, "updated": 0, "skipped": 0, "errors": []}

    for item in plan.items:
        if item.action == "skip":
            results["skipped"] += 1
            continue
        if item.action not in ("create", "update"):
            continue
        dst = Path(item.dst)
        if not dst.is_absolute():
            dst = repo / dst
        if item.category == "poc" and item.src is None:
            if dry_run:
                results["created"] += 1
                continue
            _ensure_parent(dst)
            if not dst.exists() or plan.force:
                dst.write_text(_poc_readme_text(), encoding="utf-8")
                results["created" if item.action == "create" else "updated"] += 1
            continue
        if not item.src:
            continue
        src = PKG_ROOT / item.src if not Path(item.src).is_absolute() else Path(item.src)
        if not src.is_file():
            results["errors"].append(f"missing source: {src}")
            continue
        if dry_run:
            results[item.action + "d" if item.action == "update" else "created"] += 1
            continue
        try:
            _ensure_parent(dst)
            shutil.copy2(src, dst)
            if item.action == "create":
                results["created"] += 1
            else:
                results["updated"] += 1
        except OSError as exc:
            results["errors"].append(f"{dst}: {exc}")

    return results


def _poc_readme_text() -> str:
    return """# POC workspace

Exploration topics live at `poc/<topic-id>/` with an `ndf/` binder (`TOPIC.md`, `PERF_BASELINE.md`, …).

- POC MUST NOT modify Trunk `src/`, `include/`, or `tests/` directly.
- Promote only after evidence + `ndf_close plan`.
- See root `AGENTS.md` and `spec/meta/process.md`.
"""


def print_plan(plan: InstallPlan, *, as_json: bool) -> None:
    payload = plan.summary()
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"NDF Harness install plan ({plan.mode})")
    print(f"  repo:     {plan.repo}")
    print(f"  profile:  {plan.profile}")
    print(f"  runtimes: {', '.join(plan.runtimes)}")
    print(f"  version:  {plan.harness_version}")
    print(f"  force:    {plan.force}")
    print()
    by_action: dict[str, list[PlanItem]] = {}
    for item in plan.items:
        by_action.setdefault(item.action, []).append(item)
    for action in ("create", "update", "skip", "conflict"):
        items = by_action.get(action, [])
        if not items:
            continue
        print(f"[{action}] ({len(items)})")
        for it in items:
            src = it.src or "-"
            print(f"  {src} -> {it.dst}  ({it.reason})")
        print()


def cmd_verify(repo: Path, profile: str, runtimes: Sequence[str], *, as_json: bool) -> int:
    cfg = load_profile_config()
    pspec = _profile_spec(cfg, profile)
    failures: list[str] = []
    notes: dict[str, Any] = {"checks": {}, "capabilities": {}}

    # VERSION in package
    if VERSION_FILE.is_file():
        notes["checks"]["harness_version"] = _read_text(VERSION_FILE).strip()
    else:
        failures.append("harness VERSION file missing")

    # AGENTS.md
    agents = repo / "AGENTS.md"
    if pspec.get("requires_agents_md", True):
        if agents.is_file():
            notes["checks"]["agents_md"] = "present"
        else:
            failures.append("AGENTS.md missing (required by profile)")
    else:
        notes["checks"]["agents_md"] = "present" if agents.is_file() else "optional_missing"

    # ndf.workflow.yaml
    wf = repo / "ndf.workflow.yaml"
    if pspec.get("requires_workflow_yaml", True):
        if wf.is_file():
            notes["checks"]["ndf_workflow_yaml"] = "present"
        else:
            failures.append("ndf.workflow.yaml missing")
    else:
        notes["checks"]["ndf_workflow_yaml"] = "present" if wf.is_file() else "optional_missing"

    # tools smoke (only installed scripts)
    tools_dir = repo / "spec/meta/tools"
    expected_tools = set(_tool_scripts_for_profile(pspec))
    smoke_results: dict[str, str] = {}
    for script in sorted(expected_tools):
        path = tools_dir / script
        if not path.is_file():
            failures.append(f"tool missing: {path}")
            smoke_results[script] = "missing"
            continue
        if script not in SMOKE_TOOLS:
            smoke_results[script] = "skipped"
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(path), "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(repo),
            )
            smoke_results[script] = "ok" if proc.returncode == 0 else f"exit_{proc.returncode}"
            if proc.returncode != 0:
                failures.append(f"{script} --help failed (exit {proc.returncode})")
        except (OSError, subprocess.TimeoutExpired) as exc:
            smoke_results[script] = f"error:{exc}"
            failures.append(f"{script} --help error: {exc}")
    notes["checks"]["tools_smoke"] = smoke_results

    # skill entry per runtime
    for runtime in runtimes:
        skill_rel = RUNTIME_SKILL_DIRS.get(runtime)
        if not skill_rel:
            notes["checks"][f"skill_{runtime}"] = "n/a"
            continue
        skill_md = repo / skill_rel / "SKILL.md"
        if skill_md.is_file():
            notes["checks"][f"skill_{runtime}"] = str(skill_md)
        else:
            notes["checks"][f"skill_{runtime}"] = "missing"
            if runtime != "generic":
                failures.append(f"skill entry missing for runtime {runtime}: {skill_md}")

    # external CLI capabilities
    for cli, label in (("openclaw", "openclaw"), ("claude", "claude-code")):
        found = shutil.which(cli)
        notes["capabilities"][label] = "available" if found else "unsupported"

    notes["ok"] = not failures
    notes["failures"] = failures
    if as_json:
        print(json.dumps(notes, indent=2, ensure_ascii=False))
    else:
        print("NDF Harness verify")
        print(f"  repo:    {repo}")
        print(f"  profile: {profile}")
        print(f"  ok:      {not failures}")
        for k, v in notes["checks"].items():
            print(f"  check {k}: {v}")
        for k, v in notes["capabilities"].items():
            print(f"  capability {k}: {v}")
        if failures:
            print("\nFailures:")
            for f in failures:
                print(f"  - {f}")

    return 0 if not failures else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    cfg = load_profile_config()
    default_profile = cfg.get("default_profile", "dual-track")
    parser = argparse.ArgumentParser(description="NDF Harness installer (stdlib only)")
    parser.add_argument("command", choices=["plan", "install", "adopt", "verify"])
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="target repository root")
    parser.add_argument("--profile", choices=VALID_PROFILES, default=default_profile)
    parser.add_argument(
        "--runtime",
        dest="runtimes",
        action="append",
        default=None,
        help=(
            "runtime adapter (repeatable or comma-separated). "
            f"choices: {', '.join(VALID_RUNTIMES)}"
        ),
    )
    parser.add_argument("--force", action="store_true", help="overwrite protected files")
    parser.add_argument("--json", action="store_true", help="JSON output for plan/adopt")
    return parser.parse_args(argv)


def _expand_runtimes(raw: Sequence[str] | None) -> list[str]:
    if not raw:
        return list(DEFAULT_RUNTIMES)
    out: list[str] = []
    for item in raw:
        for part in str(item).split(","):
            name = part.strip()
            if not name:
                continue
            if name not in VALID_RUNTIMES:
                raise SystemExit(f"unknown runtime {name!r}")
            if name not in out:
                out.append(name)
    return out or list(DEFAULT_RUNTIMES)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runtimes = _expand_runtimes(args.runtimes)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"error: repo not found: {repo}", file=sys.stderr)
        return 1

    if args.command == "verify":
        return cmd_verify(repo, args.profile, runtimes, as_json=args.json)

    mode = args.command if args.command != "install" else "install"
    if args.command == "adopt":
        mode = "adopt"
    plan = build_plan(repo, args.profile, runtimes, args.force, mode)

    if args.command == "plan":
        print_plan(plan, as_json=args.json)
        return 0

    if args.command == "adopt":
        print_plan(plan, as_json=args.json)
        return 0

    results = execute_plan(plan)
    print(json.dumps({"status": "installed", "results": results, "plan_counts": plan.summary()["counts"]}, indent=2))
    if results["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
