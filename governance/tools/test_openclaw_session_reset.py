#!/usr/bin/env python3
"""Self-check: OpenClaw dispatch resets session before each hop."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import ndf_dispatch_send as dispatch  # noqa: E402


def main() -> int:
    os.environ.pop("NDF_OPENCLAW_RESET_SESSION", None)
    assert dispatch._openclaw_reset_session_enabled() is True
    os.environ["NDF_OPENCLAW_RESET_SESSION"] = "0"
    assert dispatch._openclaw_reset_session_enabled() is False
    os.environ["NDF_OPENCLAW_RESET_SESSION"] = "1"
    assert dispatch._openclaw_reset_session_enabled() is True

    key = "agent:main:feishu:direct:ou_example"
    argv = dispatch._openclaw_sessions_reset_argv("openclaw", key)
    assert argv[:5] == ["openclaw", "gateway", "call", "sessions.reset", "--json"]
    params = json.loads(argv[argv.index("--params") + 1])
    assert params == {"key": key, "reason": "reset"}

    missing = dispatch._reset_openclaw_session(executable="openclaw", session_key="")
    assert missing is not None
    assert missing["error"] == "openclaw_session_reset_failed"
    assert missing["detail"] == "session_key_missing"

    assert dispatch._gateway_call_payload_ok('{"ok": true, "key": "x"}') is True
    assert dispatch._gateway_call_payload_ok('{"ok": false}') is False
    assert dispatch._gateway_call_payload_ok('{"error": {"type": "fail"}}') is False
    assert dispatch._gateway_call_payload_ok("") is False
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
