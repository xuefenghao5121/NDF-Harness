#!/usr/bin/env python3
"""META-019: bundle_dispatch licenses implement; lease does not require episode_id."""
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
context = _load("ndf_context")


def _bundle_receipt(**extra) -> dict:
    row = {
        "gate": "bundle_dispatch",
        "phrase": "派发",
        "status": "approved",
        "approved_content_sha": "a" * 64,
        "expected_content_sha": "a" * 64,
        "bundle_mode": "review_slice",
        "receipt_bundle_mode": "review_slice",
        "expected_bundle_mode": "review_slice",
    }
    row.update(extra)
    return row


class Meta019Dispatch(unittest.TestCase):
    def test_process_md_defines_clause(self) -> None:
        text = _process_md().read_text(encoding="utf-8")
        self.assertIn("{#META-019}", text)
        self.assertIn("lease_pack_incomplete", text)
        self.assertIn("{#META-017}", text)
        self.assertIn("宿主网络", text)

    def test_lease_missing_fields_ignore_episode_id(self) -> None:
        missing = dispatch.isolated_lease_missing_fields(
            {
                "topic": "sample-topic",
                "base_sha": "c" * 40,
                "allowed_write_root": "poc/sample-topic/",
            }
        )
        self.assertEqual(missing, [])

    def test_lease_missing_fields_still_require_handshake(self) -> None:
        missing = dispatch.isolated_lease_missing_fields({"episode_id": "ep-1"})
        self.assertEqual(missing, ["topic", "base_sha", "allowed_write_root"])

    def test_bundle_dispatch_is_implement_license(self) -> None:
        self.assertTrue(context.valid_implement_license_receipt(_bundle_receipt()))
        self.assertFalse(
            context.valid_implement_license_receipt(
                _bundle_receipt(approved_content_sha="b" * 64)
            )
        )
        self.assertFalse(
            context.valid_implement_license_receipt(_bundle_receipt(gate="topic_review"))
        )


if __name__ == "__main__":
    unittest.main()
