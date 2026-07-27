"""Reconciliation pass item 4: the live local registry (this machine's real,
gitignored `data/aios_memory.db`) was found admitting `granite3.2:2b` for
`summarise` with `admission_reason="Passed all qualification checks"`,
directly contradicted by the checked-in live evidence at
`release/slice32/granite-qualification-live.json` (0/3 runs passed all 16
checks; `summarisation` failed in all 3). These tests drive
`qualification_evidence.py` against that real evidence file, not a
hand-built fixture, to prove it would have caught the drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from aios.application.local_workforce.qualification_evidence import (
    evidence_backed_profiles,
    unsupported_claimed_profiles,
)
from aios.domain.local_workforce.contracts import LocalJobProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
GRANITE_EVIDENCE_PATH = (
    REPO_ROOT / "release" / "slice32" / "granite-qualification-live.json"
)
QWEN_EVIDENCE_PATH = (
    REPO_ROOT / "release" / "slice32" / "qwen25coder7b-qualification-live.json"
)


def _granite_evidence() -> dict:
    return json.loads(GRANITE_EVIDENCE_PATH.read_text(encoding="utf-8"))


def _qwen_evidence() -> dict:
    return json.loads(QWEN_EVIDENCE_PATH.read_text(encoding="utf-8"))


def test_real_granite_evidence_backs_extract_classify_cluster_not_summarise() -> None:
    evidence = _granite_evidence()

    backed = evidence_backed_profiles(evidence)

    assert backed == frozenset(
        {LocalJobProfile.EXTRACT, LocalJobProfile.CLASSIFY, LocalJobProfile.CLUSTER}
    )
    assert LocalJobProfile.SUMMARISE not in backed


def test_real_granite_evidence_flags_the_actual_drift_found_in_the_live_registry() -> (
    None
):
    """This is the literal claim found in data/aios_memory.db at grounding
    time: admitted for summarise/triage/format_report, none of which the
    evidence backs (summarise failed; triage/format_report were never
    tested by this suite at all)."""
    evidence = _granite_evidence()
    claimed = frozenset(
        {
            LocalJobProfile.SUMMARISE,
            LocalJobProfile.TRIAGE,
            LocalJobProfile.FORMAT_REPORT,
            LocalJobProfile.EXTRACT,
        }
    )

    unsupported = unsupported_claimed_profiles(evidence, claimed)

    assert unsupported == frozenset(
        {
            LocalJobProfile.SUMMARISE,
            LocalJobProfile.TRIAGE,
            LocalJobProfile.FORMAT_REPORT,
        }
    )
    assert LocalJobProfile.EXTRACT not in unsupported


def test_a_profile_failing_on_only_one_of_several_runs_is_not_backed() -> None:
    evidence = {
        "runs": [
            {"result": {"test_results": [{"test_id": "extraction", "passed": True}]}},
            {"result": {"test_results": [{"test_id": "extraction", "passed": False}]}},
        ]
    }

    assert evidence_backed_profiles(evidence) == frozenset()


def test_a_profile_with_no_corresponding_test_id_is_never_backed() -> None:
    evidence = {
        "runs": [
            {
                "result": {
                    "test_results": [
                        {"test_id": "extraction", "passed": True},
                        {"test_id": "classification", "passed": True},
                    ]
                }
            }
        ]
    }

    backed = evidence_backed_profiles(evidence)

    assert LocalJobProfile.TRIAGE not in backed
    assert LocalJobProfile.FORMAT_REPORT not in backed


def test_empty_evidence_backs_nothing() -> None:
    assert evidence_backed_profiles({"runs": []}) == frozenset()
    assert evidence_backed_profiles({}) == frozenset()


def test_real_qwen_coder_evidence_backs_all_four_mapped_profiles() -> None:
    """Tier-1/2 follow-up: unlike granite3.2:2b, qwen2.5-coder:7b passes ALL
    16 checks in every one of 3 live runs (release/slice32/
    qwen25coder7b-qualification-live.json) -- the same unmodified suite,
    a genuinely better-suited model, not a loosened validator."""
    evidence = _qwen_evidence()

    backed = evidence_backed_profiles(evidence)

    assert backed == frozenset(
        {
            LocalJobProfile.EXTRACT,
            LocalJobProfile.CLASSIFY,
            LocalJobProfile.CLUSTER,
            LocalJobProfile.SUMMARISE,
        }
    )


# --------------------------------------------------------------------------- #
# Organ 33: a profile must be EARNED, not asserted.
#
# POST /api/v1/local-workforce/{model_id}/profiles wrote whatever the request
# body asked for, validating only that each value was a real vocabulary member.
# That is the exact mechanism behind the drift already found in this repo's live
# registry: granite3.2:2b claimed `summarise` while every recorded qualification
# run failed summarisation. Vocabulary validation could never catch it --
# `summarise` IS a valid profile, the model just had not earned it.
# --------------------------------------------------------------------------- #


def test_a_never_qualified_model_earns_nothing() -> None:
    """None persisted evidence means nothing is backed. Refusing everything is
    the honest answer, not an inconvenience to route around."""
    from aios.application.local_workforce.qualification_evidence import (
        evidence_backed_profiles,
    )

    assert evidence_backed_profiles({"runs": []}) == frozenset()


def test_a_profile_failing_in_any_run_is_not_backed() -> None:
    """One flaky pass is not proof -- the profile must pass in EVERY run."""
    from aios.domain.local_workforce.contracts import LocalJobProfile
    from aios.application.local_workforce.qualification_evidence import (
        evidence_backed_profiles,
    )

    def _run(summarisation_passed: bool) -> dict:
        return {
            "result": {
                "test_results": [
                    {"test_id": "extraction", "passed": True},
                    {"test_id": "summarisation", "passed": summarisation_passed},
                ]
            }
        }

    both_passed = evidence_backed_profiles({"runs": [_run(True), _run(True)]})
    one_failed = evidence_backed_profiles({"runs": [_run(True), _run(False)]})

    assert LocalJobProfile.SUMMARISE in both_passed
    assert LocalJobProfile.SUMMARISE not in one_failed
    # extraction passed in both runs either way
    assert LocalJobProfile.EXTRACT in one_failed


def test_the_service_refuses_a_profile_its_evidence_does_not_back() -> None:
    """Guards the regression at the level that matters: the production write
    path must consult evidence, not just the vocabulary."""
    import inspect

    from aios.application.local_workforce import service as service_module

    source = inspect.getsource(service_module.LocalWorkforceService.update_profiles)

    assert "unsupported_profile_claims" in source
    assert "UnsupportedJobProfileClaim" in source
