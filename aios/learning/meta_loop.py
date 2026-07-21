"""Local-only meta-loop and council self-assessment evidence.

This module summarizes existing evidence into review proposals. It does not
call models, mutate stores, apply code, change policy, or authorize actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from aios.security.secret_scanner import scan_and_redact


@dataclass(frozen=True)
class MetaLoopSnapshot:
    reflections: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    mistakes: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    skills: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    audit_events: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    policies: Sequence[Any] = field(default_factory=tuple)
    hibernation: Mapping[str, Any] | None = None
    council_deliberations: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


@dataclass(frozen=True)
class MetaLoopSource:
    name: str
    count: int
    status: str
    highlights: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "status": self.status,
            "highlights": self.highlights,
        }


@dataclass(frozen=True)
class MetaLoopProposal:
    kind: str
    title: str
    reason: str
    evidence_sources: list[str]
    risk: str = "YELLOW"
    authority: str = "proposal/evidence"
    requires_human_review: bool = True
    can_auto_apply: bool = False
    allowed_actions: list[str] = field(
        default_factory=lambda: ["review", "route_followup_task"]
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "reason": self.reason,
            "evidenceSources": self.evidence_sources,
            "risk": self.risk,
            "authority": self.authority,
            "requiresHumanReview": self.requires_human_review,
            "canAutoApply": self.can_auto_apply,
            "allowedActions": self.allowed_actions,
        }


@dataclass(frozen=True)
class MetaLoopAssessment:
    sources: list[MetaLoopSource]
    proposals: list[MetaLoopProposal]
    blockers: list[str]
    safety_status: str
    activation: str = "proposal/evidence"
    authority: str = "proposal/evidence"
    local_only: bool = True
    cloud_calls: int = 0
    writes_performed: bool = False
    policy_mutations: int = 0
    self_apply_attempted: bool = False
    can_authorize: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "activation": self.activation,
            "authority": self.authority,
            "localOnly": self.local_only,
            "cloudCalls": self.cloud_calls,
            "writesPerformed": self.writes_performed,
            "policyMutations": self.policy_mutations,
            "selfApplyAttempted": self.self_apply_attempted,
            "canAuthorize": self.can_authorize,
            "safetyStatus": self.safety_status,
            "sources": [source.as_dict() for source in self.sources],
            "proposals": [proposal.as_dict() for proposal in self.proposals],
            "blockers": self.blockers,
        }


def collect_meta_loop_evidence(
    *,
    reflections: Sequence[Mapping[str, Any]] = (),
    mistakes: Sequence[Mapping[str, Any]] = (),
    skills: Sequence[Mapping[str, Any]] = (),
    audit_events: Sequence[Mapping[str, Any]] = (),
    policy_engine: Any | None = None,
    hibernation_report: Any | None = None,
    council_deliberations: Sequence[Mapping[str, Any]] = (),
) -> MetaLoopSnapshot:
    """Collect caller-supplied local evidence without mutating any source."""
    policies: Sequence[Any] = ()
    if policy_engine is not None:
        policies = tuple(policy_engine.policy_chain())
    hibernation = (
        _to_mapping(hibernation_report) if hibernation_report is not None else None
    )
    return MetaLoopSnapshot(
        reflections=tuple(_mapping_items(reflections)),
        mistakes=tuple(_mapping_items(mistakes)),
        skills=tuple(_mapping_items(skills)),
        audit_events=tuple(_mapping_items(audit_events)),
        policies=tuple(policies),
        hibernation=hibernation,
        council_deliberations=tuple(_mapping_items(council_deliberations)),
    )


def assess_meta_loop(snapshot: MetaLoopSnapshot) -> MetaLoopAssessment:
    """Summarize evidence into advisory proposals and safety blockers."""
    sources = [
        _reflection_source(snapshot.reflections),
        _mistake_source(snapshot.mistakes),
        _skill_source(snapshot.skills),
        _audit_source(snapshot.audit_events),
        _policy_source(snapshot.policies),
        _hibernation_source(snapshot.hibernation),
        _council_source(snapshot.council_deliberations),
    ]
    proposals = _proposals(snapshot)
    blockers = _blockers(snapshot)
    safety_status = "blocked" if blockers else "advisory"
    if not proposals and not blockers:
        proposals.append(
            MetaLoopProposal(
                kind="evidence_collection",
                title="Collect more local self-assessment evidence",
                reason="No reflection, mistake, skill, audit, policy, hibernation, or council evidence was supplied.",
                evidence_sources=[],
                risk="GREEN",
            )
        )
    return MetaLoopAssessment(
        sources=sources,
        proposals=proposals,
        blockers=blockers,
        safety_status=safety_status,
    )


def _reflection_source(items: Sequence[Mapping[str, Any]]) -> MetaLoopSource:
    return MetaLoopSource(
        name="reflection",
        count=len(items),
        status="available" if items else "empty",
        highlights=_highlights(items, ("lesson", "summary", "fixes")),
    )


def _mistake_source(items: Sequence[Mapping[str, Any]]) -> MetaLoopSource:
    recurring = [
        item
        for item in items
        if _int(item.get("occurrence_count")) > 1
        or str(item.get("verification_status", "")).lower() == "verified"
    ]
    return MetaLoopSource(
        name="mistake",
        count=len(items),
        status="recurring_lessons"
        if recurring
        else ("available" if items else "empty"),
        highlights=_highlights(
            recurring or items, ("lesson_text", "error_type", "root_cause")
        ),
    )


def _skill_source(items: Sequence[Mapping[str, Any]]) -> MetaLoopSource:
    candidates = [
        item for item in items if str(item.get("status", "")).lower() != "verified"
    ]
    return MetaLoopSource(
        name="skill",
        count=len(items),
        status="candidates_need_review"
        if candidates
        else ("available" if items else "empty"),
        highlights=_highlights(candidates or items, ("goal_pattern", "status")),
    )


def _audit_source(items: Sequence[Mapping[str, Any]]) -> MetaLoopSource:
    risky = [
        item for item in items if str(item.get("risk", "")).upper() in {"YELLOW", "RED"}
    ]
    return MetaLoopSource(
        name="audit",
        count=len(items),
        status="risk_evidence" if risky else ("available" if items else "empty"),
        highlights=_highlights(risky or items, ("summary", "reason", "risk")),
    )


def _policy_source(items: Sequence[Any]) -> MetaLoopSource:
    proposed = [item for item in items if _policy_status(item) == "proposed"]
    return MetaLoopSource(
        name="policy",
        count=len(items),
        status="proposals_pending" if proposed else ("available" if items else "empty"),
        highlights=[_policy_highlight(item) for item in (proposed or list(items))[:3]],
    )


def _hibernation_source(item: Mapping[str, Any] | None) -> MetaLoopSource:
    if item is None:
        return MetaLoopSource("hibernation", 0, "empty", [])
    proposals = item.get("proposals", [])
    count = len(proposals) if isinstance(proposals, list) else 1
    status = "unsafe_evidence" if _hibernation_unsafe(item) else "local_preview"
    highlights = (
        [_clean(value) for value in proposals[:3]]
        if isinstance(proposals, list)
        else []
    )
    return MetaLoopSource("hibernation", count, status, highlights)


def _council_source(items: Sequence[Mapping[str, Any]]) -> MetaLoopSource:
    risky = [
        item for item in items if str(item.get("risk", "")).upper() in {"YELLOW", "RED"}
    ]
    return MetaLoopSource(
        name="council",
        count=len(items),
        status="review_needed" if risky else ("available" if items else "empty"),
        highlights=_highlights(risky or items, ("summary", "reason", "risk")),
    )


def _proposals(snapshot: MetaLoopSnapshot) -> list[MetaLoopProposal]:
    proposals: list[MetaLoopProposal] = []
    if snapshot.reflections:
        proposals.append(
            MetaLoopProposal(
                kind="reflection_review",
                title="Review recent reflection pivots",
                reason="Recent reflection evidence may contain behavior changes worth promoting to operator-reviewed workflow guidance.",
                evidence_sources=["reflection"],
                risk="GREEN",
            )
        )
    if any(_int(item.get("occurrence_count")) > 1 for item in snapshot.mistakes):
        proposals.append(
            MetaLoopProposal(
                kind="recurring_mistake_review",
                title="Review recurring verified mistake lessons",
                reason="Repeated mistakes should strengthen future planning only after their mitigation remains verifier-backed.",
                evidence_sources=["mistake"],
            )
        )
    if any(
        str(item.get("status", "")).lower() != "verified" for item in snapshot.skills
    ):
        proposals.append(
            MetaLoopProposal(
                kind="skill_review",
                title="Review candidate or quarantined skill trails",
                reason="Candidate skills can inform follow-up testing but must not become trusted workflow memory without verification.",
                evidence_sources=["skill"],
            )
        )
    if any(
        str(item.get("risk", "")).upper() in {"YELLOW", "RED"}
        for item in snapshot.audit_events
    ):
        proposals.append(
            MetaLoopProposal(
                kind="audit_review",
                title="Review elevated audit evidence",
                reason="YELLOW or RED audit evidence needs human review before it can affect execution strategy.",
                evidence_sources=["audit"],
                risk="RED",
            )
        )
    if any(_policy_status(item) == "proposed" for item in snapshot.policies):
        proposals.append(
            MetaLoopProposal(
                kind="policy_review",
                title="Review pending policy proposals",
                reason="Policy evolution is additive and review-gated; meta-loop output may only point at pending proposals.",
                evidence_sources=["policy"],
            )
        )
    if snapshot.hibernation is not None:
        proposals.append(
            MetaLoopProposal(
                kind="hibernation_review",
                title="Review hibernation maintenance preview",
                reason="Hibernation output is local-only maintenance evidence and should remain a proposal until approved.",
                evidence_sources=["hibernation"],
                risk="RED" if _hibernation_unsafe(snapshot.hibernation) else "GREEN",
            )
        )
    if snapshot.council_deliberations:
        proposals.append(
            MetaLoopProposal(
                kind="council_self_assessment",
                title="Review council deliberation patterns",
                reason="Council memory can expose recurring uncertainty or review load, but it cannot authorize future work.",
                evidence_sources=["council"],
            )
        )
    return proposals


def _blockers(snapshot: MetaLoopSnapshot) -> list[str]:
    blockers: list[str] = []
    if snapshot.hibernation is not None and _hibernation_unsafe(snapshot.hibernation):
        blockers.append(
            "hibernation evidence reported cloud calls, writes, or non-local behavior; treat as blocked safety evidence"
        )
    return blockers


def _hibernation_unsafe(item: Mapping[str, Any]) -> bool:
    local_only = _bool(item.get("localOnly", item.get("local_only", True)))
    cloud_calls = _int(item.get("cloudCalls", item.get("cloud_calls", 0)))
    writes = _bool(item.get("writesPerformed", item.get("writes_performed", False)))
    return not local_only or cloud_calls > 0 or writes


def _policy_status(item: Any) -> str:
    status = (
        item.get("status") if isinstance(item, Mapping) else getattr(item, "status", "")
    )
    if isinstance(status, Enum):
        return str(status.value).lower()
    return str(status).lower()


def _policy_highlight(item: Any) -> str:
    if isinstance(item, Mapping):
        policy_id = item.get("policy_id", "")
        constraint = item.get("constraint", "")
        status = item.get("status", "")
    else:
        policy_id = getattr(item, "policy_id", "")
        constraint = getattr(item, "constraint", "")
        status = getattr(item, "status", "")
    return _clean(f"{policy_id} {status}: {constraint}".strip())


def _highlights(
    items: Sequence[Mapping[str, Any]],
    keys: tuple[str, ...],
    *,
    limit: int = 3,
) -> list[str]:
    highlights: list[str] = []
    for item in items:
        parts = [str(item[key]) for key in keys if item.get(key)]
        if parts:
            highlights.append(_clean(" - ".join(parts)))
        if len(highlights) >= limit:
            break
    return highlights


def _mapping_items(items: Sequence[Mapping[str, Any]]) -> Iterable[Mapping[str, Any]]:
    for item in items:
        yield {str(key): _clean_value(value) for key, value in item.items()}


def _to_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        raw = value.to_dict()
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raw = dict(getattr(value, "__dict__", {}))
    return {str(key): _clean_value(item) for key, item in raw.items()}


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, Mapping):
        return {str(key): _clean_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clean_value(item) for item in value)
    return value


def _clean(value: Any) -> str:
    return scan_and_redact(str(value)).scrubbed[:240]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


__all__ = [
    "MetaLoopAssessment",
    "MetaLoopProposal",
    "MetaLoopSnapshot",
    "MetaLoopSource",
    "assess_meta_loop",
    "collect_meta_loop_evidence",
]
