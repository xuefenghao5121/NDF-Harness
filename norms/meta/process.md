# Meta Process — 探索轨 / 晋升 / 负结果 / 装订

> scope: ndf-process  
> 条款索引: `CHR-008`, `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`, `BEH-026`, `META-006`, `META-007`  
> 目录边界: [[ARCH-008]]；SLA 隔离: [[CON-POC-001]]  
> 术语: [[DEF-020]], [[DEF-021]], [[DEF-022]], [[DEF-023]], [[DEF-NDF-GRAPH]]  
> 缺陷分类: [[DEF-NDF-CYCLE]]…[[DEF-NDF-BINDER-DUAL-HEAD]]（见 `meta/glossary.md`）
> 性能线: [[META-006]], [[META-007]]（产品金标条款由消费仓自行定义）

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
   `spec/meta/open/proposal-meta-*.md`（见 `AGENTS.md` track=process）
2. MUST NOT 将探索期指标写入 `status=stable` 的产品 SLA / 性能约束 must 行
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
5. **装订器收口**：`TOPIC.md` status → `promoted`；`COMMITS.md` 记录一对
   `src_commit` + `spec_commit`；装订器迁入 `spec/archive/YYYY-MM/poc-<topic>/`
   或保留摘要指针（二选一，promote 提案写明）。若存在 `poc/<topic>/NOTES.md`，MUST
   将文件头 status 与 TOPIC 对齐为 `promoted`（日期/DEC/提案指针；见 [[BEH-025]]）。
   **partial** 且主题仍 exploring 时：NOTES SHOULD 标明 `partial` + TOPIC 仍 exploring，
   MUST NOT 写成全量关闭。
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

禁止：先合主线再补 stable 契约；或先写 stable must 再补 POC 证据。

## 金标更新义务 {#META-006}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.11 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-019 -->

每次 promote / bug / refactor 合入 Trunk `src/` 后，MUST：

1. 按**产品**金标约束（产品树现行金标条款）重跑其声明的标准配置矩阵，得到完整观测点集，
   每点至少 2 轮。
2. 在产品验证树写入**新**观测基线卡（`baselines/bl-trunk-golden-<shortsha>.md` 或项目约定等价路径）：
   - 新 Trunk SHA（`git rev-parse HEAD`）
   - 各点的吞吐 / 质量 / 变异指标（产品协议字段）
   - 列出所用配置身份（`cfg-*` 或等价 id）
   MUST NOT 原地偷改仍被 TOPIC `vs:` 引用的旧基线卡数字而不 bump id。
3. 如测量配置变更：在产品验证树的配置空间新增或 bump 配置身份，并薄更新产品金标条款指针。
4. 更新产品金标索引（thin 导航 → 现行基线卡 + 配置身份）。
5. MUST NOT 仅靠改写产品 stable SLA 正文中的观测/叙事数字冒充金标更新（合约下限 ≠ 观测线；
   见 [[META-007]]）。
6. 金标更新 commit MUST 引用触发的 promote/bug 提案（`Promotes:` / `Fixes:` trailer）。

**豁免**：纯文档变更（spec/ / README）、POC 目录内变更（poc/）不触发金标更新。

> rationale: 金标三要素落在产品验证树的可引用配置/基线身份；索引薄导航避免双份数字。
> 产品落点见验证树 `configs/` + `baselines/`（本仓 `spec/50-verification/`）。
> 提案: spec/meta/open/proposal-meta-perf-baseline-space.md

## 性能线读写义务 {#META-007}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.9.12 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-025,META-006,CON-POC-001 -->

Agent / 协作者在 POC 开题、写相对性能、委派压测前 MUST：

1. 读 `poc/<topic>/ndf/TOPIC.md` 的 `perf_baseline`（R0 后 MUST 存在）
2. 读该路径指向的性能线卡（通常 `ndf/PERF_BASELINE.md`）
3. 按卡内配置身份 / experimental Config、`Numbers`（或显式沿用的 `vs:` 基线卡）作对照

