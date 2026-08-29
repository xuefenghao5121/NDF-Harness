---
name: ndf-workflow
description: >-
  Unique human-facing NDF workflow entry (ADR-META-004): Command Agent surface
  for 初始化项目 / 提交Idea / 派发 / 继续 / 关闭. Resolves Control/Implementation via
  ndf.workflow.yaml role bindings. Never asks the user to pick a skill, button, or command.
disable-model-invocation: false
---

# NDF Workflow（唯一人类入口）

## Authority

1. **Installed repo** `AGENTS.md`
2. **Installed** `spec/meta/`（`README.md`、`language.md`、`process.md`、`decisions/`）
3. **This skill tree**（`skill/ndf-workflow/`）
4. 项目 `ndf.workflow.yaml`（三角色绑定）

**MUST NOT** reverse-correct consumer SoT from `packages/ndf-harness/`. The package
is a portable seed; the installed repo is authoritative after init/adopt.

## 三层能力（Command / Control / Implementation）

| 层 | 角色 | 默认绑定 | 做什么 |
|----|------|----------|--------|
| **Command** | Command Agent（当前宿主） | 当前宿主 + 本 skill | 听五句口令、分流 Idea、等人审、造 pack、调 CLI、报告 blockers / 写根 / 磁盘结果 |
| **Control** | Design agent | OpenClaw | 提案、装订器、门禁文档（见 [delegate.md](delegate.md)） |
| **Implementation** | Implementation agent | Claude Code ACP | `poc/` 实现/测量；Genesis / promote 代码（见 [delegate.md](delegate.md)） |

Command MUST NOT：写 worker 边界内的实现/测量；写 `poc/<topic>/ndf/` 装订器 SoT 正文；
直接 `openclaw.chat_send`；打开面板。产品提案「已审核」后只造 Control `binder_pipeline`
pack，等人「派发」；OpenClaw 不可用时走配置的 fallback，MUST NOT 手写装订器赶进度。
三角色绑定见 `ndf.workflow.yaml`；缺绑定 → `roles_unbound`。

**MUST NOT 在 Cursor 沙箱里委派**：gateway 探测、`control-pack` / `poc-dispatch` /
`dispatch-send`、角色 spawn 一律在宿主机网络（`required_permissions: ["all"]`）执行。
沙箱连不上本机 gateway 会误判 `runtime_unavailable` 并错误落到 `in-host`；
沙箱 `ECONNREFUSED` MUST NOT 当作 gateway 已挂（[[META-017]]）。见 adapter
`rules/ndf-no-sandbox-dispatch.mdc`。

## Human cognitive contract

| 人说 | Command 做 | 等人一句 | 委派谁 |
|------|----------|----------|--------|
| **初始化项目** | 角色向导 → 绑内核 → 一句「派发」（契约+基线）→ `GENESIS已审核` 骨架/基线 stable | `角色已配置` / `派发` / `GENESIS已审核` | Control + 同句测量；greenfield 另可 `genesis-pack` |
| **提交Idea** | [intake.md](intake.md) 分流 → [proposal.md](proposal.md) | 「已确认」「已审核」 | Control |
| **派发** | 写 `bundle_dispatch`（POC）+ 造 pack | 本聊天已确认「派发」 | Control 或 Implementation（按平面） |
| **继续** | 修订装订器再造 pack | 「派发」 | Control（文档）→ Implementation（实现） |
| **关闭** | `ndf_close.py plan` | 选模式 / 审核 promote | Implementation（合入）和/或 Control（收口） |
| （健康） | [health.md](health.md) 只读 | — | 不派发 |

内部模块：[genesis.md](genesis.md) / [intake.md](intake.md) / [proposal.md](proposal.md) /
[poc.md](poc.md) / [close.md](close.md) / [health.md](health.md) / [delegate.md](delegate.md)；
角色契约：[roles/control.md](roles/control.md) / [roles/implementation.md](roles/implementation.md)。
Init/adopt/govern/sync：[install.md](install.md) / [adopt.md](adopt.md) / [govern.md](adopt.md) / [sync.md](sync.md)。
**禁止**让用户选 skill / CLI 子命令。

总览（调用图 + Context/Amend/图健康闭环）：[OVERVIEW.md](OVERVIEW.md)。

## Idea 平面（[[ADR-META-004]]）

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆两个互相引用的提案 |
| ambiguous | **先问人**；MUST NOT 默认 poc |

## 硬规则

- 成功 = 磁盘 `ndf-agent-completion/v1`；transport ACK / stdout ≠ success。
  stdout notify 缺失或心跳 stall MUST NOT 单独否定合法磁盘回执（[[META-016]]）。
- 口令回执写 `GATES.md`（人、时间、内容 SHA）；文件存在 ≠ 已批准
- Genesis：绑内核 → 一句派发（`ndf-genesis-idea/v1` 骨架 `00–50` + 复现基线）→ `GENESIS已审核` 将骨架与已测基线标 stable；欠基线「继续」
- Context Compiler 只在 pack 内部跑；失败只报 `context_verify_failed` + SHA
- `roles_unbound` → 不得派发；先跑 [genesis.md](genesis.md) G-1 角色向导
- promote 合入与 TOPIC 归档分 hop（[[META-018]]）；发前 MOVE 活回执
- CLI 已 `sessions.reset` 后本次 `dispatch-send` MUST `NDF_OPENCLAW_RESET_SESSION=0`

## CLI（Command 内部）

```bash
# Role binding
python3 spec/meta/tools/ndf_role_binding.py bind|resolve|status --json

# Implementation POC
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure --send

# Control / Process
python3 spec/meta/tools/ndf_workflow_status.py control-pack … --json
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack … --json
python3 spec/meta/tools/ndf_dispatch_send.py \
  --pack-file tmp/ndf-dispatch-last-pack.json

# Genesis / Close / Health
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
python3 spec/meta/tools/ndf_genesis_idea.py check docs/cycles/cycle-<id>.md
python3 spec/meta/tools/ndf_workflow_status.py genesis-pack --mode greenfield|adopt --json
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
```

## Session startup

重读 `AGENTS.md` + 相关 `spec/meta/` + `ndf.workflow.yaml`；有则读 `MEMORY.md` /
`ndf.workspace.json` 或 `.openclaw/state.json`。相对路径在 `workspace.repo_root` 下解析。
