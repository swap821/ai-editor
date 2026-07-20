"""Intelligence boundary domain for GAGOS."""

from aios.domain.intelligence.contracts import HiringRequest, HiringDecision
from aios.domain.intelligence.privacy import PrivacyBroker
from aios.domain.intelligence.broker import HiringBroker
from aios.domain.intelligence.repository import HiringRecord, HiringRecordRepository

__all__ = [
    "HiringRequest",
    "HiringDecision",
    "PrivacyBroker",
    "HiringBroker",
    "HiringRecord",
    "HiringRecordRepository",
]
