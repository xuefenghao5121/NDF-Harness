# Adapter: OpenClaw

1. Install root `AGENTS.md` from `workflow/AGENTS.md`（command / control default entry）.  
2. Optional: copy or symlink skill core into the OpenClaw skills directory:

```text
skills/ndf-workflow/SKILL.md  →  packages/ndf-harness/skill/ndf-workflow/SKILL.md
```

Prefer **pointer/symlink** over duplicating workflow prose.

3. OpenClaw sessions MUST follow root `AGENTS.md` track workflow; internal init/govern/sync
   modules are for Command Agent only.

See [`SKILL.md`](SKILL.md) wrapper.
