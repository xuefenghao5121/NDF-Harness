# Meta Process — 探索轨 / 晋升 / 负结果 / 装订

> scope: ndf-process  
> 条款索引: `CHR-008`, `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`, `BEH-026`,
> `META-006`, `META-007`, `META-009`, `META-010`, `META-011`, `META-012`, `META-013`, `META-014`, `META-015`, `META-016`, `META-017`, `META-018`, `META-019`, `META-020`, `META-022`, `META-023`, `META-024`, `META-025`, `META-026`
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
<!-- ndf: depends-on=META-003,META-008,META-010 -->

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
- 角色向导 MUST 将 Command / Control / Implementation 三角色绑定写入项目
  `ndf.workflow.yaml`，且 MUST 在绑内核与「派发」之前完成；人类口令 **角色已配置**
  MUST 追加到 Genesis `GATES.md`，并绑定 roles 段内容 SHA。
- `roles_unbound` MUST 阻塞 Foundation（G1）与所有 dispatch（`safe_to_dispatch=false`）。
  operational 项目首次派发若未绑定亦 MUST 先跑角色向导。

初始化 MUST 收成两步人话（[[ADR-META-003]]；不比 POC 更重）：

```text
角色已配置 →（Command 绑内核）→ 派发（写契约 + 复现基线）→ GENESIS已审核
```

`greenfield` 在「派发」与 `GENESIS已审核` 之间 MAY 插入 `可以建立初始主线` +
一次 Implementation `genesis-pack`。`adopt` MUST 跳过该代码切片 hop。

1. **内核绑定（Command，不派 OpenClaw）**：MUST 写短
   `spec/open/project-genesis/FOUNDATION.md`（`bootstrap_mode`、`observed_trunk_sha`、
   roles SHA）与 `GATES.md` 骨架。MUST NOT 在此步写产品契约长文。
2. **一次「派发」**：`hop=genesis_design`（对人类仍一句口令）。MUST：
   (a) Control 对照 Trunk 写满 `spec/00–50`（落盘时可为 draft）及必要
   `spec/decisions/` / `spec/INDEX.md`；MUST NOT 写 `spec/meta/` stable 正文；
   (b) 按刚写入的 VER 协议复现测试与金标/ sustained（Implementation 可同包串行），
   写入 `spec/50-verification/configs/` 与 `baselines/`，数字绑定 `observed_trunk_sha`。
   成功以磁盘 `ndf-agent-completion/v1` 为准。测不出 MUST 在 completion 标明
   `baseline_status=deferred` 与原因；欠账用一句「继续」补测，MUST NOT 展开日常
   promote 长教程。
3. **`GENESIS已审核`（Command 落地，不另派 OpenClaw）**：非性能骨架条款
   （CHR/ARCH/BEH/API/非 SLA 约束/VER 协议正文）MUST → `status=stable`，作为后续
   优化与二次开发的对照目标；已复现且绑定 Trunk SHA 的 baseline 与对应 `CON-SLA-*`
   MUST → `status=stable`；未复现成功的性能数字 MUST 留 `not-established`。
   项目进入 `operational`。MUST NOT 要求 GENESIS 后再走一轮日常 promote 才 stable 骨架。
4. `greenfield`：收到「可以建立初始主线」后 **Implementation 角色** MAY 隔离环境建立
   最小可构建垂直切片；MUST NOT 改 L0/L1 或 `spec/meta/`。`adopt` MUST NOT 为此再派。
5. Genesis 决策 MUST 绑定 NDF tree SHA、Trunk SHA、verification/baseline ref。
6. **Legacy（已废弃）**：CHARTER/ARCHITECTURE/VERIFICATION 连派。新 bootstrap MUST NOT
   走此路径；`genesis_per_draft_dispatch` fail-closed。
7. `genesis-status` 下一句：缺 FOUNDATION → 绑内核；骨架未写满 → 「派发」；
   设计+基线 completion 后 → `GENESIS已审核`（或 greenfield 的 `可以建立初始主线`）。
