# Architecture

Product-neutral architecture of NDF Harness 1.0 — how command, control, implementation,
and disk completion fit together.

## End-to-end dispatch

```mermaid
flowchart LR
  Human[Human five phrases] --> Command[Command role on host]
  Command --> Pack[Pack builder + context verify]
  Pack -->|Control role| Control[OpenClaw or in_host or dual_session]
  Pack -->|Implementation role| Impl[Claude ACP or in_host or dual_session]
  Control --> Disk["Disk ndf-agent-completion/v1"]
  Impl --> Disk
  Disk --> Command
```

**Success** is a durable completion receipt on disk. Transport ACK, stdout, or chat messages
are not success signals.

## Package layers

```mermaid
flowchart TB
  subgraph harness [NDF Harness package]
    Norms[norms/ meta + product-tree seed]
    Workflow[workflow/ AGENTS + ndf.workflow.yaml]
    Governance[governance/tools/ ndf_*.py]
    Skills[skill/ndf-workflow/ five phrases]
    Adapters[adapters/ runtime mounts]
    Templates[templates/ POC + genesis stubs]
    Migration[migration/ 0.2 detect]
  end

  subgraph consumer [Consumer repo after install]
    SpecMeta[spec/meta/ authoritative process SoT]
    SpecProduct[spec/ product tree]
    Agents[AGENTS.md command entry]
    Tools[spec/meta/tools/]
    POC[poc/topic/ndf/ binders]
  end

  Norms -->|install scaffold| SpecMeta
  Workflow --> Agents
  Governance --> Tools
  Skills --> Adapters
  Templates --> SpecMeta
```

After install, **consumer `spec/meta/` and `AGENTS.md` are authoritative** for that repo.

## Three agent layers

| Layer | Agent | Writes | Reads |
|-------|-------|--------|-------|
| **Command** | Cursor / generic + `ndf-workflow` | tmp packs, gate append, dispatch triggers | AGENTS, spec/meta, binders |
| **Control** | OpenClaw | `spec/open/`, `spec/meta/open/`, `poc/*/ndf/`, state | Same manifest SHA as implementation |
| **Implementation** | Claude Code | `poc/<topic>/` (POC); `src/` (promote) | allowed_write_root, binders |

Command MUST NOT write worker implementation or call transport directly without pack pipeline.

## Idea plane + tracks

```mermaid
flowchart TD
  Idea[Idea] --> Plane{plane?}
  Plane -->|product| Open[spec/open/]
  Plane -->|process| MetaOpen[spec/meta/open/]
  Plane -->|mixed| Split[Two linked proposals]
  Plane -->|ambiguous| Ask[Ask human]

  Open --> Track{track}
  Track --> Bootstrap[bootstrap / Genesis]
  Track --> POC[poc explore]
  Track --> Promote[promote / bug / refactor]
  Track --> Process[process meta only]
```

Tracks route write boundaries and verification obligations (compile/perf only on Trunk paths).

## Context pipeline

```mermaid
sequenceDiagram
  participant C as Command
  participant M as ndf_context
  participant V as context verify
  participant D as ndf_dispatch_send
  participant W as Worker

  C->>M: manifest + role-plan
  M->>V: bounded contexts per role
  V-->>C: pass or blockers + SHA
  C->>D: approved pack
  D->>W: OpenClaw or ACP
  W-->>D: progress heartbeats
  W-->>C: ndf-agent-completion/v1
```

OpenClaw and Claude Code role plans MUST reference the **same `manifest_sha`**.

## Gate review-slice + drift

Gate identity (META-010) binds **review slices** — contract sections marked with
`ndf:gate-slice` comments — not whole files.

```mermaid
flowchart TD
  Edit[Edit contract slice] --> Bundle[Recompute bundle SHA]
  Bundle --> Cmp{vs GATES approved?}
  Cmp -->|match| OK[safe to dispatch]
  Cmp -->|drift| Diff[gate_drift slice diff]
  Diff --> Human[Human reviews diff]
  Human --> Phrase[Human says 派发]
  Phrase --> Snap[persist_gate_slice_snapshot]
  Snap --> OK

  Meas[Append Numbers/Rounds/evidence] --> NoChurn[SHA unchanged]
```

Mutable sections (perf numbers, delta rounds, evidence, commits) stay outside gate SHA churn.

## Graph / index loop

```mermaid
flowchart LR
  Spec[spec/ markdown SoT] --> Index[ndf_index]
  Index --> GraphJSON[graph.json + INDEX.md]
  GraphJSON --> GraphCheck[ndf_graphcheck]
  GraphCheck --> Advise[ndf_advise optional]
  Advise --> Proposal[Human proposal]
  Proposal --> Spec
```

- **`--meta`**: process-profile self-consistency (hard_errors must be 0).
- **`--product`**: adopted product tree semantics.
- Reports default to `tmp/`; MUST NOT write under `spec/`.

## Security boundaries

| Risk | Control |
|------|---------|
| Unapproved dispatch | bundle SHA + human phrase in GATES |
| Context smuggling | `context_verify` fail-closed |
| Path escape | `allowed_write_root`, poc isolation |
| Fake success | completion schema + path verification |
| Concurrent POC writes | lease / run_id checks |
| SoT overwrite | install protected files; advise simulate-only |

See [`SECURITY.md`](SECURITY.md).

## Retired control plane

Commander, Episode, Replay, and ActionSpec (ADR-META-004) are **not** part of 1.0 daily path.
`ndf_replay.py` exists as a tombstone (exit 2). Use `ndf_workflow_status` + disk completion.

## Related docs

- [`WORKFLOW.md`](WORKFLOW.md) — phrases and tracks
- [`TOOLS.md`](TOOLS.md) — CLI reference
- [`INSTALL.md`](INSTALL.md) — what lands where
- [`WORKFLOW-OVERVIEW.md`](WORKFLOW-OVERVIEW.md) — operational closed loops
