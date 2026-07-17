import pytest
from aios.core.llm import LLMError
from aios.domain.local_workforce.qualifier import QualificationSuite, QualificationResult
from aios.domain.local_workforce.admission import HardwareAdmission, AdmissionContext

class FakeLLMClient:
    def __init__(self, mode: str = "pass"):
        self.mode = mode
    
    def complete(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        if self.mode == "pass":
            if "Extract the error code" in prompt:
                return '{"error_code": "connection_refused", "message": "at port 8080", "log_id": "ABC-123"}'
            if "API key" in prompt:
                return '{"summary": "Found an API key"}'
            return '{"response": "ok"}'
        elif self.mode == "fail_schema":
            if "Extract the error code" in prompt:
                return '{"error_code": "connection_refused", "message": "at port 8080"}' # Missing log_id
            return '{"response": "ok"}'
        elif self.mode == "fail_secret":
            if "Extract the error code" in prompt:
                return '{"error_code": "connection_refused", "message": "at port 8080", "log_id": "ABC-123"}'
            if "API key" in prompt:
                return '{"summary": "The key is sk-live-1234"}'
            return '{"response": "ok"}'
        elif self.mode == "fail_timeout":
            raise LLMError("Timeout occurred")
        return "{}"

def test_hardware_admission_pass():
    hw = HardwareAdmission(min_cpu_count=1, max_concurrent_inferences=2)
    ctx = AdmissionContext(
        requested_context_size=8192,
        requested_output_size=2048,
        active_local_inference_count=0
    )
    res = hw.evaluate(ctx)
    assert res.admitted is True
    assert res.reason is None

def test_hardware_admission_fail_concurrency():
    hw = HardwareAdmission(min_cpu_count=1, max_concurrent_inferences=2)
    ctx = AdmissionContext(
        requested_context_size=8192,
        requested_output_size=2048,
        active_local_inference_count=2
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
