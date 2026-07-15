"""One promotion, provenance and retrieval policy for specialized memories."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
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
    ) -> Sequence[MemoryHit]: ...

    def rebuild_derived_indexes(self) -> None: ...


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

    def owns_store(self, name: str, candidate: Any) -> bool:
        """Return whether *candidate* is the authority's production store.

        Explicit dependency-injection fakes and temporary test databases must
        remain usable without silently redirecting them to the process-wide
        authority store.  Production stores are identified by adapter identity
        or by their normalized database path.
        """
        adapter = self.adapters.get(name)
        canonical = getattr(adapter, "store", None)
        if canonical is None or candidate is None:
            return False
        if canonical is candidate:
            return True
        candidate_path = getattr(candidate, "db_path", None)
        canonical_path = getattr(canonical, "db_path", None)
        if candidate_path is None or canonical_path is None:
            return False
        try:
            return Path(candidate_path).resolve() == Path(canonical_path).resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            return str(candidate_path) == str(canonical_path)

    def register_adapter(self, name: str, adapter: SpecializedMemoryAdapter) -> None:
        """Attach a process-owned specialist after authority bootstrap."""
        self.adapters[name] = adapter

    def with_adapter(
        self, name: str, adapter: SpecializedMemoryAdapter
    ) -> "MemoryAuthority":
        """Return a mission-scoped authority with one adapter overridden.

        Council state is isolated per runtime root, so it must not be attached
        to the process-wide authority registry.  Copying the registry keeps
        the shared authority store and all other adapters intact while making
        the scoped specialist explicit.
        """
        return MemoryAuthority(
            store=self.store,
            adapters={**self.adapters, name: adapter},
            pheromone_adapter=self.pheromone_adapter,
        )

    def recall(
        self,
        query: str,
        context: MemoryRecallContext | Mapping[str, Any] | None = None,
        *,
        retrieval_fn: Any | None = None,
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
        if retrieval_fn is not None and adapter_name == "semantic":
            # The legacy semantic adapter accepts this only as a bounded
            # retrieval seam.  The authority still owns routing and trust
            # filtering; the hook keeps existing deterministic tests/fakes
            # from reaching around the authority while the legacy index is
            # being retired.
            hits = tuple(adapter.recall(query, resolved, retrieval_fn=retrieval_fn))
        else:
            hits = tuple(adapter.recall(query, resolved))
        if resolved.include_unverified:
            return hits[: resolved.limit]
        return tuple(
            hit
            for hit in hits
            if hit.verification_status == MemoryStatus.VERIFIED.value or hit.advisory
        )[: resolved.limit]

    @staticmethod
    def trust_level(hit: MemoryHit) -> str:
        """Translate a memory record's status into event trust semantics.

        Recall is allowed to include unverified records for inspection, but
        that option must never upgrade their event trust.  Advisory pheromones
        remain advisory even when their physical store uses another status.
        """
        if hit.advisory or hit.verification_status == "advisory":
            return "advisory"
        if hit.verification_status in {
            MemoryStatus.VERIFIED.value,
            "authoritative",
            "trusted",
        }:
            return "verified"
        if hit.verification_status in {"blocked", "rejected"}:
            return "blocked"
        return "unknown"

    @classmethod
    def is_trusted(cls, hit: MemoryHit) -> bool:
        """Return whether a hit may drive a trusted-memory event."""
        return cls.trust_level(hit) == "verified"

    def propose(self, proposal: MemoryProposal) -> MemoryProposal:
        """Quarantine a reference; proposals are never returned as trusted hits."""
        if not proposal.source_turn_id and not proposal.source_mission_id:
            raise MemoryAuthorityError(
                "memory proposal needs a turn or mission lineage"
            )
        if len(set(proposal.evidence_ids)) != len(proposal.evidence_ids):
            raise MemoryAuthorityError("duplicate evidence ids are not allowed")
        return self.store.save_proposal(proposal)

    def record_episodic(self, session_id: str, role: str, content: str) -> int:
        """Write a session turn through the episodic authority adapter."""
        adapter = self.adapters.get("episodic")
        record = getattr(adapter, "record", None)
        if not callable(record):
            raise MemoryAuthorityError("episodic memory adapter is unavailable")
        return int(record(session_id, role, content))

    def record_semantic_chat(self, content: str, *, indexer: Any | None = None) -> int:
        """Index an unverified chat observation through the semantic adapter."""
        adapter = self.adapters.get("semantic")
        record = getattr(adapter, "record_chat", None)
        if not callable(record):
            raise MemoryAuthorityError("semantic memory adapter is unavailable")
        return int(record(content, indexer=indexer))

    def semantic_add_verified(
        self,
        content: str,
        *,
        memory_type: str,
        count_occurrence: bool = True,
    ) -> int:
        """Index and promote trusted semantic memory through its adapter."""
        mem_id = int(
            self._adapter_operation(
                "semantic",
                "add",
                content,
                memory_type=memory_type,
                verification_status="verified",
                count_occurrence=count_occurrence,
            )
        )
        self._adapter_operation("semantic", "promote", mem_id)
        return mem_id

    def semantic_supersede_text(self, text: str) -> int:
        """Preserve semantic supersession lineage through its adapter."""
        return int(self._adapter_operation("semantic", "supersede_text", text))

    def facts_search(self, query: str) -> list[Any]:
        """Read active facts through the facts adapter."""
        return list(self._adapter_operation("facts", "search", query))

    def facts_neighbors(self, subject: str) -> list[Any]:
        """Read one-hop fact context through the facts adapter."""
        return list(self._adapter_operation("facts", "neighbors", subject))

    def facts_traverse_weighted(
        self,
        subject: str,
        *,
        max_depth: int = 3,
        min_path_confidence: float = 0.3,
    ) -> list[Any]:
        """Read confidence-weighted fact paths through the facts adapter."""
        return list(
            self._adapter_operation(
                "facts",
                "traverse_weighted",
                subject,
                max_depth=max_depth,
                min_path_confidence=min_path_confidence,
            )
        )

    def facts_strengthen_or_propose(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        source: str = "auto-extract",
    ) -> Any:
        """Form a quarantined fact proposal or strengthen an approved fact."""
        return self._adapter_operation(
            "facts", "strengthen_or_propose", subject, predicate, obj, source=source
        )

    def facts_add_fact(self, *args: Any, **kwargs: Any) -> Any:
        return self._adapter_operation("facts", "add_fact", *args, **kwargs)

    def facts_reconcile(self, *args: Any, **kwargs: Any) -> Any:
        return self._adapter_operation("facts", "reconcile", *args, **kwargs)

    def facts_pending_proposals(self, limit: int = 100) -> list[Any]:
        return list(self._adapter_operation("facts", "pending_proposals", limit))

    def facts_approve_proposal(self, proposal_id: int, *, approved_by: str) -> Any:
        return self._adapter_operation(
            "facts", "approve_proposal", proposal_id, approved_by=approved_by
        )

    def facts_reject_proposal(self, proposal_id: int, *, rejected_by: str) -> bool:
        return bool(
            self._adapter_operation(
                "facts", "reject_proposal", proposal_id, rejected_by=rejected_by
            )
        )

    def facts_traverse(self, subject: str, max_depth: int = 2) -> list[Any]:
        return list(self._adapter_operation("facts", "traverse", subject, max_depth))

    def recall_skills(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Return verified reusable workflows through the skills adapter."""
        return list(
            self._adapter_operation("skills", "relevant_verified", query, limit)
        )

    def recall_lessons(
        self, query: str, task_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return pending and verified lessons through the lessons adapter."""
        return list(
            self._adapter_operation("lessons", "recall_relevant", query, task_id, limit)
        )

    def recall_verified_lessons(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return only verified cross-task lessons for planning calibration."""
        return list(
            self._adapter_operation("lessons", "relevant_verified", query, limit)
        )

    def development_success_rate(self, query: str, **kwargs: Any) -> Any:
        """Read evidence-backed developmental history through its adapter."""
        return self._adapter_operation(
            "development", "relevant_success_rate", query, **kwargs
        )

    def development_summary(self) -> dict[str, Any]:
        """Read development metrics through the authority-owned adapter."""
        return dict(self._adapter_operation("development", "summary"))

    def skills_list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        """Read procedural skills through the authority-owned adapter."""
        return list(self._adapter_operation("skills", "list", status=status))

    def skills_trail_map(self) -> dict[str, Any]:
        """Read pheromone-backed skill trails through the authority boundary."""
        return dict(self._adapter_operation("skills", "trail_map"))

    def record_development(self, *args: Any, **kwargs: Any) -> int:
        return int(self._adapter_operation("development", "record", *args, **kwargs))

    def record_skill_attempt(self, *args: Any, **kwargs: Any) -> int:
        return int(self._adapter_operation("skills", "record_attempt", *args, **kwargs))

    def record_skill_reuse(self, *args: Any, **kwargs: Any) -> list[int]:
        return list(self._adapter_operation("skills", "record_reuse", *args, **kwargs))

    def record_lesson_or_increment(self, *args: Any, **kwargs: Any) -> tuple[int, bool]:
        return self._adapter_operation(
            "lessons", "record_or_increment", *args, **kwargs
        )

    def lesson_record(self, *args: Any, **kwargs: Any) -> int:
        return int(self._adapter_operation("lessons", "record", *args, **kwargs))

    def lesson_get(self, mistake_id: int) -> Any:
        return self._adapter_operation("lessons", "get", mistake_id)

    def lessons_by_status(self, status: str) -> list[Any]:
        return list(self._adapter_operation("lessons", "rows_by_status", status))

    def promote_lesson(self, mistake_id: int, **kwargs: Any) -> None:
        self._adapter_operation("lessons", "promote", mistake_id, **kwargs)

    def pending_lesson_commands(self, task_id: str) -> list[tuple[int, str]]:
        return list(
            self._adapter_operation("lessons", "pending_command_pairs", task_id)
        )

    def pending_lessons_for_task(self, task_id: str, limit: int = 5) -> list[Any]:
        """Read same-task pending lessons through the lessons adapter."""
        return list(
            self._adapter_operation("lessons", "pending_for_task", task_id, limit)
        )

    def consolidate_lesson(self, *args: Any, **kwargs: Any) -> Any:
        return self._adapter_operation(
            "consolidation", "consolidate_lesson", *args, **kwargs
        )

    def promote_fact(self, *args: Any, **kwargs: Any) -> Any:
        return self._adapter_operation("consolidation", "promote_fact", *args, **kwargs)

    def reconcile_fact(self, *args: Any, **kwargs: Any) -> Any:
        return self._adapter_operation(
            "consolidation", "reconcile_fact", *args, **kwargs
        )

    def consolidate(self) -> dict[str, Any]:
        return self._adapter_operation("consolidation", "run")

    def compact_memory(self, *, dry_run: bool = True) -> dict[str, Any]:
        """Run the audited forgetting sweep through the authority adapter."""
        return dict(self._adapter_operation("compaction", "compact", dry_run=dry_run))

    def touch_working_session(self, session_id: str) -> None:
        self._adapter_operation("compaction", "touch_working_session", session_id)

    def record_council_deliberation(self, *args: Any, **kwargs: Any) -> int:
        """Persist advisory Council evidence through its scoped adapter."""
        return int(
            self._adapter_operation("council", "record_deliberation", *args, **kwargs)
        )

    def council_deliberations_for(self, mission_id: str) -> list[Any]:
        """Read append-only Council evidence through its scoped adapter."""
        return list(self._adapter_operation("council", "deliberations_for", mission_id))

    def pheromone_query(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Read advisory pheromones through the authority-owned adapter."""
        return list(self._pheromone_operation("query", *args, **kwargs))

    def pheromone_for_contract(self, allowed_files: list[str]) -> list[str]:
        """Read non-authoritative pheromone context for a mission contract."""
        return list(self._pheromone_operation("for_contract", allowed_files))

    def pheromone_deposit(self, *args: Any, **kwargs: Any) -> int:
        """Persist an advisory pheromone through its specialist adapter."""
        return int(self._pheromone_operation("deposit", *args, **kwargs))

    def pheromone_reinforce(self, *args: Any, **kwargs: Any) -> None:
        self._pheromone_operation("reinforce", *args, **kwargs)

    def pheromone_decay(self) -> int:
        return int(self._pheromone_operation("decay_all"))

    def facts_for(self, subject: str, predicate: str | None = None) -> list[Any]:
        """Read active operator facts through the facts adapter."""
        if predicate is None:
            return list(self._adapter_operation("facts", "facts_for", subject))
        return list(self._adapter_operation("facts", "facts_for", subject, predicate))

    def facts_by_status(self, status: str) -> list[Any]:
        return list(self._adapter_operation("facts", "rows_by_status", status))

    def operator_model(self) -> dict[str, Any]:
        """Read the structured operator model through the facts adapter."""
        return dict(self._adapter_operation("facts", "operator_model"))

    def self_model(self) -> str:
        """Build the deterministic verified-only self-model through adapters."""
        from aios.memory.self_model import render, synthesize_self_model

        development = self._adapter_operation("development", "task_profile")
        lessons = self._adapter_operation("lessons", "recurring", 3)

        class _DevelopmentView:
            def task_profile(self) -> dict[str, tuple[int, float]]:
                return development

        class _LessonsView:
            def recurring(self, *, limit: int = 3) -> list[dict[str, Any]]:
                return lessons[:limit]

        return render(synthesize_self_model(_DevelopmentView(), _LessonsView()))

    def recent_episodic(self, session_id: str, limit: int) -> list[Any]:
        """Read chronological session turns through the episodic adapter."""
        adapter = self.adapters.get("episodic")
        recent = getattr(adapter, "recent", None)
        if not callable(recent):
            raise MemoryAuthorityError("episodic memory adapter is unavailable")
        return list(recent(session_id, limit))

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
            evidence_id for item in items for evidence_id in _evidence_ids(item)
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
                raise MemoryPromotionDenied(
                    "privileged operator authentication is required"
                )
        elif resolved.requires_operator_approval:
            raise MemoryPromotionDenied(
                "operator approval is required for this proposal"
            )
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
            operator_approval=actor.actor_id
            if actor.actor_type == "operator"
            else None,
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

    def supersede(
        self, record: MemoryRecord | str, replacement: MemoryRecord | str
    ) -> MemoryRecord:
        """Supersede without deleting lineage or crossing project boundaries."""
        record_id = (
            record.record_id if isinstance(record, MemoryRecord) else str(record)
        )
        replacement_id = (
            replacement.record_id
            if isinstance(replacement, MemoryRecord)
            else str(replacement)
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
                raise MemoryAuthorityError(
                    "proposal content changed after registration"
                )
            return stored
        stored = self.store.get_proposal(str(proposal))
        if stored is None:
            raise MemoryAuthorityError("proposal not found")
        return stored

    def _adapter_operation(
        self, name: str, operation: str, *args: Any, **kwargs: Any
    ) -> Any:
        adapter = self.adapters.get(name)
        method = getattr(adapter, operation, None)
        if not callable(method):
            raise MemoryAuthorityError(f"{name} memory adapter is unavailable")
        return method(*args, **kwargs)

    def _pheromone_operation(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.pheromone_adapter, operation, None)
        if not callable(method):
            raise MemoryAuthorityError("pheromone memory adapter is unavailable")
        return method(*args, **kwargs)

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
