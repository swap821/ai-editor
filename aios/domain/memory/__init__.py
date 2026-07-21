"""Canonical memory contracts used by every specialized memory adapter."""

from .contracts import (
    MemoryHit,
    MemoryProposal,
    MemoryPromotionActor,
    MemoryRecallContext,
    MemoryRecord,
    MemoryRecordProvenance,
    MemoryStatus,
    MemoryVerification,
)
from .human_representation import (
    CorrectionRecordV1,
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)

__all__ = [
    "CorrectionRecordV1",
    "HumanStateHypothesis",
    "MemoryHit",
    "MemoryProposal",
    "MemoryPromotionActor",
    "MemoryRecallContext",
    "MemoryRecord",
    "MemoryRecordProvenance",
    "MemoryStatus",
    "MemoryVerification",
    "OperatorPreferenceV1",
    "ProjectPassportV1",
]
