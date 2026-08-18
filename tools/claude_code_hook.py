"""PreToolUse hook: route a Claude Code tool call through the GAGOS gates.

Claude Code calls this before running a tool, passing the call as JSON on stdin
and reading a permission decision from stdout. That makes it the seam where an
external agent's actions can be adjudicated instead of being an opaque
subprocess -- the gap in the PTY-wrapper design that ships elsewhere.

Install (project settings):

    "hooks": {
      "PreToolUse": [{
        "matcher": "*",
        "hooks": [{"type": "command",
                   "command": "python tools/claude_code_hook.py"}]
      }]
    }

HONEST LIMIT: this is adjudication the client CHOOSES to consult, not
containment. Claude Code honours its own hook; a patched client, a different
agent, or a crashed hook simply does not ask. It raises the floor from "opaque"
to "adjudicated and recorded" and does not reach the guarantee the in-process
executor gives, which cannot be bypassed at all. See aios/application/
agent_bridge.py.

Fails CLOSED: any error denies the call. A hook that fails open is a hook that
stops existing the moment something goes wrong.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception as exc:  # noqa: BLE001 - fail closed on unparseable input
        _emit(False, f"GAGOS bridge: unreadable hook payload ({exc}).")
        return 0

    tool = str(event.get("tool_name") or event.get("tool") or "")
    payload = event.get("tool_input") or event.get("input") or {}

    try:
        from aios.application.agent_bridge import authorize

        decision = authorize(tool, payload if isinstance(payload, dict) else {})
    except Exception as exc:  # noqa: BLE001 - fail closed on any gate error
        _emit(False, f"GAGOS bridge: gate error, refusing ({exc}).")
        return 0

    _emit(decision.allowed, f"GAGOS {decision.zone}: {decision.reason}")
    return 0


def _emit(allowed: bool, reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow" if allowed else "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
