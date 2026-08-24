"""Control-plane retirement: no live Commander/Episode/Replay requirement."""
from __future__ import annotations

import re
import unittest

from tests._helpers import PKG_ROOT, read_text, run_tool_script

ACTIVE_DOC_PATHS = (
    PKG_ROOT / "workflow" / "AGENTS.md",
    PKG_ROOT / "skill" / "ndf-workflow" / "SKILL.md",
    PKG_ROOT / "skill" / "ndf-workflow" / "OVERVIEW.md",
    PKG_ROOT / "skill" / "ndf-workflow" / "delegate.md",
)


class TestControlRetirement(unittest.TestCase):
    def test_replay_tool_exits_two(self) -> None:
        proc = run_tool_script("ndf_replay.py")
        self.assertEqual(proc.returncode, 2, proc.stdout)

    def test_agents_skill_do_not_require_live_commander(self) -> None:
        must_use = re.compile(r"must\s+use\s+commander", re.IGNORECASE)
        for path in ACTIVE_DOC_PATHS:
            text = read_text(path)
            for match in must_use.finditer(text):
                start = max(0, match.start() - 80)
                context = text[start : match.end() + 80].lower()
                self.assertTrue(
                    any(k in context for k in ("deprecated", "retired", "无", "no ")),
                    f"{path.name} has active 'must use Commander' without retirement context",
                )

    def test_agents_mentions_no_commander_episode_replay(self) -> None:
        agents = read_text(PKG_ROOT / "workflow" / "AGENTS.md")
        self.assertIn("无 Commander", agents)
        self.assertIn("无 Episode", agents)
        self.assertIn("无 Replay", agents)


if __name__ == "__main__":
    unittest.main()