8. closeout 失败且无合法磁盘 completion → 同一 hop「继续」；MUST NOT 送下一 hop。
9. **Greenfield DESIGN_MAP 映射层**：`greenfield` Idea cycle (`ndf-genesis-idea/v1`)
   MUST NOT 直接物化 `spec/00–50`。MUST：(a) `hop=genesis_synthesis` 写
   `DESIGN_MAP.md` (`ndf-genesis-design-map/v1`)，信息面对齐 adopt 从 Trunk 可读的
   模块/数据流/算法/ABI/验证性质；(b) 人 **架构已确认**（`architecture_review`）绑定
   cycle + DESIGN_MAP SHA；(c) `hop=genesis_design` 只从已审核 DESIGN_MAP 物化 spec。
   一个 `cycle_id` = 一个项目周期；散文路书 MUST NOT 为 `source_ref`。Command 造
   synthesis pack 前 MUST `ndf_genesis_idea.py check`；DESIGN_MAP MUST
   `ndf_genesis_design_map.py check`。Pack MUST 携带 `design_evidence`；未
   `architecture_review` → fail-closed。**Adopt** 以 `trunk_observation` 一次 design hop。

日常优化/二次开发对照 Genesis 冻结的骨架与基线；不把「升 init 骨架 stable」做成多轮口令。

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
   `bundle_dispatch` 代替闸 3；内容束 MUST 与 `implementation_approval` 相同。
   Context verify / `poc-dispatch` MUST 认该替代（[[META-019]]）。
   `topic_review` / `design_review` 三闸串行对该路径为 legacy/可选。
   产品提案内容闸是「已确认」；POC「已审核」审的是装订器 markdown；
   「派发」才开租约并送出（[[META-025]]）。`bundle_dispatch` MAY 在装订器
   「已审核」后写入（`source_ref` 绑该次审核）；phrase 字段仍可为 `派发`
   以兼容既有校验。
5. 口令仍由人触发；Command Agent / 工具 MUST NOT 静默批准或伪造 `approved_by`。
6. 本条不要求回填历史 POC；历史主题显示 `legacy/unknown`。
7. 未收到 `GENESIS已审核` 的 bootstrap MAY 整树作废（删 `spec/open/project-genesis/`、
   重置 GATES、清 workspace `active_topic`），不必 append-only 续写旧 Foundation 审稿回执。
   作废后 MUST 按 [[META-009]] 新形状重跑内核绑定与设计 hop。

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

Process proposal 的 `已确认` 属于人工回执，其内容束与状态机由
[[META-014]] / [[META-025]] 定义；MUST NOT 直接套用 POC gate 推导规则，或由
proposal 文件存在与 Agent acknowledged 推进状态。

## 文字委派与磁盘完成合同 {#META-011}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.13 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=META-008,META-010 -->

日常 POC 与 Control 委派的权威合同是**文字指挥 + 机械安全门 + 磁盘 completion**，不是可视化面板或回放仪式（[[ADR-META-003]]、[[ADR-META-004]]）。无面板亦 MUST 能完成完整环。

**文字优先主路径**（[[ADR-META-003]] / [[META-025]]）：

```text
Idea → 产品提案「已确认」（审提案 markdown）
→ 整包装订器（TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE）
→ Human「已审核」（审 poc/<topic>/ndf/*.md）
→ bundle_dispatch + worker pack + pack-view 散文
→ Human「派发」（审 pack-view；开租约 + send）
→ Human「继续」修订装订器再编，或选 close 模式
```

人审对象 MUST 是上列 markdown / 分层散文。MUST NOT 把 completion JSON、
last-pack.json 或「是否写入磁盘」当给人审的主文。日常写入口是 CLI
`poc-dispatch`：未 `--send` 时 MUST NOT 建租约；`--send` / `dispatch-send`
MUST 已有同源 pack-view（[[META-025]]）。聊天确认 ≠ 回执存在。legacy 三闸
「可以开始实现」仅兼容旧主题。

### 成功分层（不得互相冒充）

1. **transport acknowledgement**：CLI / agent exit 0 只表示消息已送达。
2. **validated completion**：以 pack 钉死的 `completion_receipt_path` 上磁盘
   `ndf-agent-completion/v1` 为准——`result=success` 且 topic/task/hop/run 身份匹配。
   `dispatch-send` 在 transport_ok 后 MUST 读取该路径。合法磁盘回执即为 hop 成功。
3. stdout `ndf-dispatch-notify/v1` 仅运输辅助，MAY 用来定位 receipt。stdout 中的
   completion MUST NOT 冒充磁盘回执。notify 缺失 MUST NOT 单独把已有合法磁盘回执
   判失败。磁盘回执缺失或身份不匹配 MUST fail-closed（`missing_disk_receipt` /
   identity mismatch）。
4. bootstrap hop 的 `completion_receipt_path` MUST 含 `hop`（及 attempt），MUST NOT
   让不同 Foundation hop 覆盖同一 `*-attempt.json`。
