# Security

Fail-closed security model for NDF Harness 1.0 dispatch and governance.

## Design principle

When safety cannot be proven, tools **stop** — they do not guess, downgrade checks, or
write authoritative spec from automation.

## Fail-closed gates

| Gate | Enforced by | On failure |
|------|-------------|------------|
| Human bundle approval | poc-dispatch, dispatch-send | block dispatch |
| Context manifest match | ndf_context verify | `context_verify_failed` |
| Write root / isolation | poc-dispatch, poc_isolation | block dispatch |
| ACP context budget | poc-dispatch | `acp_context_over_budget` |
| Disk completion | dispatch-send | no success declared |
| Graph hard errors (promote/close) | graphcheck | block close apply |
| Report path under spec/ | ndf_report_io | exit 2 |

Soft checks (bindcheck, full graph on daily POC) warn in health but may not block hot path.

## Credentials

- Harness tools do **not** embed API keys or session secrets in repo files.
- OpenClaw / Claude credentials live in host agent configuration — outside harness package.
- Pack JSON MUST NOT contain raw tokens; reference session IDs only.
- `.openclaw/state.json` per repo is gitignored; contains workspace binding, not secrets.

**Rule:** never commit credentials into `spec/`, packs, or completion receipts.

## Path escape

- POC implementation: `allowed_write_root` = `poc/<topic>/` (or worktree equivalent).
- Control: spec open dirs + binder paths only.
- Command: `tmp/` for packs and reports.
- `ndf_report_io` rejects report paths under `spec/`.
- Dispatch validates `workspace.repo_root` before send.

Agents MUST NOT write Trunk production paths during POC track.

## Fake completion

Blocked patterns:

- Declaring success from transport ACK or worker stdout alone
- Writing completion file without schema `ndf-agent-completion/v1`
- Receipt SHA mismatch vs pack manifest / repo HEAD
- Completion path outside declared `completion_receipt_path`

`ndf_dispatch_send.py` reads and validates disk receipt before recording success.

## Concurrent write

- One active write run per topic at a time (lease / run_id).
- Stale lease vs HEAD triggers block until resolved.
- Command agent MUST NOT parallelize two `--send` dispatches for same topic.

## Installer integrity

- Protected files: `AGENTS.md`, `spec/meta/*.md` — skip without `--force`.
- Adopt mode never silent-overwrites settled SoT.
- `--force` requires explicit human decision (document in migration plan).

## Advisor sandbox

- `ndf_advise simulate` mutates in-memory copy only.
- MUST NOT apply graph/bind surgery to disk without human proposal landing.

## Retired attack surface

Commander, Replay, ActionSpec, and panel auto-send paths removed (ADR-META-004) to reduce
ambient trust in UI transport.

## Incident response

1. Stop further dispatches for affected topic.
2. Preserve `tmp/ndf-dispatch-last*.json` and completion receipts.
3. Run topic-health + isolation check.
4. Revert unauthorized Trunk writes via git.
5. Re-dispatch only after gate SHA re-approved.

## Related

- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`WORKFLOW.md`](WORKFLOW.md)
