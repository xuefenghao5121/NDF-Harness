# Genesis Task Order — fill rules

> role: info (not a product or process clause)
> schema: ndf-genesis-idea/v1
> template: `TASK_ORDER.md.stub`

## Authority

Greenfield Genesis human input MUST use a filled copy of `TASK_ORDER.md.stub`.
Multi-phase prose roadmaps MUST NOT be `source_ref` for `hop=genesis_design`.

This file is filling guidance. It MUST NOT be indexed as NDF must.

## One file = one cycle

| Rule | Detail |
|------|--------|
| `cycle_id` | kebab-case; unique in the repo |
| `maps_to` | MUST be `skeleton` |
| Forbidden | `maps_to: product_contract`; multiple `cycle_id` in one file |
| Sibling cycles | Named only under **Out-of-scope**; MAY live as separate filled files later |

## Required header keys

All of: `schema`, `track`, `bootstrap_mode`, `cycle_id`, `maps_to`, `status`.
Missing any → illegal input → Command MUST NOT build `control-pack`.

## Required sections (fixed names, fixed order)

1. `## Verbatim intent`
2. `## Problem and user`
3. `## In-scope (this cycle)`
4. `## Out-of-scope (this cycle)`
5. `## Success (not SLA)`
6. `## Hard constraints`
7. `## Guidance (non-normative)`
8. `## Mapping`

Do not rename, reorder, or omit sections. Do not add `{#CHR-…}` / `{#BEH-…}` anchors.

## Section rules

| Section | MUST | MUST NOT |
|---------|------|----------|
| Verbatim intent | Blockquote; human wording unchanged | Paraphrase into goals |
| Problem and user | Three bullets: Problem / Target user / Existing alternative | Multi-phase plans |
| In-scope | 1–5 L0 goals for **this** cycle | Subtask IDs; "then phase N"; sibling cycle work |
| Out-of-scope | At least one numbered item; name sibling `cycle_id` when a longer roadmap exists | Empty section |
| Success (not SLA) | Table; Status only `draft` or `tbd` | Numeric must SLA as established |
| Hard constraints | Platform / language; comparison **name** only | Performance numbers as must |
| Guidance | Lead sentence exact: `本栏不是契约。Control MUST NOT 将本栏写入 BEH/API/CON-SLA must。` | Be treated as contract |
| Mapping | Copy stub table verbatim | Change allowed/forbidden columns |

## Illegal input (fail-closed before pack)

- Second phase/cycle treated as In-scope
- Long MUST/SHOULD work-breakdown outside Guidance
- Clause anchors `{#CHR-` / `{#BEH-` / `{#API-` / `{#CON-` / `{#VER-`
- Fenced code block longer than 15 lines
- Missing `cycle_id` or empty Out-of-scope

Command MUST run:

```bash
python3 spec/meta/tools/ndf_genesis_idea.py check <filled-cycle.md>
```

Non-zero exit → MUST NOT `control-pack`.

## Control landing budget

After a valid fill: `hop=genesis_design` writes draft skeleton under `spec/00–50`
using **only** the Mapping table. Clause budget ≤20; default `status=draft`;
`layer=L0` preferred. Guidance MUST NOT become BEH/API/CON-SLA must.
`baseline_status=deferred` when no Trunk yet.

## Suggested path for filled copies

`docs/cycles/cycle-<cycle_id>.md`