5. 心跳 / stall 与磁盘回执：见 [[META-016]]。文字优先租约身份：见 [[META-019]]。

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
| Command | Command Agent（当前宿主） | 当前宿主 + `ndf-workflow` skill | 口令快捷 + 图/pack 观察面；造 pack；等人审；调 CLI | tmp pack / 人读投影 / 触发回执 CLI；MUST NOT 写 worker 实现/测量 |
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
`session_configured`（`ndf.workflow.yaml` `roles.control.session_key` 非空；
`AGENTS.md` 仅作迁移输入）、`session_dispatchable`（routing key 可匹配 sessions store，
或本身为合法 UUID，且 managed binding 通过 [[META-020]]）。`session_key`（可含 `:` 的
通道路由串）与 `openclaw agent --session-id`（UUID）MUST 区分。Control
`safe_to_dispatch` MUST 要求 gateway 可达、session 可派发、且
`multi_project_safe=true`。`dispatch-send` MUST 使用 pack `agent_id`（不得硬编码
`main`）；对 routing key 走 gateway `sessionKey`；仅已解析 UUID 才用 `--session-id`。
OpenClaw `dispatch-send` MUST 在发出本 hop agent 消息之前，**若该 `session_key` 已在
sessions store 存在**，对路由 `session_key` 调用 gateway `sessions.reset`（默认开启；
`NDF_OPENCLAW_RESET_SESSION=0` 关闭），使每 hop 为短对话；`session_key` 路由身份
MUST 保持不变。首 hop（尚无 session 行）MUST 跳过 reset 并允许创建。reset 失败 MUST
`openclaw_session_reset_failed` fail-closed，MUST NOT 把消息送进旧长对话。
`NDF_OPENCLAW_DISPATCH_CMD` 覆盖路径不自动 reset。这与 ACP 默认 `--fork-session`
对等，不是 completion。

Worker 消息 MUST 携带 pack `request.intent`（若有）。slim JSON MUST 含 `request`。
intent 声明 `track: bootstrap` 的 hop MUST 标 `track=bootstrap` 且 `hop=genesis_*`，
MUST NOT 标成新产品 Idea（`track=poc` + `next_human_phrase=已确认`）。缺意图或
Genesis 被标成 POC 时 `dispatch-send` MUST fail-closed（`worker_intent_stripped` /
`genesis_pack_labeled_poc` / `genesis_hop_unlabeled`），MUST NOT 把消息送出。
intent 头部 `hop: genesis_*` MUST 优先于正文子串。无头部时 MUST 按串行顺序、
以 `CHARTER.md` / `ARCHITECTURE.md` / `VERIFICATION.md` 写目标推断，MUST NOT 因
「MUST NOT write Architecture」等禁写句跳到 Architecture hop。bootstrap
`context_plan.topic` MUST 等于 pack `topic`（notify 身份，非 POC `topic_dir`）。

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

机械入口：`ndf_context.py manifest-create|role-plan|context-expand|context-verify`；
人读投影与 overlay 见 [[META-023]] / [[META-024]]（`pack-view` / `overlay-apply`；
主文=分层散文）。

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

## 心跳不得否定磁盘 completion {#META-016}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.1 source=stated scope=ndf-process -->
<!-- ndf: depends-on=META-011,META-009,META-010 -->

`dispatch-send` 心跳是探活，不是成功合同。

1. closeout MUST 再读 `completion_receipt_path`（含 pack/lease **worktree** 根）。
   身份匹配且 `result=success` 的磁盘 `ndf-agent-completion/v1` MUST 将 hop 判成功。
   `openclaw_stalled` / ACP stall / transport 非零 MUST NOT 单独否定该回执。
2. 心跳 progress MUST 认：会话 token/`updatedAt`、**回执文件出现或增大**、
   worktree **git HEAD 前进**。MUST NOT 只盯单一 adapter 的 token。
3. `genesis-pack` MUST 写入 `session_key` / `session_transport`（OpenClaw 运输时）；
   `provider` MUST 从 `roles.implementation.adapter` 解析。`task=project_genesis` /
   `hop=genesis_*` 的 pack MUST 映射 Implementation 角色，MUST NOT 因
   `provider=openclaw` 误派 Control。
4. `hop=genesis_trunk` / `task=project_genesis` 的 stall MUST ≥ 3600s，或
   `NDF_OPENCLAW_STALL_SEC` / `NDF_ACP_STALL_SEC` 覆盖。900s 仅 POC 默认。
5. `genesis-status` MUST NOT 因仅有 `src/.ndf-completion/` 判定已有 Trunk。

> rationale: greenfield vendor hop 上运输会话空转 + 实做写盘会导致假 stall。

