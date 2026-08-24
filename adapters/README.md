# Runtime adapters

**Business prose SoT:** installed `AGENTS.md`, `spec/meta/`, and `skill/ndf-workflow/SKILL.md`.

Each adapter only explains **how to load** the skill core in that runtime.
Adding a runtime = add a folder; do **not** fork the workflow text.

| Adapter | Typical mount |
|---------|----------------|
| [`generic/`](generic/) | Tell the agent to read `skill/ndf-workflow/SKILL.md` + root `AGENTS.md` |
| [`openclaw/`](openclaw/) | OpenClaw control agent + skill pointer |
| [`claude-code/`](claude-code/) | Claude Code skills / CLAUDE.md pointer |
| [`opencode/`](opencode/) | OpenCode instruction / skill path |
| [`cursor/`](cursor/) | `.cursor/skills/ndf-workflow/` install or pointer |

Human entry is always [`../skill/ndf-workflow/SKILL.md`](../skill/ndf-workflow/SKILL.md).
