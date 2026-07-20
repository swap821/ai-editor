from aios.core.llm import LLMError
from aios.domain.local_workforce.qualifier import QualificationSuite
from aios.domain.local_workforce.admission import HardwareAdmission, AdmissionContext


class FakeLLMClient:
    def __init__(self, mode: str = "pass"):
        self.mode = mode

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        if self.mode == "pass":
            if "one field result" in prompt:
                return '{"result": "ok"}'
            if "reference identifier" in prompt:
                return '{"reference_id": "REF-15"}'
            if "Extract the error code" in prompt:
                return '{"error_code": "connection_refused", "message": "port unavailable"}'
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
    assert res.suite_version == "r15-v2"
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
