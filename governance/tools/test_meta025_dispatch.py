#!/usr/bin/env python3
"""META-025: one proposal confirm; pack-view before POC send; no lease until --send."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _repo_root() -> Path:
    from ndf_paths import detect_repo_root

    return detect_repo_root(TOOLS)


ROOT = _repo_root()


def _process_md() -> Path:
    for cand in (ROOT / "norms" / "meta" / "process.md", ROOT / "spec" / "meta" / "process.md"):
        if cand.is_file():
            return cand
    raise FileNotFoundError("process.md not found under norms/meta or spec/meta")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


dispatch = _load("ndf_dispatch_send")
workflow = _load("ndf_workflow_status")


class Meta025Dispatch(unittest.TestCase):
    def test_process_md_defines_clause(self) -> None:
        text = _process_md().read_text(encoding="utf-8")
        self.assertIn("{#META-025}", text)
        self.assertIn("human_pack_view_missing", text)
        self.assertIn("提案只确认一次", text)
        self.assertNotIn(
            "implemented_pending_review",
            text.split("{#META-014}")[1].split("{#BEH-020}")[0]
            if "{#META-014}" in text
            else text,
        )

    def test_confirmed_implemented_process_proposal_is_done(self) -> None:
        path = ROOT / "spec/meta/open/proposal-meta-pack-human-send-gate.md"
        if not path.is_file():
            self.skipTest("META-025 proposal not in this tree")
        record = workflow.proposal_record(path)
        self.assertEqual(record.get("lifecycle"), "reviewed")
        self.assertIsNone(record.get("hop"))
        self.assertIsNone(record.get("next_human_phrase"))

    def test_poc_send_without_pack_view_blocked(self) -> None:
        self.assertEqual(
            dispatch.pack_view_send_blocker(
                {
                    "track": "poc",
                    "task": "poc_implementation",
                    "topic": "meta025-missing-view",
                    "plan_sha": "a" * 64,
                }
            ),
            "human_pack_view_missing",
        )

    def test_process_land_does_not_require_pack_view(self) -> None:
        self.assertIsNone(
            dispatch.pack_view_send_blocker(
                {"track": "process", "task": "ndf_improvement_land"}
            )
        )

    def test_matching_v2_pack_view_allows_send_gate(self) -> None:
        plan_sha = "b" * 64
        rel = "tmp/ndf-pack-view-meta025-unit.md"
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# NDF pack view\n> schema: ndf-pack-view/v2\n\n" + plan_sha + "\n",
            encoding="utf-8",
        )
        self.assertIsNone(
            dispatch.pack_view_send_blocker(
                {
                    "track": "poc",
                    "task": "poc_implementation",
                    "topic": "meta025-unit",
                    "plan_sha": plan_sha,
                    "pack_view_path": rel,
                }
            )
        )

    def test_poc_dispatch_leases_only_on_send(self) -> None:
        src = (TOOLS / "ndf_poc_dispatch.py").read_text(encoding="utf-8")
        self.assertIn("if hard_ok and send:", src)
        self.assertIn("pack_view_send_blocker", src)


if __name__ == "__main__":
    unittest.main()
