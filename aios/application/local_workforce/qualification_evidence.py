"""Cross-checks a model's admitted job profiles against real qualification
evidence (reconciliation pass item 4).

Found while grounding this item: the live local registry (`data/
aios_memory.db`, this machine's actual running state, not a test fixture)
currently admits `granite3.2:2b` for `summarise` with `admission_reason=
"Passed all qualification checks"` -- but the checked-in live evidence at
`release/slice32/granite-qualification-live.json` shows the opposite: 0 of
3 independent live runs passed all 16 checks, and the *only* check that
ever failed, in all 3 runs, was `summarisation`. The registry's admitted
profile was never actually derived from qualification evidence anywhere in
this codebase -- `LocalWorkforceRegistry.update_profiles()` just stores
whatever a caller passes it, on trust.

This module does not build the missing automatic derivation pipeline (that
would need the qualification suite itself to become profile-aware, a real
design task -- most `LocalJobProfile` values, e.g. `TRIAGE`/
`FORMAT_REPORT`, have no corresponding test at all in the current 16-check
suite, so there is nothing to auto-derive for them regardless). What it
adds is the narrower, honest, useful piece: given a `QualificationResult`-
shaped evidence payload (matching the schema already recorded in
`release/slice32/*.json`) and a set of currently-claimed profiles, report
which of those claimed profiles the evidence actually backs, so a caller
can never re-introduce this exact class of drift silently.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aios.domain.local_workforce.contracts import LocalJobProfile

#: The job profiles with an unambiguous, name-matched qualification test_id.
#: A profile with SEVERAL tests is backed only when every one of them passes.
#:
#: 2026-10-11: the four Slice-32 tests (structure_validation ...
#: context_completeness) had been in the suite all along while this map still
#: said their profiles had "zero test coverage"; they are mapped now. And
#: SELECT_SKILL -- the only profile production code asks for -- gained its two
#: tests (aios/domain/local_workforce/skill_selection.py); until then no model
#: could ever earn it, so that job always escalated.
#:
#: Still with no test, so never grantable: TRIAGE, FORMAT_REPORT,
#: PREPARE_BRIEFING, PARAMETERISE_SKILL.
TEST_ID_TO_JOB_PROFILE: Mapping[str, LocalJobProfile] = {
    "extraction": LocalJobProfile.EXTRACT,
    "classification": LocalJobProfile.CLASSIFY,
    "summarisation": LocalJobProfile.SUMMARISE,
    "duplicate_grouping": LocalJobProfile.CLUSTER,
    "structure_validation": LocalJobProfile.VALIDATE_STRUCTURE,
    "disagreement_summary": LocalJobProfile.SUMMARISE_DISAGREEMENT,
    "route_explanation": LocalJobProfile.EXPLAIN_ROUTE,
    "context_completeness": LocalJobProfile.CHECK_CONTEXT_COMPLETENESS,
    "skill_selection_applies": LocalJobProfile.SELECT_SKILL,
    "skill_selection_abstains": LocalJobProfile.SELECT_SKILL,
}


def evidence_backed_profiles(
    evidence: Mapping[str, Any],
) -> frozenset[LocalJobProfile]:
    """Return the profiles whose mapped test_id passed in *every* recorded
    run. A single flaky pass is not enough -- the qualification suite's own
    `repeated_run_reliability` case exists precisely because a one-off pass
    is not proof of qualification, and this function holds itself to the
    same standard."""
    runs: Sequence[Mapping[str, Any]] = evidence.get("runs", ())
    if not runs:
        return frozenset()
    backed = set(TEST_ID_TO_JOB_PROFILE.values())
    for run in runs:
        test_results = run.get("result", {}).get("test_results", ())
        passed_ids = {
            item["test_id"] for item in test_results if item.get("passed") is True
        }
        for test_id, profile in TEST_ID_TO_JOB_PROFILE.items():
            if test_id not in passed_ids:
                backed.discard(profile)
    return frozenset(backed)


def unsupported_claimed_profiles(
    evidence: Mapping[str, Any], claimed_profiles: frozenset[LocalJobProfile]
) -> frozenset[LocalJobProfile]:
    """Of the profiles a registry currently claims a model is admitted for,
    return the ones this evidence payload does not actually back -- either
    because a mapped test failed on at least one run, or because the
    profile has no test coverage in this suite at all."""
    return claimed_profiles - evidence_backed_profiles(evidence)


__all__ = [
    "TEST_ID_TO_JOB_PROFILE",
    "evidence_backed_profiles",
    "unsupported_claimed_profiles",
]
