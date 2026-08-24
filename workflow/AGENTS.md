# AGENTS.md — NDF 指挥工作流（可移植）

> **工作流 SoT（操作层）** · 任意指挥 Agent 会话开始时 MUST 阅读。  
> 规范正文：`spec/meta/` · 产品契约：`spec/00–50` · 项目：⟨TBD: project-name⟩  
> 本地 profile：`ndf.workflow.yaml`（roots / roles / gates / completion）

## Session Startup

**CRITICAL** — 每次响应前重读：

1. 本文件 `AGENTS.md`
2. **流程 SoT**：`spec/meta/README.md`、`spec/meta/language.md`、`spec/meta/process.md`
   （[[CHR-008]]、[[BEH-018]]…[[BEH-020]]、[[BEH-025]]、[[META-006]]、[[META-007]]、
   [[META-009]]…[[META-012]]、[[META-014]]；[[META-013]]/[[META-015]] 已 deprecated）
3. 当前相关**产品**契约：`spec/00–50` 与 `spec/open/` 提案

若存在 `SOUL.md` / `MEMORY.md`，一并重读；不存在则跳过。

**Per-Project Workspace**：若存在 `.openclaw/state.json` 或 pack 内 `workspace`，MUST 读取
`workspace.repo_root` 与 `active_topic`。所有相对路径 MUST 在 `repo_root` 下解析。

| 优先级 | 绑定来源 |
|--------|----------|
| 1 | 委派 pack（`control-pack` / `genesis-pack` / `poc-dispatch`）内 `workspace.repo_root` |
| 2 | `{repo_root}/.openclaw/state.json`（仅当 cwd 已确认为目标仓） |
| 3 | 切换 `repo_root` 时 MUST 更新绑定并告知人类 |

模板：`spec/meta/templates/openclaw/state.json.example`。

**角色**：指挥 Agent 依据 NDF 判定 track、写 L0/L1；可执行实现委托 Implementation Agent。
新项目走 **bootstrap / Project Genesis**；operational 项目按 track 运作。

**Meta 自洽**：meta 条款 MUST NOT `depends-on` 产品 ID；must 正文 MUST NOT 写产品功能专名。
门禁：`python3 spec/meta/tools/ndf_graphcheck.py --meta`（hard_errors=0）。

---

## 1. Idea 平面与 track

每次需求先判定 **Idea 平面**（[[ADR-META-004]]），再判定 **track**。

提案头部 MUST 标明：

```text
> track: bootstrap | poc | promote | process | bug | refactor | rollback
```

### Idea 平面分流

| Idea 类型 | 落点 |
|-----------|------|
| 产品能力、运行中项目、bug、性能、POC、Genesis | `spec/open/` |
| NDF 语言、工作流、Agent 编排、治理工具 | `spec/meta/open/` |
| 同时影响两面（mixed） | 拆成两个互相引用的提案 |
| 无法判断（ambiguous） | **先问人**；MUST NOT 默认 poc |

人类日常入口：运行时 skill（如 `.cursor/skills/ndf-workflow/`）— 初始化 / 提交 Idea /
派发 / 继续 / 关闭。内部模块对人类不可见。

### 三工作空间（文档视角）

Design（契约）、Implementation（代码）、Test（绑定/证据）是**组织视角**，不是逐项修绿的状态机。
组装上下文 MUST：主题装订器读序 → NDF 图 `depends-on` → 当前 git/evidence；
MUST NOT 从 SLA/NOTES 叙述偷取观测数字。

**日常路径是纯文字指挥**（[[ADR-META-003]] / [[ADR-META-004]]）：**无 Commander、无 Episode、无 Replay**；
不依赖面板。成功仅以磁盘 **`ndf-agent-completion/v1`** 为准。

```text
Idea → 提案「已确认」/「已审核」
→ Control 写齐 POC 装订器（文字优先）
→ Human「派发」（绑定 bundle SHA）
→ Implementation 实现/测量（poc-dispatch）
→ Human「继续」或 close 模式
```

### 闸门（硬门）

| 闸门 | 触发 | 编排 |
|------|------|------|
| POC（文字优先） | 产品提案审核 → 整包装订器 → 「派发」 | 契约→实现/测量 |
| Genesis | 分段门禁 → `可以建立初始主线` → `GENESIS已审核` | IDEA→NDF→初始 Trunk |
| 产品/process 提案 | `已确认` → `已审核` | 契约/流程落地 |
| promote | R0 Numbers + `ndf_close plan` | 测试空间收敛 |

口令 MUST 追加到 `GATES.md`，绑定人、时间与内容 SHA（[[META-010]]）。
**文件存在不得推断审批**（gate drift 防护）。旧主题 MAY 用三闸
（`TOPIC已审核`→`DESIGN已审核`→`可以开始实现`）；新主题默认只用「派发」。

---

