# AGENTS.md — NDF 指挥工作流（跨运行时）

> 本文件是仓库级 **工作流 SoT（操作层）**。任意指挥 Agent（OpenClaw / OpenCode / Cursor /
> 其他）在会话开始时 MUST 阅读。规范正文在 `spec/meta/`；产品契约在 `spec/00–50`。  
> ⟨TBD: project-name⟩ · 实现主线目录默认 `src/`（可改）

## Session Startup

**CRITICAL**: Before each response, re-read:

1. 本文件 `AGENTS.md`
2. **流程 SoT**：`spec/meta/README.md` + `spec/meta/language.md`（[[META-001]]…[[META-005]]）
   + `spec/meta/process.md`（[[CHR-008]]、[[BEH-018]]…[[BEH-020]]、[[BEH-025]]、
   [[META-006]]、[[META-007]]）
3. 当前相关的**产品**契约：`spec/00–50`（及产品 `spec/open/` 提案）

**角色（逻辑标签，可映射到具体运行时）**：

| 角色 | 职责 |
|------|------|
| **指挥 Agent** | 依据 NDF 判定 track、写 L0/L1 提案与落地；不写 Trunk 实现 |
| **实现 Agent** | 按 track 改 `poc/` 或 Trunk 实现 / 测试 |
| **审核面** | 跑治理 CLI、脚手架、规范卫生（可与指挥同一人或同一会话） |

权威流程条款正文在 **`spec/meta/`**：[[CHR-008]]、[[ARCH-008]]、[[BEH-018]]、[[BEH-019]]、
[[BEH-020]]、[[BEH-025]]、[[CON-POC-001]]、[[META-006]]、[[META-007]]。分层见 [[ADR-META-001]]。  
本文件不得与上述条款矛盾。

---

## 1. 工作流程（按 track）

提案头部 MUST 标明：

```text
> track: poc | promote | process | bug | refactor | rollback
```

### 步骤1：接收需求

**输出**：
> 收到需求。track=<…>。开始生成提案。

### 步骤2：生成提案

| track | 提案落点 |
| :--- | :--- |
| **process** | `spec/meta/open/proposal-meta-*.md` |
| **poc / promote / bug / refactor / rollback** | `spec/open/proposal-*.md` |

内容规范：

- L1：`{#BEH-XXX}` 等 + `<!-- ndf: … -->`（元条款加 `scope=ndf-process`）
- 关联：`refines=` / `deprecates=` / `depends-on=`
- **poc**：默认 `status=draft`；MUST NOT 立刻写 stable must SLA
- **promote**：证据摘要 + draft→stable ID 列表
- **process**：改 `spec/meta/**` + 产品 thin 指针；禁止把元条款长文写回 `20-behavior/`

### 步骤3：人工确认

> 提案已生成：…。请审阅，确认后回复「已确认」。

### 步骤4：落地（确认后由指挥执行）

1. 校验引用的条款 ID 存在（或本提案同时新增）
2. 不通过 → 不落地
3. 通过 → 按 track 写入；提案顶部 `Status: Implemented on YYYY-MM-DD`

### 步骤5：人工审核

> 提案已落地。变更摘要：…。请审核，回复「已审核」。

### 步骤6+：按 track 继续

| track | 已审核之后 |
| :--- | :--- |
| **poc** | 委派实现 Agent 改 **`poc/<topic>/` only**（禁写 Trunk `src/`/`include/`/`tests/`）；
  R0 后写 `PERF_BASELINE.md`；不跑 Trunk SLA 验收 |
| **promote** | `ndf_close plan` → 干净合入 Trunk → 功能验证 →（适用时）性能/金标更新 [[META-006]] |
| **process** | 仅 meta + thin 指针 + 本文件等；跳过实现委派与性能 |
| **bug / refactor / rollback** | 通常同 promote；若仅文档则同 process |

---

## 2. 写入边界（指挥 Agent）

| 可以写 | 绝不写 |
| :--- | :--- |
| `spec/meta/**` | Trunk 实现主线（探索期） |
| 产品 L0/L1（`00–40` 协议级） | 产品 L2/L3、字段级实现细节（除非 track 允许且已确认） |
| 产品 `open/`、`decisions/` | 把 POC 补丁写入 `spec/models/` |
| `poc/<topic>/ndf/` 装订器（实现优先委派） | 将探索默认开启合入 Trunk |
| 本 `AGENTS.md` | |

`spec/models/`：仅 L3 参考模型；禁止生产路径实验补丁（[[ARCH-008]]）。

---

## 3. 记忆（ADR）

| 类型 | 落点 |
| :--- | :--- |
| 产品域 DEC / SLA | `spec/decisions/` |
| 卫生 / 双轨 / 装订 / 元分层 | `spec/meta/decisions/` |

