# Meta Process — 探索轨 / 晋升 / 负结果 / 装订

> scope: ndf-process  
> 条款索引: `CHR-008`, `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`, `BEH-026`,
> `META-006`, `META-007`, `META-009`, `META-010`, `META-011`, `META-012`, `META-013`, `META-014`, `META-015`
> 目录边界: [[ARCH-008]]；SLA 隔离: [[CON-POC-001]]  
> 术语: [[DEF-020]], [[DEF-021]], [[DEF-022]], [[DEF-023]], [[DEF-NDF-GRAPH]]  
> 缺陷分类: [[DEF-NDF-CYCLE]]…[[DEF-NDF-BINDER-DUAL-HEAD]]（见 `meta/glossary.md`）

## 探索与晋升双轨 {#CHR-008}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.7 source=deduced scope=ndf-process -->

本仓库产品规范与代码演进 MUST 区分：

1. **探索轨（POC）**：验证某优化/机制是否成立；允许失败与回退（[[DEF-020]]）。
2. **主线轨（Trunk）**：已证明有效、纳入产品行为与 SLA 的实现（[[DEF-021]]）。

探索轨产物 MUST NOT 被默认当作 Trunk SoT；负结果 MUST 以决策记录关闭，不得靠
「静默删条款却留主线代码」或「删代码却留 stable must」维持表面一致。

反面教材：探索方向过早合入 Trunk 后证伪（详见产品负结果 DEC）。
流程细则见 [[BEH-018]]…[[BEH-020]]；目录边界见 [[ARCH-008]]。

## 探索期 NDF 纪律 {#BEH-018}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=ARCH-008,DEF-020 -->

当某方向仍在探索轨时：

1. 契约草稿 MUST 留在 `spec/open/proposal-*.md` 或主题装订器 `poc/<topic>/ndf/proposals/`，
   或固定目录中显式 `status=draft` / `level=tbd`；凡本主题提案 MUST 登记进
   `poc/<topic>/ndf/TOPIC.md`（[[BEH-025]]）。**流程/卫生**提案 MUST 写在
   `spec/meta/open/proposal-meta-*.md`（见 `AGENTS.md` track=process）。
   Draft 状态的存在与演进 MUST 由 `spec/meta/open/draft-map/` 并发映射承载；
   固定模块正文的 `status` 字段 MUST NOT 单独充当 Draft 事实源。
2. MUST NOT 将探索期指标写入 `status=stable` 的 `{#CON-SLA-*}` must 行
3. MUST NOT 将探索期行为标为生产默认（环境变量默认开启、去掉 opt-in 门控等）
4. 正文与提案 MUST 使用明确标记：`POC` / `status=draft` / `explore=`，并 `depends-on`
   对应开放提案或 DEC 方向
5. 多轮深入（v1→v2→…）MUST 在**同一探索主题**下追加证据，优先改 `poc/<topic>/`、
   装订器与提案，而不是反复改写 Trunk 的 stable 条款
6. **可执行试错 MUST 落在 `poc/<topic>/`**（或专用 POC 分支）。探索期 / poc track：
   **MUST NOT 修改** Trunk 树中的 `src/**`、`include/**`、`tests/**`（含头文件与
   「生产默认路径」）。若 POC 需改接口或实现：MUST 将相关 `.h`/`.cpp`（及必要依赖）
   **复制到** `poc/<topic>/` 后再改；对本 topic 修改面，构建 MUST 优先使用 topic 内
   路径（如 `-I.`），MUST NOT 向 Trunk `include/` / `src/` 写回。**MAY** 只读编译链接
   **未修改**的 Trunk 源/头（例如未改动的 `../../src/core/*.cpp`、`-I../../include`
   中未改动的头）作 R0/对照。若已误改 Trunk：MUST 按 [[BEH-020]] 或显式 revert /
   迁出到 `poc/`，并做矫正检查（见 `AGENTS.md` §6.2a）。开题/委派前后 SHOULD 跑
   `python3 spec/meta/tools/ndf_poc_isolation.py check --topic <topic>`。
7. MUST NOT 在未登记 `TOPIC.md` 的情况下改写 Trunk `status=stable` 条款「顺便服务某 POC」
8. 探索中发现的 Trunk 缺陷（主线 bug）：默认 MUST 在当前 `poc/<topic>/` 登记为 bug
   切片并修测取证（TOPIC / amend 提案 / COMMITS）；MUST NOT 为「顺便修 bug」绕过本条
   第 6 款直接改 Trunk `src/` / `include/` / `tests/`。确认合入时 MUST 开产品提案
   （track=bug 或挂 promote 干净切片），干净合入 `src/`（及必要 `include/`），并可用
   `ndf_close --mode partial` 收口子集而主题继续 exploring。仅当缺陷已确认与当前假设
   无关且需紧急修生产路径时，允许 track=bug 直改 Trunk，事后 MUST 补 DEC/VER。
9. 开题前 MUST 扫描活跃 exploring 主题的 `explore_surface`（[[BEH-025]]）：
   相交则 MUST 串行（`depends_on_topics`）或声明 `conflicts_with_topics`，MUST NOT 默认可并行。

> rationale: 过早把探索写进 Trunk stable，或直接改 `src/`/`include/`，是 NDF 与 Trunk
> 漂移的主因（反面样板见产品负结果 DEC；含误改头文件）。写入隔离（方案 A）：改则必拷
> 进 `poc/<topic>/`，允许只读链未改 Trunk。主题装订器提供收敛与可复现，不引入第二套
> must SoT。POC 内发现主线 bug 见第 8 条；有条件并行见第 9 条与 [[BEH-025]]。
> 提案：`spec/meta/open/proposal-meta-poc-write-isolation.md`。

## 晋升闸门 {#BEH-019}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-021,DEF-022,META-004,META-005 -->

晋升到 Trunk MUST 同时满足：

1. **证据**：至少一组与目标协议一致的测量；MUST 对齐产品树现行诚实基准与严格隔离
   验收协议（权威路径：`spec/40-constraints/sla.md`）
2. **提案**：`proposal-*` 经人工确认；固定目录条款从 draft→stable（或新增 stable）；
   promote 提案 MUST 列出 draft→stable ID 清单，并引用该主题 `TOPIC.md`
3. **代码**：以**干净合入**方式进入 `src/`（重写/cherry-pick 最小切片），
   commit message 引用条款 ID 与提案/DEC，并含 trailers：`Topic:`、`Proposals:`、
   `Clauses:`、`Promotes: <topic>`（[[BEH-025]]）
