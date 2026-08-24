# Adapter: Claude Code

1. Root `AGENTS.md` remains the workflow SoT for any command / control session.  
2. Install implementer boundaries from `templates/implementer-boundaries.md` into `.claude/CLAUDE.md`（or merge）.  
3. Optional skill mount:

```text
.claude/skills/ndf-workflow/SKILL.md  →  packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

4. Claude Code is typically the **实现 Agent**：poc → `poc/` only；promote → Trunk implementation after 「已审核」.

See [`SKILL.md`](SKILL.md) wrapper.

## How this host spawns Control/Implementation children

Claude Code is typically the **Implementation** adapter:

| Path | Mechanism |
|------|-----------|
| Preferred | `poc-dispatch --send` / ACP `genesis-pack` with isolated worktree |
| `in_host` | N/A when Claude is Implementation — Command spawns into this session |
| `dual_session` | Human pastes Implementation role prompt + pack into a Claude Code chat |

Control on this host: resolve to `openclaw` via Command's `dispatch-send`, or `dual_session`.
