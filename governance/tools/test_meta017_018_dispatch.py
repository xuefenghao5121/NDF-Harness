#!/usr/bin/env python3
"""META-017 / META-018 distill contract checks (no live gateway)."""
from __future__ import annotations

import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _repo_root() -> Path:
    from ndf_paths import detect_repo_root

    return detect_repo_root(TOOLS)


ROOT = _repo_root()


def _first_existing(*cands: Path) -> Path:
    for cand in cands:
        if cand.is_file():
            return cand
    raise FileNotFoundError("none of: " + ", ".join(str(c) for c in cands))


class Meta017018Process(unittest.TestCase):
    def test_process_md_defines_clauses(self) -> None:
        text = _first_existing(
            ROOT / "norms" / "meta" / "process.md",
            ROOT / "spec" / "meta" / "process.md",
        ).read_text(encoding="utf-8")
        self.assertIn("{#META-017}", text)
        self.assertIn("{#META-018}", text)
        self.assertIn("promote_land", text)
        self.assertIn("close_finalize", text)
        self.assertIn("NDF_OPENCLAW_RESET_SESSION=0", text)
        self.assertIn("宿主网络", text)

    def test_cursor_rule_seed_exists(self) -> None:
        rule = _first_existing(
            ROOT / "adapters" / "cursor" / "rules" / "ndf-no-sandbox-dispatch.mdc",
            ROOT / ".cursor" / "rules" / "ndf-no-sandbox-dispatch.mdc",
        )
        body = rule.read_text(encoding="utf-8")
        self.assertIn("META-017", body)
        self.assertIn("ECONNREFUSED", body)

    def test_dispatch_send_refuses_impl_inhost_collapse(self) -> None:
        src = (TOOLS / "ndf_dispatch_send.py").read_text(encoding="utf-8")
        self.assertIn('mapped == "implementation"', src)
        self.assertIn('provider") or "") == "openclaw"', src)
        self.assertIn("META-017", src)

    def test_skill_mentions_meta(self) -> None:
        skill = _first_existing(
            ROOT / "skill" / "ndf-workflow" / "SKILL.md",
            ROOT / ".cursor" / "skills" / "ndf-workflow" / "SKILL.md",
        ).read_text(encoding="utf-8")
        self.assertIn("META-017", skill)
        self.assertIn("META-018", skill)
        close = _first_existing(
            ROOT / "skill" / "ndf-workflow" / "close.md",
            ROOT / ".cursor" / "skills" / "ndf-workflow" / "close.md",
        ).read_text(encoding="utf-8")
        self.assertIn("promote_land", close)
        self.assertIn("close_finalize", close)


if __name__ == "__main__":
    unittest.main()
