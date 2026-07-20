import hashlib
import hmac
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from aios import config
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
        self._signing_key = self._resolve_signing_key()
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS verification_results (
                        verification_id TEXT PRIMARY KEY,
                        mission_id TEXT NOT NULL,
                        action_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        payload_digest TEXT NOT NULL,
                        integrity_proof TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                # Migration check for existing SQLite tables
                existing_cols = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(verification_results)").fetchall()
                }
                if "payload_digest" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE verification_results ADD COLUMN payload_digest TEXT NOT NULL DEFAULT ''"
                    )
                if "integrity_proof" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE verification_results ADD COLUMN integrity_proof TEXT NOT NULL DEFAULT ''"
                    )
                if "created_at" not in existing_cols:
                    conn.execute(
                        "ALTER TABLE verification_results ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
                    )

    _INSECURE_DEFAULT_KEYS: frozenset[str] = frozenset({
        "aios-authority-verification-key-v1",
        "aios-authority-key",
        "changeme",
        "secret",
        "default",
    })

    @staticmethod
    def _resolve_signing_key() -> str:
        """Return the configured signing key or raise RuntimeError if insecure."""
        import os
        key = (
            os.environ.get("AIOS_VERIFICATION_AUTHORITY_KEY")
            or os.environ.get("VERIFICATION_AUTHORITY_KEY")
            or getattr(config, "VERIFICATION_AUTHORITY_KEY", "")
        )
        is_test = os.environ.get("AIOS_ENV", "").lower() in ("test", "testing", "ci")
        allow_insecure = bool(os.environ.get("AIOS_TEST_SIGNING_KEYS_ALLOWED", ""))
        if not key:
            if is_test or allow_insecure:
                return "test-verification-signing-key-placeholder-safe"
            raise RuntimeError(
                "AIOS_VERIFICATION_AUTHORITY_KEY must be set to a secret of at least "
                "32 characters. The verification integrity chain is insecure without it."
            )
        if key in VerificationAuthority._INSECURE_DEFAULT_KEYS:
            raise RuntimeError(
                f"AIOS_VERIFICATION_AUTHORITY_KEY is set to a known insecure default "
                f"({key!r}). Provide a unique secret."
            )
        if len(key) < 32 and not (is_test or allow_insecure):
            raise RuntimeError(
                "AIOS_VERIFICATION_AUTHORITY_KEY must be at least 32 characters."
            )
        return key

    def _compute_integrity_proof(
        self, verification_id: str, payload_digest: str, created_at: str
    ) -> str:
        import hmac as _hmac
        material = f"{verification_id}:{payload_digest}:{created_at}"
        return _hmac.new(
            self._signing_key.encode("utf-8"), material.encode("utf-8"), hashlib.sha256
        ).hexdigest()

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
        """Persist one immutable, tamper-evident verification result."""
        existing = self.get(result.verification_id)
        if existing is not None:
            if existing.model_dump(mode="json") == result.model_dump(mode="json"):
                return
            raise ValueError(
                f"Verification record {result.verification_id} is immutable and cannot be overwritten"
            )

        self._results[result.verification_id] = result
        if self.database_path is not None:
            payload = json.dumps(result.model_dump(mode="json"), sort_keys=True)
            payload_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            created_at = result.observed_at or _utc_now()
            integrity_proof = self._compute_integrity_proof(
                result.verification_id, payload_digest, created_at
            )

            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO verification_results (
                        verification_id, mission_id, action_id, payload_json, payload_digest, integrity_proof, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.verification_id,
                        result.mission_id,
                        result.action_id,
                        payload,
                        payload_digest,
                        integrity_proof,
                        created_at,
                    ),
                )

    def get(self, verification_id: str) -> VerificationResult | None:
        """Return the verified, tamper-checked verification result."""
        if self.database_path is not None:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT mission_id, action_id, payload_json, payload_digest, integrity_proof, created_at FROM verification_results WHERE verification_id = ?",
                    (verification_id,),
                ).fetchone()
            if row is not None:
                indexed_mission_id = row["mission_id"]
                indexed_action_id = row["action_id"]
                payload_json = row["payload_json"]
                stored_digest = row["payload_digest"]
                stored_proof = row["integrity_proof"]
                created_at = row["created_at"]

                # Integrity checks
                if not stored_digest or not stored_proof:
                    return None  # Unsigned legacy row quarantined
                actual_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                if stored_digest != actual_digest:
                    return None  # Tamper detected: payload digest mismatch

                actual_proof = self._compute_integrity_proof(
                    verification_id, stored_digest, created_at
                )
                if not hmac.compare_digest(stored_proof, actual_proof):
                    return None  # Tamper detected: integrity proof mismatch

                result = VerificationResult.model_validate(json.loads(payload_json))

                # Blocker 14 fix: bind signed payload fields back against indexed columns.
                # An attacker who changes the indexed column but not the payload digest
                # will be caught here.
                if result.mission_id != indexed_mission_id:
                    return None  # Tamper detected: indexed mission_id was changed
                if result.action_id != indexed_action_id:
                    return None  # Tamper detected: indexed action_id was changed

                self._results[verification_id] = result
                return result
            return None
        return self._results.get(verification_id)

    def list_results_for_mission(self, mission_id: str) -> tuple[VerificationResult, ...]:
        """Return all valid, authority-verified results for a specific mission."""
        if self.database_path is not None:
            with self._connection() as conn:
                rows = conn.execute(
                    "SELECT verification_id FROM verification_results WHERE mission_id = ? ORDER BY verification_id",
                    (mission_id,),
                ).fetchall()
            results: list[VerificationResult] = []
            for row in rows:
                v = self.get(row["verification_id"])
                if v is not None:
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
