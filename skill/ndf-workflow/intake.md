# Intake — Idea 分流

收到需求后**先分流平面**，再写提案。概念上对齐
`classify_idea_plane`（`ndf_workflow_status.py`）；可跑工具对照，不可盲默认。

## 标记启发

| 倾向 | 示例标记 |
|------|----------|
| **process** | 流程、meta、AGENTS.md、装订、gate、规范卫生、graphcheck、dispatch、skill、NDF 工作流 |
| **product** | qps、recall、SLA、缓存、HNSW、IO、PQ、性能、bug、Trunk、`src/`、检索、向量、`poc/` |
| **bootstrap** | 初始化项目、Genesis、greenfield、adopt、接管已有、从 IDEA 建 |

## 判定表

| 结果 | 动作 |
|------|------|
| product | → [proposal.md](proposal.md) `product_proposal` → `spec/open/`；track 默认 poc（除非人要 promote/合入） |
| process | → [proposal.md](proposal.md) `process_proposal` → `spec/meta/open/` |
| mixed（两边都命中） | 拆**两个**互相引用提案；勿一刀切 |
| bootstrap 且非 process | → [genesis.md](genesis.md)；提案 `spec/open/proposal-project-genesis.md` |
| **ambiguous** | **问人**：这是产品能力还是 NDF 流程？MUST NOT 默认写成 poc |

## 输出模板

> 收到需求。plane=\<product\|process\|mixed\|ask\>。track=\<…\>。开始生成提案。

`ask` 时停在提问，不落文件。
