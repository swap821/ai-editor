"""Versioned, structured messages for the isolated Executor Service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutorCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    action_digest: str
    mission_contract_digest: str
    expires_at: str


class MountPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_only: bool = True
    read_only_root: bool = True
    writable_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()


class NetworkPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["none", "allowlist"] = "none"
    allowed_hosts: tuple[str, ...] = ()
    allowed_methods: tuple[str, ...] = ()


class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: int = Field(default=30, ge=1, le=86_400)
    max_output_bytes: int = Field(default=1_048_576, ge=1, le=100_000_000)
    cpu_budget: float = Field(default=1.0, gt=0, le=64)
    memory_budget_mb: int = Field(default=512, ge=64, le=131_072)
    pids_limit: int = Field(default=128, ge=16, le=100_000)
    temporary_directory_bytes: int = Field(default=64 * 1024 * 1024, ge=1)


class ExecutorJob(BaseModel):
    """A job contains argv, never an opaque shell command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1"
    job_id: str
    mission_contract_digest: str
    capability: ExecutorCapability
    image: str
    argv: tuple[str, ...] = ()
    worker_entrypoint: tuple[str, ...] = ()
    workspace_snapshot: str
    mount_policy: MountPolicy = Field(default_factory=MountPolicy)
    environment_allowlist: tuple[str, ...] = ()
    environment: dict[str, str] = Field(default_factory=dict)
    network_policy: NetworkPolicy = Field(default_factory=NetworkPolicy)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    verification_expectation: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: _utc_now())

    @model_validator(mode="after")
    def validate_command_shape(self) -> "ExecutorJob":
        if bool(self.argv) == bool(self.worker_entrypoint):
            raise ValueError("exactly one of argv or worker_entrypoint is required")
        selected = self.argv or self.worker_entrypoint
        if any(
            not part or any(char in part for char in ";&|<>`\r\n\x00")
            for part in selected
        ):
            raise ValueError("executor arguments must be non-empty and shell-free")
        if not self.mount_policy.workspace_only:
            raise ValueError("executor jobs may mount only the staged workspace")
        unknown = set(self.environment) - set(self.environment_allowlist)
        if unknown:
            raise ValueError("environment contains names outside its allowlist")
        if self.network_policy.mode == "none" and self.network_policy.allowed_hosts:
            raise ValueError("network hosts are invalid when network mode is none")
        if self.mission_contract_digest != self.capability.mission_contract_digest:
            raise ValueError("capability is bound to a different mission contract")
        return self


class ExecutorResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    status: Literal["completed", "failed", "timeout", "unavailable", "killed"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    output_truncated: bool = False
    isolation_verified: bool = False
    environment_digest: str | None = None
    started_at: str = Field(default_factory=lambda: _utc_now())
    ended_at: str = Field(default_factory=lambda: _utc_now())
    reason: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "ExecutorCapability",
    "ExecutorJob",
    "ExecutorResult",
    "MountPolicy",
    "NetworkPolicy",
    "ResourceLimits",
]