## 宿主网络委派（沙箱不得选 provider） {#META-017}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.1.2 source=stated scope=ndf-process -->
<!-- ndf: depends-on=META-011,META-014 -->

Command 面的网关探活与委派 MUST 在 **宿主网络**（或等价全权限 shell）执行。

1. Command MUST NOT 在受限沙箱 / 无宿主 loopback 的环境里：做 gateway 探活、
   造会选定 `provider` 的 pack、或执行 `dispatch-send` / `poc-dispatch --send` /
   角色 spawn。
2. 沙箱对 `127.0.0.1:<gateway>` 的 `ECONNREFUSED` 或 `runtime_unavailable`
   MUST NOT 单独证明 gateway 已挂，MUST NOT 因此选定 `in-host`。
3. 若探活仅在沙箱失败：MUST 在宿主网络重探后再判定 fallback。
4. pack `provider=openclaw` 且角色为 Implementation 时，运输失败 MUST NOT 静默塌到
   `in-host`（避免指挥面/实现面作者身份塌缩）。Control 仍可按 yaml `fallback` 降级。

> rationale: 沙箱 loopback 连不上本机 gateway 会假报不可达并错误选 in-host。

## promote 合入与收口分 hop {#META-018}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.1.2 source=stated scope=ndf-process -->
<!-- ndf: depends-on=META-006,META-010,META-011 -->

`trunk_src_writes=required` 的 promote MUST 拆成合入 hop 与收口 hop；成功仍只认磁盘
`ndf-agent-completion/v1`。

1. **Implementation** hop（建议名 `promote_land`）：合入 Trunk / 工具 / L1–L3 与
   [[META-006]] 金标等 close-plan §5 检查。MUST NOT 用 `poc-dispatch --send`
  （其写界钉死在 `poc/<topic>/`）。
2. §5 全绿之后，**Control** hop（建议名 `close_finalize`）才执行 close-plan §4：
   `TOPIC`→`promoted`、COMMITS、`spec/archive/…` 指针（或物理迁）、提案薄注。
   MUST NOT 在 §5 未绿时标 `promoted`。
3. 同审查切片 SHA 再「派发」：GATES 旧 `approved` → `invalidated`，再 append 同行
   SHA 新批（[[META-010]]）。文件存在 MUST NOT 推断已批准。
4. 发 hop 前：目标 `completion_receipt_path` 与会假成功的活回执 MUST **MOVE** 走
   （`mv`）。仅 `cp` 而原路径仍在 = 假成功。
5. 指挥面已对同一 `session_key` 做过 `sessions.reset` 后，本次 `dispatch-send`
   MUST 设 `NDF_OPENCLAW_RESET_SESSION=0`，避免二次 reset 冲掉短会话。

> rationale: operational promote 验证——合入绿与 TOPIC 归档分 hop；活回执与二次 reset
> 会导致假成功 / 假失败。

## 文字优先不得因 Episode / 闸3 残留 fail-closed {#META-019}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.1.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-010,META-011,META-016 depends-on=ADR-META-003,ADR-META-004 -->

文字优先委派（[[ADR-META-003]] / [[ADR-META-004]]）MUST NOT 因缺 Episode / Replay
字段或仅缺闸 3 行而 fail-closed。

1. **闸 3 替代。** 实现 / 测量 hop 的 context verify MUST 接受有效
   `bundle_dispatch`（phrase=`派发`，SHA 对齐，`review_slice`）作为
   `implementation_approval` 的替代；内容束 MUST 与闸 3 相同。未收到人审口令
   MUST NOT 伪造 `approved_by`。
2. **租约身份。** 内联隔离租约 MUST 用 `run_id` / `session_id` / `base_sha` /
   `allowed_write_root` 作为握手身份。缺 `episode_id` MUST NOT 构成
   `lease_pack_incomplete`。若内部仍要相关字段，MUST 合成 `lease-<topic>-<stamp>`
   一类与 Replay 无关的 id；MUST NOT `init_episode`，MUST NOT 把 Episode 当成功条件。

> rationale: 文字优先 pack 故意不绑 Episode，Context / 租约仍按旧三闸与 Replay 字段拦截。

## 每项目独立 OpenClaw agent（跨项目并行） {#META-020}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.2.0 source=stated scope=ndf-process -->
<!-- ndf: depends-on=META-011,META-014 -->

本地多 Git 项目 MAY 并行委派 OpenClaw Control；每个项目 MUST 绑定独立 agent 与
`session_key`。同一 Git common-dir（含其 worktree）MUST 共用一个 agent，项目内
Control 仍串行。

