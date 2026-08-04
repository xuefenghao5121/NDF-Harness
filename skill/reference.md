# Skill reference

## Path rules

1. Process SoT → `spec/meta/**`  
2. Product SoT → `spec/00–50`  
3. Review tools → `spec/meta/tools/` only（not product `scripts/`）  
4. Workflow entry → repo-root `AGENTS.md`  
5. Skill core → `packages/ndf-harness/skill/`（or vendored copy）；adapters are thin  

## Overlay policy

| Target exists | Action |
|---------------|--------|
| Human-finalized | Propose patch / side-by-side `*.stub.md` only |
| Stub only | Refresh skeleton; keep answered ⟨TBD⟩ |
| Missing | Copy from package |

## Confirm gate

Do not fill ⟨TBD⟩ or claim init complete until human says confirm（「已确认」/「已确认生成」）.
