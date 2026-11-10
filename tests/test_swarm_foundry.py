"""The ant colony runs through the Worker Foundry (2026-11-09).

The operator, 2026-11-04: "can be multiple workers working that's y o made
queens and ant-colony inspired workers are we honestly using those". They were
not: production refused every swarm turn until its castes entered the one
boundary every acting worker crosses. Pinned here, with fake agents:

* every caste leg is a worker the Foundry admits, and its lifecycle reaches
  the bus (requested, admitted, started, completed, dissolved);
* an engaged emergency stop refuses the next leg, and the swarm ends saying so;
* worker legs run side by side when concurrency allows;
* a leg paused for the operator's approval is recorded as awaiting it.
"""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any

import pytest
from types import SimpleNamespace

from aios.agents import swarm
from aios.application.workers.swarm_foundry import SwarmFoundry


class _Stop:
    def __init__(self) -> None:
        self.engaged = False

    def assert_operational(self) -> None:
        if self.engaged:
            raise RuntimeError("emergency stop engaged")


class _Bus:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self._lock = threading.Lock()

    def append(self, event: Any) -> None:
        with self._lock:
            self.events.append(event)


class _Agent:
    def __init__(self, answer: str, on_run=None, pause: bool = False) -> None:
        self.answer, self.on_run, self.pause = answer, on_run, pause

    def run(self, messages):
        if self.on_run is not None:
            self.on_run()
        if self.pause:
            yield {"type": "human_required", "command": "rm -rf build", "reason": "x"}
            return
        if self.answer == "worker did its part":
            # What a worker that wrote reports: the synthesizer runs after it.
            yield {
                "type": "tool_result",
                "tool": "create_file",
                "output": "ok",
                "id": "w",
            }
        yield {"type": "text", "text": self.answer}
        yield {"type": "done"}


def _factory(on_worker=None, pause_worker: bool = False):
    def make_agent(**overrides):
        prompt = overrides.get("system_prompt", "")
        if prompt == swarm.DECOMPOSER_PROMPT:
            return _Agent("1. read the code\n2. write the test\n3. run the test")
        if prompt == swarm.WORKER_PROMPT:
            return _Agent("worker did its part", on_run=on_worker, pause=pause_worker)
        return _Agent("synthesized")

    return make_agent


@pytest.fixture()
def colony():
    stop, bus = _Stop(), _Bus()
    foundry = SwarmFoundry(emergency_stop=stop, bus=bus, max_workers=4)
    yield foundry, stop, bus
    foundry.close()


def _run(foundry: SwarmFoundry, make_agent, **kw) -> list[dict]:
    mission = foundry.mission()
    return list(
        swarm.run_swarm(
            make_agent,
            [{"role": "user", "content": "add a test"}],
            enable_scout=False,
            admit=lambda role, tools, run: foundry.admit(
                mission, role, run, allowed_tools=tuple(tools)
            ),
            **kw,
        )
    )


def _states(bus: _Bus) -> dict[str, list[str]]:
    by_worker: dict[str, list[str]] = {}
    for event in bus.events:
        by_worker.setdefault(event.payload["worker_id"], []).append(
            event.payload["state"]
        )
    return by_worker


def test_every_caste_leg_is_a_worker_the_foundry_admits(colony) -> None:
    foundry, _stop, bus = colony
    events = _run(foundry, _factory())
    assert events[-1] == {"type": "done"}
    assert any(e.get("type") == "swarm_plan" for e in events)
    states = _states(bus)
    # The decomposer, three workers and the synthesizer: five admitted workers.
    assert len(states) == 5, states
    for lifecycle in states.values():
        # BORN is internal; the bus carries the public lifecycle.
        assert lifecycle == [
            "requested",
            "admitted",
            "running",
            "completed",
            "dissolved",
        ]
    assert {e.payload["strategy"] for e in bus.events} == {"swarm"}
    assert len({e.payload["mission_id"] for e in bus.events}) == 1, (
        "one mission per turn"
    )


def test_an_engaged_stop_refuses_the_next_leg_and_the_swarm_says_so(colony) -> None:
    foundry, stop, bus = colony

    def stop_now() -> None:
        stop.engaged = True

    events = _run(foundry, _factory(on_worker=stop_now))
    refused = [e for e in events if e.get("code") == "worker_refused"]
    assert refused and "emergency stop" in refused[0]["text"]
    assert events[-1] != {"type": "done"}, "a refused leg ends the swarm"
    assert not any(e.get("caste") == "synthesizer" for e in events)


def test_worker_legs_run_side_by_side_when_concurrency_allows(colony) -> None:
    foundry, _stop, _bus = colony
    meeting = threading.Barrier(3, timeout=10)
    events = _run(foundry, _factory(on_worker=meeting.wait), worker_concurrency=3)
    assert events[-1] == {"type": "done"}, "three workers met at once"


def test_a_leg_paused_for_approval_is_recorded_as_awaiting_it(colony) -> None:
    foundry, _stop, bus = colony
    events = _run(foundry, _factory(pause_worker=True))
    assert any(e.get("type") == "human_required" for e in events)
    assert (
        Counter(s for states in _states(bus).values() for s in states)[
            "awaiting_capability"
        ]
        == 1
    )


