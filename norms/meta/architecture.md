# Meta Architecture — POC / models 边界

> scope: ndf-process  
> 条款索引: `ARCH-008`

## `models/` 与 `poc/` 边界 {#ARCH-008}
<!-- ndf: kind=arch level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=DEF-020,DEF-021,DEF-022,BEH-025 -->

1. `spec/models/` MUST 只承载 NDF L3 **参考模型**（可重复、可测试、由条款 `model=` 引用）。
2. 探索性生产路径改动 MUST 落在仓库根目录 `poc/<topic>/`（或专用 POC 分支），
   MUST NOT 伪装为 `spec/models/` 参考模型。
3. `poc/` MUST 在 `ndf.yaml` 中声明为 **非 SoT**（`sot: false`）。
4. 允许在 `spec/models/` 下仅存放与参考模型对照的算法草稿；不得提交链入生产主路径的实验补丁。
5. 每个活跃 `poc/<topic>/` MUST 维护主题装订器 `poc/<topic>/ndf/`（[[DEF-022]] / [[BEH-025]]）。
   装订器 **MUST NOT** 被当作 Trunk `status=stable` must 的实现依据；
   stable must 源仍以 `spec/00-50` 为准。

> rationale: `models/` 是金标，不是实验沙箱。
