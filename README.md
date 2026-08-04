# NDF Portable Harness

> **role:** ndf-process-package  
> **product_behavior:** false  
> **version:** see `VERSION`  
> **proposal:** `{#PROP-META-NDF-PORTABLE-HARNESS}`

可移植包：把 **NDF 规范**、**仓库级工作流（`AGENTS.md`）**、**治理 CLI** 装进任意工程。  
消费方包括 OpenClaw、Claude Code、OpenCode、Cursor 及其他能读仓库约定的 Agent——**不绑某一 IDE**。

## 装什么（P0）

| 目录 | 内容 |
|------|------|
| [`norms/`](norms/) | 条款格式 + process profile 种子 + 空产品树骨架 |
| [`workflow/AGENTS.md`](workflow/AGENTS.md) | 真实项目指挥工作流（跨运行时默认入口） |
| [`governance/`](governance/) | GOVERNANCE + 工具取得说明 + 日常命令卡 |
| [`skill/`](skill/) | init / adopt / govern / sync（**运行时无关**正文） |

P1：[`adapters/`](adapters/) 把同一 `skill/` 挂到各运行时。

## 快速开始

1. 读 [`docs/QUICKSTART.md`](docs/QUICKSTART.md)  
2. 选 profile（默认 `dual-track`，见 `ndf.profile.yaml`）  
3. 按 [`docs/INIT.md`](docs/INIT.md) 或让 Agent 执行 skill 模式 **init**  
4. 任选 [`adapters/<runtime>/`](adapters/) 挂载 skill  
5. 按 [`governance/docs/GOVERN.md`](governance/docs/GOVERN.md) 跑基线检查  

顺序：**规范 → AGENTS.md → 治理基线**。

## 非目标

- 不包含任何具体产品域契约 / SLA / 模块名  
- 不自动 apply advise 沙盒、不静默改 git  
- 不把某一运行时（如 Cursor）当作唯一入口  

## 本维护仓中的实现源

审核工具 Python 实现以维护仓 `spec/meta/tools/*.py` 为唯一源；本包见 [`governance/tools/VENDOR.md`](governance/tools/VENDOR.md)。

## Published repository

Canonical public tree for this package: https://github.com/xuefenghao5121/NDF-Harness
