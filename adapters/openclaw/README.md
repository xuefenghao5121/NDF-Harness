# Adapter: OpenClaw

1. Install root `AGENTS.md` from `workflow/AGENTS.md`（command / control default entry）.  
2. Optional: copy or symlink skill core into the OpenClaw skills directory:

```text
skills/ndf-workflow/SKILL.md  →  packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

Prefer **pointer/symlink** over duplicating workflow prose.

3. OpenClaw sessions MUST follow root `AGENTS.md` track workflow; internal init/govern/sync
   modules are for Command Agent only.

See [`SKILL.md`](SKILL.md) wrapper.

## How this host spawns Control/Implementation children

When OpenClaw is **Command** (unusual): follow `skill/ndf-workflow/SKILL.md` five phrases.

When OpenClaw is **Control** (default binding):

| Path | Mechanism |
|------|-----------|
| Preferred | `dispatch-send` → gateway `sessionKey` from pack |
| `in_host` | N/A — OpenClaw is the Control adapter itself |
| `dual_session` | Human opens second OpenClaw chat with role prompt from pack |

Implementation on this host: delegate to `claude-code` adapter or `in_host` spawn file from Command.
