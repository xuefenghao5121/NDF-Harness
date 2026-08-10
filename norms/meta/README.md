# NDF Process Profile（种子）

> **role:** ndf-process-profile  
> **product_behavior:** false  
> **sot:** true（Agent **流程纪律**）；**false**（目标项目**产品行为**）

本目录是目标仓的 **process profile**：探索/晋升双轨、POC 边界、主题装订、规范卫生。  
**不是**产品行为契约树——产品条款写在 `spec/00–50`。

## 读序

| 角色 | 先读 |
|------|------|
| 指挥 | 仓库根 `AGENTS.md` → 本 README → [`language.md`](language.md) → [`process.md`](process.md) |
| 产品契约 | `../00-charter/`…`50-verification/` + 产品 `../open/` |
| 治理 | `tools/GOVERNANCE.md`（安装后）→ `tools/` |
| 探索 | `poc/<topic>/ndf/` |

## 本目录

| 文件 | 内容 |
|------|------|
| [`language.md`](language.md) | META-001…005（语言 / 语义核 / trunk-ref） |
| [`process.md`](process.md) | CHR-008, BEH-018…020, BEH-025/026, META-006/007 |
| [`architecture.md`](architecture.md) | ARCH-008 |
| [`constraints.md`](constraints.md) | CON-POC-001 |
| [`glossary.md`](glossary.md) | DEF-020…023, DEF-META-ID-NS, DEF-NDF-* |
| [`decisions/`](decisions/) | meta ADR（分层 / ID 命名空间 / 装订 / 卫生…） |
| `open/` | process 提案 `proposal-meta-*.md`（消费仓创建） |
| `tools/` | 审核 harness（从 VENDOR 取得实现） |
