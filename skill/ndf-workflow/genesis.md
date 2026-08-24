# Genesis — 初始化项目（G-1→G3）

[[META-009]] / track=`bootstrap`。模式：`greenfield` | `adopt`。
已 accepted Genesis 的 operational 项目 **MUST NOT** 重跑；棕地可标
`operational_legacy`，不挡日常 POC。

提案唯一落点：`spec/open/proposal-project-genesis.md`。

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
```

## G-1 — Role wizard（角色向导）

**在 G0 之前**（或与 IDEA 并行但 MUST 先完成）：

1. 探测 CLI：`openclaw`、`claude`、`opencode`、`codex` 等（按宿主可用性）。
2. 询问人类：Command / Control / Implementation 三角色 adapter、fallback、model。
3. 写入绑定：
   ```bash
   python3 spec/meta/tools/ndf_role_binding.py bind \
     --command-adapter <runtime> \
     --control-adapter <runtime> --control-fallback in_host|dual_session|custom \
     --implementation-adapter <runtime> --implementation-fallback in_host|dual_session|custom
   ```
   或直接编辑 `ndf.workflow.yaml` `roles.*`。
4. 等人 **角色已配置**（回执 → Genesis `GATES.md`，绑定 roles 段 SHA）。
5. `roles_unbound` → MUST NOT 进入 G0 / G1 / 任何 dispatch。

operational 项目首次「派发」若未绑定，亦 MUST 先跑本向导。

## G0 — IDEA

1. 保存原始 IDEA（模板 `spec/meta/templates/genesis/IDEA.md.stub`）；区分原话与推断。
2. 写/更新 Genesis 提案；等人 **IDEA已审核**（回执 → Genesis `GATES.md`）。
3. 未过闸前 MUST NOT 写 stable `spec/meta/` 正文或开产品 POC。

## G1 — Foundation

模板 `FOUNDATION.md.stub`。串行口令（均写 `GATES.md`）：

```text
CHARTER已审核 → ARCHITECTURE已审核 → VERIFICATION已审核 → 可以建立初始主线
```

无证据性能值保持 `draft` / TBD / not-established。Control 维护 L0/L1；
不伪造 SLA。

## G2 — genesis-pack → Trunk candidate

「可以建立初始主线」后：

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-pack \
  --mode greenfield|adopt --json
# 或 project-control-pack（bootstrap 任务）；仅 safe_to_dispatch 后
# 人回「派发」→ dispatch-send（见 delegate.md）
```

Implementation 角色：独立 worktree/branch，最小可构建垂直切片；可写初始
`src/`/`include/`/`tests`/构建与 L2/L3；**禁止**改 L0/L1、charter、architecture、
decisions、`spec/meta/`。未知机制留给后续 POC。

## G3 — 验收与 GENESIS已审核

门禁：角色已配置 + Foundation 回执齐全、`ndf_index` + `ndf_graphcheck`、构建与最低功能验收、
可解析 NDF/Trunk SHA。失败不得写 Genesis accepted。

决策绑定 IDEA 来源、NDF tree SHA、Trunk SHA、verification ref、known drafts。
人回 **GENESIS已审核** → Status accepted → 项目进入 operational。
adopt 不改写既有 git 历史。
