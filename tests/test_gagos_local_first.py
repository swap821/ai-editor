"""The local writer goes first on a goal a mission skill guides (2026-11-15).

The operator's "best of both": an activated mission skill guides the frontier
writers, and the README's step 16 -- "the local clerk may reuse the skill under
matching conditions" -- is its other half. Pinned here: the local writer gets
the same job, guidance included; its change is kept only if the static checks
and the sandbox pass it (verified once, not twice); otherwise its proposals are
refused saying so and the goal escalates to the frontier writer (step 17); and
it is not tried without a skill, with local-first off, or on files too big for
the operator's laptop.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from aios.maintenance import sandbox_tests as sb
from tests import test_gagos_mission_hour as hour_tests
from tests.test_gagos_council_origination import TEST, WORDS
from tools import gagos_daily as tool

led, workshop = hour_tests.led, hour_tests.workshop

LOCAL = "the local writer's change\n"
FRONTIER = "the frontier writer's change\n"
GUIDANCE = {"skill_id": "gagos-1", "version": 1, "line": "GAGOS learned: do it so."}


def _contract(guided=True):
    return SimpleNamespace(
        mission_id="mission-0123456789ab",
        metadata={"skill_guidance": [GUIDANCE]} if guided else {},
    )


def _work(led, root, *, local=None, frontier=None):
    tid = led.add_task(TEST, WORDS, said_by="operator")
    asked = {"local": [], "frontier": []}

    def ask_local(prompt, system, rid):
        asked["local"].append(prompt)
        if isinstance(local, Exception):
            raise local
        return LOCAL if local is None else local

    def ask_frontier(prompt, system, rid):
        asked["frontier"].append(prompt)
        return FRONTIER if frontier is None else frontier

    work = tool.MissionWork(
        led,
        root,
        "head",
        led.task(tid),
        region="r",
        complete=ask_frontier,
        local_complete=ask_local,
        reviewer=lambda prompt: ("accept", "it does what he asked", "claude-opus"),
    )
    return work, asked


@pytest.fixture()
def guided(monkeypatch):
    """Local-first on, and the writers' guidance read from the contract."""
    monkeypatch.setenv("AIOS_GAGOS_LOCAL_WRITER", "qwen3.5:9b")
    monkeypatch.setattr(tool, "load_direction", lambda path: SimpleNamespace(notes=()))


def test_the_local_writer_goes_first_and_its_passing_change_is_kept(
    led, workshop, guided, tmp_path, capsys
):
    tested, _built = workshop
    work, asked = _work(led, tmp_path)
    edits = work.write(_contract())
    assert edits == {TEST: LOCAL}
    assert len(asked["local"]) == 1 and asked["frontier"] == []
    (p,) = led.proposals()
    assert p["model"] == "qwen3.5:9b" and p["status"] == "proposed"
    assert work.wrote_with == "qwen3.5:9b"
    # The council verifies the same change again: the sandbox ran once.
    assert work.verify(edits).outcome == sb.PASSED
    assert len(tested) == 1
    assert "local first: qwen3.5:9b wrote it, guided; the sandbox passes" in (
        capsys.readouterr().out
    )


def test_a_local_change_the_sandbox_fails_escalates_to_the_frontier(
    led, workshop, guided, tmp_path, monkeypatch, capsys
):
    def run_change_tests(trees, *, base_commit, changes):
        if LOCAL in changes.values():
            return sb.SandboxVerdict(
                sb.BROKE, "1 test fails", tests=(TEST,), broken=(TEST,)
            )
        return sb.SandboxVerdict(sb.PASSED, "2 tests pass", tests=(TEST,))

    monkeypatch.setattr(tool, "run_change_tests", run_change_tests)
    work, asked = _work(led, tmp_path)
    edits = work.write(_contract())
    assert edits == {TEST: FRONTIER}
    assert len(asked["local"]) == 1 and len(asked["frontier"]) == 1
    local, frontier = sorted(led.proposals(), key=lambda p: p["created_at"])
    assert local["model"] == "qwen3.5:9b" and local["status"] == "refused"
    # The sandbox's own refusal is kept, and the escalation added.
    assert local["refusal"].startswith(sb.BROKE_PREFIX)
    assert local["refusal"].endswith(f"the goal escalated to {work.model}")
    assert frontier["status"] == "proposed"
    assert work.wrote_with == work.model
    # Only the frontier's change is the mission's now.
    assert [r["proposal_id"] for r in work._rows()] == [frontier["proposal_id"]]
    assert "escalated to" in capsys.readouterr().out


