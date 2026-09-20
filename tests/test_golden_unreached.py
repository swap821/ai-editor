"""A turn no provider served must not be scored as a model failure.

Organ 34's circuit breaker opens after three consecutive provider failures and
then refuses that provider for sixty seconds. A cohort paced at a few seconds a
mission spends the rest of its run inside that window: every turn streams
cleanly, ends with no verification evidence, and is indistinguishable from a
model that wrote nothing -- so the cohort records ability it never measured.

Two cohorts on 2026-09-14 (nova-pro, mistral-large-3) each recorded a full 0/15
this way, their last two repeats 100% ``unverified`` at ~3s a mission. The
``cloud_route`` frame is the only thing that separates "the model failed" from
"we never asked it".
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
