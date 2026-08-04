# ADR: NDF 元规范与产品契约分层 {#ADR-META-001}

> 日期: 2026-08-04  
> 状态: Accepted（seed）  
> track: process

## Context

双轨、POC 边界、装订与卫生若与产品行为条款混排，易被误读为产品 must。

## Decision

1. `spec/meta/` 为 **NDF process profile**（流程 SoT；非产品行为 SoT）。  
2. 产品行为契约在 `spec/00–50`；产品树对 process 条款仅 **adopted 薄指针**。  
3. process 提案 → `spec/meta/open/proposal-meta-*.md`；产品提案 → `spec/open/`。  
4. 卫生/双轨/装订 ADR → `spec/meta/decisions/`；产品 DEC → `spec/decisions/`。  
5. 指挥面以仓库根 `AGENTS.md` 为跨运行时工作流入口。

## Consequences

- INDEX 可分组 META vs product。  
- 实现 Agent 默认禁止改写 `spec/meta/`（除非 track=process 且人工确认）。  
- 纯 process ID MUST NOT 写入产品 adopted 表。
