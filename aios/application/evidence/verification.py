"""Target-specific verification authority built on the existing strength rules."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from aios.application.evidence.authority import EvidenceAuthority
from aios.core.verification_strength import derive_strength
from aios.domain.evidence import (
    VerificationObservation,
    VerificationPlanV1,
    VerificationResult,
)
from aios.domain.verification import aggregate_strength, evidence_is_fresh


class VerificationAuthority:
    """Challenge results against a plan and canonical workspace identity."""

    def __init__(
        self,
        evidence: EvidenceAuthority | None = None,
        database_path: Path | str | None = None,
    ) -> None:
        self.evidence = evidence or EvidenceAuthority()
        self._results: dict[str, VerificationResult] = {}
        self.database_path = Path(database_path) if database_path else None
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS verification_results (
                        verification_id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        action_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )

    def verify(
        self,
        *,
        mission_id: str,
        action_id: str,
        worker_id: str,
        target: str,
        plan: VerificationPlanV1,
        workspace_digest: str,
        diff_digest: str,
        environment_digest: str,
        observation: VerificationObservation,
    ) -> VerificationResult:
        if plan.targets and target not in plan.targets:
            raise ValueError(f"verification target is not in plan: {target}")
        passed = observation.exit_code == 0
        strength = int(
            derive_strength(
                passed=passed,
                passed_count=observation.passed_count,
                failed_count=observation.failed_count,
                command=observation.command,
            )
        )
        output = observation.stdout + "\n" + observation.stderr
        output_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        evidence = self.evidence.record(
            mission_id=mission_id,
            action_id=action_id,
            worker_id=worker_id,
            evidence_type="test",
            source="verification_authority",
            content=output,
            environment_digest=environment_digest,
            tool_version=observation.tool_version,
            trust_level="verified" if passed else "failed",
            verification_strength=strength,
            metadata={"target": target, "command": observation.command},
        )
        result = VerificationResult(
            verification_id=f"verification-{uuid.uuid4().hex}",
            mission_id=mission_id,
            action_id=action_id,
            target=target,
            passed=passed,
            strength=strength,
            required_strength=plan.minimum_strength,
            evidence_ids=(evidence.evidence_id,),
            workspace_digest=workspace_digest,
            diff_digest=diff_digest,
            environment_digest=environment_digest,
            command=observation.command,
            output_digest=output_digest,
            tool_version=observation.tool_version,
            observed_at=observation.observed_at,
        )
        self.save(result)
        return result

    def save(self, result: VerificationResult) -> None:
        """Persist one verification result into memory and durable storage."""
        self._results[result.verification_id] = result
        if self.database_path is not None:
            payload = json.dumps(result.model_dump(mode="json"), sort_keys=True)
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO verification_results (verification_id, mission_id, action_id, payload_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(verification_id) DO UPDATE SET
                        payload_json = excluded.payload_json
                    """,
                    (result.verification_id, result.mission_id, result.action_id, payload),
                )

    def get(self, verification_id: str) -> VerificationResult | None:
        """Return the verification result held by this authority."""
        if verification_id in self._results:
            return self._results[verification_id]
        if self.database_path is not None:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT payload_json FROM verification_results WHERE verification_id = ?",
                    (verification_id,),
                ).fetchone()
            if row is not None:
                result = VerificationResult.model_validate(json.loads(row[0]))
                self._results[verification_id] = result
                return result
        return None

    def list_results_for_mission(self, mission_id: str) -> tuple[VerificationResult, ...]:
        """Return all verification results held for a specific mission."""
        if self.database_path is not None:
            with self._connection() as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM verification_results WHERE mission_id = ? ORDER BY verification_id",
                    (mission_id,),
                ).fetchall()
            results: list[VerificationResult] = []
            for row in rows:
                v = VerificationResult.model_validate(json.loads(row[0]))
                self._results[v.verification_id] = v
                results.append(v)
            return tuple(results)
        return tuple(r for r in self._results.values() if r.mission_id == mission_id)

    def is_authoritative(self, result: VerificationResult) -> bool:
        """Reject caller-forged result objects, even when their IDs look valid."""
        held = self.get(result.verification_id)
        if held is None:
            return False
        return held.model_dump(mode="json") == result.model_dump(mode="json")

    def is_current(
        self,
        result: VerificationResult,
        *,
        workspace_digest: str,
        diff_digest: str,
        now: str | None = None,
        freshness_seconds: int = 300,
    ) -> bool:
        return (
            result.workspace_digest == workspace_digest
            and result.diff_digest == diff_digest
            and evidence_is_fresh(
                result.observed_at,
                now=now or _utc_now(),
                freshness_seconds=freshness_seconds,
            )
        )

    def promotion_strength(self, results: list[VerificationResult]) -> int:
        return aggregate_strength(
            result.strength if result.meets_requirement else 0 for result in results
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self.database_path is None:
            raise RuntimeError("VerificationAuthority database_path is not configured")
        conn = sqlite3.connect(self.database_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = ["VerificationAuthority"]
