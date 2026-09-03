# Architecture — 代码与算法架构

> track: bootstrap · cycle_id: fft-jit-1d
> source_ref: docs/cycles/cycle-fft-jit-1d.md
> amends: spec/open/proposal-fftw-base-skeleton.md

## 宿主与内核边界 {#ARCH-FFT-001}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.1 source=deduced -->

系统 MUST 分为 **宿主** 与 **变换内核** 两层：

- **宿主**（C/C++）：公开 C ABI、缓冲生命周期、plan 调度。
- **内核**：第一骨架为 FFTW 衍生的 1D 复数路径（[[ARCH-FFT-007]]）；固定
  N=2^n（n=0…10，N≤1024）时 MAY 走 Xbyak JIT 路径（[[ARCH-FFT-008]]）。
  execute 经 plan handle 调用，MUST NOT 在每次 execute 重新 plan。

> rationale: FFTW 骨架保留；N=1024 JIT 已由 `jit-n1024-xbyak` promote 落地。

## 固定 N 流水线 {#ARCH-FFT-002}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.1 source=deduced -->

对 plan 期确定的常量 `N`，plan 流水线 MUST 为：

`N` → FFTW 衍生 planner 建立可缓存 plan → opaque handle。

`N` MUST 在 plan 前固定；execute MUST NOT 接受运行时变更的 N。

> rationale: Fixed-N pipeline without requiring JIT unfold on first skeleton.

## 算法核 {#ARCH-FFT-003}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.1 source=deduced -->

内核 MUST 实现复数正向 DFT（见 [[BEH-FFT-001]]）。第一骨架 MUST 跟随上游 FFTW 1D
算法与输出序。DIF 位逆序 Cooley-Tukey 为后续 JIT MegaKernel 路径，MUST NOT 作为
第一骨架必交付算法形态。

IFFT 为本周期架构注记，MUST NOT 作为本周期必交付的第二内核。

> rationale: FFTW-native first skeleton; DIF deferred.

## 旋转因子子系统 {#ARCH-FFT-004}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.1 source=deduced -->

非 JIT 路径 SHOULD 使用 FFTW 内部 twiddle 表。家族 JIT 路径 MUST 在 plan 期固化
twiddle：n≤8（N=2…256）MAY 用立即数池，n=9…10（N=512,1024）MUST 用预计算 LUT
（[[ARCH-FFT-009]]），MUST NOT 另造与 FFTW 平行的第二套 Trunk twiddle 子系统。

> rationale: FFTW twiddle for skeleton path; 家族 JIT n≤8 立即数池、n=9…10 LUT。

## 可选融合缝 {#ARCH-FFT-005}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.1 source=deduced -->

后续改造 SHOULD 支持在第一级蝶形前对输入乘预计算高斯窗，MUST NOT 要求独立的
全缓冲额外遍历作为第一骨架必交付路径。

> rationale: Optional fusion seam — not first-skeleton must.

## 模块布局 {#ARCH-FFT-006}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.1 source=deduced -->

Trunk 目录级分解 MUST 为：

| 路径 | 职责 |
|------|------|
| `include/` | 公开 C ABI |
| `third_party/fftw/` | FFTW vendor/fork（上游 SHA + GPL-2.0） |
| `src/host/` | plan 缓存、调度改造后的 1D 路径 |
| `src/adapt/` | 二次改造面（固定 N、in-place、ABI） |
| `src/jit/` | 固定 N JIT backend（[[ARCH-FFT-008]]；家族 n=0…10，N=2^n ≤1024） |

> rationale: genesis-pack 第一刀 blueprint；`src/jit/` 经 promote 启用。

## 初始实现源 {#ARCH-FFT-007}
<!-- ndf: kind=arch level=must layer=L0 status=stable since=0.1 source=stated -->

初始 Trunk 候选 MUST 以开源 FFTW 为起点（vendor 或明确记录的 fork 基线 SHA），
在其 1D 复数 FFT 路径上做二次改造。MUST NOT 把「空树手写 JIT 蝶形」作为
`可以建立初始主线` 的第一刀骨架。MUST NOT 以系统 `libfftw3` 动态链接作为唯一内核
（对照测量除外）。

二次改造本周期 must：固定 N、in-place、plan/execute 对齐 [[API-FFT-001]]。
固定 N=2^n（n=0…10，N≤1024）的 JIT 执行路径见 [[ARCH-FFT-008]] / [[ARCH-FFT-009]] / [[ARCH-FFT-011]]。

> rationale: proposal-fftw-base-skeleton 已确认；jit-n1024-xbyak promote 补齐 JIT 切片。

## JIT 固定 N 执行路径 {#ARCH-FFT-008}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.2 source=stated -->
<!-- ndf: depends-on=ARCH-FFT-001,ARCH-FFT-006,ARCH-FFT-007,CON-FFT-002 -->

Trunk MUST 在 `src/jit/` 为 **N=2^n 家族（n=0…10，N≤1024）** 提供 Xbyak 发射的
1D 复数 in-place 正向内核；`fft_execute` MUST 经 plan 缓存的函数指针调用，MUST NOT
在每次 execute 重新 generate。非 2 的幂或 N>1024 MUST 继续走 FFTW 衍生骨架
（[[ARCH-FFT-007]]）；n=0…10（N=2^n ≤1024）MAY 走家族 JIT。MUST NOT 要求本条
覆盖全部 N。

> rationale: `jit-n1024-xbyak` promote 后家族化；n=0…10 家族 JIT，非 2 的幂 / 超 N=1024 仍走骨架。

## 旋转因子 LUT（N=1024）{#ARCH-FFT-009}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.2 source=stated -->
<!-- ndf: depends-on=ARCH-FFT-004,ARCH-FFT-008 -->

N=1024 的 JIT 路径 MUST 使用 plan 期预计算 twiddle LUT（地址编入 JIT），MUST NOT
另造与 FFTW 平行的 Trunk twiddle 子系统；MUST NOT 把立即数编入指令当作本条 must
（路书阈值 N≤256）。

> rationale: 大 N 用 LUT；本条只锁定 N=1024。

## JIT 旋转因子按 N 分策固化 {#ARCH-FFT-011}
<!-- ndf: kind=arch level=should layer=L0 status=stable since=0.3 source=stated -->
<!-- ndf: refines=ARCH-FFT-009 depends-on=ARCH-FFT-004,ARCH-FFT-008,ARCH-FFT-009 -->

固定 N 的 JIT 路径 MAY 按变换长度选择 twiddle 固化方式（plan 期完成，execute MUST NOT
再算三角）：

- **n=0（N=1）**：退化 DFT（恒等）。
- **n=1…8（N=2…256）**：MAY 将旋转因子作为立即数编入指令（`mov` / 浮点常量池）。
  n=1…4 MAY 用全展开寄存器驻留核（无 bitrev/stage 循环）。
- **n=9…10（N=512, 1024）**：MUST 将 LUT 基址编入 JIT，execute 以向量加载读取
  （本仓 x86：`vmovaps` / `vmovups`）。MUST NOT 把立即数路径当作 N=1024 的 must。

非 2 的幂或 N>1024 MUST 继续走 FFTW 衍生骨架。仍 MUST 满足 [[ARCH-FFT-009]]：
MUST NOT 另造与 FFTW 平行的 Trunk twiddle 子系统。

> source: spec/open/proposal-jit-twiddle-imm-lut.md ; poc/jit-twiddle-imm-lut/ndf/TOPIC.md
> track: promote ; Topic: jit-twiddle-imm-lut
