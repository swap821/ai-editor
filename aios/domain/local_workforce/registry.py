"""Durable registry for the Local Workforce (R15 Slice 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence

from aios.core.llm import OllamaClient
from aios.domain.local_workforce.contracts import LocalWorkerModel, LocalJobProfile
from aios.domain.local_workforce.qualifier import QUALIFICATION_SUITE_VERSION
from aios.memory.db import get_connection


class LocalWorkforceRegistry:
    """Manages the durable configuration of local clerical workers."""

    def __init__(self, ollama_client: OllamaClient | None = None) -> None:
        self._ollama = ollama_client or OllamaClient()

    def reconcile(self) -> None:
        """Discover installed Ollama models and register them if missing.

        Does not delete models that have been removed from Ollama, but sets
        `installed=False` to preserve operator approval and job assignments.
        """
        detailed_models = self._ollama.list_detailed_models()
        seen_ids = set()

        with get_connection() as conn:
            # Upsert discovered models
            for m in detailed_models:
                model_id = m.get("name")
                if not model_id:
                    continue
                seen_ids.add(model_id)
                details = m.get("details", {})

                # Check if it exists
                cursor = conn.execute(
                    "SELECT admission_status, artifact_digest, expires_at, "
                    "qualification_suite_version FROM local_worker_models "
                    "WHERE model_id = ?",
                    (model_id,),
                )
                existing = cursor.fetchone()

                if not existing:
                    # Insert new discovery
                    family = details.get("family", "unknown")
                    parameter_size = details.get("parameter_size", "unknown")
                    quantization = details.get("quantization_level", "unknown")

                    conn.execute(
                        """
                        INSERT INTO local_worker_models (
                            model_id, provider, family, parameter_size, quantization,
                            installed, operator_approved, health, admission_status,
                            max_context, max_output, max_parallelism, allowed_job_profiles_json,
                            metadata_confidence, model_version, artifact_digest,
                            qualification_suite_version, qualification_evidence_digest,
                            limitations_json, qualified_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            model_id,
                            "ollama",
                            family,
                            parameter_size,
                            quantization,
                            1,  # installed
                            0,  # operator_approved (default false)
                            "unknown",  # health
                            "pending",  # admission_status
                            8192,  # safe default context
                            2048,  # safe default output
                            1,  # safe default parallelism
                            "[]",  # no profiles allowed yet
                            "verified" if family != "unknown" else "inferred",
                            None,  # model_version
                            None,  # artifact_digest
                            None,  # qualification_suite_version
                            None,  # qualification_evidence_digest
                            "[]",  # limitations_json
                            None,  # qualified_at
                            None,  # expires_at
                        ),
                    )
                else:
                    # Model already known
                    status = existing[0]
                    saved_digest = existing[1]
                    expires_str = existing[2]
                    saved_suite = existing[3]

                    new_digest = m.get("digest")
                    suspend_reason = None

                    if status == "approved":
                        if saved_suite and saved_suite != QUALIFICATION_SUITE_VERSION:
                            # The 5th auto-suspend trigger. A pass recorded
                            # under an older suite is not proof against the
                            # current bar; without this, bumping the suite
                            # leaves every model approved forever on
                            # superseded evidence.
                            suspend_reason = (
                                f"Qualification suite changed "
                                f"({saved_suite} -> {QUALIFICATION_SUITE_VERSION})"
                            )
                        elif saved_digest and new_digest and saved_digest != new_digest:
                            suspend_reason = "Model artifact digest changed"
                        elif expires_str:
                            try:
                                dt = datetime.fromisoformat(
                                    expires_str.replace(" ", "T")
                                ).replace(tzinfo=timezone.utc)
                                if datetime.now(timezone.utc) > dt:
                                    suspend_reason = "Qualification evidence expired"
                            except ValueError:
                                pass

                    if suspend_reason:
                        conn.execute(
                            "UPDATE local_worker_models SET installed = 1, admission_status = 'suspended', admission_reason = ? WHERE model_id = ?",
                            (suspend_reason, model_id),
                        )
                    else:
                        conn.execute(
                            "UPDATE local_worker_models SET installed = 1 WHERE model_id = ?",
                            (model_id,),
                        )

            # Mark models not seen as uninstalled (preserve history) and suspend if approved
            if seen_ids:
                placeholders = ",".join("?" for _ in seen_ids)
                conn.execute(
                    f"UPDATE local_worker_models SET admission_status = 'suspended', admission_reason = 'Required runtime disappeared' WHERE admission_status = 'approved' AND model_id NOT IN ({placeholders})",
                    tuple(seen_ids),
                )
                conn.execute(
                    f"UPDATE local_worker_models SET installed = 0 WHERE model_id NOT IN ({placeholders})",
                    tuple(seen_ids),
                )
            else:
                conn.execute(
                    "UPDATE local_worker_models SET admission_status = 'suspended', admission_reason = 'Required runtime disappeared' WHERE admission_status = 'approved'"
                )
                conn.execute("UPDATE local_worker_models SET installed = 0")

            conn.commit()

    def get_model(self, model_id: str) -> LocalWorkerModel | None:
        """Retrieve a local model by ID."""
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM local_worker_models WHERE model_id = ?", (model_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def list_models(self) -> Sequence[LocalWorkerModel]:
        """Retrieve all local models, installed or historic."""
        models = []
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM local_worker_models ORDER BY model_id")
            for row in cursor.fetchall():
                models.append(self._row_to_model(row))
        return models

    def update_approval(self, model_id: str, approved: bool) -> None:
        """Update operator approval status."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE local_worker_models 
                SET operator_approved = ?
                WHERE model_id = ?
                """,
                (1 if approved else 0, model_id),
            )
            conn.commit()

    def update_admission(
        self, model_id: str, status: str, reason: str | None = None
    ) -> None:
        """Update the formal admission status after qualification."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE local_worker_models 
                SET admission_status = ?, admission_reason = ?
                WHERE model_id = ?
                """,
                (status, reason, model_id),
            )
            conn.commit()

    def update_profiles(self, model_id: str, profiles: set[LocalJobProfile]) -> None:
        """Update allowed job profiles."""
        profiles_list = [p.value for p in profiles]
        with get_connection() as conn:
            conn.execute(
                "UPDATE local_worker_models SET allowed_job_profiles_json = ? WHERE model_id = ?",
                (json.dumps(profiles_list), model_id),
            )
            conn.commit()

    def record_health(self, model_id: str, status: str, success: bool = True) -> None:
        """Record a health check or job outcome."""
        with get_connection() as conn:
            if success:
                conn.execute(
                    """
                    UPDATE local_worker_models 
                    SET health = ?, last_success = CURRENT_TIMESTAMP
                    WHERE model_id = ?
                    """,
                    (status, model_id),
                )
            else:
                # If health falls below threshold, suspend if it was approved
                if status == "failing":
                    conn.execute(
                        """
                        UPDATE local_worker_models 
                        SET health = ?, failure_count = failure_count + 1,
                            admission_status = CASE WHEN admission_status = 'approved' THEN 'suspended' ELSE admission_status END,
                            admission_reason = CASE WHEN admission_status = 'approved' THEN 'Health fell below threshold' ELSE admission_reason END
                        WHERE model_id = ?
                        """,
                        (status, model_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE local_worker_models 
                        SET health = ?, failure_count = failure_count + 1
                        WHERE model_id = ?
                        """,
                        (status, model_id),
                    )
            conn.commit()

    def record_passport(self, model: LocalWorkerModel) -> None:
        """Update passport details for an admitted model."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE local_worker_models 
                SET model_version = ?, artifact_digest = ?,
                    qualification_suite_version = ?, qualification_evidence_digest = ?,
                    limitations_json = ?, qualified_at = ?, expires_at = ?
                WHERE model_id = ?
                """,
                (
                    model.model_version,
                    model.artifact_digest,
                    model.qualification_suite_version,
                    model.qualification_evidence_digest,
                    json.dumps(model.limitations),
                    model.qualified_at.isoformat() if model.qualified_at else None,
                    model.expires_at.isoformat() if model.expires_at else None,
                    model.model_id,
                ),
            )
            conn.commit()

    def record_qualification(self, model_id: str, result: Any) -> None:
        """Persist the REAL QualificationResult a suite run produced.

        Organ 36's dispatcher must be able to see a FAILING qualification, so
        a failure is recorded exactly as faithfully as a pass. Before this,
        `qualify()` ran the suite, read `.passed`, and discarded the result --
        which left the dispatcher's call site with nothing real to pass, and
        it fabricated a perfect one instead.
        """
        with get_connection() as conn:
            conn.execute(
                "UPDATE local_worker_models SET qualification_result_json = ? "
                "WHERE model_id = ?",
                (result.model_dump_json(), model_id),
            )
            conn.commit()

    def get_qualification(self, model_id: str) -> Any | None:
        """The persisted QualificationResult, or None when the model has never
        been qualified.

        None is the honest answer for an unqualified model, and the dispatcher
        already treats it correctly -- it escalates to frontier rather than
        trusting a model that has not proven itself.
        """
        from aios.domain.local_workforce.qualifier import QualificationResult

        with get_connection() as conn:
            row = conn.execute(
                "SELECT qualification_result_json FROM local_worker_models "
                "WHERE model_id = ?",
                (model_id,),
            ).fetchone()
        if row is None:
            return None
        raw = (
            row[0]
            if not isinstance(row, dict)
            else row.get("qualification_result_json")
        )
        try:
            raw = row["qualification_result_json"]
        except (TypeError, IndexError, KeyError):
            pass
        if not raw:
            return None
        try:
            return QualificationResult.model_validate_json(raw)
        except Exception:
            # A malformed stored result is not evidence of anything. Fail
            # closed to "unqualified" rather than guessing.
            return None

    def suspend_passport(self, model_id: str, reason: str) -> None:
        """Suspend a model's passport."""
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE local_worker_models 
                SET admission_status = 'suspended', admission_reason = ?
                WHERE model_id = ?
                """,
                (reason, model_id),
            )
            conn.commit()

    def _row_to_model(self, row: dict[str, Any]) -> LocalWorkerModel:
        profiles_raw = json.loads(row["allowed_job_profiles_json"])
        profiles = frozenset(LocalJobProfile(p) for p in profiles_raw)

        # sqlite3.Row acts like a dict for key lookups but doesn't have .get()
        limitations_raw = json.loads(
            row["limitations_json"]
            if "limitations_json" in row.keys() and row["limitations_json"] is not None
            else "[]"
        )
        limitations = tuple(str(x) for x in limitations_raw)

        def parse_dt(val: str | None) -> datetime | None:
            if not val:
                return None
            try:
                return datetime.fromisoformat(val.replace(" ", "T")).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                return None

        last_success = parse_dt(row["last_success"])
        qualified_at = parse_dt(
            row["qualified_at"] if "qualified_at" in row.keys() else None
        )
        expires_at = parse_dt(row["expires_at"] if "expires_at" in row.keys() else None)

        return LocalWorkerModel(
            model_id=row["model_id"],
            provider=row["provider"],
            family=row["family"],
            parameter_size=row["parameter_size"],
            quantization=row["quantization"],
            installed=bool(row["installed"]),
            operator_approved=bool(row["operator_approved"]),
            health=row["health"],
            admission_status=row["admission_status"],
            admission_reason=row["admission_reason"],
            max_context=row["max_context"],
            max_output=row["max_output"],
            max_parallelism=row["max_parallelism"],
            allowed_job_profiles=profiles,
            last_success=last_success,
            failure_count=row["failure_count"],
            metadata_confidence=row["metadata_confidence"],
            model_version=row["model_version"]
            if "model_version" in row.keys()
            else None,
            artifact_digest=row["artifact_digest"]
            if "artifact_digest" in row.keys()
            else None,
            qualification_suite_version=row["qualification_suite_version"]
            if "qualification_suite_version" in row.keys()
            else None,
            qualification_evidence_digest=row["qualification_evidence_digest"]
            if "qualification_evidence_digest" in row.keys()
            else None,
            limitations=limitations,
            qualified_at=qualified_at,
            expires_at=expires_at,
        )
