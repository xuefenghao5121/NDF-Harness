# Changelog

## 1.0.1 — 2026-08-24

Role-adapter fallback: three roles (Command / Control / Implementation) configured at
init; missing OpenClaw/Claude CLI falls back to `in-host` / `dual-session` / `custom`.
Adds `ndf_role_binding.py`, `roles/*` skill modules, `codex` adapter, Genesis gate
`角色已配置`, and `roles_unbound` dispatch hard door.

## 1.0.0 — 2026-08-24

Major release: text-first workflow, review-slice gates, migration tooling, and full docs set.

### Breaking / behavioral

- **Human entry** is five phrases via `skill/ndf-workflow/` (初始化项目 / 提交Idea / 派发 / 继续 / 关闭).
  Init/adopt/govern/sync are internal modules — not a public skill menu.
- **Gate identity** binds review-slice bundle SHA + `slice_manifest_sha`; whole-file gate SHA is legacy.
- **Commander / Episode / Replay / ActionSpec** retired (ADR-META-004); `ndf_replay.py` is tombstone only.
- **Success criterion** = disk `ndf-agent-completion/v1`; transport ACK is not success.
- **Installer** (`install.py`): `plan` | `install` | `adopt` | `verify`; protected SoT without `--force`.

### Added

- `migration/detect_0_2.py`, `migration/plan_1_0.md`, `migration/README.md`
- Full `docs/` set: ARCHITECTURE, INSTALL, WORKFLOW, TOOLS, ADAPTERS, MIGRATION-1.0,
  TROUBLESHOOTING, SECURITY, WORKFLOW-OVERVIEW
- Package root `README.md` rewrite as post-install entry
- Workflow tools: `ndf_context`, `ndf_dispatch_send`, `ndf_gate_slices`, `ndf_workflow_status` hot path,
  `ndf_acp_session_bootstrap`, `ndf_poc_dispatch`, `ndf_workflow_evidence`
- `ndf.workflow.yaml` + `workflow/profile.schema.json`
- Runtime adapters with SKILL wrappers (cursor, openclaw, claude-code, opencode, generic)
- `bin/ndf-harness` convenience launcher

### Docs

- Rewrote QUICKSTART / INIT / WORKFLOW-FEATURES to point at 1.0 install + five phrases
- Product-neutral prose (no domain-specific examples in package docs)

### Compatibility

- Consumer repos on 0.2.x: run `migration/detect_0_2.py` then follow `migration/plan_1_0.md`
- Legacy three-gate POC topics remain readable; hot path uses `bundle_dispatch` + 派发

## 0.2.0 — 2026-08-10

Distill from verified local NDF process (generic; no product SLA/module names).

### Docs

- Add `docs/WORKFLOW-FEATURES.md` — capability catalog distilled from META/process/tools

### Norms

- Add `language.md` (META-001…005)
- Expand `process.md`: BEH-018 write isolation + surface gating; BEH-025 explore_surface /
  baseline stale / sibling restart / `perf_baseline`; META-006 / META-007 perf-line duties
- Refresh meta ADRs (id-namespace, hygiene portable summary, poc-track, topic-binder)
- Product-tree stub: `50-verification/{configs,baselines}/` registry pattern

### Tools

- Sync governance CLIs from local SoT
- Add `ndf_report_io.py`, `ndf_poc_isolation.py`, `ndf_perf_baseline.py`
- Report UX: default `tmp/`; `--report -`; MUST NOT write under `spec/`

### Workflow / templates / skill

- `workflow/AGENTS.md`: isolation, perf baseline, close-plan, sibling restart
- `templates/poc/PERF_BASELINE.md.stub` + richer TOPIC stub
- `implementer-boundaries.md` aligned with BEH-018 §6
- `skill/MODES.md` govern/sync checklists updated

## 0.1.0

Initial portable harness skeleton.
