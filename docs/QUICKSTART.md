# QUICKSTART

1. **Norms** — copy `norms/meta/` → `spec/meta/`（含 `language.md` + `process.md` META-006/007）；
   `ndf.yaml.stub` → `spec/ndf.yaml`；create empty product dirs（见 `norms/product-tree/README.md`）。
   Dual-track：复制 `product-tree/50-verification/{configs,baselines}/` 骨架。  
2. **AGENTS** — copy `workflow/AGENTS.md` → repo root；fill ⟨TBD⟩ after human confirm.  
3. **Tools** — copy `governance/tools/ndf_*.py` + `ndf_report_io.py` + `GOVERNANCE.md` + `README.md`
   → `spec/meta/tools/`（见 `VENDOR.md`）。  
4. **Templates** — `templates/poc/{TOPIC,PERF_BASELINE,COMMITS}.md.stub` → 新 POC 装订器。  
5. **Adapter（optional）** — pick `adapters/generic|openclaw|claude-code|opencode|cursor`.  
6. **Baseline** — run commands in `governance/docs/GOVERN.md`；reports under `tmp/`
   （MUST NOT under `spec/`）；可选 `ndf_poc_isolation` / `ndf_perf_baseline`。

Skill modes: read `skill/SKILL.md`. Package version: see `VERSION` / `CHANGELOG.md`.
