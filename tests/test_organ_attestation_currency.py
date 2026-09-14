"""An attestation the code has moved out from under is not evidence.

WHY THIS FILE EXISTS. The twelve-condition green contract asks, in C12, whether
`last_verified_sha` is an ANCESTOR of HEAD:

    elif ancestry_fn(root, sha) is False:
        failures.append(("C12", f"last_verified_sha {sha} is not an ancestor..."))

An old commit is an ancestor of HEAD forever. So an organ verified once stays
green however far the code beneath it travels, and nothing in C1-C12 notices.

Measured 2026-09-13, before this rule existed:

    38 of 55 organs pinned to one sha dated 2026-07-31
    199 commits landed since
    46 of 55 organs had their OWN production_entrypoints change after their
       attestation -- all 46 of them green

That is not a hypothetical drift. Three PRs in the same week (#328, #329, #330)
found live ungoverned production objects -- a CapabilityAuthority issuing
capabilities the emergency stop could not halt, MissionService built with no
latch in four production sites, thirteen runtime boundaries whose stop check
returned silently when nothing was wired -- every one inside a GREEN organ, and
not one line of the ledger changed.

The rule here is relevance, not age. An organ whose entrypoints have not been
touched since it was verified is still telling the truth however old it is. A
two-day-old attestation over a file that changed yesterday is not.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "_verify_currency", REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py"
)
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)


def _record(sha: str | None, entrypoints: list[str]):
    return SimpleNamespace(
        organ_id=999,
        name="probe",
        last_verified_sha=sha,
        production_entrypoints=entrypoints,
    )


def _sha_that_predates(path: str) -> str | None:
    """A commit from before *path* last changed, or None if history is too thin."""
    out = subprocess.run(
        ["git", "log", "--format=%H", "-2", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    return out[1] if len(out) > 1 else None


def test_the_organ_that_was_green_over_thirteen_fail_open_boundaries_is_flagged() -> (
    None
):
    """THE BAR, reproduced against the real ledger rather than asserted.

    Organ 26's authority owner is `EmergencyStopHardWiringAuthority` and its
    `production_entrypoints` are -- exactly -- the files whose stop check was
    fail-open: the gateway, learning, maintenance, recovery, capabilities,
    main.py, actions and council routes.

    It declared C1-C12 PASS over the thirteen boundaries that could not be
    halted. This rule is the one that refuses that.
    """
    from aios.application.governance.organ_ledger import load_ledger

    ledger = load_ledger(REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json")
    organ_26 = next((r for r in ledger if r.organ_id == 26), None)
    assert organ_26 is not None, "organ 26 is missing from the ledger"

    # ASSERTS THE RULE, ON ORGAN 26'S OWN SHAPE -- not that organ 26 is
    # currently stale.
    #
    # This test used to read the live row and require `failures` to be
    # non-empty, which made it depend on organ 26 REMAINING broken. On
    # 2026-09-14 the organ was legitimately re-verified at a current tip and
    # this test went red for the best possible reason: the thing it was
    # watching had been fixed. Keeping it green by leaving an organ stale would
    # invert the entire point.
    #
    # So the fixture is now synthetic and built from organ 26's REAL
    # entrypoints, pinned to a sha from before they last moved. The historical
    # incident stays documented, the bar stays enforced, and the organ is free
    # to be current.
    entrypoints = [str(p) for p in organ_26.production_entrypoints]
    assert entrypoints, "organ 26 declares no production_entrypoints"
    stale_sha = next(
        (sha for path in entrypoints if (sha := _sha_that_predates(path))), None
    )
    if stale_sha is None:
        pytest.skip("history too thin to find a commit predating organ 26's files")

    failures = _verify._staleness_failures(_record(stale_sha, entrypoints), REPO_ROOT)

    assert failures, (
        "an attestation pinned BEFORE organ 26's own files moved is treated as "
        "current -- the exact gap that let it stay green over thirteen "
        "fail-open boundaries"
    )
    condition, message = failures[0]
    assert condition == "C12"
    assert "STALE" in message
    assert "production_entrypoints" in message


def test_an_untouched_entrypoint_is_not_called_stale() -> None:
    """A rule that fires on a truthful attestation is worse than no rule.

    `AGENTS.md` has not changed in a long time and is not an entrypoint of
    anything; pinned at HEAD, nothing has moved since, so nothing is stale.
    """
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()

    assert not _verify._staleness_failures(_record(head, ["AGENTS.md"]), REPO_ROOT)


def test_a_file_that_changed_after_the_attestation_is_stale() -> None:
    """The mechanism itself, on a synthetic record.

    Pins the rule independently of whatever the shipped ledger happens to say,
    so it keeps meaning something after the re-verification sweep.
    """
    target = "scripts/verify_organ_twelve_conditions.py"
    older = _sha_that_predates(target)
    if older is None:  # pragma: no cover - only in a shallow clone
        pytest.skip("history too shallow to name a commit before the last change")

    failures = _verify._staleness_failures(_record(older, [target]), REPO_ROOT)

    assert failures, f"{target} changed after {older[:12]} and was not flagged"
    assert target in failures[0][1]


def test_an_organ_with_no_entrypoints_is_left_to_the_other_conditions() -> None:
    """Scoped deliberately: this rule answers one question and no others.

    With nothing declared to attest to, there is nothing to be stale about --
    C1 and C2 are the conditions that care about a missing entrypoint list.
    """
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()

    assert not _verify._staleness_failures(_record(head, []), REPO_ROOT)


def test_a_missing_sha_is_left_to_c11() -> None:
    """C11 already reports a missing or malformed sha; do not double-report it.

    Organ 55 legitimately carries a null sha while it awaits the operator's
    attestation, and must not collect a second, misleading failure here.
    """
    assert not _verify._staleness_failures(_record(None, ["AGENTS.md"]), REPO_ROOT)
    assert not _verify._staleness_failures(
        _record("not-a-sha", ["AGENTS.md"]), REPO_ROOT
    )


# --------------------------------------------------------------------------- #
# C10 currency -- the same hole, one level down
#
# The recount fixed ATTESTATION currency. Evidence currency was still unchecked:
# `_evidence_reference_failures` compares an artifact's tip_sha to the evidence
# row's OWN declared commit_sha, which is self-referential. Evidence could be
# arbitrarily old and C10 said nothing.
#
# Why it mattered the day this was written: all 41 organs the recount demoted
# clear every non-test condition at HEAD, so re-running their cited tests would
# have restored green -- stamping a current sha onto live proof gathered ~199
# commits earlier. Anyone running the tests could have undone the recount
# without writing a single dishonest line.
# --------------------------------------------------------------------------- #


def _evidence_record(organ_id: int, entrypoints: list[str], evidence_sha: str):
    """A record carrying one live evidence row at *evidence_sha*."""
    return SimpleNamespace(
        organ_id=organ_id,
        name="probe",
        status="green",
        last_verified_sha="0" * 40,
        production_entrypoints=entrypoints,
        live_evidence=[
            SimpleNamespace(
                proof_level="live",
                commit_sha=evidence_sha,
                description="probe evidence",
            )
        ],
    )


def test_evidence_older_than_the_code_it_attests_to_is_refused() -> None:
    """THE BAR. Re-running tests does not refresh a live proof.

    A green claim whose live evidence predates changes to its own entrypoints is
    asserting something it has not re-observed.
    """
    target = "scripts/verify_organ_twelve_conditions.py"
    older = _sha_that_predates(target)
    if older is None:  # pragma: no cover - only in a shallow clone
        pytest.skip("history too shallow to name a commit before the last change")

    failures = _verify._evidence_currency_failures(
        _evidence_record(999, [target], older), REPO_ROOT
    )

    assert failures, f"{target} changed after {older[:12]} and the evidence passed"
    condition, message = failures[0]
    assert condition == "C10"
    assert "STALE" in message
    assert "re-running the cited tests does not refresh" in message


def test_current_evidence_is_not_flagged() -> None:
    """A rule that fires on truthful evidence is worse than no rule."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()

    assert not _verify._evidence_currency_failures(
        _evidence_record(999, ["AGENTS.md"], head), REPO_ROOT
    )


