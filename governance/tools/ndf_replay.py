#!/usr/bin/env python3
"""ndf_replay — retired CLI tombstone (ADR-META-004).

Replay/Episode control-plane tooling was removed from the daily workflow.
Use ndf_workflow_status.py, ndf_dispatch_send.py, and disk
ndf-agent-completion/v1 receipts instead.
"""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "ndf_replay is retired (ADR-META-004).\n"
        "Use ndf_workflow_status.py and ndf-agent-completion/v1 disk receipts.\n"
        "See norms/meta/decisions/adr-meta-control-retirement.md.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
