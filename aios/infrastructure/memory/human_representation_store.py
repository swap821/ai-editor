"""Durable persistence for OperatorPreferenceV1 and ProjectPassportV1
(Tier-1 closure pass, organs 27 and 28).

`OperatorPreferenceStore` is a thin adapter, not a replacement persistence
layer: the core (subject, predicate, object, confidence) triple and its
contradiction-aware write path stay owned by `aios.memory.facts.SemanticFacts`
exactly as this contract's own docstring intends. This store adds only the
typed fields SemanticFacts has no column for, keyed to the fact it decorates.

It never constructs `SemanticFacts` itself -- `tests/test_memory_architecture.py`
quarantines direct legacy-memory-type construction to `aios/api/deps.py`
(production code is meant to route through `MemoryAuthority`'s adapters, per
`aios/application/memory/authority.py`). `facts` is a required, injected
dependency instead: the real caller wires it through `MemoryAuthority`
(`facts_add_fact`/`facts_get`), and tests inject a bare `SemanticFacts`
directly (test files are outside the quarantine's scan).

`ProjectPassportStore` has no existing durable analog to defer to --
`harvest_project_passport()` recomputes a passport from the filesystem every
time, it never persists one -- so this is a genuinely new append-only,
digest-verified history store, following the same convention as
`GovernanceAmendmentStore` (Slice 37).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.infrastructure.storage.migrations import apply_migrations
from aios.memory.db import init_memory_db

_PREFERENCE_PREDICATE = "value"


class FactsLike(Protocol):
    """Structural contract for whatever supplies the core (subject,
    predicate, object, confidence) triple -- a real `SemanticFacts`
    instance in tests, or a `MemoryAuthority` in production."""

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        approved_by: str | None = None,
        confidence: float = 1.0,
    ) -> Any: ...

    def get(self, fact_id: int) -> Any: ...


class RecordTamperedError(RuntimeError):
    """Raised when a stored record's digest no longer matches its content."""


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class OperatorPreferenceSaveResult:
    """Outcome of saving one preference -- a contradiction is surfaced, never
    silently resolved, matching SemanticFacts' own contradiction discipline."""

    __slots__ = ("saved", "reason", "conflict_object")

    def __init__(
        self, *, saved: bool, reason: str, conflict_object: str | None = None
    ) -> None:
        self.saved = saved
        self.reason = reason
        self.conflict_object = conflict_object