4. **验证**：触发编译验证与相关 SLA/VER；失败则不得宣称已晋升
5. **装订器最终收口**：在代码集成、index/graphcheck、编译、适用的性能与金标验证全部通过前，
   主题只能处于 `closing` 编排态，MUST NOT 先标 `promoted` 或归档。全部通过后：
   `TOPIC.md` status → `promoted`；`COMMITS.md` 记录 `src_commit` + `spec_commit`；
   装订器迁入 `spec/archive/YYYY-MM/poc-<topic>/` 或保留摘要指针（二选一，promote 提案写明）。
   若存在 `poc/<topic>/NOTES.md`，MUST 将文件头 status 与 TOPIC 对齐为 `promoted`
   （日期/DEC/提案指针；见 [[BEH-025]]）。**partial** 且主题仍 exploring 时：
   NOTES SHOULD 标明 `partial` + TOPIC 仍 exploring，MUST NOT 写成全量关闭。
6. **语义核决策**（[[META-004]]）：promote 或 partial 收口 MUST 决定是否蒸馏 L3 语义核
   （**要** / **不要** / **延期**）。造核为 MAY（同提案或紧随产品提案交付 `spec/models/` +
   `model=`）；MUST NOT 用 poc/patch/ledger 冒充金标；**不**替代 VER。
   决策清单承载面：`python3 spec/meta/tools/ndf_close.py plan --mode promote|partial`
   （只读 plan；缺 MODEL 不是工具失败条件）。
   若合入引入或变更运行时旋钮 / 性能约束，SHOULD 按 [[META-005]] 更新相关条款的
   `trunk-ref=`（指向合入 feat SHA 或 tag）。
7. **基线失效与表面冲突**（[[BEH-025]]）：promote 或 partial 合入后 MUST：
   - 将受影响 exploring 主题（**含本主题若仍 exploring**）`baseline_status` → `stale`；
   - 对 `explore_surface` 相交的活跃主题做冲突/依赖复核（`conflicts_with_topics` /
     `depends_on_topics`）；MUST NOT 默认可加跨主题收益。
   清单承载：`ndf_close` plan §4c / §4d。
8. **Draft 映射受控路径**：晋升 MUST 以 `spec/meta/open/draft-map/` 映射条目为闸门。
   条目 `proposed_status` MUST 按 `exploring → closing` 由提案确认触发；全部闸门通过后
   MUST 将映射条目归档（`spec/meta/open/draft-map/archive/` 或等效摘要指针），然后固定
   模块正文才写入对应 `status=stable` 条款。MUST NOT 在映射条目仍 `exploring` 时把正文
   写成 stable。

禁止：先合主线再补 stable 契约；或先写 stable must 再补 POC 证据。

## 金标更新义务 {#META-006}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.11 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-019 -->

每次 promote / bug / refactor 合入 Trunk `src/` 后，MUST：

1. 重跑产品树现行 Golden 约束声明的标准配置与测量矩阵。
2. 生成或更新产品验证树中的 Golden Baseline：
   - 绑定新 Trunk SHA（`git rev-parse HEAD`）
   - 记录现行协议要求的性能、质量、稳定性与资源指标
3. 如配置参数变更（新增/修改运行时旋钮、默认值、数据路径），同步更新产品 Golden
   约束所指向的配置快照。
4. 金标更新 commit MUST 引用触发的 promote/bug 提案（`Promotes:` / `Fixes:` trailer）。

**豁免**：纯文档变更（spec/ / README）、POC 目录内变更（poc/）不触发金标更新。

> rationale: 性能测试不仅依赖代码，还依赖配置参数。流程层只规定 SHA + 配置 + 测量结果
> 的更新义务；具体矩阵、路径与指标属于产品验证树。

## POC 性能线唯一绑定 {#META-007}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.12 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-025,META-006 -->

活跃性能 POC MUST 由 TOPIC `perf_baseline` 唯一指向 `PERF_BASELINE.md`，卡头 MUST 绑定：

```text
vs × config_id × measure_script
```

1. `vs` 标识比较金标或显式 Trunk 基准；`config_id` 标识配置快照；
   `measure_script` 标识可执行测量入口，可另列 `measure_binary`。
2. 首次 R0 前 Numbers MAY 为 pending；R0 后 MUST 写 `baseline_trunk_sha`、
   `baseline_status=current` 与 Numbers。
3. 比 Δ% / 压测 MUST 只读 TOPIC → PERF_BASELINE（绑定与 Numbers）→ DELTA；
   MUST NOT 从 stable SLA 或 NOTES 抄观测数字。
4. `DELTA.md` 记录 Feature / Hotspot / Bind snapshot / Rounds，是 Design↔Test 变化账本，
   不替代比较 SoT 或原始 evidence。
5. 配置-only 变更 MUST 更新绑定并重测，不得以修改 stable SLA 代替。

> rationale: 性能结论必须能回答「对谁、用什么配置、由哪个入口、得到哪些数」；
> SLA 是合约下限，不是探索观测线。

## Project Genesis 初始化轨 {#META-009}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-003,META-008 -->

NDF 工作流 MUST 在日常 Proposal/POC 前支持一次性 `track=bootstrap`：

```text
> track: bootstrap
> bootstrap_mode: greenfield | adopt
```

- `greenfield` 从用户原始 IDEA 建立项目目标、本地 NDF Foundation 与初始 Trunk candidate。
- `adopt` 对已有代码做 observed 盘点、建立本地 NDF、验证并冻结 Genesis；
  MUST NOT 改写既有 git 历史。
- 已存在 accepted Project Genesis 决策的 operational 项目 MUST NOT 重跑 bootstrap；
  重建基准另走 process/refactor 提案。
- 兼容既有健康棕地：无 Genesis 决策但已有完整 `spec/00–50`、产品代码与可运行治理门禁时，
  MAY 标 `operational_legacy` 并提示可选 adopt；MUST NOT 因新流程阻断既有日常 POC。
- 日常指挥面是**任意宿主**上运行 ndf-workflow 五句口令（Cursor / OpenClaw / Claude /
  OpenCode / Codex / generic 等 Command Agent）——**不是** Cursor-only；无可视化面板义务。
- G0 `IDEA已审核` 之前（或与 IDEA 并行但 MUST 先完成）：角色向导 MUST 将 Command /
  Control / Implementation 三角色绑定写入项目 `ndf.workflow.yaml`；人类口令 **角色已配置**
  MUST 追加到 Genesis `GATES.md`，并绑定 roles 段内容 SHA。
