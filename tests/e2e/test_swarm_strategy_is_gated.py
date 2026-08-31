"""The swarm/cloud-burst strategy is refused by design -- pinned by a test.

## Why this file replaces `tests/e2e/e2e_cloud_burst.py`

`GAGOS_REMAINING_INVENTORY.md` item 85 recorded that `tests/e2e/e2e_cloud_burst.py`
and `tests/e2e/e2e_yellow_verify.py` were "real, working end-to-end scripts" that
pytest silently skipped because their filenames miss the `test_*.py` pattern, and
proposed a rename so CI would run them.

Running the cloud-burst script before renaming anything showed the inventory
entry was optimistic on two counts, both of which the entry's own "risk if
skipped" clause predicted would happen:

1. **It no longer authenticates.** Standalone it dies on
   `403 Mutation requires a bearer token or a valid session, exact Origin, and
   session-bound CSRF proof`. The scripts were last touched 2026-06-25; the
   mutation guard landed after. `tests/conftest.py` seeds exactly that proof into
   every loopback `TestClient`, so running under pytest fixes this half for free.

2. **The path it demonstrates is gated off on purpose.** `generate_pipeline`
   now short-circuits *before* any provider is chosen::

       if req.swarm or req.role_pass:
           yield sse("error", {"code": "strategy_unavailable", ...})

   landed 2026-07-15 in c8e3da0e, three weeks after the script was last touched.
   A `cloud_route` frame can no longer be emitted, so renaming the script into
   the suite would have wired in a permanently red test.

So the demo is not resurrected. What is asserted instead is the contract that is
actually true today -- and a grep of `tests/` found **no** test anywhere covering
`strategy_unavailable`, so the fail-closed gate that retired the whole swarm path
had no regression guard at all. That gap is the real finding, and this file
closes it.

If the swarm strategy is ever routed through WorkerFoundry and re-enabled, this
test is the thing that must be rewritten first -- deliberately, not by accident.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from aios import config as config_mod
from aios.api.main import app, get_bedrock_client, get_ollama_client


class _FakeChat:
    """A provider that must never be consulted: the gate precedes the LLM."""

    def list_models(self) -> dict:
        return {"available": True, "models": ["qwen2.5-coder:7b"]}

    def chat(self, messages: list[dict[str, Any]], **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError(
            "the swarm gate let a request through to a provider; it is supposed "
            "to refuse before any model is contacted"
        )


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


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_ollama_client] = _FakeChat
    app.dependency_overrides[get_bedrock_client] = _FakeChat
    try:
        # The loopback address is what makes conftest seed the authenticated
        # Human Sovereign session + CSRF proof -- the exact thing the standalone
        # script was missing.
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _generate(client: TestClient, **extra: Any) -> list[dict[str, object]]:
    body = {
        "sessionId": f"gate-{uuid.uuid4().hex[:8]}",
        "modelId": "ollama.qwen2.5-coder:7b",
        "messages": [{"role": "user", "content": "report cloud and local status"}],
        "approvalTokens": [],
        **extra,
    }
    with client.stream("POST", "/api/generate", json=body) as resp:
        assert resp.status_code == 200, (
            f"the turn did not even reach the pipeline: HTTP {resp.status_code}"
        )
        return _parse_sse(resp)


@pytest.mark.parametrize("strategy", ["swarm", "role_pass"])
def test_an_experimental_strategy_is_refused_before_any_provider_is_chosen(
    client: TestClient, strategy: str
) -> None:
    """Both experimental strategies fail closed, and say why.

    Asserted through the real SSE stream rather than by reading the source, so a
    refactor that moves the gate keeps this honest as long as the behaviour holds.
    """
    events = _generate(client, **{strategy: True})

    errors = [e for e in events if e.get("event") == "error"]
    assert errors, (
        f"{strategy}=true produced no error frame; the experimental-strategy gate "
        f"is open. Frames seen: {[e.get('event') for e in events]}"
    )

    data = errors[0]["data"]
    assert isinstance(data, dict)
    assert data.get("code") == "strategy_unavailable", data
    assert strategy in str(data.get("text", "")), (
        "the refusal must name the strategy it refused, or an operator cannot "
        f"tell which switch to turn off: {data}"
    )

    assert any(e.get("event") == "done" for e in events), (
        "the stream must still terminate with `done` after refusing, or the UI "
        "hangs on a turn that already ended"
    )


def test_the_refusal_emits_no_cloud_route_frame(client: TestClient) -> None:
    """The specific thing `e2e_cloud_burst.py` existed to demonstrate.

    `cloud_route` is the frame that tells the UI a leg of the turn left the local
    machine. While the strategy is gated off, no such frame may appear -- a
    silent regression here would mean work is being shipped to a cloud provider
    on a path nobody believes is reachable.
    """
    events = _generate(client, swarm=True)

    assert not [e for e in events if e.get("event") == "cloud_route"], (
        "a cloud_route frame was emitted by a strategy that is supposed to be "
        "refused -- local work reached a cloud provider through a gated path"
    )


def test_cloud_burst_stays_off_by_default(client: TestClient) -> None:
    """The gate above is not the only thing holding this closed.

    `SWARM_CLOUD_BURST_ENABLED` is what decides whether a cloud client is built
    for a swarm turn at all. It defaults to False, so even if the strategy gate
    were lifted the burst path would still need a deliberate opt-in. Pinned
    because a default flip is a one-character change with a cloud-egress blast
    radius.
    """
    assert config_mod.SWARM_CLOUD_BURST_ENABLED is False, (
        "AIOS_SWARM_CLOUD_BURST now defaults to on; cloud burst must remain an "
        "explicit opt-in"
    )
