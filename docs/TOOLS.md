# Tools

Reference for every Python script shipped under `governance/tools/`. After install they
live at `spec/meta/tools/` in the consumer repo.

**Report policy:** derived reports default to `tmp/`; writing under `spec/` exits **2**
(`ndf_report_io`).

## Index

| Script | Role |
|--------|------|
| [`ndf_index.py`](#ndf_indexpy) | Clause index / validate / impact |
| [`ndf_graphcheck.py`](#ndf_graphcheckpy) | Graph semantic linter |
| [`ndf_bindcheck.py`](#ndf_bindcheckpy) | Binder / provenance linter |
| [`ndf_advise.py`](#ndf_advisepy) | Graph/bind surgical advisor |
| [`ndf_advise_bind.py`](#ndf_advise_bindpy) | Bind advisor implementation |
| [`ndf_close.py`](#ndf_closepy) | POC close planner |
| [`ndf_report_io.py`](#ndf_report_iopy) | Report path policy |
| [`ndf_poc_isolation.py`](#ndf_poc_isolationpy) | POC write isolation |
| [`ndf_perf_baseline.py`](#ndf_perf_baselinepy) | Perf baseline card |
| [`ndf_gate_slices.py`](#ndf_gate_slicespy) | Review-slice gate helpers |
| [`ndf_context.py`](#ndf_contextpy) | Context compiler |
| [`ndf_workflow_evidence.py`](#ndf_workflow_evidencepy) | Evidence / receipt helpers |
| [`ndf_poc_dispatch.py`](#ndf_poc_dispatchpy) | POC dispatch safety kernel |
| [`ndf_workflow_status.py`](#ndf_workflow_statuspy) | Workflow CLI hub |
| [`ndf_dispatch_send.py`](#ndf_dispatch_sendpy) | Pack transport + completion wait |
| [`ndf_acp_session_bootstrap.py`](#ndf_acp_session_bootstrappy) | ACP session bootstrap |
| [`ndf_role_binding.py`](#ndf_role_bindingpy) | Role adapter bind / probe / resolve |
| [`ndf_replay.py`](#ndf_replaypy) | **Retired tombstone** |

---

## ndf_index.py

**Purpose:** Build searchable index and `graph.json` from markdown SoT.

**Commands:**

```bash
python3 ndf_index.py index [--meta]
python3 ndf_index.py validate [--meta]
python3 ndf_index.py impact <CLAUSE_ID>
python3 ndf_index.py diff <git-ref>
python3 ndf_index.py poc-topics
```

**Output:** `spec/INDEX.md`, `spec/graph.json` (derived, not must正文).

**Exit codes:** `0` ok; `1` validation/index errors.

---

## ndf_graphcheck.py

**Purpose:** Semantic graph linter — cycles, stable→draft deps, conflict asymmetry, meta dangling.

**Commands:**

```bash
python3 ndf_graphcheck.py [--meta | --product]
python3 ndf_graphcheck.py --format text|json --report tmp/ndf-graphcheck.md
python3 ndf_graphcheck.py --detail --hop N
```

**Output:** Report file or stdout (`--report -`).

**Exit codes:** `0` pass; `1` hard errors; `2` bad report path.

---

## ndf_bindcheck.py

**Purpose:** Binder provenance — trailers, COMMITS ledger, dual-head, observation grain.

**Commands:**

```bash
python3 ndf_bindcheck.py check --topic <topic> [--report tmp/ndf-bindcheck.md]
python3 ndf_bindcheck.py scan [--zombie] [--drift]
```

**Exit codes:** `0` pass; `1` findings; `2` report path error.

---

## ndf_advise.py

**Purpose:** Interactive advisor — surgical options + in-memory simulate (**never writes SoT**).

**Commands:**

```bash
python3 ndf_advise.py plan --surface graph|bind [--meta] [--report tmp/ndf-advise.md]
python3 ndf_advise.py simulate --surface graph|bind --option <id>
```

**Exit codes:** `0` ok; `1` no plan / simulate failure; `2` report path error.

---

## ndf_advise_bind.py

**Purpose:** Bind-surface advisor implementation (library; invoked by `ndf_advise --surface bind`).

**CLI:** none — import-only.

---

## ndf_close.py

**Purpose:** Read-only close round-trip plan (promote / partial / reject).

**Commands:**

```bash
python3 ndf_close.py plan --topic <topic> --mode promote|partial|reject [--json]
```

**Output:** stdout plan markdown or JSON under `tmp/` when `--report` used.

**Exit codes:** `0` plan emitted; `1` topic/plan errors.

---

## ndf_report_io.py

**Purpose:** Shared report path resolver — enforces tmp-only policy.

**API:** `resolve_report_path(raw, default_rel)` → `Path | None`.

**Exit codes:** raises `ReportPathError` → callers exit `2`.

---

## ndf_poc_isolation.py

**Purpose:** Verify POC commits/workspace do not touch Trunk `src/`, `include/`, `tests/`.

**Commands:**

```bash
python3 ndf_poc_isolation.py check --topic <topic> [--workspace]
```

**Exit codes:** `0` isolated; `1` violation detected.

---

## ndf_perf_baseline.py

**Purpose:** Resolve and validate TOPIC `perf_baseline` → PERF_BASELINE card fields.

**Commands:**

```bash
python3 ndf_perf_baseline.py show --topic <topic>
python3 ndf_perf_baseline.py check --topic <topic>
```

**Exit codes:** `0` valid; `1` missing/mismatch fields.

---

## ndf_gate_slices.py

**Purpose:** Canonical review slices, bundle SHA, drift diff, snapshot persistence (META-010).

**API:** library used by `ndf_workflow_status`, `ndf_context`.

**Key functions:** slice extraction, `bundle_sha`, `gate_drift_explain`, `persist_gate_slice_snapshot`.

**CLI:** none — import-only.

---

## ndf_context.py

**Purpose:** Compile task manifest + role-specific bounded contexts; verify manifest/plan SHA.

**Commands:**

```bash
python3 ndf_context.py manifest --task <task> --topic <topic> [--json]
python3 ndf_context.py role-plan --manifest-sha <sha> --role control|implementation
python3 ndf_context.py verify --pack-file <pack.json>
```

**Output:** JSON to stdout; optional evidence under `tmp/`.

**Exit codes:** `0` ok; `1` compile/verify failure.

---

## ndf_workflow_evidence.py

**Purpose:** Shared receipt hashing, completion validation, safe tmp paths.

**API:** library for dispatch and close tools.

**CLI:** none — import-only.

---

## ndf_poc_dispatch.py

**Purpose:** POC dispatch **hard gate** kernel (identity, bundle license, isolation, context, budget).

**API:** invoked by `ndf_workflow_status poc-dispatch`.

**CLI:** none — import-only.

---

## ndf_workflow_status.py

**Purpose:** Workflow hub — packs, health, text-first dispatch.

**Commands:**

```bash
python3 ndf_workflow_status.py poc-dispatch --topic <t> --intent implement|measure [--send]
python3 ndf_workflow_status.py control-pack --task <task> … [--json]
python3 ndf_workflow_status.py project-control-pack … [--json]
python3 ndf_workflow_status.py genesis-status [--json]
python3 ndf_workflow_status.py genesis-pack --mode greenfield|adopt [--json]
python3 ndf_workflow_status.py topic-health --topic <t> [--json]
python3 ndf_workflow_status.py spec-health [--json]
python3 ndf_workflow_status.py host-pids [--json]
python3 ndf_workflow_status.py dispatch-probe [--json]
python3 ndf_workflow_status.py close-plan --topic <t> --mode …
python3 ndf_workflow_status.py lease-record …
```

**Output:** JSON status, pack paths under `tmp/`.

**Exit codes:** `0` success / safe; `1` blockers; subcommands may vary.

---

## ndf_dispatch_send.py

**Purpose:** Send approved pack to OpenClaw or Claude ACP; wait; validate disk completion.

**Commands:**

```bash
python3 ndf_dispatch_send.py --pack-file tmp/ndf-dispatch-last-pack.json [--prepare-only]
```

**Input:** pack JSON with `completion_receipt_path`, `workspace.repo_root`, manifest SHA.

**Output:** `tmp/ndf-dispatch-last.json` snapshot.

**Exit codes:** `0` validated completion; `1` blockers / timeout / fake completion.

---

## ndf_acp_session_bootstrap.py

**Purpose:** Bootstrap Claude Code ACP session from AGENTS.md binding.

**Commands:**

```bash
python3 ndf_acp_session_bootstrap.py [--resume]
```

**Exit codes:** `0` ok; `1` bootstrap failure.

---

## ndf_role_binding.py

**Purpose:** Bind / probe / resolve Command / Control / Implementation adapters
(`ndf.workflow.yaml`). Used at init (角色已配置) and by dispatch when preferred CLI
is missing (`in-host` / `dual-session` / `custom`).

**Commands:**

```bash
python3 ndf_role_binding.py probe --repo . --json
python3 ndf_role_binding.py status --repo . --json
python3 ndf_role_binding.py bind --repo . \
  --command cursor --control openclaw --control-fallback in-host \
  --implementation claude-code --implementation-fallback in-host
```

**Exit codes:** `0` roles bound / probe ok; `1` unbound; `2` bind args error.

---

## ndf_replay.py

**Purpose:** **Retired tombstone** (ADR-META-004). Replay/Episode control plane removed.

**Commands:**

```bash
python3 ndf_replay.py   # always prints retirement message to stderr
```

**Exit codes:** **2** always.

Daily path: `ndf_workflow_status` + disk `ndf-agent-completion/v1`.

---

## Typical chains

```bash
# Meta hygiene
ndf_index.py index --meta && ndf_graphcheck.py --meta

# POC dispatch
ndf_workflow_status.py poc-dispatch --topic T --intent implement --send

# Close
ndf_close.py plan --topic T --mode promote
```

See [`../governance/docs/GOVERN.md`](../governance/docs/GOVERN.md) for governance card.

## Related

- [`WORKFLOW.md`](WORKFLOW.md)
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)
- [`../governance/tools/README.md`](../governance/tools/README.md)
