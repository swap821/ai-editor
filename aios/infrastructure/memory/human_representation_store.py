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
        subject = f"operator.{pref.domain}.{pref.key}"
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
        record = pref.model_copy(update={"confidence": pref.confidence})
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
                    json.dumps(
                        {k: list(v) for k, v in passport.commands.items()}
                    ),
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


def _passport_from_row(row: sqlite3.Row) -> ProjectPassportV1:
    record = ProjectPassportV1(
        project_id=row["project_id"],
        goal=row["goal"],
        architecture_summary=row["architecture_summary"],
        invariants=tuple(json.loads(row["invariants_json"])),
        important_paths=tuple(json.loads(row["important_paths_json"])),
        commands={
            k: tuple(v) for k, v in json.loads(row["commands_json"]).items()
        },
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
        self, session_id: str, turn_id: str, corrected_state: str
    ) -> bool:
        """Real ground truth for one turn's hypothesis -- ``user_correctable``
        was pinned ``True`` on every hypothesis since organ 30 shipped, but
        nothing ever gave a human a place to actually exercise it. Never
        authoritative: this corrects the durable record only, it cannot
        change anything about the turn that already happened.

        Returns ``False`` (not an error) when no hypothesis exists for this
        session/turn -- a caller-supplied unknown pair is a real, honest
        "nothing to correct", not a system failure."""
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE human_state_hypotheses
                SET corrected_state = ?, corrected_at = ?
                WHERE id = (
                    SELECT id FROM human_state_hypotheses
                    WHERE session_id = ? AND turn_id = ?
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (corrected_state, _utc_now(), session_id, turn_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def accuracy_report(self) -> HumanStateAccuracyReport:
        """Measure the deterministic classifier against every real
        correction recorded so far -- the honest answer to organ 30's own
        "not measured against real production traffic" gap, computed from
        whatever real corrections exist rather than synthetic examples.
        An empty report (``total_corrected == 0``) is itself an honest
        signal: no one has corrected a hypothesis yet, not that the
        classifier is unmeasurable."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT state, corrected_state FROM human_state_hypotheses "
                "WHERE corrected_state IS NOT NULL"
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


__all__ = [
    "HumanStateAccuracyReport",
    "HumanStateHypothesisStore",
    "OperatorPreferenceSaveResult",
    "OperatorPreferenceStore",
    "ProjectPassportStore",
    "RecordTamperedError",
]
