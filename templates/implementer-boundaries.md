# Implementer boundaries（通用片段）

Map into runtime-specific files（e.g. `.claude/CLAUDE.md`）.

## Never

- Edit `spec/meta/`（process profile）unless track=process and commander already landed the proposal  
- Edit L0/L1 product clauses without an Implemented proposal  
- Put production-path experiments into `spec/models/`  
- On **poc** track: change Trunk production defaults（e.g. under `src/`）

## May

- **poc**: `poc/<topic>/` + binder updates + evidence  
- **promote / bug / refactor**: Trunk implementation, tests, `50-verification/`, L2/L3 after 「已审核」

Commit trailers when touching POC/promote: `Topic:` / `Proposals:` / `Clauses:`（+ `Promotes:` / `Rejects:` as applicable）.
