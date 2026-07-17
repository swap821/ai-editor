"""Domain models for the Curated Local Workforce (clerical model tier)."""
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict


class LocalJobProfile(str, Enum):
    """Specific clerical jobs the local workforce is allowed to perform."""
    CLASSIFY = "classify"
    EXTRACT = "extract"
    SUMMARISE = "summarise"
    CLUSTER = "cluster"
    TRIAGE = "triage"
    FORMAT_REPORT = "format_report"
    PREPARE_BRIEFING = "prepare_briefing"
    SELECT_SKILL = "select_skill"
    PARAMETERISE_SKILL = "parameterise_skill"


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
