# Delegate — 委派 OpenClaw / 委派 Claude Code

指挥面（Command Agent）只造 pack、等人审、调 `dispatch-send` / `poc-dispatch`。
成功只认磁盘 `ndf-agent-completion/v1`。

## 委派 OpenClaw（Control）

| 用途 | CLI |
|------|-----|
| 产品 Idea | `control-pack --task product_proposal --intent-file tmp/intent.md --json` |
| 流程 Idea / land | `project-control-pack --task ndf_improvement_proposal\|ndf_improvement_land … --json` |
| 装订器 / 门禁文档 | `control-pack --topic <t> --task binder_pipeline\|gate_pipeline … --json` |
| 送出 | 人回「派发」/「继续」→ `dispatch-send --pack-file tmp/ndf-dispatch-last-pack.json` |

**可写**：`spec/open/`（产品）、`spec/meta/open/`（流程）、`poc/<topic>/ndf/`、`.openclaw/state.json`。  
**禁止**：`src/`、`include/`、`tests/`；静默写 `GATES.md` 的 `approved_by`；未人审写 `spec/meta/` 稳定正文。

```bash
python3 spec/meta/tools/ndf_workflow_status.py control-pack \
  --task product_proposal --intent-file tmp/intent.md --json
# → 人「派发」→
python3 spec/meta/tools/ndf_dispatch_send.py \
  --pack-file tmp/ndf-dispatch-last-pack.json
```

## 委派 Claude Code（Implementation）

| 用途 | CLI |
|------|-----|
| POC 实现 / 测量 | `poc-dispatch --topic <t> --intent implement\|measure --send` |
| Genesis Trunk candidate | `genesis-pack --mode greenfield\|adopt --json`（Foundation 闸过后）→「派发」→ `dispatch-send` |
| promote / bug 合入 | 按 `ndf_close.py plan` 的 ACP 路径 |

**可写**：POC 仅 `poc/<topic>/`；genesis / promote 按 close plan / pack 的 `allowed_write_root`。  
**禁止**：L0/L1、`spec/meta/` 正文、越界写根。

```bash
python3 spec/meta/tools/ndf_workflow_status.py poc-dispatch \
  --topic <topic> --intent implement --send
```

日常 POC **不要**用 legacy `pack`；兼容代码可留，指挥面不教。

## 成功合同

1. Pack `safe_to_dispatch=true`（否则取消，报告 blockers）
2. 本聊天等人确认「派发」/「继续」（可写 pack 不自动送；POC「派发」另写 `GATES.md` `bundle_dispatch`）
3. `dispatch-send` 或 `poc-dispatch --send` 送 worker + 心跳等待
4. 读 `completion_receipt_path`：磁盘 completion + closeout succeeded
5. MUST NOT 用手抄 Numbers、transport ACK、stdout JSON 冒充成功

在途问进展 → `dispatch-probe`（探活，不重派）。

硬安全门（fail-closed）

错仓库、越界写根、缺人审 bundle、同 topic 并发写 run、上下文漂移、伪造 completion、
ACP 预算溢出、`openclaw_session_invalid`。

因 bundle SHA 漂移硬阻塞时：先展示 `gate_drift_markdown`（slice diff），再请人「派发」；
MUST NOT 只输出不透明哈希。

握手须含：`repo_root`、`run_id`/`session_id`、`base_sha`、独立 worktree/branch、
`allowed_write_root`。OpenClaw 收到 pack 后更新 `{repo_root}/.openclaw/state.json`。

禁止：指挥面直接 `openclaw.chat_send` 绕过 `dispatch-send`；用 Episode/Replay 当成功条件。
