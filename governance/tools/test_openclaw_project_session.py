#!/usr/bin/env python3
"""Per-project OpenClaw agent/session isolation (multi-project parallel)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
import importlib.util


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


role_binding = _load("ndf_role_binding")
dispatch = _load("ndf_dispatch_send")


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


def _write_workflow(repo: Path, *, control_extra: str = "") -> None:
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
            "    adapter: in-host",
            "",
        ]
    )
    (repo / "ndf.workflow.yaml").write_text(text, encoding="utf-8")


class OpenClawProjectSession(unittest.TestCase):
    def test_identity_differs_across_repos(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "proj-a"
            b = Path(td) / "proj-b"
            a.mkdir()
            b.mkdir()
            _git_init(a)
            _git_init(b)
            ia = role_binding.openclaw_repo_identity(a)
            ib = role_binding.openclaw_repo_identity(b)
            self.assertNotEqual(ia["agent_id"], ib["agent_id"])
            self.assertNotEqual(ia["session_key"], ib["session_key"])
            self.assertTrue(ia["session_key"].startswith(f"agent:{ia['agent_id']}:"))

    def test_worktree_shares_identity(self) -> None:
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
            ia = role_binding.openclaw_repo_identity(main)
            ib = role_binding.openclaw_repo_identity(wt)
            self.assertEqual(ia["agent_id"], ib["agent_id"])
            self.assertEqual(ia["session_key"], ib["session_key"])

    def test_legacy_shared_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "legacy"
            repo.mkdir()
            _git_init(repo)
            _write_workflow(repo)
            (repo / "AGENTS.md").write_text(
                "OpenClaw 指挥会话 session_key：`agent:main:main`\n",
                encoding="utf-8",
            )
            cfg = role_binding.configured_openclaw_session(repo)
            self.assertEqual(cfg["ownership"], "legacy_shared")
            self.assertFalse(cfg["multi_project_safe"])
            self.assertIn("openclaw_session_legacy_shared", cfg["blockers"])

    def test_stale_copied_binding_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "copied"
            repo.mkdir()
            _git_init(repo)
            _write_workflow(
                repo,
                control_extra="\n".join(
                    [
                        "agent_id: ndf-other-deadbeef1234",
                        "session_key: agent:ndf-other-deadbeef1234:main",
                        "session_transport: session_key",
                        "session_binding_version: ndf-v1",
                    ]
                ),
            )
            cfg = role_binding.configured_openclaw_session(repo)
            self.assertEqual(cfg["ownership"], "stale")
            self.assertIn(
                "openclaw_session_collision_or_stale_binding", cfg["blockers"]
            )

    def test_provision_writes_managed_binding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "fresh"
            repo.mkdir()
            _git_init(repo)
            _write_workflow(repo)
            expected = role_binding.managed_openclaw_binding(repo)

            def fake_list(*_a, **_k):
                return [], None

            real_run = role_binding.subprocess.run

            def fake_run(cmd, **kwargs):
                cmd_list = list(cmd)
                if len(cmd_list) >= 3 and cmd_list[1] == "agents" and cmd_list[2] == "add":
                    class R:
                        returncode = 0
                        stdout = json.dumps(
                            {
                                "id": expected["agent_id"],
                                "workspace": expected["workspace"],
                            }
                        )
                    return R()
                return real_run(cmd, **kwargs)

            with mock.patch.object(
                role_binding.shutil, "which", lambda n: "/usr/bin/openclaw" if n == "openclaw" else None
            ), mock.patch.object(
                role_binding, "list_openclaw_agents", fake_list
            ), mock.patch.object(role_binding.subprocess, "run", fake_run):
                result = role_binding.provision_openclaw_project_agent(repo)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["provisioned"])
            after = role_binding.configured_openclaw_session(repo)
            self.assertEqual(after["ownership"], "managed")
            self.assertTrue(after["multi_project_safe"])
            self.assertEqual(after["agent_id"], expected["agent_id"])
            self.assertEqual(after["session_key"], expected["session_key"])
            yaml_text = (repo / "ndf.workflow.yaml").read_text(encoding="utf-8")
            self.assertIn(f"agent_id: {expected['agent_id']}", yaml_text)
            self.assertIn("session_binding_version: ndf-v1", yaml_text)

    def test_workspace_collision_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "collide"
            repo.mkdir()
            _git_init(repo)
            _write_workflow(repo)
            expected = role_binding.managed_openclaw_binding(repo)

            def fake_list(*_a, **_k):
                return [
                    {
                        "id": expected["agent_id"],
                        "workspace": "/tmp/other-project",
                    }
                ], None

            with mock.patch.object(
                role_binding.shutil, "which", lambda n: "/usr/bin/openclaw"
            ), mock.patch.object(role_binding, "list_openclaw_agents", fake_list):
                result = role_binding.provision_openclaw_project_agent(repo)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "openclaw_agent_workspace_collision")

    def test_dispatch_uses_pack_agent_id(self) -> None:
        pack = {
            "agent_id": "ndf-demo-abc123",
            "session_key": "agent:ndf-demo-abc123:main",
            "session_transport": "session_key",
            "multi_project_safe": True,
            "openclaw_ownership": "managed",
            "topic": "t",
            "task": "control_proposal",
        }
        self.assertEqual(dispatch._openclaw_agent_id(pack), "ndf-demo-abc123")

    def test_dispatch_blocks_legacy_shared(self) -> None:
        result = dispatch._send_openclaw(
            {
                "session_key": "agent:main:main",
                "openclaw_ownership": "legacy_shared",
                "multi_project_safe": False,
            },
            message="hi",
            timeout_sec=5,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "openclaw_session_not_multi_project_safe")

    def test_reset_skipped_when_session_missing(self) -> None:
        with mock.patch.object(dispatch, "_openclaw_session_exists", return_value=False):
            out = dispatch._reset_openclaw_session(
                executable="/usr/bin/openclaw",
                session_key="agent:ndf-demo-abc123:main",
            )
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
