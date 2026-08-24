#!/usr/bin/env python3
"""Bootstrap the configured ACP session from AGENTS.md (creates resume jsonl)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[3]

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ndf_workflow_status as workflow  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap the configured ACP session (creates resume jsonl)."
    )
    parser.parse_args(argv)

    session_id = workflow.configured_acp_session_id()
    if not session_id:
        print("error: ACP session unconfigured in AGENTS.md", file=sys.stderr)
        return 1
    exe = shutil.which("claude")
    if not exe:
        print("error: claude CLI missing", file=sys.stderr)
        return 1
    resume_path = workflow.claude_acp_resume_path(session_id)
    if resume_path.is_file() and resume_path.stat().st_size > 0:
        print(f"resume already exists: {resume_path}")
        return 0
    cmd = [
        exe,
        "--session-id",
        session_id,
        "-p",
        "NDF ACP bootstrap: reply OK",
        "--output-format",
        "text",
    ]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode != 0:
        print(f"error: bootstrap failed exit={proc.returncode}", file=sys.stderr)
        return proc.returncode
    if not resume_path.is_file() or resume_path.stat().st_size == 0:
        print(f"error: resume missing after bootstrap: {resume_path}", file=sys.stderr)
        return 1
    print(f"ok: {resume_path} ({resume_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
