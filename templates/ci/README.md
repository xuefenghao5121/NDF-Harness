# Optional CI stub

Example job idea（adapt to your CI）:

```yaml
# ndf-graphcheck:
#   script:
#     - python3 spec/meta/tools/ndf_index.py index
#     - python3 spec/meta/tools/ndf_graphcheck.py
```

Not enabled by default; product pipelines stay separate from NDF review tools.
