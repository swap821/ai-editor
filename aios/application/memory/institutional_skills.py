"""The live skills slot served by the institutional skill library (Phase 2 slice 2.4).

Operator decision (2026-09-25): the institutional library, which organ 43
governs, becomes the live skill store. This adapter gives the memory authority's
``skills`` slot the same interface ``SkillMemoryAdapter`` has, backed by
``SkillRepository`` instead of ``procedural_skills``. Swapping the slot in
``bootstrap.py`` is then the whole switch: the authority, the turn pipeline and
every caller keep calling the same operations (``docs/learning/PHASE2_DESIGN.md``).

What changes in meaning, on purpose
-----------------------------------
* **Nothing promotes itself.** The legacy store flipped an arc to ``verified``
  after three floor-meeting successes. Here an arc is born ``candidate``, and only
  the operator activates it, with a capability proof. Evidence accumulates, and a
  candidate that meets the old promotion rule is reported ``review_ready``.
* **Recall and reuse credit read ACTIVE skills only**, the institutional
  equivalent of ``verified``.
* **Demotion is organ 43's.** Failures go through
  ``SkillLifecycleAuthority.apply_reuse_outcome``, so an active skill that keeps
  failing is demoted by the library's own policy. A success never promotes.
* **A reviewed contract is never rewritten.** The legacy "better recipe" refresh
  still applies to a candidate, whose contract may be refined before review, and
  is skipped for anything reviewed (the store refuses it anyway).

Identity
--------
The turn path, the planners, the cerebellum's foreign key and the frontend all
carry a skill as an INTEGER. The library's identity is ``(skill_id, version)`` in
a different database file. ``SkillTrailIndex`` maps a stable integer *trail id*
to each institutional skill. A migrated skill keeps its legacy
``procedural_skills.id``, so nothing typed as an integer changed at the switch,
and a new arc takes a library-issued id (from ``LIBRARY_ID_BASE``). The table
also holds the live ranking bookkeeping the contract has no place for (reuse
pheromone, last reuse).

Since slice 2.4c-B this is the ONLY skill store. ``procedural_skills`` is
read-only history, and there is no mode to choose.

Every write asks the emergency stop first, the ranking counters included.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from aios import config
from aios.application.governance.emergency_stop import EmergencyStopError
from aios.application.memory import write_budget
from aios.application.learning.skill_lifecycle import SkillLifecycleAuthority
from aios.core.verification_strength import VerificationStrength, meets_learning_floor
from aios.domain.learning.repository import SkillRecord, SkillRepository
from aios.domain.learning.skill_contracts import BIRTH_STATE
from aios.domain.memory.contracts import MemoryHit, MemoryRecallContext
from aios.memory.construction_ledger import record_construction
from aios.memory.learning_freeze import assert_learning_permitted
from aios.memory.relevance import relevance, skill_signature_v2
from aios.memory.skills import ReadOnlySkillHistoryError, SkillMemory, _better_recipe
from aios.security.secret_scanner import scan_and_redact

logger = logging.getLogger(__name__)

#: The library's word for the legacy recall pool.
ACTIVE = "active"
#: States a skill is retired in; an arc in one of these starts a new version.
_RETIRED = frozenset({"deprecated", "superseded", "revoked"})
#: Automatic, reversible disablement: the institutional analogue of a legacy
#: trail quarantined by reuse failures.
_QUARANTINED = frozenset({"degraded", "suspended"})
#: Trail ids the library issues itself -- for a skill with no legacy row --
#: start here. Legacy ``procedural_skills`` ids are small and keep growing during
#: the pilot, so a library-issued id taken from the same low range would later
#: be handed to a DIFFERENT legacy skill, and reuse credit for one skill would
#: land on another's row. Found by a test that put the two counters out of
#: step; the two ranges now never meet.
LIBRARY_ID_BASE = 1_000_000_000
#: How ``provenance.procedure_format`` marks a procedure that is a JSON step list.
_STEPS_JSON = "legacy_steps_json"
#: A new arc's starting confidence is its success ratio, never above the prior a
#: verified-trajectory candidate gets (same cap as the migration tool).
_CONFIDENCE_CAP = 0.8


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _hours_since(timestamp: str, now: datetime) -> float:
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace(" ", "T"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max((now - parsed).total_seconds() / 3600.0, 0.0)


def _steps(record: SkillRecord) -> list[str]:
    if record.provenance.get("procedure_format") == _STEPS_JSON:
        try:
            steps = json.loads(record.procedure)
        except (TypeError, ValueError):
            return [record.procedure]
        return (
            [str(step) for step in steps]
            if isinstance(steps, list)
            else [record.procedure]
        )
    return [record.procedure]


def _success_rate(record: SkillRecord) -> float:
    return record.success_count / max(record.success_count + record.failure_count, 1)


def _legacy_id(record: SkillRecord) -> Optional[int]:
    """The ``procedural_skills`` id a record carries, if it came from there."""
    raw = record.provenance.get("legacy_id")
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def is_review_ready(
    record: SkillRecord, *, min_successes: int = 3, min_success_rate: float = 0.8
) -> bool:
    """A candidate the operator can reasonably review for activation.

    ONE derivation for every caller (the trail map, the scoreboard, the
    activation tool): two definitions of "ready" already disagreed once, 11
    against 8. It is the legacy promotion rule, plus, for a migrated arc, the
    legacy store's own verdict. A legacy trail that met the rule but was
    QUARANTINED -- demoted for reuse failures, the only way the legacy store
    leaves a rule-meeting arc a candidate -- is not presented as ready.
    """
    if record.state != BIRTH_STATE:
        return False
    ok, bad = record.success_count, record.failure_count
    if ok < max(min_successes, 1) or ok / max(ok + bad, 1) < min_success_rate:
        return False
    if record.provenance.get("source") == "migrated":
        return record.provenance.get("review_ready") == "true"
    return True


def library_summary(path: Path | str) -> dict[str, object]:
    """Read-only counts of the institutional skill library, for every reporter.

    One reader for the scoreboard and the doctor alike, so they cannot drift
    the way two definitions of "review-ready" once did. Opened ``mode=ro``: it
    never creates or migrates the store it reports on, and an absent library
    reads as absent (``library_present: False``), never as zeros.
    """
    from typing import get_args

    from aios.domain.learning.skill_contracts import SkillState

    stats: dict[str, object] = {"library_present": False}
    db = Path(path)
    if not db.is_file():
        return stats
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "institutional_skills" not in tables:
            return stats
        stats["library_present"] = True
        states: dict[str, int] = {}
        successes = failures = review_ready = 0
        for (payload,) in conn.execute("SELECT payload_json FROM institutional_skills"):
            record = SkillRecord.model_validate(json.loads(payload))
            states[record.state] = states.get(record.state, 0) + 1
            successes += record.success_count
            failures += record.failure_count
            review_ready += is_review_ready(record)
        for state in get_args(SkillState):
            stats[f"library_{state}"] = states.get(state, 0)
        stats["library_review_ready"] = review_ready
        stats["library_successes"] = successes
        stats["library_failures"] = failures
        if "skill_trails" in tables:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(reuse_success_count), 0), "
                "COALESCE(SUM(reuse_failure_count), 0) FROM skill_trails"
            ).fetchone()
            stats["library_trails"] = int(row[0])
            stats["library_reuse_successes"] = int(row[1])
            stats["library_reuse_failures"] = int(row[2])
    finally:
        conn.close()
    return stats


class SkillTrailIndex:
    """Integer trail ids for institutional skills, plus live ranking bookkeeping.

    A sidecar table beside ``institutional_skills``, owned by this module and
    never referenced by the library, so organ 43's contract does not carry the
    turn path's mechanics. Two id ranges that never meet: a legacy id is kept
    as-is (small), and an id the library issues itself starts at
    ``LIBRARY_ID_BASE``.
    """

    def __init__(self, database: Path | str) -> None:
        # R11: a physical store. Production builds exactly one, in bootstrap.py.
        record_construction("SkillTrailIndex")
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_trails (
                    trail_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    reuse_success_count INTEGER NOT NULL DEFAULT 0,
                    reuse_failure_count INTEGER NOT NULL DEFAULT 0,
                    last_reused_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (skill_id, version)
                )
                """
            )

    def trail_for(
        self, skill_id: str, version: int, *, preferred_id: Optional[int] = None
    ) -> int:
        """The trail id of ``(skill_id, version)``, assigning one if new.

        *preferred_id* is honoured when it is free: a migrated skill keeps its
        legacy id, and a dual-written arc keeps the id the legacy store gave it.
        An id already held by another skill is never reused.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT trail_id FROM skill_trails WHERE skill_id = ? AND version = ?",
                (skill_id, version),
            ).fetchone()
            if row is not None:
                return int(row[0])
        assert_learning_permitted("skill_trails.assign")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT trail_id FROM skill_trails WHERE skill_id = ? AND version = ?",
                (skill_id, version),
            ).fetchone()
            if row is not None:
                return int(row[0])
            now = _utc_now().isoformat()
            if preferred_id is not None:
                taken = connection.execute(
                    "SELECT 1 FROM skill_trails WHERE trail_id = ?",
                    (int(preferred_id),),
                ).fetchone()
                if taken is None:
                    connection.execute(
                        "INSERT INTO skill_trails (trail_id, skill_id, version, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (int(preferred_id), skill_id, version, now),
                    )
                    return int(preferred_id)
            highest = connection.execute(
                "SELECT MAX(trail_id) FROM skill_trails WHERE trail_id >= ?",
                (LIBRARY_ID_BASE,),
            ).fetchone()[0]
            issued = LIBRARY_ID_BASE if highest is None else int(highest) + 1
            connection.execute(
                "INSERT INTO skill_trails (trail_id, skill_id, version, created_at) "
                "VALUES (?, ?, ?, ?)",
                (issued, skill_id, version, now),
            )
            return issued

    def key_for(self, trail_id: int) -> Optional[tuple[str, int]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT skill_id, version FROM skill_trails WHERE trail_id = ?",
                (int(trail_id),),
            ).fetchone()
        return None if row is None else (str(row[0]), int(row[1]))

    def all(self) -> dict[tuple[str, int], dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM skill_trails").fetchall()
        return {(str(r["skill_id"]), int(r["version"])): dict(r) for r in rows}

    def record_reuse(self, trail_id: int, *, success: bool, now: datetime) -> None:
        """Ranking pheromone only. Frozen by the stop like every learning write."""
        assert_learning_permitted("skill_trails.record_reuse")
        # Two fixed statements rather than a formatted column name: nothing
        # here is caller-supplied, but SQL assembled by formatting is the
        # shape a reader has to prove safe, so there is none.
        sql = (
            "UPDATE skill_trails SET reuse_success_count = reuse_success_count + 1, "
            "last_reused_at = ? WHERE trail_id = ?"
            if success
            else "UPDATE skill_trails SET reuse_failure_count = reuse_failure_count + 1, "
            "last_reused_at = ? WHERE trail_id = ?"
        )
        with self._connection() as connection:
            connection.execute(sql, (now.isoformat(), int(trail_id)))

    def adopt_migrated(self, repository: SkillRepository) -> list[int]:
        """Give every migrated skill a trail at its legacy id. Idempotent."""
        adopted = []
        for record in repository.list_skills():
            legacy = record.provenance.get("legacy_id")
            if record.provenance.get("source") != "migrated" or not legacy:
                continue
            adopted.append(
                self.trail_for(
                    record.skill_id, record.version, preferred_id=int(legacy)
                )
            )
        return adopted

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


class InstitutionalSkillAdapter:
    """The ``skills`` authority slot, served by the institutional library."""

    memory_types = ("skill", "workflow")

    def __init__(
        self,
        repository: SkillRepository,
        trails: SkillTrailIndex,
        *,
        legacy: Optional[SkillMemory] = None,
        min_successes: int = 3,
        min_success_rate: float = 0.8,
        migration_pending: Optional[str] = None,
    ) -> None:
        self.repository = repository
        self.trails = trails
        self.lifecycle = SkillLifecycleAuthority(repository)
        # ``MemoryAuthority.owns_store`` routes callers through the authority
        # only when the slot's ``store`` is the production SkillMemory, so the
        # legacy store stays attached, as read-only history.
        self.store = legacy
        self.migration_pending = migration_pending
        self.min_successes = max(min_successes, 1)
        self.min_success_rate = max(0.0, min(1.0, min_success_rate))

    # -- writes ---------------------------------------------------------- #

    def record_attempt(
        self,
        goal: str,
        steps: list[str],
        *,
        success: bool,
        strength: VerificationStrength = VerificationStrength.STRONG,
        legacy_id: Optional[int] = None,
    ) -> int:
        """Record one verification-backed attempt of an arc; return its trail id.

        A success below the learning floor is not evidence for the arc (as in
        the legacy store); it neither counts nor refreshes the recipe.
        """
        if self.migration_pending:
            raise SkillMigrationPendingError(self.migration_pending)
        assert_learning_permitted("institutional_skills.record_attempt")
        # Plan Phase 6b: spent before anything is written.
        write_budget.spend(self, "institutional_skills")
        clean_steps = [
            scan_and_redact(step.strip()).scrubbed for step in steps if step.strip()
        ]
        goal = scan_and_redact(goal.strip()).scrubbed
        if not goal or not clean_steps:
            raise ValueError("skill attempt requires a goal and workflow steps")
        eligible = success and meets_learning_floor(strength)
        signature = skill_signature_v2(goal, clean_steps)
        skill_id = f"arc-{signature}"
        steps_json = json.dumps(clean_steps, separators=(",", ":"))

        versions = [r for r in self.repository.list_skills() if r.skill_id == skill_id]
        live = [r for r in versions if r.state not in _RETIRED]
        if not live:
            version = max((r.version for r in versions), default=0) + 1
            attempts = 1 if (eligible or not success) else 0
            ratio = (1.0 if eligible else 0.0) if attempts else 0.0
            now = _utc_now().isoformat()
            provenance = {
                "source": "live",
                "signature_v2": signature,
                "procedure_format": _STEPS_JSON,
                "first_strength": strength.name if success else "",
            }
            if legacy_id is not None:
                provenance["legacy_id"] = str(int(legacy_id))
            self.repository.save(
                SkillRecord(
                    skill_id=skill_id,
                    version=version,
                    problem_signature=goal,
                    applicability_conditions={},
                    known_exclusions=[],
                    required_inputs=[],
                    required_project_state={},
                    procedure=steps_json,
                    allowed_tools=sorted(
                        {s.split(":", 1)[0].strip() for s in clean_steps}
                    ),
                    allowed_scope_pattern="",
                    expected_observations=[],
                    verification_plan=None,
                    escalation_conditions=[],
                    source_trajectory_ids=[],
                    confidence=round(min(_CONFIDENCE_CAP, ratio), 2),
                    success_count=1 if eligible else 0,
                    failure_count=0 if success else 1,
                    last_validated_versions=[],
                    state=BIRTH_STATE,
                    created_at=now,
                    updated_at=now,
                    provenance=provenance,
                )
            )
            return self.trails.trail_for(skill_id, version, preferred_id=legacy_id)

        current = max(live, key=lambda r: r.version)
        trail = self.trails.trail_for(
            current.skill_id, current.version, preferred_id=legacy_id
        )
        if success and not eligible:
            return trail
        self.lifecycle.apply_reuse_outcome(
            current.skill_id,
            current.version,
            success=eligible,
            reason=None if eligible else "verification",
        )
        refreshed = self.repository.get(current.skill_id, current.version)
        if (
            eligible
            and refreshed is not None
            and refreshed.state == BIRTH_STATE
            and refreshed.provenance.get("procedure_format") == _STEPS_JSON
            and _better_recipe(steps_json, refreshed.procedure)
        ):
            self.repository.save(refreshed.model_copy(update={"procedure": steps_json}))
        return trail

    def record_reuse(
        self,
        skill_ids: Sequence[int],
        *,
        success: bool,
        now: Optional[datetime] = None,
    ) -> list[int]:
        """Credit or stain recalled ACTIVE skills after a verifier-judged turn."""
        if self.migration_pending:
            raise SkillMigrationPendingError(self.migration_pending)
        moment = now or _utc_now()
        credited: list[int] = []
        for trail_id in skill_ids:
            key = self.trails.key_for(int(trail_id))
            if key is None:
                continue
            record = self.repository.get(*key)
            if record is None or record.state != ACTIVE:
                continue
            self.trails.record_reuse(int(trail_id), success=success, now=moment)
            self.lifecycle.apply_reuse_outcome(
                *key, success=success, reason=None if success else "verification"
            )
            credited.append(int(trail_id))
        return credited

    # -- reads ----------------------------------------------------------- #

    def relevant_verified(
        self, query: str, limit: int = 3, *, now: Optional[datetime] = None
    ) -> list[dict[str, Any]]:
        """ACTIVE skills relevant to *query*, in the legacy recall row shape."""
        if not query or limit <= 0:
            return []
        moment = now or _utc_now()
        stats = self.trails.all()
        ranked = []
        for record in self.repository.list_skills():
            if record.state != ACTIVE:
                continue
            score = relevance(query, record.problem_signature)
            if score <= 0:
                continue
            row = self._row(record, stats, moment)
            if row is None:
                continue
            row["relevance"] = score
            ranked.append(row)
        ranked.sort(
            key=lambda r: (r["relevance"], r["strength"], r["success_count"]),
            reverse=True,
        )
        return ranked[:limit]

    def active_procedures(self) -> dict[int, dict[str, Any]]:
        """The only reflex source: ACTIVE skills by trail id.

        Read-only. An active skill with no trail yet is left out rather than
        assigned one, because a read must not write (the #375 lesson): it gets a
        reflex once the next read that may write has given it a trail.
        """
        stats = self.trails.all()
        activated: dict[int, dict[str, Any]] = {}
        for record in self.repository.list_skills():
            if record.state != ACTIVE:
                continue
            trail = stats.get((record.skill_id, record.version))
            if trail is None:
                continue
            steps = _steps(record)
            activated[int(trail["trail_id"])] = {
                "skill_id": record.skill_id,
                "version": record.version,
                "goal_pattern": record.problem_signature,
                "steps": steps,
                "success_count": record.success_count,
                "signature_v2": record.provenance.get("signature_v2")
                or skill_signature_v2(record.problem_signature, steps),
            }
        return activated

    def withdraw_reflex_source(self, trail_id: int) -> bool:
        """Suspend the ACTIVE skill behind a trail whose reflex the machine
        retired (operator decision, 2026-09-29).

        ``suspended`` is an automatic, reviewable disablement; the only way
        back is the operator's capability-backed re-activation. A withdrawal,
        so the emergency stop allows it. True when the skill is out of
        ``active``, now or already; False when the trail is unknown.
        """
        key = self.trails.key_for(int(trail_id))
        record = None if key is None else self.repository.get(*key)
        if record is None:
            return False
        if record.state != ACTIVE:
            return True
        self.repository.transition_state(record.skill_id, record.version, "suspended")
        return True

    def successes(self, trail_id: int) -> Optional[int]:
        """The library's success count for a trail, in any state; read-only.

        Bookkeeping only since 2026-09-29: a retired reflex returns by the
        operator's re-activation, never by a count.
        """
        key = self.trails.key_for(int(trail_id))
        record = None if key is None else self.repository.get(*key)
        return None if record is None else record.success_count

    def list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        moment = _utc_now()
        stats = self.trails.all()
        rows = [
            row
            for row in (
                self._row(r, stats, moment) for r in self.repository.list_skills()
            )
            if row is not None
        ]
        if status is not None:
            rows = [r for r in rows if r["status"] == status]
        return rows

    def trail_map(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        """The operator's view of every trail, with the review queue marked."""
        moment = now or _utc_now()
        stats = self.trails.all()
        trails, fragments = [], []
        for record in self.repository.list_skills():
            row = self._row(record, stats, moment)
            if row is None:
                continue
            if record.state in _RETIRED:
                fragments.append(
                    {
                        "skill_id": row["skill_id"],
                        "goal_pattern": row["goal_pattern"],
                        "superseded_by": None,
                        "success_count": row["success_count"],
                        "failure_count": row["failure_count"],
                        "institutional_state": record.state,
                    }
                )
                continue
            trails.append(row)
        trails.sort(key=lambda t: t["strength"], reverse=True)
        return {
            "trails": trails,
            "superseded_fragments": fragments,
            "summary": {
                "verified": sum(1 for t in trails if t["status"] == "verified"),
                "candidate": sum(1 for t in trails if t["status"] == "candidate"),
                "quarantined": sum(1 for t in trails if t["quarantined"]),
                "superseded": len(fragments),
                "review_ready": sum(1 for t in trails if t["review_ready"]),
            },
            "constants": {
                "lambda_decay_per_hour": config.SKILL_LAMBDA_DECAY_PER_HOUR,
                "reuse_boost_max": config.SKILL_REUSE_BOOST_MAX,
                "reuse_penalty_max": config.SKILL_REUSE_PENALTY_MAX,
                "reuse_success_k": config.SKILL_REUSE_SUCCESS_K,
                "reuse_failure_k": config.SKILL_REUSE_FAILURE_K,
                "reuse_factor_floor": config.SKILL_REUSE_FACTOR_FLOOR,
                "min_successes": self.min_successes,
                "min_success_rate": self.min_success_rate,
            },
            "store": "institutional_skills",
            "migration_pending": self.migration_pending,
        }

    def recall(self, query: str, context: MemoryRecallContext) -> tuple[MemoryHit, ...]:
        rows = self.relevant_verified(query, context.limit)
        return tuple(
            MemoryHit(
                record_id=f"skill:{row['skill_id']}",
                external_id=int(row["skill_id"]),
                memory_type="workflow",
                content_reference=(
                    f"institutional_skills:{row['institutional']['skill_id']}"
                    f"@v{row['institutional']['version']}"
                ),
                text=str(row["goal_pattern"]),
                score=float(row.get("relevance", 0.0)),
                verification_status="verified",
                source="institutional_skills",
            )
            for row in rows
        )

    def rebuild_derived_indexes(self) -> None:
        return None

    # -- shape ----------------------------------------------------------- #

    def _row(
        self,
        record: SkillRecord,
        stats: dict[tuple[str, int], dict[str, Any]],
        moment: datetime,
    ) -> Optional[dict[str, Any]]:
        trail = stats.get((record.skill_id, record.version))
        if trail is None:
            # A skill written outside this adapter (a mission-trajectory
            # candidate) has no trail yet. Assigning one is a write; under the
            # stop a READ must not fail -- the #375 lesson -- so the skill is
            # left out until the stop is cleared, rather than blinding the read.
            try:
                trail_id = self.trails.trail_for(
                    record.skill_id, record.version, preferred_id=_legacy_id(record)
                )
            except EmergencyStopError:
                return None
            reuse_s = reuse_f = 0
            last_reused = None
        else:
            trail_id = int(trail["trail_id"])
            reuse_s = int(trail["reuse_success_count"])
            reuse_f = int(trail["reuse_failure_count"])
            last_reused = trail["last_reused_at"]
        rate = _success_rate(record)
        freshness = math.exp(
            -config.SKILL_LAMBDA_DECAY_PER_HOUR
            * _hours_since(record.updated_at, moment)
        )
        reuse_factor = SkillMemory._reuse_factor(reuse_s, reuse_f)
        return {
            "skill_id": trail_id,
            "id": trail_id,
            "goal_pattern": record.problem_signature,
            "steps": _steps(record),
            "status": "verified" if record.state == ACTIVE else "candidate",
            "quarantined": record.state in _QUARANTINED,
            "review_ready": is_review_ready(
                record,
                min_successes=self.min_successes,
                min_success_rate=self.min_success_rate,
            ),
            "success_count": record.success_count,
            "failure_count": record.failure_count,
            "success_rate": round(rate, 6),
            "confidence": record.confidence,
            "reuse_success_count": reuse_s,
            "reuse_failure_count": reuse_f,
            "freshness": round(freshness, 6),
            "reuse_factor": round(reuse_factor, 6),
            "strength": round(min(1.0, rate * freshness * reuse_factor), 6),
            "updated_at": record.updated_at,
            "last_reused_at": last_reused,
            "institutional": {
                "skill_id": record.skill_id,
                "version": record.version,
                "state": record.state,
            },
        }


class SkillMigrationPendingError(RuntimeError):
    """The library refuses new arcs until the legacy history has been migrated.

    ``tools/migrate_skills_to_institutional.py`` refuses to write anything when
    an ``arc-...`` record it would create already exists. A store that learned
    new arcs before migrating could therefore never migrate its history, so the
    library learns nothing until the migration has run.
    """


def _history_rows(history: Any) -> int:
    """Rows in the legacy history table, read-only; 0 when there is none."""
    path = getattr(history, "db_path", None)
    if path is None or not Path(path).is_file():
        return 0
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='procedural_skills'"
        ).fetchone()
        if present is None:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM procedural_skills").fetchone()[0])
    finally:
        conn.close()


