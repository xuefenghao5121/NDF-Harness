# Implementation role — write boundary & completion

**Role**: Implementation agent (default adapter: Claude Code ACP).

## Writable roots (by track)

| track | allow | deny |
|-------|-------|------|
| poc | `poc/<topic>/` | Trunk `src/`、`include/`、`tests/`、`spec/meta/` |
| bootstrap | isolated worktree: `src/`、`include/`、`tests/`、L2/L3 | L0/L1、charter、architecture、decisions、`spec/meta/` |
| promote / bug / refactor | `src/`、`include/`、`tests/`、`50-verification/`、L2/L3 | `poc/`（unless close plan says otherwise） |

Exact globs: `ndf.workflow.yaml` `write_roots_by_track`.

## Forbidden (any track)

- L0/L1 条款、`spec/meta/` 流程正文
- 越界写根（outside `allowed_write_root`）
- 实验补丁写入 `spec/models/` 冒充 L3 金标

## Handshake required

- `workspace.repo_root`
- `allowed_write_root`
- `base_sha`
- `run_id` / `session_id`
- 独立 worktree/branch（或可证等价）

## Completion contract

Success = disk `ndf-agent-completion/v1` with changed files, commit SHA (if any),
reproduce commands, and evidence paths. Transport ACK ≠ success.

Implementation receives Task Manifest + Implementation role plan (same `manifest_sha` as Control).

## Adapter notes

- `claude-code`: `poc-dispatch --send` / ACP genesis-pack
- `in_host`: Command spawns Implementation sub-agent; spawn file in `tmp/`
- `dual_session`: human pastes prompt in second chat
- `custom`: user-provided command from `ndf.workflow.yaml`

See [[META-011]] and [../delegate.md](../delegate.md).
