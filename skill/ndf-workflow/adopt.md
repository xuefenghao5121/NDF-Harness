# Adopt（internal）

Brownfield checklist — see [`../../docs/INIT.md`](../../docs/INIT.md) § Brownfield.

1. Scan existing `spec/`, `AGENTS.md`, misplaced root `tools/`.
2. Diff against package `norms/` + `workflow/AGENTS.md`; emit **gap report only**.
3. MUST NOT silent-overwrite finalized `AGENTS.md` or stable meta clauses.
4. Install missing tools into `spec/meta/tools/` per [VENDOR.md](../../governance/tools/VENDOR.md).
5. Optional: refresh adapters; point Command Agent at installed `skill/ndf-workflow/SKILL.md`.
6. Baseline: `ndf_graphcheck --meta` + product `--product` if tree exists.

Human entry remains [SKILL.md](SKILL.md).
