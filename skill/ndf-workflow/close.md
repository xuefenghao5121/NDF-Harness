# Close — 关闭主题

人说「关闭」或选定收口模式后执行。先 **plan（只读）**，再提案/委派 apply。

```bash
python3 spec/meta/tools/ndf_close.py plan \
  --topic <topic> --mode promote|partial|reject
```

读 plan：§4b 语义核、§4c 基线 stale、§4d 表面冲突。禁止跳过 plan 宣称收口。

## 模式

| mode | 含义 |
|------|------|
| **promote** | 全量合入；draft→stable；干净合入 `src/`；`Promotes: <topic>`；编译+性能+金标（META-006） |
| **partial** | 子集合入；TOPIC 可仍 exploring |
| **reject** | 负结果：DEC + deprecated；TOPIC=`rejected`；默认 `trunk_src_writes=none`；装订器迁 archive |

promote 提案 MUST：引用 TOPIC + draft→stable ID 清单 + **语义核**（要 / 不要+理由 / 延期）。
稳定性能 SLA 须 `depends-on` API + `trunk-ref`（META-005）。

## 顺序

1. plan → 对人展示决策点与 blockers
2. 需契约变更 → [proposal.md](proposal.md) →「已确认」/「已审核」
3. `trunk_src_writes=required` → Claude Code（[delegate.md](delegate.md)）
4. index + graphcheck；promote 路径跑编译/性能/金标更新
5. 全部通过才改 TOPIC status（promoted / rejected）；同步 NOTES 头

探索中发现的 Trunk bug：默认本主题修测；合入另开 `bug` 或挂 promote 切片。
