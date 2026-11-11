"""GAGOS's one tool for a crew agent: run its changes' tests in the sandbox
(2026-11-11, the operator's choice "Files + sandboxed tests").

A crew agent edits a masked copy of the project with its own file tools. When
it wants to know whether its change works, it calls ``run_tests``. This server,
started by the agent's CLI over stdio (the Model Context Protocol), then:

1. reads what the agent changed, created and deleted in its copy
   (:func:`crew_workspace.changes`) and restores the real values
   (:func:`crew_workspace.restore`) from a state file kept OUTSIDE the copy,
   where the agent cannot read it;
2. runs those changes' tests and the type check in GAGOS's sealed sandbox
   (:func:`sandbox_tests.run_change_tests`, the same step every proposal
   passes), judged against the base commit;
3. answers with the verdict masked again under the copy's placeholders and
   passed through the egress scrubbers, so nothing the copy hid comes back.

Model-written code runs only there. The agent gets no shell, no web and no
other tool of GAGOS's.

Usage (by the agent's CLI, never by hand)::

    python tools/gagos_crew_mcp.py --project <repo> --state <state.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import IO, Any

PROTOCOL = "2025-06-18"
SERVER = {"name": "gagos-crew", "version": "1"}

RUN_TESTS = {
    "name": "run_tests",
    "description": (
        "Run the tests of everything you have changed so far, and the "
        "frontend's type check, in GAGOS's sealed sandbox, judged against the "
        "base commit. Takes no arguments. Answers PASSED, BROKE (with the tests "
        "or type errors your change caused), UNTESTED (no test covers the "
        "change) or UNAVAILABLE (the sandbox could not run)."
    ),
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
}


def _reply(id_: Any, result: Any = None, error: tuple[int, str] | None = None) -> dict:
    out: dict = {"jsonrpc": "2.0", "id": id_}
    if error is None:
        out["result"] = result
    else:
        out["error"] = {"code": error[0], "message": error[1]}
    return out


def handle(message: Mapping, tools: Mapping[str, Callable[[dict], str]]) -> dict | None:
    """One JSON-RPC message in; the reply, or None for a notification."""
    method = message.get("method")
    id_ = message.get("id")
    if id_ is None:
        return None  # notifications (notifications/initialized ...) need no reply
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion") or PROTOCOL
        return _reply(
            id_,
            {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER,
            },
        )
    if method == "ping":
        return _reply(id_, {})
    if method == "tools/list":
        return _reply(id_, {"tools": [RUN_TESTS] if "run_tests" in tools else []})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        if name not in tools:
            return _reply(id_, error=(-32602, f"unknown tool: {name}"))
        try:
            text = tools[name](params.get("arguments") or {})
            return _reply(
                id_, {"content": [{"type": "text", "text": text}], "isError": False}
            )
        except Exception as exc:  # said to the agent, never hidden
            return _reply(
                id_,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": f"run_tests failed: {type(exc).__name__}",
                        }
                    ],
                    "isError": True,
                },
            )
    return _reply(id_, error=(-32601, f"method not found: {method}"))


def serve(
    stdin: IO[str], stdout: IO[str], tools: Mapping[str, Callable[[dict], str]]
) -> None:
    """Line-delimited JSON-RPC over stdio until the input closes."""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            reply = _reply(None, error=(-32700, "parse error"))
        else:
            reply = handle(message, tools)
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def save_state(ws, path: Path) -> None:
    """Keep what restores the agent's copy OUTSIDE it (it holds real values)."""
    Path(path).write_text(
        json.dumps(
            {
                "root": str(ws.root),
                "base_commit": ws.base_commit,
                "shown": ws.shown,
                "mapping": ws.mapping,
                "left_out": ws.left_out,
            }
        ),
        encoding="utf-8",
    )


def load_state(path: Path):
    from aios.maintenance.crew_workspace import Workspace

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Workspace(
        root=Path(data["root"]),
        base_commit=data["base_commit"],
        shown=data["shown"],
        mapping=data["mapping"],
        left_out=data["left_out"],
    )


def run_tests_for(
    project: Path,
    ws,
    *,
    redact: Callable[[str], str],
    run: Callable[..., Any] | None = None,
) -> str:
    """The ``run_tests`` answer for the agent working in *ws*."""
    from aios.maintenance import crew_workspace as cw
    from aios.maintenance import sandbox_tests as st
    from aios.maintenance.daily_work import ProposalRefused, mask_like

    try:
        changed = cw.restore(ws, cw.changes(ws))
    except ProposalRefused as exc:
        return f"REFUSED: {exc}"
    if not changed:
        return "UNTESTED: you have not changed anything yet"
    run = run or st.run_change_tests
    with st.BaseTrees(project) as trees:
        verdict = run(trees, base_commit=ws.base_commit, changes=changed)
    lines = [f"{verdict.outcome.upper()}: {verdict.summary}"]
    if verdict.broken:
        lines.append("broken by your change: " + "; ".join(verdict.broken[:20]))
    if verdict.failing_anyway:
        lines.append(
            "failing without it too: " + "; ".join(verdict.failing_anyway[:10])
        )
    text = "\n".join(lines)
    # Under the copy's own mask, then the scrubbers: nothing hidden comes back.
    return redact(mask_like(text, ws.mapping) if ws.mapping else text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--state", required=True)
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from tools.gagos_daily import egress_redact

    ws = load_state(Path(args.state))
    project = Path(args.project)
    serve(
        sys.stdin,
        sys.stdout,
        {"run_tests": lambda _args: run_tests_for(project, ws, redact=egress_redact)},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
