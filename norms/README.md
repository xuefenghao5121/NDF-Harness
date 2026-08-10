# NDF norms seed

Install into the target repo as `spec/` process profile + empty product tree.

| Source here | Target path |
|-------------|-------------|
| `ndf.yaml.stub` | `spec/ndf.yaml`（填写 ⟨TBD: project⟩） |
| `CLAUSE-FORMAT.md` | keep as reference or `spec/meta/CLAUSE-FORMAT.md` |
| `meta/*` | `spec/meta/*`（含 `language.md`、META-006/007） |
| `product-tree/*` | `spec/00-charter` … `50-verification` + `open/` + `decisions/` |
| `product-tree/50-verification/{configs,baselines}` | 配置/基线注册表骨架（消费仓填身份） |

**MUST** strip any product-domain clauses before shipping updates to this seed.
