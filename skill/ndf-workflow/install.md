# Install（internal）

Greenfield checklist — full detail in [`../../docs/INIT.md`](../../docs/INIT.md).

1. Confirm profile in `ndf.profile.yaml`（default `dual-track`）.
2. Copy `norms/` → consumer `spec/meta/`（merge; do not overwrite finalized clauses）.
3. Install `workflow/AGENTS.md` → repo root `AGENTS.md`.
4. Copy `governance/tools/` → `spec/meta/tools/`（see [`../../governance/tools/VENDOR.md`](../../governance/tools/VENDOR.md)）.
5. Mount skill via [`../../adapters/<runtime>/`](../../adapters/)（Command Agent reads `skill/ndf-workflow/SKILL.md`）.
6. Smoke: `ndf_index index` + `ndf_graphcheck --meta`.
7. Wait for human confirm before filling ⟨TBD⟩ product tree slots.

Human entry remains [SKILL.md](SKILL.md) — do not expose this file to end users.
