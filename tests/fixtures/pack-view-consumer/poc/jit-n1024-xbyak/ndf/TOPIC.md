# Topic: jit-n1024-xbyak

> ndf_topic: jit-n1024-xbyak
> topic_id: jit-n1024-xbyak
> status: promoted
> closed_at: 2026-08-31
> close_mode: promote
> close_proposal: spec/open/proposal-promote-jit-n1024-xbyak.md
> src_commit: 1fd2e69c89bb3b2677842a0d7782f3c06fd65837
> spec_commit: pending
> archive: spec/archive/2026-08/poc-jit-n1024-xbyak/
> baseline_status: n/a
> baseline_trunk_sha: 7f2e646b00861e95bcc1996de1786aec927033d5
> baseline_protocol: spec/50-verification/verification.md
> perf_baseline: ndf/PERF_BASELINE.md
> next_gate: TOPIC已审核

The lifecycle/baseline/next_gate headers above are mutable runtime navigation and are
outside the human review slice.

**Close record（promote @ 2026-08-31，close_finalize）**：close-plan §4 收口
（[[META-018]] 合入/收口分 hop）。§5 证据：Implementation `promote_land` 磁盘回执
`result=success`（`src/.ndf-completion/promote_land-completion.json`）；land commit
`1fd2e69c89bb3b2677842a0d7782f3c06fd65837` 已 fast-forward 进 `main`，trailers
`Topic: jit-n1024-xbyak` / `Promotes: jit-n1024-xbyak` /
`Clauses: ARCH-FFT-008,ARCH-FFT-009`；VER-FFT-001..003 PASS on land；post-land
bench 1,800.894 ns/exec 复现 R0 1,802.135（Δ −63.4% vs `bl-trunk-7f2e646`
project 4,927.020）；graphcheck product 0 hard errors。`{#ARCH-FFT-008}` /
`{#ARCH-FFT-009}` 已 stable 落 `spec/10-architecture/architecture.md`；
`{#CON-SLA-FFT-001}` 保持 `not-established`（[[CON-POC-001]]，R0 数字不写
stable must SLA）。归档：以指针 `spec/archive/2026-08/poc-jit-n1024-xbyak/` 登记
（本 hop 不物理迁移，装订器原位保留；物理归档由后续卫生动作执行）。
`spec_commit` 待 spec 收口 commit 后回填 `COMMITS.md`。后续同方向探索 MUST 开
平级新 topic 并声明 `depends_on_topics: jit-n1024-xbyak`（[[BEH-025]] 关闭后
重启）；MUST NOT 复活本 `topic_id`。

<!-- ndf:gate-slice begin=topic_contract -->
## Scope and hypothesis

> explore_surface: jit-xbyak, n1024-1d-complex, twiddle-lut
> depends_on_topics: none
> conflicts_with_topics: none

**Active hypothesis**（`active_hypothesis`）：对固定 N=1024 的 1D 复数 in-place 正向 FFT，
plan 期用 Xbyak 发射一份自然序 JIT 内核 + 预计算 twiddle LUT（地址编入 JIT），之后每次
execute 只跳 JIT 函数指针，不再进入 `fftwf_execute_dft`。在同一套
`cfg-n1024-1d-complex-inplace` 上，execute-only 墙钟 **低于** Genesis 骨架 project 线
（`bl-trunk-7f2e646`：4,927.020 ns/exec，`FFTW_ESTIMATE` + 调用方 malloc）。对未改造上游
FFTW MEASURE（3,968.078 ns/exec）只记账，MUST NOT 写成 stable `{#CON-SLA-*}` must。

**Success criteria（探索级）**：VER-FFT-001…003（线性/脉冲/移位，N=1024）PASS；PERF
Numbers 绑定 `vs=bl-trunk-7f2e646` × `cfg-n1024-1d-complex-inplace` × 可执行 measure
入口，相对 ESTIMATE 骨架报 Δ。未打过 ESTIMATE = 假设未证实，不得 promote、不得写
stable SLA。

**Non-goals（明确不做）**：高斯窗融合（`{#ARCH-FFT-005}` 留平级后续 topic）；AVX-512 /
SVE 指令 must 清单（第一刀标量或现有 SIMD 即可）；DIF 输出序 / 位逆序消除；把 adapt
改成 `FFTW_MEASURE` 冒充优化；动态链系统 `libfftw3` 作唯一内核；数值 must SLA /
×0.85 契约；嵌套子 POC（同题塞 SIMD / 融合 / PATIENT）。

**Proposal paths**：`spec/open/proposal-jit-n1024-xbyak.md`（track=poc，role=root）。

**Draft clauses**：`{#ARCH-FFT-008}`（JIT 固定 N 执行路径，status=draft）、
`{#ARCH-FFT-009}`（旋转因子 LUT N=1024，status=draft）。

**Baseline 对照**：`vs` = `bl-trunk-7f2e646` project 列（ESTIMATE 骨架，不是 MEASURE 列）；
金标 `baseline_trunk_sha` 指向 Genesis trunk
`7f2e646b00861e95bcc1996de1786aec927033d5`。
<!-- ndf:gate-slice end=topic_contract -->
