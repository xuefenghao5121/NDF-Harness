# Workflow

Human-facing NDF workflow for Harness 1.0 — five phrases, tracks, gates, and close modes.

## Authority stack

1. Installed repo `AGENTS.md`
2. Installed `spec/meta/` (process SoT)
3. `skill/ndf-workflow/` (command skill — routes phrases only)

The harness package is a seed; after install the **consumer repo wins**.

## Five phrases

| Phrase | Command agent action | Wait for human | Delegates to |
|--------|---------------------|----------------|--------------|
| **初始化项目** | Genesis status + IDEA proposal | Genesis gate phrases | OpenClaw → Claude genesis-pack |
| **提交Idea** | Plane split + draft proposal | 已确认 · 已审核 | OpenClaw |
| **派发** | Gate receipt + build pack | 派发 (this chat) | OpenClaw or Claude by plane |
| **继续** | Amend binder + new pack | 派发 again | OpenClaw → Claude |
| **关闭** | `ndf_close plan` | close mode choice | Claude merge ± OpenClaw |
| *(健康)* | topic-health / graphcheck | — | no dispatch |

Humans MUST NOT be asked to pick skills, CLI subcommands, or init/adopt menus.

## Idea plane

| plane | Write root |
|-------|------------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | two cross-linked proposals |
| ambiguous | **ask human** — do not default to poc |

## Tracks

| track | Scope | Trunk verify |
|-------|-------|--------------|
| **bootstrap** | Genesis → initial trunk | build + acceptance |
| **poc** | `poc/<topic>/` explore | self-test only |
| **promote** | draft→stable + clean merge | compile + perf |
| **process** | `spec/meta/` hygiene | n/a |
| **bug / refactor / rollback** | Trunk fix | compile + perf |

Default for uncertain product ideas: **poc** unless human requests promote.

## Human gates

### Proposal gates

```text
提案 → 已确认 (land) → 已审核 (authorize work)
```

Receipts MAY be recorded in project gates files with approver, time, and content SHA.

### POC gates (text-first default)

Hot path uses **one dispatch gate**:

| gate | phrase | binds |
|------|--------|-------|
| `bundle_dispatch` | 派发 | review-slice bundle SHA |

Legacy three-gate topics (`TOPIC已审核`, `DESIGN已审核`, `可以开始实现`) remain readable;
new topics use text-first bundle dispatch after proposal 已审核.

**File existence ≠ approval.** Each receipt records `approved_by`, `approved_at`,
`approved_content_sha`, `bundle_mode`, `slice_manifest_sha`.

### Genesis gates (bootstrap)

Serial: `IDEA已审核` → `CHARTER已审核` → `ARCHITECTURE已审核` →
`VERIFICATION已审核` → `可以建立初始主线` → `GENESIS已审核`.

## POC lifecycle

```text
提案已审核
  → write binder poc/<topic>/ndf/ (TOPIC, DESIGN, PERF_BASELINE, DELTA, INTERFACE, GATES)
  → human 派发
  → poc-dispatch --send
  → disk completion
  → 继续 (amend?) or 关闭
```

**Write isolation (poc):** MUST NOT modify Trunk `src/`, `include/`, `tests/` — copy into
`poc/<topic>/` first.

**Perf numbers:** compare Δ% only from TOPIC→PERF_BASELINE binding, not from SLA tables.

## Gate drift

When contract **slices** change, bundle SHA changes → gate drift.

1. Command shows slice unified diff (`gate_drift_markdown`).
2. Human reviews diff.
3. Human says **派发** → new snapshot persisted.
4. Re-dispatch.

Append-only changes (Numbers, Rounds, evidence, COMMITS) do **not** invalidate bundle SHA.

## Close modes

Run plan first (read-only):

```bash
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject
```

| mode | TOPIC status | Trunk |
|------|--------------|-------|
| **promote** | promoted | clean merge + verify |
| **partial** | exploring | subset merged; topic continues |
| **reject** | rejected | revert / confirm clean; archive binder |

Promote MUST include semantic-core decision (distill model / defer / skip).

## Success criterion

```text
ndf-agent-completion/v1 on disk at completion_receipt_path
```

Transport ACK, chat OK, or stdout JSON alone ≠ success.

## Related

- [`WORKFLOW-OVERVIEW.md`](WORKFLOW-OVERVIEW.md) — diagrams and closed loops
- [`WORKFLOW-FEATURES.md`](WORKFLOW-FEATURES.md) — META capability catalog
- [`TOOLS.md`](TOOLS.md) — CLI for dispatch and health
- [`../skill/ndf-workflow/SKILL.md`](../skill/ndf-workflow/SKILL.md) — skill entry
