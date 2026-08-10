# ADR: Meta 条款独立编号命名空间 {#ADR-META-002}

<!-- ndf: kind=decision date=2026-08-05 status=stable scope=ndf-process -->
<!-- ndf: depends-on=ADR-META-001 -->

> 日期: 2026-08-05  
> 状态: Accepted  
> 场景: process / 规范卫生  
> track: process  
> 提案: `spec/meta/open/proposal-meta-id-namespace.md`  
> 关联: [[ADR-META-001]], [[DEF-META-ID-NS]], [[DEF-NDF-GRAPH]]

## Context

[[ADR-META-001]] 将流程条款迁入 `spec/meta/` 且 **ID 不换号**，路径分层已成立，但
`CHR` / `BEH` / `ARCH` / `DEF` 与产品共用数字池，造成「递进续号」误读（如 CHR-008、
BEH-025 与产品行为交错）。`CON-POC-*`、`DEF-NDF-*`、`ADR-META-*` 已证明语义/独立前缀可行。

全量把 `CHR-008`/`BEH-018`… 改名为 `META-*` 会打碎既有 wiki、装订器与工具图边，成本过高。

## Decision

1. **冻结（canonical 不换号）**：下列历史 meta ID 永久保留，MUST NOT 重命名为 `META-*`：
   - `CHR-008`
   - `BEH-018`, `BEH-019`, `BEH-020`, `BEH-025`, `BEH-026`
   - `ARCH-008`
   - `DEF-020`, `DEF-021`, `DEF-022`, `DEF-023`
2. **自 2026-08-05 起**，新建 `spec/meta/` 正文条款 MUST 使用独立命名空间，MUST NOT 再占用
   产品 `CHR` / `BEH` / `ARCH` / `DEF` / `CON-SLA` / `CON-00n` 数字续号。
3. **一般流程条款**：单调序列 **`META-nnn`**，自 **`META-001`** 起；角色由
   `<!-- ndf: kind=… layer=… -->` 表达，不开 `META-BEH-*` / `META-CHR-*` 子号池。
4. **语义前缀并存**：`DEF-NDF-*`、`CON-POC-*`、`ADR-META-*` / `ADR-TOPIC-*`、
   `DEC-HYGIENE-*` 等继续按既有惯例取号。
5. **全局唯一**：meta + product 仍一张图（[[DEF-NDF-GRAPH]]）；产品 MUST NOT 复用本 ADR
   冻结占用的同号。
6. **相对 [[ADR-META-001]]**：路径分层与「历史 ID 不换号」仍成立；本 ADR **部分取代**其
   「今后新建流程条款仍与产品共用数字续号」的隐含惯例。

## Consequences

- `ndf.yaml` `id-prefixes` 含 `META`；INDEX META 分组继续收录冻结旧号与新 `META-*`。
- process 提案拟增条款时 MUST 按 [[DEF-META-ID-NS]] 取号。
- 第一版不强制工具拒绝 `meta/` 下新建 `{#BEH-nnn}`（文档纪律）；工具检查可另案。

## Non-goals

- 不把 `CHR-008` 等重命名为 `META-001`
- 本轮不同步 NDF-Harness
- 不改产品条款 ID（如 `BEH-024`）
