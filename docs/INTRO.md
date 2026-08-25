# NDF Harness：少说，写对地方，做完可查

版本 1.0.2。装包、CLI、排障在文末。这里只讲一件事：Harness 的内核。

人少言。Agent 有界。做完看盘，不看嘴。

> 五句口令对人。Command 听令、造 pack、等人审。Control 写提案和装订器。Implementation 只动允许的写根。成功只认磁盘 `ndf-agent-completion/v1`。探索进 `poc/`，契约与 Trunk 分轨。

原始 NDF 管「规范写成什么样」。Harness 管「人跟 Agent 每天怎么干」。装进消费仓后，说了算的是那边的 `spec/meta/` 和 `AGENTS.md`。这个包是种子。

上游格式提案（不是本仓 SoT）：
[hengliao1972/normative_language - `normative_language_cn.md`](https://github.com/hengliao1972/normative_language/blob/main/normative_language_cn.md)（v0.1）。

## 1. 失序

复杂系统该听谁？不听实现，不听抽样测试。听仓库里一份写清「应当 / 不得 / 可以」的规范。人跟 Agent 一起设计时，这份东西常常根本没落成文件。

言多而散。人丢半成品，Agent 吐设计与报告，人再补一句，几百轮。管事的往往是「参考文档 + 初稿 + 整段 prompt」。散在聊天和脑子里：没法重放，后句盖前句，清聊天就没了。系统有了，规范没有。以后改代码只能考古。（原始提案 §1.3。）

名随 PR 灭。Spec Kit 一类也用 Markdown、也说先规范后代码，可规范常跟单个变更一起生灭：合入就扔。复杂系统要的是能跟着项目活几年的那份，不是每发一个 PR 换一本。（原始提案 §3。）

成而不核。ACK、聊天一句 OK、stdout 一段 JSON，就当委派成功；盘上没有回执。或者面板和回放把一次日常 POC 拖成几小时，人盯仪式不盯假设。见 [`SECURITY.md`](SECURITY.md) 与 ADR-META-003 / ADR-META-004。

三问：

1. 规范能不能持续改、带历史、人和机器都读得懂？
2. 没证伪的东西能不能默认写成 stable、直接改生产路径？
3. 谁批准、写到哪、怎样算做完，能不能机器判定？

第一问靠怎么写。后两问靠怎么干。Harness 内核冲着后两问，顺手把第一问接进口令。

## 2. 底座：NDF

**NDF（Normative Description Format）** 是 Markdown + Git 上的约定。不造新格式，不开服务器。纯文本加 `git` 即可。

纯散文：含混、难合并、难查询。全盘形式化（ASL、TLA+、证明助手）：写起来可能比设计本身还重，早期含混和工程判断塞不进去。NDF 取中：自然语言为主；结构加在组织层（标识、分类、连接、版本）；该嵌代码就嵌规范性片段。

> 散文在树，语义在图，时间在 git。稳定条款 ID 把三者串起来。

树（`spec/00-charter/` 到 `50-verification/`）管归属。图（`refines`、`depends-on`、`conflicts-with`、`verifies`...）管语义。Git 加决策记录管历史；改意图就留下记录，别悄悄删。

条款：标题块 + `{#稳定ID}` + `<!-- ndf: ... -->`，正文 MUST / SHOULD / MAY。L0 意图、L1 契约、L2 机制、L3 可执行模型都留着，用 `refines` 串。

协作上，提案 §7 设想：人写章程和 L0/L1；Agent 接「基线 `spec-vX` + 条款 ID」的工单；产出回流成条款和决策记录；人批变更，Agent 提议。§9 也承认：一致性靠评审，不是证明；蒸馏会丢信息；纪律会松。

NDF 说清了「规范怎么写成可持续的仓库工件」。日常脏活它没说：试错写哪儿、人说哪句才算授权、怎样算 Agent 做完、要不要让人选工具。这些是 Harness 的活。

## 3. 内核：Harness

**NDF Harness** 不是再写一套产品规范。它是把已验证的流程纪律打成可安装种子：条款语言、双轨、五句口令、治理 CLI、运行时 adapter。

装完后消费仓说了算。包负责第一次（或 adopt）把种子放对。消费仓验证过的实践可以提炼进包再分发；反过来用包改已经落地的本地 SoT，不行。

```text
NDF：条款怎么写、图怎么连、prompt 怎么收成决策记录
Harness：谁说哪句才派、写到哪、怎样算完成、探索怎么不脏主线
```

### 四事

1. **少言**：人对指挥面只说五句。初始化项目 / 提交Idea / 派发 / 继续 / 关闭。不选 skill，不开面板，不背 CLI。入口见 [`skill/ndf-workflow/`](../skill/ndf-workflow/SKILL.md)。
2. **有界**：Command 听令、造 pack；Control 写提案和装订器；Implementation 只动 `allowed_write_root`。没绑角色就 `roles_unbound`，派不出去。
3. **分轨**：探索只在 `poc/<topic>/`；探索期 MUST NOT 改 Trunk `src/` / `include/` / `tests/`（[[CHR-008]] / [[BEH-018]]）。
4. **知止**：成功只认磁盘 `ndf-agent-completion/v1`。ACK / stdout 不算。派发要绑 `GATES` 里的 bundle SHA（[[META-010]]）。文件在，不等于人批过。

对三问：

| 你要什么 | NDF | Harness |
|----------|-----|---------|
| 规范能持续改 | 条款树 + 图 + git | Genesis 定出对照骨架；日常提案进 `spec/open/` 或 `spec/meta/open/` |
| 探索不脏主线 | （没定写界） | `poc/` 隔离；性能 Δ% 只读 PERF_BASELINE（[[META-007]]）；探索数字进不了 stable SLA（[[CON-POC-001]]） |
| 权威可检查 | 「人批 PR」还是概念 | 五句口令 + bundle SHA + 三角色写根 + 磁盘 completion |

同一 `manifest_sha` 给 Control 和 Implementation。Genesis：绑内核、一句「派发」、再 `GENESIS已审核`（[[META-009]]）。证伪走 reject + DEC，不许静默删条款留代码（[[BEH-020]]）。

## 4. 得其用

人这边：出 Idea、审契约、说口令、看 blockers 和磁盘回执。指挥面听令、造 pack、等人审、调工具、把失败原因甩回来。

写界：

| 层 | 默认谁 | 写什么 |
|----|--------|--------|
| Command | 当前宿主 + ndf-workflow | `tmp/`、门禁回执、派发触发；不写 worker 实现 |
| Control | OpenClaw（可 fallback） | 提案、装订器、门禁；bootstrap 设计 hop 可写 `spec/00-50` draft |
| Implementation | Claude Code ACP（可 fallback） | POC 只动 `poc/<topic>/`；promote / genesis 才动 Trunk |

`draft` / `stable` 是状态；`poc/` 是物理隔离。没有这层，条款树会被试错写乱。

日常不走 Commander / Episode / Replay。错仓库、越界写根、缺人审 bundle、并发写、上下文漂移、伪造 completion、超预算：过不了就停。见 [`SECURITY.md`](SECURITY.md)。

两边读同一份上下文。失败只报 `context_verify_failed` 和 SHA。人修装订器或重审，不用猜 Agent 读错了哪段聊天。

宿主可换：Cursor / OpenClaw / Claude Code / OpenCode / Codex / generic；缺 CLI 可以 fallback。成功不绑某个 IDE。

原始提案 §8 里的 `ndf ingest` / `ndf publish`，本包没做，也不装作做了。交付的是治理 CLI 和上面这套内核。

## 5. 行

假定消费仓已装 dual-track，指挥 Agent 已加载 ndf-workflow。安装见 [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)。

### 初始化项目

人说：**初始化项目**。

| 步骤 | 人说 / 做 | 盘上出现什么 | 成功看什么 |
|------|-----------|--------------|------------|
| 角色向导 | **角色已配置** | `ndf.workflow.yaml` 三角色；Genesis `GATES.md` 回执 | `roles_unbound=false` |
| 绑内核 | Command 写，不另派 | `FOUNDATION.md` + `GATES.md` 骨架 | mode、Trunk SHA、roles SHA；不写产品长文 |
| 一次派发 | **派发** | Control 写满 `spec/00-50`（多为 draft），复现测试/金标进 configs / baselines | 磁盘 completion；测不出则 `baseline_status=deferred`，「继续」补测 |
| 仅 greenfield | **可以建立初始主线** | 一次 `genesis-pack` | adopt 跳过 |
| 冻结 | **GENESIS已审核** | 非 SLA 骨架升 `stable`；已复现基线/SLA 升 `stable` | 项目进入 operational |

人尽量只说：角色，派发，GENESIS已审核。别在 GENESIS 后再走一轮日常 promote 才升骨架。做完这步，后面优化至少有对照目标。

### 提交 Idea

人说：**提交Idea**，或者直接描述需求。

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆成两个互相引用的提案 |
| ambiguous | 先问人；MUST NOT 默认 poc |

产品 track 拿不准就默认 **poc**。落地等人 **已确认**，审核等人 **已审核**。没确认就别动 Trunk / stable。新意图先进开放提案，别直接改已稳定的契约。

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

闸门没过完，主题别先标 `promoted`。能合就合进主线；合不了就把负结果记下来。别靠静默覆盖。

### 口令

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

言生于聊，不成于仓。NDF 管树、图、git。Harness 内核四事：少言、有界、分轨、知止。人拍板，Agent 在界内干，成以盘上的回执为准。
