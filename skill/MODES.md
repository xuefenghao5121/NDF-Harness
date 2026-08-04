# Mode checklists

## init (greenfield)

```text
- [ ] Choose profile: dual-track (default) | minimal | linter-only
- [ ] Copy norms/meta → spec/meta/
- [ ] Copy ndf.yaml.stub → spec/ndf.yaml (⟨TBD⟩)
- [ ] Create empty product-tree dirs under spec/
- [ ] Install workflow/AGENTS.md → repo root   ★ required unless linter-only
- [ ] Install governance docs → spec/meta/tools/ (README + GOVERNANCE pointer)
- [ ] Obtain tools per VENDOR.md
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
- [ ] optional simulate; remind sandbox ≠ apply
- [ ] human edits SoT via proposal discipline → recheck
- [ ] POC close: ndf_close.py plan --topic <t> --mode promote|reject|partial
```

## sync

```text
- [ ] Compare package VERSION vs installed seed notes
- [ ] Refresh CLAUSE-FORMAT / GOVERNANCE / VENDOR as needed
- [ ] Diff AGENTS.md; never silent overwrite
```
