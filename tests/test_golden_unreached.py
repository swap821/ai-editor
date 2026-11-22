"""A turn no provider served must not be scored as a model failure.

Organ 34's circuit breaker opens after three consecutive provider failures and
then refuses that provider for sixty seconds. A cohort paced at a few seconds a
mission spends the rest of its run inside that window: every turn streams
cleanly, ends with no verification evidence, and is indistinguishable from a
model that wrote nothing -- so the cohort records ability it never measured.

Two cohorts on 2026-09-14 (nova-pro, mistral-large-3) each recorded a full 0/15
this way, their last two repeats 100% ``unverified`` at ~3s a mission. The
``cloud_route`` frame was then the only thing that separated "the model
failed" from "we never asked it".

2026-11-22: only the swarm sends ``cloud_route``, so every single-agent turn
that ended unverified was filed as unreached and retried: a failure was either
voided (the cohort declares itself INVALID) or retried into a pass. The
backend's ``done`` frame now says whether the model answered and which one
did, and that decides.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from tools import golden_mission_runner as gmr
from tests.source_rules import executable_source


class _Resp:
    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return None


class _Session:
    def post_stream(self, *_a: Any, **_k: Any) -> _Resp:
        return _Resp()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gmr, "_session", lambda: _Session())


def _stream(events: list[tuple[str, dict]]):
    def _parse(_resp: Any) -> Iterator[tuple[str, dict]]:
        yield from events

    return _parse


def test_cloud_route_frame_marks_the_turn_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gmr,
        "parse_sse",
        _stream([("cloud_route", {"provider": "bedrock", "model": "m"}), ("done", {})]),
    )
    result = gmr.run_prompt("p", "s", model_id="m")
    assert result["reached_provider"] is True


def test_a_clean_stream_with_no_cloud_route_is_unreached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The breaker's signature: a normal-looking turn that asked nobody."""
    monkeypatch.setattr(gmr, "parse_sse", _stream([("done", {})]))
    result = gmr.run_prompt("p", "s", model_id="m")
    assert result["reached_provider"] is False
    # And it earned no evidence, which is what makes it look like a failure.
    assert result["outcome"] == "unverified"


def test_unverified_with_evidence_is_still_a_real_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reaching the provider and failing is a MEASUREMENT -- never suppressed."""
    monkeypatch.setattr(
        gmr,
        "parse_sse",
        _stream(
            [
                ("cloud_route", {"provider": "bedrock", "model": "m"}),
                ("step", {"output": "[VERIFY FAIL] 0 passed, 1 failed"}),
                ("done", {}),
            ]
        ),
    )
    result = gmr.run_prompt("p", "s", model_id="m")
    assert result["reached_provider"] is True
    assert result["outcome"] == "verified_failure"


def test_a_turn_the_model_looped_in_was_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live cohort of 2026-11-22: Sonnet alternated read_file and
    read_directory until the loop guard stopped it. No `cloud_route` frame
    (only the swarm sends one), so the step was filed as unreached and the
    cohort voided. The guard fires only on calls the model returned."""
    monkeypatch.setattr(
        gmr,
        "parse_sse",
        _stream(
            [
                ("step", {"output": "read_file training_ground/t.py"}),
                ("error", {"code": "agent_loop", "text": "Agent loop detected"}),
            ]
        ),
    )
    result = gmr.run_prompt("p", "s", model_id="m")
    assert result["reached_provider"] is True
    assert result["outcome"] == "unverified"


def test_a_turn_with_no_model_output_stays_unreached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A turn the breaker skipped also ends with no output, so this code cannot
    tell the two apart and must not count as reached."""
    monkeypatch.setattr(
        gmr,
        "parse_sse",
        _stream([("error", {"code": "model_no_output", "text": "no output"})]),
    )
    result = gmr.run_prompt("p", "s", model_id="m")
    assert result["reached_provider"] is False


def _done(output: bool, served: str) -> tuple[str, dict]:
    return ("done", {"model_produced_output": output, "served_model_id": served})


def test_a_turn_the_model_answered_in_prose_is_scored_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live cohort of 2026-11-22: Sonnet created both files, then stopped
    without running the tests. Its failure, measured once."""
    monkeypatch.setattr(
        gmr,
        "parse_sse",
        _stream([("text_chunk", {"text": "I created both files."}), _done(True, "m")]),
    )
    result = gmr.run_prompt("p", "s", model_id="m")
    assert result["reached_provider"] is True
    assert result["outcome"] == "unverified"


@pytest.mark.parametrize(
    "done,model_id",
    [
        (_done(False, "m"), "m"),  # nothing produced: a skipped turn looks the same
        (_done(True, "other"), "m"),  # failover served a different model
        (("done", {}), "m"),  # a backend that does not say
    ],
)
def test_otherwise_the_turn_stays_unreached(monkeypatch, done, model_id) -> None:
    monkeypatch.setattr(gmr, "parse_sse", _stream([done]))
    assert gmr.run_prompt("p", "s", model_id=model_id)["reached_provider"] is False


def test_auto_counts_whichever_model_answered(monkeypatch) -> None:
    monkeypatch.setattr(gmr, "parse_sse", _stream([_done(True, "plan.x")]))
    assert gmr.run_prompt("p", "s", model_id="auto")["reached_provider"] is True


def test_retry_is_bounded_and_waits_out_the_breaker() -> None:
    """The cooldown must exceed organ 34's 60s recovery window, or the retry
    lands inside the same open circuit and measures nothing again."""
    from aios.application.models.health import ProviderHealthBudgetAuthority

    assert (
        gmr.UNREACHED_COOLDOWN_S > ProviderHealthBudgetAuthority.recovery_after_seconds
    )
    assert gmr.UNREACHED_RETRIES >= 1


def test_a_cohort_with_unreached_steps_is_reported_invalid() -> None:
    """The score must carry its own validity, not just a percentage."""
    src = executable_source(gmr.cmd_run)
    assert '"valid": not _UNREACHED_STEPS' in src
    assert "INVALID" in src
