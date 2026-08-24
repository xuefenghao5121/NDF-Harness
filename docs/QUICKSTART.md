# Quickstart

Get NDF Harness 1.0 running in a consumer repo in minutes.

## 1. Install

```bash
HARNESS=packages/ndf-harness   # or path to vendored checkout

python3 "$HARNESS/install.py" install --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code

python3 "$HARNESS/install.py" verify --repo . --profile dual-track \
  --runtime cursor --runtime openclaw --runtime claude-code
```

Brownfield? Run [`migration/detect_0_2.py`](../migration/detect_0_2.py) and
[`install.py adopt`](../docs/INSTALL.md) first.

## 2. Baseline governance

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_graphcheck.py --meta
```

## 3. Use five phrases

Open your command agent (Cursor + `.cursor/skills/ndf-workflow/`). Say:

- **提交Idea** — start a proposal
- **派发** — after human review, authorize worker dispatch
- **继续** — amend and re-dispatch
- **关闭** — promote / partial / reject a topic
- **初始化项目** — greenfield Genesis

Do **not** use the old public init/adopt skill menu — install/adopt are via `install.py` only.

## Next reads

| Doc | When |
|-----|------|
| [`README.md`](../README.md) | full package tour |
| [`INSTALL.md`](INSTALL.md) | profiles and runtimes |
| [`WORKFLOW.md`](WORKFLOW.md) | tracks and gates |
| [`WORKFLOW-OVERVIEW.md`](WORKFLOW-OVERVIEW.md) | diagrams |
| [`INIT.md`](INIT.md) | greenfield vs brownfield checklist |

Version: [`VERSION`](../VERSION) · Changes: [`CHANGELOG.md`](../CHANGELOG.md)
