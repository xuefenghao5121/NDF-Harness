# Genesis Task Order — fill rules

> role: info (not a product or process clause)  
> schema: ndf-genesis-idea/v1  
> template: `TASK_ORDER.md.stub`

## Authority

Greenfield Genesis human input MUST use a filled copy of `TASK_ORDER.md.stub`.
Legacy prose roadmaps MUST NOT be `source_ref` for any Genesis hop.

Idea files feed **synthesis** (`hop=genesis_synthesis` → DESIGN_MAP), not spec directly.
See `DESIGN_MAP.md.stub` and `ndf_genesis_design_map.py`.

## Required sections (fixed names, fixed order)

1. `## Verbatim intent`
2. `## Problem and user`
3. `## In-scope (this cycle)`
4. `## Out-of-scope (this cycle)`
5. `## Success (not SLA)`
6. `## Hard constraints`
7. `## Guidance (non-normative)`
8. `## Mapping (synthesis inputs)`

Do not add `{#CHR-…}` / `{#BEH-…}` anchors. Do not add `## Implementation architecture`
to Idea — architecture belongs in DESIGN_MAP after synthesis.

## Illegal input (fail-closed before synthesis pack)

- Subtask IDs or multi-phase in In-scope
- Clause anchors in cycle file
- Fenced code block longer than 15 lines
- Success table with process conditions (NDF landed, gate phrases, clause counts)
- Empty Out-of-scope when siblings exist

## Greenfield rail (after Idea valid)

```text
派发 → genesis_synthesis (DESIGN_MAP)
架构已确认 → architecture_review gate
派发 → genesis_design (spec/00–50 from approved DESIGN_MAP)
可以建立初始主线 → genesis-pack (greenfield only)
GENESIS已审核
```

## Adopt contrast

Adopt uses `design_evidence.kind=trunk_observation` from existing `src/` @ SHA;
skips synthesis/review/trunk_approval. Same `genesis_design` spec materializer.

## Suggested path

`docs/cycles/cycle-<cycle_id>.md`
