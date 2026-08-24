# NDF Workflow 总览（调用图 + 闭环）

> **入口**：Command Agent + `skill/ndf-workflow/`（Cursor 见 [`../adapters/cursor/`](../adapters/cursor/)）  
> **权威**：installed `AGENTS.md` + `spec/meta/`  
> **日期**：2026-08-24  
> **非 SoT**：本文是人类可读总览；条款正文以 `spec/meta/process.md` 为准。

---

## 0. 一句话

人只跟**指挥面**说话 → 内部模块分流 → **OpenClaw**（文档）/ **Claude Code**（代码）→ 磁盘 `ndf-agent-completion/v1`。  
改契约靠 **SHA + slice diff** 识别；图/RAG 出问题走 **graphcheck → 提案改 SoT → 再检**。

| 层 | 谁 | 做什么 |
|----|-----|--------|
| 指挥面 | Command Agent + `ndf-workflow` | 五句口令、等人审、造 pack、报 blockers |
| OpenClaw | Control | `spec/open/`、`spec/meta/open/`、`poc/<topic>/ndf/` |
| Claude Code | Implementation | `poc-dispatch` / `genesis-pack` / close 合入 |

成功 = 磁盘 completion；transport ACK ≠ success。无面板义务。

---

## 1. Skill / 模块调用图

内部 `*.md` 是**模块**，不是让用户再选的第二套 skill。

```mermaid
flowchart TB
  Human[Human 五句口令] --> Skill["/ndf-workflow 指挥面"]

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
  Genesis --> Delegate
  Proposal --> Delegate
  Poc --> Delegate
  CloseM --> Delegate
  CloseM --> CloseCLI[ndf_close plan]
  HealthM --> HealthCLI[topic-health]

  Delegate --> CtrlCLI[control-pack / project-control-pack]
  Delegate --> PocCLI[poc-dispatch --send]
  Delegate --> GenCLI[genesis-pack]

  CtrlCLI --> OpenClaw[OpenClaw Control]
  PocCLI --> Claude[Claude Code]
  GenCLI --> Claude
  CloseCLI --> Claude
  CloseCLI --> OpenClaw

  OpenClaw --> Disk[磁盘 ndf-agent-completion/v1]
  Claude --> Disk
```

### 口令 → 工作流

| 人说 | 内部模块 | 等人一句 | 委派谁 |
|------|----------|----------|--------|
| 初始化项目 | genesis → delegate | Genesis 分段口令 | OpenClaw L0/L1 → Claude `genesis-pack` |
| 提交Idea | intake → proposal → delegate | 「已确认」「已审核」 | OpenClaw |
| 派发 | poc + delegate | 「派发」+ `GATES` bundle | POC→Claude；Control→OpenClaw |
| 继续 | poc + delegate | 再「派发」 | OpenClaw 改装订器 → Claude |
| 关闭 | close → delegate | 选 promote/partial/reject | Claude 合入 ± OpenClaw 收口 |
| 健康 | health | — | 只读；不派发 |

### Idea 平面（intake）

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆两个互相引用的提案 |
| ambiguous | **先问人**；MUST NOT 默认 poc |

### 内部模块文件

| 文件 | 职责 |
|------|------|
| `SKILL.md` | 唯一入口：口令路由、三层合同、硬规则 |
| `intake.md` | Idea 平面分流 |
| `proposal.md` | 写提案；等人确认/审核 |
| `genesis.md` | bootstrap G0–G3 |
| `poc.md` | 装订 → 派发/继续；SHA 漂移先看 diff |
| `close.md` | `ndf_close plan` |
| `health.md` | topic-health / graphcheck；不派发 |
| `delegate.md` | 唯一委派合同 |

旁路指针：`skills/ndf-workflow/SKILL.md` → 本目录。退役：`ndf-harness` 墓碑（勿作入口）。

---

## 2. 闭环 A — Context：人如何检查

人**不**打开可视化 Compiler。Context 在造 pack 时内嵌校验；人只看 blockers / SHA。

```mermaid
flowchart LR
  Ask[人：健康/能派发吗] --> TH[topic-health]
  TH --> Pack[造 pack]
  Pack --> CV[context-verify]
  CV -->|pass| OK[safe_to_dispatch]
  CV -->|fail| Bl[blockers + SHA]
  Bl --> Fix[人修装订器或重审派发]
  Fix --> Pack
```

| 对人可见 | 对人不可见 / 不要求 |
|----------|---------------------|
| `safe_to_dispatch` / blockers | 可视化 Compiler 面板、整份 context dump |
| `context_verify_failed` + manifest/plan SHA | 两边 agent 各自拼不同上下文 |
| topic-health findings（含闸漂移摘要） | Episode / Replay / Canvas 投影 |

OpenClaw 与 Claude 的 role plan MUST 引用同一 `manifest_sha`。

---

## 3. 闭环 B — 人修改后如何识别

身份钉 = review-slice **bundle SHA**；人审 UI = **slice unified diff**（META-010）。

