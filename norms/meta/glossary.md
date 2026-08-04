# Meta Glossary — 双轨 / 装订 / 缺陷分类术语

> scope: ndf-process

## DEF: POC（概念验证） {#DEF-020}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->

针对单一探索主题的**可丢弃**实现与测量集合。目标是产生证据（正/负），不是扩展生产 API。  
承载面见 [[ARCH-008]]；纪律见 [[BEH-018]]。

## DEF: 晋升（Promote） {#DEF-021}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->

将 POC 中已证实有效的最小变更集，经提案确认后写入 stable 契约并合入 Trunk 实现的过程。  
闸门见 [[BEH-019]]。

## DEF: Topic Binder（主题装订器） {#DEF-022}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-020,ARCH-008,BEH-025 -->

`poc/<topic>/ndf/`（含 `TOPIC.md`、`proposals/`、`evidence/`、`COMMITS.md`）。  
**不是** Trunk SoT；Trunk must 仍只在 `spec/00–50`。纪律见 [[BEH-025]]。

## DEF: Commit Ledger（提交账本） {#DEF-023}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-022,BEH-025 -->

`COMMITS.md` 对照表：绑定 `code_commit` 与（可选）`ndf_commit`、提案、条款、验证协议。

## DEF: NDF 条款语义图模型 {#DEF-NDF-GRAPH}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=ADR-META-001,BEH-025,CHR-008 -->

Trunk SoT 条款构成多关系有向图：顶点为 `{#ID}`；边键仅允许 NDF meta
（`refines`,`depends-on`,`verifies`,`conflicts-with`,`affects`,`superseded-by`,`couples-with`,`model`）。

- `refines` ∪ `depends-on` **MUST** 为 DAG  
- `conflicts-with` **MUST** 对称  

图语义面缺陷见 [[DEF-NDF-CYCLE]]…[[DEF-NDF-UNLINKED]]；  
绑定溯源面见 [[DEF-NDF-SPEC-DRIFT]]…[[DEF-NDF-BINDER-DUAL-HEAD]]。

## DEF: 依赖环缺陷 {#DEF-NDF-CYCLE}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

依赖边集上存在有向环。修复 MUST 恢复 DAG。

## DEF: stable must 依赖非 stable {#DEF-NDF-STABLE-DRAFT}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH,BEH-019,CON-POC-001 -->

`status=stable` 且 `level=must` 经依赖边指向 `status≠stable`（含空）目标。

## DEF: conflicts 非对称 {#DEF-NDF-CONFLICT-ASYM}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

`conflicts-with` 缺少反向边。

## DEF: meta 边悬空 {#DEF-NDF-META-DANGLING}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

meta 边目标 ID 不在顶点集中。

## DEF: 未连接条款（warning） {#DEF-NDF-UNLINKED}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

选定边集上入度出度均为 0（检索卫生；默认 warning）。

## DEF: 规范漂移 {#DEF-NDF-SPEC-DRIFT}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=CHR-008,BEH-019,DEF-023 -->

实现已变而相关 L1 未同步。探索轨与 Trunk 不一致不属本缺陷（[[CHR-008]]）。

## DEF: 僵尸规范 {#DEF-NDF-ZOMBIE-SPEC}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-020,DEF-NDF-GRAPH -->

条款仍引用已删除/改名的路径、符号、API。

## DEF: 可复现绑定缺失 {#DEF-NDF-REPRO-BIND-GAP}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-023,BEH-025 -->

缺少 Commit Ledger 行或必需 git trailers。

## DEF: 观测粒度过粗 {#DEF-NDF-OBS-GRAIN}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-023 -->

ledger 无法回答「一次测量对应哪对 SHA / 哪些条款 / 何种协议」。

## DEF: 装订器双头漂移 {#DEF-NDF-BINDER-DUAL-HEAD}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-022,BEH-018,BEH-019,BEH-025 -->

装订器登记与 Trunk 同 ID 的 `status`/`topic=` 不一致且未按 promote/reject 回合。
