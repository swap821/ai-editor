"""Phase 2, slice 3: the skill migration tool (`tools/migrate_skills_to_institutional.py`).

The tool moves the live stack's learned arcs into the institutional library.
These tests run it against throwaway databases shaped like the live ones,
including the shape found in the live data on 2026-09-26: six superseded arcs
sharing a ``signature_v2`` with the arc that replaced them.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.domain.learning.repository import SkillRepository
from aios.memory import learning_freeze
from aios.memory.db import init_memory_db
from tools import migrate_skills_to_institutional as mig

NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

#: (signature, signature_v2, status, steps, success, failure)
LEGACY = [
    ("s1", "sigA", "candidate", ["read_file: filepath=a.py"], 1, 0),
    ("s2", "sigB", "verified", ["verify: command=pytest t.py -q"], 4, 1),
    (
        "s3",
        "sigC",
        "superseded",
        ["create_file: path=x.py", "verify: command=pytest"],
        2,
        2,
    ),
    (
        "s4",
        "sigC",
        "verified",
        ["create_file: path=x.py", "edit_file: path=x.py"],
        5,
        0,
    ),
    ("s5", "sigD", "superseded", ["execute_terminal: command=ls"], 0, 3),
    ("s6", "sigE", "candidate", ["read_directory: path=."], 0, 0),
]


@pytest.fixture()
def dbs(tmp_path: Path, monkeypatch):
    latch = tmp_path / "emergency_stop.db"
    monkeypatch.setattr(learning_freeze, "_latch_path", lambda: latch)
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    source = tmp_path / "memory.db"
    init_memory_db(source)
    conn = sqlite3.connect(source)
    try:
        with conn:
            for signature, sig2, status, steps, ok, bad in LEGACY:
                conn.execute(
                    """INSERT INTO procedural_skills
                       (signature, goal_pattern, steps_json, status, success_count,
                        failure_count, signature_v2, reuse_success_count,
                        reuse_failure_count, verification_strength)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 3, 1, 'STRONG')""",
                    (
                        signature,
                        f"goal for {signature}",
                        json.dumps(steps),
                        status,
                        ok,
                        bad,
                        sig2,
                    ),
                )
        # Fold the WAL into the main file and close now: a connection left to
        # the garbage collector checkpoints whenever it is collected, which
        # would change the source's bytes mid-test and blame the tool.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return source, tmp_path / "operational.db", tmp_path / "backups", latch


def _run(dbs, *, apply: bool) -> dict:
    source, target, backups, _ = dbs
    return mig.run(
        source=source, target=target, backup_dir=backups, do_apply=apply, now=NOW
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _by_legacy_id(target: Path) -> dict[str, object]:
    return {r.provenance["legacy_id"]: r for r in SkillRepository(target).list_skills()}


class TestDryRunByDefault:
    def test_the_cli_writes_nothing_without_apply(self, dbs, capsys) -> None:
        source, target, backups, _ = dbs
        code = mig.main(
            [
                "--source",
                str(source),
                "--target",
                str(target),
                "--backup-dir",
                str(backups),
            ]
        )
        report = json.loads(capsys.readouterr().out)
        assert code == 0 and report["mode"] == "dry-run"
        assert report["to_create"] == len(LEGACY)
        assert not target.exists() and not backups.exists()

    def test_the_source_is_never_written(self, dbs) -> None:
        source = dbs[0]
        wal = source.with_name(source.name + "-wal")
        before = (_digest(source), wal.read_bytes() if wal.exists() else b"")
        _run(dbs, apply=True)
        after = (_digest(source), wal.read_bytes() if wal.exists() else b"")
        assert after == before


class TestWhatMoves:
    def test_every_row_arrives_with_its_identity_and_version(self, dbs) -> None:
        report = _run(dbs, apply=True)
        assert report["verified"] is True and report["created"] == len(LEGACY)
        got = _by_legacy_id(dbs[1])
        assert len(got) == len(LEGACY)
        assert (got["3"].skill_id, got["3"].version) == ("arc-sigC", 1)
        assert (got["4"].skill_id, got["4"].version) == ("arc-sigC", 2)
        assert all(
            r.skill_id == f"arc-{r.provenance['signature_v2']}" for r in got.values()
        )

    def test_states_follow_the_design_and_nothing_is_activated(self, dbs) -> None:
        _run(dbs, apply=True)
        got = _by_legacy_id(dbs[1])
        states = {lid: r.state for lid, r in got.items()}
        assert states == {
            "1": "candidate",
            "2": "candidate",
            "3": "deprecated",
            "4": "candidate",
            "5": "deprecated",
            "6": "candidate",
        }
        assert not {"human_reviewed", "probation", "active"} & set(states.values())

    def test_only_legacy_verified_arcs_are_review_ready(self, dbs) -> None:
        report = _run(dbs, apply=True)
        got = _by_legacy_id(dbs[1])
        ready = {
            lid for lid, r in got.items() if r.provenance["review_ready"] == "true"
        }
        assert ready == {"2", "4"}
        assert report["review_ready_legacy_ids"] == [2, 4]

    def test_the_procedure_is_the_exact_steps(self, dbs) -> None:
        _run(dbs, apply=True)
        got = _by_legacy_id(dbs[1])
        for index, (_sig, _sig2, _status, steps, _ok, _bad) in enumerate(
            LEGACY, start=1
        ):
            record = got[str(index)]
            assert json.loads(record.procedure) == steps
            assert list(record.allowed_tools) == sorted(
                {s.split(":")[0] for s in steps}
            )

    def test_confidence_is_the_success_ratio_capped_at_the_prior(self, dbs) -> None:
        _run(dbs, apply=True)
        got = _by_legacy_id(dbs[1])
        assert got["1"].confidence == 0.8  # 1/1, capped
        assert got["2"].confidence == 0.8  # 4/5 = 0.8
        assert got["3"].confidence == 0.5  # 2/4
        assert got["5"].confidence == 0.0  # 0/3
        assert got["6"].confidence == 0.0  # never attempted

    def test_a_migrated_skill_can_never_pass_mission_reuse(self, dbs) -> None:
        """No scope, no source trajectory, no structured verifier: even an
        activated migrated skill fails applicability closed."""
        _run(dbs, apply=True)
        for record in _by_legacy_id(dbs[1]).values():
            assert record.allowed_scope_pattern == ""
            assert not record.source_trajectory_ids and record.verification_plan is None


class TestSafety:
    def test_a_second_run_writes_nothing(self, dbs) -> None:
        _run(dbs, apply=True)
        target = dbs[1]
        before = _digest(target)
        report = _run(dbs, apply=True)
        assert (report["created"], report["finished"], report["already_done"]) == (
            0,
            0,
            len(LEGACY),
        )
        assert report["backup"] is None
        assert _digest(target) == before

    def test_an_interrupted_run_is_finished(self, dbs) -> None:
        """Saved as a candidate but not yet deprecated: the next run completes it."""
        planned = mig.plan(mig.load_legacy(dbs[0]), migrated_at=NOW.isoformat())
        interrupted = next(p for p in planned if p.final_state == "deprecated")
        SkillRepository(dbs[1]).save(interrupted.record)
        report = _run(dbs, apply=True)
        assert report["finished"] == 1 and report["created"] == len(LEGACY) - 1
        assert _by_legacy_id(dbs[1])[str(interrupted.legacy.id)].state == "deprecated"

    def test_a_skill_the_operator_moved_on_is_left_alone(self, dbs) -> None:
        _run(dbs, apply=True)
        repo = SkillRepository(dbs[1])
        repo.transition_state("arc-sigB", 1, "human_reviewed")
        repo.transition_state("arc-sigB", 1, "active")
        report = _run(dbs, apply=True)
        assert report["moved_on_since_migration"] == 1 and report["verified"] is True
        assert repo.get("arc-sigB", 1).state == "active"

    def test_a_foreign_record_aborts_before_any_write(self, dbs) -> None:
        planned = mig.plan(mig.load_legacy(dbs[0]), migrated_at=NOW.isoformat())
        squatter = planned[-1].record.model_copy(
            update={"provenance": {"source": "live"}}
        )
        SkillRepository(dbs[1]).save(squatter)
        before = _digest(dbs[1])
        with pytest.raises(mig.MigrationError, match="refusing to write anything"):
            _run(dbs, apply=True)
        assert _digest(dbs[1]) == before
        assert not dbs[2].exists(), "no backup either: nothing was going to be written"

    def test_the_target_is_backed_up_before_the_first_write(self, dbs) -> None:
        target = dbs[1]
        SkillRepository(target)  # an existing, empty library
        before = _digest(target)
        report = _run(dbs, apply=True)
        backup = Path(report["backup"])
        assert backup.parent == dbs[2] and backup.exists()
        with sqlite3.connect(backup) as conn:
            assert (
                conn.execute("SELECT COUNT(*) FROM institutional_skills").fetchone()[0]
                == 0
            )
        assert _digest(target) != before

    def test_an_engaged_stop_refuses_the_migration(self, dbs) -> None:
        latch = dbs[3]
        stop = EmergencyStopController(
            latch,
            hooks=EmergencyStopHooks(
                revoke_capabilities=lambda *a, **k: None,
                cancel_queued_missions=lambda *a, **k: None,
                kill_active_workers=lambda *a, **k: None,
                disable_autonomy=lambda *a, **k: None,
                preserve_evidence=lambda *a, **k: None,
            ),
        )
        stop.engage(
            EmergencyStopRequest(
                operator_id="operator:test",
                authentication_event_id="event:engage",
                reason="migration freeze test",
            )
        )
        with pytest.raises(EmergencyStopError):
            _run(dbs, apply=True)
        assert SkillRepository(dbs[1]).list_skills() == ()

    def test_an_unmapped_legacy_status_is_refused(self, dbs) -> None:
        with sqlite3.connect(dbs[0]) as conn:
            conn.execute("PRAGMA ignore_check_constraints = ON")
            conn.execute("UPDATE procedural_skills SET status = 'retired' WHERE id = 1")
        with pytest.raises(mig.MigrationError, match="unmapped legacy statuses"):
            _run(dbs, apply=False)
