# Meta Glossary — 双轨 / 装订 / 缺陷分类术语

> scope: ndf-process  
> 条款索引: `DEF-020`…`DEF-023`, `DEF-META-ID-NS`, `DEF-NDF-GRAPH`, `DEF-NDF-CYCLE`, `DEF-NDF-STABLE-DRAFT`, `DEF-NDF-CONFLICT-ASYM`, `DEF-NDF-META-DANGLING`, `DEF-NDF-UNLINKED`, `DEF-NDF-SPEC-DRIFT`, `DEF-NDF-ZOMBIE-SPEC`, `DEF-NDF-REPRO-BIND-GAP`, `DEF-NDF-OBS-GRAIN`, `DEF-NDF-BINDER-DUAL-HEAD`  
> 产品树 adopted 指针: `00-charter/glossary.md`  
> 分类提案: `meta/open/proposal-meta-ndf-defect-taxonomy.md`  
> ID 命名空间: [[ADR-META-002]]

## DEF: POC（概念验证） {#DEF-020}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->

针对单一探索主题（通常对应一个 `proposal-*` / DEC 方向）的**可丢弃**实现与测量集合。
POC 的目标是产生证据（正/负），不是扩展生产 API 表面。承载面见 [[ARCH-008]]；纪律见 [[BEH-018]]。

## DEF: 晋升（Promote） {#DEF-021}
<!-- ndf: kind=def layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->

将 POC 中**已证实有效**的最小变更集，经提案确认后写入固定目录（stable 契约）并合入 `src/`
的过程。晋升 MUST 可追溯到证据与 DEC/提案 ID。闸门见 [[BEH-019]]。

## DEF: Topic Binder（主题装订器） {#DEF-022}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-020 -->

某一 `poc/<topic>/` 探索主题的**进度与可复现入口**，目录为 `poc/<topic>/ndf/`
（含 `TOPIC.md`、`proposals/`、`evidence/`、`COMMITS.md`）。装订器 **不是** Trunk SoT
（`poc.sot: false`）；Trunk must 仍只在 `spec/00–50`。纪律见 [[BEH-025]]。

## DEF: Commit Ledger（提交账本） {#DEF-023}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-022 -->

`poc/<topic>/ndf/COMMITS.md` 中的对照表：将 `code_commit` 与（可选）`ndf_commit`、
提案 ID、条款 ID、验证协议绑定，使仅凭装订器即可定位如何复现该提交的测量结果。

## DEF: Meta 条款 ID 命名空间 {#DEF-META-ID-NS}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=ADR-META-001,ADR-META-002,DEF-NDF-GRAPH -->

Process profile（`spec/meta/`）条款 ID 规则：

1. **新建一般条款**：`META-nnn`（自 `META-001`）；`kind`/`layer` 表达角色，不开
   `META-BEH-*` / `META-CHR-*` 子号池。
2. **语义前缀并存**：`DEF-NDF-*`、`CON-POC-*`、`ADR-META-*` / `ADR-TOPIC-*`、
   `DEC-HYGIENE-*`。
3. **冻结 canonical（不换号）**：`CHR-008`、`BEH-018`…`BEH-026`、`ARCH-008`、
   `DEF-020`…`DEF-023`。
4. MUST NOT 再为新 process 条款占用产品 `CHR`/`BEH`/`ARCH`/`DEF`/`CON-SLA`/`CON-00n`
   数字续号；产品亦 MUST NOT 复用上述冻结同号。

权威决策见 [[ADR-META-002]]。

## DEF: NDF 条款语义图模型 {#DEF-NDF-GRAPH}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=ADR-META-001,CHR-008,META-001,META-002 -->

条款书写与边键词汇见 [[META-001]]、[[META-002]]（[`language.md`](language.md)）。
Trunk SoT 条款构成多关系有向图 \(G=(V,E)\)：顶点为 `{#ID}`，标签 \(\lambda\) 含 NDF
`status`/`level`；边键仅允许 NDF meta（`refines`,`depends-on`,`verifies`,`conflicts-with`,
`affects`,`superseded-by`,`couples-with`,`model`）。

