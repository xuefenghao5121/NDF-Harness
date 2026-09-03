---
name: ndf-workflow
description: >-
  Unique human-facing NDF workflow entry (ADR-META-004 / META-023): Command
  surface for 初始化项目 / 提交Idea / 派发 / 继续 / 关闭 plus graph/pack observation.
  Resolves Control/Implementation via ndf.workflow.yaml. Never asks the user to
  pick a skill or button; five phrases are shortcuts, not the only verbs.
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
| **Command** | Command Agent（当前宿主） | 当前宿主 + 本 skill | 口令快捷 + 图/pack 观察；分流 Idea、等人审、造 pack、调 CLI、报告 blockers / 写根 / 磁盘结果 |
| **Control** | Design agent | OpenClaw | 提案、装订器、门禁文档（见 [delegate.md](delegate.md)） |
| **Implementation** | Implementation agent | Claude Code ACP | `poc/` 实现/测量；Genesis / promote 代码（见 [delegate.md](delegate.md)） |

Command MUST NOT：写 worker 边界内的实现/测量；写 `poc/<topic>/ndf/` 装订器 SoT 正文；
直接 `openclaw.chat_send`；打开面板。产品提案「已确认」后只造 Control `binder_pipeline`
pack，等人「派发」；OpenClaw 不可用时走配置的 fallback，MUST NOT 手写装订器赶进度。
三角色绑定见 `ndf.workflow.yaml`；缺绑定 → `roles_unbound`。

**MUST NOT 在 Cursor 沙箱里委派**：gateway 探测、`control-pack` / `poc-dispatch` /
`dispatch-send`、角色 spawn 一律在宿主机网络（`required_permissions: ["all"]`）执行。
沙箱连不上本机 gateway 会误判 `runtime_unavailable` 并错误落到 `in-host`；
沙箱 `ECONNREFUSED` MUST NOT 当作 gateway 已挂（[[META-017]]）。见 adapter
`rules/ndf-no-sandbox-dispatch.mdc`。

## Human cognitive contract

**人读定义（SoT）**：`spec/meta/language.md`、图边、双轨；本 skill 的口令表是
**Agent 操作手册**，不得冒充 SoT（[[META-023]]）。

| 人说 | Command 做 | 等人一句 | 委派谁 |
|------|----------|----------|--------|
| **初始化项目** | 角色向导 → 绑内核 → 一句「派发」（契约+基线）→ `GENESIS已审核` 骨架/基线 stable | `角色已配置` / `派发` / `GENESIS已审核` | Control + 同句测量；greenfield 另可 `genesis-pack` |
| **提交Idea** | [intake.md](intake.md) 分流 → [proposal.md](proposal.md)；短表展示相关闭包 | 「已确认」（审提案 markdown） | Control |
| **已审核**（poc） | 人审 `poc/<topic>/ndf/*.md` 后写 `bundle_dispatch` + pack-view | 「派发」 | Command 造 pack；不 send |
| **派发** | 人已读 pack-view 散文后：开租约 worktree + send | 本聊天已确认「派发」 | Implementation（poc）/ Control（非 poc） |
| **继续** | 修订装订器再造 pack（可先 overlay） | 「派发」 | Control（文档）→ Implementation（实现） |
| **关闭** | `ndf_close.py plan`；展示 promote 分层散文 | 选模式 / 审核 promote | Implementation（合入）和/或 Control（收口） |
| （健康） | [health.md](health.md) 只读 | — | 不派发 |
| （看闭包 / 改依赖） | `ndf_context.py pack-view` / `overlay-apply`（人审主文=散文） | 可选「派发」 | 不强制委派 |

五句口令是 SHOULD 快捷入口，MUST NOT 限制人为只能说那五句。人可直接改树内
`depends-on`，或要求「看 packed 散文」「排除某 ID 再编」。
**禁止**强迫人选 skill / CLI 子命令；模块文件名仍不必暴露给人。
**禁止**把节点/边表当给人审的主文（附录除外；[[META-024]]）。
条款溯源 MUST 写在主文标题下，MUST NOT 只堆附录。

内部模块：[genesis.md](genesis.md) / [intake.md](intake.md) / [proposal.md](proposal.md) /
[poc.md](poc.md) / [close.md](close.md) / [health.md](health.md) / [delegate.md](delegate.md)；
角色契约：[roles/control.md](roles/control.md) / [roles/implementation.md](roles/implementation.md)。
Init/adopt/govern/sync：[install.md](install.md) / [adopt.md](adopt.md) / [govern.md](adopt.md) / [sync.md](sync.md)。

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
  `bundle_dispatch` 可替闸 3；租约不以 Episode 为成功条件（[[META-019]]）。
- 口令回执写 `GATES.md`（人、时间、内容 SHA）；文件存在 ≠ 已批准
- poc-dispatch 未 `--send` MUST NOT 建租约；`--send` 无 v2 pack-view MUST fail-closed（`human_pack_view_missing`，[[META-025]]）
- Genesis：绑内核 → 一句派发（`ndf-genesis-idea/v1` 骨架 `00–50` + 复现基线）→ `GENESIS已审核` 将骨架与已测基线标 stable；欠基线「继续」
- Context Compiler 编 pack 时 MUST 落人读**分层散文**（[[META-024]]）；每条
  条款标题下有 `> 源：path:line · status · 因…`（装订器为路径 + slice id）。
  失败报 `context_verify_failed` + SHA；人可用 overlay 再编。口头汇报 MUST
  指向主文，MUST NOT 只念节点表
- `roles_unbound` → 不得派发；先跑 [genesis.md](genesis.md) G-1 角色向导
- promote 合入与 TOPIC 归档分 hop（[[META-018]]）；发前 MOVE 活回执
- CLI 已 `sessions.reset` 后本次 `dispatch-send` MUST `NDF_OPENCLAW_RESET_SESSION=0`

## CLI（Command 内部）

```bash
# Role binding
python3 spec/meta/tools/ndf_role_binding.py bind|resolve|status --json

# Human pack view / overlay（META-024 分层散文）
python3 spec/meta/tools/ndf_context.py pack-view \
  --topic <t> --task <task> --track <track> --role claude-code \
  --report tmp/ndf-pack-view-<t>.md
python3 spec/meta/tools/ndf_context.py overlay-apply \
  --overlay tmp/ndf-overlay.json \
  --topic <t> --task <task> --track <track> --role claude-code \
  --report tmp/ndf-pack-view-<t>.md

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
