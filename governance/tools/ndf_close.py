#!/usr/bin/env python3
"""NDF POC close planner — round-trip plan onto Trunk graph (read-only).

Does NOT modify SoT. Emits a Markdown plan: inventory, graph additions,
POC prose provenance templates, binder archive checklist, and mandatory
post-merge checks (ndf_index + ndf_graphcheck).

Usage:
  python3 spec/meta/tools/ndf_close.py plan --topic l4-cache-mgmt --mode partial
  python3 spec/meta/tools/ndf_close.py plan --topic io-pipelining --mode promote \\
      --report /tmp/close-plan.md
  python3 spec/meta/tools/ndf_close.py plan --topic pq-quality --mode reject
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ndf_index as ndx  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
POC = ROOT / "poc"
TOOL = "spec/meta/tools/ndf_close.py"

ID_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\b")
WIKI_ID_RE = re.compile(r"\[\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?:\s*\|\s*[^\]]+)?\]\]")


@dataclass
class ProposalRow:
    role: str
    path: str
    status: str


@dataclass
class TopicInfo:
    topic_id: str
    status: str
    baseline: str
    depends_on: str
    path: Path
    text: str
    draft_ids: list[str] = field(default_factory=list)
    proposals: list[ProposalRow] = field(default_factory=list)
    evidence_dir: Path | None = None
    commits_path: Path | None = None
    latest_commit_hint: str = "—"


def load_topic(topic: str) -> TopicInfo:
    topic_dir = POC / topic
    topic_md = topic_dir / "ndf" / "TOPIC.md"
    if not topic_md.is_file():
        raise FileNotFoundError(f"missing binder: {topic_md.relative_to(ROOT)}")
    text = topic_md.read_text(encoding="utf-8", errors="replace")

    def meta_field(name: str, default: str = "—") -> str:
        m = re.search(rf"(?im)^>\s*{name}:\s*(.+)$", text)
        return m.group(1).strip() if m else default

    info = TopicInfo(
        topic_id=meta_field("topic_id", topic),
        status=meta_field("status"),
        baseline=meta_field("baseline_protocol"),
        depends_on=meta_field("depends_on_topics"),
        path=topic_md,
        text=text,
    )

    # Draft clauses: ONLY wiki/IDs under "## Draft clauses" (never baseline/binder noise)
    ids: list[str] = []
    seen: set[str] = set()
    m = re.search(r"(?is)##\s*Draft clauses\s*\n(.*?)(?=\n##\s|\Z)", text)
    if m:
        for wid in WIKI_ID_RE.findall(m.group(1)):
            if wid not in seen:
                seen.add(wid)
                ids.append(wid)
        # bare IDs in table cells without wiki syntax
        for bare in ID_RE.findall(m.group(1)):
            if bare.startswith(("BEH-", "API-", "CON-", "CHR-", "VER-", "ARCH-", "DEF-")):
                if bare not in seen:
                    seen.add(bare)
                    ids.append(bare)
    info.draft_ids = ids

    # Proposals table rows: | role | path | status |
    prop_sec = ""
    pm = re.search(r"(?is)##\s*Proposals\s*\n(.*?)(?=\n##\s|\Z)", text)
    if pm:
        prop_sec = pm.group(1)
    for line in prop_sec.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0].lower() in ("role", "---") or set(cells[0]) <= {"-", ":"}:
            continue
        # unwrap markdown links
        path = cells[1]
        lm = re.search(r"\[([^\]]+)\]\([^)]+\)", path)
        if lm:
            path = lm.group(1)
        path = path.strip("`")
        info.proposals.append(ProposalRow(role=cells[0], path=path, status=cells[2]))

    ev = topic_dir / "ndf" / "evidence"
    info.evidence_dir = ev if ev.is_dir() else None
    commits = topic_dir / "ndf" / "COMMITS.md"
    if commits.is_file():
        info.commits_path = commits
        # try first sha-like token in table
        ct = commits.read_text(encoding="utf-8", errors="replace")
        sm = re.search(r"\b([0-9a-f]{7,40})\b", ct)
        if sm:
            info.latest_commit_hint = sm.group(1)
    return info


def trunk_ids_for_topic(by_id: dict[str, ndx.Clause], topic: str) -> list[str]:
    out = []
    for cid, c in by_id.items():
        t = c.meta.get("topic", "")
        if t == topic:
            out.append(cid)
    return sorted(out)


def suggest_next_id(by_id: dict[str, ndx.Clause], prefix: str) -> str:
    nums = []
    for cid in by_id:
        if cid.startswith(prefix + "-"):
            tail = cid[len(prefix) + 1 :]
            if tail.isdigit():
                nums.append(int(tail))
    n = (max(nums) + 1) if nums else 1
    return f"{prefix}-{n:03d}"


def default_disposition(
    mode: str,
    cid: str,
    c: ndx.Clause | None,
    promote_ids: set[str],
    topic: str,
) -> str:
    owned = bool(c and c.meta.get("topic") == topic)
    if mode == "reject":
        # Only deprecate topic-owned or explicit draft-list clauses; never process SoT noise
        if c and c.status == "draft" and (owned or cid in promote_ids):
            return "deprecate"
        if owned and c and c.status in ("draft", "stable"):
            # topic-tagged stable from this POC: deprecate only if still exploration surface
            if c.status == "draft":
                return "deprecate"
            return "archive-only-ref"  # already trunk; reject topic does not yank unrelated stables
        if c is None:
            return "skip-missing"
        return "archive-only-ref"
    if mode == "promote":
        if c and c.status == "stable":
            return "already-stable"
        return "promote-to-stable"
    # partial
    if cid in promote_ids or (c and c.status == "stable" and owned):
        if c and c.status == "stable":
            return "already-stable"
        return "promote-to-stable"
    if c and c.status == "draft":
        return "keep-draft"
    if c is None:
        return "new-id-needed"
    return "keep-draft"


def edge_suggestions(c: ndx.Clause | None) -> list[str]:
    if not c:
        return []
    lines = []
    for rel, ids in sorted(c.edges.items()):
        for t in ids:
            lines.append(f"{c.id} -[{rel}]-> {t}")
    return lines


def build_plan_report(
    topic: TopicInfo,
    by_id: dict[str, ndx.Clause],
    mode: str,
    promote_ids: set[str],
    year_month: str,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    trunk_topic_ids = trunk_ids_for_topic(by_id, topic.topic_id)
    all_ids: list[str] = []
    seen: set[str] = set()
    for cid in topic.draft_ids + trunk_topic_ids + sorted(promote_ids):
        if cid not in seen:
            seen.add(cid)
            all_ids.append(cid)

    lines: list[str] = []
    lines.append(f"# NDF close plan: `{topic.topic_id}`")
    lines.append("")
    lines.append(f"> Generated by `{TOOL}` at {now}")
    lines.append(f"> mode: **{mode}**")
    lines.append(
        "> Principle: **add nodes/edges onto the Trunk NDF graph** "
        "(`spec/00–50` + `spec/meta`); do **not** lift `poc/*/ndf` into a second SoT."
    )
    lines.append("")
    lines.append("## 1. Inventory")
    lines.append("")
    lines.append(f"| field | value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| topic_id | `{topic.topic_id}` |")
    lines.append(f"| TOPIC status | {topic.status} |")
    lines.append(f"| binder | `{topic.path.relative_to(ROOT)}` |")
    lines.append(f"| baseline_protocol | {topic.baseline} |")
    lines.append(f"| depends_on_topics | {topic.depends_on} |")
    lines.append(f"| draft_ids (TOPIC) | {', '.join(f'`{i}`' for i in topic.draft_ids) or '—'} |")
    lines.append(
        f"| trunk topic= meta | {', '.join(f'`{i}`' for i in trunk_topic_ids) or '—'} |"
    )
    lines.append("")
    lines.append("### Proposals")
    lines.append("")
    if not topic.proposals:
        lines.append("_(none parsed)_")
    else:
        lines.append("| Role | Path | Status |")
        lines.append("|------|------|--------|")
        for p in topic.proposals:
            lines.append(f"| {p.role} | `{p.path}` | {p.status} |")
    lines.append("")
    lines.append("### Clause locations in Trunk")
    lines.append("")
    lines.append("| ID | status | level | file:line | meta edges |")
    lines.append("|----|--------|-------|-----------|------------|")
    for cid in all_ids:
        c = by_id.get(cid)
        if not c:
            lines.append(f"| `{cid}` | **MISSING** | — | — | — |")
            continue
        edges = ", ".join(
            f"{rel}→{t}" for rel, ids in c.edges.items() for t in ids
        ) or "—"
        lines.append(
            f"| `{cid}` | {c.status or '—'} | {c.level or '—'} | "
            f"`{c.file}:{c.line}` | {edges} |"
        )
    lines.append("")

    lines.append("## 2. Graph addition plan (onto Trunk SoT)")
    lines.append("")
    lines.append(
        "Only confirmed dispositions below should be applied to `spec/00–50`. "
        "POC binder remains non-SoT."
    )
    lines.append("")
    lines.append("| ID | disposition | suggested Trunk action |")
    lines.append("|----|-------------|------------------------|")
    add_nodes: list[str] = []
    add_edges: list[str] = []
    touched: list[str] = []
    for cid in all_ids:
        c = by_id.get(cid)
        disp = default_disposition(mode, cid, c, promote_ids, topic.topic_id)
        touched.append(cid)
        if disp == "promote-to-stable":
            action = (
                f"Set `status=stable` (keep `topic={topic.topic_id}` until archive "
                f"or clear per promote proposal); ensure level/must appropriate; "
                f"file `{c.file if c else 'TBD'}`"
            )
            add_nodes.append(f"upgrade `{cid}` draft→stable in `{c.file if c else 'TBD'}`")
            if c:
                for e in edge_suggestions(c):
                    tgt = e.split("->")[-1].strip()
                    tc = by_id.get(tgt)
                    note = ""
                    if tc and tc.status == "draft":
                        note = " ⚠️ target still draft — fix before/with promote"
                    add_edges.append(f"keep/review `{e}`{note}")
        elif disp == "already-stable":
            action = "No status change; verify edges do not `refines` a remaining draft"
            if c:
                for e in edge_suggestions(c):
                    tgt = e.split("->")[-1].strip()
                    tc = by_id.get(tgt)
                    if tc and tc.status == "draft":
                        add_edges.append(
                            f"FIX `{e}` — stable must not refine/depend on draft"
                        )
        elif disp == "deprecate":
            action = (
                f"Set `status=deprecated`; leave thin shell pointing at "
                f"`spec/archive/{year_month}/poc-{topic.topic_id}/`"
            )
            add_nodes.append(f"deprecate shell `{cid}`")
        elif disp == "archive-only-ref":
            action = (
                "Referenced in TOPIC but not owned as topic draft — "
                "**do not** deprecate; only archive binder / cite in reject DEC"
            )
        elif disp == "skip-missing":
            action = "ID not in Trunk graph — ignore or allocate under promote path"
        elif disp == "keep-draft":
            action = "Leave `status=draft`; topic remains exploring (partial close)"
        elif disp == "new-id-needed":
            prefix = cid.split("-")[0] if "-" in cid else "BEH"
            nxt = suggest_next_id(by_id, prefix)
            action = (
                f"Allocate new id (suggestion `{nxt}` if `{cid}` unused) in "
                f"appropriate `spec/20-behavior|30-interfaces|40-constraints/...`; "
                f"wire `refines=`/`depends-on=` to existing Trunk parents"
            )
            add_nodes.append(f"create `{{#{nxt}}}` (requested as `{cid}`)")
        else:
            action = disp
        lines.append(f"| `{cid}` | `{disp}` | {action} |")

    if mode == "reject" and not any(
        default_disposition(mode, cid, by_id.get(cid), promote_ids, topic.topic_id)
        == "deprecate"
        for cid in all_ids
    ):
        lines.append("")
        lines.append(
            "> Note: no topic-owned draft clauses to deprecate. "
            "Reject path is binder archive + DEC (`Rejects:`) only."
        )
    lines.append("")
    lines.append("### Add nodes")
    lines.append("")
    if add_nodes:
        for n in add_nodes:
            lines.append(f"- {n}")
    else:
        lines.append("- _(none — all listed IDs already placed or keep-draft)_")
    lines.append("")
    lines.append("### Add / update edges")
    lines.append("")
    if add_edges:
        for e in add_edges:
            lines.append(f"- {e}")
    else:
        lines.append("- Review existing meta edges; attach new clauses to Trunk parents only.")
    lines.append("")
    lines.append("### Do not add")
    lines.append("")
    lines.append("- POC `evidence/` QPS/Recall numbers as `status=stable` must SLA ([[CON-POC-001]])")
    lines.append("- Entire `poc/<topic>/ndf/` tree as a second SoT")
    lines.append("- Unconfirmed amend proposals without draft→stable ID list")
    lines.append("")

    # Suggest next free IDs for common prefixes (informational)
    lines.append("### Suggested free IDs (if creating new clauses)")
    lines.append("")
    for pref in ("BEH", "API", "CON-SLA", "VER", "DEC"):
        # CON-SLA is awkward — use CON for scan of CON-SLA-*
        if pref == "CON-SLA":
            nums = []
            for cid in by_id:
                m = re.match(r"CON-SLA-(\d+)$", cid)
                if m:
                    nums.append(int(m.group(1)))
            sug = f"CON-SLA-{(max(nums)+1) if nums else 1:03d}"
        elif pref == "DEC":
            nums = []
            for cid in by_id:
                m = re.match(r"DEC-(\d+)$", cid)
                if m:
                    nums.append(int(m.group(1)))
            sug = f"DEC-{(max(nums)+1) if nums else 1:03d}"
        else:
            sug = suggest_next_id(by_id, pref)
        lines.append(f"- `{sug}`")
    lines.append("")

    lines.append("## 3. Prose provenance (POC 溯源 — required)")
    lines.append("")
    lines.append(
        "Any prose copied into Trunk (rationale, DEC body, VER notes, promote write-up) "
        "**MUST** retain source lines:"
    )
    lines.append("")
    lines.append("```text")
    lines.append(
        f"> source: poc/{topic.topic_id}/ndf/TOPIC.md ; "
        f"proposals/<file> ; "
        f"evidence/ ; "
        f"COMMITS.md @ {topic.latest_commit_hint}"
    )
    lines.append(f"> track: {mode} ; Topic: {topic.topic_id}")
    lines.append("```")
    lines.append("")
    lines.append("Per-artifact templates:")
    lines.append("")
    for p in topic.proposals:
        lines.append(f"- Proposal `{p.path}`:")
        lines.append("  ```text")
        lines.append(
            f"  > source: {p.path} (binder role={p.role}, status={p.status})"
        )
        lines.append(f"  > track: {mode} ; Topic: {topic.topic_id}")
        lines.append("  ```")
    if topic.evidence_dir:
        lines.append(
            f"- Evidence dir `{topic.evidence_dir.relative_to(ROOT)}`: cite round + date; "
            "do not paste as must SLA."
        )
    lines.append(
        f"- TOPIC narrative (`Active hypothesis` / results): "
        f"`poc/{topic.topic_id}/ndf/TOPIC.md`"
    )
    lines.append("")
    lines.append("**Forbidden:** pasting POC prose into `spec/00–50` without `source:` lines.")
    lines.append("")

    lines.append("## 4. Archive / binder checklist (not executed by this tool)")
    lines.append("")
    arch = f"spec/archive/{year_month}/poc-{topic.topic_id}/"
    if mode == "reject":
        lines.append(f"- [ ] Set `TOPIC.md` status → `rejected`")
        lines.append(
            "- [ ] Sync `NOTES.md` header status → `rejected` "
            "(or N/A if no NOTES.md) ([[BEH-025]])"
        )
        lines.append(f"- [ ] Write/update product DEC with `Rejects: {topic.topic_id}`")
        lines.append(f"- [ ] Move binder → `{arch}`")
        lines.append(
            "- [ ] If any topic-owned drafts existed: leave `deprecated` shells in Trunk"
        )
    elif mode == "promote":
        lines.append(f"- [ ] Set `TOPIC.md` status → `promoted`")
        lines.append(
            "- [ ] Sync `NOTES.md` header status → `promoted` "
            "(or N/A if no NOTES.md) ([[BEH-025]])"
        )
        lines.append(f"- [ ] Record `src_commit` + `spec_commit` in `COMMITS.md`")
        lines.append(f"- [ ] Move binder → `{arch}` (or summary pointer)")
        lines.append(f"- [ ] Commit trailers: `Topic:`, `Proposals:`, `Clauses:`, `Promotes: {topic.topic_id}`")
    else:
        lines.append("- [ ] Keep `TOPIC.md` status `exploring` (or note partial promote subset)")
        lines.append(
            "- [ ] NOTES.md: mark partial / still exploring "
            "(MUST NOT imply full close) (or N/A if no NOTES.md)"
        )
        lines.append("- [ ] Archive only closed amend proposals if desired; do not full-close topic")
        lines.append(f"- [ ] Promoted subset trailers: `Promotes: {topic.topic_id}` (partial)")
        lines.append(f"- [ ] Full binder archive `{arch}` deferred until topic closed")
    lines.append(f"- [ ] `spec/open/` stubs for Implemented proposals if still pointing at live paths")
    lines.append("")

    # §4b Semantic core (MODEL) — promote/partial only; [[META-004]] / [[BEH-019]]
    if mode == "reject":
        lines.append("## 4b. Semantic core (MODEL)")
        lines.append("")
        lines.append("Semantic core: **N/A (reject)** — no distill decision required ([[META-004]]).")
        lines.append("")
        lines.append("## 4c / 4d. Baseline & surface")
        lines.append("")
        lines.append(
            "Baseline invalidation / surface overlap: **N/A (reject)** "
            "([[BEH-025]])."
        )
        lines.append("")
    else:
        lines.append(
            "## 4b. Semantic core decision (MAY deliver; MUST decide; "
            "[[META-004]] / [[BEH-019]])"
        )
        lines.append("")
        lines.append(
            "Not executed by this tool. Missing MODEL is **not** a close/graphcheck failure."
        )
        lines.append("")
        lines.append(
            "- [ ] Decide: distill L3 semantic core for promoted behavior?"
        )
        lines.append(
            "  - [ ] No — reason: ________ (L1+VER enough / bugfix only / …)"
        )
        lines.append(
            "  - [ ] Defer — follow-up product proposal after Trunk green"
        )
        lines.append(
            "  - [ ] Yes — deliver in promote proposal or immediate follow-up:"
        )
        lines.append(
            "    - [ ] Add `spec/models/<name>.md` "
            "(oracle only: enable / timing / ops / invariants)"
        )
        lines.append(
            "    - [ ] Wire `model=<MODEL-ID>` on owning L1 clause(s)"
        )
        lines.append(
            "    - [ ] MUST NOT copy poc tree / git patches / COMMITS into `models/`"
        )
        lines.append(
            "- [ ] If Yes: after land, `python3 spec/meta/tools/ndf_index.py index` "
            "(model node + edge visible)"
        )
        lines.append("")

        lines.append(
            "## 4c. Baseline invalidation (Trunk moved; [[BEH-025]] / [[BEH-019]])"
        )
        lines.append("")
        lines.append("Not executed by this tool. Checklist for Agent/human after merge.")
        lines.append("")
        lines.append(
            "- [ ] Note new Trunk `src` SHA after this close "
            f"(topic=`{topic.topic_id}`, mode=`{mode}`)"
        )
        lines.append(
            "- [ ] List exploring topics: "
            "`python3 spec/meta/tools/ndf_index.py poc-topics`"
        )
        lines.append(
            "- [ ] Set `baseline_status=stale` on affected exploring topics "
            "(**including this topic if still exploring** after partial)"
        )
        lines.append(
            "- [ ] Disjoint-surface siblings MAY mark N/A + reason "
            "(still SHOULD refresh `baseline_trunk_sha` when convenient)"
        )
        lines.append(
            "- [ ] Do NOT treat pre-promote R0 tables as current-Trunk baseline"
        )
        lines.append(
            "- [ ] Before next round on a stale topic: re-measure R0 @ current Trunk"
        )
        lines.append("")

        lines.append(
            "## 4d. Surface overlap / conflict check ([[BEH-025]] / [[BEH-018]] §9)"
        )
        lines.append("")
        lines.append(
            "- [ ] Read this topic `explore_surface` from TOPIC.md"
        )
        lines.append(
            "- [ ] List exploring topics whose `explore_surface` intersects "
            "(from `poc-topics`)"
        )
        lines.append(
            "- [ ] For each overlap: confirm `depends_on_topics` / "
            "`conflicts_with_topics` OR resolve before claiming additive gains"
        )
        lines.append(
            "- [ ] Overlapping exploring siblings: `baseline_status=stale` "
            "AND `next_gate` includes conflict re-check vs promoted slice"
        )
        lines.append(
            "- [ ] MUST NOT promote two overlapping topics in the same close"
        )
        lines.append(
            "- [ ] Cross-topic ΔQPS: re-measure on same "
            "`baseline_trunk_sha` + protocol (gains not default-additive)"
        )
        lines.append("")

    report_path = f"spec/open/graphcheck-after-close-{topic.topic_id}.md"
    lines.append("## 5. Post-merge checks (MUST run after Trunk edits)")
    lines.append("")
    lines.append("After applying graph additions to Trunk SoT:")
    lines.append("")
    lines.append("```bash")
    lines.append(f"python3 spec/meta/tools/ndf_index.py index")
    lines.append(
        f"python3 spec/meta/tools/ndf_graphcheck.py --report {report_path}"
    )
    lines.append("```")
    lines.append("")
    lines.append("**Pass criteria for this close:**")
    lines.append("")
    lines.append(
        f"- `ndf_graphcheck` reports **no new hard errors** on touched IDs: "
        + ", ".join(f"`{i}`" for i in touched)
    )
    lines.append(
        "- Pre-existing warehouse cycles (e.g. meta `CHR-008`↔`BEH-018`) may remain; "
        "document them as pre-existing — but **this close must not** add "
        "`stable/must`→`draft` refine/depends edges."
    )
    lines.append("- Re-run `python3 spec/meta/tools/ndf_index.py poc-topics` to confirm binder status.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"_End of plan. Mode={mode}. No SoT files were modified by `{TOOL}`._"
    )
    lines.append("")
    return "\n".join(lines)


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        topic = load_topic(args.topic)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    by_id = ndx.load_graph(include_archive=False, include_open=False)
    promote_ids = set(args.ids or [])
    # partial: if no --ids, treat already-stable topic clauses as the promoted subset
    if args.mode == "partial" and not promote_ids:
        for cid in trunk_ids_for_topic(by_id, topic.topic_id) + topic.draft_ids:
            c = by_id.get(cid)
            if c and c.status == "stable":
                promote_ids.add(cid)

    ym = args.archive_month or datetime.now(timezone.utc).strftime("%Y-%m")
    report = build_plan_report(topic, by_id, args.mode, promote_ids, ym)
    print(report)
    if args.report:
        path = Path(args.report)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"\nwrote report: {path}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="emit close/round-trip plan (read-only)")
    p.add_argument("--topic", required=True, help="poc/<topic> id")
    p.add_argument(
        "--mode",
        required=True,
        choices=("promote", "reject", "partial"),
        help="close mode (BEH-019 / BEH-020 / partial)",
    )
    p.add_argument(
        "--ids",
        nargs="*",
        default=[],
        help="for partial/promote: clause IDs explicitly in scope",
    )
    p.add_argument("--report", type=str, help="also write Markdown report to PATH")
    p.add_argument(
        "--archive-month",
        default="",
        help="YYYY-MM for archive path suggestion (default: current UTC month)",
    )
    args = ap.parse_args()
    if args.cmd == "plan":
        return cmd_plan(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
