# Workflow Overview

Human-readable overview of NDF Workflow 1.0 — call graph and closed loops.

**Not SoT.** Clause text lives in installed `spec/meta/process.md`. Entry skill:
[`skill/ndf-workflow/SKILL.md`](../skill/ndf-workflow/SKILL.md).

## One sentence

Human speaks five phrases to the **command surface** → internal modules route →
**OpenClaw** (documents) / **Claude Code** (code) → disk `ndf-agent-completion/v1`.
Contract changes are detected by **review-slice SHA + diff**; graph problems loop through
**graphcheck → proposal → re-check**.

| Layer | Who | Role |
|-------|-----|------|
| Command | Command agent + `ndf-workflow` | phrases, wait for human, build pack, report blockers |
| Control | OpenClaw | proposals, binders, gate docs |
| Implementation | Claude Code | POC / genesis / promote code |

Success = disk completion. No panel obligation.

## Skill call graph

```mermaid
flowchart TB
  Human[Human five phrases] --> Skill[ndf-workflow skill]

  Skill --> Init[初始化项目]
  Skill --> Idea[提交Idea]
  Skill --> Disp[派发]
  Skill --> Cont[继续]
  Skill --> Close[关闭]
  Skill --> Health[健康]

  Init --> Genesis[genesis.md]
  Idea --> Intake[intake.md]
  Intake --> Proposal[proposal.md]
  Disp --> Poc[poc.md]
  Cont --> Poc
  Disp --> Delegate[delegate.md]
  Cont --> Delegate
  Close --> CloseM[close.md]
  Health --> HealthM[health.md]

  Delegate --> CtrlCLI[control-pack]
  Delegate --> PocCLI[poc-dispatch]
  Delegate --> GenCLI[genesis-pack]
  CloseM --> CloseCLI[ndf_close plan]

  CtrlCLI --> OpenClaw[OpenClaw]
  PocCLI --> Claude[Claude Code]
  GenCLI --> Claude
  CloseCLI --> Claude
  CloseCLI --> OpenClaw

  OpenClaw --> Disk[ndf-agent-completion/v1]
  Claude --> Disk
```

Internal modules (`genesis.md`, `poc.md`, …) are **not** a second public skill menu.

## Phrase routing

| Phrase | Modules | Human waits | Delegate |
|--------|---------|-------------|----------|
| 初始化项目 | genesis → delegate | Genesis gate phrases | OpenClaw → Claude |
| 提交Idea | intake → proposal → delegate | 已确认 · 已审核 | OpenClaw |
| 派发 | poc + delegate | 派发 | Claude or OpenClaw |
| 继续 | poc + delegate | 派发 again | OpenClaw → Claude |
| 关闭 | close → delegate | close mode | Claude ± OpenClaw |
| 健康 | health | — | read-only |

## Loop A — Context verify

```mermaid
flowchart LR
  Ask[Health / ready?] --> TH[topic-health]
  TH --> Pack[build pack]
  Pack --> CV[context verify]
  CV -->|pass| OK[safe_to_dispatch]
  CV -->|fail| Bl[blockers + SHA]
  Bl --> Fix[fix binder / re-review]
  Fix --> Pack
```

Humans see blockers and SHA — not full context dumps. Both workers share one `manifest_sha`.

## Loop B — Amend detection

```mermaid
flowchart TD
  Edit[edit contract slice] --> SHA[recompute bundle SHA]
  SHA --> Cmp{vs GATES?}
  Cmp -->|same| Go[dispatch OK]
  Cmp -->|drift| Diff[slice diff]
  Diff --> Phrase[human 派发 + snapshot]
  Phrase --> SHA

  Meas[Numbers/Rounds/evidence only] --> NoChurn[no re-review]
```

Command MUST show slice diff on drift — not only hex SHAs.

## Loop C — Graph health

```mermaid
flowchart TD
  Sym[graph/binder wrong] --> Health[健康]
  Health --> GC[graphcheck]
  Health --> IDX[index validate]
  Health --> BC[bindcheck]
  GC --> R[tmp findings]
  R --> Idea[提交Idea]
  Idea --> Land[land SoT]
  Land --> Recheck[re-check]
```

| Tool | Checks |
|------|--------|
| graphcheck | cycles, stable deps, meta dangling |
| index | links, indexability |
| bindcheck | ledger, dual-head, grain |
| advise | options only — no SoT writes |

## End-to-end ring

```text
Idea → 已确认 → 已审核
  → binder poc/<topic>/ndf/
  → 派发 (bundle SHA + slice snapshot)
  → pack + context verify
  → worker → disk completion
  → 继续: contract change? → diff → 派发
           measure only? → no SHA churn
  → 健康: graphcheck / bindcheck / index
  → 关闭: ndf_close plan → merge or reject
```

## Hard vs soft gates (daily POC)

**Hard block:** identity, human bundle, write root, isolation, concurrent run, context verify,
ACP budget, disk completion.

**Soft audit (health / close):** full meta graph, bindcheck, projection/Replay (retired).

## Related files

| Path | Role |
|------|------|
| `skill/ndf-workflow/SKILL.md` | human entry |
| `spec/meta/process.md` | META-010/011/012 |
| `docs/WORKFLOW.md` | phrases + tracks |
| `docs/TOOLS.md` | CLI reference |
| `docs/ARCHITECTURE.md` | layer diagram |

## Retired

Commander, Episode, Replay, ActionSpec — see ADR-META-004. Do not document as active paths.
