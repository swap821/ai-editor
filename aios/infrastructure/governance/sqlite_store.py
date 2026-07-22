"""SQLite persistence for the Constitutional Amendment Authority (Slice 37)
and Constitutional Learning Organ (Slice 38) -- reconciliation pass item 6.

Both organs shipped as pure, in-memory pipelines: every state transition
(`propose_amendment`, `critique_amendment`, ..., `activate_amendment`) built
a new `model_copy` but nothing durable ever recorded it. A process restart
mid-ratification silently lost the proposal's entire history. This module
adds the missing durable half only -- storage, not new authority. Every
transition function in `amendment_authority.py` / `constitutional_learning.py`
is unchanged; callers now additionally persist each returned object here.

Rows are append-only per `(id, revision)`, matching the correction-lineage
convention from Slice 28 (prior interpretation retained, current
interpretation added as a new row) rather than upserted in place -- so the
full propose -> critique -> simulate -> ratify -> activate/reject/rollback
sequence for a proposal remains inspectable after the fact, not just its
current status. Each row carries a `record_digest` (sha256 of the
canonical-JSON dump, the same convention as `LocalWorkforceProvenanceStore`)
verified at read time.

Deliberately out of scope here (see the reconciliation-pass ledger note for
organs 37/38): wiring a real HTTP route for
`CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION` and registering it in
`aios.domain.actions.envelope.ActionType` / the capability-issuance table.
`amendments.py` already documents that as separate follow-up work, not
assumed by Slice 37 -- this module does not change that scope.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from aios.domain.governance.amendments import ConstitutionalAmendmentProposalV1
from aios.domain.governance.learning import GovernanceLessonV1
from aios.infrastructure.storage.migrations import apply_migrations


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class GovernanceAmendmentStore:
    """Durable, append-only history for `ConstitutionalAmendmentProposalV1`
    and `GovernanceLessonV1`. Each `save_*` call adds one new revision row;
    it never overwrites a prior one, so a caller cannot lose earlier history
    by saving again."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="governance")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_proposal(self, proposal: ConstitutionalAmendmentProposalV1) -> int:
        payload = proposal.model_dump(mode="json")
        digest = _digest(payload)
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM "
                "governance_amendment_proposals WHERE proposal_id = ?",
                (proposal.proposal_id,),
            ).fetchone()
            revision = int(row[0]) + 1
            conn.execute(
                """
                INSERT INTO governance_amendment_proposals (
                    proposal_id, revision, target_articles_json, proposed_diff,
                    motivation, incident_refs_json, evidence_refs_json,
                    threat_model_json, expected_benefits_json, new_risks_json,
                    migration_plan, rollback_plan, proposed_by, proposer_type,
                    status, critiques_json, simulation_notes_json,
                    ratified_by_operator_id, ratification_capability_digest,
                    created_at, recorded_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    revision,
                    json.dumps(list(proposal.target_articles)),
                    proposal.proposed_diff,
                    proposal.motivation,
                    json.dumps(list(proposal.incident_refs)),
                    json.dumps(list(proposal.evidence_refs)),
                    json.dumps(list(proposal.threat_model)),
                    json.dumps(list(proposal.expected_benefits)),
                    json.dumps(list(proposal.new_risks)),
                    proposal.migration_plan,
                    proposal.rollback_plan,
                    proposal.proposed_by,
                    proposal.proposer_type,
                    proposal.status,
                    json.dumps(list(proposal.critiques)),
                    json.dumps(list(proposal.simulation_notes)),
                    proposal.ratified_by_operator_id,
                    proposal.ratification_capability_digest,
                    proposal.created_at,
                    _utc_now(),
                    digest,
                ),
            )
            conn.commit()
        return revision

    def get_current_proposal(
        self, proposal_id: str
    ) -> ConstitutionalAmendmentProposalV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM governance_amendment_proposals "
                "WHERE proposal_id = ? ORDER BY revision DESC LIMIT 1",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return None
        return _proposal_from_row(row)

    def get_proposal_history(
        self, proposal_id: str
    ) -> tuple[ConstitutionalAmendmentProposalV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM governance_amendment_proposals "
                "WHERE proposal_id = ? ORDER BY revision ASC",
                (proposal_id,),
            ).fetchall()
        return tuple(_proposal_from_row(row) for row in rows)

    def save_lesson(self, lesson: GovernanceLessonV1) -> int:
        payload = lesson.model_dump(mode="json")
        digest = _digest(payload)
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM governance_lessons "
                "WHERE lesson_id = ?",
                (lesson.lesson_id,),
            ).fetchone()
            revision = int(row[0]) + 1
            conn.execute(
                """
                INSERT INTO governance_lessons (
                    lesson_id, revision, problem_class, evidence_refs_json,
                    observed_harm, current_rule, proposed_improvement,
                    confidence, amendment_proposal_id, status, created_at,
                    recorded_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson.lesson_id,
                    revision,
                    lesson.problem_class,
                    json.dumps(list(lesson.evidence_refs)),
                    lesson.observed_harm,
                    lesson.current_rule,
                    lesson.proposed_improvement,
                    lesson.confidence,
                    lesson.amendment_proposal_id,
                    lesson.status,
                    lesson.created_at,
                    _utc_now(),
                    digest,
                ),
            )
            conn.commit()
        return revision

    def get_current_lesson(self, lesson_id: str) -> GovernanceLessonV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM governance_lessons WHERE lesson_id = ? "
                "ORDER BY revision DESC LIMIT 1",
                (lesson_id,),
            ).fetchone()
        if row is None:
            return None
        return _lesson_from_row(row)

    def get_lesson_history(self, lesson_id: str) -> tuple[GovernanceLessonV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM governance_lessons WHERE lesson_id = ? "
                "ORDER BY revision ASC",
                (lesson_id,),
            ).fetchall()
        return tuple(_lesson_from_row(row) for row in rows)


