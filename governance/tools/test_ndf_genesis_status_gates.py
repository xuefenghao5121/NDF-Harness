#!/usr/bin/env python3
"""Self-check: genesis-status follows kernel-bind + design-dispatch shape."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ndf_workflow_status as workflow  # noqa: E402


def main() -> int:
    design_intent = """track: bootstrap
hop: genesis_design
bootstrap_mode: adopt

Inventory observed `include/` and `src/`. Write draft product NDF under:
- spec/00-charter/
- spec/10-architecture/
- spec/20-behavior/
- spec/30-interfaces/
- spec/40-constraints/
- spec/50-verification/
MUST NOT write spec/meta/ stable body. Clauses default status=draft.
"""
    assert workflow.infer_genesis_hop(design_intent) == "genesis_design"

    legacy_charter = (
        "track: bootstrap\n"
        "Write `spec/open/project-genesis/CHARTER.md`.\n"
        "MUST NOT write Architecture body until CHARTER已审核.\n"
    )
    assert workflow.infer_genesis_hop(legacy_charter) == "genesis_charter"

    pack, code = workflow.control_proposal_idea_pack(intent=legacy_charter)
    assert code != 0
    assert "genesis_per_draft_dispatch" in pack.get("blockers", [])

    rows = [
        {"gate": "roles_bound", "status": "approved"},
        {"gate": "genesis_review", "status": "pending"},
    ]
    nxt = workflow.genesis_serial_next_step(rows=rows)
    assert nxt is not None
    assert nxt["id"] in {"kernel_bind", "design_dispatch"}

    rows_foundation = [
        {"gate": "roles_bound", "status": "approved"},
    ]
    # Without GATES file path, kernel_bind when no foundation on disk — skip live path
    assert workflow.read_bootstrap_mode() in {"adopt", "greenfield"}

    status = workflow.genesis_status()
    live = workflow.genesis_serial_next_step()
    assert status.get("next_step") == live
    if live and live["id"] not in {"genesis_review", "trunk_approval"}:
        assert live["phrase"] in {"角色已配置", "绑内核", "派发", "GENESIS已审核", "可以建立初始主线"}
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
