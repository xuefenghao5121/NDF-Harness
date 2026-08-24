# ADR: Idea 分流与控制面减法 {#ADR-META-004}

<!-- ndf: kind=decision date=2026-08-24 status=stable scope=ndf-process -->
<!-- ndf: depends-on=META-009,META-010,META-011,BEH-025 -->

**Context.** [[ADR-META-003]] 将 Commander/Episode/Replay 从 POC 热路径降为可选诊断，
但仍保留面板可信、ActionSpec、回放沙箱等义务。实践中这些机制继续占用人类时间与
理解空间，并把「可信」误绑在投影仪式上。同时产品 Idea 与 NDF 流程 Idea 曾共享
写根，容易一刀切。

**Decision.**

1. **少则得**：人的注意力只用于 Idea、契约、证据和决策。可信度由最小机械安全门
   保证（身份、写根、人审 bundle、并发、上下文、预算、磁盘 completion），而非
   面板/回放仪式。
2. **Idea 分流**：产品/项目 Idea → `spec/open/`；NDF 工作流 Idea → `spec/meta/open/`；
   mixed 拆双案；ambiguous 先问人。
3. **完整退役** Commander、ActionSpec、snapshot freshness、serve/SSE、Episode 运行链、
   Replay/Guest/button-action。历史 `.ndf/replay/` 只读考古，不参与成功合同。
4. **唯一文字入口 skill** 编排初始化（Genesis G0–G3）、Idea、派发、继续、关闭；
   内部模块对人类不可见。
5. **supersedes** ADR-META-003 中「保留 Episode/Replay 为审计工具」的运行义务；
   ADR-META-003 的文字优先 POC 热路径与硬安全门仍然有效。

**Alternatives rejected.**

| 方案 | 拒绝理由 |
|------|----------|
| 继续只读 Commander + 降级 Replay | 仍强迫人理解投影与回放状态 |
| 取消全部人工门禁 | 会回到「文件存在=已批准」 |
| 保留 ActionSpec 作文字路由表 | 与按钮目录同源，继续制造假依赖 |

**Source.** `spec/meta/open/proposal-meta-idea-routing-control-retirement.md`；
人工确认实现指令 2026-08-24。

> rationale: 大道至简。控制面不得反客为主；分流写根，删除仪式，保留安全内核。
