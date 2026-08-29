# Adapter: OpenClaw

1. Install root `AGENTS.md` from `workflow/AGENTS.md`（command / control default entry）.  
2. Bind roles and provision a **per-project** OpenClaw agent ([[META-020]]):

```bash
python3 spec/meta/tools/ndf_role_binding.py bind --repo . \
  --command cursor --control openclaw --implementation claude-code
# or:
python3 spec/meta/tools/ndf_role_binding.py provision-openclaw-session --repo .
```

This writes `roles.control.agent_id` / `session_key` / `session_binding_version: ndf-v1`
into `ndf.workflow.yaml` and runs `openclaw agents add <agent_id> --non-interactive
--workspace <repo>`. Do **not** reuse shared `agent:main:main` across projects.

3. Optional: copy or symlink skill core into the OpenClaw skills directory:

```text
skills/ndf-workflow/SKILL.md  →  packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

Prefer **pointer/symlink** over duplicating workflow prose.

4. OpenClaw sessions MUST follow root `AGENTS.md` track workflow; internal init/govern/sync
   modules are for Command Agent only.

See [`SKILL.md`](SKILL.md) wrapper.

## How this host spawns Control/Implementation children

When OpenClaw is **Command** (unusual): follow `skill/ndf-workflow/SKILL.md` five phrases.

When OpenClaw is **Control** (default binding):

| Path | Mechanism |
|------|-----------|
| Preferred | `dispatch-send` → gateway `sessionKey` + pack `agentId` (per-project) |
| `in_host` | N/A — OpenClaw is the Control adapter itself |
| `dual_session` | Human opens second OpenClaw chat with role prompt from pack |

**Parallelism:** distinct local Git repos MAY dispatch concurrently (each has its own
agent/session). Same repo Control hops remain serial. Implementation on this host:
delegate to `claude-code` adapter or `in_host` spawn file from Command.
