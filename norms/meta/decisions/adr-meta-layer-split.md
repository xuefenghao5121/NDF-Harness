# ADR: NDF 元规范与产品契约分层 {#ADR-META-001}

> 日期: 2026-08-03
> 状态: Accepted
> 场景: process / 规范卫生
> track: process

## Context

双轨（[[CHR-008]] / [[BEH-018]]…）、POC 边界（[[ARCH-008]] / [[CON-POC-001]]）、
主题装订（[[BEH-025]]）与卫生 ADR 曾写在产品 `spec/00–50` 与 `spec/open/`，
与产品检索/SLA 叙事混排，易被误读为产品行为 must。

## Decision

1. 新增 `spec/meta/` 作为本仓 **NDF process profile**（流程 SoT；非产品行为 SoT）。
2. 上述条款 ID **不换号**，正文迁入 `meta/`；产品树仅 **adopted 薄指针**。
3. **process** 提案 → `spec/meta/open/proposal-meta-*.md`；产品提案仍 → `spec/open/`。
4. 卫生/双轨/装订 ADR → `spec/meta/decisions/`；产品域 DEC 仍在 `spec/decisions/`。
5. 指挥面同步：`AGENTS.md`、`skills/ndf-workflow`、`ndf-harness`、`.claude/CLAUDE.md`。

## Consequences

- INDEX 增加 META 分组；`ndf.yaml` 声明 `meta:`。
- Claude Code **禁止**改写 `spec/meta/`。
- 不强制本轮改写 upstream `normative_language`。
- **编号命名空间**（2026-08-05 起）：新建 process 条款见 [[ADR-META-002]] /
  [[DEF-META-ID-NS]]（`META-*` + 语义前缀；历史 CHR-008/BEH-018… 冻结不换号）。
  本 ADR §Decision.2「不换号」仅约束**已迁入**条款，不表示今后继续与产品共用数字续号。

## Migration table

| ID / 文件 | 原路径 | 新路径 |
|-----------|--------|--------|
| CHR-008, BEH-018..025 | charter / process.md | `meta/process.md` |
| ARCH-008 | modules.md | `meta/architecture.md` |
| CON-POC-001 | sla.md | `meta/constraints.md` |
| DEF-020..023 | glossary.md | `meta/glossary.md` |
| adr-ndf-hygiene, adr-poc-track | `decisions/` | `meta/decisions/` |
| proposal-poc-topic-binder | `open/` | `meta/open/` |