- `roles_unbound` MUST 阻塞 Foundation（G1）与所有 dispatch（`safe_to_dispatch=false`）。
  operational 项目首次派发若未绑定亦 MUST 先跑角色向导。

初始化门禁 MUST 串行：

```text
角色已配置 → IDEA已审核 → CHARTER已审核 → ARCHITECTURE已审核
→ VERIFICATION已审核 → 可以建立初始主线 → GENESIS已审核
```

1. 用户原始 IDEA MUST 原样保存来源；确认后的目标/scope/non-goals 进入产品 Charter，
   取舍、已知 draft 与 Genesis 绑定进入产品 Genesis 决策。
2. 无证据的性能数字 MUST 为 draft/TBD/`not-established`，MUST NOT 冒充性能金标。
3. 收到「可以建立初始主线」后才可通过 **Implementation 角色**（默认 Claude Code ACP；
   MAY 为 `in_host` / `dual_session` / `custom`）隔离环境建立最小可构建垂直切片。
4. Implementation 角色 MAY 写初始代码、测试、构建配置与 L2/L3；MUST NOT 修改 L0/L1、
   Charter、Architecture、Decisions 或 `spec/meta/`。
5. NDF 图、构建、最低功能验收与三空间追踪均闭合后，Project Genesis 决策 MUST 绑定
   IDEA 来源、NDF tree SHA、Trunk SHA、verification ref 与 known drafts；
   收到 `GENESIS已审核` 后项目才进入 `operational`。

项目目标金标（Charter + Genesis 决策 + git SHA）与性能 Golden Baseline 是不同对象。

## 人工门禁回执 {#META-010}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-001,META-008 -->

需要机械展示或自动委派的人工作业 MUST 使用 append-only 门禁回执。POC 回执位于
`poc/<topic>/ndf/GATES.md`；Genesis 使用初始化 GATES。每条回执 MUST 记录：

```text
gate / phrase / approved_by / approved_at
approved_content_sha / source_ref / status
```

1. 文件存在 MUST NOT 推导为人工已审核；缺回执时只能显示 `missing` / `unknown`。
2. 内容 SHA MUST 由该闸绑定的 canonical 文件束计算；实质修改后，下游回执 MUST
   追加 `invalidated`，不得改写历史审批。
3. POC 的 `topic_review` 绑定 TOPIC + root proposal；
   `design_review` 绑定 TOPIC + DESIGN；
   `implementation_approval` 绑定 TOPIC + DESIGN + PERF_BASELINE 绑定头 + DELTA 假设 +
   INTERFACE。
4. **文字优先路径**（[[ADR-META-003]]）：新托管主题 MAY 用单次回执
   `bundle_dispatch`（phrase=`派发`）代替闸 3；内容束 MUST 与
   `implementation_approval` 相同。`topic_review` / `design_review` 三闸串行对
   该路径为 legacy/可选；产品提案「已确认」/「已审核」仍为契约落地门。
5. 口令仍由人触发；Command Agent / 工具 MUST NOT 静默批准或伪造 `approved_by`。
6. 本条不要求回填历史 POC；历史主题显示 `legacy/unknown`。

### POC 门禁 review slice

新建或已迁移主题的门禁 MUST 绑定显式 `review_slice`，而不是冻结整份探索日志。
切片标记 MUST 在同一文件内成对、ID 唯一、不可嵌套；canonical 输入为：

```text
slice_id NUL repo_relative_path NUL slice_bytes NUL
```

bundle 中切片按 `slice_id + path` 排序后计算 SHA-256。推荐标记：

```markdown
<!-- ndf:gate-slice begin=topic_contract -->
... reviewed contract ...
<!-- ndf:gate-slice end=topic_contract -->
```

| gate | review slices |
|------|---------------|
| `topic_review` | TOPIC intent/scope/hypothesis/directions/proposal contract |
| `design_review` | topic contract + DESIGN goals/non-goals/modules/data-flow/trunk-boundary/design contract |
| `implementation_approval` | 上述 contract + PERF bind header + DELTA hypothesis + INTERFACE contract |
| `bundle_dispatch`（文字优先） | 与 `implementation_approval` 相同；phrase=`派发` |

下列 mutable 内容 MUST 位于 review slice 外；仅追加它们 MUST NOT 改变闸 SHA：
TOPIC lifecycle/baseline 导航字段、PERF Numbers、DELTA Rounds、`evidence/`、
`COMMITS.md`、`GATES.md`。若结果反向修改假设、接口、绑定配置或实现边界，MUST 先修改
对应 review slice，不得借 mutable 区绕过重审。

**证伪 / drop 落点（[[BEH-019]] partial 路径）**：假设证伪或 Feature/Hotspot 标
`dropped` 的**叙事与证据** MUST 写入可变面（DELTA Rounds 结论行、NOTES、`evidence/`）。
改 `delta_hypothesis` / DESIGN contract 中 Feature 或 Hotspot 的 **status 字段**
属于实质 amend：MUST 走 `binder_amend`（或装订器流水线）并按失效矩阵重审受影响闸，
MUST NOT 指挥官直改契约切片后假装闸回执仍有效。再派 ACP 写码前 MUST 重过闸 3；
**选 `partial` / 跑 `ndf_close plan --mode partial` MUST NOT 仅因闸 3 invalidated 被挡**
（见下「门禁完成、探索决策与关闭资格」）。

失效矩阵：

| changed review slice | invalidated gates |
|----------------------|-------------------|
| TOPIC contract | topic_review, design_review, implementation_approval |
| DESIGN contract | design_review, implementation_approval |
| PERF bind / DELTA hypothesis / INTERFACE contract | implementation_approval |
| Numbers / Rounds / evidence / COMMITS / GATES | none |

缺标记、重复标记、错配或嵌套 MUST fail closed。旧主题 MAY 显示
`bundle_mode=legacy_whole_file`；迁移必须追加 invalidated/迁移说明并重新审核，
旧 whole-file SHA MUST NOT 验证为 review-slice SHA。

### 闸漂移解释（人审 UI）

内容 SHA 仍是身份钉；人审需要的是 **相对最近一次有效回执** 的可读 diff，不是两个
hex。当任一 POC 闸（含 `bundle_dispatch`）为 `invalidated` 或
`approved_content_sha` ≠ 当前 `expected_content_sha` 时，指挥面与相关 CLI（至少
`poc-dispatch`、`topic-health`）MUST 产出漂移解释，至少含：

