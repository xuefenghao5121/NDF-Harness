#!/usr/bin/env python3
"""NDF bind/provenance checker (clause↔commit↔binder↔path).

Checks reproducibility binding and binder dual-head (taxonomy «绑定溯源面»,
formerly labeled Layer B). Independent of ndf_index and ndf_graphcheck
(图语义面 / Layer A). Implements DEF-NDF-REPRO-BIND-GAP, BINDER-DUAL-HEAD,
OBS-GRAIN, and optional ZOMBIE-SPEC / SPEC-DRIFT heuristics.

Usage:
  python3 spec/meta/tools/ndf_bindcheck.py check --topic <topic>
  python3 spec/meta/tools/ndf_bindcheck.py check --all-topics \\
      --checks bind,dual,grain,zombie,drift --report tmp/ndf-bindcheck.md
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import ndf_close as ncl  # noqa: E402
import ndf_index as ndx  # noqa: E402
import ndf_report_io as rio  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
POC = ROOT / "poc"
TOOL = "spec/meta/tools/ndf_bindcheck.py"
DEFAULT_REPORT = "tmp/ndf-bindcheck.md"

DEFAULT_CHECKS = ("bind", "dual", "grain")
ALL_CHECKS = ("bind", "dual", "grain", "zombie", "drift")

HARD_DEFS = frozenset(
    {
        "DEF-NDF-REPRO-BIND-GAP",
        "DEF-NDF-BINDER-DUAL-HEAD",
    }
)

ID_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\b")
SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
PATH_TICK_RE = re.compile(
    r"`((?:src|poc|spec|tests|scripts)/[A-Za-z0-9_./+-]+\.(?:h|hpp|cpp|cc|c|py|md|sh))`"
)
BARE_SRC_RE = re.compile(
    r"\b((?:src|poc)/[A-Za-z0-9_./+-]+\.(?:h|hpp|cpp|cc|c|py))\b"
)
TRAILER_TOPIC = re.compile(r"(?im)^Topic:\s*(.+)$")
TRAILER_CLAUSES = re.compile(r"(?im)^Clauses:\s*(.+)$")
NOTE_MIN_LEN = 12
CLAUSES_PER_ROW_WARN = 5


@dataclass
class Finding:
    def_id: str
    severity: str  # error | warning
    topic: str
    kind: str  # missing_trailer | bad_ledger_sha | …
    message: str
    detail: str = ""
    loc: str = ""
    evidence: list[str] = field(default_factory=list)
    fix: str = ""
    # mermaid: nodes=(id,label), edges=(src,rel,tgt,highlight)
    diagram_nodes: list[tuple[str, str]] = field(default_factory=list)
    diagram_edges: list[tuple[str, str, str, bool]] = field(default_factory=list)


@dataclass
class LedgerRow:
    date: str
    code_commit: str
    ndf_commit: str
    proposals: str
    clauses: str
    protocol: str
    note: str
    line_no: int = 0

    @property
    def clause_ids(self) -> list[str]:
        return ID_RE.findall(self.clauses)

    @property
    def code_sha(self) -> str | None:
        m = SHA_RE.search(self.code_commit)
        return m.group(1) if m else None

    @property
    def ndf_sha(self) -> str | None:
        m = SHA_RE.search(self.ndf_commit)
        return m.group(1) if m else None


@dataclass
class TopicResult:
    topic: str
    findings: list[Finding] = field(default_factory=list)
    bipartite: list[tuple[str, str]] = field(default_factory=list)  # clause, sha
    skipped: list[str] = field(default_factory=list)


def git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return p.returncode, out.strip()
    except FileNotFoundError:
        return 127, "git not found"


def git_ok(sha: str) -> bool:
    code, _ = git("rev-parse", "--verify", f"{sha}^{{commit}}")
    return code == 0


def parse_ledger(path: Path) -> tuple[list[LedgerRow], bool]:
    """Parse COMMITS.md table. Returns (rows, not_backfilled_flag)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    not_backfilled = bool(
        re.search(r"(?i)not\s+backfilled|historical\s+commits", text)
    )
    rows: list[LedgerRow] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        head0 = cells[0].lower()
        if head0 in ("date", "---") or set(head0) <= {"-", ":"}:
            continue
        # pad note
        while len(cells) < 7:
            cells.append("")
        rows.append(
            LedgerRow(
                date=cells[0],
                code_commit=cells[1],
                ndf_commit=cells[2],
                proposals=cells[3],
                clauses=cells[4],
                protocol=cells[5],
                note=cells[6],
                line_no=i,
            )
        )
    return rows, not_backfilled


def list_topics() -> list[str]:
    out = []
    if not POC.is_dir():
        return out
    for d in sorted(POC.iterdir()):
        if d.is_dir() and (d / "ndf" / "TOPIC.md").is_file():
            out.append(d.name)
    return out


def commit_message(sha: str) -> str:
    code, out = git("log", "-1", "--format=%B", sha)
    return out if code == 0 else ""