class OperatorPreferenceStore:
    """Store and reconstruct OperatorPreferenceV1 records.

    The subject/predicate/object/confidence core is owned by SemanticFacts
    (subject `operator.<domain>.<key>`, predicate "value", object the JSON-
    encoded preference value) -- this class never duplicates its
    contradiction-detection or write logic, only decorates it.
    """

    def __init__(self, db_path: str | Path, *, facts: FactsLike) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        init_memory_db(self.db_path)
        with self._connect() as conn:
            apply_migrations(conn, scope="human_representation")
        self.facts = facts

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, pref: OperatorPreferenceV1) -> OperatorPreferenceSaveResult:
        # `scope` is part of the contradiction-check subject (not just
        # domain+key) -- otherwise two preferences correctly isolated by
        # `list_for_scope` (e.g. the same domain+key in two different
        # projects) would spuriously collide as a "contradiction" the
        # instant they disagreed, even though they were never in conflict.
        subject = f"operator.{pref.scope}.{pref.domain}.{pref.key}"
        value_json = json.dumps(pref.value, sort_keys=True, separators=(",", ":"))
        result = self.facts.add_fact(
            subject, _PREFERENCE_PREDICATE, value_json, confidence=pref.confidence
        )
        if not result.committed or result.fact_id is None:
            return OperatorPreferenceSaveResult(
                saved=False,
                reason=result.reason,
                conflict_object=result.conflict_object,
            )
        # Re-read the fact this store just wrote (or reused) rather than
        # trusting `pref.confidence` -- SemanticFacts.add_fact()'s idempotent
        # "exact triple already exists" path leaves the STORED confidence
        # untouched unless `approved_by` is set (which this store never
        # passes). Digesting the requested-but-not-actually-applied
        # confidence produced a permanent false RecordTamperedError on every
        # later read: re-saving "the same" preference with a different
        # confidence updated the sidecar's digest to a value the fact row
        # never actually held.
        stored_fact = self.facts.get(result.fact_id)
        actual_confidence = (
            float(stored_fact["confidence"])
            if stored_fact is not None
            else pref.confidence
        )
        record = pref.model_copy(update={"confidence": actual_confidence})
        digest = _digest(record.model_dump(mode="json"))
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO operator_preference_sidecar (
                    preference_id, fact_id, domain, key, scope, source_type,
                    source_ids_json, valid_from, review_after, supersedes_json,
                    contradicted_by_json, status, recorded_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(preference_id) DO UPDATE SET
                    fact_id = excluded.fact_id,
                    domain = excluded.domain,
                    key = excluded.key,
                    scope = excluded.scope,
                    source_type = excluded.source_type,
                    source_ids_json = excluded.source_ids_json,
                    valid_from = excluded.valid_from,
                    review_after = excluded.review_after,
                    supersedes_json = excluded.supersedes_json,
                    contradicted_by_json = excluded.contradicted_by_json,
                    status = excluded.status,
                    recorded_at = excluded.recorded_at,
                    record_digest = excluded.record_digest
                """,
                (
                    pref.preference_id,
                    result.fact_id,
                    pref.domain,
                    pref.key,
                    pref.scope,
                    pref.source_type,
                    json.dumps(list(pref.source_ids)),
                    pref.valid_from,
                    pref.review_after,
                    json.dumps(list(pref.supersedes)),
                    json.dumps(list(pref.contradicted_by)),
                    pref.status,
                    _utc_now(),
                    digest,
                ),
            )
            conn.commit()
        return OperatorPreferenceSaveResult(saved=True, reason=result.reason)

    def get(self, preference_id: str) -> OperatorPreferenceV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM operator_preference_sidecar WHERE preference_id = ?",
                (preference_id,),
            ).fetchone()
        if row is None:
            return None
        return self._reconstruct(row)

    def list_for_scope(self, scope: str) -> tuple[OperatorPreferenceV1, ...]:
        """Every lookup is scope-filtered by construction -- there is no
        "all preferences regardless of scope" method, which is exactly the
        leak-prevention this organ's ledger entry names."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM operator_preference_sidecar WHERE scope = ? "
                "ORDER BY recorded_at ASC",
                (scope,),
            ).fetchall()
        records = (self._reconstruct(row) for row in rows)
        return tuple(record for record in records if record is not None)

    def list_active_for_scope(self, scope: str) -> tuple[OperatorPreferenceV1, ...]:
        """The subset of `list_for_scope` a real consumer (Organ 31's
        `active_preferences` parameter) would feed forward -- `status`
        alone is filtered here; a caller also wanting to drop expired
        preferences composes this with `is_operator_preference_expired`
        (application layer), since this store only ever depends on the
        domain layer, never upward on application code."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM operator_preference_sidecar "
                "WHERE scope = ? AND status = 'active' ORDER BY recorded_at ASC",
                (scope,),
            ).fetchall()
        records = (self._reconstruct(row) for row in rows)
        return tuple(record for record in records if record is not None)

    def withdraw(self, preference_id: str) -> bool:
        """Organ 27's withdrawal support: an operator can retract a
        preference they previously stated. Reuses `save()`'s existing
        upsert-by-preference_id path rather than a second write path, so
        withdrawal stays digest-verified and idempotent the same way every
        other mutation on this row already is. Returns `False` (no-op) for
        an unknown preference_id instead of raising -- withdrawing
        something that was never recorded is not an error condition."""
        current = self.get(preference_id)
        if current is None:
            return False
        result = self.save(current.model_copy(update={"status": "withdrawn"}))
        return result.saved

    def _reconstruct(self, row: sqlite3.Row) -> OperatorPreferenceV1 | None:
        fact = self.facts.get(int(row["fact_id"]))
        if fact is None:
            return None
        record = OperatorPreferenceV1(
            preference_id=row["preference_id"],
            domain=row["domain"],
            key=row["key"],
            value=json.loads(str(fact["object"])),
            scope=row["scope"],
            confidence=float(fact["confidence"]),
            source_type=row["source_type"],
            source_ids=tuple(json.loads(row["source_ids_json"])),
            valid_from=row["valid_from"],
            review_after=row["review_after"],
            supersedes=tuple(json.loads(row["supersedes_json"])),
            contradicted_by=tuple(json.loads(row["contradicted_by_json"])),
            status=row["status"],
        )
        recomputed = _digest(record.model_dump(mode="json"))
        if recomputed != row["record_digest"]:
            raise RecordTamperedError(
                f"stored preference digest mismatch for {row['preference_id']!r}: "
                "the row was altered outside this store"
            )
        return record


class ProjectPassportStore:
    """Append-only, digest-verified history for ProjectPassportV1 --
    genuinely new persistence, no existing store to defer to."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="human_representation")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, passport: ProjectPassportV1) -> int:
        digest = _digest(passport.model_dump(mode="json"))
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM project_passports "
                "WHERE project_id = ?",
                (passport.project_id,),
            ).fetchone()
            revision = int(row[0]) + 1
            conn.execute(
                """
                INSERT INTO project_passports (
                    project_id, revision, goal, architecture_summary,
                    invariants_json, important_paths_json, commands_json,
                    environments_json, current_phase, known_risks_json,
                    explicit_human_decisions_json, verified_at_commit,
                    passport_digest, recorded_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    passport.project_id,
                    revision,
                    passport.goal,
                    passport.architecture_summary,
                    json.dumps(list(passport.invariants)),
                    json.dumps(list(passport.important_paths)),
                    json.dumps({k: list(v) for k, v in passport.commands.items()}),
                    json.dumps(list(passport.environments)),
                    passport.current_phase,
                    json.dumps(list(passport.known_risks)),
                    json.dumps(list(passport.explicit_human_decisions)),
                    passport.verified_at_commit,
                    passport.passport_digest,
                    _utc_now(),
                    digest,
                ),
            )
            conn.commit()
        return revision

    def get_current(self, project_id: str) -> ProjectPassportV1 | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM project_passports WHERE project_id = ? "
                "ORDER BY revision DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return _passport_from_row(row)

    def get_history(self, project_id: str) -> tuple[ProjectPassportV1, ...]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM project_passports WHERE project_id = ? "
                "ORDER BY revision ASC",
                (project_id,),
            ).fetchall()
        return tuple(_passport_from_row(row) for row in rows)

    def set_active(self, project_id: str, summary: dict[str, Any]) -> None:
        """Durably record which project was most recently scanned --
        organ 28's own named gap: previously this lived only in a
        process-local module global in ``routes/projects.py`` and was
        silently lost on every restart, even though the scan history
        itself (``project_passports``) was already durable."""
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO active_project_pointer (
                    id, project_id, last_scan_summary_json, updated_at
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    last_scan_summary_json = excluded.last_scan_summary_json,
                    updated_at = excluded.updated_at
                """,
                (project_id, json.dumps(summary), _utc_now()),
            )
            conn.commit()

    def get_active(self) -> tuple[str, dict[str, Any]] | None:
        """Return (project_id, last_scan_summary) for the active project,
        surviving a process restart -- ``None`` only when nothing has ever
        been scanned, not merely because this process just started."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT project_id, last_scan_summary_json "
                "FROM active_project_pointer WHERE id = 1"
            ).fetchone()
        if row is None:
            return None
        return row["project_id"], json.loads(row["last_scan_summary_json"])


def _passport_from_row(row: sqlite3.Row) -> ProjectPassportV1:
    record = ProjectPassportV1(
        project_id=row["project_id"],
        goal=row["goal"],
        architecture_summary=row["architecture_summary"],
        invariants=tuple(json.loads(row["invariants_json"])),
        important_paths=tuple(json.loads(row["important_paths_json"])),
        commands={k: tuple(v) for k, v in json.loads(row["commands_json"]).items()},
        environments=tuple(json.loads(row["environments_json"])),
        current_phase=row["current_phase"],
        known_risks=tuple(json.loads(row["known_risks_json"])),
        explicit_human_decisions=tuple(
            json.loads(row["explicit_human_decisions_json"])
        ),
        verified_at_commit=row["verified_at_commit"],
        passport_digest=row["passport_digest"],
    )
    recomputed = _digest(record.model_dump(mode="json"))
    if recomputed != row["record_digest"]:
        raise RecordTamperedError(
            f"stored project passport digest mismatch for {row['project_id']!r}: "
            "the row was altered outside this store"
        )
    return record


class HumanStateAccuracyReport:
    """Real measured accuracy of ``classify_human_state()`` against actual
    human corrections -- organ 30's own named gap ("not measured against
    real production traffic") answered with real data instead of left
    permanently open. ``total_corrected`` is the only trustworthy
    denominator: an un-corrected hypothesis is not evidence of either
    correctness or error, so it is excluded rather than assumed correct."""

    __slots__ = ("total_corrected", "agreements", "by_state")

    def __init__(
        self,
        *,
        total_corrected: int,
        agreements: int,
        by_state: dict[str, dict[str, int]],
    ) -> None:
        self.total_corrected = total_corrected
        self.agreements = agreements
        self.by_state = by_state

    @property
    def accuracy(self) -> float | None:
        if self.total_corrected == 0:
            return None
        return self.agreements / self.total_corrected

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_corrected": self.total_corrected,
            "agreements": self.agreements,
            "accuracy": self.accuracy,
            "by_state": self.by_state,
        }


class HumanStateHypothesisStore:
    """Organ 30: append-only history of ``classify_human_state()`` outputs,
    one row per live conversation turn.

    ``HumanStateHypothesis`` carries no session/turn identity of its own
    (a pure classification result) -- ``save()`` supplies it externally,
    the same pattern ``MissionTransitionJournal`` uses for a domain-agnostic
    event keyed onto a caller-supplied ``mission_id``.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="human_representation")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(
        self, session_id: str, turn_id: str, hypothesis: HumanStateHypothesis
    ) -> None:
        digest = _digest(hypothesis.model_dump(mode="json"))
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO human_state_hypotheses (
                    session_id, turn_id, state, confidence, visible_reason,
                    recorded_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
                    hypothesis.state,
                    hypothesis.confidence,
                    hypothesis.visible_reason,
                    _utc_now(),
                    digest,
                ),
            )
            conn.commit()

    def get_history(
        self, session_id: str
    ) -> tuple[tuple[str, HumanStateHypothesis], ...]:
        """(turn_id, hypothesis) pairs for one session, oldest first."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM human_state_hypotheses WHERE session_id = ? "
                "ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        results: list[tuple[str, HumanStateHypothesis]] = []
        for row in rows:
            hypothesis = HumanStateHypothesis(
                state=row["state"],
                confidence=row["confidence"],
                visible_reason=row["visible_reason"],
            )
            recomputed = _digest(hypothesis.model_dump(mode="json"))
            if recomputed != row["record_digest"]:
                raise RecordTamperedError(
                    "stored human-state hypothesis digest mismatch for turn "
                    f"{row['turn_id']!r}: the row was altered outside this store"
                )
            results.append((str(row["turn_id"]), hypothesis))
        return tuple(results)

    def record_correction(
        self,
        session_id: str,
        turn_id: str,
        corrected_state: str,
        *,
        operator_id: str | None = None,
    ) -> bool:
        """Real ground truth for one turn's hypothesis -- ``user_correctable``
        was pinned ``True`` on every hypothesis since organ 30 shipped, but
        nothing ever gave a human a place to actually exercise it. Never
        authoritative: this corrects the durable record only, it cannot
        change anything about the turn that already happened.

        Appends a new row to ``human_state_corrections`` rather than
        mutating the original hypothesis row -- a correction is a genuinely
        new event, digested over the hypothesis's own digest plus the
        correction's own fields, so altering a correction after the fact is
        detectable exactly like altering a hypothesis already is.
        ``operator_id`` is best-effort and honestly nullable: this route is
        reachable from an unauthenticated local session by design, and
        recording ``None`` is more honest than fabricating an identity.

        Returns ``False`` (not an error) when no hypothesis exists for this
        session/turn -- a caller-supplied unknown pair is a real, honest
        "nothing to correct", not a system failure."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, record_digest FROM human_state_hypotheses "
                "WHERE session_id = ? AND turn_id = ? ORDER BY id DESC LIMIT 1",
                (session_id, turn_id),
            ).fetchone()
            if row is None:
                return False
            hypothesis_id = int(row["id"])
            hypothesis_digest = str(row["record_digest"])
            corrected_at = _utc_now()
            correction_digest = _digest(
                {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "hypothesis_digest": hypothesis_digest,
                    "corrected_state": corrected_state,
                    "operator_id": operator_id,
                    "corrected_at": corrected_at,
                }
            )
            conn.execute(
                """
                INSERT INTO human_state_corrections (
                    session_id, turn_id, hypothesis_id, hypothesis_digest,
                    corrected_state, operator_id, corrected_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
                    hypothesis_id,
                    hypothesis_digest,
                    corrected_state,
                    operator_id,
                    corrected_at,
                    correction_digest,
                ),
            )
            conn.commit()
            return True

    def get_corrections(
        self, session_id: str, turn_id: str
    ) -> tuple[dict[str, Any], ...]:
        """Every correction ever recorded for one turn, oldest first, with
        tamper detection on each row. Plural (not "the" correction) because
        a human may correct the same turn more than once -- the newest row
        is the current ground truth; the rest are retained history, never
        deleted or overwritten."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM human_state_corrections "
                "WHERE session_id = ? AND turn_id = ? ORDER BY id ASC",
                (session_id, turn_id),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            recomputed = _digest(
                {
                    "session_id": row["session_id"],
                    "turn_id": row["turn_id"],
                    "hypothesis_digest": row["hypothesis_digest"],
                    "corrected_state": row["corrected_state"],
                    "operator_id": row["operator_id"],
                    "corrected_at": row["corrected_at"],
                }
            )
            if recomputed != row["record_digest"]:
                raise RecordTamperedError(
                    "stored human-state correction digest mismatch for turn "
                    f"{row['turn_id']!r}: the row was altered outside this store"
                )
            results.append(
                {
                    "sessionId": row["session_id"],
                    "turnId": row["turn_id"],
                    "hypothesisDigest": row["hypothesis_digest"],
                    "correctedState": row["corrected_state"],
                    "operatorId": row["operator_id"],
                    "correctedAt": row["corrected_at"],
                }
            )
        return tuple(results)

    def accuracy_report(self) -> HumanStateAccuracyReport:
        """Measure the deterministic classifier against every real
        correction recorded so far -- the honest answer to organ 30's own
        "not measured against real production traffic" gap, computed from
        whatever real corrections exist rather than synthetic examples.
        An empty report (``total_corrected == 0``) is itself an honest
        signal: no one has corrected a hypothesis yet, not that the
        classifier is unmeasurable.

        Joins on each hypothesis's own row id (not its content digest --
        two hypotheses can share identical content and therefore an
        identical digest, which would otherwise silently fold distinct
        corrections together) so a correction always measures against the
        exact hypothesis it was recorded against, and only ever the newest
        correction per hypothesis counts -- a superseded correction is
        history, not a second vote."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT h.state AS state, c.corrected_state AS corrected_state
                FROM human_state_hypotheses h
                JOIN human_state_corrections c ON c.hypothesis_id = h.id
                WHERE c.id = (
                    SELECT MAX(id) FROM human_state_corrections c2
                    WHERE c2.hypothesis_id = c.hypothesis_id
                )
                """
            ).fetchall()
        by_state: dict[str, dict[str, int]] = {}
        agreements = 0
        for row in rows:
            state = str(row["state"])
            bucket = by_state.setdefault(state, {"total": 0, "agreements": 0})
            bucket["total"] += 1
            if row["corrected_state"] == state:
                bucket["agreements"] += 1
                agreements += 1
        return HumanStateAccuracyReport(
            total_corrected=len(rows), agreements=agreements, by_state=by_state
        )


