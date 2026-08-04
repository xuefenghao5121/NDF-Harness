# Adapter: generic

No IDE-specific layout.

1. Ensure repo-root `AGENTS.md` is installed from `workflow/AGENTS.md`.  
2. Point the agent (system prompt or user message) at:

```text
packages/ndf-harness/skill/SKILL.md
packages/ndf-harness/skill/MODES.md
```

Or, after vendoring into the repo, the same paths under your chosen prefix.

3. Modes: init | adopt | govern | sync — semantics identical to skill core.
