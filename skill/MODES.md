# Mode checklists

## init (greenfield)

```text
- [ ] Choose profile: dual-track (default) | minimal | linter-only
- [ ] Copy norms/meta → spec/meta/
- [ ] Copy ndf.yaml.stub → spec/ndf.yaml (⟨TBD⟩)
- [ ] Create empty product-tree dirs under spec/
- [ ] Install workflow/AGENTS.md → repo root   ★ required unless linter-only
- [ ] Install governance docs → spec/meta/tools/ (README + GOVERNANCE pointer)
- [ ] Copy `governance/tools/ndf_*.py` → `spec/meta/tools/`（见 VENDOR.md）
- [ ] Optional: install one adapters/<runtime>/
- [ ] dual-track: poc/README + example binder templates/
- [ ] Status: Draft — wait for 「已确认生成」/「已确认」
- [ ] After confirm: fill ⟨TBD⟩; run index + graphcheck baseline → tmp/
```

## adopt (brownfield)

```text
- [ ] Detect existing spec/meta, AGENTS.md, tools location
- [ ] Report gaps (missing binder, tools under wrong path, no AGENTS)
- [ ] Propose stubs alongside; do not overwrite finalized files
- [ ] Optional baseline: graphcheck/bindcheck → tmp/ndf-baseline-*.md
```

## govern

```text
- [ ] python3 spec/meta/tools/ndf_index.py index
- [ ] python3 spec/meta/tools/ndf_graphcheck.py --report tmp/ndf-graphcheck.md
- [ ] python3 spec/meta/tools/ndf_bindcheck.py --report tmp/ndf-bindcheck.md
- [ ] python3 spec/meta/tools/ndf_advise.py plan --surface graph|bind ...
- [ ] optional: ndf_poc_isolation.py check --all-topics
- [ ] optional: ndf_perf_baseline.py check --all-exploring
- [ ] optional simulate; remind sandbox ≠ apply
- [ ] human edits SoT via proposal discipline → recheck
- [ ] POC close: ndf_close.py plan --topic <t> --mode promote|reject|partial
- [ ] MUST NOT write check reports under spec/ (use tmp/ or --report -)
```

## sync

```text
- [ ] Compare package VERSION vs installed seed notes
- [ ] Refresh CLAUSE-FORMAT / GOVERNANCE / VENDOR / tools (incl. report_io, isolation, perf_baseline)
- [ ] Diff norms/meta process+language vs package; never silent overwrite consumer edits
- [ ] Diff AGENTS.md; never silent overwrite
```
