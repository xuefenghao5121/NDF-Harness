# Adapter: Cursor

Cursor is **one** consumer. Workflow SoT is installed repo `AGENTS.md` + `spec/meta/` +
[`../../skill/ndf-workflow/SKILL.md`](../../skill/ndf-workflow/SKILL.md).

## Install

**Option A — pointer skill**（recommended）:

```text
.cursor/skills/ndf-workflow/SKILL.md
  → frontmatter + "Follow packages/ndf-harness/skill/ndf-workflow/SKILL.md"
```

**Option B — copy tree** after vendoring the package:

```bash
mkdir -p .cursor/skills/ndf-workflow
cp -a packages/ndf-harness/skill/ndf-workflow/* .cursor/skills/ndf-workflow/
```

Do **not** fork process prose into a second copy; refresh from package on sync.

## Modes

Same workflow as skill core（初始化 / Idea / 派发 / 继续 / 关闭）. Internal init/adopt/govern/sync
modules stay under `skill/ndf-workflow/` — not exposed to humans.

See [`SKILL.md`](SKILL.md) wrapper in this folder.