---

## 4. 实现 Agent 边界（摘要）

- **禁止**改 `spec/meta/`、L0/L1 条款（除非 process 且指挥已落地）
- **poc**：只写 `poc/<topic>/`；MUST NOT 改 Trunk `src/**` `include/**` `tests/**`（先拷再改）；
  比性能 MUST 读 TOPIC → `perf_baseline`（[[META-007]]）
- **promote / bug / refactor**：可写实现主线、测试、`50-verification/`、L2/L3
- **任何 track**：MUST NOT 把实验补丁塞进 `spec/models/` 冒充 L3
- SHOULD：`ndf_poc_isolation.py check`；`ndf_perf_baseline.py check`（装订门禁）

细节可映射到运行时文件（如 `CLAUDE.md`）；语义以本表 + meta 条款为准。

---

## 5. 场景路由

| 关键词 | track | 后续 |
| :--- | :--- | :--- |
| 探索 / POC / 试验 | **poc** | `poc/`；不跑 Trunk SLA |
| 晋升 / 合入主线 | **promote** | 验证 |
| 流程 / AGENTS / 规范卫生 / 双轨 | **process** | 写 meta |
| 修复 / Bug | **bug** | 验证 |
| 重构（Trunk） | **refactor** | 验证 |
| 回滚 | **rollback** | 验证 |
| 负结果 / 证伪 | §6.2d | DEC + 弃条款 |

不确定时：**默认先 poc**。

---

## 6. 变更类流程（摘要）

共同：接收 → 提案 →「已确认」→ 落地 →「已审核」。

### 6.2a poc

- draft / 装订器 / MUST NOT stable SLA
- 先有 `poc/<topic>/ndf/TOPIC.md` 再实现；开题填 `explore_surface`
- 禁写 Trunk `src/**` `include/**` `tests/**`（[[BEH-018]]）；先拷再改
- R0 后：`baseline_trunk_sha` + `perf_baseline` → `PERF_BASELINE.md`（[[META-007]]）
- 已 `rejected`/`promoted`：禁止同 topic 重开；平级新 topic + `depends_on_topics`（[[BEH-025]]）
- commit trailers + `COMMITS.md`
- 正结果 → promote 提案；负结果 → §6.2d

### 6.2b promote

- draft→stable；干净合入；`Promotes: <topic>`
- MUST：`ndf_close.py plan`（含语义核 / 基线 stale / 表面冲突）
- 功能验证 +（适用）性能验证对照 stable SLA
- 金标更新：产品验证树 configs/baselines + 索引（[[META-006]]）；禁止只刷 SLA 观测数字

### 6.2c process

- 只改 meta / thin / AGENTS / harness；`validation`/`perf` = n/a

### 6.2d 负结果

对齐 [[BEH-020]]：产品 DEC（`Rejects:`）→ deprecated → 确认 Trunk 无 POC 表面 → 装订器归档；
关闭后重启见 [[BEH-025]] 平级新 topic。

### 场景5 / 6 / 7

- **编译/功能验证**：Trunk 代码路径后触发；poc/process 默认不触发  
- **性能验证**：对照 `status=stable` SLA + 产品金标矩阵（[[META-006]]）；
  POC 数字不进 Trunk SLA（[[CON-POC-001]]）；Agent 读线见 [[META-007]]  
- **失败闭环**：≤3 轮；产品冲突 → `spec/open/feedback-*`；流程冲突 → `spec/meta/open/feedback-*`

---

## 7. 归档纪律

- `spec/archive/` 与 `poc/` 均为 **sot: false**
- 已关闭产品提案 → `spec/archive/YYYY-MM/`
- **禁止** `spec/open/archive/`

---

## 常设指令

### 核心原则

1. **先提案，后行动**（Trunk 实现或 stable 契约变更前）  
2. **确认后落地**；「已审核」后再委派实现  
3. **双轨**：探索在 `poc/` + draft；晋升才 stable + Trunk（[[CHR-008]]）  
4. **验证闭环**：仅 Trunk 代码路径必须验证；poc/process 不得假装主线验收完成  

### 禁止行为

* 提案前改 Trunk 实现  
* 探索期直接改 Trunk `src/`/`include/`/`tests/`  
* 探索期写 stable must SLA，或 POC 默认开启合入 Trunk  
* 实验补丁写入 `spec/models/`  
* 元规范长文写回产品 `20-behavior/`  
* 配置-only 调参刷 SLA 观测数字冒充新基线（[[META-007]]）  
* poc/process 跳过验证却宣告「主线完成」；promote 跳过 `ndf_close plan`/验证直接完成  
* 主题未关闭却宣称 NDF/实现「回合完成」  
* 已关闭 topic 原地复活（须平级新 topic）
