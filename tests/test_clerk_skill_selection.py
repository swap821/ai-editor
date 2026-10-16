"""The clerk's one live job can be earned, and qualifying measures that job.

Found 2026-10-11 by the production scoreboard (docs/PRODUCTION_HARDENING.md):
the only production caller of the clerk asks for SELECT_SKILL, and

1. no qualification test covered SELECT_SKILL, so no model could ever earn it
   and the job ALWAYS escalated;
2. its prompt gave the clerk no criteria and embedded an example answer that
   already said yes, so a model copying the example "passed";
3. its declared schema had 3 fields while the prompt asked for 7, and the job
   runner refuses extra fields -- so an obedient model was always refused;
4. four roles had qualification tests all along but were never mapped.

Pinned here, both directions: the shared module reads only the asked shape;
an always-yes and an always-no model each fail one case and cannot earn the
role, a correct one earns it; the live caller sends exactly the shared prompt
and schema; the four tested roles are grantable.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aios.application.local_workforce.qualification_evidence import (
    TEST_ID_TO_JOB_PROFILE,
    evidence_backed_profiles,
)
from aios.domain.local_workforce import skill_selection as ss
from aios.domain.local_workforce.contracts import LocalJobProfile, LocalJobResult

GOOD = {
    "applicable": True,
    "abstain": False,
    "required_inputs_present": True,
    "confidence": 0.9,
    "reason": "inputs present",
}


# --------------------------------------------------------------------------- #
# Reading the answer
# --------------------------------------------------------------------------- #


def test_only_the_asked_shape_is_read() -> None:
    assert ss.read_skill_selection(GOOD) is not None
    assert ss.read_skill_selection({**GOOD, "extra": 1}) is None
    assert (
        ss.read_skill_selection({k: v for k, v in GOOD.items() if k != "abstain"})
        is None
    )
    assert ss.read_skill_selection({**GOOD, "applicable": "true"}) is None, (
        "a string is not a yes"
    )
    assert ss.read_skill_selection({**GOOD, "confidence": True}) is None
    assert ss.read_skill_selection({**GOOD, "confidence": 1.5}) is None
    assert ss.read_skill_selection({**GOOD, "reason": None}) is None
    assert ss.read_skill_selection(None) is None


@pytest.mark.parametrize(
    "change",
    [
        {"applicable": False},
        {"abstain": True},
        {"required_inputs_present": False},
        {"confidence": ss.MIN_CONFIDENCE - 0.01},
    ],
)
def test_any_doubt_is_a_veto(change) -> None:
    answer = ss.read_skill_selection({**GOOD, **change})
    assert answer is not None and not answer.admits()
    assert ss.read_skill_selection({**GOOD, "confidence": ss.MIN_CONFIDENCE}).admits()


def test_the_schema_is_the_fields() -> None:
    assert tuple(ss.OUTPUT_SCHEMA) == ss.FIELDS


# --------------------------------------------------------------------------- #
# The question
# --------------------------------------------------------------------------- #


def test_the_prompt_carries_the_criteria_and_no_answer() -> None:
    prompt = ss.qualification_prompt(ss.EXCLUDED_SITUATION)
    for criterion in (
        ss.QUALIFICATION_SKILL["problem_signature"],
        "test_path",
        "the test file has been deleted",
        "the tests need network access",
    ):
        assert criterion in prompt
    assert "true" not in prompt.lower().replace("(boolean: true when", ""), (
        "the question must not contain an answer to copy"
    )


# --------------------------------------------------------------------------- #
# Qualification: always-yes and always-no cannot earn the role
# --------------------------------------------------------------------------- #


def _run(answer_for) -> dict:
    """A qualification run's evidence, with each case answered by *answer_for*."""
    results = []
    for test_id, check, situation in (
        ("skill_selection_applies", ss.check_applies, ss.APPLIES_SITUATION),
        ("skill_selection_abstains", ss.check_abstains, ss.EXCLUDED_SITUATION),
    ):
        passed, _ = check(answer_for(situation))
        results.append({"test_id": test_id, "passed": passed})
    return {"runs": [{"result": {"test_results": results}}]}