## 2. 三层能力（Command / Control / Implementation）

| 层 | 谁 | 入口 | 写界 |
|----|----|------|------|
| **Command** | 指挥面（Cursor 等 + ndf-workflow skill） | 五句口令；造 pack；等人审；调 CLI | `tmp/`、触发回执；禁写 worker 实现 |
| **Control** | 指挥 Agent（OpenClaw 等） | `control-pack` → dispatch | `spec/open/`、`spec/meta/open/`、`poc/<topic>/ndf/`、`.openclaw/state.json` |
| **Implementation** | 实现 Agent（Claude Code 等） | `poc-dispatch --send`；`genesis-pack`；promote close plan | POC 仅 `poc/<topic>/`；promote 可写 Trunk |

成功 = 磁盘 completion receipt；**不以 transport ACK / stdout 冒充**。

### 委派 pack 类型

| Pack | 用途 |
|------|------|
| `control-pack` / `project-control-pack` | Control 写提案/装订器/门禁 |
| `poc-dispatch` | Implementation 在 `poc/<topic>/` 实现或测量 |
| `genesis-pack` | bootstrap 隔离 worktree 建初始 Trunk 切片 |

所有 pack MUST 含 `workspace.repo_root`。Implementation handshake MUST 含
`allowed_write_root`、`base_sha`、独立 worktree/branch。缺任一项 = `unsafe`，不得派发。

**硬安全门**：错仓库、越界写根、缺人审 bundle、并发写 run、上下文漂移、伪造 completion、
上下文超预算（`NDF_ACP_CONTEXT_MAX_TOKENS`）→ fail-closed。

Command MUST NOT 直接调用外部 chat 发送 API 绕过 pack 纪律。

---

## 3. 工作流程（按 track）

### 步骤1：接收需求

**输出**：
> 收到需求。plane=<product|process|mixed|ask>。track=<…>。开始生成提案。

### 步骤2：生成提案

| track | 提案落点 |
|-------|----------|
| **bootstrap** | `spec/open/proposal-project-genesis.md` |
| **process** | `spec/meta/open/proposal-meta-*.md` |
| **poc / promote / bug / refactor / rollback** | `spec/open/proposal-*.md` |

- L1：`{#BEH-XXX}` 等 + `<!-- ndf: … -->`（process 加 `scope=ndf-process`）
- 新建 process ID：`{#META-nnn}` 或 `ADR-META-*`；MUST NOT 续产品 BEH/CHR 数字号
- **poc**：`status=draft`；MUST NOT 立刻写 stable must SLA
- **promote**：证据 + draft→stable 列表 + **语义核决策**（要/不要/延期）[[META-004]]
- **process**：改 `spec/meta/**` + 产品 thin 指针；禁止元条款长文写回 `20-behavior/`

### 步骤3–5：确认 → 落地 → 审核

> 提案已生成：…。请审阅，确认后回复「已确认」。  
> （落地后）请审核，回复「已审核」。

落地前 MUST 校验 `refines`/`deprecates`/`depends-on` 引用存在。

### 步骤6+：按 track 继续

| track | 已审核之后 |
|-------|------------|
| **bootstrap** | Genesis 分段门禁 → `genesis-pack` → 构建验收 → `GENESIS已审核` |
| **poc** | 文字优先装订器 → Human「派发」→ `poc-dispatch`；多轮继续/关闭；**不**跑 Trunk SLA |
| **promote** | `ndf_close plan` → 干净合入 Trunk → 编译 → 性能/金标 |
| **process** | 仅 meta + thin + AGENTS；跳过实现委派 |
| **bug / refactor / rollback** | 通常同 promote |

---

## 4. 写入边界

### Control Agent

| 可以写 | 绝不写 |
|--------|--------|
| `spec/meta/**`（含 open/decisions） | Trunk `src/`（探索期） |
| 产品 L0/L1（`00–40` 协议级） | `include/`、`tests/`（poc 期） |
| 产品 `open/`、`decisions/` | 把 POC 补丁写入 `spec/models/` |
| `poc/<topic>/ndf/` 装订器 | 探索默认开启合入 Trunk |
| `AGENTS.md`、`.openclaw/state.json` | |

### Implementation Agent

- **禁止**改 `spec/meta/`、L0/L1（除非 promote/process 已落地）
- **bootstrap**：隔离 branch 可写初始 `src/`/`include/`/`tests/`；MUST NOT 改 L0/L1/meta
- **poc**：只写 `poc/<topic>/`；改 Trunk 头/源 MUST 先拷进 poc（[[BEH-018]] §6）
- **promote / bug / refactor**：可写 Trunk、测试、`50-verification/`、L2/L3
- SHOULD：`ndf_poc_isolation.py check`；`ndf_perf_baseline.py check`

`spec/models/`：仅 L3 参考；禁止生产路径实验补丁（[[ARCH-008]]）。

---

