# NDF Harness 是干什么的

版本 1.0.2。给要在人跟 Agent 一起做复杂系统的人看。

这不是操作手册。装包、CLI、排障去文末那几篇。这里只讲一件事：原始 NDF 把「圣经」钉住了，日常协作里还有几道坑没钉；Harness 补的是那几道坑。

上游格式提案（不是本仓 SoT）：
[hengliao1972/normative_language - `normative_language_cn.md`](https://github.com/hengliao1972/normative_language/blob/main/normative_language_cn.md)（v0.1）。

装进消费仓之后，说了算的是那边的 `spec/meta/` 和 `AGENTS.md`。这个包只是种子。

## 先说三个会翻车的地方

**聊天当圣经。** 常见循环：人丢一段半成品描述，Agent 吐设计或测试报告，人再补一句纠正，再来几百轮。真正管设计的往往是「参考文档 + 初稿 + 整段 prompt」。这坨东西散在聊天和脑子里，没法重放，后一句悄悄盖掉前一句，还经常整段丢掉。系统有了，规范性描述没有。以后改代码就得考古。（原始提案 §1.3。）

**规范只活一个 PR。** Spec Kit 一类脚手架也用 Markdown、「先规范后代码」，但规范常常跟着单个变更请求生灭：合入就扔。复杂系统要的是能跟着项目活几年的那本：能演进、能查、能对着某个基线说话。不是每发一个 PR 换一本。（原始提案 §3 对这类工具的批评。）

**Agent「做完了」。** 规范钉进仓库之后还会翻车：transport ACK、聊天里一句 OK、stdout 一段 JSON，就被当成委派成功，磁盘上没有可核的回执。或者面板、回放、多层 fail-closed 把一次日常 POC 拖成几小时，人盯仪式不盯假设。我们把这些写进了流程决策（文字优先、退役 Commander / Episode / Replay），见 [`SECURITY.md`](SECURITY.md) 和安装后 `spec/meta/decisions/` 里的 ADR-META-003 / ADR-META-004。

三件事叠在一起：

1. 规范性描述要能增量长、带历史、人和机器都能读。
2. 没证伪的东西不能默认写成 stable，也不能直接改生产路径。
3. 谁批准、写到哪、怎样算做完，得能机械判定，不能靠聊天感觉。

## 原始 NDF 钉住了什么

提案名是 **NDF（Normative Description Format）**：Markdown + Git 上的约定，外加一小套工具愿景。不发明新文件格式，不搞服务器。纯文本加 `git` 就能写。这点是真的关键。

两端它都不要。纯散文：含混、不可合并、不可查询，Agent 时代连「收拢在一处」都做不到。全盘形式化（ASL、TLA+、证明助手）：工作量可能超过设计本身，早期含混和工程判断写不进去，能读的人变少。NDF 的路子是：自然语言当主载体；结构加在组织层（标识、分类、连接、版本），不把每句话写成形式语言；代码比散文便宜的地方就嵌「规范性代码岛」。目标是单调变好，不是完美。

一句话纪律：

> 散文活在树里，语义活在图里，时间活在 git 里。稳定的条款 ID 是铆钉。

树是 `spec/00-charter/` 到 `50-verification/` 这类目录，管归属。图是条款之间带类型的边：`refines`、`depends-on`、`conflicts-with`、`verifies`...。历史是 Git 加决策记录，取代而不是静默删。

原子单元叫**条款**：标题块 + `{#稳定ID}` + `<!-- ndf: ... -->`，正文用 MUST / SHOULD / MAY。精化层 L0 意图 -> L1 契约 -> L2 机制 -> L3 可执行模型都留着，用 `refines` 串，后层不覆盖前层。

协作循环（提案 §7，概念层面）：人先写章程和 L0/L1 骨架；Agent 任务写成「基线 `spec-vX` + 引用条款 ID 的工单」；产出和纠正回流成条款、决策记录、开放问题，不能只活在聊天里；人类批规范性变更，Agent 提议并交叉校验。

提案 §9 自己也说了：一致性靠评审和经验，不是证明；蒸馏会丢信息；纪律会衰减；`refines` 记了但不验证。格式解决的是圣经怎么写、怎么钉。

它还没规定：探索代码写哪、怎么禁止误改主线；人说哪一句才算授权；怎样才算一次 Agent 任务做完；日常要不要让人选工具、理解控制面。这些才是工作流要落地的。

## 缺口在哪，Harness 补什么

**NDF Harness** 把已经验证过的流程纪律打成可安装种子：条款语言、双轨过程、五句口令、治理 CLI、运行时 adapter。它不是产品行为契约，也不是消费仓 `spec/meta/` 的上级。

装完之后消费仓说了算。包只负责第一次（或 adopt）把种子放对。方向是单向的：消费仓验证过的实践提炼进包，再分发。禁止用包去纠正已经落地的本地 SoT。

条款权威在安装后的 `spec/meta/`。对照如下：

| 原始 NDF 没钉死的 | Harness 落地 |
|------------------|--------------|
| 单一规范树持续精化，探索容易提前写成 `stable` must | 双轨 [[CHR-008]] / [[BEH-018]]：试错落在 `poc/<topic>/`；探索期 MUST NOT 改 Trunk `src/` / `include/` / `tests/` |
| §7 是概念循环；人还要选工具、啃控制面 | 五句口令是唯一人类入口；内部模块对人不可见（[`skill/ndf-workflow/`](../skill/ndf-workflow/SKILL.md)） |
| 「人批了 PR」不等于可检查的门禁身份 | 口令回执写 `GATES.md`（人、时间、内容 SHA）；review-slice 的 **bundle SHA**；文件在 ≠ 已批准（[[META-010]]） |
| 「圣经在」不等于一次委派完成 | 成功 = 磁盘 `ndf-agent-completion/v1`；ACK / stdout 不算 |
| 人与 Agent 读写对称 | Command / Control / Implementation 写根分裂；未绑定角色则 `roles_unbound`，派不出去 |
| `option` / DSE 有参数空间，没有主题装订和性能读序 | 装订器 `poc/<topic>/ndf/`；比 Δ% 只读 TOPIC 到 PERF_BASELINE（[[META-007]]）；探索数字进不了 stable SLA（[[CON-POC-001]]） |
| `ndf init` 搭脚手架，不冻结「对照目标」 | Genesis：绑内核，一句「派发」（契约+基线），再 `GENESIS已审核`（[[META-009]]） |

Harness 补的是探索隔离和人机权威协议，不是另写一本产品圣经。

```text
原始 NDF：条款怎么写、图怎么连、prompt 怎么蒸馏进决策
Harness：谁说哪句才派、写到哪、怎样算完成、探索怎么不脏主线
```

## 对人跟 Agent 一起干活，这几处最有用

**人要记的口令很少。** 就五句：初始化项目 / 提交Idea / 派发 / 继续 / 关闭（健康是只读旁路）。人出 Idea、审契约、说口令、看 blockers 和磁盘回执。不用选 skill，不用开面板，不用背 CLI。指挥面听口令、造 pack、等人审、调工具、把失败原因甩回来。

**权威不对称，而且能执行。** pack 上有 `allowed_write_root`、`workspace.repo_root`、角色绑定。

| 层 | 默认谁 | 写什么 |
|----|--------|--------|
| Command | 当前宿主 + ndf-workflow | `tmp/`、门禁回执、派发触发；不写 worker 实现 |
| Control | OpenClaw（可 fallback） | 提案、装订器、门禁；bootstrap 设计 hop 可写 `spec/00-50` draft |
| Implementation | Claude Code ACP（可 fallback） | POC 只动 `poc/<topic>/`；promote / genesis 才动 Trunk |

人批准规范性变更和「派发」；Agent 在写根里干活。权威不对称，读写分工清楚。原始 §7 想要的那个形状，这里能跑起来。

**文字优先，硬门不砍。** `GATES.md` 里带 SHA 的「派发」回执；过不了就停。日常不走 Commander / Episode / Replay（已退役）。错仓库、越界写根、缺人审 bundle、并发写、上下文漂移、伪造 completion、超预算：证不了安全就停，不猜、不降级、不静默改权威规范。见 [`SECURITY.md`](SECURITY.md)。

**两边读同一份上下文。** pack 里嵌 Task Manifest，同一 `manifest_sha`。失败只报 `context_verify_failed` 和 SHA，不甩一坨长上下文。人去修装订器或重审就行，不用猜 Agent 读错了哪段聊天。

**负结果也是一等公民。** `ndf_close.py plan --mode reject` 写出 DEC（`Rejects:`），条款 deprecated，装订器归档。不许静默删条款留代码，也不许删代码留 stable must。证伪跟晋升一样，得有记录（[[BEH-020]]）。

**宿主随便换。** `install.py`、`adapters/`、`ndf.workflow.yaml` 三角色。Cursor / OpenClaw / Claude Code / OpenCode / Codex / generic；缺 CLI 可以 fallback 到 `in-host` / `dual-session`。成功看磁盘回执，不绑某个 IDE。

刻意不宣称的：原始提案 §8 里的 `ndf ingest`、`ndf publish` 这类愿景工具。本包交付的是治理 CLI 和工作流纪律，不是那张完整清单。

## 跟着口令走一遍

假定消费仓已经装好 dual-track，指挥 Agent 加载了 ndf-workflow。安装细节见 [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)。

### 初始化项目

人说：**初始化项目**。

| 步骤 | 人说 / 做 | 盘上出现什么 | 成功看什么 |
|------|-----------|--------------|------------|
| 角色向导 | **角色已配置** | `ndf.workflow.yaml` 三角色；Genesis `GATES.md` 回执（绑 roles SHA） | `roles_unbound=false` |
| 绑内核 | Command 自己写，不另派 | `FOUNDATION.md` + `GATES.md` 骨架 | 短记录：mode、Trunk SHA、roles SHA；不写产品长文 |
| 一次派发 | **派发** | Control 写满 `spec/00-50`（多为 draft），复现测试/金标进 configs / baselines | 磁盘 `ndf-agent-completion/v1`；测不出就 `baseline_status=deferred`，「继续」补测 |
| 仅 greenfield | **可以建立初始主线** | 一次 `genesis-pack`，最小可构建切片 | adopt 跳过 |
| 冻结 | **GENESIS已审核** | 非 SLA 骨架升 `stable`；已复现基线/SLA 升 `stable`；没复现的留 `not-established` | 项目进入 operational |

人这边尽量只说：角色，派发，GENESIS已审核。别在 GENESIS 之后再教人走一轮日常 promote 才把骨架升 stable。

### 提交 Idea

人说：**提交Idea**，或者直接描述需求。

Command 先分流平面，再写提案：

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆成两个互相引用的提案 |
| ambiguous | 先问人；MUST NOT 默认 poc |

产品 track 拿不准就默认 **poc**。落地等人 **已确认**，审核等人 **已审核**。没确认就别动 Trunk / stable 契约。

### POC 探索

提案「已审核」后，Control 一次写齐装订器 `poc/<topic>/ndf/`：

`TOPIC`，`DESIGN`，`PERF_BASELINE`，`DELTA`，`INTERFACE`（以及 `GATES`）

开题填 `explore_surface`。跟活跃 exploring 相交就写 `depends_on_topics` / `conflicts_with_topics`，别默认能并行。

人审完契约说：**派发**。

1. `GATES.md` 追加 `bundle_dispatch`（phrase=`派发`）+ **bundle SHA**（契约 review-slice，不是整文件瞎哈希）；
2. `poc-dispatch --send`，Implementation 只写 `poc/<topic>/`；
3. 成功只认磁盘 `ndf-agent-completion/v1`。

之后人对指挥面说 **继续** 或 **关闭**。假设 / 接口 / 测量协议 / 写边界真改了，才换 SHA 再派发；Numbers、Rounds、evidence 追加不重审。契约切片变了、SHA 没跟上，就是 gate drift：先看 slice unified diff，再重审「派发」。别只甩两个 hex。

### 关闭 POC

人说：**关闭**（或选定模式）。先跑只读 plan：

```bash
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject
```

| mode | 含义 |
|------|------|
| **promote** | 全量合入；draft 升 stable；干净合入 `src/`；`Promotes: <topic>`；编译 + 性能 + 金标（[[META-006]]）；语义核要 / 不要 / 延期（[[META-004]]） |
| **partial** | 子集合入；TOPIC 可以还在 exploring |
| **reject** | 负结果 DEC + deprecated；装订器归档；默认不写 Trunk `src/` |

闸门没过完之前，主题别先标 `promoted`。plan 里的基线 stale 和表面冲突清单要执行。

### 口令速查

| 人说 | 主要工件 | 成功信号 |
|------|----------|----------|
| 初始化项目 | FOUNDATION / `spec/00-50` / baselines / Genesis DEC | `GENESIS已审核` + operational |
| 提交Idea | `spec/open/` 或 `spec/meta/open/` 提案 | 「已确认」「已审核」回执 |
| 派发 | `GATES` bundle SHA + pack + worker 写入 | 磁盘 `ndf-agent-completion/v1` |
| 继续 | 修订装订器；契约变了才换新 SHA | 再次合法派发 + completion |
| 关闭 | close plan，再 promote / partial / reject | TOPIC status + 归档 / Trunk 验证 |

## 还想往下看

- [`WORKFLOW.md`](WORKFLOW.md)：轨道、门禁、关闭模式
- [`WORKFLOW-OVERVIEW.md`](WORKFLOW-OVERVIEW.md)：调用图和闭环
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：三层、派发管线、安全边界
- [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)：装进消费仓
- [`TOOLS.md`](TOOLS.md)：治理 CLI
- [`SECURITY.md`](SECURITY.md)：fail-closed 清单
- 安装后的 `spec/meta/language.md` 和 `process.md`：条款正文 SoT

原始 NDF 让圣经能写、能钉、能长。Harness 让人用五句口令指挥 Agent，把写界和磁盘回执变成能检查的合同。探索脏不了主线，聊天也不再冒充成功。
