#!/usr/bin/env python3
"""Self-check for ndf_genesis_design_map.py."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
import importlib.util

spec = importlib.util.spec_from_file_location(
    "ndf_genesis_design_map", TOOLS / "ndf_genesis_design_map.py"
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

LEGAL = """\
# Design Map

> schema: ndf-genesis-design-map/v1
> track: bootstrap
> bootstrap_mode: greenfield
> cycle_id: sample-kernel
> source_ref: docs/cycles/cycle-sample.md
> source_content_sha: abc
> hop: genesis_synthesis
> status: draft

## Product scope (from Idea)

### In scope

- fixed-size kernel

### Out of scope

- sibling cycle

## Module decomposition

| Module / path | Responsibility | Depends on |
|---------------|----------------|------------|
| `include/` | ABI | |
| `src/host/` | plan | include |

## Runtime data flow

plan once execute many

## Algorithm and invariants

- fixed N

## Interfaces and ownership

- caller owns buffer

## Verification properties

| Property | Mathematical meaning | Maps to (hint) |
|----------|---------------------|----------------|
| linearity | alpha beta | VER-1 |

## Assumptions and open questions

| Item | Assumption / question | Blocks spec? |
|------|----------------------|--------------|
| N | power of two | no |

## Trace rows

| source_section | source_excerpt | target_layer | target_path | clause_id_hint | source_tag |
|----------------|----------------|--------------|-------------|----------------|------------|
| In-scope #1 | kernel | ARCH | spec/10-architecture/ | ARCH-1 | deduced |
| In-scope #1 | kernel | BEH | spec/20-behavior/ | BEH-1 | deduced |
| Hard constraints | platform | CON | spec/40-constraints/ | CON-1 | deduced |

## Exclusions (Guidance MUST NOT become must)

- roadmap prose

## Budget

- clause_budget: ≤20
- guidance_landed_in_must: false
"""


class DesignMapCheckTests(unittest.TestCase):
    def test_legal_passes_structure(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(LEGAL)
            path = Path(f.name)
        try:
            errs = mod.check(path)
            self.assertEqual(errs, [])
        finally:
            path.unlink(missing_ok=True)

    def test_sparse_trace_fails(self) -> None:
        bad = LEGAL.replace(
            "| Hard constraints | platform | CON | spec/40-constraints/ | CON-1 | deduced |\n",
            "",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(bad)
            path = Path(f.name)
        try:
            errs = mod.check(path)
            self.assertIn("trace_rows_sparse", errs)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
