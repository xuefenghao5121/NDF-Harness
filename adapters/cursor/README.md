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

## How this host spawns Control/Implementation children

Cursor is the **Command** role. Resolve Control/Implementation from `ndf.workflow.yaml`:

| Role | Preferred | Fallback on Cursor |
|------|-----------|-------------------|
| Control | `openclaw` → `dispatch-send` | `in_host`: subagent Task with control pack; or `dual_session` prompt |
| Implementation | `claude-code` → `poc-dispatch --send` | `in_host`: subagent Task with isolated worktree + `allowed_write_root` |

Command MUST NOT write worker boundaries itself. Success = disk completion receipt.
