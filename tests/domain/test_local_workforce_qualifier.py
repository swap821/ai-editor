import pytest
from aios.core.llm import LLMError
from aios.domain.local_workforce.qualifier import QualificationSuite
from aios.domain.local_workforce.admission import HardwareAdmission, AdmissionContext


class FakeLLMClient:
    def __init__(self, mode: str = "pass"):
        self.mode = mode
        self.calls: list[str] = []

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        self.calls.append(prompt)
        if self.mode == "schema_retry_then_pass":
            if "reference identifier" in prompt:
                # Wrong field name on the first attempt (no retry-correction
                # text present yet), the instructed one once corrected.
                if "was rejected" not in prompt:
                    return '{"ref_id": "REF-15"}'
                return '{"reference_id": "REF-15"}'
            return '{"result": "ok"}'
        if self.mode == "schema_retry_exhausted":
            if "reference identifier" in prompt:
                return '{"ref_id": "REF-15"}'
            return '{"result": "ok"}'
        if self.mode == "pass":
            from aios.domain.local_workforce.skill_selection import (
                qualification_fixture_answer,
            )

            answer = qualification_fixture_answer(prompt)
            if answer is not None:
                return answer
            if "one field result" in prompt:
                return '{"result": "ok"}'
            if "reference identifier" in prompt:
                return '{"reference_id": "REF-15"}'
            if "Extract the error code" in prompt:
                return '{"error_code": "connection_refused", "message": "port unavailable"}'
            if "Triage this report" in prompt:
                if "expired session token" in prompt:
                    return '{"severity": "high", "area": "security", "escalate": true}'
                return '{"severity": "low", "area": "frontend", "escalate": false}'
            if "Prepare a briefing" in prompt:
                import json as _json

                return _json.dumps(
                    {
                        "goal": "Stop the Recent activity panel showing closed results twice.",
                        "files": [
                            "frontend/src/workbench/RecentActivity.tsx",
                            "frontend/src/workbench/RecentActivity.test.tsx",
                        ],
                        "constraints": ["Do not touch the backend."],
                        "done_when": "frontend/src/workbench/RecentActivity.test.tsx passes",
                    }
                )
            if "Classify" in prompt:
                return '{"label": "bug"}'
            if "Summarise only" in prompt:
                return '{"summary": "Service unavailable."}'
            if "Two records" in prompt:
                return '{"group_id": "dup-1", "record_ids": ["REC-1", "REC-2"]}'
            if "only supported fact" in prompt:
                return '{"claims": []}'
            if "no owner" in prompt:
                return '{"missing_fields": ["owner"]}'
            if "untrusted text" in prompt:
                return '{"safe": true}'
            if "API key" in prompt:
                return '{"secret_present": false, "summary": "redacted"}'
            if "shell command" in prompt:
                return '{"accepted": false}'
            if "bounded" in prompt:
                return '{"bounded": "ok"}'
            if "must contain fields 'id' and 'status'" in prompt:
                return '{"valid": false, "missing_fields": ["status"]}'
            if "Two analyses disagree" in prompt:
                return '{"disagreement_summary": "timeout vs permissions issue"}'
            if "routed to frontier escalation" in prompt:
                return '{"explanation": "the local model failed qualification"}'
            if "fix the bug" in prompt:
                return (
                    '{"complete": false, "missing": '
                    '["file_path", "error_message", "reproduction_steps"]}'
                )
            return '{"result": "ok"}'
        elif self.mode == "fail_schema":
            if "one field result" in prompt:
                return '{"result": '  # Invalid JSON
            return '{"result": "ok"}'
        elif self.mode == "fail_secret":
            if "one field result" in prompt:
                return '{"result": "ok"}'
            if "API key" in prompt:
                return '{"secret_present": true, "summary": "sk-live-1234"}'
            return '{"result": "ok"}'
        elif self.mode == "fail_timeout":
            raise LLMError("Timeout occurred")
        return '{"result": "ok"}'

    def running_model_metrics(self):
        return {"available": True, "models": [{"size": 1024}]}


def test_hardware_admission_pass():
    hw = HardwareAdmission(min_cpu_count=1, max_concurrent_inferences=2)
    ctx = AdmissionContext(
        requested_context_size=8192,
        requested_output_size=2048,
        active_local_inference_count=0,
    )
    res = hw.evaluate(ctx)
    assert res.admitted is True
    assert res.reason is None


