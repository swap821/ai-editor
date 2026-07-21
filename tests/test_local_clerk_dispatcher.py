"""Slice 32: Production Local Clerk Front Desk."""

from __future__ import annotations

import json
from pathlib import Path

from aios.application.local_workforce import dispatch_clerical_job
from aios.domain.local_workforce.contracts import LocalJobProfile
from aios.domain.local_workforce.qualifier import QualificationResult

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_EVIDENCE_PATH = REPO_ROOT / "release" / "slice32" / "granite-qualification-live.json"


def _qualification(**overrides: object) -> QualificationResult:
    fields: dict[str, object] = dict(
        passed=True,
        schema_validity=1.0,
        identifier_preservation=1.0,
        authority_mutation_attempts=0,
        tool_requests_accepted=0,
        secret_reproduction=0,
        unsupported_claim_rate=0.0,
        timeout_rate=0.0,
    )
    fields.update(overrides)
    return QualificationResult(**fields)


# --- profile catalog ---------------------------------------------------


def test_local_job_profile_has_the_four_slice_32_additions() -> None:
    names = {member.name for member in LocalJobProfile}
    assert {
        "VALIDATE_STRUCTURE",
        "SUMMARISE_DISAGREEMENT",
        "EXPLAIN_ROUTE",
        "CHECK_CONTEXT_COMPLETENESS",
    } <= names


def test_local_job_profile_did_not_duplicate_existing_concepts() -> None:
    """CLASSIFY_REQUEST/PREPARE_FRONTIER_BRIEF/TRIAGE_FAILURE are the plan's
    names for jobs this enum already covers under CLASSIFY/PREPARE_BRIEFING/
    TRIAGE -- confirm we didn't fragment the enum with near-duplicates."""
    names = {member.name for member in LocalJobProfile}
    assert "CLASSIFY_REQUEST" not in names
    assert "PREPARE_FRONTIER_BRIEF" not in names
    assert "TRIAGE_FAILURE" not in names
    assert "CLASSIFY" in names
    assert "PREPARE_BRIEFING" in names
    assert "TRIAGE" in names


# --- dispatcher --------------------------------------------------------


def test_deterministic_code_always_wins_first() -> None:
    decision = dispatch_clerical_job(
        deterministic_available=True,
        qualification=_qualification(passed=False),
    )
    assert decision == "deterministic"


def test_no_admitted_local_model_results_in_frontier_escalation() -> None:
    decision = dispatch_clerical_job(
        deterministic_available=False, qualification=None
    )
    assert decision == "frontier_escalation"


def test_failed_qualification_results_in_frontier_escalation_not_local_use() -> None:
    """Cloud denial (no qualification) must never be silently treated as if
    the local clerk had completed frontier-level reasoning -- it escalates
    honestly instead of proceeding with an unqualified model."""
    decision = dispatch_clerical_job(
        deterministic_available=False,
        qualification=_qualification(passed=False),
        confidence=0.95,  # even a high self-reported confidence can't override this
    )
    assert decision == "frontier_escalation"


def test_low_confidence_escalates_to_human_clarification() -> None:
    decision = dispatch_clerical_job(
        deterministic_available=False,
        qualification=_qualification(passed=True),
        confidence=0.2,
        confidence_floor=0.6,
    )
    assert decision == "human_clarification"


def test_qualified_model_with_sufficient_confidence_uses_local_clerk() -> None:
    decision = dispatch_clerical_job(
        deterministic_available=False,
        qualification=_qualification(passed=True),
        confidence=0.9,
        confidence_floor=0.6,
    )
    assert decision == "local_clerk"


def test_qualified_model_with_no_reported_confidence_uses_local_clerk() -> None:
    """Absence of a confidence score is not the same as low confidence."""
    decision = dispatch_clerical_job(
        deterministic_available=False,
        qualification=_qualification(passed=True),
        confidence=None,
    )
    assert decision == "local_clerk"


# --- live evidence -------------------------------------------------------


def test_live_qualification_evidence_file_is_honest_not_cherry_picked() -> None:
    """This is real evidence recorded against the live granite3.2:2b model
    via Ollama in this environment -- not a synthetic fixture. It must
    record every run's outcome, not just a passing one."""
    payload = json.loads(LIVE_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["model"]["exact_tag"] == "granite3.2:2b"
    assert payload["model"]["digest"]
    assert payload["hardware_profile"]["os"]
    runs = payload["runs"]
    assert len(runs) >= 3
    assert payload["summary"]["total_runs"] == len(runs)
    # The summary's pass count must match what the individual runs say --
    # this test would fail if someone hand-edited the summary to look
    # better than the recorded runs.
    assert payload["summary"]["runs_passed_16_of_16"] == sum(
        1 for run in runs if run["passed"]
    )
