# Implementer boundaries（通用片段）

Map into runtime-specific files（e.g. `.claude/CLAUDE.md`）.

## Never

- Edit `spec/meta/`（process profile）unless track=process and the command / control agent already landed the proposal  
- Edit L0/L1 product clauses without an Implemented proposal  
- Put production-path experiments into `spec/models/`  
- On **poc** track: modify Trunk `src/**`、`include/**`、`tests/**`（[[BEH-018]] §6）；
  copy headers/sources into `poc/<topic>/` before editing; MAY read-only link unmodified Trunk  
- On **poc** track: write exploration metrics into stable product SLA must（[[CON-POC-001]]）  
- Compare Δ% without reading TOPIC → `perf_baseline` card（[[META-007]]）

## May

- **poc**: `poc/<topic>/` + binder + `PERF_BASELINE.md` + evidence  
- **promote / bug / refactor**: Trunk implementation, tests, `50-verification/`, L2/L3 after 「已审核」

## Should run

```bash
python3 spec/meta/tools/ndf_poc_isolation.py check --topic <topic>
python3 spec/meta/tools/ndf_perf_baseline.py check --topic <topic>
```

Commit trailers when touching POC/promote: `Topic:` / `Proposals:` / `Clauses:`（+ `Promotes:` / `Rejects:` as applicable）.