ALWAYS_YES = lambda situation: dict(GOOD)  # noqa: E731
ALWAYS_NO = lambda situation: {**GOOD, "applicable": False, "abstain": True}  # noqa: E731


def _correct(situation) -> dict:
    if situation is ss.APPLIES_SITUATION:
        return dict(GOOD)
    return {**GOOD, "applicable": False, "abstain": True, "reason": "file deleted"}


@pytest.mark.parametrize(
    "model", [ALWAYS_YES, ALWAYS_NO], ids=["always-yes", "always-no"]
)
def test_a_model_that_does_not_judge_cannot_earn_the_role(model) -> None:
    assert LocalJobProfile.SELECT_SKILL not in evidence_backed_profiles(_run(model))


def test_a_model_that_judges_earns_the_role() -> None:
    assert LocalJobProfile.SELECT_SKILL in evidence_backed_profiles(_run(_correct))


def test_abstaining_for_the_wrong_reason_fails() -> None:
    """The input is present; claiming it is missing is not the judgement asked."""
    wrong = {
        **GOOD,
        "applicable": False,
        "abstain": True,
        "required_inputs_present": False,
    }
    assert ss.check_abstains(wrong)[0] is False


def test_the_suite_asks_both_cases() -> None:
    from aios.domain.local_workforce.qualifier import _cases

    ids = {case.test_id for case in _cases()}
    assert {"skill_selection_applies", "skill_selection_abstains"} <= ids


def test_every_mapped_test_is_in_the_suite() -> None:
    """A mapped test the suite never runs could never back its role."""
    from aios.domain.local_workforce.qualifier import _cases

    ids = {case.test_id for case in _cases()}
    assert set(TEST_ID_TO_JOB_PROFILE) <= ids


def test_the_four_tested_roles_are_grantable() -> None:
    assert {
        LocalJobProfile.VALIDATE_STRUCTURE,
        LocalJobProfile.SUMMARISE_DISAGREEMENT,
        LocalJobProfile.EXPLAIN_ROUTE,
        LocalJobProfile.CHECK_CONTEXT_COMPLETENESS,
        LocalJobProfile.SELECT_SKILL,
    } <= set(TEST_ID_TO_JOB_PROFILE.values())


# --------------------------------------------------------------------------- #
# The live caller asks exactly that question
# --------------------------------------------------------------------------- #


def _live_request(tmp_path: Path, answer: dict):
    from tests.test_canonical_skill_reuse_validator import (
        _build_real_service,
        _reuse_attempt,
        _valid_skill_record,
    )

    service = _build_real_service(tmp_path)
    assert service.local_workforce_service is not None
    seen = MagicMock(
        return_value=LocalJobResult(
            job_id="j",
            model_id="m",
            structured_output=answer,
            schema_valid=True,
            evidence_references_preserved=True,
            unsupported_claims=(),
            latency=0.01,
            status="completed",
        )
    )
    service.local_workforce_service.run_advisory_job = seen
    skill = _valid_skill_record()
    directive = _reuse_attempt(service, skill)
    return seen.call_args.args[0], skill, directive


def test_the_live_job_sends_the_shared_question_and_schema(tmp_path) -> None:
    request, skill, directive = _live_request(tmp_path, dict(GOOD))
    assert request.job_profile == LocalJobProfile.SELECT_SKILL
    assert dict(request.required_output_schema) == dict(ss.OUTPUT_SCHEMA)
    assert skill.problem_signature in request.redacted_payload
    assert json.dumps(list(skill.escalation_conditions)) in request.redacted_payload
    assert type(directive).__name__ == "LocalExecutionDirective"


def test_a_live_abstention_escalates(tmp_path) -> None:
    _, _, directive = _live_request(
        tmp_path, {**GOOD, "abstain": True, "reason": "excluded"}
    )
    assert type(directive).__name__ == "EscalateToFrontierDirective"
    assert directive.reason == "excluded"


def test_a_malformed_live_answer_escalates(tmp_path) -> None:
    _, _, directive = _live_request(
        tmp_path, {"applicable": True, "confidence": 0.9, "reason": "ok"}
    )
    assert type(directive).__name__ == "EscalateToFrontierDirective"