def build_skills_slot(
    *,
    repository: SkillRepository,
    trails: SkillTrailIndex,
    history: Optional[SkillMemory],
) -> InstitutionalSkillAdapter:
    """The memory authority's ``skills`` slot: the institutional library, alone.

    Phase 2 slice 2.4c-B. The dual-write pilot and ``AIOS_SKILL_STORE_MODE``
    are gone: every write goes to the library, which organ 43 governs, and
    nothing promotes itself. *history* is the legacy store, attached READ-ONLY
    so ``MemoryAuthority.owns_store`` still recognises the production store
    callers hold.

    Legacy history that was never migrated keeps the slot from learning (see
    :class:`SkillMigrationPendingError`), loudly. A store with no history, a
    fresh install, has nothing to migrate.

    The stores are passed in, never built here: R11 keeps every physical
    store's construction in ``bootstrap.py``.
    """
    migrated = any(
        r.provenance.get("source") == "migrated" for r in repository.list_skills()
    )
    pending: Optional[str] = None
    if not migrated and _history_rows(history):
        pending = (
            "legacy skill history has not been migrated into the institutional "
            "library; run tools/migrate_skills_to_institutional.py --apply"
        )
        logger.error("skill library refuses new arcs: %s", pending)
    try:
        trails.adopt_migrated(repository)
    except EmergencyStopError:
        logger.warning("stop engaged at startup: migrated trail ids assigned lazily")
    return InstitutionalSkillAdapter(
        repository, trails, legacy=history, migration_pending=pending
    )


__all__ = [
    "InstitutionalSkillAdapter",
    "ReadOnlySkillHistoryError",
    "SkillMigrationPendingError",
    "SkillTrailIndex",
    "build_skills_slot",
    "is_review_ready",
    "library_summary",
]