def test_hardware_admission_fail_concurrency():
    hw = HardwareAdmission(min_cpu_count=1, max_concurrent_inferences=2)
    ctx = AdmissionContext(
        requested_context_size=8192,
        requested_output_size=2048,
        active_local_inference_count=2,
    )
    res = hw.evaluate(ctx)
    assert res.admitted is False
    assert "Too many active local inferences" in res.reason


def test_qualification_suite_pass():
    client = FakeLLMClient(mode="pass")
    suite = QualificationSuite(client)
    res = suite.run()
    assert res.passed is True
    assert res.schema_validity == 1.0
    assert res.identifier_preservation == 1.0
    assert res.secret_reproduction == 0
    assert res.suite_version == "r15-v3"
    assert res.metrics["tests_run"] == len(res.test_results)
    assert len(res.test_results) >= 12
    assert {item.test_id for item in res.test_results} >= {
        "prompt_injection",
        "tool_command_rejection",
        "resource_memory",
        "concurrency_refusal",
        "repeated_run_reliability",
    }


def test_qualification_suite_fail_schema():
    client = FakeLLMClient(mode="fail_schema")
    suite = QualificationSuite(client)
    res = suite.run()
    assert res.passed is False
    assert res.schema_validity == 0.0


def test_qualification_suite_fail_secret():
    client = FakeLLMClient(mode="fail_secret")
    suite = QualificationSuite(client)
    res = suite.run()
    assert res.passed is False
    assert res.secret_reproduction == 1


def test_qualification_suite_fail_timeout():
    client = FakeLLMClient(mode="fail_timeout")
    suite = QualificationSuite(client)
    res = suite.run()
    assert res.passed is False
    assert res.timeout_rate == 1.0


# --- Organ 35: qualification coverage for the four new LocalJobProfile cases


def test_qualification_suite_covers_the_four_new_organ_35_cases():
    client = FakeLLMClient(mode="pass")
    suite = QualificationSuite(client)
    res = suite.run()
    assert res.passed is True
    test_ids = {item.test_id for item in res.test_results}
    assert test_ids >= {
        "structure_validation",
        "disagreement_summary",
        "route_explanation",
        "context_completeness",
    }


# --- Organ 37: bounded schema-normalising retry ----------------------------


def test_schema_retry_recovers_from_a_wrong_field_name():
    """A model that used the wrong field name once, then the correct one
    when the exact rejection reason is fed back, ends up passing -- and the
    result honestly records that it took 2 attempts."""
    client = FakeLLMClient(mode="schema_retry_then_pass")
    suite = QualificationSuite(client)
    res = suite.run()
    identifier_result = next(
        item for item in res.test_results if item.test_id == "identifier_preservation"
    )
    assert identifier_result.passed is True
    assert identifier_result.attempts == 2
    assert res.identifier_preservation == 1.0


def test_schema_retry_is_bounded_and_still_reports_honest_failure():
    """A model that never produces the right field name still fails --
    the retry gives it one more real chance, not infinite chances, and the
    final result is an honest failure, not a fabricated pass."""
    client = FakeLLMClient(mode="schema_retry_exhausted")
    suite = QualificationSuite(client)
    res = suite.run()
    identifier_result = next(
        item for item in res.test_results if item.test_id == "identifier_preservation"
    )
    assert identifier_result.passed is False
    assert identifier_result.attempts == 2  # 1 initial + 1 retry, then stop
    assert res.identifier_preservation == 0.0


def test_schema_retry_does_not_apply_to_invalid_json():
    """Retrying invalid JSON or a timeout would not plausibly fix them and
    would only mask a real failure -- only a validator-stage rejection
    (valid, safe JSON in the wrong shape) is retried."""
    client = FakeLLMClient(mode="fail_schema")
    suite = QualificationSuite(client)
    res = suite.run()
    json_case = next(
        item for item in res.test_results if item.test_id == "json_validity"
    )
    assert json_case.passed is False
    assert json_case.attempts == 1


def test_schema_retries_can_be_disabled():
    client = FakeLLMClient(mode="schema_retry_then_pass")
    suite = QualificationSuite(client, max_schema_retries=0)
    res = suite.run()
    identifier_result = next(
        item for item in res.test_results if item.test_id == "identifier_preservation"
    )
    assert identifier_result.passed is False
    assert identifier_result.attempts == 1


def test_max_schema_retries_must_be_non_negative():
    import pytest

    with pytest.raises(ValueError):
        QualificationSuite(FakeLLMClient(), max_schema_retries=-1)


# --- A failed call is diagnosable, and never mistaken for a wrong answer ---


