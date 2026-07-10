"""Run ledger construction and persistence for Council Runtime v0.1."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aios.core.verification_strength import (
    VerificationStrength,
    derive_strength,
    parse_test_counts,
)
from aios.runtime.backends import WorkerHandle
from aios.runtime.contracts import MissionContract, RunLedger, WorkerResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _verification_strength(results: Any) -> VerificationStrength:
    """Weakest-link verification strength across a mission's checks (fail-closed).

    Each entry is a ``run_command`` result dict (``command``/``returncode``/
    ``stdout``/``stderr``). Strength is COMMAND-AWARE (reused from the Phase 1
    taxonomy), so a check that merely prints "N passed" cannot read STRONG. The
    mission strength is the MINIMUM across checks — a failed, empty, unparseable,
    or non-test check reads ``NONE``, so one strong check cannot launder a weak
    sibling and a mission with any failed check is never STRONG. No checks at all
    → ``NONE`` (unverified).
    """
    if not isinstance(results, list) or not results:
        return VerificationStrength.NONE
    strengths: list[VerificationStrength] = []
    for entry in results:
        if not isinstance(entry, dict):
            return VerificationStrength.NONE
        raw_command = entry.get("command") or []
        command = (
            raw_command if isinstance(raw_command, str)
            else " ".join(str(part) for part in raw_command)
        )
        output = (entry.get("stdout") or "") + (entry.get("stderr") or "")
        passed_count, failed_count = parse_test_counts(output)
        strengths.append(
            derive_strength(
                passed=(entry.get("returncode") == 0),
                passed_count=passed_count,
                failed_count=failed_count,
                command=command,
            )
        )
    return min(strengths, default=VerificationStrength.NONE)


def build_run_ledger(
    *,
    contract: MissionContract,
    handle: WorkerHandle,
    result: WorkerResult,
    created_at: str,
) -> RunLedger:
    evidence: dict[str, Any] = dict(result.evidence)
    return RunLedger(
        mission_id=contract.mission_id,
        mission=contract.goal,
        risk_before=contract.risk_level,
        risk_after=result.risk_after,
        contract=contract,
        workers_created=[handle.worker_id],
        files_allowed=list(contract.allowed_files),
        files_touched=list(result.files_touched),
        blocked_attempts=list(evidence.get("blocked_attempts", [])),
        tool_calls=list(result.tool_calls),
        verification={
            "commands": evidence.get("verification", []),
            # The TYPED strength the King/operator approves on (Slice A1). Weakest
            # link, command-aware, fail-closed — see _verification_strength.
            "strength": _verification_strength(evidence.get("verification", [])).name,
        },
        snapshot_id=contract.snapshot_id,
        rollback_id=result.rollback_id,
        status=result.status,
        created_at=created_at,
        completed_at=result.ended_at or _utc_now(),
        evidence=evidence,
    )


class RunLedgerStore:
    """Persist one run ledger per mission under the runtime root."""

    def __init__(self, runtime_root: str | Path) -> None:
        from aios.runtime import _safe_resolve
        self.runtime_root = _safe_resolve(runtime_root)

    def path_for(self, mission_id: str) -> Path:
        base = (self.runtime_root / "missions").resolve()
        candidate = (base / mission_id).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            raise ValueError(f"Invalid mission_id escapes missions directory: {mission_id}")
        return candidate / "run_ledger.json"

    def write(self, ledger: RunLedger) -> Path:
        path = self.path_for(ledger.mission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")
        return path

    def read(self, mission_id: str) -> RunLedger:
        return RunLedger.model_validate_json(
            self.path_for(mission_id).read_text(encoding="utf-8")
        )


__all__ = ["RunLedgerStore", "build_run_ledger"]
