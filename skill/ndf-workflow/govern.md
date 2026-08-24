# Govern（internal）

Read-only governance pass — detail in [`../../governance/docs/GOVERN.md`](../../governance/docs/GOVERN.md).

1. `python3 spec/meta/tools/ndf_index.py index`（+ `--meta` for process profile）.
2. `python3 spec/meta/tools/ndf_graphcheck.py --report tmp/ndf-graphcheck.md`.
3. Optional: `ndf_bindcheck check --all-topics`, `ndf_poc_isolation check --all-topics`.
4. Advise surfaces: `ndf_advise.py plan --surface graph|bind`（**never** auto-apply to SoT）.
5. Close planning: `ndf_close.py plan --topic <topic> --mode …` before promote/partial/reject.

Reports default to `tmp/`; tools MUST NOT write under `spec/open/`.

Human entry remains [SKILL.md](SKILL.md).
