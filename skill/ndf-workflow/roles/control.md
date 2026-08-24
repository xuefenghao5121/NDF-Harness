# Control role — write boundary & completion

**Role**: Design agent (default adapter: OpenClaw).

## Writable roots

- `spec/open/`（产品提案）
- `spec/meta/open/`（流程提案；land 除外 stable 正文须人审）
- `poc/<topic>/ndf/`（装订器、GATES 文档面）
- `.openclaw/state.json` / `ndf.workspace.json`（workspace 绑定）

## Forbidden

- Trunk `src/`、`include/`、`tests/`
- `spec/meta/` stable 正文（未经 process land + 人审）
- 静默写 `GATES.md` 的 `approved_by`
- 伪造磁盘 completion

## Completion contract

Success = disk `ndf-agent-completion/v1` at pack `completion_receipt_path` with
matching topic/task/run identity. Transport ACK ≠ success.

Control receives Task Manifest + Control role plan (same `manifest_sha` as Implementation).
MUST NOT read Implementation-only write roots.

## Adapter notes

- `openclaw`: `dispatch-send` → gateway session
- `in_host`: Command spawns Control sub-agent; spawn file in `tmp/`
- `dual_session`: human pastes prompt in second chat; still waits for completion receipt
- `custom`: user-provided command from `ndf.workflow.yaml`

See [[META-011]] and [../delegate.md](../delegate.md).
