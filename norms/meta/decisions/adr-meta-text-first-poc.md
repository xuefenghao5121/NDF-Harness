# ADR: 文字优先 POC 热路径 {#ADR-META-003}

<!-- ndf: kind=decision date=2026-08-24 status=stable scope=ndf-process -->
<!-- ndf: depends-on=BEH-025,META-010,META-011,META-012,META-013 -->

**Context.** 2026-08 中下旬为修复假 green、未派出测量、stdout 冒充成功、PID 耗尽、
租约 stub 等问题，叠加了 Commander action-registry、Episode/Replay、双流水线、
多层 fail-closed。这些机制对**控制面自举与争议审计**有价值，但对**日常 POC**
把准备成本从分钟级拉到小时级，并出现「代码已落地、回执链判失败」的假失败。

**Decision.**

1. **POC 业务热路径**恢复为文字指挥：提案审核 → 整包装订器 → 「派发」→ 实现/测量
   → 继续或 close（见 `proposal-meta-text-first-poc-path.md`）。
2. **Commander / Episode / Replay / Control 流水线**降为可选诊断与 meta 改进工具，
   MUST NOT 作为日常 POC 的必经写路径或红色业务失败源。
3. **硬安全门**保留：错仓库、越界写根、缺人审 bundle、并发写 run、上下文漂移、
   伪造 completion、ACP 预算溢出。
4. **软审计**（meta graph、全量 bindcheck、projection freshness、Replay 完整度）
   移出 `poc-dispatch` 阻塞集；在 close/promote 与争议审计时再强制。

**Alternatives rejected.**

| 方案 | 拒绝理由 |
|------|----------|
| 继续把面板当主指挥面、仅修文案 | 根因是职责叠层，不是文案 |
| 删除全部 Episode/Replay | 审计与回归仍需要；应降级而非销毁 |
| 取消全部人工门禁 | 会回到「文件存在=已批准」；保留「派发」绑定 bundle SHA |

**Source.** `spec/meta/open/proposal-meta-text-first-poc-path.md`；计划
`text-first-poc-flow`；人工确认实现指令 2026-08-24。

> rationale: 产品探索应把人的注意力留在假设、实现与证据上；控制面可信度用按需
> 诊断保证，不得反客为主。

**Supersession note (2026-08-24).** 「删除全部 Episode/Replay」一行已被
[[ADR-META-004]] 完整退役控制面所 supersede；文字优先热路径与硬安全门仍有效。
详见 `decisions/adr-meta-control-retirement.md`。
