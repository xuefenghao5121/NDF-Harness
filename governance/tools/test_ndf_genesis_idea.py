#!/usr/bin/env python3
"""Self-check: ndf-genesis-idea/v1 checker (legal fill vs illegal multi-cycle)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ndf_genesis_idea as idea  # noqa: E402

LEGAL = """# Sample cycle

> schema: ndf-genesis-idea/v1
> track: bootstrap
> bootstrap_mode: greenfield
> cycle_id: sample-kernel
> maps_to: skeleton
> status: draft

## Verbatim intent

> One-cycle skeleton only.

## Problem and user

- Problem: need a skeleton
- Target user: maintainers
- Existing alternative: none

## In-scope (this cycle)

1. Define project skeleton for this cycle only.

## Out-of-scope (this cycle)

1. sibling cycle_id: `later-integrate` — deferred.

## Success (not SLA)

| Condition | Measure | Status |
|-----------|---------|--------|
| Skeleton exists | draft files | draft |

## Hard constraints

- Platform: generic
- Language/runtime: C
- Performance comparison target (name only, no numeric SLA): baseline library
- Other: one cycle

## Guidance (non-normative)

本栏不是契约。Control MUST NOT 将本栏写入 BEH/API/CON-SLA must。

- hints stay here

## Mapping

| 输入栏目 | 允许写入 | 禁止 |
|----------|----------|------|
| Verbatim + In-scope | `00-charter` 目标 | 拆成任务清单 BEH |
"""

ILLEGAL = LEGAL.replace(
    "1. Define project skeleton for this cycle only.\n",
    "1. Define skeleton then do phase 2 integration.\n",
)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.md"
        bad = Path(tmp) / "bad.md"
        good.write_text(LEGAL, encoding="utf-8")
        bad.write_text(ILLEGAL, encoding="utf-8")
        assert idea.check(good) == [], idea.check(good)
        assert idea.main(["check", str(good)]) == 0
        bad_errs = idea.check(bad)
        assert "in_scope_multi_cycle" in bad_errs, bad_errs
        assert idea.main(["check", str(bad)]) == 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
