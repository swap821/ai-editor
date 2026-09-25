"""Migrate the live stack's learned skills into the institutional skill library.

Plan Phase 2, slice 2.3 (``docs/learning/PHASE2_DESIGN.md``). Operator
decision, 2026-09-25: the institutional library (organ 43) becomes the live
skill store, so the arcs the live stack learned move into it.

What moves, and how
-------------------
* Every ``procedural_skills`` row becomes one institutional skill.
  ``skill_id`` is ``arc-<signature_v2>``, the arc identity the live path already
  computes, so slice 2.4 can find a migrated skill from a live turn. Rows that
  share a ``signature_v2`` (a superseded arc and the arc that replaced it)
  become successive *versions* of one skill, in legacy-id order.
* Everything is born ``candidate``, because the store refuses anything else.
  Legacy ``superseded`` rows then move ``candidate -> deprecated``: the
  library's word for "replaced by a newer version, not wrong".
* Legacy ``verified`` rows stay ``candidate`` and are marked
  ``review_ready``. They are **not** activated: activation needs the
  operator's capability proof, so skill recall and reflexes go quiet until the
  operator activates what they choose.
* ``procedure`` is the arc's exact ``steps_json``, so a playbook can be
  recompiled from it byte for byte. ``allowed_tools`` are the step tools.
  ``allowed_scope_pattern`` is empty and there is no source trajectory or
  structured verifier, so a migrated skill can never pass mission-reuse
  applicability, even when active. It fails closed.
* ``confidence`` is the legacy success ratio, capped at 0.8, the prior a
  trajectory-born candidate gets. A migrated arc has no stronger evidence
  than a verified mission trajectory.
* Lessons (``mistake_pool``) and playbooks do not move. See the design doc.

Safety
------
* **Dry run by default.** ``--apply`` writes.
* The source is opened read-only and never written.
* The whole plan is checked against the target before anything is written. A
  ``(skill_id, version)`` already held by a record that is not this migration
  aborts the run with nothing written.
* The target is backed up (SQLite online backup) before the first write.
* **Idempotent:** a second run writes nothing. A run interrupted between a
  save and its deprecation is completed by the next run.
* Every write goes through ``SkillRepository``, so the lifecycle and the
  emergency stop apply. An engaged stop refuses the migration.
* Counts are asserted after writing: every planned record present, in its
  planned state, carrying its legacy id.

The operator is asked before this runs on live data.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios.domain.learning.repository import SkillRecord, SkillRepository  # noqa: E402
from aios.domain.learning.skill_contracts import BIRTH_STATE  # noqa: E402

MIGRATION = "procedural_skills->institutional_skills/v1"
CONFIDENCE_CAP = 0.8
_LEGACY_TO_FINAL = {"candidate": "candidate", "verified": "candidate", "superseded": "deprecated"}
_REQUIRED_COLUMNS = frozenset(
    {
        "id",
        "created_at",
        "goal_pattern",
        "steps_json",
        "status",
        "success_count",
        "failure_count",
        "signature_v2",
        "reuse_success_count",
        "reuse_failure_count",
        "verification_strength",
    }
)


class MigrationError(RuntimeError):
    """The migration cannot proceed safely; nothing further is written."""


@dataclass(frozen=True)
class LegacySkill:
    id: int
    created_at: str
    goal_pattern: str
    steps_json: str
    status: str
    success_count: int
    failure_count: int
    signature_v2: str
    reuse_success_count: int
    reuse_failure_count: int
    verification_strength: str


@dataclass(frozen=True)
class Planned:
    legacy: LegacySkill
    record: SkillRecord  # always in BIRTH_STATE; the final state is reached after
    final_state: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.record.skill_id, self.record.version)


def _iso(sqlite_timestamp: str) -> str:
    """SQLite ``CURRENT_TIMESTAMP`` is UTC without a zone; say so."""
    try:
        parsed = datetime.fromisoformat(sqlite_timestamp.replace(" ", "T"))
    except ValueError:
        return sqlite_timestamp
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def load_legacy(source: Path) -> list[LegacySkill]:
    """One read-only snapshot of ``procedural_skills``."""
    if not source.exists():
        raise MigrationError(f"source database not found: {source}")
    connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(procedural_skills)")}
        missing = _REQUIRED_COLUMNS - columns
        if missing:
            raise MigrationError(f"procedural_skills lacks columns: {sorted(missing)}")
        rows = connection.execute(
            f"SELECT {', '.join(sorted(_REQUIRED_COLUMNS))} FROM procedural_skills ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    skills = [LegacySkill(**{key: row[key] for key in row.keys()}) for row in rows]
    unknown = sorted({s.status for s in skills} - set(_LEGACY_TO_FINAL))
    if unknown:
        raise MigrationError(f"unmapped legacy statuses: {unknown}")
    if any(not s.signature_v2 for s in skills):
        raise MigrationError("a legacy skill has no signature_v2; its identity is undefined")
    return skills


def _tools(steps: Sequence[str]) -> list[str]:
    return sorted({str(step).split(":", 1)[0].strip() for step in steps})


def _confidence(skill: LegacySkill) -> float:
    attempts = skill.success_count + skill.failure_count
    if attempts <= 0:
        return 0.0
    return round(min(CONFIDENCE_CAP, skill.success_count / attempts), 2)


def plan(skills: Iterable[LegacySkill], *, migrated_at: str) -> list[Planned]:
    """Pure: the records this migration would write, in write order."""
    by_signature: dict[str, list[LegacySkill]] = {}
    for skill in sorted(skills, key=lambda s: s.id):
        by_signature.setdefault(skill.signature_v2, []).append(skill)
    planned: list[Planned] = []
    for signature, group in by_signature.items():
        for version, skill in enumerate(group, start=1):
            steps = json.loads(skill.steps_json)
            if not isinstance(steps, list):
                raise MigrationError(f"legacy skill {skill.id}: steps_json is not a list")
            record = SkillRecord(
                skill_id=f"arc-{signature}",
                version=version,
                problem_signature=skill.goal_pattern,
                applicability_conditions={},
                known_exclusions=[],
                required_inputs=[],
                required_project_state={},
                procedure=skill.steps_json,
                allowed_tools=_tools(steps),
                allowed_scope_pattern="",
                expected_observations=[],
                verification_plan=None,
                escalation_conditions=[],
                source_trajectory_ids=[],
                confidence=_confidence(skill),
                success_count=skill.success_count,
                failure_count=skill.failure_count,
                last_validated_versions=[],
                state=BIRTH_STATE,
                created_at=_iso(skill.created_at),
                updated_at=migrated_at,
                provenance={
                    "source": "migrated",
                    "migration": MIGRATION,
                    "legacy_table": "procedural_skills",
                    "legacy_id": str(skill.id),
                    "legacy_status": skill.status,
                    "legacy_verification_strength": str(skill.verification_strength or ""),
                    "legacy_reuse": f"{skill.reuse_success_count}/{skill.reuse_failure_count}",
                    "signature_v2": signature,
                    "procedure_format": "legacy_steps_json",
                    "review_ready": "true" if skill.status == "verified" else "false",
                    "migrated_at": migrated_at,
                },
            )
            planned.append(Planned(skill, record, _LEGACY_TO_FINAL[skill.status]))
    return planned


def _existing(target: Path) -> dict[tuple[str, int], SkillRecord]:
    """What the target holds, read without creating anything."""
    if not target.exists():
        return {}
    connection = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    try:
        has_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='institutional_skills'"
        ).fetchone()
        if not has_table:
            return {}
        rows = connection.execute("SELECT payload_json FROM institutional_skills").fetchall()
    finally:
        connection.close()
    records = (SkillRecord.model_validate(json.loads(row[0])) for row in rows)
    return {(r.skill_id, r.version): r for r in records}


@dataclass(frozen=True)
class Preflight:
    to_create: tuple[Planned, ...]
    to_finish: tuple[Planned, ...]  # saved by an interrupted run, not yet deprecated
    done: tuple[Planned, ...]
    #: Migrated earlier and since moved by someone else -- e.g. the operator
    #: activated a review-ready skill. Left alone; it never blocks a re-run.
    moved_on: tuple[Planned, ...] = ()


def preflight(planned: Sequence[Planned], target: Path) -> Preflight:
    existing = _existing(target)
    create: list[Planned] = []
    finish: list[Planned] = []
    done: list[Planned] = []
    moved_on: list[Planned] = []
    conflicts: list[str] = []
    for item in planned:
        held = existing.get(item.key)
        if held is None:
            create.append(item)
            continue
        ours = (
            held.provenance.get("migration") == MIGRATION
            and held.provenance.get("legacy_id") == str(item.legacy.id)
        )
        if not ours:
            conflicts.append(f"{item.key} is held by a record this migration did not write")
        elif held.state == item.final_state:
            done.append(item)
        elif held.state == BIRTH_STATE:
            # Nothing is ever reborn a candidate, so a migrated record still in
            # BIRTH_STATE with a different final state is one an interrupted
            # run saved and did not get to deprecate.
            finish.append(item)
        else:
            moved_on.append(item)
    if conflicts:
        raise MigrationError("refusing to write anything: " + "; ".join(conflicts))
    return Preflight(tuple(create), tuple(finish), tuple(done), tuple(moved_on))


def backup(target: Path, backup_dir: Path, *, stamp: str) -> Path | None:
    """SQLite online backup of the target, taken before the first write."""
    if not target.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"{target.stem}.pre-skill-migration.{stamp}.db"
    source = sqlite3.connect(target)
    copy = sqlite3.connect(destination)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return destination


def apply(checked: Preflight, repository: SkillRepository) -> dict[str, int]:
    created = finished = 0
    for item in checked.to_create:
        repository.save(item.record)
        created += 1
        if item.final_state != BIRTH_STATE:
            repository.transition_state(*item.key, item.final_state)
    for item in checked.to_finish:
        repository.transition_state(*item.key, item.final_state)
        finished += 1
    return {"created": created, "finished": finished}


def verify(planned: Sequence[Planned], checked: Preflight, target: Path) -> None:
    """Every planned record is present and carries its legacy id; every record
    this run wrote or finished is in its planned state. Records that moved on
    before this run keep whatever state they were moved to."""
    existing = _existing(target)
    moved_on = {item.key for item in checked.moved_on}
    wrong = [
        f"{item.key}: {'missing' if item.key not in existing else existing[item.key].state}"
        for item in planned
        if item.key not in existing
        or existing[item.key].provenance.get("legacy_id") != str(item.legacy.id)
        or (item.key not in moved_on and existing[item.key].state != item.final_state)
    ]
    if wrong:
        raise MigrationError(f"post-write check failed for {len(wrong)} record(s): {wrong[:5]}")


def summarize(planned: Sequence[Planned]) -> dict[str, object]:
    by_final: dict[str, int] = {}
    for item in planned:
        by_final[item.final_state] = by_final.get(item.final_state, 0) + 1
    versioned = sorted({item.record.skill_id for item in planned if item.record.version > 1})
    return {
        "legacy_rows": len(planned),
        "skills": len({item.record.skill_id for item in planned}),
        "by_final_state": by_final,
        "review_ready_legacy_ids": [
            item.legacy.id for item in planned if item.record.provenance["review_ready"] == "true"
        ],
        "skills_with_several_versions": len(versioned),
    }


def run(
    *,
    source: Path,
    target: Path,
    backup_dir: Path,
    do_apply: bool,
    now: datetime | None = None,
) -> dict[str, object]:
    moment = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    migrated_at = moment.isoformat()
    planned = plan(load_legacy(source), migrated_at=migrated_at)
    checked = preflight(planned, target)
    report: dict[str, object] = {
        "mode": "apply" if do_apply else "dry-run",
        "source": str(source),
        "target": str(target),
        **summarize(planned),
        "to_create": len(checked.to_create),
        "to_finish": len(checked.to_finish),
        "already_done": len(checked.done),
        "moved_on_since_migration": len(checked.moved_on),
    }
    if not do_apply:
        return report
    if checked.to_create or checked.to_finish:
        stamp = moment.strftime("%Y%m%dT%H%M%SZ")
        written = backup(target, backup_dir, stamp=stamp)
        report["backup"] = None if written is None else str(written)
        report.update(apply(checked, SkillRepository(target)))
    else:
        report.update({"backup": None, "created": 0, "finished": 0})
    verify(planned, checked, target)
    report["verified"] = True
    return report


def main(argv: Sequence[str] | None = None) -> int:
    from aios import config

    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--source", type=Path, default=Path(config.MEMORY_DB_PATH))
    parser.add_argument("--target", type=Path, default=Path(config.OPERATIONAL_STATE_DB_PATH))
    parser.add_argument("--backup-dir", type=Path, default=Path(config.DATA_DIR) / "backups")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args(argv)
    try:
        report = run(
            source=args.source,
            target=args.target,
            backup_dir=args.backup_dir,
            do_apply=args.apply,
        )
    except MigrationError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
