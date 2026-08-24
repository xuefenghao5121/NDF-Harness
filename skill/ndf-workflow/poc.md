# POC — 派发 / 继续

文字优先（[[ADR-META-003]] / [[ADR-META-004]] / [[BEH-025]]）。

## 装订一次

产品提案「已审核」后，**OpenClaw** 一次写齐 `poc/<topic>/ndf/`：

`TOPIC` → `DESIGN` → `PERF_BASELINE`（金标绑定头）→ `DELTA` 骨架 → `INTERFACE`

开题填 `explore_surface`；扫活跃 exploring 相交则 depends/conflicts。

> POC 装订器已写好：`poc/<topic>/ndf/`。请审阅契约；确认无误后回复「派发」。

## 派发（Claude Code）

人回「派发」：

1. `GATES.md` 写 `bundle_dispatch`（phrase=`派发`）+ bundle SHA
2. **同时** `persist_gate_slice_snapshot`（按 `approved_content_sha` 存 review-slice
   基线），否则下次漂移只能报 `diff_unavailable`
3. 执行：

```bash
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure --send
```

`--send` 内联租约 + 送 Claude Code（硬门见 META-011）。成功只认磁盘
`ndf-agent-completion/v1`。

若被 `missing_human_dispatch` / SHA 拦住：先读 pack 的 `gate_drift_markdown` 或
`tmp/ndf-gate-drift-<topic>.md`（slice unified diff），再请人重审后「派发」。
**禁止**只甩两个 hex。

写界：仅 `poc/<topic>/`；禁 Trunk `src/`/`include/`/`tests`、stable SLA、`spec/meta/`。

## 继续

轮次后请人：**继续**（OpenClaw 修订假设/接口/测量 → 新 SHA → 再「派发」Claude）或
**关闭**（[close.md](close.md)）。

- Numbers / Rounds / evidence **追加**不触发重审
- 实质 amend TOPIC/DESIGN/INTERFACE/测量协议/写边界 → 下次派发绑新 SHA
- 同假设留同题；分叉开平级新 topic（禁嵌套子 POC）

旧主题若仍用三闸（`TOPIC已审核` → `DESIGN已审核` → `可以开始实现`），未到闸不得写下一装订器/主题代码；新主题默认只用「派发」。
