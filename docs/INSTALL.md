# Install

Exact commands for installing NDF Harness 1.0 into a consumer repository.

## Prerequisites

- Python 3.10+ (stdlib only — no pip dependencies for installer)
- Git repository root as `--repo`
- Write access to target paths

## Harness location

Either vendor the package:

```bash
git subtree add …   # or copy packages/ndf-harness into consumer
```

Or reference an external checkout:

```bash
HARNESS=/path/to/ndf-harness
python3 "$HARNESS/install.py" …
```

## Commands

| Command | Writes disk? | Purpose |
|---------|--------------|---------|
| `plan` | No | Show create/update/skip/conflict items |
| `adopt` | No | Brownfield plan (same as plan, mode=adopt) |
| `install` | Yes | Apply scaffold |
| `verify` | No | Post-install smoke |

Common flags:

```text
--repo PATH          consumer root (default: cwd)
--profile NAME       dual-track | minimal | linter-only
--runtime NAME       repeatable: cursor, openclaw, claude-code, opencode, generic
--force              overwrite protected AGENTS.md / spec/meta/*.md (dangerous)
--json               JSON output
```

## Profiles

### dual-track (default)

Full explore/promote workflow.

```bash
python3 install.py plan --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code

python3 install.py install --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code
```

**Installs:**

- Full `norms/meta/` → `spec/meta/`
- Product tree skeleton → `spec/{00-charter,10-architecture,…}/`
- All governance tools → `spec/meta/tools/`
- `workflow/AGENTS.md` → `AGENTS.md` (skip if exists, unless `--force`)
- `workflow/ndf.workflow.yaml` → `ndf.workflow.yaml`
- Templates → `spec/meta/templates/`
- Skill tree → runtime paths (below)

### minimal

Slim norms + index/graphcheck only.

```bash
python3 install.py install --repo . --profile minimal --runtime generic
```

**Installs:** slim meta files, AGENTS, workflow yaml, `ndf_index.py`, `ndf_graphcheck.py`.

### linter-only

Governance CLI without norms or AGENTS requirement.

```bash
python3 install.py install --repo . --profile linter-only
```

Useful for CI graph gates on repos that already have custom AGENTS/spec.

## Runtimes — what lands where

| Runtime | Skill destination | Extra files |
|---------|-------------------|-------------|
| **generic** | none (read `skill/ndf-workflow/SKILL.md` in package) | — |
| **cursor** | `.cursor/skills/ndf-workflow/` | copy skill tree |
| **openclaw** | `skills/ndf-harness/` | `spec/meta/templates/openclaw/state.json.example` |
| **claude-code** | `.claude/skills/ndf-harness/` | `.claude/CLAUDE.md` from implementer boundaries |
| **opencode** | `.opencode/skills/ndf-harness/` | copy skill tree |

Repeat `--runtime` for multiple adapters:

```bash
python3 install.py install --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code --runtime opencode
```

See [`ADAPTERS.md`](ADAPTERS.md) for capability matrix.

## Brownfield adopt

**Never silent-overwrite settled SoT.**

```bash
# 1. Detect legacy
python3 migration/detect_0_2.py --repo . --pretty

# 2. Plan only
python3 install.py adopt --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code --json

# 3. Review conflicts, then install without --force
python3 install.py install --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code
```

Protected without `--force`:

- Existing `AGENTS.md`
- Existing `spec/meta/*.md` process clauses
- Append-only gate files

## Verify

```bash
python3 install.py verify --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code --json
```

Exit codes: `0` ok, `2` failures (missing tools, skill entry, etc.).

Verify also reports optional CLI availability:

- `openclaw` → `available` | `unsupported`
- `claude` → `available` | `unsupported`

Missing CLIs do not fail verify; dispatch will fail-closed at runtime.

## Post-install baseline

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_graphcheck.py --meta
```

Reports → `tmp/` (gitignored).

## Upgrade from 0.2

See [`MIGRATION-1.0.md`](MIGRATION-1.0.md) and [`../migration/plan_1_0.md`](../migration/plan_1_0.md).

## Uninstall

No automated uninstall. Revert via git or remove:

- `spec/meta/tools/ndf_*.py` (harness copies)
- `.cursor/skills/ndf-workflow/` (or symlink)
- Other runtime skill dirs

Keep consumer-authored spec and POC content.

## Related

- [`QUICKSTART.md`](QUICKSTART.md)
- [`INIT.md`](INIT.md)
- [`../ndf.profile.yaml`](../ndf.profile.yaml)