1. **SoT。** Managed 绑定 MUST 写入 `{repo}/ndf.workflow.yaml`
   `roles.control.{agent_id,session_key,session_transport,session_binding_version}`
   （`session_binding_version=ndf-v1`）。`AGENTS.md` session 行仅作迁移输入。
2. **身份。** `agent_id` / `session_key` MUST 由 Git `git-common-dir` 派生
   （`ndf-<slug>-<hash>` / `agent:<agent_id>:main`）。同仓 worktree MUST 得到相同
   agent；不同仓库 MUST 不同。
3. **Provision。** `ndf_role_binding.py bind|provision-openclaw-session` MUST 幂等
   调用 `openclaw agents add <agent_id> --non-interactive --workspace <primary>`；
   agent 已存在但 workspace 冲突 MUST fail-closed
   （`openclaw_agent_workspace_collision`）。
4. **Fail-closed。** 共享默认 `agent:main:main`、复制来的 stale managed 绑定、
   未验证的自定义 key MUST NOT `safe_to_dispatch` /
   MUST NOT `dispatch-send`（`openclaw_session_legacy_shared` /
   `openclaw_session_collision_or_stale_binding` /
   `openclaw_session_ownership_unverified`）。自定义 key 升级 MUST 显式
   `--rebind-openclaw-session`。
5. **派发。** Pack MUST 携带 `agent_id` + `session_key`；运输 MUST 使用该
   `agentId`。本条不开放单项目多 topic OpenClaw 并发。同项目 Control 与
   Implementation 皆走 OpenClaw 时的**角色分 session**见 [[META-022]]。

> rationale: 共用 `agent:main:main` 时 per-hop `sessions.reset` 会跨项目互冲；
> 独立 agent 隔离网关会话，NDF lease/completion 本就按仓隔离。

## OpenClaw 按角色分 session（Control ≠ Implementation） {#META-022}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.2.2 source=stated scope=ndf-process -->
<!-- ndf: depends-on=META-011,META-017,META-020 -->

当 Control 与 Implementation **都**绑定 OpenClaw 运输时，项目 MUST 绑定两套
managed 身份；MUST NOT 让 Implementation pack 复用 `roles.control.session_key`。

1. **SoT。** Control 继续写在 `roles.control.{agent_id,session_key,…}`
   （[[META-020]]）。Implementation MUST 写入
   `roles.implementation.{agent_id,session_key,session_transport,session_binding_version}`。
2. **身份。** 均由同一 `git-common-dir` 派生；Implementation MUST 带角色后缀：
   Control `ndf-<slug>-<hash>` / `agent:…:main`；Implementation
   `ndf-<slug>-<hash>-impl` / `agent:…-impl:main`。同仓 worktree MUST 同双身份；
   不同仓库 MUST 不同。两角色 `session_key` MUST 字面不同。
3. **Provision。** `bind` / `provision-openclaw-session` MUST 幂等为两角色各
   `agents add`（允许同 workspace 上的配对 agent）；冲突 MUST fail-closed。
4. **派发。** Pack / `dispatch-send` MUST 按 mapped role（task 优先）戳对应角色
   session。Implementation 复用 Control `session_key` MUST NOT
   `safe_to_dispatch` / MUST NOT `dispatch-send`
   （`openclaw_role_session_collapsed`）。OpenClaw 失败时 MUST NOT 静默塌到
   in-host（[[META-017]]）。
5. **并发。** 不开放单角色多 topic OpenClaw 并发；跨项目隔离仍以 [[META-020]] 为准。

> rationale: 同仓共用一条 session 时 Control 上下文与 sticky model 会污染
> Implementation hop；分 session 隔离角色而不放松跨项目边界。

## 人类可理解、可改依赖的 NDF 面 {#META-023}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.2.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-012,ADR-META-004,META-011 depends-on=META-001,META-002,META-008,META-011,META-012,ADR-META-004 -->

NDF 三栖纪律（树 / 图 / git）对人可见：人 MUST 能维护条款边、阅读 Compiler 编出的
packed 闭包，并在派发前用 overlay 修订依赖路径。五句口令是 SHOULD 快捷入口，
MUST NOT 写成「人只能说这五句」。MUST NOT 复活 Commander / Episode / Replay /
Canvas；写根、bundle SHA、磁盘 completion 等机械安全门仍有效（[[META-011]]）。

### A. 定义面（条款图）

1. 人 MAY 直接编辑树中 `{#ID}` 旁的 `<!-- ndf: depends-on=… -->` / `refines=…`；
   改完 MUST 跑 `ndf_index.py index` 与 `ndf_graphcheck.py`（`--meta` 或 `--product`
   按触达面）。不经五句口令亦合法。