1. `gate`、`approved_content_sha`、`expected_content_sha`；
2. `changed_slices`（`slice_id` + 相对路径）；未变切片 MUST NOT 喧宾夺主；
3. `slice_diffs`：每个变更切片的 unified diff（或等价行级 diff），**仅**
   `ndf:gate-slice` 内字节；
4. `human_next`：重审后回「派发」，或先改回契约再派发。

mutable 面（Numbers / Rounds / evidence / COMMITS / GATES / TOPIC 导航头）MUST NOT
进入该 diff。无法还原批准时刻切片正文时 MUST 报 `diff_unavailable` + 原因，并仍列出
当前 slice 指纹；MUST NOT 静默假装无变化或自动重批。

为可 diff，写入有效闸回执时 MUST 保留可对比基线（按 `approved_content_sha` 索引的
slice 快照、可 `git show` 的 `source_ref`、或 pack 内嵌副本之一）。缺基线 →
`diff_unavailable`。解释默认落聊天；全文 MAY 写 `tmp/ndf-gate-drift-<topic>.md`，
MUST NOT 写入 `spec/open/`。

Process proposal 的 `已确认` / `已审核` 也属于人工回执，其内容束与状态机由
[[META-014]] 定义；MUST NOT 直接套用 POC gate 推导规则，或由 proposal 文件存在
与 Agent acknowledged 推进状态。

## 文字委派与磁盘完成合同 {#META-011}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-008,META-010 -->

日常 POC 与 Control 委派的权威合同是**文字指挥 + 机械安全门 + 磁盘 completion**，不是可视化面板或回放仪式（[[ADR-META-003]]、[[ADR-META-004]]）。无面板亦 MUST 能完成完整环。

**文字优先主路径**（[[ADR-META-003]]）：

```text
Idea → 产品提案「已确认」/「已审核」
→ 整包装订器（TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE）
→ Human「派发」（绑定当前契约 bundle SHA）
→ poc-dispatch（实现|测量）
→ Human「继续」修订装订器再派发，或选 close 模式
```

日常写入口是 CLI `poc-dispatch`（内联租约）。人审「派发」/「继续」是聊天确认授权送出 ready
pack；POC「派发」仍 MUST 把 `bundle_dispatch` 回执写入 `GATES.md`（[[META-010]]），
聊天确认 ≠ 回执存在。legacy 三闸「可以开始实现」仅兼容旧主题。

### 成功分层（不得互相冒充）

1. **transport acknowledgement**：CLI / agent exit 0 只表示消息已送达。
2. **validated completion**：日常 POC 以 pack 钉死的 `completion_receipt_path` 上磁盘
   `ndf-agent-completion/v1` 为准——`result=success` 且 topic/task/run 身份匹配。
3. stdout `ndf-dispatch-notify/v1` 仅运输辅助；stdout 中的 completion MUST NOT 冒充磁盘回执。

历史 Episode / Replay 缺字段 MUST NOT 单独把实质完成判失败（[[ADR-META-004]]）。

### 硬安全门

委派前 MUST 同时满足：

1. `workspace_truth.workspace_bound`（`repo_root` + `active_topic` 等身份一致）；
2. 对应人工回执有效且 approved content / bundle SHA 未漂移；
3. `allowed_write_root` 在 `repo_root` 下可解析 + POC isolation 通过；
4. 同 topic 无其它写 run；`run_id` 作为 lease；
5. Claude Code 管道返回 `run_id/session_id`、`base_sha`、独立 worktree/branch（或可证等价）与写根；
6. context manifest / role plan 发送时有效；ACP 估算不超 `NDF_ACP_CONTEXT_MAX_TOKENS`。

缺任一项 MUST `unsafe` / 拒绝派发。`workspace_bound=false` 时 MUST NOT `safe_to_dispatch`。
因人工 bundle SHA 漂移而硬阻塞时，报告 MUST 满足 [[META-010]] 闸漂移解释最小合同
（changed slices + slice diff 或 `diff_unavailable`），使人可完成重审；MUST NOT 仅输出
不透明哈希。

身份绑定与执行 HEAD 绑定 MUST 分离：仅身份失配构成 `workspace_unbound`；HEAD 漂移单独记
`execution_binding_stale`。`execution_binding_stale` MUST NOT 挡测量或实现。pack `base_sha`
MUST 取 live `git_head()`。

`prepare-acp-lease` 保持 lease_only legacy；`poc-dispatch` MUST 内联创建或复用隔离租约，
不得要求人工第二跳。lease MUST 写入隔离 worktree 与 `tmp/ndf-workflow-leases.jsonl`，
MUST NOT 用空 stub 冒充。ACP 可达 ≠ 活跃隔离租约。

### 三层能力（Command / Control / Implementation）

| 层 | 角色 | 默认绑定 | 入口 | 写界 |
|----|------|----------|------|------|
| Command | Command Agent（当前宿主） | 当前宿主 + `ndf-workflow` skill | 五句口令；造 pack；等人审；调 CLI | tmp pack / 触发回执 CLI；MUST NOT 写 worker 实现/测量 |
| Control | Design agent | OpenClaw | `control-pack` / `project-control-pack` →「派发」→ `dispatch-send` | `poc/<topic>/ndf/`、`spec/open/`、`spec/meta/open/`、`.openclaw/state.json` |
| Implementation | Implementation agent | Claude Code ACP | `poc-dispatch`（POC）；`genesis-pack`（初始化）；promote 按 close plan | track 允许写根（POC 仅 `poc/<topic>/`） |

Control MUST NOT 写 `src/`、`include/`、`tests/`、`spec/meta/` 稳定正文（land 除外且须人审），
MUST NOT 静默写 `GATES.md` 的 `approved_by`。Implementation MUST NOT 改 L0/L1 / `spec/meta/`。
Command MUST NOT 代写 worker 边界内的实现/测量，MUST NOT 直接 `openclaw.chat_send` 绕过
`dispatch-send`，MUST NOT 打开可视化面板。运行态从管道查询，MUST NOT 写入
`.openclaw/state.json` 冒充装订器 must。

### 角色适配器解析

三角色绑定落项目 `ndf.workflow.yaml` 的 `roles.*`（`adapter` / `fallback` / `model`）。
MUST NOT 把三层塌缩为一层；Command MUST NOT 兼做 Control+Implementation 写 worker 边界。

