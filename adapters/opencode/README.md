# Adapter: OpenCode

1. Install root `AGENTS.md`.  
2. Register or `@`-include the skill core in OpenCode's instruction/skill mechanism:

```text
packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

3. Do not maintain a second copy of track/proposal rules inside OpenCode-only docs — link `AGENTS.md` instead.

See [`SKILL.md`](SKILL.md) wrapper.

## How this host spawns Control/Implementation children

OpenCode is typically **Command**. Per `ndf.workflow.yaml`:

| Role | Preferred | Fallback |
|------|-----------|----------|
| Control | `openclaw` → `dispatch-send` | `in_host` spawn file in `tmp/` or `dual_session` |
| Implementation | `claude-code` → `poc-dispatch --send` | `in_host` spawn file or `dual_session` |
