# ADR: POC 探索轨与 `models/` 边界

<!-- ndf: kind=decision date=2026-08-01 affects=CHR-008,ARCH-008,BEH-018,BEH-019,BEH-020,CON-POC-001,DEF-020,DEF-021 -->

**Context.** 沿同一提案多轮深入探索时，若过早把契约与实现合入 Trunk（`src/` + stable
must），方向证伪后会出现：NDF 可回退/废弃，但代码 commit 仍挂在主线，SoT 与实现漂移。
产品负结果 DEC 是典型反面教材。有人提议用 `spec/models/` 承载 POC。

**Decision.**

1. 采用 **探索轨 / 主线轨** 双轨（[[CHR-008]]）：试错进 `poc/<topic>/`；仅晋升有效切片进 `src/`。
2. **`spec/models/` 保留 NDF L3 参考模型语义**，禁止当作生产路径实验沙箱（[[ARCH-008]]）。
3. 探索期禁止 stable must SLA 与生产默认开启（[[BEH-018]]、[[CON-POC-001]]）。
4. 负结果走 DEC + deprecated + revert/不合并，不要求改写 git 历史（[[BEH-020]]）。

**Alternatives rejected.**

| 方案 | 拒绝理由 |
|------|----------|
| POC 放进 `spec/models/` | 污染 L3 金标；Agent 易把草稿当 must 实现 |
| 仅靠 feature 分支 | 合并瞬间重新耦合；无 NDF 状态机约束 |
| 主线 + env 默认关继续探索 | 仍易提前落地 stable 条款/SLA（RC 路径） |

**Source.** `spec/open/proposal-ndf-poc-track.md`；人工确认 2026-08-01。

> rationale: 散文可在 open/ 起草，可执行试错进 poc/，主线只收有效果的切片——
> 时间仍在 git，承诺态只在晋升闸门之后出现。