每角色独立解析序：

1. **首选 adapter** 且 CLI / 会话可用 → 现行 dispatch 路径
2. **`in_host`**（或配置的 fallback）→ Command 在同宿主 spawn 子 agent（写出 spawn 文件；
   不伪造 transport ACK）
3. **`dual_session`** → 输出角色 prompt；人类在两聊天粘贴；仍等磁盘 completion
4. **`custom`** + `command` → 用户自定义命令
5. 否则 → `role_adapter_unsupported` + `human_next`；MUST NOT 伪装成功

缺 OpenClaw / Claude Code CLI **不是** workflow-fatal，若 `ndf.workflow.yaml` 已配置合法
fallback。`roles_unbound` 仍 MUST fail-closed。

机械入口：`python3 spec/meta/tools/ndf_role_binding.py bind|resolve|status`。

当 Control `adapter=openclaw` 时，OpenClaw 探测 MUST 分三态：`gateway_reachable`、
`session_configured`（`AGENTS.md` 非空 session_key）、`session_dispatchable`（routing key
可匹配 sessions store，或本身为合法 UUID）。`session_key`（可含 `:` 的通道路由串）与
`openclaw agent --session-id`（UUID）MUST 区分。Control `safe_to_dispatch` MUST 要求
gateway 可达且 session 可派发。`dispatch-send` 对 routing key 走 gateway `sessionKey`；
仅已解析 UUID 才用 `--session-id`。

Control 与 Implementation 等待 MUST 用心跳续等（`NDF_OPENCLAW_*` / `NDF_ACP_PING_SEC` /
`STALL_SEC` / `MAX_SEC`）：有会话或磁盘回执进展则刷新 stall；连续无进展达 stall 阈值才
stalled；绝对上限才 timeout。MUST NOT 仅靠固定墙钟把仍在工作的长 hop 判死。在途 hop
「进展如何」MUST `dispatch-probe`，MUST NOT 对同一 pack 再 `dispatch-send`。

ACP `dispatch-send` MUST 在运输前估算 transcript 与 slim worker 预算；超限 MUST
`acp_context_over_budget` fail-closed。默认 `--fork-session`（可用 env 关闭），每 hop
分叉执行面。换绑 ACP 会话后 MUST `ndf_acp_session_bootstrap.py` 再派发。

### Per-Project Workspace

项目本地指挥状态首选 `{repo_root}/ndf.workspace.json`；`.openclaw/state.json` 作兼容
alias（OpenClaw Control 收到 pack 后 MAY 写入）。MUST NOT 与 `~/.openclaw/` 全局 session
混淆。所有 pack MUST 含 `workspace`（`repo_root`、`repo_head`、`active_topic`、`topic_dir`
等）。相对路径 MUST 在 `workspace.repo_root` 下解析。Implementation worktree MUST 在
`repo_root` 下。

### 宿主 PID 卫生（简化）

发现 Agent Shell `EAGAIN` / fork 失败时 MUST 先跑
`python3 spec/meta/tools/ndf_workflow_status.py host-pids --json`，读 cgroup /
consumers / advice，再决定是否清理嫌疑进程。MUST NOT 改 `environment=cloud` 绕开，
MUST NOT 调大 TasksMax。

完成回执 MUST 含 changed files、commit SHA（若有）、复现命令与 evidence 路径；随后 MUST
再跑写入隔离检查。POC 正结果关闭顺序仍为 promote 提案 → `ndf_close plan` → 集成 →
index/graphcheck → 编译/性能/金标 → TOPIC 收口（见 [[BEH-019]]）。

> rationale: 可信度由身份、写根、人审 bundle、并发、上下文预算与磁盘 completion 保证；
> 面板与回放不得反客为主（[[ADR-META-004]]）。

## NDF 任务上下文与证据绑定 {#META-012}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.14 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-002,META-008,META-010,META-011 -->

Command Agent、OpenClaw 与 Claude Code MUST 使用同一份带 SHA 的 Task Manifest，并从中派生
各自的 role-specific Context Plan；不同 role plan SHA MAY 不同，但 MUST 引用同一
`manifest_sha`。工具只读投影 Manifest / 角色摘要，MUST NOT 成为第四上下文 SoT
（[[ADR-META-004]]）。

任务上下文 MUST 按以下顺序机械组装：

```text
BinderReadOrder → NDFGraphClosure → Git/ImplementationSurface
→ Evidence/Baseline → Gate/RuntimeLease → RoleSpecificPrivilege
```

1. Binder MUST 先按 [[BEH-025]] 读序；clause seed MUST 来自 TOPIC、提案、ledger /
   trailers、task 默认条款或 close plan，禁止仅凭自由文本猜测。
2. 图默认只沿 `depends-on` / `refines` 展开；其它边 MUST 按 task 明确启用。
   traversal MUST 有 depth/node/byte budget，截断 MUST 报告。
3. Task Manifest MUST 绑定 task、track、topic、repo HEAD、共享图/evidence/gate；
   Context Plan MUST 绑定 manifest SHA、role、source generation、gate bundle、
   baseline、ordered reads、图策略、允许写根、禁止路径与人工口令。
4. Context Bundle MUST 绑定 plan SHA、每个文件/条款 chunk SHA、git/evidence joins；
   Agent 执行前 MUST `context-verify`，漂移时 MUST 停止并重新编译。
5. 默认 bundle MUST NOT 从 NOTES / stable SLA 抄 POC 观测数字；仅显式测量 task
   MAY 读取 PERF_BASELINE Numbers。
6. OpenClaw 只接收 Control 文档流 role plan；Claude Code 只接收 Implementation/Test
   及对应已批准契约 role plan。不兼容 `role × task × track` MUST fail closed。
7. Task Manifest MUST 绑定 Context Compiler 派生证明（compiler identity/version、
   policy、seed/binder/graph/evidence 输入摘要，以及 closure、truncation、conflicts、
   baseline、blockers 与 role policy 摘要）。验证 MUST 用同一 policy 重新派生语义；
   仅重算 `manifest_sha` 不足以证明合法。
8. Task Manifest / Context Plan MUST 绑定
   `bundle_mode | slice_id/path/content_sha | allowed_sections | mutable_sections`。
   Context verify MUST 重算 slice SHA；legacy whole-file 与 review-slice plan 不兼容时
   MUST 新 Manifest，不得 silently 混用。
9. Project-control 任务 MUST 额外绑定 `proposal_id | flow_id | hop | origin`，以及
   `intent_sha` 或 `proposal_path + proposal_sha`。内容或 hop 漂移时 MUST 创建新
   Manifest。