2. `spec/INDEX.md` / `spec/graph.json` 仍是索引投影，MUST NOT 升成条款 SoT。
3. Command 在提交 Idea、关闭计划、健康诊断时 MAY 用短表口头展示相关闭包
   （ID、边、为何进任务），MUST NOT 只报 SHA。短表 MUST NOT 冒充 pack-view 主文
   （人审主文见 [[META-024]]）。

### B. 观察 / 修订面（packed 上下文）

1. 每次可派发 pack MUST 另落一份人读投影（默认 `tmp/ndf-pack-view-*.md`）。
   **主文** MUST 是分层编译散文（[[META-024]]）；节点表、SHA、边列表属附录，
   MUST NOT 当人审主文。
2. promote / `promote_land` 投影 MUST 在前言额外含：draft→stable 清单、Trunk 写根、
   `Promotes:` 意图。禁止黑盒自定义 JSON 当作唯一依赖说明书。
3. 人 MAY 在派发前写 overlay（增/删 seed、临时 `depends-on`、排除节点）。
   Command MUST 再 compile + verify；MUST NOT 静默丢 overlay。再编后散文变化
   才算给人看懂。
4. Overlay MUST NOT 冒充条款 SoT；永久改图仍改树内 `depends-on`。
5. 人可用自然语言要求「看 packed 闭包」「从闭包排除某 ID 再编」等；Command
   MUST 映射到 compile / overlay / 派发。

### C. 文档分层

1. **人读定义**：`spec/meta/language.md`、图纪律、双轨；AGENTS / skill 入口须指向此。
2. **Agent 操作手册**：口令路由、pack CLI、委派细节；MUST NOT 冒充流程 SoT。
3. 内部 CLI 模块文件名仍不必让人选 skill；「对人类不可见」仅指不必选 skill/CLI
   子命令，不指图闭包与 packed 依赖路径（[[ADR-META-004]]）。

机械入口：`ndf_context.py pack-view|overlay-apply`（见 `spec/meta/tools/README.md`）。

> rationale: Compiler 从图编出任务闭包；人必须能看见并修订依赖路径，否则 meta
> 退化为仅 Agent 可操作的黑盒实例化流程。

## Compiler 分层编散文给人审 {#META-024}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.2.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-023,META-012 depends-on=META-001,META-003,META-008,META-012,META-023,BEH-025,ADR-META-004 -->

人与 NDF 文档的桥是 Context Compiler 的**人审文**：MUST 按 spec 目录层拼接闭包内
条款正文，再叠 POC 装订器切片，形成一篇可从头读到尾的 Markdown。图闭包只负责选句；
MUST NOT 以节点/边表冒充人审主文。MUST NOT 用模型另写摘要顶替条款正文。

### 编译管线

```text
图闭包选句 → 按 spec 目录编章（只含闭包命中条款） → 叠 poc/<topic>/ndf 切片 → 一篇 Markdown
```

1. Compiler MUST 只拼接已有 SoT（条款 body + 装订器 gate-slice）；`<!-- ndf: … -->`
   元数据行 MUST 剥掉；条款标题保留 `{#ID}`。每条编入主文的条款 MUST 紧接标题给出
   **溯源一行**：源文件路径与行号、status、进包原因（种子及来源，或因哪条
   `depends-on` / `refines` 拉入）。装订器切片 MUST 标明路径与 slice id。
   MUST NOT 把 SHA 或边表当作这一行。
2. **产品 track** 章序（空层省略）：前言 → `00-charter` → `10-architecture` →
   `20-behavior` → `30-interfaces` → `40-constraints` → `50-verification` →
   `decisions` → POC 装订 → 附录。跨平面 `spec/meta/**` 条款 MUST NOT 灌进主文正文，
   MAY 在附录列标题。
3. **process track**：`meta/language` → `meta/process` → 其余命中 meta 文件 →
   `meta/open` 本提案；跨平面产品条款同样只进附录标题。
4. POC 叠加读序对齐 [[BEH-025]]，内容对齐 [[META-010]] 切片：TOPIC=`topic_contract`、
   DESIGN=`design_contract`、PERF=`perf_bind`（非测量 task 消毒 Numbers）、
   DELTA=`delta_hypothesis`、INTERFACE=`interface_contract`。GATES/COMMITS/evidence
   MUST NOT 整文件倾倒进主文。无 slice 标记时 MAY 退回「第一个 `##` 到文末」并注明。
