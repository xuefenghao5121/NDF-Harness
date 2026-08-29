#!/usr/bin/env python3
"""META-017 / META-018 distill contract checks (no live gateway)."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = Path(__file__).resolve().parent


class Meta017018Process(unittest.TestCase):
    def test_process_md_defines_clauses(self) -> None:
        text = (ROOT / "norms" / "meta" / "process.md").read_text(encoding="utf-8")
        self.assertIn("{#META-017}", text)
        self.assertIn("{#META-018}", text)
        self.assertIn("promote_land", text)
        self.assertIn("close_finalize", text)
        self.assertIn("NDF_OPENCLAW_RESET_SESSION=0", text)
        self.assertIn("宿主网络", text)

    def test_cursor_rule_seed_exists(self) -> None:
        rule = ROOT / "adapters" / "cursor" / "rules" / "ndf-no-sandbox-dispatch.mdc"
        self.assertTrue(rule.is_file())
        body = rule.read_text(encoding="utf-8")
        self.assertIn("META-017", body)
        self.assertIn("ECONNREFUSED", body)

    def test_dispatch_send_refuses_impl_inhost_collapse(self) -> None:
        src = (TOOLS / "ndf_dispatch_send.py").read_text(encoding="utf-8")
        self.assertIn('mapped == "implementation"', src)
        self.assertIn('provider") or "") == "openclaw"', src)
        self.assertIn("META-017", src)

    def test_skill_mentions_meta(self) -> None:
        skill = (ROOT / "skill" / "ndf-workflow" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("META-017", skill)
        self.assertIn("META-018", skill)
        close = (ROOT / "skill" / "ndf-workflow" / "close.md").read_text(encoding="utf-8")
        self.assertIn("promote_land", close)
        self.assertIn("close_finalize", close)


if __name__ == "__main__":
    unittest.main()
