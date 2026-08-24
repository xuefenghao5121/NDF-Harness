# Genesis — 初始化项目（G0→G3）

[[META-009]] / track=`bootstrap`。模式：`greenfield` | `adopt`。
已 accepted Genesis 的 operational 项目 **MUST NOT** 重跑；棕地可标
`operational_legacy`，不挡日常 POC。

提案唯一落点：`spec/open/proposal-project-genesis.md`。

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
```

## G0 — IDEA

1. 保存原始 IDEA（模板 `spec/meta/templates/genesis/IDEA.md.stub`）；区分原话与推断。
2. 写/更新 Genesis 提案；等人 **IDEA已审核**（回执 → Genesis `GATES.md`）。
3. 未过闸前 MUST NOT 写 stable `spec/meta/` 正文或开产品 POC。

## G1 — Foundation

模板 `FOUNDATION.md.stub`。串行口令（均写 `GATES.md`）：

```text
CHARTER已审核 → ARCHITECTURE已审核 → VERIFICATION已审核 → 可以建立初始主线
```

无证据性能值保持 `draft` / TBD / not-established。OpenClaw 维护 L0/L1；
不伪造 SLA。

## G2 — genesis-pack → Trunk candidate

「可以建立初始主线」后：

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-pack \
  --mode greenfield|adopt --json
# 或 project-control-pack（bootstrap 任务）；仅 safe_to_dispatch 后
# 人回「派发」→ dispatch-send（见 delegate.md）
```

Claude Code：独立 worktree/branch，最小可构建垂直切片；可写初始
`src/`/`include/`/`tests`/构建与 L2/L3；**禁止**改 L0/L1、charter、architecture、
decisions、`spec/meta/`。未知机制留给后续 POC。

## G3 — 验收与 GENESIS已审核

门禁：Foundation 回执齐全、`ndf_index` + `ndf_graphcheck`、构建与最低功能验收、
可解析 NDF/Trunk SHA。失败不得写 Genesis accepted。

决策绑定 IDEA 来源、NDF tree SHA、Trunk SHA、verification ref、known drafts。
人回 **GENESIS已审核** → Status accepted → 项目进入 operational。
adopt 不改写既有 git 历史。
