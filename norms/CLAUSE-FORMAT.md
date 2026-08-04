# NDF clause format

一句话纪律：**散文活在树里，语义活在图里，时间活在 git 里——稳定的条款 ID 是铆钉。**

## Clause skeleton

```markdown
## 条款标题 {#PREFIX-AREA-NNN}
<!-- ndf: kind=<kind> level=<level> layer=<layer> status=<status> since=<version> -->
<!-- ndf: refines=<PARENT-ID> depends-on=<DEP-ID> -->

条款正文。MUST / SHOULD / MAY 全部大写。

1. 可测试条件
2. 用 [[OTHER-ID]] 交叉引用

> rationale: 设计依据
```

### Metadata

| Field | Required | Values |
|-------|----------|--------|
| `kind` | yes | `req` / `def` / `arch` / `constraint` / `option` / `verif` / `info` |
| `level` | yes | `must` / `should` / `may` / `tbd` |
| `layer` | yes | `L0` / `L1` / `L2` / `L3` |
| `status` | yes | `draft` / `stable` / `deprecated` / … |
| `scope` | process clauses | `ndf-process` for meta profile |

### Edge keys (graph)

Allowed meta edges: `refines`, `depends-on`, `verifies`, `conflicts-with`,
`affects`, `superseded-by`, `couples-with`, `model`.

Process clauses live in `spec/meta/`；product behavior in `spec/00–50`.
Pure process IDs MUST NOT be listed as product-tree adopted must.