**SLA ≠ 性能线**：产品 stable SLA 是合约下限；观测金标与 POC R0 在产品验证树配置/基线空间
与主题 `PERF_BASELINE.md`。MUST NOT 从 SLA 正文抄观测表当 R0；MUST NOT 因配置-only 调参
改写 stable SLA 数字冒充新基线（[[CON-POC-001]]）。

**配置-only 变更**：MUST 选用或新增配置身份（或在主题卡 inline 全量测量配置），重测并更新
主题卡 / 必要时新基线卡；MUST NOT 静默改共用配置身份语义。

**stale**：`baseline_status=stale` 时 MUST 重测并更新主题卡与 `baseline_trunk_sha`，或
evidence 显式 `vs_trunk=<old>` 且 MUST NOT 当作现行 Trunk 基线叙事（[[BEH-025]]）。

校验/摘要：`python3 spec/meta/tools/ndf_perf_baseline.py show|check --topic <id>`
（流程装订门禁，与 bindcheck 同族；不含产品 SLA/吞吐业务逻辑）。

> rationale: 收口既有黄金意图到 Agent 必读路径；配置身份防止基线漂移。
> 提案: spec/meta/open/proposal-meta-perf-baseline-space.md

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
  PERF_BASELINE.md  # 性能线卡（R0 后 MUST；[[META-007]]）
  proposals/     # 本主题提案正文，或 stub 指回 spec/open/
  evidence/      # validation / 对照表
  COMMITS.md     # Commit Ledger [[DEF-023]]
```

### 呈现规则（唯一入口与阅读顺序）

- `poc/<topic>/ndf/` MUST 作为 POC 内唯一规范性呈现面；如存在 `poc/<topic>/README.md`，MUST NOT 作为 must 源（仅允许导航指针）。
- 协作者在 POC 内获取 NDF 的推荐阅读顺序 MUST 为：
  1. `poc/<topic>/ndf/TOPIC.md`
  2. `poc/<topic>/ndf/PERF_BASELINE.md`（若已 R0 / 已声明 `perf_baseline`；比性能 MUST 读）
  3. `poc/<topic>/ndf/proposals/`（或 stub → `spec/open/`）
  4. `poc/<topic>/ndf/evidence/`
  5. `poc/<topic>/ndf/COMMITS.md`

### TOPIC.md

MUST 记录至少：`topic_id`；`status` ∈ {`exploring`,`blocked`,`promoted`,`rejected`}；
`baseline_protocol`（测量口径指针，可与性能线卡 `protocol` 一致；**不是**数字源）；
`explore_surface`（逗号分隔短标签，开题 MUST；例：`fine-rerank` / `page-cache-l4` /
`pq-codes` / `mt-scaling`）；
`baseline_trunk_sha`（首次 R0 后 MUST：当时 Trunk `src` 短 SHA）；
`baseline_status` ∈ {`current`,`stale`,`n/a`}（R0 后默认 `current`；关闭主题可用 `n/a`）；
首次 R0 后 MUST 另有 **`perf_baseline`**（相对装订器路径，通常 `ndf/PERF_BASELINE.md`）；
比 Δ% / 压测对照 MUST 只读该卡（[[META-007]]），MUST NOT 从产品 SLA 正文抄观测表当 R0；
`proposals[]`（路径、Status、角色 root/amend/process-hygiene）；`draft_clauses[]`；
`active_hypothesis` / `next_gate`；可选 `depends_on_topics[]`；互斥时 MUST
`conflicts_with_topics[]`。

### PERF_BASELINE.md

主题内唯一性能线卡。头字段至少：`trunk_sha`（与 TOPIC `baseline_trunk_sha` 前缀一致）、
`config_id`（`cfg-*`）或标明 experimental、`protocol`、`status`；宜有 `vs:` 指向现行
`bl-trunk-golden-*`。正文 MUST 含 **Config** 与 **Numbers**（本主题 R0 表，或显式
「沿用 `baselines/<id>`」并链接）。模板：
`spec/50-verification/baselines/PERF_BASELINE.topic-template.md`。

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
  - MUST 新建装订器；首次 R0 后 MUST 写本主题 `baseline_trunk_sha`、
    `perf_baseline` → `PERF_BASELINE.md` 与 `baseline_status=current`
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
为准；装订器仅服务探索进度与可复现。

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