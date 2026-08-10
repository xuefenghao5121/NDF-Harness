# ADR: NDF 规范防腐化（可移植摘要） {#DEC-HYGIENE-001}

> 日期: 2026-07-31  
> 状态: Accepted  
> 场景: 规范卫生 / 防腐化  
> 注: 本包为通用摘要；消费仓可用本地卫生 ADR 覆盖细节

## Context

`spec/` 在快速迭代后易出现结构性腐化：条款 ID 撞车、幽灵决策、死链、Charter/SLA
冲突叙事、`open/` 堆积已落地文件。若继续在腐化图上叠加条款，精化链与验证覆盖将不可审计。

## Decision

1. **先图后语义**：优先消除重复 ID、物化幽灵决策、重写 `ndf.yaml` 前缀、重定向死链，
   再调和 SLA 与归档。
2. **SLA 不静默改写**：合约下限与观测线分离；观测更新走验证树 / 提案，不刷 stable SLA 数字冒充新基线（见 [[META-006]] / [[META-007]]）。
3. **消除双重真相**：冲突 DEC 用 `superseded-by` 收口。
4. **归档不删除**：已关闭提案/验证迁入 `spec/archive/`（禁止 `spec/open/archive/`）。
5. **写入边界**：指挥整治 L0/L1/协议/SLA/决策；`50-verification` 与 L2 委派实现 Agent。

## Alternatives considered

| 方案 | 为何拒绝 |
|------|----------|
| A. 静默改写 Charter 性能数字 | 抹掉合法生产路径与历史对照 |
| B. 引入外部强制 CLI 替代纪律 | 门禁 + ADR 清单已够；工具是辅助 |
| C. 重写全部 L2 为外部契约 | 超出防腐化范围 |

## Consequences

- 固定目录 ID 唯一；`open/` 变薄；历史可追溯于 `archive/`
- 后续 SLA/金标变更走提案 + 验证树身份 bump
