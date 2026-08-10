# Verification tree — config & baseline registry (stub)

Portable layout for locking **code SHA × config identity × measured numbers**.
Product fills concrete ids; process obligations are [[META-006]] / [[META-007]].

```text
spec/50-verification/
  configs/
    README.md          # index of cfg-*
    cfg-<id>.md        # full measurement knobs / env
  baselines/
    README.md          # index of bl-*
    bl-trunk-<sha>.md  # trunk_sha + config_id(s) + numbers
    PERF_BASELINE.topic-template.md  # optional; or use package templates/poc/
  golden-baseline.md   # thin index → current bl-* + cfg-* (optional name)
```

## Rules (generic)

1. SLA / constraint clauses = contractual floors; measured lines live here  
2. Config-only change → new or bumped `cfg-*` (or topic-local experimental full env)  
3. New trunk measurements → new `bl-trunk-<shortsha>` (do not silently rewrite cited ids)  
4. POC: `poc/<topic>/ndf/PERF_BASELINE.md` points at `config_id` / `vs:` baseline  

See package `templates/poc/PERF_BASELINE.md.stub`.
