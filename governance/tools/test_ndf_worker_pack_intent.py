#!/usr/bin/env python3
"""Self-check: worker pack keeps Genesis intent; bootstrap is not labeled poc."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ndf_dispatch_send as dispatch  # noqa: E402
import ndf_workflow_status as workflow  # noqa: E402

DESIGN_INTENT = """track: bootstrap
hop: genesis_design
Write draft NDF under spec/00-charter/ and spec/10-architecture/.
"""


def main() -> int:
    assert workflow.intent_header_track(DESIGN_INTENT) == "bootstrap"
    assert workflow.infer_genesis_hop(DESIGN_INTENT) == "genesis_design"

    pack, _ = workflow.control_proposal_idea_pack(intent=DESIGN_INTENT)
    normalized = workflow.normalize_human_intent(DESIGN_INTENT)
    pack["request"] = {"origin": "human_intent", "intent": normalized}

    slim = dispatch._slim_pack_for_acp_worker(pack)
    assert slim["request"]["intent"] == normalized
    assert slim["track"] == "bootstrap"
    assert slim["hop"] == "genesis_design"

    message = dispatch._build_worker_message(pack)
    assert "BEGIN HUMAN_INTENT" in message
    assert "spec/00-charter/" in message
    assert dispatch._pack_worker_contract_errors(pack, message) == []

    mislabeled = dict(pack)
    mislabeled["track"] = "poc"
    mislabeled["hop"] = "draft"
    bad = dispatch._pack_worker_contract_errors(
        mislabeled, dispatch._build_worker_message(mislabeled)
    )
    assert "genesis_pack_labeled_poc" in bad
    assert "genesis_hop_unlabeled" in bad
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
