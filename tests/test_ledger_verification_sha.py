"""The ledger's `last_verified_sha` must point at a real, tested commit.

Green-contract condition 11 is "the exact tested commit is recorded" and
condition 12 is "CI verifies that commit". Both are worthless if the recorded
sha names a commit that never existed on the mainline or that CI never ran.

That is not hypothetical. `release/organ-proof-manifest.json` has its own
generator script whose docstring records the same failure already happening
once -- "`source_commit_sha` pointed at a rebased-away commit" -- and that
script exists to stop it recurring. `last_verified_sha` in the ledger had no
equivalent guard, and so it happened again: organs 48-51 were flipped green
against a squash-merged PR-branch commit that was never on master and had zero
CI check-runs.

`validate_ledger()` cannot catch this. It compares the ledger against a
registry of expected strings; it never asks git whether a recorded sha is
real.

Deliberately degrades rather than lying: CI checks out shallow
(`actions/checkout` with no `fetch-depth`), so historical objects are absent
there and ancestry is genuinely unknowable. A test that failed in that case
would be reporting a checkout depth, not a ledger defect. What is always
checkable -- the sha is well-formed, and is not one of the shapes we know to
be wrong -- is checked unconditionally; ancestry is asserted only where the
object is actually present, which covers every developer machine and any full
clone.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

_LEDGER = Path(".aios/state/ORGAN_GREEN_LEDGER.json")
_SHA = re.compile(r"\A[0-9a-f]{40}\Z")


def _organs() -> list[dict]:
    return json.loads(_LEDGER.read_text(encoding="utf-8"))


def _recorded() -> list[tuple[int, str]]:
    return [
        (organ["organ_id"], organ["last_verified_sha"])
        for organ in _organs()
        if organ.get("last_verified_sha")
    ]


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=Path.cwd()
    )


def _object_present(sha: str) -> bool:
    return _git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def test_every_recorded_sha_is_well_formed() -> None:
    """Always checkable, shallow clone or not."""
    malformed = [(oid, sha) for oid, sha in _recorded() if not _SHA.fullmatch(sha)]

    assert not malformed, (
        f"last_verified_sha must be a full 40-char lowercase hex commit sha: {malformed}"
    )


def test_a_recorded_sha_is_never_one_already_known_to_be_unbacked() -> None:
    """Pins the specific defect this module was written for.

    `d5b2f52...` was a squash-merged PR-branch commit: never on master, zero CI
    check-runs, yet recorded as the verified commit for organs 48-51. Naming it
    explicitly is deliberate -- a general rule cannot be enforced here (see the
    ancestry test's shallow-clone caveat), but this exact regression can be.
    """
    known_unbacked = {"d5b2f52d7fec8a9d560d25d22c3c46102e4cacfc"}

    offenders = [(oid, sha[:9]) for oid, sha in _recorded() if sha in known_unbacked]

    assert not offenders, (
        "these organs record a commit already established as never-tested and "
        f"not on master: {offenders}"
    )


def test_recorded_shas_are_reachable_from_head_when_the_objects_exist() -> None:
    """The real guard. Skips only when git genuinely cannot answer.

    A sha that is not an ancestor of HEAD is either a squash-merged
    PR-branch commit (which no longer exists on the mainline) or an
    unrelated one. Either way nothing on master was ever verified at it.
    """
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        pytest.skip("not a git work tree")

    recorded = _recorded()
    if not recorded:
        pytest.skip("no organ records a verified sha")

    checkable = [(oid, sha) for oid, sha in recorded if _object_present(sha)]
    if not checkable:
        pytest.skip(
            "no recorded commit object is present locally (shallow clone) -- "
            "ancestry is unknowable here, not violated"
        )

    orphaned = [
        (oid, sha[:9])
        for oid, sha in checkable
        if _git("merge-base", "--is-ancestor", sha, "HEAD").returncode != 0
    ]

    assert not orphaned, (
        "these organs record a last_verified_sha that is NOT an ancestor of "
        "HEAD, so the commit they claim to be verified at is not in this "
        f"history at all: {orphaned}"
    )


def test_the_unrecorded_green_organs_do_not_grow() -> None:
    """A ratchet, not a rule.

    12 of the 38 green organs record no `last_verified_sha` at all, so
    condition 11 does not hold for them. Asserting that every green organ must
    record one would fail on the existing ledger, and deciding whether those 12
    should be recorded or un-greened is an operator call about what "green"
    means -- not something a test should force.

    What a test CAN do is stop the gap widening: a NEW green organ arriving
    without a recorded commit fails here, while the existing backlog is left
    visible and untouched.
    """
    green = [organ for organ in _organs() if organ["status"] == "green"]
    unrecorded = sorted(o["organ_id"] for o in green if not o.get("last_verified_sha"))

    #: The known backlog as of this test being written. Lower it when organs
    #: are genuinely verified; never raise it to make a new flip pass.
    known_backlog = [24, 26, 34, 35, 37, 39, 40, 41, 43, 45, 47, 54]

    new_offenders = [oid for oid in unrecorded if oid not in known_backlog]

    assert not new_offenders, (
        "these organs are green but record no verified commit, so condition 11 "
        f"cannot hold for them: {new_offenders}"
    )
    assert len(unrecorded) <= len(known_backlog), (
        f"the unrecorded-green backlog grew: {unrecorded}"
    )
