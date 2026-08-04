# Adapter: Cursor

Cursor is **one** consumer. Workflow SoT is still root `AGENTS.md` + `packages/ndf-harness/skill/`.

## Install

Place a thin skill under `.cursor/skills/ndf-harness/` whose body **points to** the package skill core（do not fork process text）:

```text
.cursor/skills/ndf-harness/SKILL.md
  → short frontmatter + "Follow packages/ndf-harness/skill/SKILL.md"
```

In this maintaining repo, `.cursor/skills/ndf-harness` is that thin adapter.

## Modes

Same four modes as skill core. Prefer `disable-model-invocation` for init/adopt if the host supports it, to avoid accidental scaffolding.
