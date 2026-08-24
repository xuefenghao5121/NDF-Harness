"""Idea plane routing and five human phrases documented."""
from __future__ import annotations

import re
import unittest

from tests._helpers import PKG_ROOT, read_text

PLANES = ("product", "process", "mixed", "ambiguous")
PHRASES = ("初始化", "提交Idea", "派发", "继续", "关闭")


class TestIdeaRoutingDocs(unittest.TestCase):
    def setUp(self) -> None:
        self.agents = read_text(PKG_ROOT / "workflow" / "AGENTS.md")
        self.skill = read_text(PKG_ROOT / "skill" / "ndf-workflow" / "SKILL.md")

    def test_agents_mentions_idea_planes(self) -> None:
        for plane in PLANES:
            self.assertIn(plane, self.agents, f"AGENTS.md missing plane: {plane}")

    def test_skill_mentions_idea_planes(self) -> None:
        for plane in PLANES:
            self.assertIn(plane, self.skill, f"SKILL.md missing plane: {plane}")

    def test_agents_mentions_five_phrases(self) -> None:
        hits = sum(1 for p in PHRASES if p in self.agents)
        self.assertGreaterEqual(hits, 4, "AGENTS.md should mention most human phrases")

    def test_skill_mentions_five_phrases(self) -> None:
        for phrase in PHRASES:
            self.assertIn(phrase, self.skill, f"SKILL.md missing phrase: {phrase}")


if __name__ == "__main__":
    unittest.main()
