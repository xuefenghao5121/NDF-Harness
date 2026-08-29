#!/usr/bin/env python3
"""META-016: disk receipt beats stall; has_src ignores .ndf-completion."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
import importlib.util


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


dispatch = _load("ndf_dispatch_send")
workflow = _load("ndf_workflow_status")


def _pack(root: Path, **extra) -> dict:
    payload = {
        "topic": "project-genesis",
        "task": "project_genesis",
        "hop": "genesis_trunk",
        "track": "bootstrap",
        "attempt_id": "attempt",
        "workspace": {"repo_root": str(root)},
        "allowed_write_roots": ["src/"],
    }
    payload.update(extra)
    return payload


def _receipt(pack: dict, root: Path, *, result: str = "success") -> Path:
    rel = dispatch.completion_receipt_path_for_pack(pack)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "ndf-agent-completion/v1",
                "result": result,
                "topic": pack["topic"],
                "task": pack["task"],
                "hop": pack["hop"],
                "attempt_id": pack["attempt_id"],
                "summary": "vendor hop done",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


class Meta016Dispatch(unittest.TestCase):
    def test_stalled_transport_then_success_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = _pack(root)
            _receipt(pack, root)
            state, blockers, summary, completion = dispatch._task_outcome_from_transport(
                {
                    "ok": False,
                    "transport_ok": False,
                    "error": "openclaw_stalled",
                    "state": "failed",
                },
                pack=pack,
                lease_only=False,
            )
            self.assertEqual(state, "succeeded")
            self.assertEqual(blockers, [])
            self.assertIsNotNone(completion)
            self.assertIn("vendor hop", summary)

    def test_stalled_without_receipt_stays_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = _pack(Path(tmp))
            state, blockers, _, completion = dispatch._task_outcome_from_transport(
                {
                    "ok": False,
                    "transport_ok": False,
                    "error": "openclaw_stalled",
                },
                pack=pack,
                lease_only=False,
            )
            self.assertEqual(state, "failed")
            self.assertIn("openclaw_stalled", blockers)
            self.assertIsNone(completion)

    def test_genesis_trunk_stall_default_is_hour(self) -> None:
        saved = {
            key: os.environ.pop(key, None)
            for key in (
                "NDF_OPENCLAW_STALL_SEC",
                "NDF_OPENCLAW_PING_SEC",
                "NDF_OPENCLAW_MAX_SEC",
            )
        }
        try:
            _, stall, _ = dispatch._openclaw_wait_budgets(
                None, {"hop": "genesis_trunk", "task": "project_genesis"}
            )
            self.assertGreaterEqual(stall, 3600)
            _, poc_stall, _ = dispatch._openclaw_wait_budgets(
                None, {"hop": "implement", "task": "poc_implementation"}
            )
            self.assertEqual(poc_stall, 900)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_trunk_src_ignores_completion_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidden = root / "src" / ".ndf-completion"
            hidden.mkdir(parents=True)
            (hidden / "attempt.json").write_text("{}", encoding="utf-8")
            self.assertFalse(workflow.trunk_src_present(root))
            (root / "src" / "kernel.c").write_text("int n;\n", encoding="utf-8")
            self.assertTrue(workflow.trunk_src_present(root))


if __name__ == "__main__":
    unittest.main()
