"""Domain models for the Curated Local Workforce (clerical model tier)."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict


class LocalJobProfile(str, Enum):
    """Specific clerical jobs the local workforce is allowed to perform.

    Slice 32 adds the four profiles named in the GAGOS Completion Plan that
    had no prior equivalent here (`VALIDATE_STRUCTURE`, `SUMMARISE_
    DISAGREEMENT`, `EXPLAIN_ROUTE`, `CHECK_CONTEXT_COMPLETENESS`). The
    plan's `CLASSIFY_REQUEST`/`PREPARE_FRONTIER_BRIEF`/`TRIAGE_FAILURE` are
    deliberately not added as separate members -- they are the same job as
    the existing `CLASSIFY`/`PREPARE_BRIEFING`/`TRIAGE`, and adding a near-
    duplicate name for the same concept would fragment this enum the way
    Slice 30 found three competing "gateway" implementations already
    fragmenting that concept.
    """

    CLASSIFY = "classify"
    EXTRACT = "extract"
    SUMMARISE = "summarise"
    CLUSTER = "cluster"
    TRIAGE = "triage"
    FORMAT_REPORT = "format_report"
    PREPARE_BRIEFING = "prepare_briefing"
    SELECT_SKILL = "select_skill"
    PARAMETERISE_SKILL = "parameterise_skill"
    VALIDATE_STRUCTURE = "validate_structure"
    SUMMARISE_DISAGREEMENT = "summarise_disagreement"
    EXPLAIN_ROUTE = "explain_route"
    CHECK_CONTEXT_COMPLETENESS = "check_context_completeness"


class LocalWorkerModel(BaseModel):
    """A registered local model capable of clerical work."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    provider: str
    family: str
    parameter_size: str
    quantization: str
    installed: bool
    operator_approved: bool
    health: Literal["healthy", "degraded", "failing", "unknown"]
    admission_status: Literal["pending", "approved", "rejected"]
    admission_reason: str | None = None
    max_context: int
    max_output: int
    max_parallelism: int
    allowed_job_profiles: frozenset[LocalJobProfile]
    last_success: datetime | None = None
    failure_count: int = 0
    metadata_confidence: Literal["verified", "inferred", "unknown"]


class LocalJobRequest(BaseModel):
    """A request for a specific clerical task."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    job_profile: LocalJobProfile
    input_schema_version: str
    evidence_references: frozenset[str]
    redacted_payload: str
    token_budget: int
    deadline: datetime
    required_output_schema: Mapping[str, Any]


class LocalJobResult(BaseModel):
    """The outcome of a clerical task.

    Hard restriction: The local clerk returns structured advisory data only.
    No shell, no filesystem tools, no Git, no network, no state mutation.
    """

    model_config = ConfigDict(frozen=True)

    job_id: str
    model_id: str
    structured_output: Mapping[str, Any] | None
    schema_valid: bool
    evidence_references_preserved: bool
    unsupported_claims: Sequence[str]
    latency: float
    status: Literal["completed", "failed", "timeout", "rejected"]
    failure_reason: str | None = None


class LocalJobRequestRecord(BaseModel):
    """Durable record of a local job request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    mission_id: str | None = None
    skill_id: str | None = None
    skill_version: int | None = None
    job_profile: str
    input_schema_version: str
    qualification_suite_version: str = "r15-v2"
    model_allowlist: tuple[str, ...] = ()
    requested_model: str
    evidence_references: tuple[str, ...] = ()
    redacted_input_digest: str
    token_budget: int
    deadline: str
    created_at: str


class LocalModelCallRecord(BaseModel):
    """Durable record of an individual local model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    local_model_call_id: str
    local_job_id: str
    provider: str = "ollama"
    exact_model_id: str
    model_digest_version: str | None = None
    qualification_version: str = "r15-v2"
    admission_record_id: str | None = None
    request_digest: str
    response_digest: str
    token_limits: int
    measured_latency: float
    start_time: str
    end_time: str
    status: str
    failure_reason: str | None = None


class LocalJobResultRecord(BaseModel):
    """Durable record of a local job result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    local_job_id: str
    local_model_call_id: str
    schema_version: str = "1.0"
    structured_result_digest: str
    schema_valid: bool
    evidence_references_preserved: bool
    unsupported_claims: tuple[str, ...] = ()
    status: str
    failure_reason: str | None = None
