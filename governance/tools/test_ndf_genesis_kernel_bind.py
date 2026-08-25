#!/usr/bin/env python3
"""Self-check: genesis_design hop, legacy per-draft dispatch blocked."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ndf_dispatch_send as dispatch  # noqa: E402
import ndf_workflow_status as workflow  # noqa: E402

DESIGN_INTENT = """track: bootstrap
hop: genesis_design
bootstrap_mode: adopt

Write draft product NDF under spec/00-charter/ through spec/50-verification/.
Inventory include/ and src/. MUST NOT write spec/meta/ stable body.
"""


def main() -> int:
    assert workflow.infer_genesis_hop(DESIGN_INTENT) == "genesis_design"

    pack, code = workflow.control_proposal_idea_pack(intent=DESIGN_INTENT)
    assert pack.get("hop") == "genesis_design"
    assert "genesis_per_draft_dispatch" not in pack.get("blockers", [])
    roots = pack.get("allowed_write_roots") or []
    assert any(str(r).startswith("spec/00-charter") for r in roots)
    assert "genesis_hop_unlabeled" not in pack.get("blockers", [])

    normalized = workflow.normalize_human_intent(DESIGN_INTENT)
    slim = dispatch._slim_pack_for_acp_worker(pack)
    assert slim["request"]["intent"] == normalized
    assert slim["hop"] == "genesis_design"

    legacy = dict(pack)
    legacy["hop"] = "genesis_charter"
    legacy["request"] = dict(pack["request"])
    legacy["request"]["intent"] = (
        "track: bootstrap\nhop: genesis_charter\nWrite CHARTER.md\n"
    )
    msg = dispatch._build_worker_message(legacy)
    assert "genesis_per_draft_dispatch" in dispatch._pack_worker_contract_errors(
        legacy, msg
    )

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
