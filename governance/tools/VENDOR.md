# Tools layout

This package **ships** the review scripts under `governance/tools/`.

## Install into a target project

```bash
mkdir -p spec/meta/tools
cp -a governance/tools/ndf_*.py governance/tools/GOVERNANCE.md \
  governance/tools/README.md \
  spec/meta/tools/
```

Or copy the whole `governance/tools/` directory contents into `spec/meta/tools/`.

## Sync policy

- **Published Harness repo** (`NDF-Harness`): tools live here for consumers.  
- Optional: record upstream commit in target `spec/meta/tools/VENDOR-PIN.md` when you vendor from a specific tag.

## Smoke

```bash
python3 spec/meta/tools/ndf_index.py --help
python3 spec/meta/tools/ndf_graphcheck.py --help
python3 spec/meta/tools/ndf_bindcheck.py --help
python3 spec/meta/tools/ndf_advise.py --help
python3 spec/meta/tools/ndf_close.py --help
```
