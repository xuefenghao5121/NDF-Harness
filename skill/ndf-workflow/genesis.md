# Genesis — 初始化（DESIGN_MAP 映射层）

[[META-009]] / track=`bootstrap`。`greenfield` | `adopt`。
已 accepted 的 operational 项目 **MUST NOT** 重跑。

```bash
python3 spec/meta/tools/ndf_workflow_status.py genesis-status --json
python3 spec/meta/tools/ndf_genesis_idea.py check docs/cycles/cycle-<id>.md
python3 spec/meta/tools/ndf_genesis_design_map.py check spec/open/project-genesis/DESIGN_MAP.md
```

## 人话

**Adopt（有源码）：**

```text
角色已配置 → 绑内核 → 派发(genesis_design) → GENESIS已审核
```

Control 从 Trunk @ SHA 归纳 observed design evidence。

**Greenfield（无源码）：**

```text
角色已配置 → 绑内核 → 派发(genesis_synthesis) → 架构已确认 → 派发(genesis_design) → 可以建立初始主线 → GENESIS已审核
```

Idea cycle 只进 synthesis；`DESIGN_MAP.md` 承担 adopt 中源码提供的信息面。

## G-1 角色向导

三角色 → 人 **角色已配置**。`roles_unbound` 不得派发。

## G0 绑内核（Command）

`FOUNDATION.md` + `GATES.md`。不写产品契约长文。

## G1a synthesis（greenfield）

`hop=genesis_synthesis`：Control **只**写 `spec/open/project-genesis/DESIGN_MAP.md`。
派发前 Command MUST `ndf_genesis_idea.py check` cycle 文件。

## G1b 架构已确认（greenfield）

人审 DESIGN_MAP bundle（cycle SHA + map SHA）→ **架构已确认** 写入 GATES。

## G1c design

`hop=genesis_design`：Control 从 **已审核** DESIGN_MAP（greenfield）或 Trunk observation（adopt）
物化 `spec/00–50`。greenfield 未 `架构已确认` → pack fail-closed。

## G2 仅 greenfield

「可以建立初始主线」→ `genesis-pack`。adopt 跳过。

## G3 GENESIS已审核

Command 冻结骨架 stable；基线欠账用 **继续**。

## Legacy

CHARTER/ARCHITECTURE 连派废弃；`genesis_per_draft_dispatch` fail-closed。
