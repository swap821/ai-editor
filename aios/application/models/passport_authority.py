"""One authority over model admission (Organ 33).

Before this, "is this model admitted, and for what?" had two disconnected
answers with complementary fields and no converter between them:

* ``ModelPassportV1`` (``aios/domain/models/contracts.py``) carried
  ``qualified_roles``/``disallowed_roles``/``tool_protocol_status`` and the
  admission lifecycle -- but NO durable store held one. Every instance was
  hand-constructed in memory and discarded on process exit, so nothing
  survived a restart and nothing could be audited.
* ``LocalWorkerModel`` (the workforce registry) is genuinely durable and now
  carries the evidence fields -- ``artifact_digest``,
  ``qualification_evidence_digest``, ``qualified_at``, ``expires_at``,
  ``limitations`` -- but has no notion of qualified ROLES.

Each had exactly what the other lacked, which is precisely why they drifted.

This module makes the registry row the single source of truth and derives the
passport FROM it. The passport stops being a second place admission can be
asserted and becomes a projection of the one place it is recorded -- so a
passport cannot claim an admission the registry does not hold, and cannot go
stale relative to it.

What this deliberately does NOT do: it does not merge the two Pydantic classes
into one. ``ModelPassportV1`` also describes cloud/provider models that have no
registry row at all (deployment_region, cost_profile, measured_success_rates),
and collapsing those into a local-worker row would invent fields for models
this registry has never seen. Projection is the honest relationship; a merge
would be a bigger, separate change.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aios.domain.local_workforce.contracts import LocalWorkerModel
from aios.domain.models.contracts import ModelPassportV1

#: Registry admission state -> passport admission state.
#:
#: The registry's vocabulary is operational ("did the operator approve it, is
#: it healthy"); the passport's is constitutional ("may it serve a role").
#: `rejected` maps to `revoked` rather than `suspended` because a rejection is
#: a decision about the model, while a suspension is a decision about its
#: evidence going stale -- collapsing them would lose why it cannot serve.
_ADMISSION_MAP: dict[str, str] = {
    "pending": "proposed",
    "approved": "admitted",
    "suspended": "suspended",
    "rejected": "revoked",
}


def _passport_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def passport_from_registry_row(model: LocalWorkerModel) -> ModelPassportV1:
    """Project a durable registry row into a ``ModelPassportV1``.

    Every field is DERIVED. Nothing is defaulted to a value that would read as
    a qualification the model has not earned:

    * ``qualified_roles`` comes from ``allowed_job_profiles``, which the
      service now grants only from real qualification evidence -- so a role
      cannot appear here that the model did not earn.
    * ``tool_protocol_status`` stays ``"unknown"`` unless the registry has
      genuine evidence. It is never upgraded to ``"verified"`` by projection,
      because `can_drive_tools()` gates real tool authority on exactly that
      value and inventing it would hand a model tool access on no evidence.
    * ``admission_status`` is mapped, never assumed: a suspended registry row
      projects to a suspended passport, so the auto-suspend triggers
      (artifact-digest change, evidence expiry, health drop, runtime gone,
      suite version bump) reach role admission automatically.
    """
    admission = _ADMISSION_MAP.get(model.admission_status, "proposed")

    payload = {
        "passport_id": f"local:{model.model_id}",
        "provider": model.provider,
        "exact_model_id": model.model_id,
        "model_version": model.model_version,
        "privacy_class": "local",
        "qualified_roles": sorted(p.value for p in model.allowed_job_profiles),
        "admission_status": admission,
        "qualification_suite_version": model.qualification_suite_version,
        "qualification_evidence_digest": model.qualification_evidence_digest,
        "artifact_digest": model.artifact_digest,
        "last_qualified_at": (
            model.qualified_at.isoformat() if model.qualified_at else None
        ),
        "expires_at": model.expires_at.isoformat() if model.expires_at else None,
        "limitations": sorted(model.limitations),
        "context_limit": model.max_context,
        "output_limit": model.max_output,
    }

    return ModelPassportV1(
        passport_id=f"local:{model.model_id}",
        provider=model.provider,
        exact_model_id=model.model_id,
        model_version=model.model_version,
        privacy_class="local",
        qualified_roles=tuple(sorted(p.value for p in model.allowed_job_profiles)),
        disallowed_roles=(),
        # Never projected as verified -- see the docstring.
        tool_protocol_status="unknown",
        structured_output_status="unknown",
        context_limit=model.max_context,
        output_limit=model.max_output,
        known_failure_modes=tuple(sorted(model.limitations)),
        admission_status=admission,  # type: ignore[arg-type]
        qualification_suite_version=model.qualification_suite_version,
        last_qualified_at=(
            model.qualified_at.isoformat() if model.qualified_at else None
        ),
        passport_digest=_passport_digest(payload),
    )


class ModelPassportAuthority:
    """The one place a local model's passport is answered from.

    Reads the durable registry rather than holding its own state, so a
    passport can never disagree with the admission the registry recorded.
    """

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def passport_for(self, model_id: str) -> ModelPassportV1 | None:
        """The current passport for `model_id`, or None if unregistered.

        None means "this authority has no record", which callers must treat as
        not-admitted. It is deliberately not a proposed-but-empty passport,
        which would look like a model merely awaiting qualification.
        """
        model = self.registry.get_model(model_id)
        if model is None:
            return None
        return passport_from_registry_row(model)

    def admitted_passports(self) -> tuple[ModelPassportV1, ...]:
        """Every model the registry currently holds as admitted."""
        return tuple(
            passport_from_registry_row(model)
            for model in self.registry.list_models()
            if model.admission_status == "approved"
        )


__all__ = [
    "ModelPassportAuthority",
    "passport_from_registry_row",
]
