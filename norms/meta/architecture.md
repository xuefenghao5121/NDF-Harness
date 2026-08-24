# Meta Architecture — POC / models 边界

> scope: ndf-process  
> 条款索引: `ARCH-008`  
> 产品树 adopted 指针: `10-architecture/modules.md`

## `models/` 与 `poc/` 边界 {#ARCH-008}
<!-- ndf: kind=arch level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-020,DEF-021 -->

1. `spec/models/` MUST 只承载 NDF L3 **参考模型**（可重复、可测试、由条款 `model=` 引用）。
2. 探索性生产路径改动（含 **头文件与实现源**）MUST 落在仓库根目录 `poc/<topic>/`
   （或专用 `poc/<topic>` git 分支），MUST NOT 伪装为 `spec/models/` 参考模型，
   MUST NOT 以「只改 `include/`」绕过本条（写入隔离见 [[BEH-018]] 第 6 条）。
3. `poc/` MUST 在 `ndf.yaml` 中声明为 **非 SoT**（与 `archive/` 同类：`sot: false`）。
4. 允许在 `spec/models/poc-notes/` 仅存放**与参考模型对照的算法草稿**；不得在此提交
   链入生产二进制的主路径补丁。
5. 每个活跃 `poc/<topic>/` MUST 维护主题装订器 `poc/<topic>/ndf/`（[[DEF-022]] / [[BEH-025]]），
   含进度/溯源与可指导编码的设计面（`DESIGN.md` / `INTERFACE.md`）。
   装订器内文档 **MUST NOT** 被 Agent 当作 Trunk `status=stable` must 的实现依据；
   确认后的契约草稿仍写入 `spec/` 且显式 `status=draft`，并登记进 `TOPIC.md`。
   装订器仅提供探索呈现、设计与复现入口；stable must 源仍以 `spec/00-50` 为准。
6. MUST NOT 将 commit ledger、`git format-patch` 产物、或探索实现伪装为 `spec/models/` 参考模型
   （时间轴与溯源见 [[DEF-023]]；预言机纪律见 [[META-004]]）。
7. `spec/models/` MAY 为空（仅边界 README）；空槽不构成流程违规。

> rationale: NDF `models/` 是金标，不是实验沙箱。误用会导致 Agent 把 POC 当 must 实现依据。
> 装订器解决多提案漂移与 commit 可复现，但不引入第二套 Trunk SoT。
> 语义核目的与 promote 触发见 [[META-004]]。
