# Adapter: generic

No IDE-specific layout.

1. Ensure repo-root `AGENTS.md` is installed from `workflow/AGENTS.md`.  
2. Point the Command Agent (system prompt or user message) at:

```text
packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

Or, after vendoring into the repo, the same paths under your chosen prefix.

3. Internal modules: `skill/ndf-workflow/install.md` | `adopt.md` | `govern.md` | `sync.md`.

See [`SKILL.md`](SKILL.md) wrapper.

## How this host spawns Control/Implementation children

Generic hosts run **Command** only. Control/Implementation resolve from `ndf.workflow.yaml`:

1. Probe CLI for configured adapters
2. Preferred adapter available → standard dispatch CLI
3. Else `in_host` → write `tmp/ndf-spawn-{control|implementation}-*.md` with pack + role prompt
4. Else `dual_session` → print prompts for human to paste in second agent chat
5. Else `custom` → run user command from yaml
6. Else `role_adapter_unsupported`
