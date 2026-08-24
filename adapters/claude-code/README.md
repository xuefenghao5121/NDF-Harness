# Adapter: Claude Code

1. Root `AGENTS.md` remains the workflow SoT for any command / control session.  
2. Install implementer boundaries from `templates/implementer-boundaries.md` into `.claude/CLAUDE.md`（or merge）.  
3. Optional skill mount:

```text
.claude/skills/ndf-workflow/SKILL.md  →  packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

4. Claude Code is typically the **实现 Agent**：poc → `poc/` only；promote → Trunk implementation after 「已审核」.

See [`SKILL.md`](SKILL.md) wrapper.
