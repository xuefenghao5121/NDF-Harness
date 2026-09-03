# Process Proposal — Compiler 分层编散文给人审

> track: process
> status: Implemented on 2026-08-31；已审核
> reviewed: 已审核
> scope: ndf-process
> idea_plane: process
> refines: META-023, META-012
> depends-on: META-001, META-003, META-008, META-012, META-023, BEH-025, ADR-META-004
> proposal-id: meta-compiler-layered-prose
> flow-id: meta-compiler-layered-prose
> control-flow: managed
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_context.py, spec/meta/tools/README.md, spec/meta/tools/test_meta023_pack_view.py, AGENTS.md, .cursor/skills/ndf-workflow/SKILL.md, .cursor/skills/ndf-workflow/OVERVIEW.md

Status: Implemented on 2026-08-31；已审核

## 问题

[[META-023]] 把「人可见 packed 上下文」落成了 **节点表**：ID、depends-on、why=seed/closure、
plan_sha。人审 dump 时理解成本过高——审的是图投影，不是契约。

这与三栖纪律反了。树里已经是散文（[[META-001]]）；Compiler（[[META-012]]）的职责是
**按 spec 层抽出本次闭包里的条款正文，再叠 POC 装订器**，编成一份人能从头读到尾的
文章。图闭包仍是内部选句机器，MUST NOT 冒充人审面。

当前反例：`tmp/ndf-pack-view-demo.md` 只有 Identity / Seeds / Graph closure 表。

## 提案 {#META-024}

<!-- ndf: kind=req level=must layer=L1 status=draft since=1.2.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-023,META-012 depends-on=META-001,META-003,META-008,META-012,META-023,BEH-025,ADR-META-004 -->

人审面 MUST 是 **分层编译散文**，MUST NOT 以节点/边表作为主文。

### 编译管线（机械，禁止另写新文）

Compiler MUST 只拼接已有 SoT 正文（条款 body + 装订器切片），MUST NOT 用模型另写摘要顶替条款。
`<!-- ndf: … -->` 是图边，人审文 MUST 剥掉；条款标题保留 `{#ID}` 以便对照 overlay。

```text
图闭包选句
  → 按 spec 目录层编章（只含闭包命中的条款正文）
  → 叠加 poc/<topic>/ndf 装订器（[[BEH-025]] 读序）
  → 一篇 Markdown
```

**产品 track** 章序（空层省略）：

1. 任务前言（一段话：这次做什么、可写/禁写目录；禁止把 SHA 当主文）
2. `spec/00-charter/`
3. `spec/10-architecture/`
4. `spec/20-behavior/`
5. `spec/30-interfaces/`
6. `spec/40-constraints/`（含 sla）
7. `spec/50-verification/`
8. `spec/decisions/`（闭包命中的 DEC）
9. **叠加** `poc/<topic>/ndf/`：TOPIC → DESIGN → PERF_BASELINE（非测量 task 仍消毒 Numbers）→ DELTA → INTERFACE；GATES/COMMITS/evidence 只在与本次 hop 相关时短引，MUST NOT 整文件倾倒
10. 附录（MAY）：节点表、截断、blockers、SHA——机器校对用，默认折叠/文末，MUST NOT 当人审主文

**process track**：用 `spec/meta/` 的 language → process → 相关 ADR，再叠 `spec/meta/open/` 本提案；无 topic 则无 POC 章。

截断 MUST 写成人话（「架构章未编入 N 条，因 depth 预算」），MUST NOT 只写 `truncated: depth`。

### 与 META-023 的关系

- 定义面（人改树内 `depends-on`）不变。
- overlay 仍改闭包选句；再 compile 后 **散文变了** 才算给人看懂。
- META-023 B「人读投影最少含节点+边」改为：那些字段属附录；主文是分层散文。
- 五句口令 / 不复活面板不变。

### 人审时看什么

人读前言 + 各 spec 章 + 装订器叠加，判断：这次 AI 将遵守的契约是否就是我想派的那份。
每条标题下的 `> 源：` 用来定位原文与进包原因。要拿掉一条：说「把 ARCH-FFT-009 拿掉再编」，Command 走 overlay，人再读新散文。

## 落地清单

- [x] `process.md` 新增 [[META-024]]；薄注 [[META-023]] B：主文=散文，表=附录
- [x] `ndf_context.py pack-view`：按层 stitch 条款 body + binder；现有节点表移附录
- [x] 测试：产品 topic dump 含 Charter/Architecture 标题与条款正文，且主文无 Graph closure 表
- [x] 主文条款标题下溯源行（`path:line` · status · 进包原因）；装订器标 slice id
- [x] skill / AGENTS：人审对象改为「分层散文」，禁止把节点表当给人口头汇报

## 明确不做

- 不让 LLM 改写/摘要条款来「更好读」
- 不把 `graph.json` 升成 SoT
- 不复活 Commander / Episode / Replay
- 不在本条接线 `poc-dispatch` 自动落文件（可 follow-up；本合同先钉人审形态）

## 验收

1. 对有 topic 的 pack-view，人打开主文能按 00→50→poc/ndf 读完相关契约，无需先学边类型。
2. 每条条款能从标题下溯源行定位到源文件行号与进包原因。
3. 节点表若存在，只在附录。
4. `ndf_graphcheck.py --meta` hard_errors=0。

## Control receipts

| event | phrase | actor | approved_at | proposal_id | flow_id | hop | proposal_sha | status |
|-------|--------|-------|-------------|-------------|---------|-----|--------------|--------|
| proposal.confirmed | 已确认 | Human | 2026-08-31T11:35:00Z | meta-compiler-layered-prose | meta-compiler-layered-prose | confirm_land | 08a927d3dec65cbf375de145d1b5fc6dffccbab942adc41b4a3c5dc8d4c3f1c5 | valid |
| proposal.reviewed | 已审核 | Human | 2026-08-31T12:11:09Z | meta-compiler-layered-prose | meta-compiler-layered-prose | review | 08a927d3dec65cbf375de145d1b5fc6dffccbab942adc41b4a3c5dc8d4c3f1c5 | valid |
