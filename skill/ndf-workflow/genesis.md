# Genesis — 初始化（绑内核 → 一次派发 → 审核冻结）

[[META-009]] / track=`bootstrap`。`greenfield` | `adopt`。
已 accepted 的 operational 项目 **MUST NOT** 重跑。

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
```

## 人话（尽量少）

```text
角色已配置 → 派发 → GENESIS已审核
```

（greenfield 可多一句：`可以建立初始主线`。）

## G-1 角色向导

三角色写入 `ndf.workflow.yaml` → 人 **角色已配置**。`roles_unbound` 不得派发。

## G0 绑内核（Command）

写 `FOUNDATION.md` + `GATES.md`。不写产品契约长文。

## G1 一次「派发」

`hop=genesis_design`：

Greenfield `source_ref` MUST 为填写完整的 `ndf-genesis-idea/v1`
（`TASK_ORDER.md.stub` / `docs/cycles/cycle-<id>.md`）。多阶段散文路书 MUST NOT
当设计 hop 输入。造 pack 前：

```bash
python3 spec/meta/tools/ndf_genesis_idea.py check docs/cycles/cycle-<id>.md
```

非法 → fail-closed，不得派发。

1. Control：按 Mapping 表写 **骨架** `spec/00–50`（及必要 decisions/INDEX）；
   条款预算 ≤20；默认 `draft` / L0。Guidance MUST NOT 进 BEH/API/CON-SLA must。
2. 同句：复现 `make test` + VER 金标/sustained → `configs/` + `baselines/`（绑 Trunk SHA）

测不出：completion 标 `baseline_status=deferred`；人说 **继续** 补测。

## G2 仅 greenfield

「可以建立初始主线」→ 一次 `genesis-pack`。adopt 跳过。

## G3 「GENESIS已审核」

Command 落地（不另派）：

- 骨架（非 SLA）→ **stable** = 优化/二次开发对照目标
- 已复现基线与对应 SLA → **stable**
- 未复现 SLA → 留 `not-established`
- 项目 → operational

MUST NOT 再教用户走一轮日常 promote 才 stable 骨架。

## Legacy

CHARTER/ARCHITECTURE/VERIFICATION 连派已废弃；`genesis_per_draft_dispatch` fail-closed。
