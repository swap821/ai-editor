"""Reconciliation pass, item 3: LocalWorkforceService.run_advisory_job() now
durably records every real job's provenance via LocalWorkforceProvenanceStore
(Slice 33) -- closing organ 38's exact stated gap ("the real local workforce
flow never writes to it").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from aios.application.local_workforce.provenance import get_clerk_job_provenance
from aios.application.local_workforce.service import LocalWorkforceService
from aios.domain.local_workforce.contracts import (
    LocalJobProfile,
    LocalJobRequest,
    LocalWorkerModel,
)
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.infrastructure.local_workforce.sqlite_store import (
    LocalWorkforceProvenanceStore,
)


def _admitted_model() -> LocalWorkerModel:
    return LocalWorkerModel(
        model_id="granite3.2:2b",
        provider="ollama",
        family="granite",
        parameter_size="2B",
        quantization="q4_K_M",
        installed=True,
        operator_approved=True,
        health="healthy",
        admission_status="approved",
        admission_reason="Passed",
        max_context=131072,
        max_output=4096,
        max_parallelism=1,
        allowed_job_profiles=frozenset({LocalJobProfile.SELECT_SKILL}),
        metadata_confidence="verified",
    )


def _request(job_id: str = "job-1") -> LocalJobRequest:
    return LocalJobRequest(
        job_id=job_id,
        job_profile=LocalJobProfile.SELECT_SKILL,
        input_schema_version="1.0",
        evidence_references=frozenset({"skill-1"}),
        redacted_payload="Evaluate skill applicability.",
        token_budget=128,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        required_output_schema={"applicable": "bool", "confidence": "float"},
    )


def _service_with(
    *, raw_output: str, provenance_store: LocalWorkforceProvenanceStore | None
) -> LocalWorkforceService:
    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.list_models.return_value = [_admitted_model()]
    llm = MagicMock()
    llm.complete.return_value = raw_output
    return LocalWorkforceService(
        registry=registry,
        ollama=llm,
        model_client_factory=lambda model_id: llm,
        provenance_store=provenance_store,
    )


def test_no_store_configured_is_a_safe_noop() -> None:
    """The pre-existing behaviour (no provenance_store) must be unchanged."""
    service = _service_with(
        raw_output='{"applicable": true, "confidence": 0.9}', provenance_store=None
    )

    result = service.run_advisory_job(_request())

    assert result.status == "completed"


def test_successful_job_is_durably_recorded(tmp_path: Path) -> None:
    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    service = _service_with(
        raw_output='{"applicable": true, "confidence": 0.9}', provenance_store=store
    )

    result = service.run_advisory_job(_request("job-success"))

    assert result.status == "completed"
    provenance = get_clerk_job_provenance(store, "job-success")
    assert provenance.request is not None
    assert provenance.request.requested_model == "granite3.2:2b"
    assert provenance.request.job_profile == LocalJobProfile.SELECT_SKILL.value
    assert len(provenance.model_calls) == 1
    assert provenance.model_calls[0].status == "completed"
    assert provenance.result is not None
    assert provenance.result.status == "completed"
    assert provenance.result.schema_valid is True


def test_rejected_job_with_no_admitted_model_is_still_recorded(
    tmp_path: Path,
) -> None:
    """Provenance must be honest about refusals too, not only successes."""
    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.list_models.return_value = []  # nothing admitted
    llm = MagicMock()
    service = LocalWorkforceService(
        registry=registry,
        ollama=llm,
        model_client_factory=lambda model_id: llm,
        provenance_store=store,
    )

    result = service.run_advisory_job(_request("job-rejected"))

    assert result.status == "rejected"
    provenance = get_clerk_job_provenance(store, "job-rejected")
    assert provenance.request is not None
    assert provenance.result is not None
    assert provenance.result.status == "rejected"
    assert (
        provenance.result.failure_reason
        == "No admitted healthy local model for profile"
    )


def test_schema_invalid_job_is_recorded_as_failed(tmp_path: Path) -> None:
    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    service = _service_with(
        raw_output='{"applicable": true}',  # missing required "confidence"
        provenance_store=store,
    )

    result = service.run_advisory_job(_request("job-bad-schema"))

    assert result.status == "failed"
    assert result.schema_valid is False
    provenance = get_clerk_job_provenance(store, "job-bad-schema")
    assert provenance.result is not None
    assert provenance.result.schema_valid is False
    assert provenance.result.status == "failed"


def test_two_jobs_do_not_collide_on_the_same_store(tmp_path: Path) -> None:
    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    service = _service_with(
        raw_output='{"applicable": true, "confidence": 0.9}', provenance_store=store
    )

    service.run_advisory_job(_request("job-a"))
    service.run_advisory_job(_request("job-b"))

    assert get_clerk_job_provenance(store, "job-a").request is not None
    assert get_clerk_job_provenance(store, "job-b").request is not None
