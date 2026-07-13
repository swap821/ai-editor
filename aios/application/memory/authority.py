"""One promotion, provenance and retrieval policy for specialized memories."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from aios.domain.evidence import EvidenceRecord, VerificationResult
from aios.domain.memory import (
    MemoryHit,
    MemoryProposal,
    MemoryPromotionActor,
    MemoryRecallContext,
    MemoryRecord,
    MemoryRecordProvenance,
    MemoryStatus,
    MemoryVerification,
)
from aios.infrastructure.memory import MemoryAuthorityStore


EvidenceLike = EvidenceRecord | VerificationResult


class MemoryAuthorityError(RuntimeError):
    """Base class for fail-closed memory authority errors."""


class MemoryPromotionDenied(MemoryAuthorityError):
    """Raised when evidence, identity or lineage is insufficient."""


class SpecializedMemoryAdapter(Protocol):
    """Adapter contract; physical stores remain owned by their specialists."""

    memory_types: tuple[str, ...]

    def recall(
        self, query: str, context: MemoryRecallContext
    ) -> Sequence[MemoryHit]:
        ...

    def rebuild_derived_indexes(self) -> None:
        ...


class MemoryAuthority:
    """Canonical memory lifecycle over the existing specialized stores."""

    def __init__(
        self,
        *,
        store: MemoryAuthorityStore,
        adapters: Mapping[str, SpecializedMemoryAdapter] | None = None,
        pheromone_adapter: SpecializedMemoryAdapter | None = None,
    ) -> None:
        self.store = store
        self.adapters = dict(adapters or {})
        self.pheromone_adapter = pheromone_adapter

    def recall(
        self,
        query: str,
        context: MemoryRecallContext | Mapping[str, Any] | None = None,
    ) -> tuple[MemoryHit, ...]:
        """Route to one relevant adapter; never query every memory subsystem."""
        resolved = (
            context
            if isinstance(context, MemoryRecallContext)
            else MemoryRecallContext.model_validate(context or {})
        )
        adapter_name = self._route_adapter(resolved)
        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            return self._registry_hits(resolved)
        hits = tuple(adapter.recall(query, resolved))
        if resolved.include_unverified:
            return hits[: resolved.limit]
        return tuple(
            hit
            for hit in hits
            if hit.verification_status == MemoryStatus.VERIFIED.value or hit.advisory
        )[: resolved.limit]

    def propose(self, proposal: MemoryProposal) -> MemoryProposal:
        """Quarantine a reference; proposals are never returned as trusted hits."""
        if not proposal.source_turn_id and not proposal.source_mission_id:
            raise MemoryAuthorityError("memory proposal needs a turn or mission lineage")
        if len(set(proposal.evidence_ids)) != len(proposal.evidence_ids):
            raise MemoryAuthorityError("duplicate evidence ids are not allowed")
        return self.store.save_proposal(proposal)

    def verify(
        self,
        proposal: MemoryProposal | str,
        evidence: Sequence[EvidenceLike],
    ) -> MemoryVerification:
        """Evaluate evidence deterministically, using the weakest item as floor."""
        resolved = self._resolve_proposal(proposal)
        items = tuple(evidence)
        reason_codes: list[str] = []
        if not items:
            reason_codes.append("EVIDENCE_REQUIRED")
        if not resolved.evidence_ids:
            reason_codes.append("EVIDENCE_LINEAGE_REQUIRED")
        evidence_ids = tuple(
            evidence_id
            for item in items
            for evidence_id in _evidence_ids(item)
        )
        if len(set(evidence_ids)) != len(evidence_ids):
            reason_codes.append("DUPLICATE_EVIDENCE")
        missing = set(resolved.evidence_ids) - set(evidence_ids)
        if missing:
            reason_codes.append("DECLARED_EVIDENCE_MISSING")
        unexpected = set(evidence_ids) - set(resolved.evidence_ids)
        if unexpected and resolved.evidence_ids:
            reason_codes.append("UNDECLARED_EVIDENCE")

        strengths = [_evidence_strength(item) for item in items]
        strength = min(strengths) if strengths else 0
        if strength < resolved.required_strength:
            reason_codes.append("VERIFICATION_STRENGTH_TOO_WEAK")
        for item in items:
            if not _evidence_passed(item):
                reason_codes.append("VERIFICATION_FAILED")
            if not _evidence_is_fresh(item, resolved.evidence_freshness_seconds):
                reason_codes.append("EVIDENCE_STALE")
            if not _evidence_belongs_to_proposal(item, resolved):
                reason_codes.append("EVIDENCE_SCOPE_MISMATCH")
        unique_reasons = tuple(dict.fromkeys(reason_codes))
        return MemoryVerification(
            proposal_id=resolved.proposal_id,
            verified=not unique_reasons,
            strength=strength,
            evidence_ids=evidence_ids,
            reason_codes=unique_reasons,
        )

    def promote(
        self,
        proposal: MemoryProposal | str,
        operator_or_policy: MemoryPromotionActor,
        *,
        evidence: Sequence[EvidenceLike],
    ) -> MemoryRecord:
        """Promote exactly once after identity, evidence and policy checks."""
        resolved = self._resolve_proposal(proposal)
        actor = MemoryPromotionActor.model_validate(operator_or_policy)
        if actor.actor_type == "operator":
            if not actor.authentication_event_id or not actor.operator_approval:
                raise MemoryPromotionDenied("privileged operator authentication is required")
        elif resolved.requires_operator_approval:
            raise MemoryPromotionDenied("operator approval is required for this proposal")
        verification = self.verify(resolved, evidence)
        if not verification.verified:
            raise MemoryPromotionDenied(";".join(verification.reason_codes))
        if self.store.proposal_status(resolved.proposal_id) != MemoryStatus.PROPOSED:
            raise MemoryPromotionDenied("proposal has already been resolved")
        if actor.actor_type == "policy" and actor.actor_id.startswith("model"):
            raise MemoryPromotionDenied("model principals cannot promote memory")
        if not resolved.source_turn_id and not resolved.source_mission_id:
            raise MemoryPromotionDenied("promotion requires turn or mission provenance")

        record_id = f"memory-{uuid.uuid4().hex}"
        provenance = MemoryRecordProvenance(
            source_principal=resolved.source_principal,
            source_turn_id=resolved.source_turn_id,
            source_mission_id=resolved.source_mission_id,
            source_action_id=resolved.source_action_id,
            evidence_ids=verification.evidence_ids,
            verification_strength=verification.strength,
            operator_approval=actor.actor_id if actor.actor_type == "operator" else None,
            project_id=resolved.project_id,
            policy_version=resolved.policy_version,
            confidence_basis=resolved.confidence_basis,
        )
        record = MemoryRecord(
            record_id=record_id,
            proposal_id=resolved.proposal_id,
            memory_type=resolved.memory_type,
            content_reference=resolved.content_reference,
            content_digest=resolved.content_digest,
            project_id=resolved.project_id,
            provenance=provenance,
        )
        return self.store.save_promoted(
            record,
            evidence_strengths=tuple(
                (evidence_id, _evidence_strength(item))
                for item in evidence
                for evidence_id in _evidence_ids(item)
            ),
        )

    def supersede(self, record: MemoryRecord | str, replacement: MemoryRecord | str) -> MemoryRecord:
        """Supersede without deleting lineage or crossing project boundaries."""
        record_id = record.record_id if isinstance(record, MemoryRecord) else str(record)
        replacement_id = (
            replacement.record_id if isinstance(replacement, MemoryRecord) else str(replacement)
        )
        return self.store.supersede(record_id, replacement_id)

    def compact(self, policy: Mapping[str, Any] | None = None) -> int:
        """Compact rejected authority metadata while retaining verified lineage."""
        keep_superseded = bool((policy or {}).get("keep_superseded", True))
        return self.store.compact(keep_superseded=keep_superseded)

    def rebuild_derived_indexes(self) -> None:
        """Rebuild specialized indexes only as an explicit recovery operation."""
        for adapter in self.adapters.values():
            adapter.rebuild_derived_indexes()
        if self.pheromone_adapter is not None:
            self.pheromone_adapter.rebuild_derived_indexes()

    def _resolve_proposal(self, proposal: MemoryProposal | str) -> MemoryProposal:
        if isinstance(proposal, MemoryProposal):
            stored = self.store.get_proposal(proposal.proposal_id)
            if stored is None:
                raise MemoryAuthorityError("proposal is not registered")
            if stored != proposal:
                raise MemoryAuthorityError("proposal content changed after registration")
            return stored
        stored = self.store.get_proposal(str(proposal))
        if stored is None:
            raise MemoryAuthorityError("proposal not found")
        return stored

    def _route_adapter(self, context: MemoryRecallContext) -> str:
        if context.session_id and "episodic" in self.adapters:
            return "episodic"
        if context.task_signature and "skill" in self.adapters:
            return "skill"
        if context.memory_types:
            for name, adapter in self.adapters.items():
                if set(context.memory_types).intersection(adapter.memory_types):
                    return name
        if "semantic" in self.adapters:
            return "semantic"
        return next(iter(self.adapters), "")

    def _registry_hits(self, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        return tuple(
            MemoryHit(
                record_id=record.record_id,
                memory_type=record.memory_type,
                content_reference=record.content_reference,
                project_id=record.project_id,
                source="memory_authority",
                verification_status=record.status.value,
            )
            for record in self.store.list_records(
                project_id=context.project_id,
                memory_types=context.memory_types,
                limit=context.limit,
            )
        )


def _evidence_ids(item: EvidenceLike) -> tuple[str, ...]:
    if isinstance(item, EvidenceRecord):
        return (item.evidence_id,)
    return item.evidence_ids or (item.verification_id,)


def _evidence_strength(item: EvidenceLike) -> int:
    return int(
        item.verification_strength
        if isinstance(item, EvidenceRecord)
        else item.strength
    )


def _evidence_passed(item: EvidenceLike) -> bool:
    return (
        item.trust_level in {"verified", "authoritative"}
        if isinstance(item, EvidenceRecord)
        else item.passed and item.strength >= item.required_strength
    )


def _evidence_belongs_to_proposal(item: EvidenceLike, proposal: MemoryProposal) -> bool:
    if proposal.source_mission_id:
        mission_id = item.mission_id
        if mission_id != proposal.source_mission_id:
            return False
    if proposal.source_action_id:
        action_id = item.action_id
        if action_id != proposal.source_action_id:
            return False
    return True


def _evidence_is_fresh(item: EvidenceLike, max_age_seconds: int) -> bool:
    value = item.produced_at if isinstance(item, EvidenceRecord) else item.observed_at
    try:
        observed = datetime.fromisoformat(value)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    return 0 <= age <= max_age_seconds


__all__ = [
    "MemoryAuthority",
    "MemoryAuthorityError",
    "MemoryPromotionDenied",
    "SpecializedMemoryAdapter",
]
