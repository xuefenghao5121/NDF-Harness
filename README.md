# NDF Harness 1.0

> **role:** ndf-process-package  
> **product_behavior:** false  
> **version:** see [`VERSION`](VERSION)

Portable package that installs **NDF process norms**, **command workflow** (`AGENTS.md`),
**governance CLI**, **skills**, and **templates** into any repository. Works with Cursor,
OpenClaw, Claude Code, OpenCode, or generic agents — no single IDE is required.

## What Harness is / is not

| Harness **is** | Harness **is not** |
|----------------|-------------------|
| A distilled, product-neutral process seed | Your project's specification SoT |
| Install scaffolding + governance tools | Automatic spec or code mutation |
| Runtime adapters (thin pointers) | A replacement for human gate phrases |
| Migration helpers for 0.2 → 1.0 | Authority over settled local `spec/meta/` |

**One-way flow:** verified practice in a consumer repo → distill into this package → redistribute.
Never use the package to reverse-correct a consumer's authoritative `spec/meta/`.

## 30-second install

```bash
cd /path/to/consumer-repo
python3 /path/to/ndf-harness/install.py install \
  --profile dual-track \
  --runtime cursor,openclaw,claude-code
python3 /path/to/ndf-harness/install.py verify --repo . --profile dual-track \
  --runtime cursor,openclaw,claude-code
```

Then open your command agent and use the **five phrases** (see [Workflow](#five-phrases--typical-session)).

## Install modes

| Mode | Command | Use when |
|------|---------|----------|
| **Greenfield** | `install.py install` | New repo; no `spec/` yet |
| **Brownfield adopt** | `install.py adopt` (plan only) then `install` | Existing NDF tree; review conflicts first |
| **Upgrade 0.2→1.0** | `migration/detect_0_2.py` + [`migration/plan_1_0.md`](migration/plan_1_0.md) | Legacy gates or Commander residue |

Details: [`docs/INSTALL.md`](docs/INSTALL.md) · [`docs/MIGRATION-1.0.md`](docs/MIGRATION-1.0.md)

## Five phrases + typical session

Human cognitive contract (唯一入口 — [`skill/ndf-workflow/SKILL.md`](skill/ndf-workflow/SKILL.md)):

| Phrase | Purpose |
|--------|---------|
| **初始化项目** | Project Genesis bootstrap |
| **提交Idea** | New proposal (product or process plane) |
| **派发** | Authorize dispatch after human review |
| **继续** | Amend binder / re-dispatch |
| **关闭** | Close topic (promote / partial / reject) |

Typical POC session:

```text
提交Idea → 已确认 → 已审核 → 装订器 written → 派发 → worker completion on disk
→ 继续 (amend?) → 派发 → … → 关闭
```

Full workflow: [`docs/WORKFLOW.md`](docs/WORKFLOW.md) · [`docs/WORKFLOW-OVERVIEW.md`](docs/WORKFLOW-OVERVIEW.md)

## Profile, runtime, layout

**Profiles** (`ndf.profile.yaml`):

| Profile | Norms | Tools | AGENTS | POC |
|---------|-------|-------|--------|-----|
| `dual-track` | full | full | required | yes |
| `minimal` | slim | index + graphcheck | required | no |
| `linter-only` | none | full | optional | no |

**Runtimes:** `cursor` · `openclaw` · `claude-code` · `opencode` · `generic`

**Install map:**

| Package path | Lands in consumer |
|--------------|-------------------|
| `norms/meta/` | `spec/meta/` |
| `norms/product-tree/` | `spec/` skeleton |
| `governance/tools/*.py` | `spec/meta/tools/` |
| `workflow/AGENTS.md` | `AGENTS.md` |
| `workflow/ndf.workflow.yaml` | `ndf.workflow.yaml` |
| `skill/ndf-workflow/` | runtime skill dir (see adapter) |
| `templates/` | `spec/meta/templates/` |

## Verify

```bash
python3 install.py verify --repo . --profile dual-track --runtime cursor --json
```

Checks: VERSION, AGENTS, workflow yaml, tool `--help` smoke, skill entry paths, optional CLI availability.

## Common blockers

| Blocker | Doc |
|---------|-----|
| Gate / bundle SHA mismatch | [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) |
| `context_verify_failed` | [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) |
| graphcheck / bindcheck failures | [`docs/TOOLS.md`](docs/TOOLS.md) |
| Wrong workspace / repo_root | [`docs/SECURITY.md`](docs/SECURITY.md) |
| Fake or missing completion | [`docs/SECURITY.md`](docs/SECURITY.md) |

## Version / compatibility

- Current: **1.0.0** ([`CHANGELOG.md`](CHANGELOG.md))
- 0.2.x repos: run [`migration/detect_0_2.py`](migration/detect_0_2.py)
- Installed consumer `spec/meta/` wins over package after adopt

## Uninstall

Harness does not track uninstall manifests. Remove installed copies manually:

- `spec/meta/tools/ndf_*.py` (if only from harness)
- Runtime skill directories (`.cursor/skills/ndf-workflow/`, etc.)
- Optionally revert `AGENTS.md` / `ndf.workflow.yaml` via git

Do **not** delete consumer-authored `spec/meta/` clauses or POC binders.

## Documentation index

| Doc | Topic |
|-----|-------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, dispatch pipeline, security boundaries |
| [`docs/INSTALL.md`](docs/INSTALL.md) | Profiles, runtimes, exact commands |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | Tracks, gates, close modes |
| [`docs/WORKFLOW-OVERVIEW.md`](docs/WORKFLOW-OVERVIEW.md) | Call graph + closed loops |
| [`docs/WORKFLOW-FEATURES.md`](docs/WORKFLOW-FEATURES.md) | Capability catalog from META |
| [`docs/TOOLS.md`](docs/TOOLS.md) | Every shipped governance script |
| [`docs/ADAPTERS.md`](docs/ADAPTERS.md) | Runtime capability matrix |
| [`docs/MIGRATION-1.0.md`](docs/MIGRATION-1.0.md) | 0.2 / legacy POC upgrade |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Operational fixes |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Fail-closed gates |
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Short path to first verify |
| [`docs/INIT.md`](docs/INIT.md) | Greenfield vs brownfield checklist |
| [`migration/README.md`](migration/README.md) | Migration tool index |
| [`governance/docs/GOVERN.md`](governance/docs/GOVERN.md) | Governance command card |

## Package layout

```text
packages/ndf-harness/
├── install.py          # plan | install | adopt | verify
├── ndf.profile.yaml    # profile selector
├── norms/              # meta + product-tree seed
├── workflow/           # AGENTS.md + ndf.workflow.yaml
├── governance/tools/   # ndf_*.py CLI
├── skill/ndf-workflow/ # five-phrase command skill
├── adapters/           # runtime mounts
├── templates/          # POC / genesis stubs
├── migration/          # 0.2 detect + plan
└── docs/               # product-neutral guides
```
