# Tools VENDOR

## Single implementation source (stage A)

Python review tools are **not** dual-copied into this package.

| Artifact | Source of truth |
|----------|-----------------|
| `ndf_index.py` | maintaining repo `spec/meta/tools/ndf_index.py` |
| `ndf_graphcheck.py` | same directory |
| `ndf_bindcheck.py` | same |
| `ndf_advise.py` / `ndf_advise_bind.py` | same |
| `ndf_close.py` | same |
| Full GOVERNANCE | maintaining repo `spec/meta/tools/GOVERNANCE.md` |

## How to obtain

1. Copy or submodule the `spec/meta/tools/*.py` (+ `README.md`, `GOVERNANCE.md`) into the target repo `spec/meta/tools/`.  
2. Or pin a release tag / path of the maintaining repository.  
3. Record the pin in the target repo（commit SHA or tag） under `spec/meta/tools/VENDOR-PIN.md`（create on install）.

## Install check

```bash
python3 spec/meta/tools/ndf_index.py --help
python3 spec/meta/tools/ndf_graphcheck.py --help
```
