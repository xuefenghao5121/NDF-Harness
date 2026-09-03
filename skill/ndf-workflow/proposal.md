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

## 人工闸（[[META-025]]）

提案 MUST 先写入磁盘，再请人确认。人审对象是**该 markdown**，MUST NOT 甩 JSON
或问「是否写入磁盘」。

1. 生成后：

> 提案已生成：`…`。请审阅该文件，确认后回复「已确认」。

2. 「已确认」→ 校验引用 ID → 按 track 落地。process：落地即结束，MUST NOT
   再要提案「已审核」。poc：立刻委派 Control 写齐装订器。
3. poc 装订器写好后：

> POC 装订器已写好：`poc/<topic>/ndf/`。请审阅这些 markdown；确认无误后回复「已审核」。

4. 「已审核」（装订器）之后：写 `bundle_dispatch` + 造 pack + pack-view，等人
   「派发」（[poc.md](poc.md)）。

## 禁止

- 未「已确认」改 Trunk / stable 契约
- process 长文写回 `20-behavior/`
- 探索期写 `status=stable` 的 must SLA
- 对人审 completion JSON / last-pack.json
