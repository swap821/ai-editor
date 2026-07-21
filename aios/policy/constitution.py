"""Truthful constitution snapshot for the governed runtime.

The constitution is not a new authority path. It is a typed, inspectable facade
over the existing security, router, budget, and caste defaults so higher-level
v10 flows can reason about policy without duplicating or weakening it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from aios import config
from aios.runtime.castes import CASTE_PROFILES, CasteProfile
from aios.runtime.resource_ecology import ResourceMode, normalize_resource_mode


FROZEN_PATH_PREFIXES: tuple[str, ...] = ("aios/security/",)


@dataclass(frozen=True)
class CasteConstitution:
    name: str
    purpose: str
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    allowed_file_scope: str
    timeout_seconds: int
    max_steps: int
    verification_required: bool
    verification_requirements: tuple[str, ...]
    evidence_output: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    requires_approval: bool

    @classmethod
    def from_profile(cls, profile: CasteProfile) -> CasteConstitution:
        return cls(
            name=profile.name,
            purpose=profile.purpose,
            allowed_tools=profile.allowed_tools,
            forbidden_tools=profile.forbidden_tools,
            allowed_file_scope=profile.allowed_file_scope,
            timeout_seconds=profile.timeout_seconds,
            max_steps=profile.max_steps,
            verification_required=profile.verification_required,
            verification_requirements=profile.verification_requirements,
            evidence_output=profile.evidence_output,
            forbidden_files=profile.forbidden_files,
            requires_approval=profile.requires_approval,
        )


@dataclass(frozen=True)
class Constitution:
    frozen_path_prefixes: tuple[str, ...]
    scope_roots: tuple[str, ...]
    router_cloud_tasks: tuple[str, ...]
    router_max_cost: str
    router_prefer_local: bool
    router_llm_pick: bool
    resource_mode: ResourceMode
    earned_autonomy_enabled: bool
    earned_autonomy_min_successes: int
    plan_stage_enabled: bool
    policy_engine_enabled: bool
    castes: Mapping[str, CasteConstitution]

    def is_frozen_path(self, path: str | Path) -> bool:
        normalized = normalize_repo_path(path)
        for prefix in self.frozen_path_prefixes:
            frozen = prefix.rstrip("/")
            if normalized == frozen or normalized.startswith(f"{frozen}/"):
                return True
        return False

    def cloud_task_allowed(self, task: str) -> bool:
        return task.strip().lower() in self.router_cloud_tasks

    def caste(self, name: str) -> CasteConstitution | None:
        return self.castes.get(name.strip().lower().replace("-", "_"))


def build_constitution(
    *,
    router_cloud_tasks: tuple[str, ...] | None = None,
    router_max_cost: str | None = None,
    resource_mode: str | None = None,
) -> Constitution:
    """Build a current-process policy snapshot from live config.

    Optional arguments are test seams only; production callers should use the
    config-backed defaults so docs/UI can show what the runtime will actually do.
    """

    castes = {
        name: CasteConstitution.from_profile(profile)
        for name, profile in CASTE_PROFILES.items()
    }
    return Constitution(
        frozen_path_prefixes=FROZEN_PATH_PREFIXES,
        scope_roots=tuple(str(root) for root in config.SCOPE_ROOTS),
        router_cloud_tasks=(
            tuple(t.strip().lower() for t in router_cloud_tasks)
            if router_cloud_tasks is not None
            else config.ROUTER_CLOUD_TASKS
        ),
        router_max_cost=(
            router_max_cost.strip().lower()
            if router_max_cost is not None
            else config.ROUTER_MAX_COST
        ),
        router_prefer_local=config.ROUTER_PREFER_LOCAL,
        router_llm_pick=config.ROUTER_LLM_PICK,
        resource_mode=normalize_resource_mode(
            resource_mode if resource_mode is not None else config.RESOURCE_MODE
        ),
        earned_autonomy_enabled=config.EARNED_AUTONOMY_ENABLED,
        earned_autonomy_min_successes=config.EARNED_AUTONOMY_MIN_SUCCESSES,
        plan_stage_enabled=config.PLAN_STAGE_ENABLED,
        policy_engine_enabled=config.POLICY_ENGINE,
        castes=MappingProxyType(castes),
    )


def normalize_repo_path(path: str | Path) -> str:
    raw = str(path)
    try:
        resolved = Path(raw).resolve()
        raw = resolved.relative_to(config.PROJECT_ROOT).as_posix()
    except (OSError, RuntimeError, ValueError):
        pass
    return raw.replace("\\", "/").lstrip("./")


__all__ = [
    "CasteConstitution",
    "Constitution",
    "FROZEN_PATH_PREFIXES",
    "build_constitution",
    "normalize_repo_path",
]
