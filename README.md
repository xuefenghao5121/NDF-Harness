# NDF Harness

按 [NDF](https://github.com/hengliao1972/normative_language/blob/main/normative_language_cn.md) 写规范的论文和预研 POC 工作流。架构师、开发者拿它把论文或 IDEA 做成能反复跑的原型。验证留在仓库里，过后还能翻回来。

当前版本 **1.2.2**，见 [`VERSION`](VERSION)。

设计只写在聊天里，后一句会盖掉前一句，清掉会话就没了。试错直接写进 `src/`，过期实现会把主干撑满。所以每个验证主题占一个 `poc/<topic>/`，假设写在该目录的装订器里。你说「派发」，代码才许改。做完只看磁盘回执。题目有开有关，关了不许用同一个 id 再开。

打开指挥 Agent 说话就行（Cursor 读 `.cursor/skills/ndf-workflow/`）。不用选 skill，也不用背命令。只要说下面五句。没说出口，Agent 不能往下走。

## 五句口令

**初始化项目**

这个仓库从现在起按这套规矩干活。后面做 POC 要有对照，不能对着空气调参。

要定的是谁指挥、谁写设计、谁写代码，以及第一版规范骨架和可复现基线能不能冻住。中间还会问两句。**角色已配置**：三种角色绑好了，否则后面派发过不去。**GENESIS已审核**：骨架和测过的基线变成对照，不是又开一轮日常 POC。空仓和已有代码，中间问的话可能不一样，但都是先立项目再开题。

**提交Idea**

有一件要验证的事，先写成能审的提案。嘴上说一句，不能开工。

分两下。**已确认**：提案写的就是要证的事，可以进 `spec/open/`（改流程进 `spec/meta/open/`）。**已审核**：可以按这份提案写装订器，主干代码还是不能动。没确认就不能开题，也不能改主干。产品问题和流程问题拆成两份提案。分不清就问人。产品上拿不准，默认走 poc。

**派发**

刚看过的那一版契约，可以拿去跑。

按 `poc/<topic>/ndf/` 里现在写的假设、能改哪些目录、怎么算测过，去改 `poc/<topic>/`。指挥面把这一版做成 SHA，记在 `GATES.md`。写代码的人只能动这个目录，不能碰主干的 `src/`、`include/`、`tests/`。做完只认磁盘上的 `ndf-agent-completion/v1`。聊天里回一句 OK、运输层 ACK、终端打出一段 JSON，都不算完。没说派发，就不能写实现。文件在，不等于人批过。

**继续**

同一道题还没关，再跑一轮。这不是新 Idea。

指挥面去改装订器，改完还要再说一次「派发」。只追加数字、日志、Rounds，SHA 不变，契约不用重审。假设、接口、怎么测、能改哪些目录变了，SHA 会变，得再看一遍再派发。还是同一个假设，就留在这个 topic。想法已经岔开了，回去「提交Idea」另开一题，别在旧目录里再叠一套。

**关闭**

这轮探索到头了。主干要么合入，要么明确不合。否定结果要留下。题目不能一直 exploring。

指挥面先给一份只读的 close plan。再选怎么收。**promote**：跑通了，干净合进主干。**partial**：只合一部分，题还可以接着做。**reject**：证伪了，否定结果写进决策记录，装订器归档。这个 topic id 关了就不能再开。还想试，另开一题。

## 第一次怎么进仓

空仓或还没装过，在仓库根目录：

```bash
python3 /path/to/ndf-harness/install.py install \
  --profile dual-track \
  --runtime cursor,openclaw,claude-code
python3 /path/to/ndf-harness/install.py verify --repo . --profile dual-track \
  --runtime cursor,openclaw,claude-code
```

已有 NDF 树先跑 `install.py adopt` 看冲突，再 install，别加 `--force`。然后说「初始化项目」。装好以后听这个仓里的 `spec/meta/` 和 `AGENTS.md`，别听安装包里的旧稿。

## 做完一次 POC

立住之后按这个顺序说。看仓库里的文件，别看聊天摘要。

提交Idea，把要证的那句话说清楚。看提案，已确认，已审核。装订器写出来，看过再说派发。看磁盘回执和 `poc/` 里的证据。不够就继续。该停就关闭。

要回到某一轮，翻 topic 目录、GATES 和 git。契约变了看切片 diff，别拿两个哈希对一下完事。