5. 前言 MUST 用短人话写：任务、写根、种子标题、截断说明；MUST NOT 把 SHA 当主文。
6. 附录 MAY 含节点表、SHA、truncated 原值、blockers、跨平面 ID；Command 口头汇报
   MUST 指向主文，MUST NOT 只念附录。
7. schema：`ndf-pack-view/v2`。机械入口同 [[META-023]]：`pack-view` / `overlay-apply`。

> rationale: 树里已是散文；Compiler 的人读职责是按目录层选句拼接，不是把图投影
> 给人当契约。

## 人审对象与热路径 {#META-025}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.2.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-010,META-011,META-014,META-023,META-024,BEH-025,ADR-META-004 depends-on=META-010,META-011,META-012,META-014,META-019,META-023,META-024,BEH-025,ADR-META-003,ADR-META-004 -->

人审闸 MUST 审内容文件，MUST NOT 审 Agent 回执 JSON 或「文件是否已落盘」。
草稿 MUST 先写入 open 提案路径再请人确认。

### 人审对象

| 阶段 | 人打开并审的文件 | 人回复 | 之后才做 |
|------|------------------|--------|----------|
| 提案 | `spec/open/proposal-*.md` 或 `spec/meta/open/proposal-meta-*.md` | **已确认** | process：落地。poc：写装订器 |
| 装订器（仅 poc） | `poc/<topic>/ndf/` 契约 markdown | **已审核** | 写 `bundle_dispatch` + 造 pack + pack-view |
| 将派契约 | `tmp/ndf-pack-view-*.md`（[[META-024]]） | **派发** | 开租约 worktree，再 send |

指挥面口头汇报 MUST 指向上表路径。磁盘 `ndf-agent-completion/v1` 仍是 hop 成功
信号（[[META-011]]），只给指挥面收口。

### 提案只确认一次

1. 产品与 process 提案的内容闸均为「已确认」（`proposal.confirmed`）。
   MUST NOT 再要求人对同一提案回复「已审核」。
2. process：`已确认` 授权 `confirm_land`；落地成功后生命周期到 `reviewed`。
   MUST NOT 再造必经的 `proposal.reviewed`。
3. 产品 poc：`已确认` 之后 MUST 立刻写齐装订器；MUST NOT 插一节提案「已审核」。
4. 「已审核」留给 POC 装订器 markdown。文件存在仍 MUST NOT 推导为已确认。

### 编译与送出分跳

1. 造 pack 与 `dispatch-send` / `poc-dispatch --send` MUST NOT 在同一跳默认完成。
2. 人审散文与 worker JSON MUST 同源（同一 `compile_plan` / `plan_sha`）。
3. 本 hop 若无 `tmp/ndf-pack-view-*.md`（schema `ndf-pack-view/v2`），POC
   `--send` / Implementation `dispatch-send` MUST fail-closed
   （`human_pack_view_missing`）。process `confirm_land` 不走此门。
4. **「派发」= 开租约 + 送出。** MUST NOT 在展示散文之前或人未回复「派发」之前
   创建 Implementation 租约。`poc-dispatch` 未 `--send` MUST NOT 建租约。

> rationale: 人看见提案时它已在磁盘上；第二闸「审核是否写入」与 JSON 回执都不是
> 人能判断的内容。租约必须等契约散文看完再开。

## OpenEvolve 作为 POC 合同内搜索 {#META-026}
<!-- ndf: kind=req level=must layer=L1 status=stable since=1.2.4 source=stated scope=ndf-process -->
<!-- ndf: refines=BEH-018,BEH-025,META-011,META-012,META-024,META-025 depends-on=BEH-018,BEH-025,CON-POC-001,META-011,META-012,META-019,META-024,META-025,ADR-META-003,ADR-META-004 -->

OpenEvolve 是「派发」后 Implementation 在 `poc/<topic>/` 内的**可选、默认关闭**
搜索执行器，不是第四角色、第六句口令、或 `roles.*.adapter`。未在装订器
`design_contract` 写 `openevolve.enabled: true` 的 topic MUST 走普通
`implement|measure`，MUST NOT 调用 OpenEvolve。启用时 MUST 在同一审查切片写明
搜索空间（演化哪些文件/什么实现细节 vs 冻结政策），并继续
`poc-dispatch --intent implement|measure --send`；成功只认磁盘
`ndf-agent-completion/v1`（[[META-011]]）。

### 合同与约束分层

1. 缺省关闭。仅当装订器 `design_contract` 与 topic `evolution.yaml` 均为
   `enabled: true` 时 Implementation 才调用 OpenEvolve；缺任一项视为关闭。