def test_a_local_writer_that_fails_escalates_to_the_frontier(
    led, workshop, guided, tmp_path
):
    work, asked = _work(led, tmp_path, local=RuntimeError("Ollama is not running"))
    assert work.write(_contract()) == {TEST: FRONTIER}
    assert len(asked["frontier"]) == 1
    assert work.wrote_with == work.model


def test_no_skill_no_local_attempt(led, workshop, guided, tmp_path):
    work, asked = _work(led, tmp_path)
    assert work.write(_contract(guided=False)) == {TEST: FRONTIER}
    assert asked["local"] == []


def test_local_first_off_is_off(led, workshop, guided, tmp_path, monkeypatch):
    monkeypatch.setenv("AIOS_GAGOS_LOCAL_WRITER", "")
    work, asked = _work(led, tmp_path)
    assert work.write(_contract()) == {TEST: FRONTIER}
    assert asked["local"] == []


def test_files_too_big_for_the_laptop_go_to_the_frontier(
    led, workshop, guided, tmp_path, capsys
):
    target = tmp_path / TEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x" * (tool.LOCAL_FIRST_MAX_CHARS + 1), encoding="utf-8")
    work, asked = _work(led, tmp_path)
    assert work.write(_contract()) == {TEST: FRONTIER}
    assert asked["local"] == []
    assert "local first: not tried -- the goal's files hold" in (
        capsys.readouterr().out
    )


def test_the_trajectory_names_the_writer_whose_change_it_carries(
    led, workshop, guided, tmp_path
):
    work, _asked = _work(led, tmp_path)
    work.write(_contract())
    captured = {}

    def capture(mission_id, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(trajectory_id="trajectory-1")

    tool.mission_trajectory(
        work, {"mission_id": "mission-1", "envelope_id": None}, "head", capture=capture
    )
    assert captured["expert_model"] == "qwen3.5:9b"
    assert captured["expert_provider"] == "ollama"


def test_the_local_writer_runs_on_the_laptop_through_the_gateway(monkeypatch):
    """Its client holds a whole file and its answer, has time to write it,
    and does not think silently first; its target is local."""
    made = {}

    class Ollama:
        def __init__(self, **kwargs):
            made.update(kwargs)

        def chat(self, messages, tools=None, model=None):
            return {"content": "the answer"}

    targets = []

    class Gateway:
        def __init__(self, provider, **kwargs):
            targets.append(kwargs["target"])
            self.provider = provider

        def complete(self, prompt, *, system=None):
            return self.provider.complete(prompt, system=system)

    import aios.application.intelligence.gateway as gateway
    import aios.core.llm as llm

    monkeypatch.setattr(llm, "OllamaClient", Ollama)
    monkeypatch.setattr(gateway, "GovernedAdvisoryCompletionClient", Gateway)
    monkeypatch.setattr(
        "aios.api.deps.get_constitution_authority",
        lambda: SimpleNamespace(
            get_active_snapshot=lambda: SimpleNamespace(
                ratified_by_operator_id="op-1", snapshot_digest="c" * 64
            )
        ),
    )
    complete = tool.local_completer("qwen3.5:9b")
    assert complete("p", "s", "rid") == "the answer"
    assert targets == ["local"]
    assert made["num_ctx"] >= 16_384 and made["think"] is False
    assert made["timeout_s"] == tool.LOCAL_WRITER_TIMEOUT_S
