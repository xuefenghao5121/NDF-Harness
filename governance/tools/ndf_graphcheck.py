#!/usr/bin/env python3
"""NDF semantic graph logic checker (not an index tool).

Independent of ndf_index CLI. Reuses parse/load helpers from ndf_index.
Writes no INDEX.md. Focus: cycles, status/dependency rules, conflicts
symmetry, meta dangling edges, orphan warnings — plus error subgraphs
for human review.

Usage:
  python3 spec/meta/tools/ndf_graphcheck.py
  python3 spec/meta/tools/ndf_graphcheck.py --meta
  python3 spec/meta/tools/ndf_graphcheck.py --product
  python3 spec/meta/tools/ndf_graphcheck.py --format text --hop 2
  python3 spec/meta/tools/ndf_graphcheck.py --report tmp/ndf-graphcheck.md
  python3 spec/meta/tools/ndf_graphcheck.py --report -   # stdout only
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 spec/meta/tools/ndf_graphcheck.py` from repo root
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ndf_index as ndx  # noqa: E402
import ndf_report_io as rio  # noqa: E402

TOOL = "spec/meta/tools/ndf_graphcheck.py"
DEFAULT_REPORT = "tmp/ndf-graphcheck.md"

# Edges used for cycle detection (refinement / dependency DAG)
CYCLE_RELS = ("refines", "depends-on")

# All meta edge kinds that count as structural deps for stable→non-stable
STRUCT_RELS = (
    "refines",
    "depends-on",
    "verifies",
    "conflicts-with",
    "affects",
    "superseded-by",
    "couples-with",
)


@dataclass
class Issue:
    kind: str  # cycle | stable_dep | conflict_asym | meta_dangling | unlinked
    severity: str  # error | warning
    message: str
    seeds: list[str] = field(default_factory=list)
    bad_edges: list[tuple[str, str, str]] = field(default_factory=list)
    # (src, rel, tgt)


def _norm_rel(rel: str) -> str:
    return rel.replace("_", "-")


def meta_edges(c: ndx.Clause) -> list[tuple[str, str]]:
    """Return (rel, tgt) for structural meta edges."""
    out: list[tuple[str, str]] = []
    for rel, ids in c.edges.items():
        r = _norm_rel(rel)
        if r not in STRUCT_RELS and r not in CYCLE_RELS:
            # still include any declared EDGE_KEYS from parser
            if r not in { _norm_rel(k) for k in ndx.EDGE_KEYS }:
                continue
        for tid in ids:
            out.append((r, tid))
    return out


def build_meta_adj(
    by_id: dict[str, ndx.Clause], rels: tuple[str, ...] | None = None
) -> dict[str, list[tuple[str, str]]]:
    """cid -> [(rel, tgt), ...]"""
    adj: dict[str, list[tuple[str, str]]] = defaultdict(list)
    allow = set(rels) if rels is not None else None
    for cid, c in by_id.items():
        for rel, tid in meta_edges(c):
            if allow is not None and rel not in allow:
                continue
            adj[cid].append((rel, tid))
    return adj


def find_cycles(
    by_id: dict[str, ndx.Clause],
) -> list[Issue]:
    """DFS cycles on refines/depends-on subgraph."""
    adj = build_meta_adj(by_id, CYCLE_RELS)
    # simplify to neighbors for cycle walk
    neigh: dict[str, list[str]] = defaultdict(list)
    edge_set: dict[tuple[str, str], str] = {}
    for src, edges in adj.items():
        for rel, tgt in edges:
            neigh[src].append(tgt)
            edge_set[(src, tgt)] = rel

    issues: list[Issue] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in by_id}
    for n in neigh:
        color.setdefault(n, WHITE)
    path: list[str] = []
    path_set: set[str] = set()
    seen_cycles: set[tuple[str, ...]] = set()

    def normalize_cycle(cyc: list[str]) -> tuple[str, ...]:
        # rotate so min id first, drop duplicate close
        if len(cyc) > 1 and cyc[0] == cyc[-1]:
            cyc = cyc[:-1]
        if not cyc:
            return tuple()
        i = cyc.index(min(cyc))
        rot = cyc[i:] + cyc[:i]
        return tuple(rot)

    def dfs(u: str) -> None:
        color[u] = GRAY
        path.append(u)
        path_set.add(u)
        for v in neigh.get(u, []):
            if color.get(v, WHITE) == WHITE:
                color.setdefault(v, WHITE)
                dfs(v)
            elif v in path_set:
                # cycle
                i = path.index(v)
                cyc = path[i:] + [v]
                key = normalize_cycle(cyc)
                if key and key not in seen_cycles:
                    seen_cycles.add(key)
                    nodes = list(key)
                    bad = []
                    for a, b in zip(nodes, nodes[1:] + [nodes[0]]):
                        rel = edge_set.get((a, b), "depends-on")
                        bad.append((a, rel, b))
                    issues.append(
                        Issue(
                            kind="cycle",
                            severity="error",
                            message=" -> ".join(nodes + [nodes[0]]),
                            seeds=nodes,
                            bad_edges=bad,
                        )
                    )
        path.pop()
        path_set.discard(u)
        color[u] = BLACK

    for n in sorted(by_id.keys()):
        if color.get(n, WHITE) == WHITE:
            dfs(n)
    return issues


def find_stable_must_deps(by_id: dict[str, ndx.Clause]) -> list[Issue]:
    issues: list[Issue] = []
    for cid, c in sorted(by_id.items()):
        if c.level != "must" or c.status != "stable":
            continue
        for rel, tid in meta_edges(c):
            if tid not in by_id:
                continue  # dangling handled elsewhere
            t = by_id[tid]
            if t.status != "stable":
                st = t.status or "(empty)"
                issues.append(
                    Issue(
                        kind="stable_dep",
                        severity="error",
                        message=(
                            f"{cid} (stable/must) -[{rel}]-> {tid} "
                            f"(status={st}, level={t.level or '—'})"
                        ),
                        seeds=[cid, tid],
                        bad_edges=[(cid, rel, tid)],
                    )
                )
    return issues


def find_conflict_asym(by_id: dict[str, ndx.Clause]) -> list[Issue]:
    issues: list[Issue] = []
    # collect conflicts-with sets
    conf: dict[str, set[str]] = defaultdict(set)
    for cid, c in by_id.items():
        for rel, tid in meta_edges(c):
            if rel == "conflicts-with":
                conf[cid].add(tid)
    seen: set[tuple[str, str]] = set()
    for a, tgts in sorted(conf.items()):
        for b in sorted(tgts):
            pair = tuple(sorted((a, b)))
            if pair in seen:
                continue
            if b not in by_id:
                continue
            if a not in conf.get(b, ()):
                seen.add(pair)
                issues.append(
                    Issue(
                        kind="conflict_asym",
                        severity="error",
                        message=f"{a} conflicts-with {b} but not reciprocal",
                        seeds=[a, b],
                        bad_edges=[(a, "conflicts-with", b)],
                    )
                )
    return issues


def find_meta_dangling(by_id: dict[str, ndx.Clause]) -> list[Issue]:
    issues: list[Issue] = []
    for cid, c in sorted(by_id.items()):
        for rel, tid in meta_edges(c):
            if tid not in by_id:
                issues.append(
                    Issue(
                        kind="meta_dangling",
                        severity="error",
                        message=f"{cid} -[{rel}]-> {tid} (MISSING)",
                        seeds=[cid, tid],
                        bad_edges=[(cid, rel, tid)],
                    )
                )
    return issues


def find_unlinked(by_id: dict[str, ndx.Clause]) -> list[Issue]:
    back = ndx.build_backlinks(by_id)
    issues: list[Issue] = []
    for cid, c in sorted(by_id.items()):
        if cid.startswith("ADR-"):
            continue
        if not ndx.all_outgoing(c) and not back.get(cid):
            issues.append(
                Issue(
                    kind="unlinked",
                    severity="warning",
                    message=f"{cid}  {c.file}:{c.line}  {c.title}",
                    seeds=[cid],
                    bad_edges=[],
                )
            )
    return issues


def expand_seeds(
    by_id: dict[str, ndx.Clause],
    seeds: list[str],
    hop: int,
) -> set[str]:
    """Expand seeds by meta in/out edges up to hop."""
    adj_out = build_meta_adj(by_id, None)
    adj_in: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for src, edges in adj_out.items():
        for rel, tgt in edges:
            adj_in[tgt].append((rel, src))

    nodes = set(seeds)
    frontier = set(s for s in seeds if s in by_id or True)
    for _ in range(max(0, hop)):
        nxt: set[str] = set()
        for u in frontier:
            for _rel, v in adj_out.get(u, []):
                if v not in nodes:
                    nxt.add(v)
            for _rel, v in adj_in.get(u, []):
                if v not in nodes:
                    nxt.add(v)
        if not nxt:
            break
        nodes |= nxt
        frontier = nxt
    return nodes


def collect_subgraph_edges(
    by_id: dict[str, ndx.Clause],
    nodes: set[str],
) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for src in sorted(nodes):
        if src not in by_id:
            continue
        for rel, tgt in meta_edges(by_id[src]):
            if tgt in nodes or src in nodes:
                if src in nodes and (tgt in nodes or tgt not in by_id):
                    key = (src, rel, tgt)
                    if key not in seen:
                        seen.add(key)
                        edges.append(key)
    return edges


def node_label(by_id: dict[str, ndx.Clause], cid: str) -> str:
    if cid not in by_id:
        return f"{cid} MISSING"
    c = by_id[cid]
    st = c.status or "—"
    lv = c.level or "—"
    return f"{cid} {st}/{lv}"


def mermaid_id(cid: str) -> str:
    return cid.replace("-", "_")


def render_subgraph_mermaid(
    by_id: dict[str, ndx.Clause],
    issue: Issue,
    hop: int,
    title: str,
) -> str:
    nodes = expand_seeds(by_id, issue.seeds, hop)
    # always include MISSING targets from bad edges
    for _s, _r, t in issue.bad_edges:
        nodes.add(t)
        nodes.add(_s)
    edges = collect_subgraph_edges(by_id, nodes)
    bad = {(s, r, t) for s, r, t in issue.bad_edges}

    lines = ["```mermaid", "flowchart LR"]
    for n in sorted(nodes):
        mid = mermaid_id(n)
        lab = node_label(by_id, n).replace('"', "'")
        lines.append(f'  {mid}["{lab}"]')
    for s, rel, t in edges:
        sm, tm = mermaid_id(s), mermaid_id(t)
        if (s, rel, t) in bad:
            lines.append(f"  {sm} -.->|{rel} !!|{tm}")
        else:
            lines.append(f"  {sm} -->|{rel}|{tm}")
    # ensure bad edges shown even if tgt missing from adj collect
    for s, rel, t in issue.bad_edges:
        if (s, rel, t) not in {(a, b, c) for a, b, c in edges}:
            sm, tm = mermaid_id(s), mermaid_id(t)
            if t not in by_id:
                lines.append(f'  {tm}["{t} MISSING"]')
            lines.append(f"  {sm} -.->|{rel} !!|{tm}")
    lines.append("```")
    return f"### {title}\n\n" + "\n".join(lines) + "\n"


def render_subgraph_text(
    by_id: dict[str, ndx.Clause],
    issue: Issue,
    hop: int,
    title: str,
) -> str:
    nodes = expand_seeds(by_id, issue.seeds, hop)
    for s, _r, t in issue.bad_edges:
        nodes.add(s)
        nodes.add(t)
    edges = collect_subgraph_edges(by_id, nodes)
    bad = {(s, r, t) for s, r, t in issue.bad_edges}
    lines = [f"### {title}", "nodes:"]
    for n in sorted(nodes):
        lines.append(f"  - {node_label(by_id, n)}")
    lines.append("edges:")
    shown = set()
    for s, rel, t in edges:
        arrow = "!!>" if (s, rel, t) in bad else "-->"
        lines.append(f"  {s} --{rel}{arrow} {t}")
        shown.add((s, rel, t))
    for s, rel, t in issue.bad_edges:
        if (s, rel, t) not in shown:
            lines.append(f"  {s} --{rel}!!> {t}")
    return "\n".join(lines) + "\n"


def render_issue_block(
    by_id: dict[str, ndx.Clause],
    issue: Issue,
    idx: int,
    hop: int,
    fmt: str,
) -> str:
    title = f"{issue.kind} #{idx}"
    head = f"**{issue.severity}** `{issue.kind}`: {issue.message}\n"
    if issue.seeds and issue.seeds[0] in by_id:
        c = by_id[issue.seeds[0]]
        head += f"  loc: `{c.file}:{c.line}`\n"
    if fmt == "text":
        return head + "\n" + render_subgraph_text(by_id, issue, hop, title)
    return head + "\n" + render_subgraph_mermaid(by_id, issue, hop, title)


def run_checks(by_id: dict[str, ndx.Clause]) -> tuple[list[Issue], list[Issue]]:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    errors.extend(find_cycles(by_id))
    errors.extend(find_stable_must_deps(by_id))
    errors.extend(find_conflict_asym(by_id))
    errors.extend(find_meta_dangling(by_id))
    warnings.extend(find_unlinked(by_id))
    return errors, warnings


def filter_product_issues(
    by_id: dict[str, ndx.Clause],
    errors: list[Issue],
    warnings: list[Issue],
) -> tuple[list[Issue], list[Issue]]:
    """Keep issues that touch at least one product (non-meta) clause.

    Full graph is still used for edge resolution (product→meta targets stay valid).
    Meta-only defects (e.g. process-profile cycles) are suppressed.
    """
    product = {cid for cid, c in by_id.items() if not ndx.is_meta_clause(c)}

    def touches_product(issue: Issue) -> bool:
        return any(s in product for s in issue.seeds)

    return (
        [i for i in errors if touches_product(i)],
        [i for i in warnings if touches_product(i)],
    )


def issue_loc(by_id: dict[str, ndx.Clause], issue: Issue) -> str:
    if issue.seeds and issue.seeds[0] in by_id:
        c = by_id[issue.seeds[0]]
        return f"{c.file}:{c.line}"
    return ""


def issue_row(by_id: dict[str, ndx.Clause], issue: Issue, idx: int) -> tuple[str, ...]:
    """Return table cells: #, sev, kind, from, edge, to, loc."""
    if issue.bad_edges:
        src, rel, tgt = issue.bad_edges[0]
    elif len(issue.seeds) >= 2:
        src, rel, tgt = issue.seeds[0], "—", issue.seeds[1]
    elif issue.seeds:
        src, rel, tgt = issue.seeds[0], "—", "—"
    else:
        src, rel, tgt = "—", "—", "—"
    return (
        str(idx),
        issue.severity,
        issue.kind,
        src,
        rel,
        tgt,
        issue_loc(by_id, issue),
    )


