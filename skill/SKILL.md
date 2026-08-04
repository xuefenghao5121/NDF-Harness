# NDF Harness Skill（运行时无关核心）

> **SoT for modes:** this file  
> **Adapters:** `../adapters/<runtime>/` — thin pointers only  
> **Do not** duplicate this workflow inside a single IDE skill tree

## When to use

- 「用 NDF 初始化 / 接入项目」→ **init** / **adopt**
- 「NDF 治理 / 跑 graphcheck / advise」→ **govern**
- 「同步 harness 规范种子或工具说明」→ **sync**

Works with OpenClaw, Claude Code, OpenCode, Cursor, or any agent that can read this file + root `AGENTS.md`.

## Modes

| Mode | Behavior |
|------|----------|
| **init** | Install `norms/` + root `AGENTS.md` + governance docs; wait for human confirm before filling ⟨TBD⟩ |
| **adopt** | Diff existing tree; propose gaps only; never overwrite finalized AGENTS/meta without diff |
| **govern** | Emit CLI from GOVERNANCE main chain; **never** auto-apply sandbox to SoT |
| **sync** | Refresh seeds/VENDOR from package version; diff prompts; no silent overwrite |

See [MODES.md](MODES.md) checklists and [reference.md](reference.md).

## Hard rules

1. Business flow text lives only in: `skill/` + `workflow/AGENTS.md` + `norms/` + `governance/`  
2. Adapters MUST NOT copy full process prose  
3. Tools never silently write clauses or git history  
4. Package MUST stay product-domain free  
5. Prefer root `AGENTS.md` as the cross-runtime command entry
