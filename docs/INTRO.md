# NDF Harness：人跟 Agent 一起干活时，圣经怎么钉住

版本 1.0.2。给要在人跟 Agent 一起做复杂系统设计 / 实现 / 验证的人看。

这不是操作手册（装包、CLI、排障见文末）。全文只推一条线：

**协作会把真正的规范散进聊天；NDF 规定圣经怎么写、怎么钉；Harness 再规定人说哪句才算授权、Agent 写到哪、怎样才算做完。** 后面五节按这条线展开。

上游格式提案（不是本仓 SoT）：
[hengliao1972/normative_language - `normative_language_cn.md`](https://github.com/hengliao1972/normative_language/blob/main/normative_language_cn.md)（v0.1）。  
装进消费仓后，说了算的是那边的 `spec/meta/` 和 `AGENTS.md`。这个包只是种子。

---

## 1. 问题：人-Agent 协作里，规范丢在哪儿

复杂系统的权威依据不该是实现本身，也不该是测试抽样，而该是一套说清「应当 / 不得 / 可以」的**规范性描述**。人跟 Agent 一起做设计时，这套描述往往根本没落成一个可查的工件。

### 场景 A：聊天成了真正的圣经

常见循环：人丢一段半成品描述，Agent 吐局部设计或测试报告，人再补澄清或纠正，几百轮下来。真正管设计的经常是：

> 背景参考 + 初稿 + 整段 prompt 纠正序列

这坨东西散在聊天、文档和脑子里：没法规范重放，后句悄悄盖前句，聊天一清就丢。系统有了，规范性描述没有。以后改代码只能考古。（原始提案 §1.3。）

### 场景 B：规范只活一个 PR

Spec Kit 一类脚手架也用 Markdown、「先规范后代码」，但规范常常跟着单个变更请求生灭：合入就扔。复杂系统要的是能跟着项目活几年的那本：能演进、能查、能对着某个基线说话。不是每发一个 PR 换一本。（原始提案 §3。）

### 场景 C：Agent「做完了」，但没人能核

就算有人开始把规范写进仓库，协作还会在下一层翻车：transport ACK、聊天一句 OK、stdout 一段 JSON，就被当成委派成功，磁盘上没有可核回执。或者面板、回放、多层 fail-closed 把一次日常 POC 拖成几小时，人盯仪式不盯假设。见 [`SECURITY.md`](SECURITY.md) 与 ADR-META-003 / ADR-META-004。

### 三个挑战（后面两节分别接）

| 挑战 | 问的是 |
|------|--------|
| 圣经要可演进 | 规范性描述能不能增量长、带历史、人和机器都能读？ |
| 探索不能脏主线 | 没证伪的机制能不能默认写成 stable、直接改生产路径？ |
| 权威与成功可检查 | 谁批准、写到哪、怎样算做完，能不能机械判定？ |

前一个挑战主要靠**格式**；后两个挑战格式不够，还要**工作流**。下一节先看 NDF 怎么钉格式。

---

## 2. NDF：规范性描述怎么写、怎么钉

**NDF（Normative Description Format）** 是叠加在 Markdown + Git 上的约定，外加小型工具愿景。不发明新文件格式，不搞服务器。纯文本加 `git` 就能写。

### 中间道路

两端都不要。纯散文：含混、不可合并、不可查询，Agent 时代连「收拢在一处」都做不到。全盘形式化（ASL、TLA+、证明助手）：工作量可能超过设计本身，早期含混和工程判断写不进去，能读的人变少。

NDF 的选择：自然语言当主载体；结构加在组织层（标识、分类、连接、版本），不把每句话写成形式语言；代码比散文便宜的地方就嵌规范性代码岛。目标是单调变好，不是完美。

### 一句纪律，三种结构

> 散文活在树里，语义活在图里，时间活在 git 里。稳定的条款 ID 是铆钉。

树（`spec/00-charter/` 到 `50-verification/`）管归属。图（`refines`、`depends-on`、`conflicts-with`、`verifies`...）管语义。Git 加决策记录管演化；取代，不静默删。

原子单元是**条款**：标题块 + `{#稳定ID}` + `<!-- ndf: ... -->`，正文用 MUST / SHOULD / MAY。精化层 L0 意图 -> L1 契约 -> L2 机制 -> L3 可执行模型都留着，用 `refines` 串，后层不覆盖前层。

### 协作循环（概念）

原始提案 §7：人写章程和 L0/L1 骨架；Agent 任务写成「基线 `spec-vX` + 引用条款 ID 的工单」；产出和纠正回流成条款、决策记录、开放问题，不能只活在聊天里；人类批规范性变更，Agent 提议并交叉校验。

### NDF 钉住了什么，还没钉什么

对第一节的挑战：NDF 主要回答「圣经要可演进」。它让规范性描述成为可版本管理、可交叉引用、可蒸馏进决策记录的工件。

提案 §9 也诚实：一致性靠评审不是证明；蒸馏会丢信息；纪律会衰减；`refines` 记了但不验证。

它**还没规定**（因而第一节的后两个挑战仍悬着）：

- 探索试错的代码写在哪，怎么禁止误改主线；
- 人说哪一句才算授权一次委派；
- 怎样才算一次 Agent 任务「做完」；
- 日常要不要让人选工具、啃控制面。

格式解决「圣经怎么写」。人跟 Agent 每天怎么围着这本圣经协作，要靠工作流。这就是 Harness 出场的理由。

---

## 3. 缺口在哪儿，Harness 工作流怎么定义

**NDF Harness** 不是第二套产品圣经。它是把已验证的 **NDF 流程纪律**打成可安装种子：条款语言、双轨过程、五句口令指挥面、治理 CLI、运行时 adapter。

装完后消费仓的 `spec/meta/` 与 `AGENTS.md` 说了算。包只负责第一次（或 adopt）把种子放对。蒸馏方向是单向的：消费仓验证过的实践进包，再分发。禁止用包反推纠正已落地的本地 SoT。

一句话分工：

```text
原始 NDF：条款怎么写、图怎么连、prompt 怎么蒸馏进决策
Harness：谁说哪句才派、写到哪、怎样算完成、探索怎么不脏主线
```

对照第一节的三个挑战，Harness 补的是后两格，并把第一格接到日常口令上：

| 挑战 | 原始 NDF | Harness 工作流 |
|------|----------|----------------|
| 圣经可演进 | 条款树 + 图 + git | Genesis 冻结对照骨架；日常提案进 `spec/open/` 或 `spec/meta/open/` |
| 探索不脏主线 | 未钉写界 | 双轨 [[CHR-008]] / [[BEH-018]]：试错只在 `poc/<topic>/`；探索期 MUST NOT 改 Trunk `src/` / `include/` / `tests/` |
| 权威与成功可检查 | 「人批 PR」是概念 | 五句口令 + `GATES` bundle SHA（[[META-010]]）；成功 = 磁盘 `ndf-agent-completion/v1`；Command / Control / Implementation 写根分裂 |

再细一点，原始提案留下的空洞与落地条款（权威在安装后的 `spec/meta/`）：

| 原始没钉死的 | Harness 落地 |
|--------------|--------------|
| §7 是概念循环；人还要选工具 | 五句口令是唯一人类入口（[`skill/ndf-workflow/`](../skill/ndf-workflow/SKILL.md)） |
| 文件在 ≠ 已批准 | 口令回执（人、时间、内容 SHA）；review-slice bundle SHA |
| 「圣经在」≠ 一次委派完成 | ACK / stdout 不算成功 |
| 人与 Agent 读写对称 | 未绑定角色则 `roles_unbound`，派不出去 |
| `option` / DSE 无主题装订与性能读序 | 装订器 + [[META-007]]：Δ% 只读 PERF_BASELINE；探索数字进不了 stable SLA（[[CON-POC-001]]） |
| `ndf init` 不冻结对照目标 | Genesis：绑内核，一句「派发」，再 `GENESIS已审核`（[[META-009]]） |

所以 Harness 的工作流定义可以收成一句：**人只通过口令行使权威；Agent 只在写根内执行；NDF 条款与装订器是共享记忆；磁盘回执是唯一成功信号。** 下一节展开这句话带来的具体优势。

---

## 4. 创新点：人-Agent 协同里，NDF 特征怎么变成优势

本节不另起炉灶。每一条都是上一节那句合同的展开，并且点明它继承了 NDF 的哪块特征。

### 人的认知合同极窄（NDF 的共享记忆 + 可执行权威）

人口令只有五句：初始化项目 / 提交Idea / 派发 / 继续 / 关闭（健康是只读旁路）。

人出 Idea、审契约、说口令、看 blockers 和磁盘回执。不用选 skill，不用开面板，不用背 CLI。指挥面（Command）听口令、造 pack、等人审、调工具、把失败原因甩回来。

NDF 特征在这里的样子：Agent 任务不再靠「环境聊天历史」，而靠条款 ID、装订器和同一份 manifest。这正是原始提案里「基线 + 条款工单」想要、但没做成日常协议的那一步。

### 权威不对称，写根可执行（把 §7 的角色不对称钉死）

| 层 | 默认谁 | 写什么 |
|----|--------|--------|
| Command | 当前宿主 + ndf-workflow | `tmp/`、门禁回执、派发触发；不写 worker 实现 |
| Control | OpenClaw（可 fallback） | 提案、装订器、门禁；bootstrap 设计 hop 可写 `spec/00-50` draft |
| Implementation | Claude Code ACP（可 fallback） | POC 只动 `poc/<topic>/`；promote / genesis 才动 Trunk |

人批准规范性变更和「派发」；Agent 在 `allowed_write_root` 里干活。原始 §7 说「人对权威不对称、对读写对称」；Harness 用角色绑定和写根把它跑成 fail-closed：没绑角色，派不出去。

### 探索与主线双轨（NDF 的 draft/stable + 可演进，落到目录）

条款可以有 `draft` / `stable`；Harness 再加上物理隔离：探索代码进 `poc/<topic>/`，稳定契约和 Trunk 生产路径分开。性能探索读 TOPIC 到 PERF_BASELINE，不把观测数字写进 stable SLA。证伪走 reject + DEC，不静默删条款留代码（[[BEH-020]]）。

没有双轨，NDF 树会被探索污染；有了双轨，树才能真的「单调变好」。

### 文字优先，硬门不砍（门禁身份，不是文件存在）

日常不走 Commander / Episode / Replay。硬门保留：错仓库、越界写根、缺人审 bundle、并发写、上下文漂移、伪造 completion、超预算。证不了安全就停。见 [`SECURITY.md`](SECURITY.md)。

NDF 强调决策记录和可追溯；Harness 把「这一次派发批准的是哪一版契约切片」收成 bundle SHA。文件在磁盘上，不等于人批准过。

### 同一 `manifest_sha`（图邻域检索的工作流版）

Control 与 Implementation 读同一份 Task Manifest。失败只报 `context_verify_failed` 和 SHA。人修装订器或重审，不用猜 Agent 读错了哪段聊天。

原始 NDF 用条款图让 Agent 拉「精确邻域」而不是塞 400 页 PDF；Harness 用同一 manifest，保证文档 Agent 和代码 Agent 看见的是同一邻域。

### 宿主可换，成功不绑 IDE

Cursor / OpenClaw / Claude Code / OpenCode / Codex / generic；缺 CLI 可 fallback。成功看磁盘 `ndf-agent-completion/v1`，不看某个面板是否亮绿。

刻意不宣称：原始提案 §8 的 `ndf ingest` / `ndf publish` 等愿景工具。本包交付的是治理 CLI 与工作流纪律。

---

## 5. 跟着工作流走：初始化、Idea、POC、关闭

假定消费仓已装 dual-track，指挥 Agent 已加载 ndf-workflow。安装见 [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)。

这一节是第三节合同、第四节优势的**日常形态**：同一条逻辑，换成人口令顺序。

### 初始化项目：先钉对照目标

人说：**初始化项目**。

| 步骤 | 人说 / 做 | 盘上出现什么 | 成功看什么 |
|------|-----------|--------------|------------|
| 角色向导 | **角色已配置** | `ndf.workflow.yaml` 三角色；Genesis `GATES.md` 回执 | `roles_unbound=false` |
| 绑内核 | Command 写，不另派 | `FOUNDATION.md` + `GATES.md` 骨架 | mode、Trunk SHA、roles SHA；不写产品长文 |
| 一次派发 | **派发** | Control 写满 `spec/00-50`（多为 draft），复现测试/金标进 configs / baselines | 磁盘 completion；测不出则 `baseline_status=deferred`，「继续」补测 |
| 仅 greenfield | **可以建立初始主线** | 一次 `genesis-pack` | adopt 跳过 |
| 冻结 | **GENESIS已审核** | 非 SLA 骨架升 `stable`；已复现基线/SLA 升 `stable` | 项目进入 operational |

人这边尽量只说：角色，派发，GENESIS已审核。别在 GENESIS 后再走一轮日常 promote 才升骨架。  
对应挑战：圣经有了可演进的起点，对照目标被冻结。

### 提交 Idea：先分流，再进树

人说：**提交Idea**（或直接描述需求）。

| plane | 写根 |
|-------|------|
| product | `spec/open/` |
| process | `spec/meta/open/` |
| mixed | 拆成两个互相引用的提案 |
| ambiguous | 先问人；MUST NOT 默认 poc |

产品 track 拿不准就默认 **poc**。落地等人 **已确认**，审核等人 **已审核**。没确认就别动 Trunk / stable。  
对应挑战：新意图先进开放提案，不直接改稳定圣经。

### POC 探索：隔离试错，口令授权，磁盘收工

提案「已审核」后，Control 一次写齐装订器 `poc/<topic>/ndf/`：

`TOPIC`，`DESIGN`，`PERF_BASELINE`，`DELTA`，`INTERFACE`（以及 `GATES`）

开题填 `explore_surface`。跟活跃 exploring 相交就写 depends / conflicts，别默认能并行。

人审完契约说：**派发**。

1. `GATES.md` 追加 `bundle_dispatch` + **bundle SHA**（契约 review-slice）；
2. `poc-dispatch --send`，Implementation 只写 `poc/<topic>/`；
3. 成功只认磁盘 `ndf-agent-completion/v1`。

之后说 **继续** 或 **关闭**。假设 / 接口 / 测量协议 / 写边界真改了才换 SHA；Numbers、Rounds、evidence 追加不重审。契约变了、SHA 没跟上，就是 gate drift：先看 slice diff，再重审「派发」。  
对应挑战：探索不脏主线；权威与成功可检查。

### 关闭 POC：晋升、子集、或负结果

人说：**关闭**。先跑只读 plan：

```bash
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|partial|reject
```

| mode | 含义 |
|------|------|
| **promote** | 全量合入；draft 升 stable；干净合入 `src/`；编译 + 性能 + 金标（[[META-006]]）；语义核要 / 不要 / 延期（[[META-004]]） |
| **partial** | 子集合入；TOPIC 可仍 exploring |
| **reject** | 负结果 DEC + deprecated；装订器归档 |

闸门没过完，主题别先标 `promoted`。  
对应挑战：圣经单调变好（晋升）或诚实留下负结果（拒绝），都不靠静默覆盖。

### 口令速查（同一条链的压缩版）

| 人说 | 主要工件 | 成功信号 | 接到哪条挑战 |
|------|----------|----------|--------------|
| 初始化项目 | FOUNDATION / `spec/00-50` / baselines | `GENESIS已审核` + operational | 圣经可演进 |
| 提交Idea | `spec/open/` 或 `spec/meta/open/` 提案 | 「已确认」「已审核」 | 圣经可演进 |
| 派发 | bundle SHA + pack + worker 写入 | 磁盘 completion | 权威可检查；探索隔离 |
| 继续 | 修订装订器；契约变了才换 SHA | 再次合法派发 + completion | 同上 |
| 关闭 | close plan；promote / partial / reject | TOPIC status + 归档 / Trunk 验证 | 三格一起收口 |

---

## 还想往下看

- [`WORKFLOW.md`](WORKFLOW.md)：轨道、门禁、关闭模式
- [`WORKFLOW-OVERVIEW.md`](WORKFLOW-OVERVIEW.md)：调用图与闭合回路
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：三层、派发管线、安全边界
- [`INSTALL.md`](INSTALL.md) / [`QUICKSTART.md`](QUICKSTART.md)：装进消费仓
- [`TOOLS.md`](TOOLS.md)：治理 CLI
- [`SECURITY.md`](SECURITY.md)：fail-closed 清单
- 安装后的 `spec/meta/language.md` 和 `process.md`：条款正文 SoT

协作把规范散进聊天。NDF 把圣经钉成树、图、git。Harness 再把人-Agent 的权威收成五句口令和磁盘回执：探索脏不了主线，聊天也不再冒充成功。
