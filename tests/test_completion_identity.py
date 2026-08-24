"""Disk completion identity contract in docs."""
from __future__ import annotations

import unittest

from tests._helpers import PKG_ROOT, read_text

COMPLETION = "ndf-agent-completion/v1"


class TestCompletionIdentity(unittest.TestCase):
    def test_agents_mentions_completion_schema(self) -> None:
        text = read_text(PKG_ROOT / "workflow" / "AGENTS.md")
        self.assertIn(COMPLETION, text)

    def test_skill_mentions_completion_schema(self) -> None:
        text = read_text(PKG_ROOT / "skill" / "ndf-workflow" / "SKILL.md")
        self.assertIn(COMPLETION, text)

    def test_docs_mention_completion_schema(self) -> None:
        docs = PKG_ROOT / "docs"
        hits = []
        for path in sorted(docs.glob("*.md")):
            if COMPLETION in read_text(path):
                hits.append(path.name)
        self.assertTrue(hits, "expected at least one docs/*.md to mention completion schema")


if __name__ == "__main__":
    unittest.main()