```mermaid
flowchart TD
  Edit[改 TOPIC/DESIGN/INTERFACE 等切片] --> SHA[重算 bundle SHA]
  SHA --> Cmp{vs GATES approved}
  Cmp -->|相同| Go[可派发]
  Cmp -->|不同| Drift[invalidated]
  Drift --> Diff[gate_drift slice diff]
  Diff --> Phrase[人看 diff →「派发」+ 新 snapshot]
  Phrase --> SHA

  Mut[只追加 Numbers/Rounds/evidence] --> NoChurn[SHA 不变 · 不强制重审]
```

| 改动 | 是否重审 |
|------|----------|
| TOPIC / DESIGN / PERF bind / DELTA 假设 / INTERFACE 契约切片 | **要** → 看 diff →「派发」 |
| Numbers / Rounds / evidence / COMMITS / GATES 追加 / TOPIC 导航头 | **不要**（不进 SHA） |

指挥面遇拦 MUST 展示 `gate_drift_markdown` 或 `tmp/ndf-gate-drift-<topic>.md`，禁止只甩两个 hex。  
写「派发」回执时 MUST `persist_gate_slice_snapshot`，否则下次只能 `diff_unavailable`。

---

## 4. 闭环 C — 健康检查与 NDF 图（RAG）修复

```mermaid
flowchart TD
  Sym[症状：图/引用/装订不对] --> Health[健康 /ndf-workflow]
  Health --> GC[ndf_graphcheck --meta 或 --product]
  Health --> IDX[ndf_index validate / index]
  Health --> BC[ndf_bindcheck --topic]
  GC --> R[tmp/*-check.md findings]
  IDX --> R
  BC --> R
  R --> Adv[可选 advise]
  Adv --> Idea[提交Idea]
  R --> Idea
  Idea --> Land[已确认落地 SoT]
  Land --> Recheck[再 graphcheck / index]
  Recheck --> GC
```

| 工具 | 查什么 | 人怎么修（经 `/ndf-workflow`） |
|------|--------|--------------------------------|
| `ndf_graphcheck.py --meta` / `--product` | 环、stable→draft、conflicts、悬空 depends-on | 提交Idea → 落地条款 → 再检 |
| `ndf_index.py validate` / `index` | 可索引性、断链、重建索引 | 修引用后 `index` |
| `ndf_bindcheck.py check --topic` | 装订器双头、ledger/trailer、粒度 | 改 `poc/<topic>/ndf` 或提案 |
| `topic-health` / `spec-health` | 闸、隔离、findings 汇总 | 按 `repair_owner` 分流 |
| `advise`（graph/bind） | 局部选项；**不写 SoT** | 人选方案后再提案落地 |

报告默认写仓库 `tmp/`（已 gitignore）；MUST NOT 写入 `spec/open/`。

### 硬门 vs 软审计（日常 POC）

`poc-dispatch` **硬拦**：身份、人审 bundle SHA、写根/隔离、并发、context verify、ACP 预算、磁盘 completion。  

下列默认 **soft**（不单独挡日常派发）：全量 meta graph、全量 bindcheck、projection/Replay 仪式。  
健康诊断与 close/promote 时再强制图/绑定检查。

---

## 5. 端到端总环

```text
Idea → 提案「已确认」「已审核」
  → 装订器 poc/<topic>/ndf/
  → 人「派发」(bundle SHA + slice snapshot)
  → pack(context-verify, 同 manifest_sha)
  → worker → 磁盘 ndf-agent-completion/v1
  →「继续」: 改切片? → gate_drift diff → 再派发
             只加测数? → SHA 不重审
  →「健康」: topic-health → graphcheck / bindcheck / index
             → advise? → 提交Idea 修 SoT → 再检
  →「关闭」: ndf_close plan → 合入或 reject
             → index + graphcheck（及适用时编译/性能/金标）
```

---

## 6. 常用命令（指挥面内部；勿让用户背）

```bash
# Claude Code POC
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure --send

# OpenClaw Control
python3 spec/meta/tools/ndf_workflow_status.py control-pack … --json
python3 spec/meta/tools/ndf_dispatch_send.py \
  --pack-file tmp/ndf-dispatch-last-pack.json

# 健康 / 图
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
python3 spec/meta/tools/ndf_graphcheck.py --meta
python3 spec/meta/tools/ndf_graphcheck.py --product
python3 spec/meta/tools/ndf_index.py validate
python3 spec/meta/tools/ndf_bindcheck.py check --topic <topic>

# 关闭
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject
```

---

## 7. 相关文件

| 路径 | 说明 |
|------|------|
| `.cursor/skills/ndf-workflow/SKILL.md` | 人类唯一入口 |
| `spec/meta/process.md` | META-010/011/012 等条款 |
| `spec/meta/tools/README.md` | graphcheck / bindcheck / advise |
| `spec/meta/open/proposal-meta-gate-drift-diff.md` | 闸漂移须附 slice diff（已审核） |
| Canvas 总览 | `canvases/ndf-workflow-overview.canvas.tsx` |
| Canvas 分图（历史） | `ndf-workflow-call-graph` · `ndf-workflow-closed-loops` |
