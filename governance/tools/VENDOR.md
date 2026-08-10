# Tools layout

This package **ships** the review scripts under `governance/tools/`.

## Install into a target project

```bash
mkdir -p spec/meta/tools
cp -a governance/tools/ndf_*.py governance/tools/ndf_report_io.py \
  governance/tools/GOVERNANCE.md governance/tools/README.md \
  spec/meta/tools/
```

Or copy the whole `governance/tools/` directory contents into `spec/meta/tools/`.

## Sync policy

- **Local verified process** → refresh this package（本仓蒸馏方向）  
- **Published Harness repo** (`NDF-Harness`): tools live here for consumers  
- Optional: record upstream commit in target `spec/meta/tools/VENDOR-PIN.md` when you vendor from a specific tag  
- MUST NOT reverse-correct consumer `spec/meta/` from a lagging package without a process proposal

## Smoke

```bash
python3 spec/meta/tools/ndf_index.py --help
python3 spec/meta/tools/ndf_graphcheck.py --help
python3 spec/meta/tools/ndf_bindcheck.py --help
python3 spec/meta/tools/ndf_advise.py --help
python3 spec/meta/tools/ndf_close.py --help
python3 spec/meta/tools/ndf_poc_isolation.py --help
python3 spec/meta/tools/ndf_perf_baseline.py --help
```
