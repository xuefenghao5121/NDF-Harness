# Meta Constraints — POC 与生产 SLA 隔离

> scope: ndf-process  
> 条款索引: `CON-POC-001`  
> 产品树 adopted 指针: `40-constraints/sla.md`

## POC 不纳入生产 SLA {#CON-POC-001}
<!-- ndf: kind=constraint level=must layer=L1 status=stable since=0.7 source=deduced scope=ndf-process -->
<!-- ndf: refines=CHR-008 depends-on=ARCH-008 -->

`poc/` 与 draft 探索条款下的性能数字 MUST NOT 自动成为产品 Trunk `status=stable`
SLA must 的一部分。相对对比实验若基线协议不同于产品诚实锚点，MUST 在产品 DEC/提案中
标注口径。