def commits_touching_topic(topic: str, since: str | None) -> list[str]:
    args = ["log", "--format=%H", "--", f"poc/{topic}"]
    if since:
        args = ["log", f"--since={since}", "--format=%H", "--", f"poc/{topic}"]
    code, out = git(*args)
    if code != 0 or not out:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


_CODEISH_SUFFIXES = (
    ".cpp",
    ".h",
    ".hpp",
    ".cc",
    ".c",
    ".py",
    ".sh",
    ".S",
)
_CODEISH_NAMES = frozenset({"Makefile", "CMakeLists.txt", "meson.build"})


def commit_changed_codeish(sha: str, topic: str) -> bool:
    """True if commit touches code/scripts under topic (BEH-025 bind surface).

    Notes/README/markdown-only edits do not require Topic:/Clauses: trailers.
    """
    code, out = git("diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    if code != 0:
        return False
    prefix = f"poc/{topic}/"
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel.startswith(prefix):
            continue
        rest = rel[len(prefix) :]
        name = Path(rest).name
        if name in _CODEISH_NAMES:
            return True
        if rest.endswith(_CODEISH_SUFFIXES):
            return True
        if "/scripts/" in rest or rest.startswith("scripts/"):
            return True
    return False


def mid(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)[:48] or "n"


def commit_subject(sha: str) -> str:
    code, out = git("log", "-1", "--format=%s", sha)
    return out if code == 0 else "(unknown)"


def commit_date(sha: str) -> str:
    code, out = git("log", "-1", "--format=%cs", sha)
    return out if code == 0 else "?"


def commit_files_for_topic(sha: str, topic: str, limit: int = 12) -> list[str]:
    code, out = git("diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    if code != 0:
        return []
    prefix = f"poc/{topic}/"
    files = [ln.strip() for ln in out.splitlines() if ln.strip().startswith(prefix)]
    if not files:
        files = [ln.strip() for ln in out.splitlines() if ln.strip()][:limit]
    return files[:limit]


def check_bind(topic: str, info: ncl.TopicInfo, since: str | None) -> list[Finding]:
    findings: list[Finding] = []
    ledger_rel = f"poc/{topic}/ndf/COMMITS.md"
    topic_rel = f"poc/{topic}/ndf/TOPIC.md"

    if not info.commits_path or not info.commits_path.is_file():
        findings.append(
            Finding(
                "DEF-NDF-REPRO-BIND-GAP",
                "error",
                topic,
                "missing_ledger",
                "missing Commit Ledger COMMITS.md",
                loc=ledger_rel,
                evidence=[f"expected path: `{ledger_rel}`"],
                fix=f"Create `{ledger_rel}` per DEF-023 / BEH-025 and append rows for code commits.",
                diagram_nodes=[
                    (mid(topic), f"topic {topic}"),
                    ("LEDGER", "COMMITS.md MISSING"),
                ],
                diagram_edges=[(mid(topic), "needs", "LEDGER", True)],
            )
        )
        return findings

    rows, not_backfilled = parse_ledger(info.commits_path)
    ledger_clauses: set[str] = set()
    for row in rows:
        for sha in (row.code_sha, row.ndf_sha):
            if not sha:
                continue
            if not git_ok(sha):
                findings.append(
                    Finding(
                        "DEF-NDF-REPRO-BIND-GAP",
                        "error",
                        topic,
                        "bad_ledger_sha",
                        f"ledger sha not in git: {sha}",
                        loc=f"{ledger_rel}:{row.line_no}",
                        evidence=[
                            f"table date={row.date}",
                            f"code_commit={row.code_commit!r} ndf_commit={row.ndf_commit!r}",
                            f"clauses={row.clauses!r}",
                        ],
                        fix="Fix typo in COMMITS.md or restore the missing commit object.",
                        diagram_nodes=[
                            ("ROW", f"ledger L{row.line_no}"),
                            (mid(sha), f"{sha[:7]} NOT IN GIT"),
                        ],
                        diagram_edges=[("ROW", "points-to", mid(sha), True)],
                    )
                )
        for cid in row.clause_ids:
            ledger_clauses.add(cid)

    for sha in commits_touching_topic(topic, since):
        if not commit_changed_codeish(sha, topic):
            continue
        msg = commit_message(sha)
        short = sha[:7]
        has_topic = bool(TRAILER_TOPIC.search(msg))
        has_clauses = bool(TRAILER_CLAUSES.search(msg))
        if has_topic and has_clauses:
            continue
        missing = []
        if not has_topic:
            missing.append("Topic:")
        if not has_clauses:
            missing.append("Clauses:")
        files = commit_files_for_topic(sha, topic)
        subj = commit_subject(sha)
        in_ledger = False
        for row in rows:
            for cand in (row.code_sha, row.ndf_sha):
                if cand and (sha.startswith(cand) or cand.startswith(short)):
                    in_ledger = True
                    break
            if in_ledger:
                break
        # Ledger SoT documents historical gap without rewriting git (advise O1).
        if in_ledger:
            continue
        findings.append(
            Finding(
                "DEF-NDF-REPRO-BIND-GAP",
                "error",
                topic,
                "missing_trailer",
                f"code commit {short} missing trailers: {', '.join(missing)}",
                detail="BEH-025 requires Topic:/Clauses: on topic code commits",
                loc=files[0] if files else f"poc/{topic}/",
                evidence=[
                    f"sha: `{sha}`",
                    f"date: {commit_date(sha)}",
                    f"subject: {subj}",
                    f"missing: {', '.join(missing)}",
                    "in COMMITS.md ledger: no",
                    "files touched:",
                    *([f"  - `{f}`" for f in files] if files else ["  - (none listed)"]),
                ],
                fix=(
                    "Prefer append a COMMITS.md row documenting the SHA (no history rewrite),\n"
                    "or re-commit / amend (if not pushed) with trailers:\n"
                    f"  Topic: {topic}\n"
                    "  Clauses: <IDs>\n"
                    f"Then ensure `{ledger_rel}` lists the SHA."
                ),
                diagram_nodes=[
                    (mid(short), f"{short} {subj[:40]}"),
                    ("TRAILER", "Topic:/Clauses:"),
                    ("LEDGER", "COMMITS.md"),
                ],
                diagram_edges=[
                    (mid(short), "missing", "TRAILER", True),
                    (mid(short), "not-in-ledger", "LEDGER", True),
                ],
            )
        )

    if info.draft_ids and not not_backfilled:
        promoteish = bool(
            re.search(r"(?i)promot|draft\s*->\s*stable|draft→stable", info.text)
        )
        if promoteish:
            for cid in info.draft_ids:
                if cid not in ledger_clauses:
                    findings.append(
                        Finding(
                            "DEF-NDF-REPRO-BIND-GAP",
                            "warning",
                            topic,
                            "clause_unbound",
                            f"draft clause {cid} never appears in ledger clauses column",
                            loc=topic_rel,
                            evidence=[
                                f"TOPIC draft_clauses includes {cid}",
                                "TOPIC has promote-related notes",
                                f"no COMMITS.md row lists {cid} under clauses",
                                "ledger header has no “not backfilled” exemption",
                            ],
                            fix=(
                                f"Add a COMMITS.md row with clauses containing {cid}, "
                                "or add a ledger header note that historical commits are not backfilled."
                            ),
                            diagram_nodes=[
                                (mid(cid), f"{cid} (draft)"),
                                ("LEDGER", "COMMITS.md"),
                            ],
                            diagram_edges=[(mid(cid), "no-row", "LEDGER", True)],
                        )
                    )
    return findings


def topic_still_exploring(status: str) -> bool:
    s = status.lower()
    return any(k in s for k in ("explor", "active", "open", "pending")) and "promoted" not in s[:20]


def check_dual(
    topic: str, info: ncl.TopicInfo, by_id: dict[str, ndx.Clause]
) -> list[Finding]:
    findings: list[Finding] = []
    exploring = topic_still_exploring(info.status)
    topic_rel = f"poc/{topic}/ndf/TOPIC.md"

    for cid in info.draft_ids:
        draft_claim = bool(
            re.search(
                rf"(?is)\[\[{re.escape(cid)}\]\].*?status\s*=\s*draft"
                rf"|`status=draft`[^\n]*{re.escape(cid)}"
                rf"|{re.escape(cid)}[^\n]*status\s*=\s*draft",
                info.text,
            )
        )
        if not draft_claim:
            draft_claim = True

        c = by_id.get(cid)
        if c is None:
            findings.append(
                Finding(
                    "DEF-NDF-BINDER-DUAL-HEAD",
                    "warning",
                    topic,
                    "orphan_draft_id",
                    f"TOPIC draft_clauses lists {cid} but ID absent from Trunk graph",
                    loc=topic_rel,
                    evidence=[
                        f"TOPIC status: {info.status}",
                        f"{cid} listed under Draft clauses",
                        "ndf_index.load_graph(): ID not found",
                    ],
                    fix="Add Trunk draft clause, or remove stale ID from TOPIC draft_clauses.",
                    diagram_nodes=[
                        ("TOPIC", "TOPIC.md draft_clauses"),
                        (mid(cid), f"{cid} ABSENT"),
                    ],
                    diagram_edges=[("TOPIC", "lists", mid(cid), True)],
                )
            )
            continue
        trunk_status = (c.status or c.meta.get("status", "")).lower()
        trunk_loc = f"spec/{c.file}:{c.line}"
        if draft_claim and trunk_status == "stable":
            findings.append(
                Finding(
                    "DEF-NDF-BINDER-DUAL-HEAD",
                    "error",
                    topic,
                    "draft_vs_stable",
                    f"{cid}: TOPIC still draft registration but Trunk status=stable",
                    loc=f"{topic_rel} ↔ {trunk_loc}",
                    evidence=[
                        f"TOPIC topic_status: {info.status}",
                        f"TOPIC Draft clauses row still registers {cid} as draft",
                        f"Trunk {cid}: status={trunk_status} file=`spec/{c.file}` line={c.line}",
                        f"Trunk title: {c.title}",
                    ],
                    fix=(
                        f"Update `{topic_rel}`: move {cid} out of Draft clauses "
                        "(mark promoted / stable), or run close plan and set TOPIC status appropriately."
                    ),
                    diagram_nodes=[
                        ("TOPIC", f"TOPIC draft {cid}"),
                        (mid(cid), f"Trunk {cid} stable"),
                    ],
                    diagram_edges=[("TOPIC", "DUAL-HEAD", mid(cid), True)],
                )
            )
        elif (not draft_claim) and trunk_status == "draft" and exploring:
            findings.append(
                Finding(
                    "DEF-NDF-BINDER-DUAL-HEAD",
                    "error",
                    topic,
                    "stable_claim_vs_draft",
                    f"{cid}: TOPIC implies non-draft but Trunk still draft while exploring",
                    loc=f"{topic_rel} ↔ {trunk_loc}",
                    evidence=[
                        f"TOPIC status: {info.status}",
                        f"Trunk {cid}: status={trunk_status} @ `spec/{c.file}`",
                    ],
                    fix="Either promote Trunk clause to stable, or keep TOPIC draft registration consistent.",
                    diagram_nodes=[
                        ("TOPIC", f"TOPIC non-draft claim"),
                        (mid(cid), f"Trunk {cid} draft"),
                    ],
                    diagram_edges=[("TOPIC", "DUAL-HEAD", mid(cid), True)],
                )
            )

    trunk_topic_ids = set(ncl.trunk_ids_for_topic(by_id, topic))
    known = set(info.draft_ids)
    for prop in info.proposals:
        known.update(ID_RE.findall(prop.path + " " + prop.role))
    known.update(ID_RE.findall(info.text))
    for cid in sorted(trunk_topic_ids - known):
        c = by_id[cid]
        findings.append(
            Finding(
                "DEF-NDF-BINDER-DUAL-HEAD",
                "warning",
                topic,
                "trunk_topic_unlisted",
                f"Trunk topic={topic} clause {cid} not listed in TOPIC draft_clauses/proposals surface",
                loc=f"spec/{c.file}:{c.line}",
                evidence=[
                    f"Trunk meta topic={topic}",
                    f"not found in TOPIC draft_clauses / proposals / body IDs",
                ],
                fix=f"Add {cid} to TOPIC draft_clauses or proposals table for binder visibility.",
                diagram_nodes=[
                    (mid(cid), f"Trunk {cid}"),
                    ("TOPIC", "TOPIC.md"),
                ],
                diagram_edges=[(mid(cid), "missing-from", "TOPIC", True)],
            )
        )
    return findings


def check_grain(topic: str, info: ncl.TopicInfo) -> list[Finding]:
    findings: list[Finding] = []
    if not info.commits_path or not info.commits_path.is_file():
        return findings
    ledger_rel = f"poc/{topic}/ndf/COMMITS.md"
    rows, _ = parse_ledger(info.commits_path)
    by_proto: dict[str, list[LedgerRow]] = defaultdict(list)
    for row in rows:
        if row.code_sha:
            by_proto[row.protocol.strip() or "(empty)"].append(row)

    for proto, group in by_proto.items():
        if len(group) < 2:
            continue
        if len(group) >= 2 and all(len(r.note.strip()) < NOTE_MIN_LEN for r in group):
            shas = sorted({r.code_sha[:7] for r in group if r.code_sha})
            findings.append(
                Finding(
                    "DEF-NDF-OBS-GRAIN",
                    "warning",
                    topic,
                    "coarse_protocol",
                    f"protocol {proto!r}: multiple code_commits ({', '.join(shas)}) with empty/short notes",
                    loc=ledger_rel,
                    evidence=[
                        f"protocol cell: {proto!r}",
                        "rows:",
                        *[
                            f"  - L{r.line_no} code={r.code_sha and r.code_sha[:7]} note={r.note!r}"
                            for r in group
                        ],
                        "checklist: cannot tell which measurement maps to which SHA from ledger alone",
                    ],
                    fix="Lengthen `note` per row (what was measured / which gate) without forcing 1:1 commits.",
                    diagram_nodes=[
                        ("PROTO", f"protocol {proto[:24]}"),
                        *[(mid(s), s) for s in shas],
                    ],
                    diagram_edges=[("PROTO", "covers", mid(s), True) for s in shas],
                )
            )

    for row in rows:
        ids = row.clause_ids
        if len(ids) > CLAUSES_PER_ROW_WARN and len(row.note.strip()) < NOTE_MIN_LEN:
            findings.append(
                Finding(
                    "DEF-NDF-OBS-GRAIN",
                    "warning",
                    topic,
                    "crowded_clauses",
                    f"row {row.date}: {len(ids)} clause IDs without disambiguating note",
                    loc=f"{ledger_rel}:{row.line_no}",
                    evidence=[
                        f"clauses={row.clauses}",
                        f"note={row.note!r} (len={len(row.note.strip())})",
                    ],
                    fix="Split rows or add a note that names which clause was exercised.",
                )
            )
    return findings


def extract_path_tokens(text: str, topic: str) -> set[str]:
    paths: set[str] = set()
    for m in PATH_TICK_RE.finditer(text):
        paths.add(m.group(1))
    for m in BARE_SRC_RE.finditer(text):
        paths.add(m.group(1))
    # also allow poc/<topic>/... without extension filter already covered
    for m in re.finditer(rf"`(poc/{re.escape(topic)}/[^`]+)`", text):
        paths.add(m.group(1))
    return paths


def check_zombie(
    topic: str, info: ncl.TopicInfo, by_id: dict[str, ndx.Clause]
) -> list[Finding]:
    findings: list[Finding] = []
    blobs: list[str] = [info.text]
    for prop in info.proposals:
        p = Path(prop.path)
        if not p.is_absolute():
            cand = ROOT / prop.path
            if cand.is_file():
                blobs.append(cand.read_text(encoding="utf-8", errors="replace"))
        elif p.is_file():
            blobs.append(p.read_text(encoding="utf-8", errors="replace"))

    for cid in info.draft_ids:
        c = by_id.get(cid)
        if c:
            # body is not stored; re-read file around id is heavy — use file text
            fp = ROOT / "spec" / c.file
            if fp.is_file():
                blobs.append(fp.read_text(encoding="utf-8", errors="replace"))

    for cid in ncl.trunk_ids_for_topic(by_id, topic):
        c = by_id.get(cid)
        if not c:
            continue
        fp = ROOT / "spec" / c.file
        if fp.is_file():
            blobs.append(fp.read_text(encoding="utf-8", errors="replace"))

    seen: set[str] = set()
    for blob in blobs:
        for rel in extract_path_tokens(blob, topic):
            if rel in seen:
                continue
            seen.add(rel)
            # skip archive/open proposal paths that are historical
            if "/archive/" in rel or rel.startswith("spec/open/"):
                continue
            if not (ROOT / rel).exists():
                findings.append(
                    Finding(
                        "DEF-NDF-ZOMBIE-SPEC",
                        "warning",
                        topic,
                        "missing_path",
                        f"referenced path missing: {rel}",
                        loc=rel,
                        evidence=[
                            f"token extracted from TOPIC / proposals / topic= clauses",
                            f"Path.exists(`{rel}`) = False",
                            "v1 path-level only; symbol-level zombie is v2",
                        ],
                        fix="Fix the path reference, restore the file, or remove the stale citation.",
                        diagram_nodes=[
                            ("SPEC", "clause/proposal text"),
                            (mid(rel), f"{rel} MISSING"),
                        ],
                        diagram_edges=[("SPEC", "cites", mid(rel), True)],
                    )
                )
    return findings


def check_drift(
    topic: str, info: ncl.TopicInfo, by_id: dict[str, ndx.Clause], since: str | None
) -> list[Finding]:
    """Timeline suspicion: files changed recently, clause cites them, no ledger bind in window."""
    findings: list[Finding] = []
    since = since or "90 days ago"
    code, out = git(
        "log",
        f"--since={since}",
        "--name-only",
        "--pretty=format:",
        "--",
        "src/",
        f"poc/{topic}/",
    )
    if code != 0:
        return findings
    changed = {ln.strip() for ln in out.splitlines() if ln.strip()}
    if not changed:
        return findings

    # ledger ndf/code shas in window
    bound_clauses: set[str] = set()
    if info.commits_path and info.commits_path.is_file():
        rows, _ = parse_ledger(info.commits_path)
        for row in rows:
            for sha in (row.code_sha, row.ndf_sha):
                if not sha or not git_ok(sha):
                    continue
                # is sha in since window?
                rc, _ = git("merge-base", "--is-ancestor", sha, "HEAD")
                if rc != 0:
                    continue
                rc2, date_s = git("log", "-1", "--format=%ct", sha)
                # also check trailers on code commits in window
                for cid in row.clause_ids:
                    bound_clauses.add(cid)

    for sha in commits_touching_topic(topic, since):
        msg = commit_message(sha)
        m = TRAILER_CLAUSES.search(msg)
        if m:
            bound_clauses.update(ID_RE.findall(m.group(1)))
    # also scan src/ commits for Clauses trailers
    code, out = git("log", f"--since={since}", "--format=%H", "--", "src/")
    if code == 0:
        for sha in out.splitlines():
            sha = sha.strip()
            if not sha:
                continue
            msg = commit_message(sha)
            m = TRAILER_CLAUSES.search(msg)
            if m:
                bound_clauses.update(ID_RE.findall(m.group(1)))

    candidate_ids = set(info.draft_ids) | set(ncl.trunk_ids_for_topic(by_id, topic))
    for cid in sorted(candidate_ids):
        c = by_id.get(cid)
        texts = [info.text]
        if c:
            fp = ROOT / "spec" / c.file
            if fp.is_file():
                texts.append(fp.read_text(encoding="utf-8", errors="replace"))
            model = c.meta.get("model", "")
            if model:
                texts.append(model)
        cited = set()
        for t in texts:
            cited |= extract_path_tokens(t, topic)
            # also model= paths
            for m in re.finditer(r"models/[A-Za-z0-9_./+-]+", t):
                cited.add(m.group(0))
        hit = cited & changed
        if hit and cid not in bound_clauses:
            findings.append(
                Finding(
                    "DEF-NDF-SPEC-DRIFT",
                    "warning",
                    topic,
                    "timeline_unbind",
                    f"{cid}: cites paths changed since {since!r} but no ledger/trailer bind in window",
                    loc=f"spec/{c.file}" if c else f"poc/{topic}/ndf/TOPIC.md",
                    evidence=[
                        f"since window: {since!r}",
                        f"path intersect (sample): {sorted(hit)[:8]}",
                        f"{cid} not in ledger clauses / trailer Clauses: for this window",
                        "non-graph: whether must still holds needs VER/human",
                    ],
                    fix=(
                        "Add COMMITS.md row / commit trailers binding this clause to the "
                        "change window, or update the clause text if the path cite is stale."
                    ),
                    diagram_nodes=[
                        (mid(cid), cid),
                        ("FILES", "changed paths"),
                        ("BIND", "ledger/trailer"),
                    ],
                    diagram_edges=[
                        (mid(cid), "cites", "FILES", False),
                        (mid(cid), "no-bind", "BIND", True),
                    ],
                )
            )
    return findings


def check_design_docs(topic: str, info: ncl.TopicInfo) -> list[Finding]:
    """BEH-025 design surface: DESIGN.md + INTERFACE.md (warning if missing).

    Historical topics may lack these files; do not hard-fail the binder suite.
    New opens MUST create them (process + AGENTS); this check only warns.
    """
    findings: list[Finding] = []
    ndf = POC / topic / "ndf"
    for name, kind in (
        ("DESIGN.md", "missing_design"),
        ("INTERFACE.md", "missing_interface"),
    ):
        path = ndf / name
        if path.is_file():
            continue
        findings.append(
            Finding(
                "BEH-025",
                "warning",
                topic,
                kind,
                f"binder missing {name} (design surface; required before new code)",
                loc=f"poc/{topic}/ndf/{name}",
                evidence=[
                    f"TOPIC status: {info.status}",
                    f"expected: poc/{topic}/ndf/{name}",
                    "template: spec/meta/templates/poc/"
                    + ("DESIGN.md.stub" if name.startswith("DESIGN") else "INTERFACE.md.stub"),
                ],
                fix=(
                    f"Copy stub to poc/{topic}/ndf/{name} and fill sections "
                    "(warning only for historical topics; MUST for new opens)."
                ),
                diagram_nodes=[
                    ("TOPIC", "TOPIC.md"),
                    ("MISS", name),
                ],
                diagram_edges=[("TOPIC", "lacks", "MISS", True)],
            )
        )
    return findings


def bipartite_summary(info: ncl.TopicInfo) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not info.commits_path or not info.commits_path.is_file():
        return pairs
    rows, _ = parse_ledger(info.commits_path)
    for row in rows:
        sha = row.code_sha or row.ndf_sha
        if not sha:
            continue
        for cid in row.clause_ids:
            pairs.append((cid, sha[:10]))
    return pairs


def run_topic(
    topic: str,
    checks: set[str],
    by_id: dict[str, ndx.Clause],
    since: str | None,
) -> TopicResult:
    result = TopicResult(topic=topic)
    try:
        info = ncl.load_topic(topic)
    except FileNotFoundError as e:
        result.findings.append(
            Finding(
                "DEF-NDF-REPRO-BIND-GAP",
                "error",
                topic,
                "missing_binder",
                str(e),
                loc=f"poc/{topic}/ndf/TOPIC.md",
                evidence=[f"missing binder: poc/{topic}/ndf/TOPIC.md"],
                fix="Create TOPIC.md binder per BEH-025 before running bindcheck.",
            )
        )
        return result

    result.bipartite = bipartite_summary(info)

    # Always scan design surface (warnings only; not gated by --checks)
    result.findings.extend(check_design_docs(topic, info))

    if "bind" in checks:
        result.findings.extend(check_bind(topic, info, since))
    if "dual" in checks:
        result.findings.extend(check_dual(topic, info, by_id))
    if "grain" in checks:
        result.findings.extend(check_grain(topic, info))
    if "zombie" in checks:
        result.skipped.append(
            "ZOMBIE-SPEC: path-level heuristic only (no C++ symbol table; v2)"
        )
        result.findings.extend(check_zombie(topic, info, by_id))
    if "drift" in checks:
        result.skipped.append(
            "SPEC-DRIFT: timeline heuristic only; must-validity is non-graph"
        )
        result.findings.extend(check_drift(topic, info, by_id, since))
    return result


def render_mermaid(f: Finding) -> str:
    if not f.diagram_nodes:
        return ""
    lines = ["```mermaid", "flowchart LR"]
    seen: set[str] = set()
    for nid, label in f.diagram_nodes:
        if nid in seen:
            continue
        seen.add(nid)
        safe = label.replace('"', "'")[:60]
        lines.append(f'  {nid}["{safe}"]')
    for src, rel, tgt, bad in f.diagram_edges:
        arrow = "-.->|" if bad else "-->|"
        lines.append(f"  {src} {arrow}{rel}|{tgt}")
    lines.append("```")
    return "\n".join(lines)


def render_finding_block(f: Finding, index: int) -> str:
    lines = [
        f"**{f.severity}** `{f.kind}` ({f.topic}): {f.message}",
        f"  def: `{f.def_id}`",
    ]
    if f.loc:
        lines.append(f"  loc: `{f.loc}`")
    if f.detail:
        lines.append(f"  note: {f.detail}")
    if f.evidence:
        lines.append("")
        lines.append("### evidence")
        lines.append("")
        for e in f.evidence:
            if e.startswith("  -"):
                lines.append(e)
            elif e.endswith(":") and not e.startswith("`"):
                lines.append(f"- {e}")
            else:
                lines.append(f"- {e}")
    if f.fix:
        lines.append("")
        lines.append("### fix")
        lines.append("")
        lines.append(f.fix)
    diag = render_mermaid(f)
    if diag:
        lines.append("")
        lines.append(f"### {f.kind} #{index}")
        lines.append("")
        lines.append(diag)
    return "\n".join(lines)


def bipartite_mermaid(topic: str, pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return "_no ledger clause↔sha edges_"
    lines = ["```mermaid", "flowchart LR"]
    seen: set[str] = set()
    for cid, sha in pairs[:40]:
        c, s = mid(cid), mid(sha)
        if c not in seen:
            lines.append(f'  {c}["{cid}"]')
            seen.add(c)
        if s not in seen:
            lines.append(f'  {s}["{sha}"]')
            seen.add(s)
        lines.append(f"  {c} -->|ledger|{s}")
    lines.append("```")
    if len(pairs) > 40:
        lines.append(f"\n_… +{len(pairs) - 40} more edges omitted_")
    return "\n".join(lines)


def render_topic_figure(topic: str, findings: list[Finding]) -> str:
    """Aggregate finding diagram edges for one topic into a single mermaid."""
    nodes: dict[str, str] = {}
    edges: list[tuple[str, str, str, bool]] = []
    seen_e: set[tuple[str, str, str, bool]] = set()
    for f in findings:
        for nid, lab in f.diagram_nodes:
            nodes.setdefault(nid, lab)
        for e in f.diagram_edges:
            if e not in seen_e:
                seen_e.add(e)
                edges.append(e)
    if not nodes and not edges:
        # fallback: kind → count nodes
        counts: dict[str, int] = defaultdict(int)
        for f in findings:
            counts[f.kind] += 1
        if not counts:
            return f"### topic `{topic}`\n\n_(no findings)_\n"
        lines = [
            f"### topic `{topic}`",
            "",
            "```mermaid",
            "flowchart LR",
            f'  T["{topic}"]',
        ]
        for kind, n in sorted(counts.items()):
            kid = mid(kind)
            lines.append(f'  {kid}["{kind}×{n}"]')
            lines.append(f"  T -->|finding|{kid}")
        lines.append("```")
        lines.append("")
        return "\n".join(lines)

    lines = [
        f"### topic `{topic}`",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for nid, lab in sorted(nodes.items()):
        safe = lab.replace('"', "'")
        lines.append(f'  {nid}["{safe}"]')
    for src, rel, tgt, bad in edges:
        arrow = "-.->|" if bad else "-->|"
        lines.append(f"  {src} {arrow}{rel}|{tgt}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def build_report(
    results: list[TopicResult],
    checks: set[str],
    max_issues: int = 40,
    detail: bool = False,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_f = [f for tr in results for f in tr.findings]
    errors = [f for f in all_f if f.severity == "error"]
    warnings = [f for f in all_f if f.severity == "warning"]

    lines: list[str] = [
        "# NDF bindcheck report",
        "",
        f"> Generated by `{TOOL}` at {now}",
        "",
        f"- topics: {len(results)} ({', '.join(tr.topic for tr in results)})",
        f"- checks: {','.join(sorted(checks))}",
        f"- hard_errors: {len(errors)}",
        f"- warnings: {len(warnings)}",
        "",
        "## Summary by kind",
        "",
        "| kind | def | count | severity |",
        "|------|-----|------:|----------|",
    ]
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for f in all_f:
        counts[(f.kind, f.def_id, f.severity)] += 1
    for (kind, def_id, sev), n in sorted(
        counts.items(), key=lambda x: (x[0][2], x[0][0])
    ):
        short_def = def_id.replace("DEF-NDF-", "")
        lines.append(f"| `{kind}` | {short_def} | {n} | {sev} |")
    lines.append("")

    lines.append("## Issue index")
    lines.append("")
    if not all_f:
        lines.append("_(none)_")
        lines.append("")
    else:
        lines.append("| # | sev | kind | topic | message | loc |")
        lines.append("|--:|-----|------|-------|---------|-----|")
        for i, f in enumerate(all_f, 1):
            msg = f.message.replace("|", "\\|")
            loc = f.loc.replace("|", "\\|")
            lines.append(
                f"| {i} | {f.severity} | `{f.kind}` | `{f.topic}` | {msg} | `{loc}` |"
            )
        lines.append("")

    lines.append("## Figures by topic")
    lines.append("")
    any_fig = False
    for tr in results:
        if not tr.findings:
            continue
        any_fig = True
        lines.append(render_topic_figure(tr.topic, tr.findings))
    if not any_fig:
        lines.append("_(none)_")
        lines.append("")

    lines.append("## Appendix: ledger bipartite (clause↔sha)")
    lines.append("")
    for tr in results:
        lines.append(f"### topic `{tr.topic}`")
        lines.append("")
        lines.append(bipartite_mermaid(tr.topic, tr.bipartite))
        lines.append("")
        for s in tr.skipped:
            lines.append(f"- note: {s}")
        if tr.skipped:
            lines.append("")

    if detail:
        lines.append("## Appendix: per-finding detail")
        lines.append("")

        def emit(title: str, items: list[Finding]) -> None:
            lines.append(f"### {title}")
            lines.append("")
            if not items:
                lines.append("_(none)_")
                lines.append("")
                return
            for i, f in enumerate(items[:max_issues], 1):
                lines.append(render_finding_block(f, i))
                lines.append("")
            if len(items) > max_issues:
                lines.append(
                    f"_… +{len(items) - max_issues} more omitted (`--max-issues`)_"
                )
                lines.append("")

        emit("Hard errors", errors)
        emit("Warnings", warnings)

    return "\n".join(lines).rstrip() + "\n"


def format_console_summary(results: list[TopicResult], checks: set[str]) -> str:
    """Short stdout summary; full detail lives in --report."""
    all_f = [f for tr in results for f in tr.findings]
    errors = sum(1 for f in all_f if f.severity == "error")
    warnings = sum(1 for f in all_f if f.severity == "warning")
    lines = [
        f"# ndf_bindcheck  checks={','.join(sorted(checks))}",
        f"summary: {errors} error(s), {warnings} warning(s)",
        "",
    ]
    for f in all_f:
        lines.append(f"- [{f.severity}] `{f.kind}` ({f.topic}) {f.message}")
        if f.loc:
            lines.append(f"  loc: `{f.loc}`")
    return "\n".join(lines).rstrip() + "\n"


def cmd_check(args: argparse.Namespace) -> int:
    checks_raw = [c.strip() for c in args.checks.split(",") if c.strip()]
    checks = set(checks_raw)
    unknown = checks - set(ALL_CHECKS)
    if unknown:
        print(f"unknown checks: {sorted(unknown)}", file=sys.stderr)
        return 2
    if not checks:
        print("no checks selected", file=sys.stderr)
        return 2

    try:
        report_path = rio.resolve_report_path(args.report, DEFAULT_REPORT)
    except rio.ReportPathError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.all_topics:
        topics = list_topics()
    elif args.topic:
        topics = [args.topic]
    else:
        print("need --topic or --all-topics", file=sys.stderr)
        return 2

    by_id = ndx.load_graph(include_archive=False, include_open=False)
    results = [run_topic(t, checks, by_id, args.since) for t in topics]
    report = build_report(
        results, checks, max_issues=args.max_issues, detail=args.detail
    )

    written = rio.write_report(report_path, report)
    if written is not None:
        print(format_console_summary(results, checks))
        print(f"wrote report: {written}")

    hard = any(
        f.severity == "error" and f.def_id in HARD_DEFS
        for tr in results
        for f in tr.findings
    )
    return 1 if hard else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="NDF bindcheck: ledger/trailer bind, binder dual-head, obs grain"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser(
        "check",
        help="Run bind/dual/grain (+ optional zombie/drift) for topic(s)",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic", help="POC topic id under poc/")
    g.add_argument("--all-topics", action="store_true")
    p.add_argument(
        "--checks",
        default=",".join(DEFAULT_CHECKS),
        help=f"comma list from {','.join(ALL_CHECKS)} (default: {','.join(DEFAULT_CHECKS)})",
    )
    p.add_argument("--since", default=None, help="git --since for bind/drift window")
    p.add_argument(
        "--report",
        default=DEFAULT_REPORT,
        help=f"Markdown report path (default: {DEFAULT_REPORT}); '-' = stdout only; "
        "MUST NOT be under spec/",
    )
    p.add_argument(
        "--max-issues",
        type=int,
        default=40,
        help="max issues in --detail appendix (default 40)",
    )
    p.add_argument(
        "--detail",
        action="store_true",
        help="include per-finding evidence/fix blocks in report appendix",
    )
    p.set_defaults(func=cmd_check)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