def test_an_acting_agent_is_built_only_by_the_turns_two_factories() -> None:
    """Every tool agent in production comes from the generate pipeline's two
    factories (make_agent, make_cloud_agent). Each runs either as the operator's
    main turn, a path kept apart from the Foundry by his decision of 2026-11-09,
    or as a swarm leg the Foundry admits. A tool agent built anywhere else
    would be an acting worker on neither path."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    built: dict[str, int] = {}
    for path in (root / "aios").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(
                    node.func, "attr", None
                )
                if name == "ToolAgent":
                    rel = path.relative_to(root).as_posix()
                    built[rel] = built.get(rel, 0) + 1
    assert built == {"aios/application/turns/generate_pipeline.py": 2}, built


# --- What the two adversarial reviews of 2026-11-09 found, pinned ------------


def test_a_legs_own_failure_is_raised_not_reported_as_a_refusal(colony) -> None:
    foundry, _stop, _bus = colony

    def boom() -> None:
        raise ValueError("the agent broke")

    with pytest.raises(ValueError, match="the agent broke"):
        _run(foundry, _factory(on_worker=boom))


def test_a_refusal_reaches_the_stream_redacted(colony) -> None:
    foundry, stop, _bus = colony
    secret = "AKIA" + "Q3EXAMPLEQ7KEY4"

    class _Leaky(_Stop):
        def assert_operational(self) -> None:
            if self.engaged:
                raise RuntimeError(f"stopped while holding {secret}")

    leaky = _Leaky()
    leaky_foundry = SwarmFoundry(emergency_stop=leaky, max_workers=4)
    try:

        def stop_now() -> None:
            leaky.engaged = True

        events = _run(leaky_foundry, _factory(on_worker=stop_now))
    finally:
        leaky_foundry.close()
    refused = [e for e in events if e.get("code") == "worker_refused"]
    assert refused and secret not in refused[0]["text"]


def test_a_hung_leg_fails_on_its_timeout_and_frees_its_slot() -> None:
    import time

    foundry = SwarmFoundry(emergency_stop=_Stop(), max_workers=1)
    try:
        hung = foundry.mission()
        started = time.monotonic()
        with pytest.raises(Exception, match="ran past 1s"):
            foundry.admit(hung, "worker-1", lambda: time.sleep(4), timeout_seconds=1)
        assert time.monotonic() - started < 3, "it did not wait for the hung leg"
        other = foundry.mission()
        assert (
            foundry.admit(other, "worker-1", lambda: "ran", timeout_seconds=5) == "ran"
        )
    finally:
        foundry.close()


def test_every_leg_that_paused_beside_another_is_named(colony) -> None:
    foundry, _stop, _bus = colony
    events = _run(foundry, _factory(pause_worker=True), worker_concurrency=3)
    asks = [i for i, e in enumerate(events) if e.get("type") == "human_required"]
    notices = [
        i
        for i, e in enumerate(events)
        if "Also waiting for your approval" in str(e.get("text", ""))
    ]
    assert asks and notices and notices[0] < asks[0], (
        "the notice comes before the pause"
    )
    notice = events[notices[0]]["text"]
    assert "worker-2" in notice and "worker-3" in notice


def test_cloud_burst_obeys_the_one_egress_law(monkeypatch) -> None:
    """Burst needs the runtime profile's word AND the law: with no task allowed
    to leave the machine, no leg goes to the cloud whatever the profile says;
    with a profile that allows no burst, none goes whatever the law allows
    (2026-11-10: the profile replaced AIOS_SWARM_CLOUD_BURST)."""
    from aios.agents import swarm as swarm_module
    from aios.application.turns import generate_pipeline
    from aios.core import router, router_wiring

    seen: dict = {}
    allows = [True]
    monkeypatch.setattr(
        generate_pipeline, "profile_allows_cloud_burst", lambda: allows[0]
    )
    monkeypatch.setattr(
        swarm_module, "run_swarm", lambda *a, **kw: seen.update(kw) or iter(())
    )
    from aios.api import deps

    stub = SimpleNamespace(mission=lambda: "m", admit=lambda *a, **k: None)
    monkeypatch.setattr(deps, "get_swarm_foundry", lambda: stub)
    for law, expected in (
        (router.Policy(cloud_tasks=frozenset()), False),
        (router.Policy(cloud_tasks=frozenset({"coding"})), True),
    ):
        monkeypatch.setattr(router_wiring, "_router_policy", lambda law=law: law)
        list(
            generate_pipeline._swarm_events(
                lambda **o: None,
                [],
                cloud_factory=lambda **o: None,
                cloud_provider="gemini",
                target="local",
                swarm_patterns=None,
                task="coding",
            )
        )
        assert seen["cloud_burst"] is expected, law
    allows[0] = False
    list(
        generate_pipeline._swarm_events(
            lambda **o: None,
            [],
            cloud_factory=lambda **o: None,
            cloud_provider="gemini",
            target="local",
            swarm_patterns=None,
            task="coding",
        )
    )
    assert seen["cloud_burst"] is False, "a profile that allows no burst"
