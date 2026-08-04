# Tools — included in this package

| Script | Role |
|--------|------|
| [`ndf_index.py`](ndf_index.py) | Index / `INDEX.md` + `graph.json` |
| [`ndf_graphcheck.py`](ndf_graphcheck.py) | Graph-semantics linter |
| [`ndf_bindcheck.py`](ndf_bindcheck.py) | Binder / ledger / trailer linter |
| [`ndf_advise.py`](ndf_advise.py) | Advisor (`--surface graph\|bind`); no SoT writes |
| [`ndf_advise_bind.py`](ndf_advise_bind.py) | Bind-surface advisor implementation |
| [`ndf_close.py`](ndf_close.py) | POC close **plan** only |

Install into a target repo as `spec/meta/tools/` (copy this directory).

Governance: [`GOVERNANCE.md`](GOVERNANCE.md) · daily commands: [`../docs/GOVERN.md`](../docs/GOVERN.md)

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_graphcheck.py --report tmp/ndf-graphcheck.md
```
