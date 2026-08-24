# Adapter: Codex

1. Install root `AGENTS.md` from `workflow/AGENTS.md`.
2. Mount the skill core (pointer recommended):

```text
.codex/skills/ndf-harness/SKILL.md  →  packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

3. Codex acts as **Command Agent** on this host; Control/Implementation resolve from
   `ndf.workflow.yaml` (defaults: OpenClaw / Claude Code ACP with `in_host` fallback).

## How this host spawns Control/Implementation children

| Role | Preferred | Fallback on this host |
|------|-----------|------------------------|
| Control | `openclaw` → `dispatch-send` | `in_host`: Command writes `tmp/ndf-spawn-control-*.md` with pack path + role prompt |
| Implementation | `claude-code` → `poc-dispatch --send` | `in_host`: Command writes `tmp/ndf-spawn-implementation-*.md` with worktree + write root |

`dual_session`: emit role prompt for human to paste in a second Codex/OpenClaw/Claude chat.
Success still = disk `ndf-agent-completion/v1`.

See [`SKILL.md`](SKILL.md) wrapper.
