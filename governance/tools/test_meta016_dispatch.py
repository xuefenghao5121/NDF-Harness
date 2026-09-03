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
            (root / "src" / "fft.c").write_text("int n;\n", encoding="utf-8")
            self.assertTrue(workflow.trunk_src_present(root))

    def test_stale_worktree_receipt_does_not_impersonate_hop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "poc/jit-twiddle-imm-lut/ndf/evidence/poc_implementation-completion.json"
            pack = _pack(
                root,
                topic="jit-twiddle-imm-lut",
                task="poc_implementation",
                hop="implement",
                track="poc",
                base_sha="b" * 40,
                allowed_write_root="poc/jit-twiddle-imm-lut/",
                completion_receipt_path=rel,
            )
            stale_body = {
                "schema": "ndf-agent-completion/v1",
                "result": "success",
                "topic": pack["topic"],
                "task": pack["task"],
                "hop": pack["hop"],
                "attempt_id": pack["attempt_id"],
                "base_sha": "a" * 40,
                "summary": "R1 winner",
            }
            wt_path = root / ".worktrees" / "lease-old" / rel
            wt_path.parent.mkdir(parents=True)
            wt_path.write_text(json.dumps(stale_body), encoding="utf-8")
            completion, errors = dispatch.load_disk_agent_completion(
                pack, {"receipt_path": rel}
            )
            self.assertIsNone(completion)
            self.assertIn("stale_disk_receipt", errors)
            self.assertIn("completion_base_sha_mismatch", errors)

            match_body = {**stale_body, "base_sha": pack["base_sha"], "summary": "this hop"}
            main_path = root / rel
            main_path.parent.mkdir(parents=True, exist_ok=True)
            main_path.write_text(json.dumps(match_body), encoding="utf-8")
            completion, errors = dispatch.load_disk_agent_completion(
                pack, {"receipt_path": rel}
            )
            self.assertIsNotNone(completion)
            self.assertEqual(errors, [])
            self.assertEqual(completion["summary"], "this hop")

    def test_stale_receipt_transport_ok_does_not_attach_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "poc/t/ndf/evidence/poc_implementation-completion.json"
            pack = _pack(
                root,
                topic="t",
                task="poc_implementation",
                hop="implement",
                track="poc",
                base_sha="b" * 40,
                allowed_write_root="poc/t/",
                completion_receipt_path=rel,
            )
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema": "ndf-agent-completion/v1",
                        "result": "success",
                        "topic": "t",
                        "task": "poc_implementation",
                        "hop": "implement",
                        "attempt_id": pack["attempt_id"],
                        "base_sha": "a" * 40,
                        "summary": "prior hop",
                    }
                ),
                encoding="utf-8",
            )
            state, blockers, _, completion = dispatch._task_outcome_from_transport(
                {
                    "ok": True,
                    "transport_ok": True,
                    "response_text": None,
                    "state": "succeeded",
                },
                pack=pack,
                lease_only=False,
            )
            self.assertEqual(state, "failed")
            self.assertIsNone(completion)
            self.assertIn("stale_disk_receipt", blockers)
            self.assertIn("completion_base_sha_mismatch", blockers)

    def test_slim_pack_keeps_lease_identity(self) -> None:
        slim = dispatch._slim_pack_for_acp_worker(
            {
                "topic": "t",
                "worktree": "/wt",
                "branch": "poc/t-lease",
                "run_id": "run-1",
                "session_id": "sess",
                "inline_lease": {"worktree": "/wt"},
                "agent_id": "impl",
                "session_key": "agent:impl:main",
            }
        )
        for key in (
            "worktree",
            "branch",
            "run_id",
            "session_id",
            "inline_lease",
            "agent_id",
            "session_key",
        ):
            self.assertIn(key, slim)

    def test_openclaw_worker_message_names_worktree(self) -> None:
        msg = dispatch._build_worker_message(
            {
                "provider": "openclaw",
                "worktree": "/tmp/lease-wt",
                "completion_receipt_path": (
                    "poc/t/ndf/evidence/poc_implementation-completion.json"
                ),
                "topic": "t",
                "task": "poc_implementation",
            }
        )
        self.assertIn("/tmp/lease-wt", msg)
        self.assertIn("MUST NOT use the main checkout", msg)
        self.assertIn("MUST NOT reuse an existing receipt", msg)

    def test_quarantine_checkout_completion_moves_canonical_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp)
            rel = "poc/t/ndf/evidence/poc_implementation-completion.json"
            path = wt / rel
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            dest = dispatch._quarantine_checkout_completion(
                wt, {"completion_receipt_path": rel}
            )
            self.assertIsNotNone(dest)
            self.assertFalse(path.is_file())
            moved = wt / dest
            self.assertTrue(moved.is_file())
            self.assertIn("checkout-moved-", moved.name)


if __name__ == "__main__":
    unittest.main()
