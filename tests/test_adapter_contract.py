"""Runtime adapter thin wrappers point at core skill."""
from __future__ import annotations

import unittest
from pathlib import Path

from tests._helpers import PKG_ROOT, read_text

CORE_SKILL_REF = "skill/ndf-workflow/SKILL.md"
CAPABILITY_HINTS = ("capability", "capabilities", "workflow", "skill", "入口", "modes")


class TestAdapterContract(unittest.TestCase):
    def test_each_adapter_has_skill_and_readme(self) -> None:
        adapters = PKG_ROOT / "adapters"
        for adapter_dir in sorted(adapters.iterdir()):
            if not adapter_dir.is_dir() or adapter_dir.name.startswith("."):
                continue
            skill = adapter_dir / "SKILL.md"
            readme = adapter_dir / "README.md"
            self.assertTrue(skill.is_file(), f"missing {adapter_dir.name}/SKILL.md")
            self.assertTrue(readme.is_file(), f"missing {adapter_dir.name}/README.md")

            skill_text = read_text(skill)
            self.assertIn(
                CORE_SKILL_REF,
                skill_text.replace("../../", ""),
                f"{adapter_dir.name}/SKILL.md must point to core skill",
            )

            readme_text = read_text(readme).lower()
            self.assertTrue(
                any(h in readme_text for h in CAPABILITY_HINTS),
                f"{adapter_dir.name}/README.md should mention capability/workflow",
            )


if __name__ == "__main__":
    unittest.main()
