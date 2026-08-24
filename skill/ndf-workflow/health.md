# Health — 只读诊断

人问「健康 / 漂移 / graphcheck / topic 是否可派发」时用。**不**改契约、不派发。

```bash
python3 spec/meta/tools/ndf_workflow_status.py topic-health --topic <topic> --json
python3 spec/meta/tools/ndf_workflow_status.py spec-health --json
```

可选：

```bash
python3 spec/meta/tools/ndf_index.py validate
python3 spec/meta/tools/ndf_graphcheck.py --meta   # 或 --product
python3 spec/meta/tools/ndf_poc_isolation.py check --topic <topic>
python3 spec/meta/tools/ndf_workflow_status.py host-pids --json  # EAGAIN / fork
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
```

## 报告要点

- `state` / blockers / SHA 是否对齐
- 闸 `invalidated` 时 MUST 展示 `gate_drift` / `gate_drift_markdown`（或
  `tmp/ndf-gate-drift-<topic>.md`）：changed slices + unified diff；禁止只报两个 hex
- 是否 `safe_to_dispatch` 相关前置（装订器、闸、隔离）
- 修复建议指向 [proposal.md](proposal.md) / [poc.md](poc.md) / 人工口令——勿静默伪造 approval

无面板义务：不启 serve、不打开可视化宿主。