def render_kind_figure(
    by_id: dict[str, ndx.Clause],
    kind: str,
    items: list[Issue],
    fmt: str,
) -> str:
    """One compact figure per kind (bad edges only; no hop expansion)."""
    if not items:
        return ""
    if kind == "unlinked":
        lines = [
            f"### Figure: `{kind}`",
            "",
            "| id | loc | title |",
            "|----|-----|-------|",
        ]
        for issue in items:
            cid = issue.seeds[0] if issue.seeds else "—"
            loc = issue_loc(by_id, issue)
            title = ""
            if cid in by_id:
                title = (by_id[cid].title or "").replace("|", "\\|")
            lines.append(f"| `{cid}` | `{loc}` | {title} |")
        lines.append("")
        return "\n".join(lines)

    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in items:
        for e in issue.bad_edges:
            if e not in seen:
                seen.add(e)
                edges.append(e)
    if not edges:
        return f"### Figure: `{kind}`\n\n_(no bad edges)_\n"

    if fmt == "text":
        lines = [f"### Figure: `{kind}`", "", "bad edges:"]
        for s, rel, t in edges:
            lines.append(f"  {s} --{rel}!!> {t}")
        lines.append("")
        return "\n".join(lines)

    nodes: set[str] = set()
    for s, _r, t in edges:
        nodes.add(s)
        nodes.add(t)
    lines = [
        f"### Figure: `{kind}`",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for n in sorted(nodes):
        mid = mermaid_id(n)
        lab = node_label(by_id, n).replace('"', "'")
        lines.append(f'  {mid}["{lab}"]')
    for s, rel, t in edges:
        lines.append(f"  {mermaid_id(s)} -.->|{rel}|{mermaid_id(t)}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def build_report(
    by_id: dict[str, ndx.Clause],
    errors: list[Issue],
    warnings: list[Issue],
    max_issues: int,
    hop: int,
    fmt: str,
    detail: bool = False,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_issues = errors + warnings
    lines = [
        "# NDF graphcheck report",
        "",
        f"> Generated by `{TOOL}` at {now}",
        "",
        f"- clauses: {len(by_id)}",
        f"- hard_errors: {len(errors)}",
        f"- warnings: {len(warnings)}",
        "",
        "## Summary by kind",
        "",
    ]
    counts: dict[str, int] = defaultdict(int)
    for i in all_issues:
        counts[i.kind] += 1
    lines.append("| kind | count | severity |")
    lines.append("|------|------:|----------|")
    for k in ("cycle", "stable_dep", "conflict_asym", "meta_dangling", "unlinked"):
        if counts[k]:
            sev = "warning" if k == "unlinked" else "error"
            lines.append(f"| {k} | {counts[k]} | {sev} |")
    lines.append("")

    lines.append("## Issue index")
    lines.append("")
    if not all_issues:
        lines.append("_(none)_")
        lines.append("")
    else:
        lines.append("| # | sev | kind | from | edge | to | loc |")
        lines.append("|--:|-----|------|------|------|----|-----|")
        for i, issue in enumerate(all_issues, 1):
            row = issue_row(by_id, issue, i)
            lines.append(
                f"| {row[0]} | {row[1]} | `{row[2]}` | `{row[3]}` | {row[4]} "
                f"| `{row[5]}` | `{row[6]}` |"
            )
        lines.append("")

    lines.append("## Figures")
    lines.append("")
    any_fig = False
    for k in ("cycle", "stable_dep", "conflict_asym", "meta_dangling", "unlinked"):
        group = [i for i in all_issues if i.kind == k]
        if not group:
            continue
        any_fig = True
        lines.append(render_kind_figure(by_id, k, group, fmt))
    if not any_fig:
        lines.append("_(none)_")
        lines.append("")

    if detail:
        lines.append("## Appendix: per-issue detail")
        lines.append("")

        def emit_section(title: str, items: list[Issue]) -> None:
            lines.append(f"### {title}")
            lines.append("")
            if not items:
                lines.append("_(none)_")
                lines.append("")
                return
            show = items[:max_issues]
            for i, issue in enumerate(show, 1):
                lines.append(render_issue_block(by_id, issue, i, hop, fmt))
                lines.append("")
            if len(items) > max_issues:
                lines.append(
                    f"_… +{len(items) - max_issues} more omitted (`--max-issues`)_"
                )
                lines.append("")

        emit_section("Hard errors", errors)
        emit_section("Warnings", warnings)

    return "\n".join(lines) + "\n"


def format_console_summary(
    scope: str,
    by_id: dict[str, ndx.Clause],
    errors: list[Issue],
    warnings: list[Issue],
    product_n: int | None = None,
) -> str:
    lines = [
        f"# ndf_graphcheck ({scope})",
        f"clauses: {len(by_id)}"
        + (f" (product≈{product_n})" if product_n is not None else ""),
        f"summary: {len(errors)} error(s), {len(warnings)} warning(s)",
        "",
    ]
    counts: dict[str, int] = defaultdict(int)
    for i in errors + warnings:
        counts[i.kind] += 1
    for k in ("cycle", "stable_dep", "conflict_asym", "meta_dangling", "unlinked"):
        if counts[k]:
            lines.append(f"  {k}: {counts[k]}")
    if counts:
        lines.append("")
    for i, issue in enumerate(errors + warnings, 1):
        row = issue_row(by_id, issue, i)
        lines.append(
            f"- [{row[1]}] `{row[2]}` {row[3]} -[{row[4]}]-> {row[5]}"
            + (f" @ `{row[6]}`" if row[6] else "")
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--archive", action="store_true", help="include spec/archive/")
    ap.add_argument("--open", action="store_true", help="include spec/open/ and spec/meta/open/")
    ap.add_argument(
        "--meta",
        action="store_true",
        help="META-only: check process-profile graph (meta/ or scope=ndf-process)",
    )
    ap.add_argument(
        "--product",
        action="store_true",
        help="PRODUCT-focus: full graph resolve, report only issues touching non-meta clauses",
    )
    ap.add_argument("--max-issues", type=int, default=20, help="max issues in --detail appendix")
    ap.add_argument("--hop", type=int, default=1, help="context hops in --detail appendix")
    ap.add_argument(
        "--format",
        choices=("mermaid", "text"),
        default="mermaid",
        help="figure / detail render format (default: mermaid)",
    )
    ap.add_argument(
        "--report",
        default=DEFAULT_REPORT,
        help=f"Markdown report path (default: {DEFAULT_REPORT}); '-' = stdout only; "
        "MUST NOT be under spec/",
    )
    ap.add_argument(
        "--detail",
        action="store_true",
        help="include per-issue hop subgraphs in report appendix",
    )
    args = ap.parse_args()

    if args.meta and args.product:
        print("error: --meta and --product are mutually exclusive", file=sys.stderr)
        return 2

    try:
        report_path = rio.resolve_report_path(args.report, DEFAULT_REPORT)
    except rio.ReportPathError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    by_id = ndx.load_graph(
        include_archive=args.archive,
        include_open=args.open,
        meta_only=args.meta,
    )
    errors, warnings = run_checks(by_id)
    if args.product:
        errors, warnings = filter_product_issues(by_id, errors, warnings)

    if args.meta:
        scope = "META"
        product_n = None
    elif args.product:
        scope = "PRODUCT"
        product_n = sum(1 for c in by_id.values() if not ndx.is_meta_clause(c))
    else:
        scope = "full"
        product_n = None

    text = build_report(
        by_id,
        errors,
        warnings,
        args.max_issues,
        args.hop,
        args.format,
        detail=args.detail,
    )
    written = rio.write_report(report_path, text)
    if written is not None:
        print(format_console_summary(scope, by_id, errors, warnings, product_n))
        print(f"wrote report: {written}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
