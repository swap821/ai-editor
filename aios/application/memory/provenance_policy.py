"""What each learned row's signature covers, and who attaches it (Phase 3b).

``docs/learning/PHASE3_DESIGN.md``. A learned row's provenance is signed over a
digest of its RECALL-RELEVANT fields: everything that changes what recall
shows, or whether it shows it, status included. A field left out of the digest
is a field a database-level edit can change without any signature noticing
(threat T11).

The digest functions here are the ONE derivation for both callers: the writer
that attests a row (3b) and the verifier that admits it into a prompt (3c).
Two derivations of "which fields matter" would drift, and the drift would be a
hole (the consistency-attack family).

The writer is best-effort by design. A row whose provenance could not be
appended is simply unsigned, and an unsigned row is never recalled (3c): the
failure is fail-closed, so it must never break the write, or the turn.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from aios.application.governance.emergency_stop import EmergencyStopError
from aios.memory.provenance import (
    LearningSigner,
    Provenance,
    ProvenanceStore,
    content_digest,
)

logger = logging.getLogger(__name__)

#: ``mistake_pool``: what a recalled lesson shows (type, text), what decides
#: whether it is recalled (status, superseded_by), what the self-model counts
#: (occurrence_count), what confirmation matches (failed_command, task_id), and
#: what calibrates the planner (confidence_delta).
LESSON_FIELDS = (
    "task_id",
    "error_type",
    "root_cause",
    "fix_applied",
    "lesson_text",
    "confidence_delta",
    "verification_status",
    "superseded_by",
    "occurrence_count",
    "failed_command",
)


#: ``semantic_memory``: what recall shows (text, type), whether it is recalled
#: (status: Phase 0b withholds unverified chat), and how often it recurred.
SEMANTIC_FIELDS = (
    "text_content",
    "memory_type",
    "verification_status",
    "occurrence_count",
)

#: ``semantic_facts``: the triple recall shows, who approved it (recall admits
#: only human-approved facts), and whether it is still active. ``confidence`` is
#: deliberately NOT covered: auto-extraction bumps it on every chat turn without
#: naming the fact, it changes ranking only, and covering it would make every
#: approved fact's record stale by the next turn.
FACT_FIELDS = ("subject", "predicate", "object", "approved_by", "status")


def _field(row: Any, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, IndexError):
        return None


def lesson_digest(row: Any) -> str:
    """The digest a lesson's provenance covers, from a ``mistake_pool`` row."""
    return content_digest({name: _field(row, name) for name in LESSON_FIELDS})


def semantic_digest(row: Any) -> str:
    """The digest a semantic memory's provenance covers."""
    return content_digest({name: _field(row, name) for name in SEMANTIC_FIELDS})


def fact_digest(row: Any) -> str:
    """The digest a fact's provenance covers."""
    return content_digest({name: _field(row, name) for name in FACT_FIELDS})


class ProvenanceWriter:
    """Attaches signed provenance to rows this process writes, as one kind.

    *source_kind* is the kind this process writes AS. The signer signs it only
    if it holds that kind's seed; otherwise the record is appended unsigned,
    which is honest (the row exists) and inert (it is never recalled).
    """

    def __init__(
        self,
        store: ProvenanceStore,
        signer: LearningSigner,
        *,
        source_kind: str,
    ) -> None:
        self.store = store
        self.signer = signer
        self.source_kind = source_kind
        self.failures = 0
        self.last_failure: Optional[str] = None

    def attest(
        self,
        table: str,
        row_id: Any,
        digest: str,
        transition: str,
        **context: Any,
    ) -> Optional[int]:
        """Append one signed (or unsigned) record for a row's current state.

        Returns the record id, or ``None`` when appending failed. A failure is
        counted and logged, never raised: the row is then unsigned, and an
        unsigned row is never recalled. The emergency stop is the exception. It
        re-raises, because the write it belongs to was refused by the same
        latch a moment earlier, and the record must not outlive that refusal.
        """
        parents = tuple(str(p) for p in (context.pop("parents", None) or ()))
        provenance = Provenance(
            table=table,
            row_id=str(row_id),
            content_sha256=digest,
            source_kind=self.source_kind,
            transition=transition,
            parents=parents,
            **{k: (None if v is None else str(v)) for k, v in context.items()},
        )
        try:
            return self.store.append(provenance, self.signer.sign(provenance))
        except EmergencyStopError:
            raise
        except Exception as exc:  # noqa: BLE001 - counted and shown, fail-closed
            self.failures += 1
            self.last_failure = f"{table}:{row_id}: {type(exc).__name__}: {exc}"[:300]
            logger.warning("provenance not recorded (%s)", self.last_failure)
            return None

    def status(self) -> Mapping[str, Any]:
        return {
            "source_kind": self.source_kind,
            "signs": self.source_kind in self.signer.kinds,
            "failures": self.failures,
            "last_failure": self.last_failure,
        }


__all__ = [
    "FACT_FIELDS",
    "LESSON_FIELDS",
    "ProvenanceWriter",
    "SEMANTIC_FIELDS",
    "fact_digest",
    "lesson_digest",
    "semantic_digest",
]