def _proposal_from_row(row: sqlite3.Row) -> ConstitutionalAmendmentProposalV1:
    record = ConstitutionalAmendmentProposalV1(
        proposal_id=row["proposal_id"],
        target_articles=tuple(json.loads(row["target_articles_json"])),
        proposed_diff=row["proposed_diff"],
        motivation=row["motivation"],
        incident_refs=tuple(json.loads(row["incident_refs_json"])),
        evidence_refs=tuple(json.loads(row["evidence_refs_json"])),
        threat_model=tuple(json.loads(row["threat_model_json"])),
        expected_benefits=tuple(json.loads(row["expected_benefits_json"])),
        new_risks=tuple(json.loads(row["new_risks_json"])),
        migration_plan=row["migration_plan"],
        rollback_plan=row["rollback_plan"],
        proposed_by=row["proposed_by"],
        proposer_type=row["proposer_type"],
        status=row["status"],
        critiques=tuple(json.loads(row["critiques_json"])),
        simulation_notes=tuple(json.loads(row["simulation_notes_json"])),
        ratified_by_operator_id=row["ratified_by_operator_id"],
        ratification_capability_digest=row["ratification_capability_digest"],
        created_at=row["created_at"],
    )
    _verify(record, row["record_digest"])
    return record


def _lesson_from_row(row: sqlite3.Row) -> GovernanceLessonV1:
    record = GovernanceLessonV1(
        lesson_id=row["lesson_id"],
        problem_class=row["problem_class"],
        evidence_refs=tuple(json.loads(row["evidence_refs_json"])),
        observed_harm=row["observed_harm"],
        current_rule=row["current_rule"],
        proposed_improvement=row["proposed_improvement"],
        confidence=row["confidence"],
        amendment_proposal_id=row["amendment_proposal_id"],
        status=row["status"],
        created_at=row["created_at"],
    )
    _verify(record, row["record_digest"])
    return record


def _verify(
    record: ConstitutionalAmendmentProposalV1 | GovernanceLessonV1,
    stored_digest: str,
) -> None:
    recomputed = _digest(record.model_dump(mode="json"))
    if recomputed != stored_digest:
        raise RecordTamperedError(
            f"stored record digest mismatch for {type(record).__name__}: "
            "the row was altered outside this store"
        )


__all__ = ["GovernanceAmendmentStore", "RecordTamperedError"]
