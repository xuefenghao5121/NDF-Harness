# Proposal — 提交 Idea

分流完成后再写。头部 MUST：

```text
> track: bootstrap | poc | promote | process | bug | refactor | rollback
```

## 写根

| task | 路径 | 内容要点 |
|------|------|----------|
| `product_proposal` | `spec/open/proposal-*.md` | 产品 L0/L1、接口、draft SLA；poc 默认 `status=draft` |
| `process_proposal` | `spec/meta/open/proposal-meta-*.md` | 改 `spec/meta/**` + 产品 thin 指针；新建 process ID 用 `META-*` / `ADR-META-*` 等（[[ADR-META-002]]） |
| bootstrap | `spec/open/proposal-project-genesis.md` | 见 [genesis.md](genesis.md) |

mixed：两案互相 `depends-on` / 引用；勿混写根。

## 人工闸

1. 生成后：

> 提案已生成：`…`。请审阅，确认后回复「已确认」。

2. 「已确认」→ 校验引用 ID → 按 track 落地 → 提案顶追加 `Status: Implemented on YYYY-MM-DD`。
3. 落地后：

> 提案已落地。变更摘要：…。请审核，回复「已审核」。

4. 「已审核」后：
   - **poc** → 写齐装订器 → 等人「派发」（[poc.md](poc.md)）
   - **process** → 结束（validation/perf = n/a）
   - **promote/bug/…** → [close.md](close.md) / Trunk 路径
   - **bootstrap** → [genesis.md](genesis.md) 分段门禁

## 禁止

- 未「已确认」改 Trunk / stable 契约
- process 长文写回 `20-behavior/`
- 探索期写 `status=stable` 的 must SLA
