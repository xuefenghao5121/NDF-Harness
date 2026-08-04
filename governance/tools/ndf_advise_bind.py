#!/usr/bin/env python3
"""NDF bind-surface advisor (v2) — surgical options over ndf_bindcheck findings.

Never writes TOPIC/COMMITS/git. Sandbox mutates in-memory binder texts only.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import ndf_bindcheck as bc  # noqa: E402
import ndf_close as ncl  # noqa: E402
import ndf_index as ndx  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
TOOL = "spec/meta/tools/ndf_advise.py"

# bind finding kind priority (lower = first)
BIND_KIND_PRIORITY = {
    "draft_vs_stable": 0,
    "stable_claim_vs_draft": 0,
    "orphan_draft_id": 1,
    "trunk_topic_unlisted": 1,
    "missing_ledger": 2,
    "missing_binder": 2,
    "bad_ledger_sha": 2,
    "missing_trailer": 3,
    "clause_unbound": 4,
    "coarse_protocol": 5,
    "crowded_clauses": 5,
    "missing_path": 6,
    "timeline_unbind": 7,
}

CONF_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class BindPatch:
    op: str
    topic: str = ""
    sha: str = ""
    clauses: str = ""
    protocol: str = ""
    note: str = ""
    clause_id: str = ""
    path: str = ""
    path_new: str = ""
    banner: str = ""
    trailer_block: str = ""

    def to_dict(self) -> dict:
        d = {"op": self.op}
        for k in (
            "topic",
            "sha",
            "clauses",
            "protocol",
            "note",
            "clause_id",
            "path",
            "path_new",
            "banner",
            "trailer_block",
        ):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d


@dataclass
class BindOption:
    opt_id: str
    title: str
    confidence: str
    impact_delta: dict
    patch: BindPatch
    rationale: str = ""
    manual_steps: list[str] = field(default_factory=list)


@dataclass
class BindAdvised:
    issue_id: str
    finding: bc.Finding
    options: list[BindOption] = field(default_factory=list)


@dataclass
class BinderSandbox:
    topic: str
    topic_text: str
    ledger_text: str
    trailer_templates: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def impact_for_finding(f: bc.Finding) -> dict:
    return {
        "topic": f.topic,
        "kind": f.kind,
        "severity": f.severity,
        "evidence_lines": len(f.evidence),
        "reachable_within_hops": 1 if f.severity == "error" else 0,
    }


def extract_sha(f: bc.Finding) -> str:
    m = re.search(r"\b([0-9a-f]{7,40})\b", f.message)
    if m:
        return m.group(1)
    for e in f.evidence:
        m = re.search(r"`([0-9a-f]{7,40})`", e)
        if m:
            return m.group(1)
        m = re.search(r"\b([0-9a-f]{7,40})\b", e)
        if m:
            return m.group(1)
    return ""


def extract_clause_id(f: bc.Finding) -> str:
    m = re.search(r"\b((?:BEH|API|CON|CHR|ARCH|VER|DEF|DEC)-\d+[A-Z0-9-]*)\b", f.message)
    return m.group(1) if m else ""


def renumber(opts: list[BindOption]) -> list[BindOption]:
    opts = sorted(
        opts,
        key=lambda o: (
            CONF_RANK.get(o.confidence, 9),
            o.impact_delta.get("reachable_within_hops", 99),
            o.title,
        ),
    )
    for i, o in enumerate(opts, 1):
        o.opt_id = f"O{i}"
    return opts


def options_for_finding(f: bc.Finding) -> list[BindOption]:
    opts: list[BindOption] = []
    impact = impact_for_finding(f)
    topic = f.topic
    sha = extract_sha(f)
    cid = extract_clause_id(f)

    if f.kind in ("draft_vs_stable", "stable_claim_vs_draft"):
        opts.append(
            BindOption(
                "Ox",
                f"Update TOPIC draft table: mark {cid or 'clause'} as promoted/stable",
                "high",
                impact,
                BindPatch(
                    "update_topic_draft_table",
                    topic=topic,
                    clause_id=cid,
                    note="status=stable (promoted)",
                ),
                rationale="Binder dual-head: Trunk already stable; TOPIC must stop claiming draft.",
                manual_steps=[
                    f"Edit poc/{topic}/ndf/TOPIC.md Draft clauses row for {cid}",
                    "Replace `status=draft` with promoted/stable note or move to Promoted section",
                    "Re-run ndf_bindcheck",
                ],
            )
        )
        opts.append(
            BindOption(
                "Ox",
                f"Close topic status if exploration finished (manual)",
                "medium",
                impact,
                BindPatch(
                    "update_topic_draft_table",
                    topic=topic,
                    clause_id=cid,
                    note="topic_status→partial/promoted",
                ),
                rationale="May also update `> status:` line when R5b etc. are done.",
            )
        )

    elif f.kind == "missing_trailer":
        short = sha[:7] if sha else "?"
        trailer = f"Topic: {topic}\nClauses: <IDs>\n"
        opts.append(
            BindOption(
                "Ox",
                f"Append COMMITS.md row documenting {short} (historical / no rewrite)",
                "high",
                impact,
                BindPatch(
                    "append_ledger_row",
                    topic=topic,
                    sha=sha or short,
                    clauses="(see note)",
                    protocol="(n/a)",
                    note=f"historical code commit {short}; trailers absent; not rewritten",
                ),
                rationale="Ledger SoT records the gap without rewriting git history.",
                manual_steps=[
                    f"Append row to poc/{topic}/ndf/COMMITS.md",
                    "Prefer --since on future bindcheck to shrink window",
                ],
            )
        )
        opts.append(
            BindOption(
                "Ox",
                f"Emit trailer template for {short} (does not amend git)",
                "medium",
                impact,
                BindPatch(
                    "add_trailers_template",
                    topic=topic,
                    sha=sha or short,
                    trailer_block=trailer,
                ),
                rationale="Template for new commits; amending pushed history is out of scope.",
                manual_steps=[
                    "Use template on *future* commits under this topic",
                    "Do not force-push amend unless policy allows",
                ],
            )
        )
        opts.append(
            BindOption(
                "Ox",
                "Ensure COMMITS.md has historical not-backfilled banner",
                "high",
                impact,
                BindPatch(
                    "add_not_backfilled_banner",
                    topic=topic,
                    banner=(
                        "> Historical commits before binder adoption are not backfilled."
                    ),
                ),
                rationale="Exempts clause_unbound warnings; documents trailer history debt.",
            )
        )

    elif f.kind == "clause_unbound":
        opts.append(
            BindOption(
                "Ox",
                f"Append ledger row binding {cid}",
                "high",
                impact,
                BindPatch(
                    "append_ledger_row",
                    topic=topic,
                    sha="-",
                    clauses=cid,
                    protocol="(fill)",
                    note=f"backfill bind for {cid}",
                ),
                rationale="Promote notes exist but clauses column never listed the ID.",
            )
        )
        opts.append(
            BindOption(
                "Ox",
                "Add not-backfilled banner (if historically expected)",
                "medium",
                impact,
                BindPatch(
                    "add_not_backfilled_banner",
                    topic=topic,
                    banner=(
                        "> Historical commits before binder adoption are not backfilled."
                    ),
                ),
            )
        )

    elif f.kind in ("missing_ledger", "missing_binder"):
        opts.append(
            BindOption(
                "Ox",
                "Create binder stub (manual checklist)",
                "high",
                impact,
                BindPatch(
                    "append_ledger_row",
                    topic=topic,
                    sha="-",
                    clauses="-",
                    protocol="-",
                    note="ledger starts",
                ),
                rationale="BEH-025 requires TOPIC.md + COMMITS.md.",
                manual_steps=[
                    f"Ensure poc/{topic}/ndf/TOPIC.md exists",
                    f"Create poc/{topic}/ndf/COMMITS.md with DEF-023 table header",
                ],
            )
        )

    elif f.kind == "bad_ledger_sha":
        opts.append(
            BindOption(
                "Ox",
                f"Fix or remove bad sha {sha[:7] if sha else '?'} in COMMITS.md",
                "high",
                impact,
                BindPatch(
                    "append_ledger_row",
                    topic=topic,
                    sha=sha,
                    note="REPLACE bad sha row (manual edit)",
                ),
                rationale="Sandbox cannot rewrite arbitrary table cells; edit by hand.",
                manual_steps=["Correct typo in COMMITS.md or delete the row"],
            )
        )

    elif f.kind in ("coarse_protocol", "crowded_clauses"):
        opts.append(
            BindOption(
                "Ox",
                "Lengthen ledger note to disambiguate measurement",
                "high",
                impact,
                BindPatch(
                    "lengthen_ledger_note",
                    topic=topic,
                    note=(
                        "disambiguate: which gate/cgroup/protocol variant this row measured"
                    ),
                ),
                rationale="OBS-GRAIN: notes must answer which SHA/measurement.",
            )
        )

    elif f.kind == "missing_path":
        path = f.loc or ""
        opts.append(
            BindOption(
                "Ox",
                f"Remove or fix stale path cite `{path}`",
                "medium",
                impact,
                BindPatch(
                    "fix_path_cite",
                    topic=topic,
                    path=path,
                    path_new="",
                    note="remove stale path token",
                ),
                rationale="Path-level zombie; pick restore file vs delete cite.",
            )
        )

    elif f.kind == "timeline_unbind":
        opts.append(
            BindOption(
                "Ox",
                f"Append ledger/trailer bind for {cid} in change window",
                "medium",
                impact,
                BindPatch(
                    "append_ledger_row",
                    topic=topic,
                    sha="(window)",
                    clauses=cid,
                    note="bind clause to recent path changes",
                ),
            )
        )

    if not opts:
        opts.append(
            BindOption(
                "Ox",
                "Manual review",
                "low",
                impact,
                BindPatch("add_trailers_template", topic=topic, note="noop"),
                rationale="No high-confidence automated option.",
            )
        )
    return renumber(opts)


def collect_findings(
    topics: list[str] | None,
    by_id: dict[str, ndx.Clause],
    checks: set[str],
    since: str | None,
) -> list[bc.Finding]:
    if not topics:
        topics = bc.list_topics()
    out: list[bc.Finding] = []
    for t in topics:
        tr = bc.run_topic(t, checks, by_id, since)
        out.extend(tr.findings)
    return out


def build_bind_queue(
    by_id: dict[str, ndx.Clause],
    *,
    topic: str | None,
    low_hanging: bool,
    max_issues: int,
    kinds: set[str] | None,
    since: str | None,
    checks: set[str] | None = None,
) -> list[BindAdvised]:
    checks = checks or {"bind", "dual", "grain"}
    topics = [topic] if topic else None
    findings = collect_findings(topics, by_id, checks, since)
    if kinds:
        findings = [f for f in findings if f.kind in kinds]

    findings.sort(
        key=lambda f: (
            BIND_KIND_PRIORITY.get(f.kind, 50),
            0 if f.severity == "error" else 1,
            f.topic,
            f.message,
        )
    )

    counters: dict[str, int] = defaultdict(int)
    queue: list[BindAdvised] = []
    for f in findings:
        prefix = {
            "draft_vs_stable": "dual",
            "stable_claim_vs_draft": "dual",
            "orphan_draft_id": "dual",
            "trunk_topic_unlisted": "dual",
            "missing_trailer": "bind",
            "clause_unbound": "bind",
            "missing_ledger": "bind",
            "missing_binder": "bind",
            "bad_ledger_sha": "bind",
            "coarse_protocol": "grain",
            "crowded_clauses": "grain",
            "missing_path": "zombie",
            "timeline_unbind": "drift",
        }.get(f.kind, f.kind)
        counters[prefix] += 1
        iid = f"{prefix}-{counters[prefix]:03d}"
        opts = options_for_finding(f)
        if low_hanging:
            opts = renumber([o for o in opts if o.confidence == "high"])
            if not opts:
                continue
        queue.append(BindAdvised(issue_id=iid, finding=f, options=opts))
        if len(queue) >= max_issues:
            break
    return queue


def load_sandbox(topic: str) -> BinderSandbox:
    topic_path = ROOT / "poc" / topic / "ndf" / "TOPIC.md"
    ledger_path = ROOT / "poc" / topic / "ndf" / "COMMITS.md"
    topic_text = (
        topic_path.read_text(encoding="utf-8", errors="replace")
        if topic_path.is_file()
        else ""
    )
    ledger_text = (
        ledger_path.read_text(encoding="utf-8", errors="replace")
        if ledger_path.is_file()
        else ""
    )
    return BinderSandbox(topic=topic, topic_text=topic_text, ledger_text=ledger_text)


def apply_bind_patch(sb: BinderSandbox, p: BindPatch) -> None:
    if p.op == "add_not_backfilled_banner":
        banner = p.banner or (
            "> Historical commits before binder adoption are not backfilled."
        )
        if not re.search(r"(?i)not\s+backfilled", sb.ledger_text):
            if sb.ledger_text.startswith("#"):
                lines = sb.ledger_text.splitlines()
                # insert after title
                insert_at = 1
                lines = lines[:insert_at] + ["", banner, ""] + lines[insert_at:]
                sb.ledger_text = "\n".join(lines) + (
                    "" if sb.ledger_text.endswith("\n") else "\n"
                )
            else:
                sb.ledger_text = banner + "\n\n" + sb.ledger_text
            sb.notes.append("inserted not-backfilled banner")
        else:
            sb.notes.append("banner already present")

    elif p.op == "append_ledger_row":
        today = date.today().isoformat()
        row = (
            f"| {today} | {p.sha or '-'} | - | (advise) | {p.clauses or '-'} | "
            f"{p.protocol or '-'} | {p.note or ''} |"
        )
        if not sb.ledger_text.strip():
            sb.ledger_text = (
                f"# Commit Ledger - {sb.topic}\n\n"
                "> Historical commits before binder adoption are not backfilled.\n\n"
                "| date | code_commit | ndf_commit | proposals | clauses | protocol | note |\n"
                "|------|-------------|------------|-----------|---------|----------|------|\n"
                f"{row}\n"
            )
        else:
            if not sb.ledger_text.endswith("\n"):
                sb.ledger_text += "\n"
            sb.ledger_text += row + "\n"
        sb.notes.append(f"appended ledger row sha={p.sha}")

    elif p.op == "update_topic_draft_table":
        cid = p.clause_id
        note = p.note or "status=stable (promoted)"
        if not cid:
            sb.notes.append("no clause_id")
            return
        # replace status=draft near the clause wiki
        pattern = rf"(\[\[{re.escape(cid)}\]\].*?status\s*=\s*)draft"
        new_text, n = re.subn(pattern, rf"\1stable", sb.topic_text, count=1, flags=re.I | re.S)
        if n:
            sb.topic_text = new_text
            sb.notes.append(f"rewrote status=draft→stable near {cid}")
        else:
            # fallback: append promoted note under Draft clauses
            marker = "## Draft clauses"
            if marker in sb.topic_text:
                sb.topic_text = sb.topic_text.replace(
                    marker,
                    f"{marker}\n\n> advise: {cid} → {note}\n",
                    1,
                )
                sb.notes.append(f"annotated Draft clauses for {cid}")
            else:
                sb.topic_text += f"\n\n> advise: {cid} → {note}\n"
                sb.notes.append("appended promote annotation")

    elif p.op == "add_trailers_template":
        sha = p.sha or "UNKNOWN"
        block = p.trailer_block or f"Topic: {sb.topic}\nClauses: <IDs>\n"
        sb.trailer_templates[sha] = block
        sb.notes.append(f"stored trailer template for {sha[:7]}")

    elif p.op == "lengthen_ledger_note":
        # append a guidance row rather than mutating all short notes
        apply_bind_patch(
            sb,
            BindPatch(
                "append_ledger_row",
                topic=sb.topic,
                sha="-",
                clauses="(grain)",
                note=p.note or "lengthen notes on prior rows",
            ),
        )

    elif p.op == "fix_path_cite":
        if p.path and p.path in sb.topic_text:
            if p.path_new:
                sb.topic_text = sb.topic_text.replace(p.path, p.path_new)
                sb.notes.append(f"retarget path {p.path} → {p.path_new}")
            else:
                sb.topic_text = sb.topic_text.replace(f"`{p.path}`", "`(removed)`")
                sb.notes.append(f"removed path cite {p.path}")
        else:
            sb.notes.append("path not found in TOPIC text (may live in proposals)")

    else:
        sb.notes.append(f"unknown op {p.op}")


def dual_resolved(sb: BinderSandbox, f: bc.Finding, by_id: dict[str, ndx.Clause]) -> bool:
    cid = extract_clause_id(f)
    if not cid:
        return False
    if f.kind == "draft_vs_stable":
        # still has status=draft next to cid?
        if re.search(
            rf"\[\[{re.escape(cid)}\]\].*?status\s*=\s*draft",
            sb.topic_text,
            flags=re.I | re.S,
        ):
            return False
        # advise annotation counts as resolved intent
        if f"advise: {cid}" in sb.topic_text or "status=stable" in sb.topic_text:
            return True
        # no draft claim left
        return "status=draft" not in sb.topic_text.lower() or cid not in sb.topic_text
    return False


def bind_finding_mitigated(sb: BinderSandbox, f: bc.Finding, patch: BindPatch) -> bool:
    if f.kind in ("draft_vs_stable", "stable_claim_vs_draft"):
        return dual_resolved(sb, f, {})

    if f.kind == "missing_trailer":
        sha = extract_sha(f) or patch.sha
        short = sha[:7] if sha else ""
        if patch.op == "add_trailers_template" and sb.trailer_templates:
            return True
        if patch.op == "append_ledger_row" and short and short in sb.ledger_text:
            return True
        if patch.op == "add_not_backfilled_banner" and re.search(
            r"(?i)not\s+backfilled", sb.ledger_text
        ):
            return True
        return False

    if f.kind == "clause_unbound":
        cid = extract_clause_id(f)
        if cid and cid in sb.ledger_text:
            return True
        if re.search(r"(?i)not\s+backfilled", sb.ledger_text):
            return True
        return False

    if f.kind in ("coarse_protocol", "crowded_clauses", "timeline_unbind"):
        return "advise" in sb.ledger_text or patch.note in sb.ledger_text

    if f.kind == "missing_path":
        return f.loc not in sb.topic_text or "(removed)" in sb.topic_text

    if f.kind in ("missing_ledger", "missing_binder"):
        return bool(sb.ledger_text.strip()) and bool(sb.topic_text.strip())

    if f.kind == "bad_ledger_sha":
        return True  # advisory

    return False


def render_bind_plan(queue: list[BindAdvised], low_hanging: bool) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# NDF advise report (bind surface)",
        "",
        f"> Generated by `{TOOL} --surface bind` at {now}",
        "",
        f"- advised_issues: {len(queue)}",
        f"- low_hanging_fruit: {low_hanging}",
        f"- surface: bind (v2)",
        f"- sandbox: virtual TOPIC.md + COMMITS.md only (never writes git/SoT)",
        "",
        "## Summary by kind",
        "",
        "| kind | count |",
        "|------|------:|",
    ]
    counts: dict[str, int] = defaultdict(int)
    for a in queue:
        counts[a.finding.kind] += 1
    for k, n in sorted(counts.items(), key=lambda x: BIND_KIND_PRIORITY.get(x[0], 99)):
        lines.append(f"| `{k}` | {n} |")
    lines.append("")

    title = (
        "## Low-hanging fruit (high confidence)"
        if low_hanging
        else "## Issue queue (DUAL-HEAD → BIND-GAP → grain → …)"
    )
    lines.append(title)
    lines.append("")

    for a in queue:
        f = a.finding
        lines.append(f"### `{a.issue_id}` — {f.kind} ({f.topic})")
        lines.append("")
        lines.append(f"**{f.severity}** `{f.def_id}`: {f.message}")
        if f.loc:
            lines.append(f"  loc: `{f.loc}`")
        lines.append("")
        if f.evidence:
            lines.append("#### evidence")
            lines.append("")
            for e in f.evidence[:12]:
                lines.append(f"- {e}")
            lines.append("")
        diag = bc.render_mermaid(f)
        if diag:
            lines.append(diag)
            lines.append("")
        lines.append("#### RefactorOptions (best first)")
        lines.append("")
        for o in a.options:
            lines.append(f"- **`{o.opt_id}`** ({o.confidence}): {o.title}")
            lines.append(
                f"  - Impact_Delta: topic={o.impact_delta.get('topic')} "
                f"sev={o.impact_delta.get('severity')}"
            )
            if o.rationale:
                lines.append(f"  - rationale: {o.rationale}")
            lines.append(
                f"  - patch: `{json.dumps(o.patch.to_dict(), ensure_ascii=False)}`"
            )
            for step in o.manual_steps:
                lines.append(f"  - step: {step}")
            lines.append(
                f"  - simulate: `python3 {TOOL} simulate --surface bind "
                f"--issue {a.issue_id} --option {o.opt_id}`"
            )
        lines.append("")
        lines.append("#### AI prompt stub")
        lines.append("")
        lines.append("```")
        lines.append(
            f"NDF bind-advise {a.issue_id} topic={f.topic}: pick O1 unless unsafe. "
            f"Do not amend git; only edit poc/{f.topic}/ndf/ after sandbox pass."
        )
        lines.append("```")
        lines.append("")

    lines.append("## Next")
    lines.append("")
    lines.append("1. `simulate --surface bind` on chosen option.")
    lines.append("2. If pass, manually edit TOPIC/COMMITS (never auto).")
    lines.append("3. Re-run `ndf_bindcheck`.")
    lines.append("")
    return "\n".join(lines)


def render_bind_simulate(
    advised: BindAdvised, opt: BindOption, sb: BinderSandbox, passed: bool
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    f = advised.finding
    lines = [
        "# NDF advise simulate (bind surface)",
        "",
        f"> Generated by `{TOOL}` at {now}",
        "",
        f"- issue: `{advised.issue_id}` ({f.kind} / {f.topic})",
        f"- option: `{opt.opt_id}` — {opt.title}",
        f"- confidence: {opt.confidence}",
        f"- sandbox: `{'pass' if passed else 'fail'}`",
        f"- patch: `{json.dumps(opt.patch.to_dict(), ensure_ascii=False)}`",
        "",
        "## apply notes",
        "",
    ]
    for n in sb.notes:
        lines.append(f"- {n}")
    if opt.patch.op == "add_trailers_template":
        sha = opt.patch.sha or "?"
        lines.append("")
        lines.append("## trailer template (not applied to git)")
        lines.append("")
        lines.append("```")
        lines.append(sb.trailer_templates.get(sha, opt.patch.trailer_block))
        lines.append("```")
    lines.append("")
    lines.append("## virtual ledger (tail)")
    lines.append("")
    lines.append("```")
    tail = "\n".join(sb.ledger_text.splitlines()[-12:])
    lines.append(tail or "(empty)")
    lines.append("```")
    lines.append("")
    lines.append("## gate")
    lines.append("")
    lines.append(f"- finding mitigated in virtual binder: {passed}")
    if f.kind == "missing_trailer":
        lines.append(
            "- note: bindcheck may still flag historical commits lacking trailers; "
            "use ledger/banner + `--since` to manage debt"
        )
    lines.append("")
    lines.append("## manual steps")
    lines.append("")
    for step in opt.manual_steps or ["Apply virtual diff to poc binder by hand"]:
        lines.append(f"- {step}")
    lines.append("")
    lines.append("## result")
    lines.append("")
    if passed:
        lines.append("sandbox **pass** — binder intent consistent; **no files written**.")
    else:
        lines.append("sandbox **fail** — choose another option.")
    lines.append("")
    return "\n".join(lines)


def cmd_bind_plan(args) -> int:
    by_id = ndx.load_graph(include_archive=False, include_open=False)
    kinds = None
    if getattr(args, "kinds", None):
        kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    checks = {"bind", "dual", "grain"}
    if getattr(args, "checks", None):
        checks = {c.strip() for c in args.checks.split(",") if c.strip()}
    queue = build_bind_queue(
        by_id,
        topic=getattr(args, "topic", None) or args.focus,
        low_hanging=args.low_hanging_fruit,
        max_issues=args.max_issues,
        kinds=kinds,
        since=getattr(args, "since", None),
        checks=checks,
    )
    text = render_bind_plan(queue, args.low_hanging_fruit)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
        print("# ndf_advise plan (bind)")
        print(f"advised_issues: {len(queue)}")
        by_k: dict[str, int] = defaultdict(int)
        for a in queue:
            by_k[a.finding.kind] += 1
        for k, n in sorted(by_k.items()):
            print(f"  {k}: {n}")
        for a in queue[:12]:
            print(
                f"  {a.issue_id}: {a.finding.topic} best={a.options[0].opt_id if a.options else '-'}"
            )
        print(f"wrote report: {args.report}")
    else:
        print(text)
    return 0


def cmd_bind_simulate(args) -> int:
    by_id = ndx.load_graph(include_archive=False, include_open=False)
    kinds = None
    if getattr(args, "kinds", None):
        kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    checks = {"bind", "dual", "grain"}
    if getattr(args, "checks", None):
        checks = {c.strip() for c in args.checks.split(",") if c.strip()}
    queue = build_bind_queue(
        by_id,
        topic=getattr(args, "topic", None) or args.focus,
        low_hanging=False,
        max_issues=max(args.max_issues, 200),
        kinds=kinds,
        since=getattr(args, "since", None),
        checks=checks,
    )
    advised = next((a for a in queue if a.issue_id == args.issue), None)
    if advised is None:
        print(f"unknown issue id: {args.issue}", file=sys.stderr)
        return 2
    opt = next((o for o in advised.options if o.opt_id == args.option), None)
    if opt is None:
        print(
            f"unknown option {args.option}; have {[o.opt_id for o in advised.options]}",
            file=sys.stderr,
        )
        return 2

    sb = load_sandbox(advised.finding.topic)
    apply_bind_patch(sb, opt.patch)
    passed = bind_finding_mitigated(sb, advised.finding, opt.patch)
    text = render_bind_simulate(advised, opt, sb, passed)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"sandbox: {'pass' if passed else 'fail'}")
        print(f"wrote report: {args.report}")
    else:
        print(text)
    return 0 if passed else 1
