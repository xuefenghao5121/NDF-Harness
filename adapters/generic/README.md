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
