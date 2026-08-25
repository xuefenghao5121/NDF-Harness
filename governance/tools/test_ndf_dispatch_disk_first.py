#!/usr/bin/env python3
"""Self-check: dispatch closeout succeeds from disk receipt without stdout notify."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ndf_dispatch_send as dispatch  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        pack = {
            "topic": "project-genesis",
            "task": "product_proposal",
            "track": "bootstrap",
            "hop": "genesis_design",
            "attempt_id": "design-g1",
            "episode_id": "project-genesis",
            "allowed_write_roots": ["spec/open/"],
            "workspace": {"repo_root": str(repo)},
        }
        rel = dispatch.completion_receipt_path_for_pack(pack)
        assert "genesis_design" in rel, rel
        assert rel != "spec/open/.ndf-completion/product_proposal-attempt.json"

        pack["completion_receipt_path"] = rel
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema": "ndf-agent-completion/v1",
            "status": "completed",
            "result": "success",
            "topic": "project-genesis",
            "task": "product_proposal",
            "hop": "genesis_design",
            "episode_id": "project-genesis",
            "attempt_id": "design-g1",
            "summary": "disk-first self-check",
        }
        path.write_text(json.dumps(receipt), encoding="utf-8")
        result, blockers, summary, completion = dispatch._task_outcome_from_transport(
            {"transport_ok": True, "ok": True, "response_text": "no notify here"},
            pack=pack,
            lease_only=False,
        )
        assert result == "succeeded", (result, blockers, summary)
        assert blockers == []
        assert "missing_dispatch_notify" not in blockers
        assert completion is not None
        assert completion["attempt_id"] == "design-g1"
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
