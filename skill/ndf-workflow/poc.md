# POC — 派发 / 继续

文字优先（[[ADR-META-003]] / [[ADR-META-004]] / [[BEH-025]] / [[META-025]]）。

## 装订一次

产品提案「已确认」后，**OpenClaw（或合法 Control fallback）** 一次写齐 `poc/<topic>/ndf/`：

`TOPIC` → `DESIGN` → `PERF_BASELINE`（金标绑定头）→ `DELTA` 骨架 → `INTERFACE`

开题填 `explore_surface`；扫活跃 exploring 相交则 depends/conflicts。
Command MUST NOT 预写装订器正文；`binder_pipeline` 在尚无 `TOPIC.md` 时可自已确认提案开题。

> POC 装订器已写好：`poc/<topic>/ndf/`。请审阅契约 markdown；确认无误后回复「已审核」。

## 已审核（装订器）→ pack-view

人回「已审核」：

1. `GATES.md` 写 `bundle_dispatch`（绑定 bundle SHA；`source_ref` 绑本次装订器审核）
2. **同时** `persist_gate_slice_snapshot`
3. 造 worker pack **并** 落 `tmp/ndf-pack-view-<topic>.md`（[[META-024]] v2 散文）
4. **停下**。MUST NOT 此时建租约、MUST NOT `--send`

> 请阅读 `tmp/ndf-pack-view-<topic>.md`。若契约无误，回复「派发」。

## 派发（开租约 + send）

人回「派发」且本轮已展示该 pack 的散文：

```bash
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement|measure --send
```

`--send` 才 inline 租约 + 送 Implementation（硬门见 META-011 / META-025）。
无 v2 散文 → `human_pack_view_missing`。成功只认磁盘 `ndf-agent-completion/v1`。
`bundle_dispatch` 可替闸 3；租约不以 Episode 为成功条件（[[META-019]]）。

若被 `missing_human_dispatch` / SHA 拦住：先读 pack 的 `gate_drift_markdown` 或
`tmp/ndf-gate-drift-<topic>.md`（slice unified diff），再请人重审装订器后「已审核」。
**禁止**只甩两个 hex。

写界：仅 `poc/<topic>/`；禁 Trunk `src/`/`include/`/`tests`、stable SLA、`spec/meta/`。

POC **默认不**跑 OpenEvolve。仅当装订器 `design_contract` 显式
`openevolve.enabled: true` 且写明搜索空间（演化文件 vs 冻结政策）时，
Implementation 才调用 OpenEvolve。LLM `api_key` / `api_base` / 模型 MUST 读宿主
`$XDG_CONFIG_HOME/openevolve/config.yaml`（默认 `~/.config/openevolve/config.yaml`；
覆盖 `OPENEVOLVE_CONFIG`）。MUST NOT 把密钥或端点写进 `poc/<topic>/` 或装订器。
机器合同：topic 内 `evolution.yaml`。`enabled: true` 但缺宿主配置 → 不得派发搜索。

未展示散文时人说了「派发」：MUST 先完成装订器审核 + pack-view，再等人一句真正送出。

## 继续

轮次后请人：**继续**（OpenClaw 修订假设/接口/测量 → 新 SHA → 再「已审核」→ pack-view →「派发」）或
**关闭**（[close.md](close.md)）。

- Numbers / Rounds / evidence **追加**不触发重审
- 实质 amend TOPIC/DESIGN/INTERFACE/测量协议/写边界 → 下次装订器审核绑新 SHA
- 同假设留同题；分叉开平级新 topic（禁嵌套子 POC）

旧主题若仍用三闸（`TOPIC已审核` → `DESIGN已审核` → `可以开始实现`），未到闸不得写下一装订器/主题代码；新主题默认用「已审核」装订器 +「派发」送出。
