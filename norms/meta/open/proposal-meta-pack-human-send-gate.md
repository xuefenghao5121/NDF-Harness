# Process Proposal — 人审对象与热路径（确认一次、审 markdown、pack-view 后再开租约）

> track: process
> status: Implemented on 2026-09-01
> scope: ndf-process
> idea_plane: process
> refines: META-010, META-011, META-014, META-023, META-024, BEH-025, ADR-META-004
> depends-on: META-010, META-011, META-012, META-014, META-019, META-023, META-024, BEH-025, ADR-META-003, ADR-META-004
> proposal-id: meta-pack-human-send-gate
> flow-id: meta-pack-human-send-gate
> control-flow: managed
> land-targets: spec/meta/process.md, spec/meta/tools/ndf_poc_dispatch.py, spec/meta/tools/ndf_workflow_status.py, spec/meta/tools/ndf_dispatch_send.py, AGENTS.md, .cursor/skills/ndf-workflow/SKILL.md, .cursor/skills/ndf-workflow/OVERVIEW.md, .cursor/skills/ndf-workflow/poc.md, .cursor/skills/ndf-workflow/proposal.md, .cursor/skills/ndf-workflow/delegate.md

Status: draft（等人读本文件后回复「已确认」）

## 问题

现行热路径把人审做成了两套互相打架的仪式：

1. **提案「已确认」后再「已审核」。** 提案 markdown 在请人确认时已经在磁盘上。第二闸常被指挥面汇报成 completion JSON /「是否写入磁盘」。人无法从 JSON 判断要同意什么；「文件在不在」也不是人该审的——写盘是 Agent 的义务，不是审核对象。
2. **「派发」同时造 pack、写 `bundle_dispatch`、开租约、`--send`。** 人面对 SHA / last-pack.json；[[META-024]] 的分层散文没有接到热路径。租约 worktree 在人还没看懂将派出的契约时就已经打开。

人要的闸只有内容，而且每道闸只审一种东西。不得为此新加面板、必背口令，或把 overlay JSON / completion JSON 当人机界面。

## 人审对象（钉死）

| 阶段 | 人打开并审的文件 | 人回复 | 审完之后 Agent 才做 |
|------|------------------|--------|---------------------|
| 提案 | `spec/open/proposal-*.md` 或 `spec/meta/open/proposal-meta-*.md` | **已确认** | process：落地 `land_targets`。poc：写齐 `poc/<topic>/ndf/` 装订器 |
| 装订器（仅 poc） | `poc/<topic>/ndf/` 下 TOPIC/DESIGN/PERF_BASELINE/DELTA/INTERFACE（markdown） | **已审核** | 写 `bundle_dispatch`（绑定装订器 bundle SHA）+ 造 worker pack + 写 pack-view 散文 |
| 将派契约 | `tmp/ndf-pack-view-*.md`（[[META-024]] 分层散文） | **派发** | 开租约 worktree，再 `dispatch-send` / `poc-dispatch --send` |

Command 口头汇报 MUST 指向上表对应路径。MUST NOT 把 `ndf-agent-completion/v1`、last-pack.json、SHA 对照表、或「请确认已写入磁盘」当作人审主文。磁盘回执仍是 **hop 成功** 信号（[[META-011]]），只给指挥面收口，不给人当审核材料。

## 提案 {#META-025}

<!-- ndf: kind=req level=must layer=L1 status=draft since=1.2.3 source=stated scope=ndf-process -->
<!-- ndf: refines=META-010,META-011,META-014,META-023,META-024,BEH-025,ADR-META-004 depends-on=META-010,META-011,META-012,META-014,META-019,META-023,META-024,BEH-025,ADR-META-003,ADR-META-004 -->

### A. 提案只确认一次

1. 草稿 MUST 先写入 open 提案路径，再请人确认。请人时 MUST 给出该 markdown 路径。
2. 产品与 process 提案的内容闸均为 **「已确认」**，绑定提案文件 SHA（[[META-014]]
   `proposal.confirmed`）。MUST NOT 再要求人对同一提案回复「已审核」。
3. process：`已确认` 授权 `confirm_land`。落地成功后生命周期直接到 `reviewed`
   （可用同一 `proposal.confirmed` 关闭；MUST NOT 再造 `proposal.reviewed` 作为必经闸）。
   指挥面落地后 MUST 指向已改的 `land_targets` 条款路径，MUST NOT 甩 JSON 请人「审核是否写入」。
4. 产品 poc：`已确认` 之后 MUST 立刻委派 Control 写齐装订器；MUST NOT 插一节提案「已审核」。
5. `已审核` 口令留给 **POC 装订器 markdown**（见 B），不再表示「提案落地回执」。
6. 文件存在仍 MUST NOT 推导为已确认（[[META-010]] 第 1 条保留）。

### B. POC：审装订器 markdown，再锁 bundle

