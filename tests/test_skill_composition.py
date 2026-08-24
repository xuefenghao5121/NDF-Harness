"""Skill tree composition and pointer layout."""
from __future__ import annotations

import unittest
from pathlib import Path

from tests._helpers import PKG_ROOT, read_text

REQUIRED_MODULES = (
    "intake.md",
    "proposal.md",
    "genesis.md",
    "poc.md",
    "close.md",
    "delegate.md",
    "health.md",
    "install.md",
    "adopt.md",
    "govern.md",
    "sync.md",
    "OVERVIEW.md",
    "roles/control.md",
    "roles/implementation.md",
)


class TestSkillComposition(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = PKG_ROOT / "skill"
        self.workflow = self.skill_root / "ndf-workflow"

    def test_ndf_workflow_has_skill_and_modules(self) -> None:
        skill_md = self.workflow / "SKILL.md"
        self.assertTrue(skill_md.is_file(), "skill/ndf-workflow/SKILL.md missing")
        for name in REQUIRED_MODULES:
            path = self.workflow / name
            self.assertTrue(path.is_file(), f"missing module: {name}")

    def test_root_skill_is_pointer(self) -> None:
        root_skill = self.skill_root / "SKILL.md"
        self.assertTrue(root_skill.is_file())
        text = read_text(root_skill)
        self.assertIn("ndf-workflow/SKILL.md", text)
        self.assertIn("Canonical human entry", text)


if __name__ == "__main__":
    unittest.main()
