#!/usr/bin/env python3
"""META-022: Control vs Implementation OpenClaw role sessions."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


role_binding = _load("ndf_role_binding")


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _write_workflow(
    repo: Path,
    *,
    control_extra: str = "",
    impl_adapter: str = "openclaw",
    impl_extra: str = "",
) -> None:
    text = "\n".join(
        [
            'version: "1"',
            "project: demo",
            "roles:",
            "  command:",
            "    label: Command surface",
            "    adapter: cursor",
            "  control:",
            "    label: Control agent",
            "    adapter: openclaw",
            "    fallback: in-host",
            *([f"    {line}" for line in control_extra.splitlines() if line.strip()]),
            "  implementation:",
            "    label: Implementation agent",
            f"    adapter: {impl_adapter}",
            *([f"    {line}" for line in impl_extra.splitlines() if line.strip()]),
            "",
        ]
    )
    (repo / "ndf.workflow.yaml").write_text(text, encoding="utf-8")


class OpenClawRoleSessions(unittest.TestCase):
    def test_impl_identity_differs_from_control(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "proj"
            repo.mkdir()
            _git_init(repo)
            ctrl = role_binding.openclaw_repo_identity(repo, role="control")
            impl = role_binding.openclaw_repo_identity(repo, role="implementation")
            self.assertNotEqual(ctrl["agent_id"], impl["agent_id"])
            self.assertNotEqual(ctrl["session_key"], impl["session_key"])
            self.assertTrue(impl["agent_id"].endswith("-impl"))
            self.assertEqual(ctrl["identity_hash"], impl["identity_hash"])
            self.assertEqual(ctrl["base_agent_id"], impl["base_agent_id"])

    def test_worktree_shares_dual_identity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            main = Path(td) / "main"
            main.mkdir()
            _git_init(main)
            wt = Path(td) / "wt"
            subprocess.run(
                ["git", "-C", str(main), "worktree", "add", str(wt), "HEAD"],
                check=True,
                capture_output=True,
            )
            for role in ("control", "implementation"):
                self.assertEqual(
                    role_binding.openclaw_repo_identity(main, role=role)["session_key"],
                    role_binding.openclaw_repo_identity(wt, role=role)["session_key"],
                )

    def test_collapse_when_impl_reuses_control_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "same"
            repo.mkdir()
            _git_init(repo)
            expected = role_binding.managed_openclaw_binding(repo, role="control")
            _write_workflow(
                repo,
                control_extra="\n".join(
                    [
                        f"agent_id: {expected['agent_id']}",
                        f"session_key: {expected['session_key']}",
                        "session_transport: session_key",
                        "session_binding_version: ndf-v1",
                    ]
                ),
                impl_adapter="openclaw",
                impl_extra="\n".join(
                    [
                        f"agent_id: {expected['agent_id']}",
                        f"session_key: {expected['session_key']}",
                        "session_transport: session_key",
                        "session_binding_version: ndf-v1",
                    ]
                ),
            )
            collapse = role_binding.openclaw_role_session_collapse(repo)
            self.assertTrue(collapse["collapsed"])
            self.assertEqual(collapse["error"], "openclaw_role_session_collapsed")
            ok, blockers = role_binding.check_roles_for_dispatch(repo)
            self.assertFalse(ok)
            self.assertIn("openclaw_role_session_collapsed", blockers)

    def test_no_collapse_when_keys_differ(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "split"
            repo.mkdir()
            _git_init(repo)
            c = role_binding.managed_openclaw_binding(repo, role="control")
            i = role_binding.managed_openclaw_binding(repo, role="implementation")
            _write_workflow(
                repo,
                control_extra="\n".join(
                    [
                        f"agent_id: {c['agent_id']}",
                        f"session_key: {c['session_key']}",
                        "session_transport: session_key",
                        "session_binding_version: ndf-v1",
                    ]
                ),
                impl_adapter="openclaw",
                impl_extra="\n".join(
                    [
                        f"agent_id: {i['agent_id']}",
                        f"session_key: {i['session_key']}",
                        "session_transport: session_key",
                        "session_binding_version: ndf-v1",
                    ]
                ),
            )
            collapse = role_binding.openclaw_role_session_collapse(repo)
            self.assertFalse(collapse["collapsed"])
            ctrl = role_binding.configured_openclaw_session(repo, role="control")
            impl = role_binding.configured_openclaw_session(repo, role="implementation")
            self.assertEqual(ctrl["ownership"], "managed")
            self.assertEqual(impl["ownership"], "managed")
            self.assertNotEqual(ctrl["session_key"], impl["session_key"])

    def test_poc_task_maps_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "map"
            repo.mkdir()
            _git_init(repo)
            _write_workflow(repo, impl_adapter="openclaw")
            resolved = role_binding.resolve_pack_provider(
                repo,
                {"provider": "openclaw", "task": "poc_implementation"},
            )
            self.assertEqual(resolved["mapped_role"], "implementation")


if __name__ == "__main__":
    unittest.main()
