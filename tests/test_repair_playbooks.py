"""The malformed-step detector, and what it must refuse to match.

A detector that over-matches deletes healthy playbooks, which is a far worse
failure than leaving a broken one alone: a decompiled playbook is inert, but a
deleted one takes a verified skill's compiled form with it.

Measured in the shipped database on 2026-09-07: three playbooks carried
``"command": "command=pytest ..."`` and were decompiled with zero replays; the
one without it had replayed twice with zero failures. The engine was fine; the
stored arguments were not.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.repair_playbooks import has_malformed_step, survey  # noqa: E402


def _steps(tool: str, args: dict) -> str:
    return json.dumps([{"tool_name": tool, "args": args}])


def test_it_catches_the_doubled_prefix() -> None:
    """The real shape, taken verbatim from the shipped database."""
    assert has_malformed_step(
        _steps("verify", {"command": "command=pytest lab/test_llp_reflex_xkj.py -q"})
    )


def test_it_leaves_a_well_formed_step_alone() -> None:
    """The playbook that actually worked must never be a candidate."""
    assert not has_malformed_step(
        _steps("verify", {"command": "pytest lab/test_llp_reflex_dyk.py -q"})
    )


@pytest.mark.parametrize(
    "command",
    [
        "pytest -k x=1",
        "FOO=bar make build",
        "python -c 'a=1'",
        "grep -n 'x=y' file.py",
    ],
)
def test_an_equals_sign_is_not_a_defect(command: str) -> None:
    """THE BAR for the detector.

    Plenty of legitimate commands contain `=`. Matching on the mere presence of
    one would delete healthy playbooks -- so the rule is specifically that the
    ARGUMENT NAME repeats itself at the front of its own value.
    """
    assert not has_malformed_step(_steps("execute_terminal", {"command": command}))


def test_it_catches_the_shape_on_any_argument_name() -> None:
    """Not hard-coded to `command`; the serializer uses the key it is given."""
    assert has_malformed_step(_steps("read_file", {"filepath": "filepath=a.py"}))


def test_malformed_json_is_not_a_defect() -> None:
    """Unparseable steps are somebody else's problem; do not delete on them."""
    assert not has_malformed_step("not json at all")
    assert not has_malformed_step("{}")


# --------------------------------------------------------------------------- #
# The survey's refusals
# --------------------------------------------------------------------------- #


def _db(tmp_path: Path, rows: list[tuple]) -> Path:
    """A minimal schema carrying just what the survey reads."""
    db = tmp_path / "m.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE procedural_skills (
            id INTEGER PRIMARY KEY, status TEXT, failure_count INTEGER DEFAULT 0);
        CREATE TABLE compiled_playbooks (
            id INTEGER PRIMARY KEY, status TEXT, replay_count INTEGER DEFAULT 0,
            consecutive_failures INTEGER DEFAULT 0, steps_json TEXT,
            skill_id INTEGER);
        """
    )
    for pid, pstatus, steps, sid, sstatus, sfail in rows:
        conn.execute(
            "INSERT INTO procedural_skills (id,status,failure_count) VALUES (?,?,?)",
            (sid, sstatus, sfail),
        )
        conn.execute(
            "INSERT INTO compiled_playbooks (id,status,steps_json,skill_id) "
            "VALUES (?,?,?,?)",
            (pid, pstatus, steps, sid),
        )
    conn.commit()
    conn.close()
    return db


def _verdicts(db: Path) -> dict[int, str]:
    conn = sqlite3.connect(db)
    try:
        return {r["id"]: r["verdict"] for r in survey(conn)}
    finally:
        conn.close()


def test_a_malformed_playbook_with_an_unverified_skill_is_kept(tmp_path) -> None:
    """Deleting this would hide a fact rather than fix a defect.

    The row cannot recompile -- its skill has not earned verification -- so
    removing it erases the record of a skill that genuinely has not qualified.
    This is the case that spared playbook 2 in the real database.
    """
    bad = _steps("verify", {"command": "command=pytest x.py"})
    db = _db(tmp_path, [(1, "decompiled", bad, 41, "candidate", 0)])

    assert _verdicts(db) == {1: "keep"}


def test_a_malformed_playbook_with_a_failing_skill_is_kept(tmp_path) -> None:
    """Verified but with failures is still not recompilable."""
    bad = _steps("verify", {"command": "command=pytest x.py"})
    db = _db(tmp_path, [(1, "decompiled", bad, 41, "verified", 2)])

    assert _verdicts(db) == {1: "keep"}


def test_a_malformed_but_still_LIVE_playbook_is_kept(tmp_path) -> None:
    """Only decompiled rows block recompilation, so only those are in scope.

    A malformed playbook still marked `compiled` is a different problem and
    deleting it would destroy a row nothing asked this tool to touch.
    """
    bad = _steps("verify", {"command": "command=pytest x.py"})
    db = _db(tmp_path, [(1, "compiled", bad, 41, "verified", 0)])

    assert _verdicts(db) == {1: "keep"}


def test_the_repairable_case_is_the_only_one_marked(tmp_path) -> None:
    """Decompiled + malformed + skill verified with zero failures."""
    bad = _steps("verify", {"command": "command=pytest x.py"})
    good = _steps("verify", {"command": "pytest y.py"})
    db = _db(
        tmp_path,
        [
            (1, "decompiled", bad, 41, "verified", 0),
            (2, "decompiled", bad, 45, "candidate", 0),
            (3, "compiled", good, 53, "verified", 0),
        ],
    )

    assert _verdicts(db) == {1: "repair", 2: "keep", 3: "keep"}
