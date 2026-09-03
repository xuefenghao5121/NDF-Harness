# Process Proposal — OpenEvolve 作为 POC 合同内搜索执行器

> track: process
> status: Implemented on 2026-09-01
> scope: ndf-process
> idea_plane: process
> refines: BEH-018, BEH-025, META-011, META-012, META-024, META-025
> depends-on: BEH-018, BEH-025, CON-POC-001, META-011, META-012, META-019, META-024, META-025, ADR-META-003, ADR-META-004
> proposal-id: meta-openevolve-poc-search
> flow-id: meta-openevolve-poc-search
> control-flow: managed
> land-targets: spec/meta/process.md, AGENTS.md, .cursor/skills/ndf-workflow/poc.md, .cursor/skills/ndf-workflow/close.md, spec/meta/templates/poc/DESIGN.md.stub
> related-product: spec/open/proposal-jit-twiddle-imm-lut-openevolve-r1.md

Status: Implemented on 2026-09-01（[[META-014]] reviewed；落地回执见 `spec/meta/.ndf-completion/ndf_improvement_land-confirm_land-attempt.json`）

## 问题

POC Implementation hop 常以单次手写/测量收敛；对多文件、多旋钮的搜索空间，缺少**合同内**、可审计、可复现的搜索执行器。OpenEvolve 可提供 MAP-Elites / LLM 变异搜索，但：

1. 原生入口是单 `initial_program`；多文件、写根、越界校验须 NDF wrapper 补上。
2. OpenEvolve v0.3.2 的 `EVOLVE-BLOCK` **只进 prompt**，生成后无强制越界校验。
3. 不能把整本 `spec/` 塞进 prompt 就宣称「按 NDF 规范演化」；MUST 分层：人审 bundle → 图闭包 → prompt 引导 → evaluator 硬门。
4. MUST NOT 新增第四角色、第六句口令、或 `roles.*.adapter=openevolve`（试点阶段）。

设计参考（非 SoT）：`docs/NDF_OpenEvolve_POC.md`（维护者本地）；集成基线 OpenEvolve **v0.3.2** / commit `411fb59`。

## 提案 {#META-026}

<!-- ndf: kind=req level=must layer=L1 status=draft since=1.2.4 source=stated scope=ndf-process -->
<!-- ndf: refines=BEH-018,BEH-025,META-011,META-012,META-024,META-025 depends-on=BEH-018,BEH-025,CON-POC-001,META-011,META-012,META-019,META-024,META-025,ADR-META-003,ADR-META-004 -->

### A. 角色与口令不变

1. 保留现有五句口令（[[META-025]] / [[ADR-META-004]]）。OpenEvolve **只改变**「派发」后
   Implementation **如何**在 `poc/<topic>/` 内找代码，不改变 Command / Control /
   Implementation 三层划分。
2. MUST NOT 新增 `intent=evolve`、第四 Agent、`provider=openevolve`、或
   `roles.implementation.adapter=openevolve`（试点阶段；两 topic 试点同构后再评估
   `ndf_openevolve_run.py` 提炼）。
3. 试点 MUST 继续使用 `poc-dispatch --intent implement|measure --send` 与磁盘
   `ndf-agent-completion/v1` 成功合同（[[META-011]]）。

### B. 合同锁搜索（bundle + 装订器）

1. 搜索空间（多文件 allowlist、seed、预算、sandbox 命令、checkpoint 策略）MUST
   写在 POC 装订器审查切片内（DESIGN `design_contract` YAML block、PERF `perf_bind`
   evaluator 绑定、INTERFACE 不变量）；**不**新增 `EVOLUTION.md` facet（试点）。
2. 人「已审核」+ Command `bundle_dispatch` SHA 锁定搜索合同；实质 amend 合同切片
   MUST 作废 `bundle_dispatch` 并重审（[[META-025]] / [[META-010]]）。
3. 一次 OpenEvolve run = 一个 DELTA Round；**不是**每一代对应人审。合同 SHA 未变时
   「继续」MAY 续 checkpoint；evaluator / allowlist / 相关 NDF 条款变化后 MUST 新
   Round，旧 checkpoint MUST NOT 续跑。

### C. 规范当约束（两层，禁止假装全强制）

1. Topic wrapper MUST 复用 Context Compiler（[[META-012]] `compile_plan`）的
   `ordered_reads`、`seed_ids`、图闭包、`manifest_sha` / `plan_sha`，派生
   `constraints.md` + `constraints.json`（源路径、条款 ID、正文 SHA、bundle SHA）。
2. **Prompt 层**：相关 NDF 条款自然语言 MUST/MUST NOT 进入固定 system prompt，仅作
   搜索引导。
3. **Evaluator 硬门**：路径 allowlist、接口/正确性测试、性能阈值、受保护文件区域
   哈希 MUST 在 evaluator 第一阶段拒绝越界候选。缺少可执行映射的 MUST MUST 标
   `prompt_only`；completion MUST NOT 宣称「规范已全部强制执行」。
