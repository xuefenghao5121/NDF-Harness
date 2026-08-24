# Sync（internal）

Refresh package seeds into an operational repo — **diff first, no silent overwrite**.

1. Note package [`VERSION`](../../VERSION) and source commit in `spec/meta/tools/VENDOR-PIN.md`（optional）.
2. Diff `packages/ndf-harness/norms/meta/` vs installed `spec/meta/`; propose process deltas only.
3. Diff `governance/tools/` vs `spec/meta/tools/`; copy updated `ndf_*.py` after human ack.
4. Diff `skill/ndf-workflow/` vs mounted adapter skill; refresh pointer or copy tree.
5. Re-run govern smoke（index + graphcheck）.

MUST NOT use package content to reverse-correct consumer SoT without a process proposal.

Human entry remains [SKILL.md](SKILL.md).