机械入口：`ndf_context.py manifest-create|role-plan|context-expand|context-verify`。

委派 readiness MUST 分离 soft 与 hard：

```text
poc_dispatch_hard_passed | static_preflight_passed | runtime_dispatch_ready
```

**文字优先硬门**（`poc-dispatch`，[[ADR-META-003]] / [[ADR-META-004]]）仅：
`repo_root`+topic 身份；Human「派发」或闸 3 绑定**当前**契约 bundle SHA；
`allowed_write_root=poc/<topic>/` + isolation；同 topic 无并发写 run；隔离
worktree/base_sha 可证；context manifest/plan 发送时有效；磁盘 completion 身份匹配；
ACP context 不超预算。

下列 MUST NOT 单独挡住 `poc-dispatch`（soft / warning）：meta graph、全量 bindcheck、
product graph、缺非必要 completion 字段、默认 runtime probe。它们 MAY 在提案收口 /
实质 amend / close/promote 时强制。

legacy `static_preflight_passed`（gate / baseline / perf / isolation / context /
bindcheck / product graph）继续门控旧 `delegate-poc` / `pack` 路径。MUST NOT 作为
`partial`/`reject` 或 close 编排必要条件。闸 3 / `bundle_dispatch` invalidated 时写派发
MUST 仍 fail-closed；Human 选 `partial` 与 `ndf_close plan --mode partial` MUST NOT
仅因此被挡。

`poc-dispatch` writable pack MUST 绑定 Task Manifest、role plan 与 exact
`allowed_write_root`。

Command Agent / 工具 MUST NOT 修改 `.openclaw/state.json`；runtime lease 只写
gitignored 临时证据。Runtime lease 在 live worktree 校验成功时 MUST 保存
acquisition-time durable binding proof；completion MUST 以 acquisition/completion
双快照证明 tracked、untracked 与越界 mutation，并使实际变化集合与声明的
`changed_files` 双向一致。Close/post-check receipt MUST 绑定注册 verifier 的绝对身份、
argv/version、真实退出码与结构化输出；任意 evidence bytes 加自报 `passed` 不得使
验证状态变绿。

> rationale: 同一 manifest SHA 装订 OpenClaw 与 Claude Code；硬门只保留执行安全与
> 磁盘合同，软检查不得伪装成日常派发仪式。

## Agent Episode、事件链与回放等级 {#META-013}
<!-- ndf: kind=req level=must layer=L1 status=deprecated since=0.9.15 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-010,META-011,META-012 -->

**历史合同（已退役运行义务）。** Agent Episode 曾是 Context Plan 之外的可审计时间 DAG：
内容寻址对象、`seq` / `prev_event_sha` / `event_sha` 事件链、R0–R3 回放等级、tool
cassette、checkpoint、Control gate/binder 双流水线分步事件，以及 Commander Replay /
button-action 账本。可写委派曾 SHOULD 绑定 Episode 与同一 `ndf-task-manifest/v1`。

按 [[ADR-META-004]]（supersedes [[ADR-META-003]] 中「保留 Episode/Replay 为审计工具」
的运行义务）：

1. Episode / Replay / Action begin-commit-finish / button-action **MUST NOT** 作为日常
   `poc-dispatch`、派发成功或 close 的必要条件。
2. 日常成功合同仅为：硬安全门（[[META-011]]）+ Task Manifest / context verify
   （[[META-012]]）+ 磁盘 `ndf-agent-completion/v1` 身份匹配。
3. 历史 `.ndf/replay/`（及同类本地回放工件）保持**只读考古**；MUST NOT 新生成参与
   成功判定，MUST NOT 要求人类理解投影/回放状态才能继续文字指挥。
4. 争议取证 MAY 只读查阅历史对象；MUST NOT 把缺完整 Episode DAG / Replay 字段单独
   判失败。

本条款 `status=deprecated`：正文保留语义摘要供考古，新建流程 MUST NOT 依赖本条运行。

> rationale: 少则得——回放仪式不得反客为主；安全内核留在 META-011/012。

## 回放沙箱与执行器边界 {#META-015}
<!-- ndf: kind=req level=must layer=L1 status=deprecated since=0.9.17 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-011,META-013 -->

**历史合同（已退役）。** 本条曾定义可选 Lvm guest 沙盒证明：执行器不在现仓、现仓对
guest 不可写、出站仅回执、`ndf-replay-guest-proof/v1` 可证伪，以及 Lsoft / Lns / Lvm
分级（仅 Lvm 可称「已回放」）。宿主 `guest-run` 曾为可选 adapter，不是文字指挥主路径。

按 [[ADR-META-004]]：Guest / Lvm / `guest-run` / R2 沙盒证明 **不再**作为日常委派、
成功判定或人类工作流义务。无 guest 后端 MUST NOT 阻塞 `poc-dispatch` 或磁盘
completion 收口。历史证明文件若存在，只读考古；MUST NOT 新要求人类跑 guest 才能
继续。

本条款 `status=deprecated`。

> rationale: 可选沙盒证明曾服务 Replay；控制面退役后不再占用注意力。

## Process Proposal 生命周期与回执 {#META-014}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.16 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-010,META-011 -->

### Idea / 提案路径分流（[[ADR-META-004]]）

| Idea 类型 | 落点 |
|-----------|------|
| 产品能力、运行中项目、bug、性能、POC、Genesis | `spec/open/` |
| NDF 语言、工作流、Agent 编排、治理工具、规范卫生 | `spec/meta/open/` |
| 同时影响两面 | 拆成两个互相引用的提案；无法判断时先问人 |

产品提案 MUST NOT 写入 `spec/meta/open/`；process 提案 MUST NOT 写入 `spec/open/`。
路径与 plane / track 不一致 MUST fail closed。共享任务名 `control_proposal` MAY 作
兼容别名，默认映射产品平面；新流程 SHOULD 使用 `product_proposal` 与
`process_proposal` / `ndf_improvement_proposal`。

### 生命周期

新托管 process proposal MUST 使用：

```text
pending_confirmation
→ confirmed_pending_land
→ implemented_pending_review
→ reviewed
```

`rejected` / `superseded` 为终态；archive 只是存储位置。旧
`Status: Implemented on ...` 与审核标记只作兼容输入；缺现代回执时 MUST 标
`legacy_*_unbound`，不得自动完成 gate 或产生可写 hop。