class _Raises:
    def __init__(self, message: str) -> None:
        self.message = message

    def complete(self, prompt, *, system=None, json_mode=False):
        raise LLMError(self.message)

    def running_model_metrics(self):
        return {"available": True, "models": [{"size": 1024}]}


def test_a_socket_timeout_counts_as_a_timeout():
    """urllib says "timed out"; matching only "timeout" kept timeout_rate at 0."""
    res = QualificationSuite(
        _Raises("Ollama request to http://127.0.0.1:11434 failed: timed out")
    ).run()
    assert res.passed is False
    assert res.timeout_rate == 1.0


def test_a_failed_call_keeps_its_error_and_is_listed_as_unreached():
    res = QualificationSuite(
        _Raises("Ollama returned HTTP 500 for model 'm': runner stopped")
    ).run()
    json_case = next(t for t in res.test_results if t.test_id == "json_validity")
    assert "HTTP 500" in json_case.details["error"]
    assert "json_validity" in res.metrics["unreached_test_ids"]
    assert "secret_handling" in res.metrics["unreached_test_ids"]
    # Fail-closed: an unanswered safety case still counts against the model.
    assert res.secret_reproduction == 1


def test_a_wrong_answer_is_not_listed_as_unreached():
    res = QualificationSuite(FakeLLMClient(mode="fail_secret")).run()
    assert res.secret_reproduction == 1
    assert "secret_handling" not in res.metrics["unreached_test_ids"]


# --------------------------------------------------------------------- triage and briefing (2026-11-11)


def _case(test_id):
    from aios.domain.local_workforce.qualifier import _cases

    return next(c for c in _cases() if c.test_id == test_id)


def test_a_constant_triage_fails_one_of_the_pair() -> None:
    always_low = {"severity": "low", "area": "frontend", "escalate": False}
    assert _case("triage_routine").validator(always_low)[0]
    assert not _case("triage_escalates").validator(always_low)[0]
    always_high = {"severity": "high", "area": "security", "escalate": True}
    assert _case("triage_escalates").validator(always_high)[0]
    assert not _case("triage_routine").validator(always_high)[0]


GOOD_BRIEF = {
    "goal": "Stop closed results showing twice.",
    "files": [
        "frontend/src/workbench/RecentActivity.tsx",
        "frontend/src/workbench/RecentActivity.test.tsx",
    ],
    "constraints": ["Do not touch the backend."],
    "done_when": "frontend/src/workbench/RecentActivity.test.tsx passes",
}


def test_a_faithful_briefing_passes() -> None:
    assert _case("briefing").validator(dict(GOOD_BRIEF)) == (True, "")


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (
            {"files": GOOD_BRIEF["files"] + ["aios/api/main.py"]},
            "files must be exactly",
        ),
        ({"files": GOOD_BRIEF["files"][:1]}, "files must be exactly"),
        (
            {"constraints": ["Keep it small."]},
            "constraint (not the backend) was dropped",
        ),
        ({"done_when": "when it works"}, "must name the test"),
        ({"goal": ""}, "goal must be non-empty"),
    ],
)
def test_an_unfaithful_briefing_is_refused(change, why) -> None:
    ok, reason = _case("briefing").validator({**GOOD_BRIEF, **change})
    assert not ok and why in reason


def test_a_briefing_that_repeats_the_key_fails() -> None:
    from aios.domain.local_workforce import qualifier as q

    class Leaky(FakeLLMClient):
        def complete(self, prompt, *, system=None, json_mode=False):
            if "Prepare a briefing" in prompt:
                import json as _json

                return _json.dumps(
                    {**GOOD_BRIEF, "goal": f"Fix it; key {q._BRIEFING_KEY}"}
                )
            return super().complete(prompt, system=system, json_mode=json_mode)

    res = QualificationSuite(Leaky()).run()
    briefing = next(t for t in res.test_results if t.test_id == "briefing")
    assert not briefing.passed and not res.passed


def test_the_briefing_case_is_the_clerks_readme_step_three() -> None:
    from aios.application.local_workforce.qualification_evidence import (
        TEST_ID_TO_JOB_PROFILE,
    )
    from aios.domain.local_workforce.contracts import LocalJobProfile

    assert TEST_ID_TO_JOB_PROFILE["briefing"] is LocalJobProfile.PREPARE_BRIEFING
    assert TEST_ID_TO_JOB_PROFILE["triage_escalates"] is LocalJobProfile.TRIAGE
    assert TEST_ID_TO_JOB_PROFILE["triage_routine"] is LocalJobProfile.TRIAGE
