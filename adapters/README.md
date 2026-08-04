# Runtime adapters

**Business prose SoT:** `../skill/SKILL.md`, `../workflow/AGENTS.md`, `../norms/`, `../governance/`.

Each adapter only explains **how to load** the skill core in that runtime.
Adding a runtime = add a folder; do **not** fork the workflow text.

| Adapter | Typical mount |
|---------|----------------|
| [`generic/`](generic/) | Tell the agent to read `skill/SKILL.md` + root `AGENTS.md` |
| [`openclaw/`](openclaw/) | OpenClaw / commander skill path |
| [`claude-code/`](claude-code/) | Claude Code skills / CLAUDE.md pointer |
| [`opencode/`](opencode/) | OpenCode instruction / skill path |
| [`cursor/`](cursor/) | `.cursor/skills/ndf-harness` thin wrapper |