1. 装订器一次写齐后，指挥面 MUST 请人审 `poc/<topic>/ndf/` 的契约 markdown
   （读序仍 [[BEH-025]]），MUST NOT 请人审 JSON。
2. 人回 **「已审核」** 后，Command 才写 `GATES.md` `bundle_dispatch`（内容束仍与闸 3
   相同，[[META-010]] / [[META-019]]），并造 worker pack。`bundle_dispatch` 的
   `source_ref` 绑定本次装订器审核，phrase 可仍为记录用字段；**不得**在未见装订器审核时
   因人说了「派发」就先写闸并 send。
3. 实质 amend 装订器契约切片 → 作废 `bundle_dispatch`，回到 B 再审 markdown。
   Numbers / Rounds / evidence 追加仍不触发重审。

### C. 编译与送出分跳；派发才开租约

1. 造 pack（worker JSON + 人审散文）与 `dispatch-send` / `poc-dispatch --send`
   MUST NOT 在同一跳默认完成。造 pack MUST 停下等人。
2. 人审散文与 worker JSON MUST 同源（同一 `compile_plan` / `plan_sha`）。
3. 无本 hop 的 `tmp/ndf-pack-view-*.md`（schema `ndf-pack-view/v2`）不得 send
   （blocker：`human_pack_view_missing`）。散文不是 hop 成功信号。
4. 指挥面 MUST 指向 pack-view 主文；MUST NOT 把 last-pack.json 当给人看的依赖说明书。
5. **「派发」= 开租约 worktree + 送出。** MUST NOT 在展示散文之前、或人未回复「派发」
   之前创建 Implementation 租约 / 隔离 worktree。未展示散文时人说了「派发」，MUST 先
   完成 A/B 与 pack-view，再等人一句真正送出（自然语言：送出 / 先改 / 拿掉某 ID 均可）。
6. 孤立租约握手仍须 `allowed_write_root` / `base_sha` / worktree（[[META-019]]）；
   只是把「建租约」从造 pack 挪到「派发」之后。

### 开口（禁止实例化成唯一 UI）

人定制闭包仍可：改树内 `depends-on`；自然语言 overlay 一次；改装订器后再编；看完不送。
MUST NOT：overlay JSON 当人机界面；新必说口令；自动送出；复活面板。

### 热路径

**产品 poc**

```text
写提案 markdown
  → 人「已确认」（审提案）
  → Control 写 poc/<topic>/ndf/*.md
  → 人「已审核」（审装订器 markdown）
  → bundle_dispatch + worker pack + pack-view 散文
  → 停下
  → 人「派发」（审 pack-view）
  → 开租约 worktree → send
```

**process**

```text
写 spec/meta/open/proposal-meta-*.md
  → 人「已确认」（审该 markdown）
  → confirm_land → 结束
```

无第二闸「已审核」。无 POC 装订器、无租约。

## 落地清单

- [ ] `process.md` `{#META-025}`；薄注 META-010 / META-011 / META-014 / BEH-025：
      提案只确认一次；`已审核`=装订器；无散文不得 send；派发才开租约
- [ ] META-014 生命周期去掉必经的 `implemented_pending_review` / `proposal.reviewed`
- [ ] `poc-dispatch` 默认不 `--send`、造 pack 时强制 pack-view、不在此步建租约
- [ ] `dispatch-send` / `--send`：校验同源 v2 散文；此时才 inline lease
- [ ] skill：`proposal.md` / `poc.md` / `delegate.md` / OVERVIEW / AGENTS 热路径与人审对象表
- [ ] 测试：无 pack-view 则 send 失败；未「已审核」装订器不得写 `bundle_dispatch` 并 send；
      process 仅 `已确认` 可 land 且不得再要 `已审核`

## 明确不做

- 不新口令、不新面板、不用 LLM 改写条款
- 不替换 worker JSON；不把 overlay / completion JSON 升成 SoT 或人审面
- 不自动同意送出
- 不改 Genesis 的「架构已确认」/「GENESIS已审核」（那是骨架/基线 stable，不是提案双闸）
- 不在本条修 OpenClaw 心跳 stall（另案）

## 验收

1. 人打开提案文件能判断要不要「已确认」；确认后指挥面不再要提案「已审核」或 JSON。
2. poc：人打开 `poc/<topic>/ndf/*.md` 回复「已审核」之后，才出现 bundle 闸与 pack-view。
3. 人说「派发」且本轮未见该 pack 的散文 → 只编译+展示，不开租约、不 send。
4. `ndf_graphcheck.py --meta` hard_errors=0。

## Control receipts

| event | phrase | actor | approved_at | proposal_id | flow_id | hop | proposal_sha | status |
|-------|--------|-------|-------------|-------------|---------|-----|--------------|--------|
| proposal.confirmed | 已确认 | Human | 2026-09-01T06:29:22Z | meta-pack-human-send-gate | meta-pack-human-send-gate | confirm_land | b88f444c3ae62260e9fbf0d369cc9b0bf1ab58491a1beb5e418bce47b05b28d0 | valid |
