# Migration to 1.0

Upgrade guide for repositories on NDF Harness **0.2.x** or legacy POC conventions.

## What changed

| Area | 0.2 / legacy | 1.0 |
|------|--------------|-----|
| Human entry | init/adopt/govern skill menu | five phrases (`ndf-workflow`) |
| POC dispatch gate | three phrases optional | `bundle_dispatch` + 派发 (text-first) |
| Gate SHA | whole-file common | review-slice bundle + `slice_manifest_sha` |
| Control plane | Commander, Replay, ActionSpec | retired (ADR-META-004) |
| Success | transport / panel | disk `ndf-agent-completion/v1` |
| Installer | manual copy steps | `install.py plan/adopt/install/verify` |

## Detect

```bash
python3 packages/ndf-harness/migration/detect_0_2.py --repo . --pretty
```

JSON fields:

| Field | Meaning |
|-------|---------|
| `has_version_0_2` | VERSION 0.2.x or old skill init/adopt menu |
| `legacy_three_gates` | TOPIC已审核 / DESIGN已审核 / 可以开始实现 in GATES |
| `whole_file_sha_gates` | Missing review_slice columns or whole-file markers |
| `commander_or_replay_residue` | Active Commander/Episode/Replay/ActionSpec references |
| `custom_local_meta` | Local spec/meta differs from harness seed |
| `recommended_actions` | Scaffold-only guidance; no silent SoT overwrite |

Exit codes: **0** always on successful scan; **2** on I/O error only.

## Migration steps (summary)

Detailed checklist: [`../migration/plan_1_0.md`](../migration/plan_1_0.md).

1. **Detect** — save JSON to `tmp/`.
2. **Adopt plan** — `install.py adopt --json`; review conflicts.
3. **Install scaffold** — without `--force` for protected files.
4. **Verify** — `install.py verify --json`.
5. **Migrate GATES** — review-slice SHA; append receipts; invalidate legacy rows if needed.
6. **Retire** Commander/Replay skills and references.
7. **Re-dispatch** — human 派发 after slice diff review.

## Legacy three-gate POC

Topics with historical gate rows remain valid as audit trail. For ongoing work:

- Add `bundle_mode=review_slice` and `slice_manifest_sha` columns.
- Obtain new **派发** receipt binding current contract bundle.
- Use `ndf_gate_slices` helpers for drift diffs.

Do not delete old gate rows.

## Whole-file SHA gates

Replace with slice manifest SHA:

1. Mark gate-slice regions in TOPIC/DESIGN/PERF/DELTA/INTERFACE.
2. Compute bundle via `ndf_gate_slices` (installed under `spec/meta/tools/`).
3. Append new dispatch row; set old rows `status=invalidated` if superseded.

## Commander / Replay cleanup

Remove or archive:

- Skills exposing Commander menus
- Replay/Episode CLI wrappers in daily docs
- ActionSpec registry references (except retirement notes)

Keep `ndf_replay.py` tombstone — it exits 2 with retirement message.

## Custom local meta

If `custom_local_meta.detected`:

- Treat local `spec/meta/` as authoritative.
- Merge harness seed changes via **process** proposal (已确认 → 已审核).
- Never `install.py install --force` on finalized clauses without explicit human approval.

## Post-migration verification

```bash
python3 install.py verify --repo . --profile dual-track --runtime cursor --json
python3 spec/meta/tools/ndf_graphcheck.py --meta
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
```

## Related

- [`../migration/README.md`](../migration/README.md)
- [`INSTALL.md`](INSTALL.md)
- [`WORKFLOW.md`](WORKFLOW.md)
