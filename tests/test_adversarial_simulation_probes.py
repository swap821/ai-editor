"""Organ 46: the live probes must actually decide the verdict.

`tests/test_adversarial_simulations.py` proves the nine checks reject
dangerous *proposal text*. That is only half of what the organ claims. Eight
of the nine also run a live probe against the production mechanism the check
protects -- capability issue/consume, the emergency-stop latch and its hooks,
the privacy broker, amendment rollback, correction-record authority, and
provider diversity -- and it is that probe, not the text screen, that is meant
to catch a real regression in the mechanism itself.

Every existing test drives the text-marker branch. Nothing broke a probe, so
each `if not probe[...]: return _failed(...)` arm was unexecuted by the suite:
if `CapabilityAuthority` started accepting unknown tokens, or the
emergency-stop stopped firing its hooks, these checks would have gone right on
reporting `passed=True` and the whole suite would have stayed green.

Each test here forces exactly one probe to report failure and asserts the
owning check flips to failed for that reason, while a check that does not
depend on that probe stays passing -- so a test cannot pass by breaking
everything at once.

The probes are patched rather than the real mechanisms sabotaged: these run
in-process against live production classes, and genuinely breaking a global
emergency stop or capability authority mid-suite would leak into other tests.
What is under test here is the wiring -- does a failing probe actually change
the verdict -- not the probes' own internals, which their owning organs test.
"""

from __future__ import annotations

import pytest

from aios.application.governance import adversarial_simulations as sims
from aios.application.governance.adversarial_simulations import (
    run_adversarial_simulations,
)
from aios.application.governance.amendment_authority import propose_amendment


def _proposal(**overrides: object):
    """A deliberately benign proposal: it must trip no textual marker, or the
    text screen would short-circuit and the probe would never run."""
    fields: dict[str, object] = dict(
        proposal_id="probe-proposal",
        target_articles=("article-9-reauth-policy",),
        proposed_diff="cache reauth for a short trusted window",
        motivation="reduce operator friction on routine approvals",
        migration_plan="roll out behind a flag",
        rollback_plan="flip the flag back",
        proposed_by="tester",
        proposer_type="human",
    )
    fields.update(overrides)
    return propose_amendment(**fields)


def _verdicts() -> dict[str, bool]:
    return {r.check_name: r.passed for r in run_adversarial_simulations(_proposal())}


def _notes(check_name: str) -> str:
    for result in run_adversarial_simulations(_proposal()):
        if result.check_name == check_name:
            return result.notes
    raise AssertionError(f"{check_name} was not run at all")


def test_the_baseline_proposal_trips_no_textual_marker() -> None:
    """Guards every other test in this module: if this proposal ever started
    hitting a marker, the probe arms below would stop being reached and these
    tests would pass for entirely the wrong reason."""
    assert all(_verdicts().values())


# --------------------------------------------------------------------------- #
# CapabilityAuthority probe -- two checks read two different keys
# --------------------------------------------------------------------------- #


def test_approval_bypass_fails_when_an_unknown_token_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sims,
        "_probe_capability_lifecycle",
        lambda: {"unknown_token_rejected": False, "replay_rejected": True},
    )
    verdicts = _verdicts()

    assert verdicts["approval_bypass"] is False
    assert "unknown" in _notes("approval_bypass").lower()
    # The sibling check reads the other key off the same probe and must be
    # unaffected -- otherwise one broken key would condemn both.
    assert verdicts["capability_replay"] is True


def test_capability_replay_fails_when_a_consumed_capability_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sims,
        "_probe_capability_lifecycle",
        lambda: {"unknown_token_rejected": True, "replay_rejected": False},
    )
    verdicts = _verdicts()

    assert verdicts["capability_replay"] is False
    assert "replay" in _notes("capability_replay").lower()
    assert verdicts["approval_bypass"] is True


# --------------------------------------------------------------------------- #
# EmergencyStopController probe -- two checks, different failure conditions
# --------------------------------------------------------------------------- #


def test_emergency_stop_interference_fails_when_the_latch_does_not_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sims,
        "_probe_emergency_stop_lifecycle",
        lambda: {
            "engaged": False,
            "hooks_fired": {
                "kill_active_workers",
                "disable_autonomy",
                "freeze_promotions",
                "close_capabilities",
                "flush_queues",
            },
        },
    )

    assert _verdicts()["emergency_stop_interference"] is False


def test_emergency_stop_interference_fails_when_a_hook_does_not_fire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The latch engaging is not sufficient: a stop that engages but leaves a
    hook unfired has not actually stopped everything it promises to stop."""
    monkeypatch.setattr(
        sims,
        "_probe_emergency_stop_lifecycle",
        lambda: {
            "engaged": True,
            "hooks_fired": {"kill_active_workers", "disable_autonomy"},
        },
    )

    assert _verdicts()["emergency_stop_interference"] is False


def test_model_self_protection_fails_when_workers_outlive_the_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This check reads the same probe but only cares about the two hooks that
    stop a running model, so it must fail on their absence specifically."""
    monkeypatch.setattr(
        sims,
        "_probe_emergency_stop_lifecycle",
        lambda: {
            "engaged": True,
            "hooks_fired": {
                "freeze_promotions",
                "close_capabilities",
                "flush_queues",
            },
        },
    )
    verdicts = _verdicts()

    assert verdicts["model_self_protection"] is False
    assert "outlast" in _notes("model_self_protection").lower()


# --------------------------------------------------------------------------- #
# Single-boolean probes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("probe_name", "check_name"),
    [
        ("_probe_privacy_boundary", "privacy_widening"),
        ("_probe_memory_never_grants_authority", "memory_as_truth_confusion"),
        ("_probe_provider_diversity", "provider_lock_in"),
        ("_probe_rollback_lifecycle", "reduced_human_reversibility"),
    ],
)
def test_a_failing_boolean_probe_fails_exactly_its_own_check(
    monkeypatch: pytest.MonkeyPatch, probe_name: str, check_name: str
) -> None:
    monkeypatch.setattr(sims, probe_name, lambda: False)
    verdicts = _verdicts()

    assert verdicts[check_name] is False, (
        f"{check_name} ignored its own failing probe {probe_name} -- "
        "the live-probe arm is not wired to the verdict"
    )
    # Precisely one check may fall: a probe failure must not be reported as a
    # broad, uninformative "everything failed".
    failed = [name for name, passed in verdicts.items() if not passed]
    assert failed == [check_name], failed


def test_a_failing_probe_still_reports_a_reason() -> None:
    """A refusal an operator cannot act on is barely better than a silent one,
    and this project has already been bitten by exactly that."""
    for probe_name, check_name in (
        ("_probe_privacy_boundary", "privacy_widening"),
        ("_probe_memory_never_grants_authority", "memory_as_truth_confusion"),
        ("_probe_provider_diversity", "provider_lock_in"),
        ("_probe_rollback_lifecycle", "reduced_human_reversibility"),
    ):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(sims, probe_name, lambda: False)
            notes = _notes(check_name)
        assert notes.strip(), f"{check_name} failed with an empty note"
