# NDF Harness：人跟 Agent 一起干活时，圣经怎么钉住

版本 1.0.2。给要在人跟 Agent 一起做复杂系统的人看。装包、CLI、排障去文末；这里只说清楚一件事：规范别散在聊天里。

上游格式提案（不是本仓 SoT）：
[hengliao1972/normative_language - `normative_language_cn.md`](https://github.com/hengliao1972/normative_language/blob/main/normative_language_cn.md)（v0.1）。  
装进消费仓后，说了算的是那边的 `spec/meta/` 和 `AGENTS.md`。这个包只是种子。

## 1. 问题：规范丢哪儿了

复杂系统该听谁的？不该听实现本身，也不该听测试抽样。该听一套说清「应当 / 不得 / 可以」的规范性描述。人跟 Agent 一起做设计时，这套东西经常根本没落成一个能查的文件。

**聊天当了圣经。** 人丢半成品，Agent 吐设计和测试报告，人再补一句，几百轮。真正管设计的往往是「参考文档 + 初稿 + 整段 prompt」。散在聊天和脑子里，没法重放，后句盖前句，清聊天就丢。系统有了，规范没有。以后改代码只能考古。（原始提案 §1.3。）

**规范只活一个 PR。** Spec Kit 一类也用 Markdown、「先规范后代码」，但规范常跟单个变更请求一起生灭：合入就扔。复杂系统要的是能跟着项目活几年的那本，不是每发一个 PR 换一本。（原始提案 §3。）

**Agent 说做完了，你核不了。** 就算规范开始进仓库，还会翻车：ACK、聊天一句 OK、stdout 一段 JSON，就被当成委派成功，磁盘上没有可核的回执。或者面板和回放把一次日常 POC 拖成几小时，人盯仪式不盯假设。见 [`SECURITY.md`](SECURITY.md) 与 ADR-META-003 / ADR-META-004。

所以你其实要解决三件事：

1. 规范能不能增量长、带历史、人和机器都能读？
2. 没证伪的东西能不能默认写成 stable、直接改生产路径？
3. 谁批准、写到哪、怎样算做完，能不能机械判定？

第一件主要靠怎么写。后两件光写不够，还得规定人跟 Agent 怎么配合。

## 2. NDF：圣经怎么写

**NDF（Normative Description Format）** 是 Markdown + Git 上的约定，外加一小套工具愿景。不发明新格式，不搞服务器。纯文本加 `git` 就能写。

纯散文不行：含混、不可合并、不可查询，连「收拢在一处」都难。全盘形式化（ASL、TLA+、证明助手）也不行：工作量可能超过设计本身，早期含混和工程判断写不进去。NDF 走中间：自然语言当主载体；结构加在组织层（标识、分类、连接、版本）；代码比散文便宜的地方就嵌规范性代码岛。目标是一点点变好，不是一步完美。

纪律就一句：

> 散文活在树里，语义活在图里，时间活在 git 里。稳定的条款 ID 是铆钉。

树（`spec/00-charter/` 到 `50-verification/`）管归属。图（`refines`、`depends-on`、`conflicts-with`、`verifies`...）管语义。Git 加决策记录管演化；取代，不静默删。

原子单元是**条款**：标题块 + `{#稳定ID}` + `<!-- ndf: ... -->`，正文用 MUST / SHOULD / MAY。L0 意图、L1 契约、L2 机制、L3 可执行模型都留着，用 `refines` 串，后层不盖掉前层。

协作上，提案 §7 想的是：人写章程和 L0/L1 骨架；Agent 接「基线 `spec-vX` + 条款 ID」的工单；产出回流成条款和决策记录，不能只活在聊天里；人批规范性变更，Agent 提议并交叉校验。

NDF 把「规范能不能长」这件事钉住了：可版本管理、可交叉引用、可蒸馏进决策记录。§9 也承认：一致性靠评审不是证明；蒸馏会丢信息；纪律会衰减；`refines` 记了但不验证。

它没说清楚的是日常那些脏事：

- 试错代码写哪儿，怎么防止误改主线；
- 人说哪句才算授权；
- 怎样才算 Agent 做完；
- 要不要让人选工具、啃控制面。

格式管「怎么写圣经」。人跟 Agent 每天围着这本圣经怎么干活，还得另定规矩。

## 3. Harness：把没钉死的变成工作流

**NDF Harness** 不是第二套产品圣经。它是把已经验证过的流程纪律打成可安装种子：条款语言、双轨、五句口令、治理 CLI、运行时 adapter。

装完之后消费仓说了算。包只负责第一次（或 adopt）把种子放对。消费仓验证过的实践可以提炼进包再分发；反过来用包纠正已落地的本地 SoT，不行。

可以这么分：

```text
原始 NDF：条款怎么写、图怎么连、prompt 怎么蒸馏进决策
Harness：谁说哪句才派、写到哪、怎样算完成、探索怎么不脏主线
```

对着上面三个问题：

| 你要什么 | NDF 给了什么 | Harness 补什么 |
|----------|--------------|----------------|
| 规范能长 | 条款树 + 图 + git | Genesis 冻结对照骨架；日常提案进 `spec/open/` 或 `spec/meta/open/` |
| 探索不脏主线 | （没钉写界） | 双轨 [[CHR-008]] / [[BEH-018]]：试错只在 `poc/<topic>/`；探索期 MUST NOT 改 Trunk `src/` / `include/` / `tests/` |
| 权威可检查 | 「人批 PR」还是概念 | 五句口令 + `GATES` bundle SHA（[[META-010]]）；成功 = 磁盘 `ndf-agent-completion/v1`；三角色写根分裂 |

更细的空洞对照（条款权威在安装后的 `spec/meta/`）：

| 原来没钉死的 | Harness 怎么钉 |
|--------------|----------------|
| §7 是概念循环；人还要选工具 | 五句口令是唯一人类入口（[`skill/ndf-workflow/`](../skill/ndf-workflow/SKILL.md)） |
| 文件在 ≠ 已批准 | 口令回执（人、时间、内容 SHA）；review-slice bundle SHA |
| 「圣经在」≠ 委派完成 | ACK / stdout 不算成功 |
| 人与 Agent 读写对称 | 未绑定角色则 `roles_unbound`，派不出去 |
| `option` / DSE 无主题装订与性能读序 | 装订器 + [[META-007]]：Δ% 只读 PERF_BASELINE；探索数字进不了 stable SLA（[[CON-POC-001]]） |
| `ndf init` 不冻结对照目标 | Genesis：绑内核，一句「派发」，再 `GENESIS已审核`（[[META-009]]） |

收成一句人话：**人只靠口令拍板；Agent 只在写根里动手；条款和装订器是共享记忆；磁盘回执才算做完。**

## 4. 这套规矩好在哪

下面几条不是另开菜单，就是上面那句人话拆开看。每条也写清：NDF 原来有什么特征，Harness 把它用到了协作里。

**人要记的很少。** 口令就五句：初始化项目 / 提交Idea / 派发 / 继续 / 关闭（健康是只读）。人出 Idea、审契约、说口令、看 blockers 和磁盘回执。不用选 skill，不用开面板，不用背 CLI。指挥面听口令、造 pack、等人审、调工具、把失败原因甩回来。

原始提案想让 Agent 按「基线 + 条款工单」干活，而不是啃整段聊天。Harness 把这变成日常：任务靠条款 ID、装订器和同一份 manifest。

**权威不对称，而且能执行。**

| 层 | 默认谁 | 写什么 |
|----|--------|--------|
| Command | 当前宿主 + ndf-workflow | `tmp/`、门禁回执、派发触发；不写 worker 实现 |
| Control | OpenClaw（可 fallback） | 提案、装订器、门禁；bootstrap 设计 hop 可写 `spec/00-50` draft |
| Implementation | Claude Code ACP（可 fallback） | POC 只动 `poc/<topic>/`；promote / genesis 才动 Trunk |

人批准规范性变更和「派发」；Agent 在 `allowed_write_root` 里干活。提案 §7 说人对权威不对称；Harness 用角色绑定和写根做成硬门：没绑角色，派不出去。

**探索和主线分开。** 条款本来就有 `draft` / `stable`。Harness 再加物理隔离：探索代码进 `poc/<topic>/`，稳定契约和 Trunk 生产路径分开。性能探索只读 TOPIC 到 PERF_BASELINE，观测数字进不了 stable SLA。证伪走 reject + DEC，不许静默删条款留代码（[[BEH-020]]）。没有这层，NDF 树会被探索写脏。

**文字指挥，硬门不砍。** 日常不走 Commander / Episode / Replay。错仓库、越界写根、缺人审 bundle、并发写、上下文漂移、伪造 completion、超预算：证不了就停。见 [`SECURITY.md`](SECURITY.md)。NDF 强调决策可追溯；Harness 把「这次派发批的是哪一版契约切片」收成 bundle SHA。文件在，不等于人批过。

**两边读同一份上下文。** Control 和 Implementation 共用 Task Manifest、同一 `manifest_sha`。失败只报 `context_verify_failed` 和 SHA。人修装订器或重审就行，不用猜 Agent 读错了哪段聊天。条款图本来是为了让 Agent 拉精确邻域，而不是塞 400 页 PDF；同一 manifest 保证写文档的和写代码的看见同一邻域。

**宿主可换。** Cursor / OpenClaw / Claude Code / OpenCode / Codex / generic；缺 CLI 可以 fallback。成功看磁盘 `ndf-agent-completion/v1`，不看某个面板亮不亮。

原始提案 §8 里的 `ndf ingest` / `ndf publish`，本包没做成，也不装作做成了。交付的是治理 CLI 和工作流纪律。

## 5. 日常怎么走：初始化、Idea、POC、关闭

假定消费仓已装 dual-track，指挥 Agent 已加载 ndf-workflow。安装见 [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)。

规矩说完了，看人每天说什么、盘上长什么。

### 初始化项目

人说：**初始化项目**。

| 步骤 | 人说 / 做 | 盘上出现什么 | 成功看什么 |
|------|-----------|--------------|------------|
| 角色向导 | **角色已配置** | `ndf.workflow.yaml` 三角色；Genesis `GATES.md` 回执 | `roles_unbound=false` |
| 绑内核 | Command 写，不另派 | `FOUNDATION.md` + `GATES.md` 骨架 | mode、Trunk SHA、roles SHA；不写产品长文 |
| 一次派发 | **派发** | Control 写满 `spec/00-50`（多为 draft），复现测试/金标进 configs / baselines | 磁盘 completion；测不出则 `baseline_status=deferred`，「继续」补测 |
| 仅 greenfield | **可以建立初始主线** | 一次 `genesis-pack` | adopt 跳过 |
| 冻结 | **GENESIS已审核** | 非 SLA 骨架升 `stable`；已复现基线/SLA 升 `stable` | 项目进入 operational |

人这边尽量只说：角色，派发，GENESIS已审核。别在 GENESIS 后再走一轮日常 promote 才升骨架。做完这步，后面的优化至少有个对照目标。

### 提交 Idea

人说：**提交Idea**，或者直接描述需求。

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆成两个互相引用的提案 |
| ambiguous | 先问人；MUST NOT 默认 poc |

产品 track 拿不准就默认 **poc**。落地等人 **已确认**，审核等人 **已审核**。没确认就别动 Trunk / stable。新意图先进开放提案，别直接改稳定圣经。

### POC 探索

提案「已审核」后，Control 一次写齐装订器 `poc/<topic>/ndf/`：

`TOPIC`，`DESIGN`，`PERF_BASELINE`，`DELTA`，`INTERFACE`（以及 `GATES`）

开题填 `explore_surface`。跟活跃 exploring 相交就写 depends / conflicts，别默认能并行。

人审完契约说：**派发**。

1. `GATES.md` 追加 `bundle_dispatch` + **bundle SHA**（契约 review-slice）；
2. `poc-dispatch --send`，Implementation 只写 `poc/<topic>/`；
3. 成功只认磁盘 `ndf-agent-completion/v1`。

之后说 **继续** 或 **关闭**。假设 / 接口 / 测量协议 / 写边界真改了才换 SHA；Numbers、Rounds、evidence 追加不重审。契约变了、SHA 没跟上，就是 gate drift：先看 slice diff，再重审「派发」。别只甩两个 hex。

### 关闭 POC

人说：**关闭**。先跑只读 plan：

```bash
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject
```

| mode | 含义 |
|------|------|
| **promote** | 全量合入；draft 升 stable；干净合入 `src/`；编译 + 性能 + 金标（[[META-006]]）；语义核要 / 不要 / 延期（[[META-004]]） |
| **partial** | 子集合入；TOPIC 可仍 exploring |
| **reject** | 负结果 DEC + deprecated；装订器归档 |

闸门没过完，主题别先标 `promoted`。晋升就让圣经变好一截；拒绝就把负结果记下来。两种都别靠静默覆盖。

### 口令速查

| 人说 | 主要工件 | 成功信号 |
|------|----------|----------|
| 初始化项目 | FOUNDATION / `spec/00-50` / baselines | `GENESIS已审核` + operational |
| 提交Idea | `spec/open/` 或 `spec/meta/open/` 提案 | 「已确认」「已审核」 |
| 派发 | bundle SHA + pack + worker 写入 | 磁盘 completion |
| 继续 | 修订装订器；契约变了才换 SHA | 再次合法派发 + completion |
| 关闭 | close plan；promote / partial / reject | TOPIC status + 归档 / Trunk 验证 |

## 还想往下看

- [`WORKFLOW.md`](WORKFLOW.md)：轨道、门禁、关闭模式
- [`WORKFLOW-OVERVIEW.md`](WORKFLOW-OVERVIEW.md)：调用图与闭合回路
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：三层、派发管线、安全边界
- [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)：装进消费仓
- [`TOOLS.md`](TOOLS.md)：治理 CLI
- [`SECURITY.md`](SECURITY.md)：fail-closed 清单
- 安装后的 `spec/meta/language.md` 和 `process.md`：条款正文 SoT

聊天里长不出能查的规范。NDF 管怎么把圣经写进树、图、git。Harness 管人怎么用五句口令指挥 Agent：写界卡死，做完以磁盘回执为准。
