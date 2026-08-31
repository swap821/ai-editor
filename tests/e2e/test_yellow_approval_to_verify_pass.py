"""A real model edits a file, a human approves it, and verification passes.

## What this is and why it is opt-in

This is `tests/e2e/e2e_yellow_verify.py` converted into a collectible test.
`GAGOS_REMAINING_INVENTORY.md` item 85 recorded that the script never ran
automatically because its filename misses pytest's `test_*.py` pattern, and
proposed a rename. Renaming alone would have collected nothing -- the file
contained a `main() -> int` and no test function -- and it would still have
failed, because standalone it never reaches the API::

    403 Mutation requires a bearer token or a valid session, exact Origin,
        and session-bound CSRF proof

`tests/conftest.py` seeds exactly that proof into every loopback `TestClient`,
so running under pytest is what actually repairs it.

Unlike its sibling (see `test_swarm_strategy_is_gated.py`, where the demonstrated
path turned out to be gated off on purpose), the flow here is still live, so the
scenario is preserved rather than replaced.

It stays **opt-in** because it needs two things CI does not have: Ollama serving
`qwen2.5-coder:7b`, and a running container runtime for the verify step. It also
takes tens of seconds and asserts on the behaviour of a 7B model, which is a
legitimate flake source. A default-CI test that depends on external daemons is a
test that turns the gate red for reasons unrelated to the change under review.
Run it with::

    AIOS_E2E_LIVE=1 python -m pytest tests/e2e/test_yellow_approval_to_verify_pass.py

Without the flag, or without either daemon, it SKIPS with the specific reason
rather than passing vacuously, so a skipped run is visible in the summary instead
of being mistaken for coverage.

## What it proves

The whole YELLOW protocol end to end, with a real model in the loop:

  1. A real LLM decides to call `edit_file` on a file inside the scope root.
  2. The boundary refuses it and emits `human_required` with an approval token --
     the model does NOT get to edit unilaterally.
  3. The turn is replayed carrying that token.
  4. The forced auto-verify runs the sibling pytest and emits `verdict: pass`.
  5. The file on disk actually changed.

Nothing here is stubbed: no fake LLM, no fake executor, no fake verifier.

## Honest status of this file as committed

Steps 1-3 were observed passing on a real `qwen2.5-coder:7b`, including the
assertion that matters most: at the moment `human_required` is emitted the file
is byte-identical on disk, so the pause is real and not decorative.

Steps 4-5 were NOT observed on the machine this was written on, because it has no
Docker daemon, so verification fails closed exactly as designed (see
`_isolated_execution_available` for the captured output). The container
precondition was added for that reason rather than weakening the assertion. On a
host with both daemons up this should run green end to end -- but that run has
not happened yet, and this note stays until it does.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

MODEL = "qwen2.5-coder:7b"
ROOT = Path(__file__).resolve().parents[2]

#: The model is asked to make this exact edit; verification asserts the result.
BEFORE = 'def hello():\n    return "hello"\n'
AFTER_FRAGMENT = 'return "hello ai-os"'


def _isolated_execution_available() -> bool:
    """True only when the container backend the verify step needs is up.

    Measured, not assumed. Without a Docker daemon the flow CANNOT reach a
    verify PASS -- and that is correct behaviour, not a regression. The run that
    established this reported::

        [VERIFY FAIL] 0 passed, 0 failed (exit 1) (strength=NONE)
        failed to connect to the docker API at npipe:////./pipe/docker_engine

    which is the fail-closed path the startup banner promises: "approved
    arbitrary execution and self-apply will FAIL CLOSED until the container is
    available". Every earlier step -- the pause, the token, the approved edit --
    still ran correctly. So this is a missing PRECONDITION for the test, and
    skipping is the honest response; asserting a PASS here would be asserting
    that the isolation boundary had been bypassed.

    The product's own `DockerRunner.ensure_available` is the check, rather than a
    second `docker version` of our own: two derivations of "is isolation up?"
    that can disagree is precisely the shape this repo has been bitten by.
    """
    try:
        from aios.core.executor import DockerRunner

        DockerRunner().ensure_available()
    except Exception:
        return False
    return True


def _live_model_available() -> bool:
    """True only when Ollama is reachable AND actually serves the model.

    Checked rather than assumed: a reachable daemon without the model produces a
    failure that looks like a product bug and is not one.
    """
    try:
        import httpx

        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        response.raise_for_status()
        names = {m.get("name") for m in response.json().get("models", [])}
    except Exception:
        return False
    return MODEL in names


pytestmark = [
    pytest.mark.e2e_live,
    pytest.mark.skipif(
        os.environ.get("AIOS_E2E_LIVE", "").strip().lower() not in {"1", "true", "yes"},
        reason="live end-to-end test; set AIOS_E2E_LIVE=1 to run it",
    ),
    pytest.mark.skipif(
        not _live_model_available(),
        reason=f"needs Ollama serving {MODEL} on localhost:11434",
    ),
    pytest.mark.skipif(
        not _isolated_execution_available(),
        reason="needs a running container runtime; verification fails closed without one",
    ),
]


@pytest.fixture()
def scope(tmp_path: Path) -> Iterator[Path]:
    """A real sandbox scope, with the global scope state restored afterwards.

    `set_scope_roots` and `config.SCOPE_ROOTS` are PROCESS-WIDE. The original
    script could set them and walk away because it owned its own process; a test
    that did the same would silently redirect every later test's containment
    checks at a temp directory. Saved and restored here for that reason.

    The scope root is deliberately not the project root, so the rollback engine
    sees a genuine sandbox.
    """
    from aios import config as config_mod
    from aios.security import scope_lock

    previous_roots = scope_lock.get_scope_roots()
    previous_config = list(getattr(config_mod, "SCOPE_ROOTS", []))

    work = tmp_path / "demo_scope"
    work.mkdir(parents=True, exist_ok=True)
    (work / "demo_module.py").write_text(BEFORE, encoding="utf-8")
    (work / "test_demo_module.py").write_text(
        "from demo_module import hello\n\n"
        "def test_hello():\n"
        "    assert hello() == 'hello ai-os'\n",
        encoding="utf-8",
    )

    config_mod.SCOPE_ROOTS = [work]
    scope_lock.set_scope_roots([work])
    try:
        yield work
    finally:
        scope_lock.set_scope_roots(previous_roots)
        config_mod.SCOPE_ROOTS = previous_config
        shutil.rmtree(work, ignore_errors=True)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A loopback client, which is what makes conftest seed the sovereign session."""
    import aios.api.main as main_mod
    from aios.api.main import app

    # Recall would let a stale trail, rather than the directive, drive the model.
    saved = (
        main_mod._recall_memory,
        main_mod._recall_lessons,
        main_mod._recall_skills,
    )
    main_mod._recall_memory = lambda *_a, **_k: None
    main_mod._recall_lessons = lambda *_a, **_k: []
    main_mod._recall_skills = lambda *_a, **_k: []
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            yield test_client
    finally:
        (
            main_mod._recall_memory,
            main_mod._recall_lessons,
            main_mod._recall_skills,
        ) = saved