class CorrectionRecordStore:
    """Organ 29: append-only, digest-verified, operator-attributed history
    for `CorrectionRecordV1`.

    `ConversationStateStore.conversation_corrections` remains the durable
    owner of the underlying before/after frames and supersession lifecycle
    -- this store does not replace it, it is the typed read/audit view this
    organ's own contract names, populated by a real caller
    (``POST /api/v1/conversation/correction``) for the first time.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn, scope="human_representation")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, record: CorrectionRecordV1) -> None:
        digest = _digest(record.model_dump(mode="json"))
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO correction_records (
                    correction_id, session_id, base_revision, correction_revision,
                    corrected_fields_json, prior_interpretation_digest,
                    current_interpretation_digest, source, operator_id,
                    created_at, record_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.correction_id,
                    record.session_id,
                    record.base_revision,
                    record.correction_revision,
                    json.dumps(list(record.corrected_fields)),
                    record.prior_interpretation_digest,
                    record.current_interpretation_digest,
                    record.source,
                    record.operator_id,
                    record.created_at,
                    digest,
                ),
            )
            conn.commit()

    def get_lineage(
        self, session_id: str, limit: int = 20
    ) -> tuple[CorrectionRecordV1, ...]:
        """Every recorded correction for one session, newest first, with
        tamper detection on each row."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM correction_records WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return tuple(self._reconstruct(row) for row in rows)

    def _reconstruct(self, row: sqlite3.Row) -> CorrectionRecordV1:
        record = CorrectionRecordV1(
            correction_id=row["correction_id"],
            session_id=row["session_id"],
            base_revision=row["base_revision"],
            correction_revision=row["correction_revision"],
            corrected_fields=tuple(json.loads(row["corrected_fields_json"])),
            prior_interpretation_digest=row["prior_interpretation_digest"],
            current_interpretation_digest=row["current_interpretation_digest"],
            source=row["source"],
            operator_id=row["operator_id"],
            created_at=row["created_at"],
        )
        recomputed = _digest(record.model_dump(mode="json"))
        if recomputed != row["record_digest"]:
            raise RecordTamperedError(
                f"stored correction record digest mismatch for {row['correction_id']!r}: "
                "the row was altered outside this store"
            )
        return record


__all__ = [
    "CorrectionRecordStore",
    "HumanStateAccuracyReport",
    "HumanStateHypothesisStore",
    "OperatorPreferenceSaveResult",
    "OperatorPreferenceStore",
    "ProjectPassportStore",
    "RecordTamperedError",
]
