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

## Sandbox false `runtime_unavailable` / wrong `in-host`

**Symptoms:** pack `provider=in-host` or `using_fallback=true` though OpenClaw gateway
is up on the host; Cursor sandbox `ECONNREFUSED` on `127.0.0.1:<gateway>`.

**Fix:**

1. Re-probe / rebuild pack / `dispatch-send` on **host network** (`required_permissions: ["all"]`)
2. Do not treat sandbox probe failure as gateway down ([[META-017]])
3. Implementation packs with `provider=openclaw` MUST NOT silently fall back to in-host

**Prevent:** install `adapters/cursor/rules/ndf-no-sandbox-dispatch.mdc`.

## OpenClaw cross-project session collision

**Symptoms:** `openclaw_session_legacy_shared`, `openclaw_session_not_multi_project_safe`,
`openclaw_session_collision_or_stale_binding`, or one project's `sessions.reset`
wipes another project's Control hop.

**Fix:**

1. Provision a managed per-project agent:
   `python3 spec/meta/tools/ndf_role_binding.py provision-openclaw-session --repo .`
2. If replacing a custom key: add `--rebind` (or bind with `--rebind-openclaw-session`)
3. Confirm `ndf.workflow.yaml` has `roles.control.agent_id` /
   `session_key` / `session_binding_version: ndf-v1`
4. Do **not** share `agent:main:main` across local projects ([[META-020]])

**Note:** Parallelism is across distinct Git repos. Same-repo Control hops stay serial.

## Implementation OpenClaw uses Control model / falls to `in-host`

**Symptoms:** `poc-dispatch` with `provider=openclaw` runs on Control's model
(e.g. deepseek), or after transport error writes `ndf-role-spawn-control.json`
and waits in-host; or gateway errors with
`provider/model overrides are not authorized for this caller`.

**Fix:**

1. `resolve_pack_provider` MUST map `poc_*` → `implementation` even when
   `provider=openclaw` ([[META-021]])
2. Do **not** put `model` in gateway `agent` params; pin `sessions.json` from
   `pack.model` after `sessions.reset` (clear sticky `modelOverride`)
3. META-017: `task` starting with `poc_` + pack `provider=openclaw` MUST NOT
   collapse to `in-host` on OpenClaw transport failure

**Prevent:** keep `_pin_openclaw_session_model` + task-first role map; do not
default META-017 mapped role to `control`.

## `required_gate_not_valid` / `lease_pack_incomplete:episode_id`

**Symptoms:** `poc-dispatch --intent implement` fails after a valid `bundle_dispatch`
(phrase=`派发`) or with an empty `episode_id` on a text-first pack.

**Fix:**

1. Context verify MUST treat SHA-aligned `bundle_dispatch` as the gate-3 substitute ([[META-019]])
2. Inline lease MUST NOT require `episode_id`; synthesize `lease-<topic>-<stamp>` only as a row id
3. MUST NOT `init_episode` or treat Replay as success

**Prevent:** keep `ndf_context.py` receipts including `bundle_dispatch`; do not add
`episode_id` back to `isolated_lease_missing_fields`.

## Live completion false success

**Symptoms:** `dispatch-send` returns succeeded immediately; receipt hop/task mismatches
current pack.

**Fix:**

1. `mv` (not only `cp`) prior `*-completion.json` and `tmp/ndf-agent-completion.json`
   off the live path before send ([[META-018]])
2. Confirm receipt `hop` / `task` / `topic` match the pack

## CLI reset then double reset

**Symptoms:** Feishu/OpenClaw session empty or mid-hop context lost right after send.

**Fix:** after Command CLI `sessions.reset`, run `dispatch-send` with
`NDF_OPENCLAW_RESET_SESSION=0` ([[META-018]]).

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
