# NDF Portable Harness

> **role:** ndf-process-package  
> **product_behavior:** false  
> **version:** see `VERSION`  
> **proposal:** `{#PROP-META-NDF-PORTABLE-HARNESS}`

可移植包：把 **NDF 规范**、**仓库级工作流（`AGENTS.md`）**、**治理 CLI** 装进任意工程。  
消费方包括 OpenClaw、Claude Code、OpenCode、Cursor 及其他能读仓库约定的 Agent——**不绑某一 IDE**。

**权威流向**：消费仓本地已验证实践 → 蒸馏进本包 → 再分发。禁止用本包反推纠正本地 SoT。

## 装什么（P0）

| 目录 | 内容 |
|------|------|
| [`norms/`](norms/) | 条款格式 + process profile 种子（含 META-006/007 性能线）+ 空产品树骨架 |
| [`workflow/AGENTS.md`](workflow/AGENTS.md) | 真实项目指挥工作流（跨运行时默认入口） |
| [`governance/`](governance/) | GOVERNANCE + **`tools/` 审核脚本**（`ndf_*.py`）+ 日常命令卡 |
| [`skill/`](skill/) | init / adopt / govern / sync（**运行时无关**正文） |
| [`templates/`](templates/) | TOPIC / PERF_BASELINE / COMMITS stubs + implementer boundaries |

P1：[`adapters/`](adapters/) 把同一 `skill/` 挂到各运行时。

## 快速开始

1. 读 [`docs/QUICKSTART.md`](docs/QUICKSTART.md)  
2. **先扫能力全景（可选）**：[`docs/WORKFLOW-FEATURES.md`](docs/WORKFLOW-FEATURES.md)  
3. 选 profile（默认 `dual-track`，见 `ndf.profile.yaml`）  
4. 按 [`docs/INIT.md`](docs/INIT.md) 或让 Agent 执行 skill 模式 **init**  
5. 任选 [`adapters/<runtime>/`](adapters/) 挂载 skill  
6. 按 [`governance/docs/GOVERN.md`](governance/docs/GOVERN.md) 跑基线检查  

顺序：**规范 → AGENTS.md → 治理基线**。

## 非目标

- 不包含任何具体产品域契约 / SLA / 模块名  
- 不自动 apply advise 沙盒、不静默改 git  
- 不把某一运行时（如 Cursor）当作唯一入口  

## 工具脚本

审核工具在 [`governance/tools/`](governance/tools/)：

| 脚本 | 职责 |
|------|------|
| `ndf_index` / `graphcheck` / `bindcheck` / `advise` / `close` | 索引 / 图 / 绑定 / 顾问 / 回合计划 |
| `ndf_report_io` | 报告路径门禁（默认 `tmp/`；禁写 `spec/`） |
| `ndf_poc_isolation` | POC 写入隔离（禁写 Trunk `src/include/tests`） |
| `ndf_perf_baseline` | 性能线装订（TOPIC→PERF_BASELINE；非 SLA 业务） |

安装到目标仓时复制到 `spec/meta/tools/`，见 [`governance/tools/VENDOR.md`](governance/tools/VENDOR.md)。

## 变更

见 [`CHANGELOG.md`](CHANGELOG.md)。
