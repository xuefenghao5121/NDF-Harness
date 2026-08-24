# Delegate — 按角色委派 Control / Implementation

Command Agent 只造 pack、等人审、调 `dispatch-send` / `poc-dispatch`。
成功只认磁盘 `ndf-agent-completion/v1`。

## 角色解析

委派前 MUST 读 `ndf.workflow.yaml` 或：

```bash
python3 spec/meta/tools/ndf_role_binding.py resolve --role control|implementation --json
```

解析序（每角色独立）：首选 adapter CLI 可用 → `in_host` spawn 文件 → `dual_session`
prompt → `custom` command → `role_adapter_unsupported`。

OpenClaw / Claude Code 是**默认** adapter，不是唯一路径。Command MUST NOT 塌缩为
自己写 Control/Implementation 边界内的实现/测量。

## 委派 Control（Design agent）

| 用途 | CLI |
|------|-----|
| 产品 Idea | `control-pack --task product_proposal --intent-file tmp/intent.md --json` |
| 流程 Idea / land | `project-control-pack --task ndf_improvement_proposal\|ndf_improvement_land … --json` |
| 装订器 / 门禁文档 | `control-pack --topic <t> --task binder_pipeline\|gate_pipeline … --json` |
| 送出 | 人回「派发」/「继续」→ `dispatch-send --pack-file tmp/ndf-dispatch-last-pack.json` |

**可写**：见 [roles/control.md](roles/control.md) 或 `ndf.workflow.yaml` `roles.control.writable`。  
**禁止**：`src/`、`include/`、`tests/`；静默写 `GATES.md` 的 `approved_by`；未人审写 `spec/meta/` 稳定正文。

`adapter=openclaw` 时走 `dispatch-send` gateway 路径；`in_host` / `dual_session` 时见
spawn 文件或 dual-session prompt（仍等磁盘 completion）。

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --task product_proposal --intent-file tmp/intent.md --json
# → 人「派发」→
python3 spec/meta/tools/ndf_dispatch_send.py \
  --pack-file tmp/ndf-dispatch-last-pack.json
```

## 委派 Implementation

| 用途 | CLI |
|------|-----|
| POC 实现 / 测量 | `poc-dispatch --topic <t> --intent implement\|measure --send` |
| Genesis Trunk candidate | `genesis-pack --mode greenfield\|adopt --json`（Foundation 闸过后）→「派发」→ `dispatch-send` |
| promote / bug 合入 | 按 `ndf_close.py plan` 的 ACP 路径 |

**可写**：见 [roles/implementation.md](roles/implementation.md)；POC 仅 `poc/<topic>/`。  
**禁止**：L0/L1、`spec/meta/` 正文、越界写根。

```bash
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement --send
```

日常 POC **不要**用 legacy `pack`；兼容代码可留，Command 不教。

## 成功合同

1. `roles_unbound=false` 且 pack `safe_to_dispatch=true`（否则取消，报告 blockers）
2. 本聊天等人确认「派发」/「继续」（可写 pack 不自动送；POC「派发」另写 `GATES.md` `bundle_dispatch`）
3. `dispatch-send` 或 `poc-dispatch --send` 送 worker + 心跳等待
4. 读 `completion_receipt_path`：磁盘 completion + closeout succeeded
5. MUST NOT 用手抄 Numbers、transport ACK、stdout JSON 冒充成功

在途问进展 → `dispatch-probe`（探活，不重派）。

硬安全门（fail-closed）

错仓库、越界写根、缺人审 bundle、同 topic 并发写 run、上下文漂移、伪造 completion、
ACP 预算溢出、`openclaw_session_invalid`、`roles_unbound`、`role_adapter_unsupported`。

因 bundle SHA 漂移硬阻塞时：先展示 `gate_drift_markdown`（slice diff），再请人「派发」；
MUST NOT 只输出不透明哈希。

握手须含：`repo_root`、`run_id`/`session_id`、`base_sha`、独立 worktree/branch、
`allowed_write_root`。Control 收到 pack 后 MAY 更新 `{repo_root}/.openclaw/state.json`
或 `ndf.workspace.json`。

禁止：Command 直接 `openclaw.chat_send` 绕过 `dispatch-send`；用 Episode/Replay 当成功条件。
