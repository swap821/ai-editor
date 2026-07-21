"""Tests for the Local Workforce domain contracts."""
import pytest
from datetime import datetime, timezone

from aios.domain.local_workforce.contracts import (
    LocalJobProfile,
    LocalJobRequest,
    LocalJobResult,
    LocalWorkerModel,
)


def test_local_worker_model_immutability():
    """Ensure LocalWorkerModel is frozen."""
    model = LocalWorkerModel(
        model_id="qwen2.5:3b",
        provider="ollama",
        family="qwen",
        parameter_size="3B",
        quantization="q4_K_M",
        installed=True,
        operator_approved=True,
        health="healthy",
        admission_status="approved",
        max_context=8192,
        max_output=1500,
        max_parallelism=1,
        allowed_job_profiles=frozenset([LocalJobProfile.CLASSIFY]),
        metadata_confidence="verified",
    )
    
    with pytest.raises(Exception):
        model.installed = False


def test_local_job_result_contains_no_authority_fields():
    """Enforce the gate: no authority field exists in local job outputs.
    
    The local clerk returns structured advisory data only, with no ability
    to mutate state, issue capabilities, or authorize actions.
    """
    forbidden_fields = {
        "capability", 
        "token", 
        "mission_state", 
        "auth", 
        "promote",
        "command",
        "execute",
        "grant",
        "action"
    }
    
    result_fields = set(LocalJobResult.model_fields.keys())
    
    # Assert there is no intersection between the result fields and forbidden fields
    violations = result_fields.intersection(forbidden_fields)
    assert not violations, f"LocalJobResult contains forbidden authority fields: {violations}"
    
    # Assert that all fields are purely advisory
    expected_advisory_fields = {
        "job_id",
        "model_id",
        "structured_output",
        "schema_valid",
        "evidence_references_preserved",
        "unsupported_claims",
        "latency",
        "status",
        "failure_reason"
    }
    
    assert result_fields == expected_advisory_fields, "LocalJobResult contains unexpected fields that may imply authority."

