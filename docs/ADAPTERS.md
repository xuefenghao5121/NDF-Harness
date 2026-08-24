# Adapters

Runtime adapters mount the same `skill/ndf-workflow/` core. They do **not** fork workflow prose.

Business SoT: installed `AGENTS.md` + `spec/meta/` + `skill/ndf-workflow/SKILL.md`.

## Capability matrix

| Capability | generic | cursor | openclaw | claude-code | opencode |
|------------|---------|--------|----------|-------------|----------|
| Five-phrase human entry | available | available | available | available | available |
| Skill tree install | unsupported | available | available | available | available |
| Command agent (orchestration) | available | available | unsupported | unsupported | available |
| OpenClaw control dispatch | unsupported | available¹ | available | available¹ | available¹ |
| Claude Code ACP dispatch | unsupported | available¹ | available¹ | available | available¹ |
| Context verify in pack | available | available | available | available | available |
| Gate slice drift UI | available | available | available | available | available |
| Per-project workspace state | available | available | available | available | available |
| Genesis bootstrap | available | available | available | available | available |
| POC poc-dispatch | available | available | available | available | available |
| Promote close merge | available | available | available | available | available |
| Init/adopt public menu | **unsupported** | **unsupported** | **unsupported** | **unsupported** | **unsupported** |
| Commander / Replay panel | **unsupported** | **unsupported** | **unsupported** | **unsupported** | **unsupported** |

¹ Requires respective CLI on PATH (`openclaw`, `claude`). Installer verify reports
`available` or `unsupported`; dispatch fails closed if missing.

## Mount paths

| Runtime | Install destination | Wrapper |
|---------|---------------------|---------|
| generic | *(none)* | Tell agent to read package `skill/ndf-workflow/SKILL.md` |
| cursor | `.cursor/skills/ndf-workflow/` | [`adapters/cursor/SKILL.md`](../adapters/cursor/SKILL.md) |
| openclaw | `skills/ndf-harness/` | [`adapters/openclaw/SKILL.md`](../adapters/openclaw/SKILL.md) |
| claude-code | `.claude/skills/ndf-harness/` | [`adapters/claude-code/SKILL.md`](../adapters/claude-code/SKILL.md) |
| opencode | `.opencode/skills/ndf-harness/` | [`adapters/opencode/SKILL.md`](../adapters/opencode/SKILL.md) |

Install:

```bash
python3 install.py install --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code
```

## generic

No files copied. Document in project README:

```text
Read AGENTS.md and skill/ndf-workflow/SKILL.md (from ndf-harness package).
```

Best for custom agent hosts or CI-only linter profiles.

## cursor

Recommended command surface. Skill at `.cursor/skills/ndf-workflow/` copies or symlinks
package skill tree. Human uses five phrases in Cursor chat.

## openclaw

Control-plane agent for proposals and binders. Requires:

- Root `AGENTS.md` from harness workflow
- Optional `skills/ndf-harness/` pointer
- Per-repo workspace state template under `spec/meta/templates/openclaw/`

Dispatch via `ndf_dispatch_send.py` (not raw chat from command agent).

## claude-code

Implementation plane. Requires:

- `.claude/skills/ndf-harness/` skill pointer
- `.claude/CLAUDE.md` implementer boundaries (from install)
- ACP session bootstrap: `ndf_acp_session_bootstrap.py`

## opencode

Same skill pointer pattern as claude-code under `.opencode/skills/ndf-harness/`.

## Adding a runtime

1. Create `adapters/<name>/README.md` + `SKILL.md` wrapper.
2. Add path to `ndf.profile.yaml` `runtime_skill_paths`.
3. Register in `install.py` `RUNTIME_SKILL_DIRS`.
4. Extend matrix in this file.

Do **not** duplicate `skill/ndf-workflow/*.md` prose into adapters.

## Related

- [`INSTALL.md`](INSTALL.md)
- [`../adapters/README.md`](../adapters/README.md)