2. 启用时 MUST 在同一审查切片用表写明搜索空间：演化哪些文件、什么实现细节 vs
   冻结政策。机器合同（allowlist、seed、预算、sandbox、evaluator）MUST 写在
   装订器审查切片（DESIGN / PERF / INTERFACE YAML）；**不**新增 `EVOLUTION.md`。
3. 人「已审核」+ `bundle_dispatch` SHA 锁定合同；实质 amend 审查切片 MUST
   作废该闸并重审（[[META-010]] / [[META-025]]）。
4. 一次 OpenEvolve run = 一个 DELTA Round，不是每一代人审。
5. Topic runner MUST 复用 `compile_plan` 图闭包派生 `constraints.md` /
   `constraints.json`。自然语言 MUST 进 prompt（`prompt_only`）；路径 /
   测试 / 阈值 / 受保护哈希进 evaluator 硬门。缺可执行映射的 MUST MUST
   标 `prompt_only`；completion MUST NOT 宣称「规范已全部强制执行」。
6. MUST NOT 演化 `spec/`、Trunk `src/`/`include/`/`tests/`、evaluator 或
   prompt（[[BEH-018]] / [[CON-POC-001]]）。

### 隔离、写回、LLM 配置

1. 候选 MUST 在临时工作区物化；MUST NOT 直接写真实 `poc/<topic>/`。
   Parser fail-closed（相对路径、allowlist、拒 `..`/绝对路径/symlink/binary）。
2. Evaluator MUST 显式算 `combined_score`。仅 timeout MUST NOT 算沙箱。
3. Winner 写回限 allowlist 代码 + 可变面；promote MUST 只收复核后的 winner
   diff，MUST NOT 合入种群 DB（[[BEH-019]]）。
4. LLM `api_key` / `api_base` / 模型 MUST 读宿主
   `$XDG_CONFIG_HOME/openevolve/config.yaml`（未设 XDG 则为
   `$HOME/.config/openevolve/config.yaml`）；覆盖 `OPENEVOLVE_CONFIG`。
   缺文件 fail-closed。MUST NOT 把密钥或端点写入 `poc/<topic>/`、装订器
   或 git。Evidence MAY 记配置路径与非密钥字段。

> rationale: NDF 锁合同与审计；OpenEvolve 只在合同内搜索。原生单文件入口由
> topic 基因组适配补上；LLM 凭据由人在宿主统一配置里把控。

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
→ reviewed
```

`已确认`（`proposal.confirmed`）授权 `confirm_land`。落地成功后 MUST 进入
`reviewed`（[[META-025]]）。MUST NOT 再要求 `proposal.reviewed` / 「已审核」
作为 process 提案必经闸。旧提案若已有 `proposal.reviewed` 回执，仍视为终态。

`rejected` / `superseded` 为终态；archive 只是存储位置。旧
`Status: Implemented on ...` 与审核标记只作兼容输入；缺现代回执时 MUST 标
`legacy_*_unbound`，不得自动完成 gate 或产生可写 hop。

### 人工回执

`proposal.confirmed` MUST 是 append-only 结构化回执，并至少绑定：

```text
proposal_id | phrase | actor | approved_at | proposal_sha | status
```

actor MUST 为 Human，phrase 为精确口令 `已确认`（[[META-010]]）。
`proposal.reviewed` / 「已审核」对 process 提案不再是必经闸（[[META-025]]）；
若历史回执存在，MUST NOT 改写。Agent acknowledged、文件存在 MUST NOT
推进生命周期。proposal 内容漂移后，下游回执 MUST append `invalidated`，
不得改写历史。

落地（confirm_land）MUST 仅写入提案声明的 `land_targets`（通常 `spec/meta/**` 与
产品 thin 指针）；MUST NOT 静默改产品实现树。指挥面落地后 MUST 指向已改的
条款路径，MUST NOT 甩 JSON 请人「审核是否写入」。

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

**文字优先主路径**（[[ADR-META-003]] / [[META-025]]）：产品提案「已确认」后，OpenClaw
MAY **一次写齐** TOPIC / DESIGN / PERF_BASELINE / DELTA / INTERFACE（及测试计划）。
Human 审这些 markdown 并回「已审核」后，Command 才写 `bundle_dispatch` 并造 pack /
pack-view。Human「派发」授权开租约并实现/测量。仅实质 amend 假设、接口、测量协议
或写入边界后，下一次装订器审核才绑定新 SHA；Numbers / Rounds / evidence 追加
MUST NOT 触发重审。

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