# NDF Harness 治理（可移植摘要）

> 完整运行纪律以安装后的 `spec/meta/tools/GOVERNANCE.md` 为准。  
> 本文件为包内副本入口；维护仓权威实现旁路见 VENDOR.md。

## 一句话

先定义缺陷词典，再 Linter 举证，再 Advisor 给局部选项，沙盒证明意图，人工改 SoT；  
工具永不静默写条款 / git。

## 主链

```text
taxonomy → ndf_index → graphcheck ‖ bindcheck → advise plan → simulate → human edit → recheck
```

## POC 收口旁路

```text
ndf_close plan → human promote/reject → index + graphcheck
```

## 命令卡

见 [`docs/GOVERN.md`](docs/GOVERN.md)。
