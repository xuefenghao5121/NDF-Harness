#!/usr/bin/env python3
"""NDF clause index / impact / validate — review surface over Markdown SoT.

Harness tool (not product pipeline). Lives under spec/meta/tools/, not scripts/.

Usage:
  python3 spec/meta/tools/ndf_index.py index              # write spec/INDEX.md + spec/graph.json
  python3 spec/meta/tools/ndf_index.py impact BEH-018 DEC-061
  python3 spec/meta/tools/ndf_index.py validate           # dangling [[ID]] / meta refs
  python3 spec/meta/tools/ndf_index.py diff [git-range]   # IDs touched + impact closure
  python3 spec/meta/tools/ndf_index.py poc-topics         # list poc/<topic>/ndf/TOPIC.md (non-SoT)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# spec/meta/tools/ndf_index.py → repo root
ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec"
TOOL = "spec/meta/tools/ndf_index.py"

ANCHOR_RE = re.compile(r"\{#([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\}")
WIKI_RE = re.compile(r"\[\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?:\s*\|\s*[^\]]+)?\]\]")
META_LINE_RE = re.compile(r"<!--\s*ndf:\s*(.*?)\s*-->")
KV_RE = re.compile(r"([a-z][a-z0-9_-]*)\s*=\s*([^\s]+)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

EDGE_KEYS = (
    "refines",
    "depends-on",
    "depends_on",
    "verifies",
    "conflicts-with",
    "conflicts_with",
    "affects",
    "superseded-by",
    "superseded_by",
    "couples-with",
    "couples_with",
    "model",
)


@dataclass
class Clause:
    id: str
    title: str
    file: str
    line: int
    kind: str = ""
    level: str = ""
    layer: str = ""
    status: str = ""
    since: str = ""
    meta: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)  # rel -> [ids]
    body_refs: list = field(default_factory=list)


def iter_spec_files(include_archive: bool, include_open: bool) -> list[Path]:
    files = []
    for p in sorted(SPEC.rglob("*.md")):
        rel = p.relative_to(SPEC).as_posix()
        if not include_archive and rel.startswith("archive/"):
            continue
        # Product open/ and meta/open/ are proposal surfaces (may duplicate / non-SoT prose)
        if not include_open and (rel.startswith("open/") or rel.startswith("meta/open/")):
            continue
        if p.name in ("INDEX.md", "README.md"):
            continue
        files.append(p)
    return files


def parse_ids_csv(val: str) -> list[str]:
    out = []
    for part in val.split(","):
        part = part.strip()
        if not part or part.startswith("models/"):
            continue
        m = re.match(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)", part)
        if m:
            out.append(m.group(1))
    return out


def sot_rank(rel: str) -> int:
    """Lower is preferred when resolving duplicate IDs."""
    if rel.startswith("open/") or rel.startswith("meta/open/"):
        return 3
    if rel.startswith("archive/"):
        return 4
    if rel.startswith("refs/"):
        return 2
    # Process-profile clauses live under meta/ (prefer over product thin pointers)
    if rel.startswith("meta/"):
        return 0
    return 1


def parse_file(path: Path) -> list[Clause]:
    rel = path.relative_to(SPEC).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    clauses: list[Clause] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        am = ANCHOR_RE.search(line)
        if not am:
            i += 1
            continue
        cid = am.group(1)
        title = line
        hm = HEADING_RE.match(line)
        if hm:
            title = ANCHOR_RE.sub("", hm.group(2)).strip()
            title = re.sub(r"\s+", " ", title)
        meta: dict[str, str] = {}
        edges: dict[str, list[str]] = defaultdict(list)
        j = i + 1
        while j < len(lines) and j <= i + 6:
            mm = META_LINE_RE.search(lines[j])
            if not mm:
                if lines[j].strip() == "" or lines[j].startswith(">"):
                    j += 1
                    continue
                break
            for k, v in KV_RE.findall(mm.group(1)):
                meta[k] = v
                key = k.replace("_", "-")
                if key in EDGE_KEYS or k in EDGE_KEYS:
                    rel_name = key.replace("_", "-")
                    for tid in parse_ids_csv(v):
                        edges[rel_name].append(tid)
            j += 1
        # body refs until next heading with anchor or next ## at same level? scan until next {#ID} heading
        body_refs: list[str] = []
        k = i + 1
        while k < len(lines):
            if k > i and ANCHOR_RE.search(lines[k]) and HEADING_RE.match(lines[k]):
                break
            for wm in WIKI_RE.finditer(lines[k]):
                body_refs.append(wm.group(1))
            k += 1
        # unique preserve order
        seen = set()
        urefs = []
        for r in body_refs:
            if r not in seen and r != cid:
                seen.add(r)
                urefs.append(r)
        clauses.append(
            Clause(
                id=cid,
                title=title or cid,
                file=rel,
                line=i + 1,
                kind=meta.get("kind", ""),
                level=meta.get("level", ""),
                layer=meta.get("layer", ""),
                status=meta.get("status", ""),
                since=meta.get("since", ""),
                meta=dict(meta),
                edges={kk: vv for kk, vv in edges.items()},
                body_refs=urefs,
            )
        )
        i = j if j > i else i + 1
    return clauses


def load_graph(include_archive: bool, include_open: bool) -> dict[str, Clause]:
    by_id: dict[str, Clause] = {}
    for path in iter_spec_files(include_archive, include_open):
        for c in parse_file(path):
            if c.id not in by_id:
                by_id[c.id] = c
                continue
            old = by_id[c.id]
            if sot_rank(c.file) < sot_rank(old.file):
                print(
                    f"warning: duplicate id {c.id}: prefer {c.file} over {old.file}",
                    file=sys.stderr,
                )
                by_id[c.id] = c
            elif sot_rank(c.file) == sot_rank(old.file) and c.file != old.file:
                print(
                    f"warning: duplicate id {c.id}: {old.file} and {c.file}",
                    file=sys.stderr,
                )
    return by_id


def all_outgoing(c: Clause) -> set[str]:
    out = set(c.body_refs)
    for ids in c.edges.values():
        out.update(ids)
    out.discard(c.id)
    return out


def build_backlinks(by_id: dict[str, Clause]) -> dict[str, set[str]]:
    back: dict[str, set[str]] = defaultdict(set)
    for cid, c in by_id.items():
        for tgt in all_outgoing(c):
            back[tgt].add(cid)
    return back


def prefix_of(cid: str) -> str:
    return cid.split("-", 1)[0]


def write_index(by_id: dict[str, Clause], out_md: Path, out_json: Path) -> None:
    back = build_backlinks(by_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# NDF Clause INDEX",
        "",
        f"> Generated by `{TOOL}` at {now}. Do not hand-edit.",
        f"> Re-run: `python3 {TOOL} index`",
        "> Default scan excludes `spec/open/`, `spec/meta/open/`, and `spec/archive/` (use `--open` / `--archive`).",
        "",
        f"**Clauses:** {len(by_id)}",
        "",
        "## Quick commands",
        "",
        "```bash",
        f"python3 {TOOL} impact BEH-018",
        f"python3 {TOOL} validate",
        f"python3 {TOOL} diff HEAD~1",
        f"python3 {TOOL} poc-topics",
        "```",
        "",
    ]

    def is_meta(c: Clause) -> bool:
        return c.file.startswith("meta/") or (c.meta.get("scope") == "ndf-process")

    def append_table(section_title: str, clauses: list[Clause]) -> None:
        lines.append(f"## {section_title}")
        lines.append("")
        if not clauses:
            lines.append("_(empty)_")
            lines.append("")
            return
        by_prefix: dict[str, list[Clause]] = defaultdict(list)
        for c in clauses:
            by_prefix[prefix_of(c.id)].append(c)
        for pref in sorted(by_prefix):
            lines.append(f"### {pref}")
            lines.append("")
            lines.append("| ID | Status | Title | Location | Out | In |")
            lines.append("|----|--------|-------|----------|-----|-----|")
            for c in sorted(by_prefix[pref], key=lambda x: x.id):
                loc = f"[`{c.file}:{c.line}`]({c.file}#{c.id})"
                st = c.status or "—"
                title = c.title.replace("|", "\\|")
                n_out = len(all_outgoing(c))
                n_in = len(back.get(c.id, ()))
                lines.append(
                    f"| [`{c.id}`]({c.file}#{c.id}) | {st} | {title} | {loc} | {n_out} | {n_in} |"
                )
            lines.append("")

    meta_list = [c for c in by_id.values() if is_meta(c)]
    product_list = [c for c in by_id.values() if not is_meta(c)]
    append_table("META (ndf-process-profile)", meta_list)
    append_table("Product (00–50 + product decisions)", product_list)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    graph = {
        "generated_at": now,
        "clause_count": len(by_id),
        "nodes": {
            cid: {
                "id": c.id,
                "title": c.title,
                "file": c.file,
                "line": c.line,
                "kind": c.kind,
                "level": c.level,
                "layer": c.layer,
                "status": c.status,
                "since": c.since,
                "scope": c.meta.get("scope", ""),
                "edges": c.edges,
                "body_refs": c.body_refs,
                "backlinks": sorted(back.get(cid, ())),
            }
            for cid, c in sorted(by_id.items())
        },
    }
    out_json.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_md.relative_to(ROOT)} ({len(by_id)} clauses)")
    print(f"wrote {out_json.relative_to(ROOT)}")


def cmd_impact(by_id: dict[str, Clause], ids: list[str], depth: int) -> int:
    back = build_backlinks(by_id)
    missing = [i for i in ids if i not in by_id]
    for m in missing:
        print(f"error: unknown id {m}", file=sys.stderr)
    if missing:
        return 1
    frontier = set(ids)
    seen = set(ids)
    layers = [sorted(ids)]
    for _ in range(max(0, depth)):
        nxt = set()
        for cid in frontier:
            c = by_id[cid]
            for t in all_outgoing(c):
                if t not in seen:
                    nxt.add(t)
            for t in back.get(cid, ()):
                if t not in seen:
                    nxt.add(t)
        nxt -= seen
        if not nxt:
            break
        layers.append(sorted(nxt))
        seen |= nxt
        frontier = nxt

    print(f"# impact depth={depth}")
    print(f"seeds: {', '.join(ids)}")
    print(f"closure_size: {len(seen)}")
    print()
    for li, layer in enumerate(layers):
        print(f"## hop {li} ({len(layer)})")
        for cid in layer:
            c = by_id[cid]
            print(f"- {cid}  {c.status or '—'}  {c.file}:{c.line}  {c.title}")
            outs = sorted(all_outgoing(c))
            inns = sorted(back.get(cid, ()))
            if outs:
                print(f"    out: {', '.join(outs)}")
            if inns:
                print(f"    in:  {', '.join(inns)}")
        print()
    return 0


def cmd_validate(by_id: dict[str, Clause]) -> int:
    back = build_backlinks(by_id)
    dangling = []
    for cid, c in by_id.items():
        for t in all_outgoing(c):
            if t not in by_id:
                dangling.append((cid, t, c.file, c.line))
    # also scan wiki refs in files that aren't under a clause? already covered via body
    print(f"clauses: {len(by_id)}")
    print(f"dangling_refs: {len(dangling)}")
    for src, tgt, f, line in dangling:
        print(f"  {src} -> {tgt}  ({f}:{line})")
    # orphans: no in no out (informational)
    orphans = [
        cid
        for cid, c in by_id.items()
        if not all_outgoing(c) and not back.get(cid) and not cid.startswith("ADR-")
    ]
    print(f"unlinked_nodes: {len(orphans)}")
    for cid in sorted(orphans)[:30]:
        c = by_id[cid]
        print(f"  {cid}  {c.file}:{c.line}")
    if len(orphans) > 30:
        print(f"  ... +{len(orphans) - 30} more")
    return 1 if dangling else 0


def ids_in_diff(range_spec: str) -> set[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "-U0", range_spec, "--", "spec/"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        print(f"git diff failed: {e}", file=sys.stderr)
        return set()
    found = set()
    for line in out.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            for m in ANCHOR_RE.finditer(line):
                found.add(m.group(1))
            for m in WIKI_RE.finditer(line):
                found.add(m.group(1))
    return found


def cmd_diff(by_id: dict[str, Clause], range_spec: str, depth: int) -> int:
    touched = sorted(ids_in_diff(range_spec))
    print(f"# ndf diff {range_spec}")
    print(f"touched_ids: {len(touched)}")
    if not touched:
        print("(no clause IDs in spec/ diff hunks)")
        return 0
    for cid in touched:
        if cid in by_id:
            c = by_id[cid]
            print(f"- {cid}  {c.status or '—'}  {c.file}:{c.line}")
        else:
            print(f"- {cid}  (removed or only in diff text)")
    print()
    known = [i for i in touched if i in by_id]
    if known:
        return cmd_impact(by_id, known, depth=depth)
    return 0


def cmd_poc_topics() -> int:
    """List poc/<topic>/ndf/TOPIC.md binders (non-SoT progress surface)."""
    poc_root = ROOT / "poc"
    print("# POC topic binders (non-SoT; see BEH-025)")
    if not poc_root.is_dir():
        print("(no poc/ directory)")
        return 0
    topics = []
    for topic_dir in sorted(poc_root.iterdir()):
        if not topic_dir.is_dir() or topic_dir.name.startswith("."):
            continue
        if topic_dir.name == "README.md":
            continue
        topic_md = topic_dir / "ndf" / "TOPIC.md"
        if not topic_md.is_file():
            topics.append((topic_dir.name, "MISSING", str(topic_md.relative_to(ROOT)), 0, "—"))
            continue
        text = topic_md.read_text(encoding="utf-8", errors="replace")
        status = "unknown"
        m = re.search(r"(?im)^\s*[-*]?\s*\**status\**\s*[:=]\s*`?([a-z_]+)`?", text)
        if m:
            status = m.group(1)
        else:
            m2 = re.search(r"(?im)^>\s*status:\s*([a-z_]+)", text)
            if m2:
                status = m2.group(1)
        prop_dir = topic_dir / "ndf" / "proposals"
        n_prop = 0
        if prop_dir.is_dir():
            n_prop = sum(1 for p in prop_dir.iterdir() if p.suffix == ".md")
        # also count proposal links in TOPIC
        n_link = len(re.findall(r"proposal-[a-z0-9_-]+\.md", text, flags=re.I))
        baseline = "—"
        mb = re.search(r"(?im)baseline_protocol\s*[:=]\s*(.+)$", text)
        if mb:
            baseline = mb.group(1).strip()[:80]
        topics.append(
            (
                topic_dir.name,
                status,
                str(topic_md.relative_to(ROOT)),
                max(n_prop, n_link),
                baseline,
            )
        )
    if not topics:
        print("(no topic directories under poc/)")
        return 0
    print(f"{'topic':<24} {'status':<12} {'proposals~':>10}  path")
    missing = 0
    for name, status, path, nprop, _bl in topics:
        print(f"{name:<24} {status:<12} {nprop:>10}  {path}")
        if status == "MISSING":
            missing += 1
    print(f"\ntopics: {len(topics)}; missing_binder: {missing}")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", action="store_true", help="include spec/archive/")
    ap.add_argument("--open", action="store_true", help="include spec/open/ and spec/meta/open/")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="write spec/INDEX.md and spec/graph.json")
    p_impact = sub.add_parser("impact", help="print dependency/backlink closure")
    p_impact.add_argument("ids", nargs="+")
    p_impact.add_argument("--depth", type=int, default=2)
    sub.add_parser("validate", help="dangling wiki/meta refs")
    p_diff = sub.add_parser("diff", help="IDs in git diff + impact")
    p_diff.add_argument("range", nargs="?", default="HEAD~1")
    p_diff.add_argument("--depth", type=int, default=1)
    sub.add_parser("poc-topics", help="list poc/<topic>/ndf/TOPIC.md binders (non-SoT)")

    args = ap.parse_args()

    if args.cmd == "poc-topics":
        return cmd_poc_topics()

    by_id = load_graph(include_archive=args.archive, include_open=args.open)

    if args.cmd == "index":
        write_index(by_id, SPEC / "INDEX.md", SPEC / "graph.json")
        return 0
    if args.cmd == "impact":
        return cmd_impact(by_id, args.ids, depth=args.depth)
    if args.cmd == "validate":
        return cmd_validate(by_id)
    if args.cmd == "diff":
        return cmd_diff(by_id, args.range, depth=args.depth)
    return 2


if __name__ == "__main__":
    sys.exit(main())
