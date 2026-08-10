#!/usr/bin/env python3
"""NDF process: resolve TOPIC perf_baseline card (META-007 / BEH-025).

Process binder check — not product SLA/QPS logic. Validates TOPIC→card fields,
optional cfg-*/bl-* path resolution under the product verification tree.

Agent-facing: resolve TOPIC.perf_baseline → card summary (sha / config / vs / numbers hint).

Usage:
  python3 spec/meta/tools/ndf_perf_baseline.py show --topic <topic>
  python3 spec/meta/tools/ndf_perf_baseline.py check --topic <topic>
  python3 spec/meta/tools/ndf_perf_baseline.py check --all-exploring

Exit 1 on check failures. Does not rewrite SoT.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POC = ROOT / "poc"
CFG_DIR = ROOT / "spec" / "50-verification" / "configs"
BL_DIR = ROOT / "spec" / "50-verification" / "baselines"


@dataclass
class Finding:
    severity: str  # error | warning
    kind: str
    topic: str
    message: str


def header_field(text: str, key: str) -> str | None:
    """Parse `> key: value` from leading blockquote headers."""
    pat = re.compile(rf"^>\s*{re.escape(key)}\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
    m = pat.search(text)
    return m.group(1).strip() if m else None


def has_section(text: str, title: str) -> bool:
    return bool(re.search(rf"^##\s+{re.escape(title)}\s*$", text, re.MULTILINE | re.IGNORECASE))


def section_body(text: str, title: str) -> str:
    m = re.search(
        rf"^##\s+{re.escape(title)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    return (m.group(1) if m else "").strip()


def resolve_card_path(topic: str, perf_baseline: str) -> Path:
    """perf_baseline is usually ndf/PERF_BASELINE.md relative to topic root."""
    topic_root = POC / topic
    p = perf_baseline.strip()
    if p.startswith("ndf/"):
        return topic_root / p
    if p.startswith("poc/"):
        return ROOT / p
    if Path(p).is_absolute():
        return Path(p)
    # relative to ndf/ or topic root
    cand = topic_root / "ndf" / p
    if cand.is_file():
        return cand
    return topic_root / p


def list_exploring_topics() -> list[str]:
    out: list[str] = []
    if not POC.is_dir():
        return out
    for d in sorted(POC.iterdir()):
        topic_md = d / "ndf" / "TOPIC.md"
        if not topic_md.is_file():
            continue
        text = topic_md.read_text(encoding="utf-8", errors="replace")
        status = (header_field(text, "status") or "").split()[0].lower()
        if status == "exploring":
            out.append(d.name)
    return out


def cfg_exists(config_id: str) -> bool:
    cid = config_id.strip()
    if not cid or cid.lower() == "experimental":
        return True
    return (CFG_DIR / f"{cid}.md").is_file()


def bl_exists(baseline_id: str) -> bool:
    bid = baseline_id.strip()
    if not bid:
        return False
    return (BL_DIR / f"{bid}.md").is_file()


@dataclass
class CardView:
    topic: str
    topic_sha: str | None = None
    topic_status: str | None = None
    perf_baseline: str | None = None
    card_path: Path | None = None
    trunk_sha: str | None = None
    config_id: str | None = None
    protocol: str | None = None
    status: str | None = None
    vs: str | None = None
    numbers_preview: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]


def inspect_topic(topic: str, require_card: bool) -> CardView:
    view = CardView(topic=topic)
    topic_md = POC / topic / "ndf" / "TOPIC.md"
    if not topic_md.is_file():
        view.findings.append(
            Finding("error", "missing_topic", topic, f"missing {topic_md.relative_to(ROOT)}")
        )
        return view

    ttext = topic_md.read_text(encoding="utf-8", errors="replace")
    view.topic_sha = header_field(ttext, "baseline_trunk_sha")
    view.topic_status = header_field(ttext, "baseline_status")
    view.perf_baseline = header_field(ttext, "perf_baseline")
    topic_life = (header_field(ttext, "status") or "").split()[0].lower()
    closed = topic_life in {"promoted", "rejected"}

    if not view.perf_baseline:
        # exploring / blocked: error when require_card; closed topics: warning only
        if closed:
            sev = "warning"
        elif require_card:
            sev = "error"
        else:
            sev = "warning"
        view.findings.append(
            Finding(
                sev,
                "missing_perf_baseline_field",
                topic,
                "TOPIC lacks `perf_baseline:` "
                + ("(ok to skip on closed topics)" if closed else "(required after R0 / for exploring)"),
            )
        )
        return view

    card = resolve_card_path(topic, view.perf_baseline)
    view.card_path = card
    if not card.is_file():
        view.findings.append(
            Finding(
                "error",
                "missing_card",
                topic,
                f"perf_baseline path not found: {view.perf_baseline}",
            )
        )
        return view

    ctext = card.read_text(encoding="utf-8", errors="replace")
    view.trunk_sha = header_field(ctext, "trunk_sha")
    view.config_id = header_field(ctext, "config_id")
    view.protocol = header_field(ctext, "protocol")
    view.status = header_field(ctext, "status")
    view.vs = header_field(ctext, "vs")

    if not view.trunk_sha:
        view.findings.append(
            Finding("error", "missing_trunk_sha", topic, "card missing `trunk_sha:`")
        )
    if not view.config_id and "experimental" not in ctext.lower():
        # allow experimental section without config_id if Config has inline env
        if not has_section(ctext, "Config"):
            view.findings.append(
                Finding(
                    "error",
                    "missing_config",
                    topic,
                    "card missing `config_id:` and Config section",
                )
            )
        else:
            view.findings.append(
                Finding(
                    "warning",
                    "no_config_id",
                    topic,
                    "no `config_id:`; ensure Config section has full env (experimental)",
                )
            )

    if view.config_id:
        for part in re.split(r"[,;\s]+", view.config_id):
            if not part:
                continue
            if part.lower() == "experimental":
                continue
            if not cfg_exists(part):
                view.findings.append(
                    Finding(
                        "error",
                        "unknown_config",
                        topic,
                        f"config_id not found: {part} (expected {CFG_DIR.name}/{part}.md)",
                    )
                )

    if not has_section(ctext, "Config"):
        view.findings.append(
            Finding("error", "missing_config_section", topic, "card missing ## Config")
        )
    if not has_section(ctext, "Numbers"):
        view.findings.append(
            Finding("error", "missing_numbers_section", topic, "card missing ## Numbers")
        )
    else:
        body = section_body(ctext, "Numbers")
        view.numbers_preview = " ".join(body.split())[:240]
        if len(body) < 8:
            view.findings.append(
                Finding("error", "empty_numbers", topic, "## Numbers is empty")
            )
        # if claims vs gold, check bl exists
        if view.vs:
            if not bl_exists(view.vs):
                view.findings.append(
                    Finding(
                        "error",
                        "unknown_vs",
                        topic,
                        f"vs baseline not found: {view.vs}",
                    )
                )
            elif "沿用" not in body and view.vs not in body and "bl-trunk" not in body.lower():
                view.findings.append(
                    Finding(
                        "warning",
                        "vs_unmentioned",
                        topic,
                        f"Numbers does not mention vs `{view.vs}` (ok if own R0 table)",
                    )
                )

    if view.topic_sha and view.trunk_sha:
        ts = view.topic_sha.strip()
        cs = view.trunk_sha.strip()
        if not (cs.startswith(ts) or ts.startswith(cs) or cs[:7] == ts[:7]):
            view.findings.append(
                Finding(
                    "error",
                    "sha_mismatch",
                    topic,
                    f"TOPIC baseline_trunk_sha={ts} != card trunk_sha={cs}",
                )
            )

    if topic_life == "exploring" and require_card and not view.perf_baseline:
        pass  # already handled

    return view


def print_show(view: CardView) -> None:
    print(f"topic: {view.topic}")
    print(f"  TOPIC baseline_trunk_sha: {view.topic_sha or '(none)'}")
    print(f"  TOPIC baseline_status:    {view.topic_status or '(none)'}")
    print(f"  TOPIC perf_baseline:      {view.perf_baseline or '(none)'}")
    if view.card_path:
        try:
            rel = view.card_path.relative_to(ROOT)
        except ValueError:
            rel = view.card_path
        print(f"  card: {rel}")
    print(f"  trunk_sha:  {view.trunk_sha or '(none)'}")
    print(f"  config_id:  {view.config_id or '(none)'}")
    print(f"  protocol:   {view.protocol or '(none)'}")
    print(f"  status:     {view.status or '(none)'}")
    print(f"  vs:         {view.vs or '(none)'}")
    if view.numbers_preview:
        print(f"  numbers:    {view.numbers_preview}")
    for f in view.findings:
        print(f"  [{f.severity}] {f.kind}: {f.message}")


def cmd_show(args: argparse.Namespace) -> int:
    view = inspect_topic(args.topic, require_card=False)
    print_show(view)
    return 1 if view.errors else 0


def cmd_check(args: argparse.Namespace) -> int:
    topics = list_exploring_topics() if args.all_exploring else [args.topic]
    if not topics:
        print("no topics to check", file=sys.stderr)
        return 2
    rc = 0
    for topic in topics:
        view = inspect_topic(topic, require_card=True)
        print_show(view)
        print()
        if view.errors:
            rc = 1
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    show = sub.add_parser("show", help="Print resolved perf baseline card")
    show.add_argument("--topic", required=True)
    show.set_defaults(func=cmd_show)

    check = sub.add_parser("check", help="Validate TOPIC→card fields")
    g = check.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic")
    g.add_argument("--all-exploring", action="store_true")
    check.set_defaults(func=cmd_check)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
