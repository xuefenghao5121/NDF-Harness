# Changelog

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