### 人工回执

`proposal.confirmed` / `proposal.reviewed` MUST 是 append-only 结构化回执，并至少绑定：

```text
proposal_id | phrase | actor | approved_at | proposal_sha | status
```

actor MUST 为 Human，phrase 分别为精确口令 `已确认` / `已审核`（[[META-010]]）。
Agent acknowledged、文件存在 MUST NOT 推进生命周期。proposal 内容漂移后，下游回执
MUST append `invalidated`，不得改写历史。

落地（confirm_land）MUST 仅写入提案声明的 `land_targets`（通常 `spec/meta/**` 与
产品 thin 指针）；MUST NOT 静默改产品实现树。审核回执 MUST NOT 重写已落地 META 正文。

`.openclaw/state.json` 只承载 workspace 绑定与 OpenClaw 指挥进度，MUST NOT 承载
proposal receipt 真值。

> rationale: process 提案用路径分流 + 人口令 SHA 生命周期即可；Episode/面板对账已退役。

## 负结果与回退 {#BEH-020}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-022 -->

当探索证伪（样板：产品负结果 DEC）时 MUST：

1. 写/更新产品 `spec/decisions/`（负结果、根因、废弃条款列表）；DEC 正文或 commit 含
   `Rejects: <topic>`
2. 将相关 draft/stable 探索条款标 `deprecated` 或移出 must；关闭产品 `open/proposal-*` /
   装订器内提案为 Rejected/Superseded
3. **Trunk `src/`**：删除或永不合并该 POC 表面；若曾误合入，用显式 revert commit（引用 DEC）
4. **`poc/<topic>/`**：可保留失败复现至下一归档周期；**默认**将 `poc/<topic>/ndf/`
   整包迁入 `spec/archive/YYYY-MM/poc-<topic>/`（防踩坑）；`TOPIC.md` status → `rejected`。
   若存在 `NOTES.md`，MUST 将文件头 status 与 TOPIC 对齐为 `rejected`（日期/`Rejects`
   DEC；见 [[BEH-025]]）
5. 仅当条款曾写入 `spec/` draft 时，主线 MUST 保留 `deprecated` 壳并指向归档装订器
6. MUST NOT 要求改写已推送的探索 commit 历史来「对齐文档」——以 DEC + 当前树为准
7. 负结果关闭后若再探索同一方向：见 [[BEH-025]]「关闭后重启」——MUST 开平级新 topic；
   MUST NOT 将 `rejected` 主题 status 改回 `exploring`/`blocked`（原地复活）

## POC 主题装订纪律 {#BEH-025}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: refines=BEH-018,ARCH-008 depends-on=DEF-022,DEF-023,CON-POC-001 -->

每个活跃探索主题 `poc/<topic>/` MUST 维护装订器目录：

```text
poc/<topic>/ndf/
  TOPIC.md
  DESIGN.md
  PERF_BASELINE.md
  DELTA.md
  INTERFACE.md
  GATES.md        # 人工回执（新主题；历史主题可无）
  proposals/     # 本主题提案正文，或 stub 指回 spec/open/
  evidence/      # validation / 对照表
  COMMITS.md     # Commit Ledger [[DEF-023]]
```

### 呈现规则（唯一入口与阅读顺序）

- `poc/<topic>/ndf/` MUST 作为 POC 内唯一规范性呈现面；如存在 `poc/<topic>/README.md`，MUST NOT 作为 must 源（仅允许导航指针）。
- 协作者在 POC 内获取 NDF 的推荐阅读顺序 MUST 为：
  1. `poc/<topic>/ndf/TOPIC.md`
  2. `poc/<topic>/ndf/DESIGN.md`
  3. `poc/<topic>/ndf/PERF_BASELINE.md`
  4. `poc/<topic>/ndf/DELTA.md`
  5. `poc/<topic>/ndf/INTERFACE.md`
  6. `poc/<topic>/ndf/GATES.md`
  7. `poc/<topic>/ndf/proposals/`（或 stub → `spec/open/`）
  8. `poc/<topic>/ndf/evidence/`
  9. `poc/<topic>/ndf/COMMITS.md`

### 分段门禁与 GATES

**文字优先主路径**（[[ADR-META-003]]）：产品提案「已确认」/「已审核」后，OpenClaw
MAY **一次写齐** TOPIC / DESIGN / PERF_BASELINE / DELTA / INTERFACE（及测试计划）。
Human 以「派发」回执（`bundle_dispatch`，绑定与闸 3 相同的契约 bundle SHA）授权
实现/测量。仅实质 amend 假设、接口、测量协议或写入边界后，下一次「派发」才绑定新
SHA；Numbers / Rounds / evidence 追加 MUST NOT 触发重审。

三闸串行仍为 **legacy/可选**：

```text
TOPIC已审核 → DESIGN已审核 →（PERF 绑定 + DELTA）→ 可以开始实现
```

对应回执 MUST 写入 `GATES.md` 并符合 [[META-010]]。未收到「派发」或「可以开始实现」
（或回执 SHA 已失效）时，MUST NOT 编写/委派主题代码。工具 MUST 同时认文字优先与
三闸回执。历史 POC 不强制回填，投影显示 legacy。

### TOPIC.md

MUST 记录至少：`topic_id`；`status` ∈ {`exploring`,`blocked`,`promoted`,`rejected`}；
`baseline_protocol`（如产品树现行验收协议路径 + 数据集/线程）；
`explore_surface`（逗号分隔短标签，开题 MUST；例：`fine-rerank` / `page-cache-l4` /
`pq-codes` / `mt-scaling`）；
`baseline_trunk_sha`（首次 R0 后 MUST：当时 Trunk `src` 短 SHA）；
`baseline_status` ∈ {`current`,`stale`,`n/a`}（R0 后默认 `current`；关闭主题可用 `n/a`）；
`proposals[]`（路径、Status、角色 root/amend/process-hygiene）；`draft_clauses[]`；
`active_hypothesis` / `next_gate`；可选 `depends_on_topics[]`；互斥时 MUST
`conflicts_with_topics[]`。

### NOTES.md（实验日志；关闭时状态镜像）

- `poc/<topic>/NOTES.md` 为粗粒度实验日志，**MUST NOT** 当作 stable must 源。
- 当 `TOPIC.md` `status` 变为 `promoted` 或 `rejected`（主题关闭）且 NOTES 存在时，MUST
  在文件头（blockquote 或首节）写入与 TOPIC **同枚举**的 status，并注关闭日期、方式
  （promote|reject）及 DEC/提案指针（若有）。推荐：`> status: promoted|rejected`。
