"""Caste profiles for temporary Council workers.

The caste layer is an adapter over ``MissionContract``. It never grants new
authority: applying a caste only narrows allowed tools, adds explicit forbiddens,
lowers budgets, and records evidence requirements for auditing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aios.runtime.contracts import MissionContract

CasteName = Literal["forager", "builder", "scout", "soldier", "nurse"]


@dataclass(frozen=True)
class CasteProfile:
    name: CasteName
    purpose: str
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    allowed_file_scope: str
    timeout_seconds: int
    max_steps: int
    verification_required: bool
    verification_requirements: tuple[str, ...]
    evidence_output: tuple[str, ...]
    forbidden_files: tuple[str, ...] = ()
    requires_approval: bool = True


_COMMON_FORBIDDEN_FILES = (
    ".env",
    ".env.*",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
    "aios/security/",
)


CASTE_PROFILES: dict[CasteName, CasteProfile] = {
    "forager": CasteProfile(
        name="forager",
        purpose="research and read-only discovery",
        allowed_tools=("request_plan", "read_file"),
        forbidden_tools=(
            "write_file",
            "run_command",
            "request_change",
            "request_approval",
        ),
        allowed_file_scope="read only within allowed_files",
        timeout_seconds=180,
        max_steps=8,
        verification_required=False,
        verification_requirements=("structured evidence summary",),
        evidence_output=("summary", "files_read", "evidence", "open_questions"),
    ),
    "builder": CasteProfile(
        name="builder",
        purpose="scoped edits under contract and verifier",
        allowed_tools=(
            "request_plan",
            "read_file",
            "write_file",
            "run_command",
            "request_change",
        ),
        forbidden_tools=("request_approval",),
        allowed_file_scope="writes only to allowed_files",
        timeout_seconds=600,
        max_steps=18,
        verification_required=True,
        verification_requirements=("verification_commands", "diff evidence"),
        evidence_output=(
            "summary",
            "files_touched",
            "diff",
            "verification_result",
            "rollback_id",
        ),
    ),
    "scout": CasteProfile(
        name="scout",
        purpose="tests and verification",
        allowed_tools=("request_plan", "read_file", "run_command"),
        forbidden_tools=("write_file", "request_change", "request_approval"),
        allowed_file_scope="read only; run only declared verification_commands",
        timeout_seconds=300,
        max_steps=12,
        verification_required=True,
        verification_requirements=("verification_commands", "test evidence"),
        evidence_output=("summary", "verification_result", "commands_run", "failures"),
    ),
    "soldier": CasteProfile(
        name="soldier",
        purpose="security inspection",
        allowed_tools=("request_plan", "read_file"),
        forbidden_tools=("write_file", "run_command", "request_change", "request_approval"),
        allowed_file_scope="read only within allowed_files; protected core remains guarded",
        timeout_seconds=240,
        max_steps=10,
        verification_required=False,
        verification_requirements=("security findings evidence",),
        evidence_output=("summary", "security_findings", "evidence", "risk_after"),
    ),
    "nurse": CasteProfile(
        name="nurse",
        purpose="debugging and failure diagnosis",
        allowed_tools=("request_plan", "read_file", "run_command"),
        forbidden_tools=("write_file", "request_change", "request_approval"),
        allowed_file_scope="read only plus declared diagnostic verification_commands",
        timeout_seconds=360,
        max_steps=14,
        verification_required=False,
        verification_requirements=("diagnostic evidence",),
        evidence_output=("summary", "diagnosis", "commands_run", "next_recommendation"),
    ),
}


def profile_for_caste(caste: str) -> CasteProfile:
    key = caste.strip().lower().replace("-", "_")
    if key not in CASTE_PROFILES:
        raise ValueError(f"unknown worker caste: {caste}")
    return CASTE_PROFILES[key]  # type: ignore[index]


def caste_from_contract(contract: MissionContract) -> CasteProfile | None:
    raw = contract.metadata.get("caste") or contract.metadata.get("worker_caste")
    if isinstance(raw, str) and raw.strip():
        return profile_for_caste(raw)

    worker_type = contract.worker_type.strip().lower().replace("-", "_")
    for name, profile in CASTE_PROFILES.items():
        if worker_type == name or worker_type.startswith(f"{name}_"):
            return profile
    return None


def apply_caste_profile(
    contract: MissionContract,
    caste: str | CasteProfile | None = None,
) -> MissionContract:
    """Return a contract narrowed by the selected caste profile."""

    profile = caste if isinstance(caste, CasteProfile) else None
    if profile is None:
        profile = profile_for_caste(caste) if isinstance(caste, str) else caste_from_contract(contract)
    if profile is None:
        return contract

    allowed_tools = [
        tool for tool in contract.allowed_tools if tool in profile.allowed_tools
    ]
    forbidden_tools = _unique([*contract.forbidden_tools, *profile.forbidden_tools])
    forbidden_files = _unique(
        [*contract.forbidden_files, *_COMMON_FORBIDDEN_FILES, *profile.forbidden_files]
    )
    required_output = _unique([*contract.required_output, *profile.evidence_output])
    metadata = dict(contract.metadata)
    metadata.update(
        {
            "caste": profile.name,
            "caste_purpose": profile.purpose,
            "caste_allowed_file_scope": profile.allowed_file_scope,
            "caste_allowed_tools": list(profile.allowed_tools),
            "caste_forbidden_tools": list(profile.forbidden_tools),
            "caste_verification_required": profile.verification_required,
            "caste_verification_requirements": list(profile.verification_requirements),
            "caste_evidence_output": list(profile.evidence_output),
            "worker_lifecycle": "ephemeral_single_task",
        }
    )
    if profile.verification_required and not contract.verification_commands:
        metadata["caste_verification_missing"] = True

    return contract.model_copy(
        update={
            "allowed_tools": allowed_tools,
            "forbidden_tools": forbidden_tools,
            "forbidden_files": forbidden_files,
            "timeout_seconds": min(contract.timeout_seconds, profile.timeout_seconds),
            "max_steps": min(contract.max_steps, profile.max_steps),
            "requires_approval": contract.requires_approval or profile.requires_approval,
            "required_output": required_output,
            "metadata": metadata,
        }
    )


def caste_contract_issues(contract: MissionContract) -> list[str]:
    """Report caste/profile drift without executing the contract."""

    profile = caste_from_contract(contract)
    if profile is None:
        return []
    issues: list[str] = []
    extra_tools = sorted(set(contract.allowed_tools) - set(profile.allowed_tools))
    if extra_tools:
        issues.append(f"tools exceed {profile.name} caste: {', '.join(extra_tools)}")
    forbidden_enabled = sorted(set(contract.allowed_tools) & set(contract.forbidden_tools))
    if forbidden_enabled:
        issues.append(f"forbidden tools still enabled: {', '.join(forbidden_enabled)}")
    if profile.verification_required and not contract.verification_commands:
        issues.append(f"{profile.name} caste requires verification_commands")
    return issues


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


__all__ = [
    "CASTE_PROFILES",
    "CasteName",
    "CasteProfile",
    "apply_caste_profile",
    "caste_contract_issues",
    "caste_from_contract",
    "profile_for_caste",
]
