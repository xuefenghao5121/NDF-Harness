# Troubleshooting

Operational fixes for NDF Harness 1.0 workflows. Reports belong in `tmp/` only.

## SHA mismatch / gate drift

**Symptoms:** `gate_drift`, `bundle_sha_mismatch`, `invalidated` gate, dispatch blocked.

**Fix:**

1. Run topic health: `ndf_workflow_status.py topic-health --topic <t> --json`
2. Read `gate_drift_markdown` or `tmp/ndf-gate-drift-<topic>.md`
3. If contract slices changed: human reviews diff → says **派发** → new snapshot
4. If only Numbers/Rounds/evidence changed: SHA should be unchanged — check slice markers

**Prevent:** call `persist_gate_slice_snapshot` when recording 派发 receipt.

## context verify failed

**Symptoms:** `context_verify_failed`, `manifest_sha` / `context_plan_sha` mismatch in pack.

**Fix:**

1. Rebuild pack from same binder HEAD
2. Ensure OpenClaw and Claude role plans share one `manifest_sha`
3. Check `ndf_context.py verify --pack-file …` output for blockers
4. Reduce pack scope if ACP context over budget

## graphcheck / bindcheck failures

**Symptoms:** `hard_errors > 0`, `cycle`, `stable_dep`, `binder-dual-head`.

**Fix:**

1. `ndf_graphcheck.py --report tmp/ndf-graphcheck.md`
2. `ndf_bindcheck.py check --topic <t> --report tmp/ndf-bindcheck.md`
3. Optional: `ndf_advise.py plan --surface graph|bind` (simulate only)
4. Fix via **提交Idea** process/product proposal — advise never writes SoT
5. Re-run index + graphcheck

## Workspace / repo_root wrong

**Symptoms:** `repo_root_mismatch`, files written outside expected tree, dispatch unsafe.

**Fix:**

1. Confirm pack `workspace.repo_root` matches consumer git root
2. Update per-project state file (OpenClaw template) if topic switched
3. Never use global agent state for project paths
4. Re-run poc-dispatch with corrected workspace binding

## Transport / dispatch

**Symptoms:** dispatch hangs, `openclaw_nonzero_exit`, `acp_nonzero_exit`, timeout.

**Fix:**

1. `ndf_workflow_status.py dispatch-probe --json`
2. `ndf_workflow_status.py host-pids --json` if fork/EAGAIN errors
3. Confirm `openclaw` / `claude` on PATH (`install.py verify`)
4. Bootstrap ACP: `ndf_acp_session_bootstrap.py`
5. Check env: `NDF_OPENCLAW_*`, `NDF_ACP_PING_SEC`, stall/max seconds

Transport ACK alone is **not** success — see completion section.

## Completion / fake success

**Symptoms:** worker said OK but command reports failure; missing receipt.

**Fix:**

1. Read pack `completion_receipt_path` on disk
2. Validate schema `ndf-agent-completion/v1`
3. Check receipt SHA matches pack manifest / repo HEAD expectations
4. Re-dispatch only after fixing root cause — do not copy stdout as receipt

## POC isolation violation

**Symptoms:** `ndf_poc_isolation.py check` exit 1; Trunk paths in POC commits.

**Fix:**

1. Move changes into `poc/<topic>/` copies
2. Revert Trunk `src/include/tests` changes
3. Re-run isolation check before dispatch

## Install / verify failures

**Symptoms:** `install.py verify` exit 2.

**Fix:**

1. Re-run with `--json` for missing tool list
2. Install missing runtime skill dir
3. For brownfield: use `adopt` plan — do not `--force` meta without review

## Concurrent write / lease

**Symptoms:** `topic_active_lease`, `concurrent_write_run`.

**Fix:**

1. Wait for in-flight hop or run dispatch-probe
2. Release stale lease via documented lease-record path
3. Do not dispatch two writes to same topic concurrently

## Still stuck

1. **健康** — topic-health + graphcheck + bindcheck
2. [`SECURITY.md`](SECURITY.md) — fail-closed expectations
3. [`TOOLS.md`](TOOLS.md) — exact CLI exit codes
4. [`MIGRATION-1.0.md`](MIGRATION-1.0.md) — legacy pattern cleanup