- **partial** promote 且 TOPIC 仍 `exploring`：NOTES SHOULD 标明 partial / 未全关，
  MUST NOT 仅写 `promoted` 以致误读为全主题关闭。
- 无 NOTES.md 时本条为 N/A（不强制创建）。

### 有条件并行（探索表面）

- **Trunk 时间线线性**：唯一现行实现由 promote/partial 推进。
- **POC 主题有条件并行**：两主题 `explore_surface` 交集为空时 MAY 并行；交集非空时 MUST
  **串行**（`depends_on_topics` 或等待对方 close）或声明 **`conflicts_with_topics`**。
- MUST NOT 将多主题 Δ 性能默认可加；跨主题结论 MUST 在同一 `baseline_trunk_sha` +
  同一 `baseline_protocol` 下重测，或引用冲突 DEC。
- 开题前 MUST 扫描活跃 exploring 的 `explore_surface`（见 [[BEH-018]] 第 9 条）。

### 基线 stale 与重测

- Promote 或 **partial** 推进 Trunk 后：受影响 exploring（**含未关闭的本主题**）MUST
  `baseline_status=stale`。表面不相交的兄弟 MAY 在 close plan 勾 N/A并注明理由。
- 继续测量前若 `stale` 或 `baseline_trunk_sha` 与现行相关 Trunk 不一致：MUST **重测 R0**
  并更新 SHA/`current`，或 evidence 显式 `vs_trunk=<old>` 且 MUST NOT 当作现行 Trunk 基线叙事。
- Partial promote 不创造「半新基线」：禁止用合入前 R0 报相对合入后 Trunk 的加速比。

### 探索延长与主题边界

- 同一假设与同一 `baseline_protocol` 下的深入（含对话延长需求）MUST 留在同一主题：
  追加 evidence、`amend` 提案、可选 partial promote。
- 假设或验收面分叉时 MUST 新建平级 `poc/<other-topic>/`，并用 `depends_on_topics[]`
  声明依赖；各自主题独立 promote/reject。
- MUST NOT 嵌套「子 POC」目录，也 MUST NOT 将子主题「晋升」进父 POC 目录。
  Promote 目标仅为 Trunk（[[BEH-019]]）。
- 欲同时 promote 两 `explore_surface` 相交主题：MUST NOT；先串行或先冲突闭环。

### 关闭后重启（平级新 topic）

- 当 `TOPIC.md` `status` ∈ {`rejected`, `promoted`}（主题已关闭）时：MUST NOT 将该
  `topic_id` 的 status 改回 `exploring` 或 `blocked`（禁止同 topic 重开）。
- 依赖工作就绪后欲再试同一方向：MUST 新建平级 `poc/<new-topic>/`，且：
  - `depends_on_topics` MUST 含已关闭的旧 `topic_id`；若另有使能依赖主题，MUST 一并列出
  - TOPIC（及存在时的 NOTES）MUST 写明相对旧 DEC / `Rejects:` 的**新假设或新 Trunk 前提**；
    MUST NOT 假装旧负结果未发生
  - MUST 新建装订器；首次 R0 后 MUST 写本主题 `baseline_trunk_sha` 与
    `baseline_status=current`
  - 开题 MUST 扫活跃 exploring 的 `explore_surface`（[[BEH-018]] 第 9 条）
- 仍为 `exploring` / `blocked`（含 **partial** promote 未全关）：继续同主题 amend /
  重测 R0（见「基线 stale」）；**不是**本小节「重启」。
- MUST NOT 将 `spec/archive/YYYY-MM/poc-<old>/` 迁回 `poc/<old>/` 冒充新开题；新题 MAY
  只读引用归档路径作为历史证据指针。

### COMMITS.md

凡修改该主题**代码或验证脚本**的 git commit，MUST 追加一行：

| date | code_commit | ndf_commit | proposals | clauses | protocol | note |

纯文档 typo 可免。目标：仅凭 TOPIC + COMMITS 即可回答「依赖哪些提案、用何协议、对哪次代码」。

### Git trailers

POC / promote / 负结果相关 commit message MUST 含：

```text
Topic: <topic>
Proposals: <id>[, ...]
Clauses: <id>[, ...]
```

promote 另加 `Promotes: <topic>`；负结果 DEC 相关 commit 加 `Rejects: <topic>`。
缺 `Topic:` 的 POC 代码提交，审查清单 MUST 判不合格（人工；hook 可选）。

### 与 Trunk SoT

装订器 **MUST NOT** 成为 `status=stable` must 源。Agent 实现 Trunk 时以 `spec/00–50`
为准；装订器仅服务探索进度与可复现。它在 [[META-008]] 中呈现 Design / Implementation /
Test 空间的 POC 工作副本，交互编排不改变其非 SoT 身份。

> rationale: 多轮提案下用主题装订收敛进度，用 ledger/trailer 绑定 commit↔NDF，
> 使「只读文档可复现测量」成为可检查纪律。有条件并行与基线 stale 防止
> Trunk 推进后旧 R0 与默认可加收益。关闭后重启一律平级新 topic，禁止同 id 复活。
> 提案见 `spec/archive/2026-08/proposal-meta-poc-topic-binder.md`、
> `spec/meta/open/proposal-meta-poc-baseline-staleness.md`、
> `spec/meta/open/proposal-meta-poc-sibling-restart.md`。

## NDF 缺陷分类（指针） {#BEH-026}
<!-- ndf: kind=info level=may layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH,CHR-008 -->

维护与修图前 MUST 使用统一缺陷词典：图语义面 / Layer A，与 **绑定溯源面**
（clause↔commit↔装订器↔路径；曾称 Layer B）。
权威定义见 [[DEF-NDF-GRAPH]] 及 [[DEF-NDF-CYCLE]]…[[DEF-NDF-BINDER-DUAL-HEAD]]
（`spec/meta/glossary.md`）；提案 `proposal-meta-ndf-defect-taxonomy`。

图语义面合法性 = NDF 规范锚点 ∧ 图论谓词（\(E_{\mathrm{dep}}\) DAG 等）。  
`ndf_graphcheck` 实现图语义面；`ndf_bindcheck` 实现绑定溯源面且 MUST `depends-on` 本分类。

> rationale: 先定义问题空间，再优化工具 / AI 维护。工具名须表意（bindcheck，非泛称 layerb）。