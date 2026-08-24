# Tools layout

This package **ships** the full governance CLI under `governance/tools/`.
Install copies them into the consumer repo at `spec/meta/tools/` — **no need to
fetch scripts from a separate maintainer repository**.

## Install into a target project

```bash
mkdir -p spec/meta/tools
cp -a governance/tools/ndf_*.py governance/tools/ndf_report_io.py \
  governance/tools/GOVERNANCE.md governance/tools/README.md \
  governance/tools/VENDOR.md \
  spec/meta/tools/
```

Or copy the entire `governance/tools/` directory contents into `spec/meta/tools/`.

## Shipped scripts (Harness 1.0)

| Script | Role |
|--------|------|
| `ndf_index.py` | Index / graph.json |
| `ndf_graphcheck.py` | Graph linter |
| `ndf_bindcheck.py` | Binder / trailer linter |
| `ndf_advise.py` / `ndf_advise_bind.py` | Advise (graph / bind surfaces) |
| `ndf_close.py` | Close plan (promote / partial / reject) |
| `ndf_poc_isolation.py` | POC write isolation |
| `ndf_perf_baseline.py` | Perf baseline card binding |
| `ndf_report_io.py` | Report path guard |
| `ndf_gate_slices.py` | Gate slice helpers |
| `ndf_context.py` | Pack context compiler |
| `ndf_workflow_evidence.py` | Workflow evidence I/O |
| `ndf_poc_dispatch.py` | POC dispatch pack builder |
| `ndf_workflow_status.py` | Workflow status / poc-dispatch / control-pack |
| `ndf_dispatch_send.py` | Pack send + completion wait |
| `ndf_acp_session_bootstrap.py` | ACP session bootstrap |
| `ndf_replay.py` | **Retired tombstone** (exit 2) |

## Sync policy

- **Local verified process** → refresh this package (maintainer distillation direction)
- Consumer installs from **this package** at install time; optional pin in
  `spec/meta/tools/VENDOR-PIN.md` (package version + source commit)
- MUST NOT reverse-correct consumer `spec/meta/` from a lagging package without a
  process proposal

## Smoke

```bash
python3 spec/meta/tools/ndf_index.py --help
python3 spec/meta/tools/ndf_graphcheck.py --help
python3 spec/meta/tools/ndf_bindcheck.py --help
python3 spec/meta/tools/ndf_advise.py --help
python3 spec/meta/tools/ndf_close.py --help
python3 spec/meta/tools/ndf_poc_isolation.py --help
python3 spec/meta/tools/ndf_perf_baseline.py --help
python3 spec/meta/tools/ndf_workflow_status.py --help
python3 spec/meta/tools/ndf_dispatch_send.py --help
python3 spec/meta/tools/ndf_replay.py   # expect exit 2
```
