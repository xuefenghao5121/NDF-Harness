# Migration 0.2 → 1.0

Step-by-step plan for brownfield repositories that installed NDF Harness 0.2.x or carry
legacy POC gate patterns.

## Prerequisites

- Read [`docs/MIGRATION-1.0.md`](../docs/MIGRATION-1.0.md) for terminology.
- Run the detector and save output:

```bash
python3 packages/ndf-harness/migration/detect_0_2.py --repo . --pretty \
  > tmp/ndf-migration-detect.json
```

- Commit or stash local work; migration is review-heavy, not silent.

## Phase 1 — Detect and plan

1. Review `recommended_actions` from detector JSON.
2. Note `custom_local_meta` hits — these are **protected**; do not `--force` overwrite.
3. List Commander/Replay residue files for manual retirement.

## Phase 2 — Adopt harness 1.0 scaffold

From the harness package root (or vendored copy):

```bash
python3 install.py plan --repo /path/to/consumer --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code --json \
  > tmp/ndf-install-plan.json

python3 install.py adopt --repo /path/to/consumer --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code --json
```

`adopt` prints the plan only (no writes). Inspect `conflict` and `skip` rows.

Apply scaffold (creates missing files; skips protected SoT):

```bash
python3 install.py install --repo /path/to/consumer --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code
```

**Without `--force`**, installer MUST NOT overwrite:

- `AGENTS.md` (if present and settled)
- `spec/meta/*.md` process clauses
- Existing gate receipts (append-only)

## Phase 3 — Review diff

Human review checklist:

| Area | Action |
|------|--------|
| `AGENTS.md` | Merge harness 1.0 command-layer updates manually if conflict |
| `spec/meta/tools/` | Accept new tools (`ndf_context`, `ndf_dispatch_send`, …) |
| `.cursor/skills/ndf-workflow/` | Replace init/adopt public menu with five-phrase skill |
| `ndf.workflow.yaml` | Add if missing |
| Retired skills | Remove `Commander`, `Replay`, `ActionSpec` entry points |

Run verify:

```bash
python3 install.py verify --repo /path/to/consumer --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code --json
```

Fix failures before proceeding.

## Phase 4 — Migrate gate snapshots to review-slice SHA

For each active `poc/<topic>/ndf/GATES.md`:

1. Ensure binder files use `<!-- ndf:gate-slice begin=… -->` markers (see
   `templates/poc/GATES.md.stub`).
2. Add columns: `bundle_mode=review_slice`, `slice_manifest_sha`.
3. Compute bundle SHA via gate slice helper (installed at `spec/meta/tools/ndf_gate_slices.py`).
4. **Append** new `bundle_dispatch` row with phrase `派发` — do not delete old receipts;
   mark superseded rows `invalidated` if whole-file SHA was used.
5. Persist slice snapshot on dispatch (`persist_gate_slice_snapshot`) so future drift diffs work.

Legacy three-gate phrases (`TOPIC已审核`, `DESIGN已审核`, `可以开始实现`) MAY remain as
historical rows; the hot path uses `bundle_dispatch` + `派发`.

## Phase 5 — Retire commander / replay skills

1. Delete or archive runtime skills that expose Commander, Episode, Replay, or ActionSpec menus.
2. Remove references from `.cursor/skills/`, `skills/`, `.opencode/skills/` except tombstone notes.
3. Confirm `ndf_replay.py` is present only as tombstone (exit 2).
4. Update team docs to point to [`docs/WORKFLOW.md`](../docs/WORKFLOW.md) five phrases.

## Phase 6 — Re-dispatch after human review

For each exploring topic:

1. Run topic health:

```bash
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
```

2. Fix blockers (context verify, gate drift, isolation).
3. Human reviews slice diff if contract changed.
4. Human says **派发** in command chat; command agent writes gate receipt + dispatches:

```bash
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement --send
```

5. Success = disk `ndf-agent-completion/v1` receipt, not transport ACK.

## Phase 7 — Baseline governance

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_graphcheck.py --meta
python3 spec/meta/tools/ndf_graphcheck.py --product
```

Reports go under `tmp/` only.

## Rollback

Harness install does not mutate git history. To rollback:

- Restore pre-migration commit of conflicted files.
- Keep appended GATES rows (append-only discipline).

## See also

- [`README.md`](README.md) — migration index
- [`../docs/MIGRATION-1.0.md`](../docs/MIGRATION-1.0.md) — detailed breaking changes
- [`../docs/INSTALL.md`](../docs/INSTALL.md) — install profiles and runtimes
