"""Installer plan/install/verify behavior (scratch repos only)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests._helpers import PKG_ROOT, read_text, run_install


class TestInstaller(unittest.TestCase):
    def test_plan_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            before = set(repo.rglob("*"))
            proc = run_install("plan", "--profile", "minimal", "--runtime", "generic", repo=repo)
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            after = set(repo.rglob("*"))
            self.assertEqual(before, after)

    def test_install_creates_core_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            proc = run_install(
                "install",
                "--profile",
                "minimal",
                "--runtime",
                "generic",
                repo=repo,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            self.assertTrue((repo / "AGENTS.md").is_file())
            self.assertTrue((repo / "ndf.workflow.yaml").is_file())
            self.assertTrue((repo / "spec/meta/tools/ndf_index.py").is_file())
            self.assertTrue((repo / "spec/meta/tools/ndf_graphcheck.py").is_file())

    def test_second_install_without_force_skips_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            first = run_install(
                "install",
                "--profile",
                "minimal",
                "--runtime",
                "generic",
                repo=repo,
            )
            self.assertEqual(first.returncode, 0, first.stderr or first.stdout)
            agents = repo / "AGENTS.md"
            agents.write_text("# custom agents marker\n", encoding="utf-8")
            mtime_before = agents.stat().st_mtime
            second = run_install(
                "install",
                "--profile",
                "minimal",
                "--runtime",
                "generic",
                repo=repo,
            )
            self.assertEqual(second.returncode, 0, second.stderr or second.stdout)
            self.assertEqual(read_text(agents), "# custom agents marker\n")
            self.assertEqual(agents.stat().st_mtime, mtime_before)

    def test_verify_exits_sensibly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            empty = run_install(
                "verify",
                "--profile",
                "minimal",
                "--runtime",
                "generic",
                "--json",
                repo=repo,
            )
            self.assertIn(empty.returncode, (0, 2))
            payload = json.loads(empty.stdout)
            self.assertIn("ok", payload)

            run_install(
                "install",
                "--profile",
                "minimal",
                "--runtime",
                "generic",
                repo=repo,
            )
            installed = run_install(
                "verify",
                "--profile",
                "minimal",
                "--runtime",
                "generic",
                "--json",
                repo=repo,
            )
            self.assertIn(installed.returncode, (0, 2))
            installed_payload = json.loads(installed.stdout)
            self.assertIn("checks", installed_payload)


if __name__ == "__main__":
    unittest.main()
