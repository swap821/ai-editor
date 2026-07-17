"""Durable registry for the Local Workforce (R15 Slice 3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence

from aios.core.llm import OllamaClient
from aios.domain.local_workforce.contracts import LocalWorkerModel, LocalJobProfile
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
                    "SELECT 1 FROM local_worker_models WHERE model_id = ?", 
                    (model_id,)
                )
                exists = cursor.fetchone() is not None

                if not exists:
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
                            metadata_confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            model_id,
                            "ollama",
                            family,
                            parameter_size,
                            quantization,
                            1,  # installed
                            0,  # operator_approved (default false)
                            "unknown", # health
                            "pending", # admission_status
                            8192,  # safe default context
                            2048,  # safe default output
                            1,     # safe default parallelism
                            "[]",  # no profiles allowed yet
                            "verified" if family != "unknown" else "inferred"
                        )
                    )
                else:
                    # Model already known, just ensure it's marked installed
                    conn.execute(
                        "UPDATE local_worker_models SET installed = 1 WHERE model_id = ?",
                        (model_id,)
                    )
            
            # Mark models not seen as uninstalled (preserve history)
            if seen_ids:
                placeholders = ",".join("?" for _ in seen_ids)
                conn.execute(
                    f"UPDATE local_worker_models SET installed = 0 WHERE model_id NOT IN ({placeholders})",
                    tuple(seen_ids)
                )
            else:
                conn.execute("UPDATE local_worker_models SET installed = 0")
            
            conn.commit()

    def get_model(self, model_id: str) -> LocalWorkerModel | None:
        """Retrieve a local model by ID."""
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM local_worker_models WHERE model_id = ?", 
                (model_id,)
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
    
    def update_approval(self, model_id: str, approved: bool, reason: str | None = None) -> None:
        """Update operator approval status."""
        admission_status = "approved" if approved else "rejected"
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE local_worker_models 
                SET operator_approved = ?, admission_status = ?, admission_reason = ?
                WHERE model_id = ?
                """,
                (1 if approved else 0, admission_status, reason, model_id)
            )
            conn.commit()

    def update_profiles(self, model_id: str, profiles: set[LocalJobProfile]) -> None:
        """Update allowed job profiles."""
        profiles_list = [p.value for p in profiles]
        with get_connection() as conn:
            conn.execute(
                "UPDATE local_worker_models SET allowed_job_profiles_json = ? WHERE model_id = ?",
                (json.dumps(profiles_list), model_id)
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
                    (status, model_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE local_worker_models 
                    SET health = ?, failure_count = failure_count + 1
                    WHERE model_id = ?
                    """,
                    (status, model_id)
                )
            conn.commit()

    def _row_to_model(self, row: dict[str, Any]) -> LocalWorkerModel:
        profiles_raw = json.loads(row["allowed_job_profiles_json"])
        profiles = frozenset(LocalJobProfile(p) for p in profiles_raw)
        
        last_success = row["last_success"]
        if last_success and isinstance(last_success, str):
            # parse CURRENT_TIMESTAMP format
            try:
                # SQLite CURRENT_TIMESTAMP is UTC 'YYYY-MM-DD HH:MM:SS'
                # but might contain 'T' or 'Z' depending on how it was written
                last_success = datetime.fromisoformat(last_success.replace(" ", "T")).replace(tzinfo=timezone.utc)
            except ValueError:
                last_success = None
                
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
            metadata_confidence=row["metadata_confidence"]
        )
