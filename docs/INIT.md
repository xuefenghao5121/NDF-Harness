# Init checklist

Greenfield and brownfield setup for NDF Harness 1.0. Human workflow uses **five phrases**
([`WORKFLOW.md`](WORKFLOW.md)), not a public init/adopt skill menu.

Install/adopt/govern/sync live under `skill/ndf-workflow/` as **internal** command-agent modules.

## Greenfield

1. Choose profile — default `dual-track` ([`ndf.profile.yaml`](../ndf.profile.yaml)).
2. Plan then install:

```bash
python3 packages/ndf-harness/install.py plan --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code

python3 packages/ndf-harness/install.py install --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code
```

3. Fill `AGENTS.md` ⟨TBD⟩ placeholders after human confirm.
4. Verify: `install.py verify --json`.
5. Baseline: `ndf_index index` + `ndf_graphcheck --meta`.
6. Start Genesis via command agent: **初始化项目**.

## Brownfield (adopt)

1. Scan legacy: `migration/detect_0_2.py --repo . --pretty`.
2. Adopt plan (no writes): `install.py adopt --json` — review `conflict` / `skip`.
3. Install without `--force` — preserves settled `AGENTS.md` and `spec/meta/*.md`.
4. Merge harness diffs manually where conflicts appear.
5. Migrate gates to review-slice SHA ([`MIGRATION-1.0.md`](MIGRATION-1.0.md)).
6. Verify + re-dispatch active topics after human **派发**.

**Never** silent-overwrite finalized AGENTS or meta clauses.

## Upgrade 0.2 → 1.0

Follow [`migration/plan_1_0.md`](../migration/plan_1_0.md) and [`MIGRATION-1.0.md`](MIGRATION-1.0.md).

## Related

- [`INSTALL.md`](INSTALL.md)
- [`QUICKSTART.md`](QUICKSTART.md)
- [`skill/ndf-workflow/install.md`](../skill/ndf-workflow/install.md) (internal)
