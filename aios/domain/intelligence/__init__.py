"""Intelligence boundary domain for GAGOS."""

from aios.domain.intelligence.contracts import HiringRequest, HiringDecision
from aios.domain.intelligence.deliberation import (
    DeliberationRecord,
    DeliberationRole,
    DeliberationRoleName,
    ModelPosition,
)
from aios.domain.intelligence.privacy import PrivacyBroker
from aios.domain.intelligence.broker import HiringBroker
from aios.domain.intelligence.repository import HiringRecord, HiringRecordRepository
from aios.domain.intelligence.representative_context import (
    PreferenceProjection,
    RepresentativeContextV1,
)

__all__ = [
    "DeliberationRecord",
    "DeliberationRole",
    "DeliberationRoleName",
    "HiringRequest",
    "HiringDecision",
    "ModelPosition",
    "PreferenceProjection",
    "PrivacyBroker",
    "HiringBroker",
    "HiringRecord",
    "HiringRecordRepository",
    "RepresentativeContextV1",
]
