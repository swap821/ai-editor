#!/usr/bin/env python3
r"""End-to-end demo: real LLM edit -> YELLOW approval -> verify PASS.

Run with the canonical venv:
    .venv\Scripts\python e2e_yellow_verify.py

The script:
  1. Seeds a tiny Python module + sibling pytest in training_ground/.
  2. Asks the local model (qwen2.5-coder:3b) to edit the module.
  3. Captures the YELLOW human_required frame for edit_file.
  4. Replays the turn with the server-issued approval token.
  5. Asserts the forced auto-verify emits a PASS verdict.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

# Make the project root importable when running from tests/e2e/.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Keep the demo lightweight: no alignment interpreter pause, no extra chat indexing.
os.environ.setdefault("AIOS_INTERPRET_ALIGNMENT", "false")
os.environ.setdefault("AIOS_INDEX_CHAT", "false")
os.environ.setdefault("AIOS_REFLECT_ON_FAILURE", "false")

from fastapi.testclient import TestClient

from aios.api.main import app

# Suppress recalled memories so the model follows the directive, not stale trails.
import aios.api.main as _main_mod
_main_mod._recall_memory = lambda _query, _top_k=3: None
_main_mod._recall_lessons = lambda *_a, **_k: []
_main_mod._recall_skills = lambda *_a, **_k: []

from aios import config as config_mod
from aios.security import scope_lock

ROOT = Path(__file__).resolve().parents[2]
SCOPE: Path | None = None
MODULE: Path | None = None
TEST: Path | None = None


def make_scope() -> Path:
    scope = ROOT / ".aios" / "tmp" / "e2e_scope" / "demo_scope"
    scope.mkdir(parents=True, exist_ok=True)
    return scope


def seed() -> None:
    global SCOPE, MODULE, TEST
    SCOPE = make_scope()
    MODULE = SCOPE / "demo_module.py"
    TEST = SCOPE / "test_demo_module.py"
    # Executor/sandbox = the temp scope; project root stays the repo root so the
    # rollback engine sees a real sandbox (scope root != project root).
    config_mod.SCOPE_ROOTS = [SCOPE]
    scope_lock.set_scope_roots([SCOPE])
    MODULE.write_text('def hello():\n    return "hello"\n', encoding="utf-8")
    TEST.write_text(
        "from demo_module import hello\n\ndef test_hello():\n    assert hello() == 'hello ai-os'\n",
        encoding="utf-8",
    )


def module_path() -> str:
    return MODULE.relative_to(ROOT).as_posix()


def clean() -> None:
    import shutil
    if SCOPE is not None:
        shutil.rmtree(SCOPE, ignore_errors=True)


def parse_sse(response) -> list[dict[str, object]]:
    """Parse event/data lines from a TestClient streaming response."""
    events: list[dict[str, object]] = []
    current: dict[str, object] = {}
    for raw in response.iter_lines():
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event: "):
            current["event"] = line[len("event: "):]
        elif line.startswith("data: "):
            current.setdefault("data", []).append(line[len("data: "):])
        elif line == "":
            if "event" in current:
                payload = json.loads("".join(current.get("data", [])))
                events.append({"event": current["event"], "data": payload})
            current = {}
    return events


def generate_turn(client: TestClient, session_id: str, tokens: list[str]) -> list[dict[str, object]]:
    directive = (
        f"The file {module_path()} contains:\n\n"
        "def hello():\n"
        "    return \"hello\"\n\n"
        "Use the edit_file tool to replace the line `return \"hello\"` "
        "with `return \"hello ai-os\"` exactly. Do not explain; just call the tool."
    )
    body = {
        "sessionId": session_id,
        "modelId": "ollama.qwen2.5-coder:7b",
        "messages": [{"role": "user", "content": directive}],
        "approvalTokens": tokens,
    }
    with client.stream("POST", "/api/generate", json=body) as resp:
        resp.raise_for_status()
        return parse_sse(resp)


def find_human_required(events: list[dict[str, object]]) -> tuple[str, dict[str, object]] | None:
    for ev in events:
        if ev.get("event") == "human_required":
            data = ev["data"]
            inp = data.get("input", {})
            return str(inp.get("approvalToken") or ""), data
    return None


def find_verify_pass(events: list[dict[str, object]]) -> dict[str, object] | None:
    for ev in events:
        if ev.get("event") == "verify_result":
            if ev["data"].get("verdict") == "pass":
                return ev["data"]
    return None


def main() -> int:
    clean()
    seed()
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            for attempt in range(1, 4):
                session_id = f"e2e-{uuid.uuid4().hex[:8]}"
                print(f"[e2e] attempt {attempt}: session={session_id}")
                events1 = generate_turn(client, session_id, [])
                hr = find_human_required(events1)
                if hr is None:
                    print(f"[e2e] attempt {attempt}: no YELLOW human_required; retrying...")
                    continue
                token, hr_data = hr
                print(f"[e2e] YELLOW approval token issued: {token[:16]}...")
                print(f"[e2e] Request text: {hr_data.get('text')}")

                events2 = generate_turn(client, session_id, [token])
                pass_frame = find_verify_pass(events2)
                if pass_frame is None:
                    print(f"[e2e] attempt {attempt}: no verify PASS after approval; dumping events...")
                    for ev in events2:
                        print("  ", ev.get("event"), json.dumps(ev.get("data"), default=str)[:320])
                    continue

                print(f"[e2e] PASS: verify_result={pass_frame}")
                updated = MODULE.read_text(encoding="utf-8")
                if 'return "hello ai-os"' in updated:
                    print("[e2e] File was updated as expected.")
                else:
                    print("[e2e] WARNING: file content did not match expected edit")
                    print(updated)
                return 0

            print("[e2e] FAIL: exhausted retries without witnessing YELLOW approval + verify PASS")
            return 1
    finally:
        clean()


if __name__ == "__main__":
    sys.exit(main())