def test_no_green_organ_outside_the_spine_has_stale_evidence() -> None:
    """Against the REAL ledger: the containment, not the count.

    This asserted equality with the frozen-spine set, because on 2026-09-13 all
    five spine organs WERE stale and that was the measurement of the day. The
    operator then re-attested the spine at a current tip and the set became
    empty -- so the test failed for the best possible reason: the condition it
    described had been fixed.

    A measurement is not an invariant. The invariant is that stale evidence
    NEVER appears on a green organ the Sovereign cannot clear: `flagged` may be
    empty, and may contain spine organs while they await his signature, but a
    non-spine green appearing here is a real finding, because an agent CAN clear
    that one by re-verifying and therefore must.
    """
    from aios.application.governance.organ_ledger import (
        FROZEN_SECURITY_ORGAN_IDS,
        load_ledger,
    )

    ledger = load_ledger(REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json")
    greens = [r for r in ledger if r.status == "green"]
    flagged = {
        r.organ_id for r in greens if _verify._evidence_currency_failures(r, REPO_ROOT)
    }

    assert not (flagged - set(FROZEN_SECURITY_ORGAN_IDS)), (
        "a green organ outside the frozen spine is resting on stale live "
        f"evidence and an agent can fix it: {sorted(flagged - set(FROZEN_SECURITY_ORGAN_IDS))}"
    )


def test_a_spine_finding_carries_the_marker_that_keeps_it_ungated() -> None:
    """The gate filters on this marker to report without blocking.

    If the wording ever loses it, five findings the Sovereign alone can clear
    would start failing CI for everyone -- so the marker is pinned here rather
    than living only in a string literal.

    PLANTED, not read from the shipped ledger. It used to take organ 1 from disk
    and rely on it being stale, which stopped working the moment the spine was
    re-attested -- the property was real but the fixture was the repository's
    passing mood. Planting a known-stale spine record tests the wording whether
    or not the real spine happens to need signing today.
    """
    target = "scripts/verify_organ_twelve_conditions.py"
    older = _sha_that_predates(target)
    if older is None:  # pragma: no cover - only in a shallow clone
        pytest.skip("history too shallow to name a commit before the last change")

    record = _evidence_record(1, [target], older)  # organ 1: frozen spine

    failures = _verify._evidence_currency_failures(record, REPO_ROOT)

    assert failures
    assert "FROZEN-SPINE" in failures[0][1]


def test_a_non_live_evidence_row_is_ignored() -> None:
    """Scoped deliberately: only `proof_level="live"` rows make a live claim."""
    older = _sha_that_predates("scripts/verify_organ_twelve_conditions.py")
    if older is None:  # pragma: no cover
        pytest.skip("history too shallow")
    record = _evidence_record(999, ["scripts/verify_organ_twelve_conditions.py"], older)
    record.live_evidence[0].proof_level = "fixture"

    assert not _verify._evidence_currency_failures(record, REPO_ROOT)