def _parse_sse(response) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    current: dict[str, object] = {}
    for raw in response.iter_lines():
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current.setdefault("data", []).append(line[len("data: ") :])  # type: ignore[union-attr]
        elif line == "":
            if "event" in current:
                payload = json.loads("".join(current.get("data", [])))  # type: ignore[arg-type]
                events.append({"event": current["event"], "data": payload})
            current = {}
    return events


def _turn(
    client: TestClient, session_id: str, module: Path, tokens: list[str]
) -> list[dict[str, object]]:
    relative = module.resolve().as_posix()
    directive = (
        f"The file {relative} contains:\n\n"
        f"{BEFORE}\n"
        'Use the edit_file tool to replace the line `return "hello"` '
        'with `return "hello ai-os"` exactly. Do not explain; just call the tool.'
    )
    body: dict[str, Any] = {
        "sessionId": session_id,
        "modelId": f"ollama.{MODEL}",
        "messages": [{"role": "user", "content": directive}],
        "approvalTokens": tokens,
    }
    with client.stream("POST", "/api/generate", json=body) as resp:
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        return _parse_sse(resp)


def _human_required(events: list[dict[str, object]]) -> tuple[str, dict] | None:
    for ev in events:
        if ev.get("event") == "human_required":
            data = ev["data"]
            assert isinstance(data, dict)
            token = str((data.get("input") or {}).get("approvalToken") or "")
            return token, data
    return None


def _verify_pass(events: list[dict[str, object]]) -> dict | None:
    for ev in events:
        data = ev.get("data")
        if ev.get("event") == "verify_result" and isinstance(data, dict):
            if data.get("verdict") == "pass":
                return data
    return None


def test_a_real_edit_pauses_for_a_human_and_verifies_after_approval(
    client: TestClient, scope: Path
) -> None:
    """The full YELLOW loop against a live model.

    Retried up to three times: the pause and the verification are deterministic
    product behaviour, but whether a 7B model emits a well-formed `edit_file`
    call on the first attempt is not. The retry covers only step 1 -- once the
    model calls the tool, every assertion below is on the system, not the model.
    """
    module = scope / "demo_module.py"
    last_events: list[dict[str, object]] = []

    for attempt in range(1, 4):
        # Re-seed per attempt. A failed attempt can get as far as applying the
        # edit and fall short only at the verify step, so attempt 2 would
        # otherwise start from an already-edited file and the pre-approval
        # assertion below would fire against its own predecessor's work.
        module.write_text(BEFORE, encoding="utf-8")
        session_id = f"e2e-{uuid.uuid4().hex[:8]}"
        first = _turn(client, session_id, module, [])
        pause = _human_required(first)
        if pause is None:
            last_events = first
            continue

        token, pause_data = pause
        assert token, f"human_required carried no approval token: {pause_data}"

        # The pause must be REAL: nothing may have been written yet.
        # Verified directly while building this test -- a turn that ends in
        # `human_required` leaves the file byte-identical on disk.
        assert module.read_text(encoding="utf-8") == BEFORE, (
            "the file changed before a human approved the edit -- the YELLOW "
            "pause is decorative"
        )

        second = _turn(client, session_id, module, [token])
        verdict = _verify_pass(second)
        if verdict is None:
            last_events = second
            continue

        assert AFTER_FRAGMENT in module.read_text(encoding="utf-8"), (
            "verification reported PASS but the file on disk does not contain "
            "the edit -- the verdict is not describing the real filesystem"
        )
        return

    verdicts = [
        e.get("data")
        for e in last_events
        if e.get("event") in {"verify_result", "error"}
    ]
    pytest.fail(
        f"exhausted {attempt} attempts without a YELLOW pause followed by a "
        f"verify PASS.\n  frames:   {[e.get('event') for e in last_events]}"
        f"\n  verdicts: {json.dumps(verdicts, default=str)[:1500]}"
    )
