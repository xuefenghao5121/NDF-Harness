#!/usr/bin/env python3
"""META-021: OpenClaw dual-role task map + session model pin (no live gateway)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))

import ndf_dispatch_send as dispatch  # noqa: E402
import ndf_role_binding as role_binding  # noqa: E402


class Meta021RoleMap(unittest.TestCase):
    def test_poc_implementation_openclaw_maps_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "ndf.workflow.yaml").write_text(
                "\n".join(
                    [
                        "version: '1'",
                        "roles:",
                        "  control:",
                        "    adapter: openclaw",
                        "    fallback: in-host",
                        "    model: deepseek/deepseek-v4-pro",
                        "  implementation:",
                        "    adapter: openclaw",
                        "    fallback: in-host",
                        "    model: zai/glm-5.2",
                        "  command:",
                        "    adapter: cursor",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            resolved = role_binding.resolve_pack_provider(
                repo,
                {
                    "provider": "openclaw",
                    "task": "poc_implementation",
                    "track": "poc",
                },
            )
            self.assertEqual(resolved["mapped_role"], "implementation")
            self.assertEqual(resolved["model"], "zai/glm-5.2")

    def test_binder_amend_openclaw_maps_control(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "ndf.workflow.yaml").write_text(
                "\n".join(
                    [
                        "version: '1'",
                        "roles:",
                        "  control:",
                        "    adapter: openclaw",
                        "    model: deepseek/deepseek-v4-pro",
                        "  implementation:",
                        "    adapter: openclaw",
                        "    model: zai/glm-5.2",
                        "  command:",
                        "    adapter: cursor",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            resolved = role_binding.resolve_pack_provider(
                repo,
                {"provider": "openclaw", "task": "binder_amend", "track": "poc"},
            )
            self.assertEqual(resolved["mapped_role"], "control")
            self.assertEqual(resolved["model"], "deepseek/deepseek-v4-pro")


class Meta021DispatchGuards(unittest.TestCase):
    def test_dispatch_source_pins_model_and_blocks_impl_collapse(self) -> None:
        src = (TOOLS / "ndf_dispatch_send.py").read_text(encoding="utf-8")
        self.assertIn("def _pin_openclaw_session_model", src)
        self.assertIn("Do NOT put model in gateway params", src)
        self.assertIn('task.startswith("poc_")', src)
        self.assertIn("META-021", src)

    def test_pin_clears_model_override(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sess_dir = home / ".openclaw" / "agents" / "main" / "sessions"
            sess_dir.mkdir(parents=True)
            key = "agent:main:feishu:direct:ou_demo"
            path = sess_dir / "sessions.json"
            path.write_text(
                json.dumps(
                    {
                        key: {
                            "key": key,
                            "model": "deepseek-v4-pro",
                            "modelProvider": "deepseek",
                            "modelOverride": "deepseek-v4-pro",
                            "modelOverrideSource": "user",
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(dispatch.Path, "home", return_value=home):
                out = dispatch._pin_openclaw_session_model(
                    session_key=key,
                    model="zai/glm-5.2",
                    agent_id="main",
                )
            self.assertTrue(out.get("ok"), out)
            row = json.loads(path.read_text(encoding="utf-8"))[key]
            self.assertEqual(row["model"], "glm-5.2")
            self.assertEqual(row["modelProvider"], "zai")
            self.assertNotIn("modelOverride", row)
            self.assertNotIn("modelOverrideSource", row)

    def test_process_md_defines_meta021(self) -> None:
        text = (ROOT / "norms" / "meta" / "process.md").read_text(encoding="utf-8")
        self.assertIn("{#META-021}", text)
        self.assertIn("resolve_pack_provider", text)


if __name__ == "__main__":
    unittest.main()
