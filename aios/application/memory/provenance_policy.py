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
from aios.domain.learning.repository import (
    SKILL_DIGEST_FIELDS,
    SKILL_PROVENANCE_TABLE,
    skill_digest,
    skill_row_id,
)
from aios.memory.provenance import (
    LearningSigner,
    LearningVerifier,
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

    **A new state of an existing row is signed only if the state it extends
    verifies** (``attest_transition``). Otherwise a row nobody signed -- a
    legacy row, or one written straight into the database -- would be signed
    the first time a real event touched it: a genuine failure recurring onto an
    injected lesson keeps the injected TEXT, and a real success promotes it.
    That would launder it into trusted memory, which the design forbids:
    re-admission is by re-earning, or by the operator.
    """

    def __init__(
        self,
        store: ProvenanceStore,
        signer: LearningSigner,
        *,
        source_kind: str,
        verifier: Optional[LearningVerifier] = None,
    ) -> None:
        self.store = store
        self.signer = signer
        self.source_kind = source_kind
        #: Pinned keys. Without them no transition can be proven to extend a
        #: signed state, so every transition is recorded unsigned.
        self.verifier = verifier
        self.failures = 0
        self.last_failure: Optional[str] = None
        #: Transitions recorded unsigned because the state they extend did not
        #: verify: a count the doctor can show, never an error.
        self.unsigned_transitions = 0

    def attest_new(
        self, table: str, row_id: Any, digest: str, transition: str, **context: Any
    ) -> Optional[int]:
        """A row this write CREATED: signed if this process holds the key."""
        return self._append(
            self._provenance(table, row_id, digest, transition, context), sign=True
        )

    def attest_transition(
        self,
        table: str,
        row_id: Any,
        digest: str,
        transition: str,
        *,
        prior_digest: Optional[str],
        **context: Any,
    ) -> Optional[int]:
        """A new state of an EXISTING row: signed only if its prior state verifies.

        *prior_digest* is the row's digest just before the write, or ``None``
        when it could not be captured (a race, or a different row matched),
        which is treated as unverifiable: fail-closed.
        """
        provenance = self._provenance(table, row_id, digest, transition, context)
        return self._append(
            provenance, sign=self._extends_a_signed_state(table, row_id, prior_digest)
        )

    def attest_approval(
        self,
        table: str,
        row_id: Any,
        digest: str,
        transition: str,
        *,
        approver: str,
        **context: Any,
    ) -> Optional[int]:
        """A state a HUMAN approved, signed if this process holds the key.

        Plan Phase 4c-2: the operator's activation of a skill. No signed prior
        state is required -- the approval vouches for exactly this content,
        as a re-admission does -- so it must name its approver.
        """
        if not str(approver or "").strip():
            raise ValueError("an approval must name its approver")
        provenance = self._provenance(
            table, row_id, digest, transition, {**context, "approver": approver}
        )
        return self._append(provenance, sign=True)

    def _extends_a_signed_state(
        self, table: str, row_id: Any, prior_digest: Optional[str]
    ) -> bool:
        if self.verifier is None or prior_digest is None:
            return False
        try:
            prior = self.store.latest(table, str(row_id))
        except Exception:  # noqa: BLE001 - unreadable proves nothing
            return False
        return self.verifier.verify(
            prior, content_sha256=prior_digest, context=self.source_kind
        ).admitted

    def _provenance(
        self,
        table: str,
        row_id: Any,
        digest: str,
        transition: str,
        context: dict[str, Any],
    ) -> Provenance:
        parents = tuple(str(p) for p in (context.pop("parents", None) or ()))
        return Provenance(
            table=table,
            row_id=str(row_id),
            content_sha256=digest,
            source_kind=self.source_kind,
            transition=transition,
            parents=parents,
            **{k: (None if v is None else str(v)) for k, v in context.items()},
        )

    def _append(self, provenance: Provenance, *, sign: bool) -> Optional[int]:
        """Append one record. A failure is counted and logged, never raised: the
        row is then unsigned, and an unsigned row is never recalled. The
        emergency stop is the exception. It re-raises, because the write it
        belongs to was refused by the same latch a moment earlier, and the
        record must not outlive that refusal.
        """
        if not sign:
            self.unsigned_transitions += 1
        try:
            return self.store.append(
                provenance, self.signer.sign(provenance) if sign else None
            )
        except EmergencyStopError:
            raise
        except Exception as exc:  # noqa: BLE001 - counted and shown, fail-closed
            self.failures += 1
            self.last_failure = (
                f"{provenance.table}:{provenance.row_id}: {type(exc).__name__}: {exc}"
            )[:300]
            logger.warning("provenance not recorded (%s)", self.last_failure)
            return None

    def status(self) -> Mapping[str, Any]:
        return {
            "source_kind": self.source_kind,
            "signs": self.source_kind in self.signer.kinds,
            "verifies_chains": self.verifier is not None,
            "failures": self.failures,
            "last_failure": self.last_failure,
            "unsigned_transitions": self.unsigned_transitions,
        }


class RecallGate:
    """Admits a learned row into a prompt only if it can prove where it came from.

    Plan Phase 3c (``docs/learning/PHASE3_DESIGN.md``). A row is admitted only
    if its NEWEST provenance record verifies under a pinned key whose kind the
    context admits, over the row's CURRENT digest. The digest is the same
    function the writer signed, one derivation for both callers. Everything
    else is refused, never "included with a warning": Phase 0b showed that a
    header is advice, not a boundary.

    Plan Phase 4c (principal scoping; operator decision 2026-10-04): a row is
    admitted only for the principal its SIGNED provenance names -- never on a
    column, which anyone with the database could edit. A recall that does not
    say who is asking is refused; so is a row learned before scoping, which
    names nobody (withheld until re-earned or readmitted by the operator).

    Refusals are counted by reason for the operator and logged once per row.
    Nothing here writes, so a recall under the emergency stop still reads.
    """

    def __init__(
        self,
        store: ProvenanceStore,
        verifier: LearningVerifier,
        *,
        context: str = "live",
    ) -> None:
        self.store = store
        self.verifier = verifier
        self.context = context
        self.admitted = 0
        self.refused: dict[str, int] = {}
        #: The same refusals, by the table the row lives in.
        self.refused_by_table: dict[str, dict[str, int]] = {}
        self._logged: set[tuple[str, str]] = set()

    def admits(
        self, table: str, row_id: Any, digest: str, *, principal: Optional[str]
    ) -> bool:
        if not principal:
            return self._refuse(
                table, row_id, "no principal: the recall did not say who is asking"
            )
        try:
            signed = self.store.latest(table, str(row_id))
        except Exception as exc:  # noqa: BLE001 - unreadable proves nothing
            return self._refuse(table, row_id, f"provenance unreadable: {exc}")
        verdict = self.verifier.verify(
            signed, content_sha256=digest, context=self.context
        )
        if not verdict.admitted or signed is None:
            return self._refuse(table, row_id, verdict.reason)
        owner = signed.provenance.principal
        if not owner:
            return self._refuse(
                table, row_id, "unattributed: learned before principal scoping"
            )
        if owner != principal:
            return self._refuse(table, row_id, "another principal")
        self.admitted += 1
        return True

    def _refuse(self, table: str, row_id: Any, reason: str) -> bool:
        key = reason.split(":", 1)[0]
        self.refused[key] = self.refused.get(key, 0) + 1
        per_table = self.refused_by_table.setdefault(table, {})
        per_table[key] = per_table.get(key, 0) + 1
        if (table, str(row_id)) not in self._logged:
            self._logged.add((table, str(row_id)))
            logger.info("recall refused %s:%s (%s)", table, row_id, reason)
        return False

    def status(self) -> Mapping[str, Any]:
        return {
            "context": self.context,
            "admitted": self.admitted,
            "refused": dict(self.refused),
            "refused_by_table": {
                table: dict(counts) for table, counts in self.refused_by_table.items()
            },
        }


__all__ = [
    "FACT_FIELDS",
    "RecallGate",
    "LESSON_FIELDS",
    "ProvenanceWriter",
    "SEMANTIC_FIELDS",
    "SKILL_DIGEST_FIELDS",
    "SKILL_PROVENANCE_TABLE",
    "fact_digest",
    "lesson_digest",
    "semantic_digest",
    "skill_digest",
    "skill_row_id",
]
