# NDF Harness

基于 [NDF](https://github.com/hengliao1972/normative_language/blob/main/normative_language_cn.md) 规范的论文和预研 POC 工作流。给架构师和开发者用：把一篇论文、一个 IDEA 做成能反复跑的原型，而且过程能查、能回。

版本见 [`VERSION`](VERSION)，当前 **1.2.2**。变更记在 [`CHANGELOG.md`](CHANGELOG.md)。

做原型时最容易坏的是两件事。设计活在聊天里：人跟 Agent 来回几百轮，后一句盖前一句，清聊天就丢，下次再验证同一篇论文只能考古。试错还不关，`src/` 里全是过期实现。Harness 管的就是这两件事。

装进你的仓库之后，说了算的是那边的 `spec/meta/` 和 `AGENTS.md`。这个包是流程种子，不许用包去改已经定稿的本地规范。

## 两件核心

**POC 管理。** 每个验证主题占一个目录 `poc/<topic>/`。假设、接口、测量协议写在装订器里（`TOPIC`、`DESIGN`、`GATES`），不写在聊天里。人说「派发」时，契约会被钉成 bundle SHA。假设变了，SHA 变，得重新审；数字、实验日志、Rounds 追加，SHA 不变。Agent 说做完了，只认磁盘上的 `ndf-agent-completion/v1`。聊天一句 OK、运输 ACK、stdout 一段 JSON，都不算。主题、SHA、git 都能回到某一轮，不用翻模型会话。

**POC 回合。** 探索只许写 `poc/<topic>/`，不许改主干的 `src/`、`include/`、`tests/`。一个主题有开有关：跑通了就 promote 合进主线，证伪了就 reject，把否定结果记进决策记录并归档装订器。关了的 id 不许再开，再试就新开主题。试错有地方放，关题时清掉，主干不会被半成品撑满。

NDF 本身管规范怎么写成树、图、git。Harness 不管你的产品 SLA 怎么写，只管验证怎么开、怎么钉、怎么关。

## 每天怎么走

人对指挥面只说五句，不选 skill，不背 CLI。

| 你说 | 实际在干什么 |
|------|----------------|
| **初始化项目** | 绑角色，写出对照用的规范骨架和可复现基线，再冻结 |
| **提交Idea** | 把论文点或 IDEA 写成开放提案。人说「已确认」才算收下，说「已审核」才许开工 |
| **派发** | 人审过契约之后，才许 Agent 在写根里改代码 |
| **继续** | 改装订器再派。契约变了才换 SHA |
| **关闭** | 先看只读 close plan，再选 promote、partial 或 reject |

常见一条线：

提交Idea，已确认，已审核。Control 写齐装订器。你审完说派发。Implementation 只动 `poc/<topic>/`，磁盘上出现 completion。数字不够就继续。该收了就关闭。

不确定的产品想法默认走 poc，不要一上来改主干。产品和流程混在一起就拆成两个提案。分不清就问人，不要默认开题。

角色三层：Command 听口令、造 pack、等人审；Control 写提案和装订器；Implementation 只在允许的写根里改代码。没绑角色派不出去。Cursor、OpenClaw、Claude Code、OpenCode 都能当宿主，成功不绑某个 IDE。

## 装进仓库

Python 3.10+，stdlib，不用 pip。在消费仓根目录：

```bash
python3 /path/to/ndf-harness/install.py install \
  --profile dual-track \
  --runtime cursor,openclaw,claude-code
python3 /path/to/ndf-harness/install.py verify --repo . --profile dual-track \
  --runtime cursor,openclaw,claude-code
```

已有 NDF 树先 `install.py adopt` 看冲突，再 install，不要加 `--force` 覆盖已定稿的 `spec/meta/`。从 0.2 升上来走 [`docs/MIGRATION-1.0.md`](docs/MIGRATION-1.0.md)。

装完打开指挥 Agent（Cursor 会读 `.cursor/skills/ndf-workflow/`），说「初始化项目」或「提交Idea」。

## 手册

人读这一页就够。下面几份是装包、排障、查命令时才翻的，不是第二套说明书。

| 文件 | 什么时候看 |
|------|------------|
| [`docs/INSTALL.md`](docs/INSTALL.md) | 三种 profile、runtime 装到哪、adopt |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | SHA 漂了、OpenClaw 串 session、派发失败 |
| [`docs/TOOLS.md`](docs/TOOLS.md) | `spec/meta/tools/` 每个脚本干什么 |
| [`docs/SECURITY.md`](docs/SECURITY.md) | 过不了就停：写根、假 completion、凭证 |
| [`docs/ADAPTERS.md`](docs/ADAPTERS.md) | 各 IDE 能挂什么 |
| [`docs/MIGRATION-1.0.md`](docs/MIGRATION-1.0.md) | 0.2 仓怎么迁 |

条款正文在装好之后的 `spec/meta/language.md` 和 `process.md`。口令路由在 [`skill/ndf-workflow/SKILL.md`](skill/ndf-workflow/SKILL.md)。