- \(E_{\mathrm{dep}}\) := `refines` ∪ `depends-on`，**MUST** 为 **DAG**（三色 DFS 后向边或 Tarjan/Kosaraju SCC 判定）
- \(E_{\mathrm{conf}}\) := `conflicts-with`，**MUST** 对称
- 修图后宜存在拓扑序（Kahn / DFS 完成时刻）

Layer A（图语义面）缺陷见 [[DEF-NDF-CYCLE]]…[[DEF-NDF-UNLINKED]]；
**绑定溯源面**（曾称 Layer B；工具 `ndf_bindcheck`）见 [[DEF-NDF-SPEC-DRIFT]]…[[DEF-NDF-BINDER-DUAL-HEAD]]。  
判定公式（Layer A）：违反本模型图论谓词即缺陷。扫描仪 MUST NOT 另造非 NDF 边类型。

> rationale: 散文在树、语义在图、时间在 git；稳定条款 ID 为铆钉。提案
> `proposal-meta-ndf-defect-taxonomy`。

## DEF: 依赖环缺陷 {#DEF-NDF-CYCLE}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

\(E_{\mathrm{dep}}\) 上存在有向环（自环或非平凡 SCC）。通常文档-only 修复；修复 MUST 恢复 DAG。

## DEF: stable must 依赖非 stable {#DEF-NDF-STABLE-DRAFT}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH,BEH-019,CON-POC-001 -->

`status=stable` 且 `level=must` 的顶点经 \(E_{\mathrm{dep}}\) 指向 `status≠stable`（含空）的目标。

## DEF: conflicts 非对称 {#DEF-NDF-CONFLICT-ASYM}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

`conflicts-with` 有向声明缺少反向边。文档-only。

## DEF: meta 边悬空 {#DEF-NDF-META-DANGLING}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

NDF meta 边目标 ID 不在顶点集 \(V\) 中。全文 wiki 断链归 `ndf_index validate`，不单列本 DEF。

## DEF: 未连接条款（warning） {#DEF-NDF-UNLINKED}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-NDF-GRAPH -->

在选定关联边集上入度出度均为 0 的条款（检索卫生）。默认 warning，不单独构成硬失败。

## DEF: 规范漂移 {#DEF-NDF-SPEC-DRIFT}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=CHR-008,BEH-019,DEF-023 -->

实现已变而相关 L1 条款未同步（代码→规范滞后）。可关联化部分：路径↔条款引用；行为是否仍满足 must 为非图论（测试/人工）。探索轨 POC 与 Trunk 不一致不属本缺陷（[[CHR-008]]）。

## DEF: 僵尸规范 {#DEF-NDF-ZOMBIE-SPEC}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=BEH-020,DEF-NDF-GRAPH -->

条款仍引用或约束已删除/改名的文件、符号、API、env（规范→实现空指）。可图论化为悬挂引用顶点；抽取规则另定。

## DEF: 可复现绑定缺失 {#DEF-NDF-REPRO-BIND-GAP}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-023 -->

主题相关 code/ndf 变更缺少 Commit Ledger 行或必需 git trailers。条款–commit 二部关联中应有顶点度为 0。

## DEF: 观测粒度过粗 {#DEF-NDF-OBS-GRAIN}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-023 -->

ledger 粒度无法回答「一次测量对应哪对 SHA / 哪些条款 / 何种协议」。**不**强制 git 1:1；要求 [[DEF-023]] 可回答性。

## DEF: 装订器双头漂移 {#DEF-NDF-BINDER-DUAL-HEAD}
<!-- ndf: kind=def layer=L1 status=stable since=0.9 source=deduced scope=ndf-process -->
<!-- ndf: depends-on=DEF-022,BEH-018,BEH-019 -->

装订器登记与 Trunk 同 ID 的 `status`/`topic=` 不一致且未按 promote/reject 回合。
