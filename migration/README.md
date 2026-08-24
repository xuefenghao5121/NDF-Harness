# Migration (0.2 → 1.0)

Tools and plans for upgrading consumer repositories to NDF Harness 1.0.0.

| File | Purpose |
|------|---------|
| [`detect_0_2.py`](detect_0_2.py) | Scan repo; emit JSON findings (exit 0; I/O errors exit 2) |
| [`plan_1_0.md`](plan_1_0.md) | Human migration checklist: adopt → diff → gates → retire → re-dispatch |

Quick start:

```bash
python3 migration/detect_0_2.py --repo /path/to/consumer --pretty
```

Product-neutral migration guide: [`../docs/MIGRATION-1.0.md`](../docs/MIGRATION-1.0.md).
