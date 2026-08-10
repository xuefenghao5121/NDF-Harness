# Daily governance commands

Assume tools installed under `spec/meta/tools/`.

```bash
python3 spec/meta/tools/ndf_index.py index
python3 spec/meta/tools/ndf_graphcheck.py --report tmp/ndf-graphcheck.md
python3 spec/meta/tools/ndf_bindcheck.py --report tmp/ndf-bindcheck.md
python3 spec/meta/tools/ndf_advise.py plan --surface graph --low-hanging-fruit \
  --report tmp/ndf-advise.md
python3 spec/meta/tools/ndf_advise.py plan --surface bind --low-hanging-fruit \
  --report tmp/ndf-advise-bind.md
# optional:
python3 spec/meta/tools/ndf_advise.py simulate --surface graph --issue <id> --option O1 \
  --report tmp/ndf-advise-sim.md
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode promote|reject|partial
python3 spec/meta/tools/ndf_poc_isolation.py check --all-topics
python3 spec/meta/tools/ndf_perf_baseline.py check --all-exploring
```

Reports: default `tmp/`；`--report -` = stdout；MUST NOT write under `spec/`.  
**sandbox pass ≠ apply.** Edit SoT only via proposal + human confirm.
