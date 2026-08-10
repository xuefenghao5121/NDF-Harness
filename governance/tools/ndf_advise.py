#!/usr/bin/env python3
"""NDF interactive advisor (surgical options + sandbox) — not a silent fixer.

Surfaces:
  graph (v1): ndf_graphcheck → RefactorOptions + graph sandbox
  bind  (v2): ndf_bindcheck  → RefactorOptions + virtual TOPIC/COMMITS sandbox

Usage:
  python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit \\
      --report tmp/ndf-advise.md
  python3 spec/meta/tools/ndf_advise.py plan --surface bind --low-hanging-fruit \\
      --report tmp/ndf-advise-bind.md
  python3 spec/meta/tools/ndf_advise.py simulate --surface bind \\
      --issue dual-001 --option O1 --report tmp/ndf-advise-bind-sim.md
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ndf_advise_bind as bindadv  # noqa: E402
import ndf_graphcheck as gc  # noqa: E402
import ndf_index as ndx  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
TOOL = "spec/meta/tools/ndf_advise.py"
ALLOWED_RELS = (
    "refines",
    "depends-on",
    "verifies",
    "conflicts-with",
    "affects",
    "superseded-by",
    "couples-with",
)
KIND_PRIORITY = {
    "stable_dep": 0,
    "cycle": 1,
    "conflict_asym": 2,
    "meta_dangling": 3,
    "unlinked": 4,
}
BFS_DEPTH = 3


@dataclass
class AtomicPatch:
    op: str
    src: str = ""
    rel: str = ""
    tgt: str = ""
    new_tgt: str = ""
    new_rel: str = ""
    new_id: str = ""
    new_status: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        d = {"op": self.op}
        for k in ("src", "rel", "tgt", "new_tgt", "new_rel", "new_id", "new_status", "note"):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d


@dataclass
class RefactorOption:
    opt_id: str
    title: str
    confidence: str  # high | medium | low
    impact_delta: dict
    patch: AtomicPatch
    rationale: str = ""
    manual_steps: list[str] = field(default_factory=list)


@dataclass
class AdvisedIssue:
    issue_id: str
    issue: gc.Issue
    options: list[RefactorOption] = field(default_factory=list)
    depth: int = 0
    cycle_len: int = 0
    context: list[str] = field(default_factory=list)


def clone_graph(by_id: dict[str, ndx.Clause]) -> dict[str, ndx.Clause]:
    return copy.deepcopy(by_id)


def ensure_rel_list(c: ndx.Clause, rel: str) -> list[str]:
    # normalize to hyphen form used by graphcheck
    key = rel
    if key not in c.edges:
        # try underscore alias
        alt = rel.replace("-", "_")
        if alt in c.edges:
            key = alt
        else:
            c.edges[rel] = []
            return c.edges[rel]
    return c.edges[key]


def remove_edge(g: dict[str, ndx.Clause], src: str, rel: str, tgt: str) -> bool:
    if src not in g:
        return False
    lst = ensure_rel_list(g[src], rel)
    norm = gc._norm_rel(rel)
    # edges may be stored under hyphen or underscore
    for key in list(g[src].edges.keys()):
        if gc._norm_rel(key) != norm:
            continue
        if tgt in g[src].edges[key]:
            g[src].edges[key] = [x for x in g[src].edges[key] if x != tgt]
            return True
    return False


def add_edge(g: dict[str, ndx.Clause], src: str, rel: str, tgt: str) -> None:
    if src not in g:
        return
    rel_n = gc._norm_rel(rel)
    # prefer hyphen key
    key = rel_n
    if key not in g[src].edges:
        for k in g[src].edges:
            if gc._norm_rel(k) == rel_n:
                key = k
                break
        else:
            g[src].edges[key] = []
    if tgt not in g[src].edges[key]:
        g[src].edges[key].append(tgt)


def apply_patch(g: dict[str, ndx.Clause], p: AtomicPatch) -> list[str]:
    """Mutate sandbox graph. Returns notes/warnings."""
    notes: list[str] = []
    op = p.op
    if op == "remove_edge":
        ok = remove_edge(g, p.src, p.rel, p.tgt)
        if not ok:
            notes.append(f"edge not found: {p.src} -[{p.rel}]-> {p.tgt}")
    elif op == "add_edge":
        add_edge(g, p.src, p.rel, p.tgt or p.new_tgt)
        notes.append(f"added {p.src} -[{p.rel}]-> {p.tgt or p.new_tgt}")
    elif op == "retarget_edge":
        if p.tgt and p.tgt != "__none__":
            remove_edge(g, p.src, p.rel, p.tgt)
        add_edge(g, p.src, p.rel, p.new_tgt)
    elif op == "change_rel":
        remove_edge(g, p.src, p.rel, p.tgt)
        add_edge(g, p.src, p.new_rel or "couples-with", p.tgt)
    elif op == "mirror_conflict":
        add_edge(g, p.tgt, "conflicts-with", p.src)
    elif op == "deprecate_node":
        if p.src in g:
            g[p.src].status = p.new_status or "deprecated"
            g[p.src].meta["status"] = g[p.src].status
            if p.new_tgt:
                add_edge(g, p.src, "superseded-by", p.new_tgt)
        else:
            notes.append(f"missing node {p.src}")
    elif op == "insert_iface":
        nid = p.new_id
        if not nid:
            notes.append("insert_iface requires new_id")
            return notes
        if nid not in g:
            g[nid] = ndx.Clause(
                id=nid,
                title=f"(sandbox iface for {p.tgt})",
                file="(sandbox)",
                line=0,
                kind="beh",
                level="must",
                status="stable",
                meta={"status": "stable", "level": "must"},
                edges={},
            )
            notes.append(f"created sandbox node {nid}")
        if p.src and p.rel and p.tgt:
            remove_edge(g, p.src, p.rel, p.tgt)
            add_edge(g, p.src, p.rel, nid)
            add_edge(g, nid, p.rel, p.tgt)
    else:
        notes.append(f"unknown op {op}")
    return notes


def count_issues(by_id: dict[str, ndx.Clause]) -> dict[str, int]:
    errors, warnings = gc.run_checks(by_id)
    counts: dict[str, int] = defaultdict(int)
    for i in errors + warnings:
        counts[i.kind] += 1
    counts["_errors"] = len(errors)
    counts["_warnings"] = len(warnings)
    return dict(counts)


def issue_fingerprint(issue: gc.Issue) -> tuple:
    return (
        issue.kind,
        tuple(issue.bad_edges),
        tuple(issue.seeds),
        issue.message,
    )


def issue_still_present(by_id: dict[str, ndx.Clause], issue: gc.Issue) -> bool:
    errors, warnings = gc.run_checks(by_id)
    fp = issue_fingerprint(issue)
    for i in errors + warnings:
        if issue_fingerprint(i) == fp:
            return True
        # same kind + same bad edge set
        if (
            i.kind == issue.kind
            and issue.bad_edges
            and i.bad_edges
            and set(i.bad_edges) == set(issue.bad_edges)
        ):
            return True
        if (
            i.kind == "cycle"
            and issue.kind == "cycle"
            and set(i.seeds) == set(issue.seeds)
        ):
            return True
    return False


def dep_adj(by_id: dict[str, ndx.Clause]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = defaultdict(list)
    for src, edges in gc.build_meta_adj(by_id, gc.CYCLE_RELS).items():
        for _rel, tgt in edges:
            adj[src].append(tgt)
    return adj


def edge_cut_impact(by_id: dict[str, ndx.Clause], src: str, tgt: str) -> int:
    """Heuristic: prefer cutting edges whose src has fewer structural outs."""
    if src not in by_id:
        return 99
    return len(list(gc.meta_edges(by_id[src])))


def node_depth(by_id: dict[str, ndx.Clause], cid: str) -> int:
    """Longest distance from any root (no inbound dep) to cid; 0 if unknown."""
    adj = dep_adj(by_id)
    inbound: dict[str, int] = defaultdict(int)
    for u, vs in adj.items():
        for v in vs:
            inbound[v] += 1
    roots = [n for n in by_id if inbound[n] == 0]
    if cid not in by_id:
        return 0
    best = 0
    for r in roots:
        q = deque([(r, 0)])
        seen = {r}
        while q:
            u, d = q.popleft()
            if u == cid:
                best = max(best, d)
            for v in adj.get(u, []):
                if v not in seen:
                    seen.add(v)
                    q.append((v, d + 1))
    return best


def impact_delta(by_id: dict[str, ndx.Clause], seeds: list[str]) -> dict:
    adj = dep_adj(by_id)
    rev: dict[str, list[str]] = defaultdict(list)
    for u, vs in adj.items():
        for v in vs:
            rev[v].append(u)

    out_n = in_n = reach = 0
    seen: set[str] = set()
    for s in seeds:
        if s in by_id:
            out_n += len(adj.get(s, []))
            in_n += len(rev.get(s, []))
        q = deque([(s, 0)])
        while q:
            u, d = q.popleft()
            if u in seen or d > BFS_DEPTH:
                continue
            seen.add(u)
            if d > 0:
                reach += 1
            for v in list(adj.get(u, [])) + list(rev.get(u, [])):
                if v not in seen:
                    q.append((v, d + 1))
    return {
        "out_edges": out_n,
        "in_edges": in_n,
        "reachable_within_hops": reach,
        "hop": BFS_DEPTH,
        "seed_count": len(seeds),
    }


def impact_sort_key(o: RefactorOption) -> tuple:
    conf_rank = {"high": 0, "medium": 1, "low": 2}.get(o.confidence, 9)
    reach = o.impact_delta.get("reachable_within_hops", 99)
    if not isinstance(reach, int):
        reach = 99
    return (conf_rank, reach, o.opt_id)


def renumber_options(opts: list[RefactorOption]) -> list[RefactorOption]:
    opts = sorted(opts, key=impact_sort_key)
    for i, o in enumerate(opts, 1):
        o.opt_id = f"O{i}"
    return opts


def find_dec_hits(cid: str) -> list[str]:
    hits: list[str] = []
    for base in (ROOT / "spec" / "decisions", ROOT / "spec" / "meta" / "decisions"):
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if cid in text or cid in p.name.upper():
                hits.append(str(p.relative_to(ROOT)))
                if len(hits) >= 5:
                    return hits
    return hits


def stable_ancestors(by_id: dict[str, ndx.Clause], start: str) -> list[str]:
    """Walk depends-on/refines targets that are stable (BFS)."""
    adj = dep_adj(by_id)
    out: list[str] = []
    q = deque(adj.get(start, []))
    seen = {start}
    while q and len(out) < 8:
        v = q.popleft()
        if v in seen:
            continue
        seen.add(v)
        if v in by_id and by_id[v].status == "stable":
            out.append(v)
        for w in adj.get(v, []):
            if w not in seen:
                q.append(w)
    return out


def is_nonstable_target(by_id: dict[str, ndx.Clause], tid: str) -> bool:
    if tid not in by_id:
        return True
    st = (by_id[tid].status or "").strip().lower()
    return st != "stable"


def is_decision_like(tid: str, by_id: dict[str, ndx.Clause]) -> bool:
    if tid.startswith("DEC-"):
        return True
    if tid in by_id and by_id[tid].file.startswith("decisions/"):
        return True
    if tid in by_id and by_id[tid].file.startswith("meta/decisions/"):
        return True
    return False


def options_for_issue(by_id: dict[str, ndx.Clause], issue: gc.Issue) -> list[RefactorOption]:
    opts: list[RefactorOption] = []
    impact = impact_delta(by_id, issue.seeds)
    kind = issue.kind

    if kind == "stable_dep" and issue.bad_edges:
        src, rel, tgt = issue.bad_edges[0]
        anc = stable_ancestors(by_id, tgt)
        # High confidence: drop meta edge to DEC / empty-status (keep [[wiki]] in body)
        drop_conf = (
            "high"
            if is_decision_like(tgt, by_id) or is_nonstable_target(by_id, tgt)
            else "medium"
        )
        opts.append(
            RefactorOption(
                "Ox",
                f"Remove edge {src} -[{rel}]-> {tgt} (keep body wiki if needed)",
                drop_conf,
                impact,
                AtomicPatch("remove_edge", src=src, rel=rel, tgt=tgt),
                rationale=(
                    "stable must MUST NOT structurally depend on non-stable. "
                    "DEC/empty-status targets are usual false deps — demote to [[wiki]]."
                ),
                manual_steps=[
                    f"Edit `spec/{by_id[src].file}`: remove `{rel}={tgt}` from ndf meta",
                    f"Optionally keep `[[{tgt}]]` in body prose",
                    "Re-run ndf_graphcheck",
                ],
            )
        )
        if anc:
            opts.append(
                RefactorOption(
                    "Ox",
                    f"Retarget {src} -[{rel}]-> {anc[0]} (stable ancestor)",
                    "high",
                    {**impact, "retarget": anc[0]},
                    AtomicPatch(
                        "retarget_edge", src=src, rel=rel, tgt=tgt, new_tgt=anc[0]
                    ),
                    rationale="Keep structural dep on a stable node.",
                    manual_steps=[f"Change `{rel}={tgt}` → `{rel}={anc[0]}` on {src}"],
                )
            )
        opts.append(
            RefactorOption(
                "Ox",
                f"Insert iface between {src} and {tgt} (proposal required)",
                "low",
                {**impact, "new_nodes": 1},
                AtomicPatch(
                    "insert_iface",
                    src=src,
                    rel=rel,
                    tgt=tgt,
                    new_id=f"IFACE-{tgt}",
                ),
                rationale="Only if product needs a stable abstraction; open a proposal.",
                manual_steps=["Open process/product proposal for new clause ID"],
            )
        )
        # NOTE: couples-with still counts in stable_dep STRUCT_RELS — do not suggest it.

    elif kind == "cycle" and issue.seeds:
        if issue.bad_edges:
            edges = list(issue.bad_edges)
        else:
            edges = []
            parts = re.findall(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+", issue.message)
            for a, b in zip(parts, parts[1:]):
                edges.append((a, "depends-on", b))
        # Prefer minimal-impact cut among cycle edges
        edges_sorted = sorted(
            edges, key=lambda e: edge_cut_impact(by_id, e[0], e[2])
        )
        for idx, (s, r, t) in enumerate(edges_sorted[:3]):
            conf = "high" if len(issue.seeds) <= 3 else ("high" if idx == 0 else "medium")
            opts.append(
                RefactorOption(
                    "Ox",
                    f"Break cycle: remove {s} -[{r}]-> {t}",
                    conf,
                    {**impact, "cut_out_degree": edge_cut_impact(by_id, s, t)},
                    AtomicPatch("remove_edge", src=s, rel=r, tgt=t),
                    rationale="Prefer cuts on low out-degree nodes (smaller Impact_Delta).",
                )
            )
        if edges_sorted:
            s, r, t = edges_sorted[0]
            opts.append(
                RefactorOption(
                    "Ox",
                    f"Downgrade {s} -[{r}]-> {t} to couples-with (exits cycle DAG)",
                    "medium",
                    impact,
                    AtomicPatch(
                        "change_rel", src=s, rel=r, tgt=t, new_rel="couples-with"
                    ),
                    rationale="CYCLE_RELS is only refines/depends-on; couples-with breaks the cycle predicate.",
                )
            )

    elif kind == "conflict_asym" and issue.bad_edges:
        s, r, t = issue.bad_edges[0]
        opts.append(
            RefactorOption(
                "Ox",
                f"Mirror conflicts-with: add {t} → {s}",
                "high",
                impact,
                AtomicPatch("mirror_conflict", src=s, rel=r, tgt=t),
                rationale="conflicts-with MUST be symmetric.",
                manual_steps=[f"Add conflicts-with={s} on {t}"],
            )
        )
        opts.append(
            RefactorOption(
                "Ox",
                f"Remove one-sided conflict {s} → {t}",
                "medium",
                impact,
                AtomicPatch("remove_edge", src=s, rel=r, tgt=t),
            )
        )

    elif kind == "meta_dangling" and issue.bad_edges:
        s, r, t = issue.bad_edges[0]
        opts.append(
            RefactorOption(
                "Ox",
                f"Remove dangling edge {s} -[{r}]-> {t}",
                "high",
                impact,
                AtomicPatch("remove_edge", src=s, rel=r, tgt=t),
                rationale="Target missing from graph.",
            )
        )

    elif kind == "unlinked" and issue.seeds:
        cid = issue.seeds[0]
        peer = None
        if cid in by_id:
            f = by_id[cid].file
            for oid, oc in by_id.items():
                if oid == cid:
                    continue
                if oc.file == f and (oc.edges or oc.body_refs):
                    peer = oid
                    break
        if peer:
            opts.append(
                RefactorOption(
                    "Ox",
                    f"Mount {cid} depends-on {peer} (same-file peer)",
                    "low",
                    impact,
                    AtomicPatch("add_edge", src=cid, rel="depends-on", tgt=peer),
                    rationale="Hygiene only; verify semantic parent before applying.",
                    manual_steps=[f"Add depends-on={peer} on {cid}"],
                )
            )

    if not opts:
        opts.append(
            RefactorOption(
                "Ox",
                "Manual review (no safe auto option)",
                "low",
                impact,
                AtomicPatch("remove_edge", note="noop"),
                rationale="Advisor could not synthesize a high-confidence patch.",
                manual_steps=["Inspect subgraph", "Open process proposal if SoT change"],
            )
        )
    return renumber_options(opts)


def apply_patch_safe(g: dict[str, ndx.Clause], p: AtomicPatch) -> list[str]:
    if p.op == "remove_edge" and not p.src and not p.note:
        return ["noop patch"]
    if p.op == "remove_edge" and p.note == "noop":
        return ["noop patch"]
    return apply_patch(g, p)


def build_queue(
    by_id: dict[str, ndx.Clause],
    focus: str | None,
    low_hanging: bool,
    max_issues: int,
    kinds: set[str] | None = None,
) -> list[AdvisedIssue]:
    errors, warnings = gc.run_checks(by_id)
    raw = errors + warnings
    advised: list[AdvisedIssue] = []

    for issue in raw:
        if kinds and issue.kind not in kinds:
            continue
        if focus and focus not in issue.seeds and focus not in issue.message:
            continue
        depth = node_depth(by_id, issue.seeds[0]) if issue.seeds else 0
        cyc = len(issue.seeds) if issue.kind == "cycle" else 0
        advised.append(
            AdvisedIssue(
                issue_id="",
                issue=issue,
                depth=depth,
                cycle_len=cyc,
            )
        )

    def sort_key(a: AdvisedIssue):
        pri = KIND_PRIORITY.get(a.issue.kind, 9)
        if a.issue.kind == "stable_dep":
            return (pri, -a.depth, a.issue.message)
        if a.issue.kind == "cycle":
            return (pri, a.cycle_len or 99, a.issue.message)
        return (pri, a.issue.message)

    advised.sort(key=sort_key)

    counters: dict[str, int] = defaultdict(int)
    out: list[AdvisedIssue] = []
    for a in advised:
        counters[a.issue.kind] += 1
        a.issue_id = f"{a.issue.kind}-{counters[a.issue.kind]:03d}"
        a.options = options_for_issue(by_id, a.issue)
        if low_hanging:
            a.options = renumber_options(
                [o for o in a.options if o.confidence == "high"]
            )
            if not a.options:
                continue
        ctx: list[str] = []
        if a.issue.kind == "stable_dep":
            ctx.append(f"dep_depth(src)={a.depth} (deeper first in queue)")
        if a.issue.kind == "cycle":
            ctx.append(f"cycle_len={a.cycle_len} (minimal cycles first)")
        for sid in a.issue.seeds[:3]:
            if sid in by_id:
                c = by_id[sid]
                ctx.append(
                    f"`{sid}` loc=`spec/{c.file}:{c.line}` status={c.status or '—'} level={c.level or '—'}"
                )
                src = c.meta.get("source", "")
                if src:
                    ctx.append(f"  source: {src}")
                for h in find_dec_hits(sid):
                    ctx.append(f"  dec_hit: `{h}`")
        a.context = ctx
        out.append(a)
        if len(out) >= max_issues:
            break
    return out


def render_seed_subgraph(by_id: dict[str, ndx.Clause], issue: gc.Issue, hop: int) -> str:
    """Highlight bad edges; default hop=0 keeps only seeds (+ bad endpoints)."""
    return gc.render_subgraph_mermaid(by_id, issue, hop, "subgraph (seeds + bad edges)")


def render_plan(
    by_id: dict[str, ndx.Clause],
    queue: list[AdvisedIssue],
    low_hanging: bool,
    hop: int,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors, warnings = gc.run_checks(by_id)
    lines = [
        "# NDF advise report (graph surface)",
        "",
        f"> Generated by `{TOOL}` at {now}",
        "",
        f"- clauses: {len(by_id)}",
        f"- linter_errors: {len(errors)}",
        f"- linter_warnings: {len(warnings)}",
        f"- advised_issues: {len(queue)}",
        f"- low_hanging_fruit: {low_hanging}",
        f"- subgraph_hop: {hop} (0 = seeds/bad-edges only)",
        f"- surface: graph (v1); bind surface = v2 pointer only",
        f"- options ranked by: confidence then Impact_Delta.reach",
        "",
        "## Summary by kind (advised)",
        "",
        "| kind | count |",
        "|------|------:|",
    ]
    counts: dict[str, int] = defaultdict(int)
    for a in queue:
        counts[a.issue.kind] += 1
    for k in ("stable_dep", "cycle", "conflict_asym", "meta_dangling", "unlinked"):
        if counts[k]:
            lines.append(f"| {k} | {counts[k]} |")
    lines.append("")
    lines.append(
        "> v2 bind surface (DUAL-HEAD / BIND-GAP / …) is contracted in "
        "`proposal-meta-ndf-graph-advise` — not implemented in this binary yet."
    )
    lines.append("")

    if low_hanging:
        lines.append("## Low-hanging fruit (high confidence only)")
        lines.append("")
        lines.append(
            "Prefer these first (stable→DEC drops, 2–3 node cycle cuts, "
            "conflict mirror, dangling remove)."
        )
        lines.append("")
    else:
        lines.append("## Issue queue (top-down)")
        lines.append("")
        lines.append(
            "Order: stable_dep (deep first) → minimal cycle → conflict/dangling → unlinked."
        )
        lines.append("")

    for a in queue:
        issue = a.issue
        lines.append(f"### `{a.issue_id}` — {issue.kind}")
        lines.append("")
        lines.append(f"**{issue.severity}**: {issue.message}")
        lines.append("")
        if a.context:
            lines.append("#### context")
            lines.append("")
            for c in a.context:
                lines.append(f"- {c}")
            lines.append("")
        lines.append(render_seed_subgraph(by_id, issue, hop))
        lines.append("")
        lines.append("#### RefactorOptions (best first)")
        lines.append("")
        for o in a.options:
            lines.append(f"- **`{o.opt_id}`** ({o.confidence}): {o.title}")
            lines.append(
                f"  - Impact_Delta: out={o.impact_delta.get('out_edges')} "
                f"in={o.impact_delta.get('in_edges')} "
                f"reach≤{o.impact_delta.get('hop')}={o.impact_delta.get('reachable_within_hops')}"
            )
            if o.rationale:
                lines.append(f"  - rationale: {o.rationale}")
            lines.append(f"  - patch: `{json.dumps(o.patch.to_dict(), ensure_ascii=False)}`")
            for step in o.manual_steps:
                lines.append(f"  - step: {step}")
            lines.append(
                f"  - simulate: `python3 {TOOL} simulate --issue {a.issue_id} "
                f"--option {o.opt_id}`"
            )
        lines.append("")
        seeds = ", ".join(issue.seeds[:6])
        lines.append("#### AI prompt stub")
        lines.append("")
        lines.append("```")
        lines.append(
            f"NDF advise {a.issue_id}: pick RefactorOption O1 unless rationale conflicts. "
            f"Allowed edge keys only: {ALLOWED_RELS}. Seeds: {seeds}. "
            f"Run simulate before any SoT edit."
        )
        lines.append("```")
        lines.append("")

    lines.append("## Next")
    lines.append("")
    lines.append("1. Pick an option and run `simulate`.")
    lines.append("2. If sandbox: pass, edit SoT manually (or open a proposal).")
    lines.append("3. Re-run `ndf_graphcheck` then `ndf_advise.py plan` again.")
    lines.append("4. Never apply patches automatically from this tool (v1).")
    lines.append("")
    return "\n".join(lines)


def cmd_plan(args: argparse.Namespace) -> int:
    if getattr(args, "surface", "graph") == "bind":
        return bindadv.cmd_bind_plan(args)
    by_id = ndx.load_graph(
        include_archive=args.archive,
        include_open=args.open,
        meta_only=getattr(args, "meta", False),
    )
    kinds = None
    if args.kinds:
        kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    queue = build_queue(
        by_id, args.focus, args.low_hanging_fruit, args.max_issues, kinds
    )
    text = render_plan(by_id, queue, args.low_hanging_fruit, args.hop)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
        print("# ndf_advise plan")
        print(f"advised_issues: {len(queue)}")
        print(f"low_hanging_fruit: {args.low_hanging_fruit}")
        by_k: dict[str, int] = defaultdict(int)
        for a in queue:
            by_k[a.issue.kind] += 1
        for k, n in sorted(by_k.items()):
            print(f"  {k}: {n}")
        for a in queue[:12]:
            n_hi = sum(1 for o in a.options if o.confidence == "high")
            best = a.options[0].opt_id if a.options else "-"
            print(
                f"  {a.issue_id}: options={len(a.options)} high={n_hi} best={best}"
            )
        if len(queue) > 12:
            print(f"  … +{len(queue) - 12} more")
        print(f"wrote report: {args.report}")
    else:
        print(text)
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    if getattr(args, "surface", "graph") == "bind":
        return bindadv.cmd_bind_simulate(args)
    by_id = ndx.load_graph(
        include_archive=args.archive,
        include_open=args.open,
        meta_only=getattr(args, "meta", False),
    )
    kinds = None
    if getattr(args, "kinds", None):
        kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    queue = build_queue(by_id, args.focus, False, args.max_issues, kinds)
    target = next((a for a in queue if a.issue_id == args.issue), None)
    if target is None:
        queue = build_queue(by_id, None, False, max(args.max_issues, 200), kinds)
        target = next((a for a in queue if a.issue_id == args.issue), None)
    if target is None:
        print(f"unknown issue id: {args.issue}", file=sys.stderr)
        print("hint: run plan and copy issue id (e.g. stable_dep-001)", file=sys.stderr)
        return 2
    opt = next((o for o in target.options if o.opt_id == args.option), None)
    if opt is None:
        print(
            f"unknown option {args.option} for {args.issue}; "
            f"have {[o.opt_id for o in target.options]}",
            file=sys.stderr,
        )
        return 2

    before = count_issues(by_id)
    g = clone_graph(by_id)
    notes = apply_patch_safe(g, opt.patch)
    after = count_issues(g)
    still = issue_still_present(g, target.issue)
    new_cycles = after.get("cycle", 0) - before.get("cycle", 0)
    new_stable = after.get("stable_dep", 0) - before.get("stable_dep", 0)
    kind_delta = after.get(target.issue.kind, 0) - before.get(target.issue.kind, 0)
    passed = (not still) and new_cycles <= 0 and new_stable <= 0
    if target.issue.kind == "conflict_asym" and after.get("conflict_asym", 0) < before.get(
        "conflict_asym", 0
    ):
        passed = new_cycles <= 0 and new_stable <= 0
    if target.issue.kind == "unlinked" and kind_delta < 0 and new_cycles <= 0:
        passed = True

    next_id = None
    for a in queue:
        if a.issue_id == target.issue_id:
            continue
        if a.options and a.options[0].confidence == "high":
            next_id = a.issue_id
            break
    if next_id is None:
        for a in queue:
            if a.issue_id != target.issue_id:
                next_id = a.issue_id
                break

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# NDF advise simulate",
        "",
        f"> Generated by `{TOOL}` at {now}",
        "",
        f"- issue: `{args.issue}` ({target.issue.kind})",
        f"- option: `{args.option}` — {opt.title}",
        f"- confidence: {opt.confidence}",
        f"- sandbox: `{'pass' if passed else 'fail'}`",
        f"- patch: `{json.dumps(opt.patch.to_dict(), ensure_ascii=False)}`",
        "",
        "## before → after counts",
        "",
        "| kind | before | after | delta |",
        "|------|-------:|------:|------:|",
    ]
    kinds_all = sorted(set(before) | set(after))
    for k in kinds_all:
        if k.startswith("_"):
            continue
        b, a = before.get(k, 0), after.get(k, 0)
        lines.append(f"| {k} | {b} | {a} | {a - b:+d} |")
    lines.append(
        f"| _errors | {before.get('_errors', 0)} | {after.get('_errors', 0)} | "
        f"{after.get('_errors', 0) - before.get('_errors', 0):+d} |"
    )
    lines.append("")
    lines.append("## gate")
    lines.append("")
    lines.append(f"- current issue still present: {still}")
    lines.append(f"- delta[{target.issue.kind}]: {kind_delta:+d}")
    lines.append(f"- new cycles: {new_cycles:+d}")
    lines.append(f"- new stable_dep: {new_stable:+d}")
    if notes:
        lines.append("")
        lines.append("## apply notes")
        lines.append("")
        for n in notes:
            lines.append(f"- {n}")
    lines.append("")
    lines.append("## manual steps (if pass)")
    lines.append("")
    for step in opt.manual_steps or ["Apply the patch fields to SoT meta by hand"]:
        lines.append(f"- {step}")
    lines.append("")
    if passed:
        lines.append("## result")
        lines.append("")
        lines.append("sandbox **pass** — safe to consider manual SoT edit / proposal.")
        lines.append("This tool did **not** write any files.")
        if next_id:
            lines.append(
                f"Suggested next: `python3 {TOOL} simulate --issue {next_id} --option O1`"
            )
    else:
        lines.append("## result")
        lines.append("")
        lines.append("sandbox **fail** — do not apply; pick another option or revise patch.")
        if still:
            lines.append("- fail reason: current issue remains")
        if new_cycles > 0:
            lines.append("- fail reason: introduced new cycle(s)")
        if new_stable > 0:
            lines.append("- fail reason: introduced new stable_dep")
    lines.append("")

    out = "\n".join(lines)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(out, encoding="utf-8")
        print(f"sandbox: {'pass' if passed else 'fail'}")
        print(f"wrote report: {args.report}")
    else:
        print(out)
    return 0 if passed else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--surface",
            choices=("graph", "bind"),
            default="graph",
            help="graph = Layer A advise (v1); bind = binding/provenance advise (v2)",
        )
        p.add_argument("--archive", action="store_true")
        p.add_argument("--open", action="store_true")
        p.add_argument(
            "--meta",
            action="store_true",
            help="META-only graph (meta/ or scope=ndf-process)",
        )
        p.add_argument(
            "--focus",
            default=None,
            help="graph: clause ID; bind: also accepted as topic id",
        )
        p.add_argument(
            "--topic",
            default=None,
            help="bind surface: POC topic id (preferred over --focus)",
        )
        p.add_argument(
            "--kinds",
            default=None,
            help="comma filter of finding kinds",
        )
        p.add_argument(
            "--checks",
            default=None,
            help="bind surface: bind,dual,grain,zombie,drift",
        )
        p.add_argument("--since", default=None, help="bind surface: git --since window")
        p.add_argument("--max-issues", type=int, default=40)
        p.add_argument(
            "--hop",
            type=int,
            default=0,
            help="graph subgraph hops (default 0)",
        )
        p.add_argument("--report", type=Path, help="write Markdown report")

    p_plan = sub.add_parser("plan", help="Emit surgical RefactorOptions worksheet")
    add_common(p_plan)
    p_plan.add_argument(
        "--low-hanging-fruit",
        action="store_true",
        help="only issues that have at least one high-confidence option",
    )
    p_plan.set_defaults(func=cmd_plan)

    p_sim = sub.add_parser("simulate", help="Sandbox-apply one option; never writes SoT")
    add_common(p_sim)
    p_sim.add_argument("--issue", required=True, help="issue id from plan, e.g. cycle-001")
    p_sim.add_argument("--option", required=True, help="option id, e.g. O1")
    p_sim.set_defaults(func=cmd_simulate)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
