"""`proof_level` must describe what a probe actually reached.

Every one of the 16 runtime proofs reported `proof_level="fixture"` -- even
the executor probe, which really does make an HTTP call to a live executor
service that spawns a real container. The parameter existed on `_proof()` and
no caller ever passed anything to it, so the field was decorative: it said
"fixture" unconditionally, whatever had happened.

A field that always says the same thing carries no information. The fix is
narrow on purpose. Exactly two proofs leave the process, so exactly two may
claim `live`; the other fourteen exercise real production classes against
real SQLite, which is genuine but in-process. Promoting those as well would
have moved the count from 0/16 to 16/16 on day one and destroyed the
distinction being introduced.

The subtler half is the failure path: off CI there is no executor service, so
the probe raises. A failed probe stamped `live` would assert it touched real
infrastructure while doing the exact opposite -- and that is the common case
on a developer machine, not a rare one.
"""

from __future__ import annotations

import pytest

from aios.application.governance.runtime_proof import (
    REQUIRED_PROOFS,
    RuntimeProof,
    _proof,
)


def test_a_passing_live_probe_is_stamped_live() -> None:
    result = _proof(
        "isolated_executor", lambda: "reached the container", proof_level="live"
    )

    assert result.passed is True
    assert result.proof_level == "live"


def test_a_failing_live_probe_never_claims_live() -> None:
    """The case that matters. Off CI the executor service does not exist, the
    probe raises, and nothing live was touched -- so nothing live may be
    claimed."""

    def boom():
        raise RuntimeError("private executor service is unavailable")

    result = _proof("isolated_executor", boom, proof_level="live")

    assert result.passed is False
    assert result.proof_level != "live"
    assert result.proof_level == "unavailable"


def test_a_failing_fixture_probe_stays_fixture() -> None:
    """Degrading only applies to live claims: a fixture probe that fails was
    still only ever a fixture, and relabelling it would lose information."""

    def boom():
        raise RuntimeError("nope")

    result = _proof("turn_coordinator", boom, proof_level="fixture")

    assert result.passed is False
    assert result.proof_level == "fixture"


def test_the_default_level_is_still_fixture() -> None:
    """Callers must opt IN to a live claim. If the default ever became live,
    every in-process probe would silently start overclaiming."""
    assert _proof("anything", lambda: "ok").proof_level == "fixture"


def test_unavailable_is_distinguishable_from_both_live_and_fixture() -> None:
    """Three genuinely different outcomes -- proved live, proved in-process,
    could not tell -- must not collapse into two."""
    levels = {
        _proof("a", lambda: "ok", proof_level="live").proof_level,
        _proof("b", lambda: "ok").proof_level,
        _proof("c", _raise, proof_level="live").proof_level,
    }
    assert levels == {"live", "fixture", "unavailable"}


def _raise():
    raise RuntimeError("unavailable")


def test_a_derived_proof_cannot_outrank_its_source() -> None:
    """`executor_runtime_available` is derived wholly from `isolated_executor`.
    Hardcoding its level would let it claim a live run on a commit where the
    probe it mirrors never reached anything."""
    source = _proof("isolated_executor", _raise, proof_level="live")
    derived = RuntimeProof(
        name="executor_runtime_available",
        passed=source.passed,
        evidence=source.evidence,
        proof_level=source.proof_level,
    )

    assert derived.proof_level == source.proof_level == "unavailable"


@pytest.mark.parametrize("name", ["isolated_executor", "executor_runtime_available"])
def test_the_two_live_capable_proofs_are_still_required(name: str) -> None:
    """If either dropped out of REQUIRED_PROOFS, `v1-check --strict` would stop
    gating on the only proofs that leave the process."""
    assert name in REQUIRED_PROOFS