## 5. 场景路由

| 关键词 | track |
|--------|-------|
| 初始化项目 / Genesis / 接管已有代码 | **bootstrap** |
| 探索 / POC / 试验 | **poc** |
| 晋升 / promote / 合入主线 | **promote** |
| 流程 / AGENTS / 规范卫生 / 双轨 | **process** |
| 修复 / Bug | **bug** |
| 重构（Trunk） | **refactor** |
| 回滚 | **rollback** |
| 负结果 / 证伪 | §6.2d |

产品 track 不确定时：**默认先 poc**。Idea ambiguous MUST 先问人。

**探索延长**（[[BEH-025]]）：同假设同 topic（amend/partial）；分叉开**平级**新 topic +
`depends_on_topics`；禁止嵌套子 POC。

**关闭后重启**：`rejected`/`promoted` MUST NOT 同 `topic_id` 重开；须平级新 topic + 新 R0。

---

## 6. 变更流程（摘要）

### 6.2a poc（文字优先）

- 产品提案审核后一次写齐 TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE
- 收到「派发」：写 `GATES.md` `bundle_dispatch`（绑定 bundle SHA）→ `poc-dispatch --send`
- 开题填 `explore_surface`；禁写 Trunk；MUST NOT stable SLA
- R0 后：`baseline_trunk_sha` + `PERF_BASELINE.md` Numbers（[[META-007]]）
- 比性能 MUST 只读 TOPIC→PERF_BASELINE 与 DELTA；MUST NOT 抄 SLA 观测表
- commit trailers + `ndf/COMMITS.md`
- POC 中发现 Trunk bug：默认在 poc 修测；合入另开 bug/promote

### 6.2b promote

- MUST：`python3 spec/meta/tools/ndf_close.py plan --topic <t> --mode promote|partial|reject`
- 干净合入；`Promotes: <topic>`；语义核决策
- 编译 + 性能对照 stable SLA + 金标（[[META-006]]）
- §4c 基线 stale / §4d 表面冲突清单 MUST 执行

### 6.2c process

- 只改 meta / thin / AGENTS / harness profile

### 6.2e bootstrap

- `bootstrap_mode=greenfield|adopt`
- 串行门禁：IDEA → CHARTER → ARCHITECTURE → VERIFICATION → 可以建立初始主线 → GENESIS已审核
- Implementation 在隔离 worktree 建最小可构建垂直切片；不改 L0/L1

### 6.2d 负结果

[[BEH-020]]：产品 DEC（`Rejects:`）→ deprecated → 确认 Trunk 无 POC 表面 → 装订器归档。

### 场景5 / 6 / 7

- **编译**：Trunk 代码路径后；poc/process 默认不触发
- **性能**：对照 stable SLA + 金标；POC 数字不进 Trunk SLA（[[CON-POC-001]]）
- **失败闭环**：≤3 轮；冲突 → `spec/open/feedback-*` 或 `spec/meta/open/feedback-*`

---

## 7. 状态与记忆

`.openclaw/state.json` 建议字段：`current_proposal`、`track`、`workspace.repo_root`、
`active_topic`、`validation_round`、`validation_status`、`perf_status`。
工作流 CLI MUST NOT 静默改写指挥状态。

| 类型 | 落点 |
|------|------|
| 产品 DEC / SLA | `spec/decisions/` |
| 流程 / 卫生 ADR | `spec/meta/decisions/` |

---

## 8. 归档纪律

- `spec/archive/` 与 `poc/` 均为 **sot: false**
- 已关闭产品提案 → `spec/archive/YYYY-MM/`
- **禁止** `spec/open/archive/`

---

## 常设指令

### 核心原则

1. **先提案，后行动**（Trunk 或 stable 契约变更前）
2. **确认后落地**；「已审核」后再委派 Implementation
3. **双轨**：探索在 `poc/` + draft；晋升才 stable + Trunk（[[CHR-008]]）
4. **先收口，再 POC**；open/ 不堆 Implemented
5. **验证闭环**：仅 Trunk 代码路径必须编译/性能验证
6. **磁盘 completion** 为唯一成功信号；无 Replay 义务

### 禁止行为

- 提案前改 Trunk 实现
- 探索期直接改 Trunk `src/`/`include/`/`tests/`
- 探索期写 stable must SLA 或 POC 默认开启合入 Trunk
- 实验补丁写入 `spec/models/`
- 元规范长文写回产品 `20-behavior/`
- 用 Harness 包反推纠正本地已验证 `spec/meta/` SoT
- poc/process 跳过验证却宣告「主线完成」
- promote 跳过 `ndf_close plan`/语义核/验证直接收口
- 主题未关闭却宣称 NDF/实现「回合完成」
- 已关闭 topic 原地复活（须平级新 topic）
- 从门禁文件存在推断已审批（gate drift）
- Commander / Episode / Replay 面板当作成功依据
