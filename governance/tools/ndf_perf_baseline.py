#!/usr/bin/env python3
"""NDF process: resolve TOPIC perf_baseline card (META-007 / BEH-025).

Process binder check — not product SLA/QPS logic. Validates TOPIC→card unique golden
bind (vs × config_id × measure), optional DELTA.md presence, and cfg-*/bl-* paths.

Agent-facing: resolve TOPIC.perf_baseline → card summary
(sha / config / measure / delta / numbers hint).

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
    severity: str  # error | warning | info
    kind: str
    topic: str
    message: str


@dataclass
class MeasureBinding:
    measure_script: str | None = None
    measure_binary: str | None = None
    source: str = ""  # card | cfg:<id> | inherit:<id>
    inherit_cfg: str | None = None


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
    cand = topic_root / "ndf" / p
    if cand.is_file():
        return cand
    return topic_root / p


def resolve_repo_path(topic: str, rel: str) -> Path:
    """Topic-relative paths resolve under poc/<topic>/; else repo root."""
    p = rel.strip()
    if not p:
        return ROOT
    if p.startswith("poc/"):
        return ROOT / p
    if Path(p).is_absolute():
        return Path(p)
    topic_root = POC / topic
    topic_cand = topic_root / p
    root_cand = ROOT / p
    if topic_cand.is_file():
        return topic_cand
    if root_cand.is_file():
        return root_cand
    # prefer topic-relative for existence check messaging
    return topic_cand if "/" not in p or not root_cand.parent.is_dir() else root_cand


def parse_inherit_cfg(measure_body: str, card_text: str) -> str | None:
    """Detect explicit inherit cfg-* in Measure section or card."""
    for src in (measure_body, card_text):
        m = re.search(r"inherit\s+(cfg-[a-z0-9-]+)", src, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def cfg_measure(config_id: str) -> MeasureBinding | None:
    cid = config_id.strip()
    if not cid or cid.lower() == "experimental":
        return None
    cfg_path = CFG_DIR / f"{cid}.md"
    if not cfg_path.is_file():
        return None
    text = cfg_path.read_text(encoding="utf-8", errors="replace")
    ms = header_field(text, "measure_script")
    mb = header_field(text, "measure_binary")
    body = section_body(text, "Measure")
    if not ms and body:
        # allow script path in Measure body (first backtick or bare path)
        m = re.search(r"`([^`]+)`", body)
        if m:
            ms = m.group(1).strip()
        elif body and not re.search(r"inherit", body, re.IGNORECASE):
            ms = body.splitlines()[0].strip() if body.splitlines() else None
    if ms or mb or body:
        return MeasureBinding(
            measure_script=ms,
            measure_binary=mb,
            source=f"cfg:{cid}",
        )
    return None


def resolve_measure(topic: str, card_text: str) -> MeasureBinding:
    binding = MeasureBinding(source="card")
    binding.measure_script = header_field(card_text, "measure_script")
    binding.measure_binary = header_field(card_text, "measure_binary")
    measure_body = section_body(card_text, "Measure") if has_section(card_text, "Measure") else ""
    binding.inherit_cfg = parse_inherit_cfg(measure_body, card_text)

    if binding.measure_script or binding.measure_binary:
        return binding

    if measure_body and len(measure_body) >= 4 and not binding.inherit_cfg:
        # inline Measure without inherit
        m = re.search(r"`([^`]+)`", measure_body)
        if m:
            binding.measure_script = m.group(1).strip()
        return binding

    if binding.inherit_cfg:
        inherited = cfg_measure(binding.inherit_cfg)
        if inherited:
            binding.measure_script = inherited.measure_script
            binding.measure_binary = inherited.measure_binary
            binding.source = f"inherit:{binding.inherit_cfg}"
            return binding

    config_id = header_field(card_text, "config_id")
    if config_id:
        for part in re.split(r"[,;\s]+", config_id):
            if not part or part.lower() == "experimental":
                continue
            inherited = cfg_measure(part)
            if inherited and inherited.measure_script:
                binding.measure_script = inherited.measure_script
                binding.measure_binary = inherited.measure_binary
                binding.source = f"cfg:{part}"
                return binding

    if measure_body and binding.inherit_cfg:
        # inherit declared but cfg has no measure yet
        binding.source = f"inherit:{binding.inherit_cfg}"
    return binding


def validate_measure(topic: str, binding: MeasureBinding) -> list[Finding]:
    findings: list[Finding] = []
    has_script = bool(binding.measure_script and binding.measure_script.strip())
    has_section_only = binding.source == "card" and not has_script

    if not has_script:
        findings.append(
            Finding(
                "warning",
                "missing_measure",
                topic,
                "no measure_script (card header, ## Measure, or inherit cfg); "
                "performance line incomplete until backfill",
            )
        )
        return findings

    rel = binding.measure_script.strip()
    resolved = resolve_repo_path(topic, rel)
    if not resolved.is_file():
        findings.append(
            Finding(
                "error",
                "missing_measure_script",
                topic,
                f"measure_script not found: {rel} (resolved {resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved})",
            )
        )

    if binding.measure_binary:
        brel = binding.measure_binary.strip()
        bpath = resolve_repo_path(topic, brel)
        if not bpath.is_file():
            findings.append(
                Finding(
                    "warning",
                    "missing_measure_binary",
                    topic,
                    f"measure_binary not found: {brel}",
                )
            )

    if has_section_only and binding.inherit_cfg and not binding.measure_script:
        pass  # covered by missing_measure warning

    return findings


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
    topic_life: str | None = None
    perf_baseline: str | None = None
    card_path: Path | None = None
    trunk_sha: str | None = None
    config_id: str | None = None
    protocol: str | None = None
    status: str | None = None
    vs: str | None = None
    measure: MeasureBinding | None = None
    delta_path: Path | None = None
    delta_exists: bool = False
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
    view.topic_life = topic_life
    closed = topic_life in {"promoted", "rejected"}

    delta = POC / topic / "ndf" / "DELTA.md"
    view.delta_path = delta
    view.delta_exists = delta.is_file()
    if not view.delta_exists and not closed:
        view.findings.append(
            Finding(
                "warning",
                "missing_delta",
                topic,
                "missing ndf/DELTA.md (feature/hotspot logic space; required after DESIGN review)",
            )
        )

    if not view.perf_baseline:
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
                + ("(ok to skip on closed topics)" if closed else "(required after golden bind / R0)"),
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
    evidence_status = header_field(ctext, "evidence_status")
    if (
        (view.status or "").split()[0].lower() == "unverified"
        or (evidence_status or "").split()[0].lower() == "unverified"
    ):
        view.findings.append(
            Finding(
                "error",
                "unverified_measurement_claim",
                topic,
                "Numbers lack a verified Claude Code run/lease/completion "
                "and measurement evidence receipt",
            )
        )

    numbers_body = section_body(ctext, "Numbers") if has_section(ctext, "Numbers") else ""
    pending_r0 = bool(re.search(r"pending\s*r0", numbers_body, re.IGNORECASE))

    if not view.trunk_sha:
        view.findings.append(
            Finding(
                "warning" if pending_r0 else "error",
                "missing_trunk_sha",
                topic,
                "card missing `trunk_sha:`"
                + (" (ok temporarily when Numbers is pending R0)" if pending_r0 else ""),
            )
        )

    if not view.vs:
        view.findings.append(
            Finding(
                "error",
                "missing_vs",
                topic,
                "card missing `vs:` (must uniquely bind bl-trunk-golden-* )",
            )
        )
    elif not bl_exists(view.vs):
        view.findings.append(
            Finding(
                "error",
                "unknown_vs",
                topic,
                f"vs baseline not found: {view.vs}",
            )
        )

    if not view.config_id and "experimental" not in ctext.lower():
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
        view.numbers_preview = " ".join(numbers_body.split())[:240]
        if len(numbers_body) < 8:
            view.findings.append(
                Finding("error", "empty_numbers", topic, "## Numbers is empty")
            )
        elif view.vs and not pending_r0:
            if (
                "沿用" not in numbers_body
                and view.vs not in numbers_body
                and "bl-trunk" not in numbers_body.lower()
            ):
                view.findings.append(
                    Finding(
                        "info",
                        "vs_unmentioned",
                        topic,
                        f"Numbers does not mention vs `{view.vs}` (ok if own R0 table)",
                    )
                )

    if not has_section(ctext, "Measure"):
        view.findings.append(
            Finding(
                "warning",
                "missing_measure_section",
                topic,
                "card missing ## Measure (use section or header measure_script)",
            )
        )

    view.measure = resolve_measure(topic, ctext)
    view.findings.extend(validate_measure(topic, view.measure))

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
    print(f"  bind vs:        {view.vs or '(none)'}")
    print(f"  bind config_id: {view.config_id or '(none)'}")
    ms = view.measure.measure_script if view.measure else None
    print(f"  bind measure:   {ms or '(none)'}")
    print(f"  trunk_sha:  {view.trunk_sha or '(none)'}")
    print(f"  protocol:   {view.protocol or '(none)'}")
    print(f"  status:     {view.status or '(none)'}")
    if view.measure:
        m = view.measure
        print(f"  measure_binary: {m.measure_binary or '(none)'}")
        print(f"  measure_source: {m.source or '(none)'}")
    print(f"  DELTA.md:   {'yes' if view.delta_exists else 'MISSING'}")
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
