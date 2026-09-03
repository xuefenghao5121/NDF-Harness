# Process Proposal — 人类可理解、可改依赖的 NDF 面

> track: process
> status: Implemented on 2026-08-31；已审核
> reviewed: 已审核
> scope: ndf-process
> idea_plane: process
> refines: META-012, ADR-META-004, META-011
> depends-on: META-001, META-002, META-008, META-011, META-012, ADR-META-004
> proposal-id: meta-human-ndf-surfaces
> flow-id: meta-human-ndf-surfaces
> control-flow: managed
> land-targets: spec/meta/process.md, spec/meta/decisions/adr-meta-control-retirement.md, AGENTS.md, .cursor/skills/ndf-workflow/SKILL.md, .cursor/skills/ndf-workflow/OVERVIEW.md, spec/meta/tools/ndf_context.py, spec/meta/tools/README.md, spec/meta/README.md

Status: Implemented on 2026-08-31；已审核

## 问题

[[ADR-META-004]] 把人的注意力收成五句口令，并把 Context Compiler / 内部模块标成
「对人不可见」。实践中 meta 文档与 skill 越来越像 **Agent 操作手册**，人失去：

1. **定义面**：直接维护条款图（`depends-on` / `refines`）而不必经口令仪式；
2. **观察面**：阅读 Compiler 编出的 packed 闭包（含 promote），理解 AI 工作依赖路径；
3. **修订面**：在派发前用 overlay 增删 seed / 临时边，再 compile。

这与 NDF 三栖纪律冲突（树=人写散文、图=人声明边、git=时间；[[META-001]] /
[[META-002]] / [[META-008]]）。Compiler（[[META-012]]）本应从图编出一次任务闭包，
不是把定义面藏进 Agent pack。

**不复活** Commander / Episode / Replay / Canvas。写根、bundle SHA、磁盘 completion
等机械安全门保留。

## 提案 {#META-023}

<!-- ndf: kind=req level=must layer=L1 status=draft since=1.2.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-012,ADR-META-004,META-011 depends-on=META-001,META-002,META-008,META-011,META-012,ADR-META-004 -->

### A. 定义面（条款图）

1. 人 MAY 直接编辑树中 `{#ID}` 旁的 `<!-- ndf: depends-on=… -->` / `refines=…`；
   改完 MUST 跑 `ndf_index.py index` 与 `ndf_graphcheck.py`（`--meta` 或 `--product`
   按触达面）。不经五句口令亦合法。
2. `spec/INDEX.md` / `spec/graph.json` 仍是索引投影，MUST NOT 升成条款 SoT。
3. Command 在提交 Idea、关闭计划、健康诊断时 MUST 用**短表**展示当前相关闭包
   （ID、边、为何进任务），MUST NOT 只报 SHA。

### B. 观察 / 修订面（packed 上下文）

1. 每次可派发 pack MUST 另落一份**人读投影**（默认 `tmp/ndf-pack-view-*.md`，
   gitignore）。最少含：task / hop / track / topic / write roots；seed 条款；
   图闭包（节点+边）；ordered_reads；截断 / conflicts / blockers。
2. promote / `promote_land` 投影 MUST 额外含：draft→stable 清单、Trunk 写根、
   `Promotes:` 意图。禁止黑盒自定义 JSON 当作唯一依赖说明书。
3. 人 MAY 在派发前写 **overlay**（增/删 seed、临时 `depends-on`、排除节点）。
   Command MUST 再 compile + verify；MUST NOT 静默丢 overlay。
4. Overlay MUST NOT 冒充条款 SoT；永久改图仍改树内 `depends-on`。
5. 五句口令是 SHOULD 快捷入口，MUST NOT 写成「人只能说这五句」。人可用自然语言
   要求「看 packed 闭包」「从闭包排除某 ID 再编」等；Command 映射到 compile /
   overlay / 派发。

### C. 文档分层

1. **人读定义**：`spec/meta/language.md`、图纪律、双轨；AGENTS / skill 入口须指向此。
2. **Agent 操作手册**：口令路由、pack CLI、委派细节；MUST NOT 冒充流程 SoT。
3. 内部 CLI **模块文件名**仍不必让人选 skill（保留 ADR-META-004 减法）；图闭包与
   packed 上下文对人可见。

### 对 ADR-META-004 的薄修订

不推翻「少则得 / 无面板义务」。第 4 点改为：唯一文字入口 skill 仍编排口令快捷路径；
**图闭包与 packed 上下文对人可见、可修订**；「内部模块对人类不可见」仅指不必选
skill/CLI 子命令，不指依赖路径。

[[META-011]] 指挥面：从「五句口令」改为「口令快捷 + 图/pack 观察面」。

## 落地清单

- [x] `spec/meta/process.md`：新增 [[META-023]]；索引补号；薄修 [[META-011]] / [[META-012]]
- [x] `spec/meta/decisions/adr-meta-control-retirement.md`：第 4 点薄订
- [x] `AGENTS.md`、`.cursor/skills/ndf-workflow/{SKILL,OVERVIEW}.md`：人读 vs Agent 操作
- [x] `ndf_context.py`：`pack-view`（人读 dump）+ `overlay-apply`（再 compile）；`tools/README.md`
- [x] `spec/meta/README.md`：指针

## 明确不做

- 不恢复 Commander / Episode / Replay / Canvas
- 不强制人学 CLI 子命令（口令仍可用）
- 不把 `graph.json` 升成 SoT
- 不把 overlay 写成永久条款边
- promote 一等 pack CLI 可另案；本条只钉合同与人读投影

## 验收

1. `ndf_graphcheck.py --meta` hard_errors=0（含 META-023）。
2. `ndf_context.py pack-view …` 写出可读 Markdown；overlay 后再编闭包变化可见。
3. AGENTS / skill 不再写「内部模块对人类不可见」而无图/pack 观察例外。

## Control receipts

| event | phrase | actor | approved_at | proposal_id | flow_id | hop | proposal_sha | status |
|-------|--------|-------|-------------|-------------|---------|-----|--------------|--------|
| proposal.confirmed | 已确认 | Human | 2026-08-31T11:06:00Z | meta-human-ndf-surfaces | meta-human-ndf-surfaces | confirm_land | abc5dda0994cfcbf994d47831e6556818d77b4b6d2387296febce9445c55911f | valid |
| proposal.reviewed | 已审核 | Human | 2026-08-31T12:11:09Z | meta-human-ndf-surfaces | meta-human-ndf-surfaces | review | abc5dda0994cfcbf994d47831e6556818d77b4b6d2387296febce9445c55911f | valid |
