"""Tests for the Structured Local Clerical Runtime."""
import json
import pytest
from datetime import datetime, timezone

from aios.core.llm import LLMError
from aios.domain.local_workforce.contracts import LocalJobRequest, LocalJobProfile
from aios.domain.local_workforce.validation import ValidationPipeline, ValidationError
from aios.domain.local_workforce.runtime import StructuredClericalRuntime


class FakeLLMClient:
    def __init__(self, responses, exception=None):
        self.responses = responses
        self.exception = exception
        self.call_count = 0
        
    def complete(self, prompt: str, *, system: str = None, json_mode: bool = False) -> str:
        if self.exception:
            raise self.exception
        resp = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return resp


@pytest.fixture
def sample_request():
    return LocalJobRequest(
        job_id="job-123",
        job_profile=LocalJobProfile.EXTRACT,
        input_schema_version="1.0",
        evidence_references=frozenset(["ev-1", "ev-2"]),
        redacted_payload="Some log data here",
        token_budget=1000,
        deadline=datetime.now(timezone.utc),
        required_output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "related_id": {"type": "string"},
                "items": {"type": "array"}
            },
            "required": ["summary"]
        }
    )


def test_validation_pipeline_success(sample_request):
    pipeline = ValidationPipeline(sample_request)
    raw = '{"summary": "A log summary", "related_id": "ev-1", "items": []}'
    
    data, unsupported = pipeline.validate(raw)
    assert data["summary"] == "A log summary"
    assert data["related_id"] == "ev-1"


def test_validation_pipeline_invalid_json(sample_request):
    pipeline = ValidationPipeline(sample_request)
    raw = '{summary": bad json}'
    
    with pytest.raises(ValidationError, match="Invalid JSON"):
        pipeline.validate(raw)


def test_validation_pipeline_missing_required(sample_request):
    pipeline = ValidationPipeline(sample_request)
    raw = '{"related_id": "ev-1"}'  # missing 'summary'
    
    with pytest.raises(ValidationError, match="Missing required field"):
        pipeline.validate(raw)


def test_validation_pipeline_invented_id(sample_request):
    pipeline = ValidationPipeline(sample_request)
    # ev-99 is not in the evidence_references frozenset
    raw = '{"summary": "hello", "related_id": "ev-99"}'
    
    with pytest.raises(ValidationError, match="Invented identifier"):
        pipeline.validate(raw)


def test_validation_pipeline_forbidden_field(sample_request):
    pipeline = ValidationPipeline(sample_request)
    raw = '{"summary": "hello", "tool_calls": []}'
    
    with pytest.raises(ValidationError, match="Forbidden field"):
        pipeline.validate(raw)


def test_runtime_successful_execution(sample_request):
    client = FakeLLMClient(['{"summary": "All good", "related_id": "ev-2"}'])
    runtime = StructuredClericalRuntime(client)
    
    result = runtime.execute_job(sample_request)
    assert result.status == "completed"
    assert result.schema_valid is True
    assert result.structured_output["summary"] == "All good"


def test_runtime_retries_and_recovers(sample_request):
    # Fails twice (bad json, missing field), then succeeds
    client = FakeLLMClient([
        '{bad json',
        '{"related_id": "ev-1"}',  # missing summary
        '{"summary": "recovered", "related_id": "ev-1"}'
    ])
    runtime = StructuredClericalRuntime(client)
    
    result = runtime.execute_job(sample_request)
    assert result.status == "completed"
    assert result.structured_output["summary"] == "recovered"
    assert client.call_count == 3


def test_runtime_rejects_after_max_retries(sample_request):
    # Fails continually
    client = FakeLLMClient(['{bad json'] * 5)
    runtime = StructuredClericalRuntime(client)
    
    result = runtime.execute_job(sample_request)
    assert result.status == "rejected"
    assert result.schema_valid is False
    assert client.call_count == 3  # Max retries is 3


def test_runtime_handles_llm_error(sample_request):
    client = FakeLLMClient([], exception=LLMError("Ollama is down"))
    runtime = StructuredClericalRuntime(client)
    
    result = runtime.execute_job(sample_request)
    assert result.status == "timeout"
    assert "Ollama is down" in result.failure_reason