4. MUST NOT 演化 NDF 规范、`spec/`、Trunk `src/`/`include/`/`tests/`、evaluator
   或 prompt 本身（[[BEH-018]] / [[CON-POC-001]]）。

### D. 多文件基因组与隔离执行

1. Allowlist 内文本文件编码为规范化 multi-file genome；OpenEvolve 仍见单
   `initial_program`，展开由 wrapper 实现。
2. 每个候选 MUST 在**全新临时工作区**物化；MUST NOT 直接写真实 `poc/<topic>/`。
3. Parser fail-closed：仅相对路径、命中 allowlist、拒绝 `..`/绝对路径/symlink/
   binary/重复路径/超限；未列文件从 baseline 只读复制。
4. Evaluator cascade：stage1 解析/越界/编译；stage2 正确性与接口；stage3 性能与
   `combined_score`（显式计算；feature dimensions 仅 MAP-Elites 分箱，非 Pareto）。
5. 只配置两个有效晋级阈值（stage1→2、stage2→3）。OpenEvolve 无 CPU/内存限制时
   runner MUST 要求外部 Docker/沙箱命令；仅 timeout MUST NOT 算作安全隔离。

### E. Winner 写回与 promote

1. Winner MUST 先以候选 diff 形式输出；wrapper 重算 metrics 并复核 SHA 后才写回
   `poc/<topic>/`。
2. 写回 MUST 限 allowlist 代码 + 可变面（Numbers / Rounds / evidence / COMMITS /
   topic runtime headers）；审查切片（TOPIC/DESIGN/INTERFACE 合同段）MUST 保持冻结，
   除非人显式 amend。
3. OpenEvolve run/checkpoint/lineage 进 `poc/<topic>/ndf/evidence/openevolve/<run-id>/`；
   大型 population DB 默认 topic 私有忽略目录或外部制品库；证据记 URI + SHA。
4. `ndf_close.py` promote MUST 只接受复核后的 winner diff；MUST NOT 把种群 DB 合入
   Trunk（[[BEH-019]] / [[META-018]]）。

### F. LLM 配置在宿主本地，不进仓

OpenEvolve v0.3.2 **没有**内置全局配置发现。NDF 试点约定一份宿主统一文件，由人把控
密钥与模型，不按 topic 复制：

1. Implementation 调 OpenEvolve 时 MUST 读宿主 LLM 配置：
   `$XDG_CONFIG_HOME/openevolve/config.yaml`（`XDG_CONFIG_HOME` 未设则
   `$HOME/.config/openevolve/config.yaml`）。覆盖：环境变量 `OPENEVOLVE_CONFIG`
   指向另一 yaml。缺文件 → fail-closed，不得回落到 POC 内 yaml 或硬编码默认模型。
2. 该文件承载 `llm.api_key` / `llm.api_base` / `llm.primary_model`（及可选
   ensemble）。MUST NOT 写入 `poc/<topic>/`、装订器审查切片、`spec/`、git。
3. Topic 内 `evolution.yaml` 只锁搜索合同（allowlist、seed、evaluator、预算）；
   MUST NOT 再放一份 `openevolve_config.yaml` 复制 LLM 端点。
4. Evidence MAY 记录配置**路径**与非密钥字段（model / api_base）；MUST NOT 把
   `api_key` 抄进 `ndf/evidence/`。

### 不写

- 不把 OpenEvolve 做成 Command 口令或面板。
- 试点前不提炼 `ndf_openevolve_run.py` 到 Harness（须 ≥2 同构 topic 试点）。
- 不承诺远程 LLM 跨机器随机种子完全重放。

## 落地清单（确认后）

- [x] `spec/meta/process.md` 入 `{#META-026}` 正文 + 薄指针
- [x] `AGENTS.md` / `ndf-workflow/poc.md` / `close.md` 各一句
- [x] `templates/poc/DESIGN.md.stub` 可选 evolution YAML 注释块
- [ ] 试点 topic wrapper + 集成测试（假 runner，不依赖 API key）

## 依赖

- [[BEH-018]]、[[BEH-025]]、[[CON-POC-001]]、[[META-011]]…[[META-025]]、[[ADR-META-003]]、[[ADR-META-004]]
- 产品试点：[[proposal-jit-twiddle-imm-lut-openevolve-r1]]

## Control receipts

| event | phrase | actor | approved_at | proposal_id | flow_id | hop | proposal_sha | status |
|-------|--------|-------|-------------|-------------|---------|-----|--------------|--------|
| proposal.confirmed | 已确认 | Human | 2026-09-01T17:00:28Z | meta-openevolve-poc-search | meta-openevolve-poc-search | confirm_land | 441c12ab199fe948ee90e44a3e98f49314332a05d4d3760b43e8ab368c9fda6c | valid |
