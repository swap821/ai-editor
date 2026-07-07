"""Tests for the Cerebellum (compiled experience engine).

The Cerebellum compiles verified procedural skills (0 failures, all steps
parsing into compilable tool calls) into deterministic playbooks that replay
without an LLM call, through the same dispatch/security path as ordinary
tool calls. These tests cover step parsing, compilation guards, lexical
matching, replay bookkeeping/decompilation, and observability.

Each test uses an isolated temporary SQLite database (via ``tmp_path``), so
the suite never touches real ``data/`` artifacts and has no network, model,
or shell side effects.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.core.cerebellum import Cerebellum, PlaybookStep, _parse_step
from aios.memory.db import get_connection, init_memory_db


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
def _insert_verified_skill(
    db_path: Path,
    goal: str,
    steps: list[str],
    *,
    failure_count: int = 0,
    signature: str = "sig_legacy",
    sig_v2: str = "sig_test",
    status: str = "verified",
) -> int:
    """Insert a procedural skill row directly, bypassing SkillMemory promotion
    logic, so compilation guards can be tested in isolation."""
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO procedural_skills
               (signature, signature_v2, goal_pattern, steps_json,
                status, success_count, failure_count)
               VALUES (?, ?, ?, ?, ?, 3, ?)""",
            (signature, sig_v2, goal, json.dumps(steps), status, failure_count),
        )
        return cur.lastrowid


def _mark_already_compiled(db_path: Path, skill_id: int, *, status: str = "compiled") -> int:
    """Insert a compiled_playbooks row for *skill_id* directly."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO compiled_playbooks
               (skill_id, goal_pattern, signature_v2, steps_json, status)
               VALUES (?, ?, ?, ?, ?)""",
            (skill_id, "already here", "sig", json.dumps([]), status),
        )
        return cur.lastrowid


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "memory.db"
    init_memory_db(path)
    return path


def _ok_dispatch(output: str = "ok") -> "callable":
    def _fn(tool_name: str, args: dict) -> tuple[str, str, bool]:
        return (output, "ok", False)
    return _fn


def _scripted_dispatch(results: list[tuple[str, str, bool]]) -> "callable":
    """Returns a dispatch_fn that yields *results* in order, one per call."""
    calls = iter(results)

    def _fn(tool_name: str, args: dict) -> tuple[str, str, bool]:
        return next(calls)

    return _fn


# --------------------------------------------------------------------------- #
# A. _parse_step
# --------------------------------------------------------------------------- #
def test_parse_step_read_file() -> None:
    step = _parse_step("read_file: src/foo.py")
    assert step == PlaybookStep("read_file", {"filepath": "src/foo.py"})


def test_parse_step_execute_terminal() -> None:
    step = _parse_step("execute_terminal: pytest tests/")
    assert step == PlaybookStep("execute_terminal", {"command": "pytest tests/"})


def test_parse_step_verify() -> None:
    step = _parse_step("verify: python -m pytest")
    assert step == PlaybookStep("verify", {"command": "python -m pytest"})


def test_parse_step_read_directory() -> None:
    step = _parse_step("read_directory: src/")
    assert step == PlaybookStep("read_directory", {"path": "src/"})


def test_parse_step_edit_file_not_compilable() -> None:
    assert _parse_step("edit_file: foo.py") is None


def test_parse_step_create_file_not_compilable() -> None:
    assert _parse_step("create_file: bar.py") is None


def test_parse_step_unknown_tool() -> None:
    assert _parse_step("unknown_tool: x") is None


def test_parse_step_no_colon() -> None:
    assert _parse_step("no colon here") is None


def test_parse_step_empty_arg() -> None:
    assert _parse_step("read_file:") is None


def test_parse_step_is_case_insensitive_on_tool_name() -> None:
    step = _parse_step("READ_FILE: src/foo.py")
    assert step == PlaybookStep("read_file", {"filepath": "src/foo.py"})


def test_playbook_step_to_dict_and_from_dict_roundtrip() -> None:
    step = PlaybookStep("read_file", {"filepath": "src/foo.py"})
    data = step.to_dict()
    assert data == {"tool_name": "read_file", "args": {"filepath": "src/foo.py"}}
    assert PlaybookStep.from_dict(data) == step


def test_playbook_step_is_frozen() -> None:
    step = PlaybookStep("read_file", {"filepath": "src/foo.py"})
    with pytest.raises(Exception):
        step.tool_name = "verify"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# B. Compilation
# --------------------------------------------------------------------------- #
def test_try_compile_all_compiles_verified_zero_failure_skill(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["read_file: src/foo.py", "verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 1
    assert cerebellum.compiled_count() == 1
    [pb] = cerebellum.playbook_map()
    assert pb["goal_pattern"] == "run the test suite"
    assert pb["status"] == "compiled"
    assert pb["step_count"] == 2
    assert pb["steps"] == [
        {"tool_name": "read_file", "args": {"filepath": "src/foo.py"}},
        {"tool_name": "verify", "args": {"command": "pytest tests/"}},
    ]


def test_try_compile_all_skips_skill_with_failures(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["read_file: src/foo.py"],
        failure_count=1,
    )
    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 0
    assert cerebellum.compiled_count() == 0


def test_try_compile_all_skips_candidate_skill(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["read_file: src/foo.py"],
        status="candidate",
    )
    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 0
    assert cerebellum.compiled_count() == 0


def test_try_compile_all_skips_skill_with_noncompilable_step(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="edit a file",
        steps=["read_file: src/foo.py", "edit_file: src/foo.py"],
    )
    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 0
    assert cerebellum.compiled_count() == 0


def test_try_compile_all_skips_already_compiled_skill(db_path: Path) -> None:
    skill_id = _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["read_file: src/foo.py"],
    )
    _mark_already_compiled(db_path, skill_id, status="compiled")

    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 0


def test_try_compile_all_skips_skill_with_decompiled_playbook(db_path: Path) -> None:
    """A previously decompiled playbook must never recompile automatically —
    the skill must re-earn verification from scratch."""
    skill_id = _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["read_file: src/foo.py"],
    )
    _mark_already_compiled(db_path, skill_id, status="decompiled")

    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 0


def test_try_compile_all_skips_skill_with_only_redacted_goal(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="   ",  # whitespace-only goal strips to empty after redaction scan
        steps=["read_file: src/foo.py"],
    )
    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 0
    assert cerebellum.compiled_count() == 0


def test_try_compile_skill_by_id(db_path: Path) -> None:
    skill_id = _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path)
    pb = cerebellum.try_compile_skill(skill_id)

    assert pb is not None
    assert pb.skill_id == skill_id
    assert pb.status == "compiled"
    assert cerebellum.compiled_count() == 1


def test_try_compile_skill_returns_none_for_unknown_id(db_path: Path) -> None:
    cerebellum = Cerebellum(db_path)
    assert cerebellum.try_compile_skill(999999) is None


def test_try_compile_skill_returns_none_when_already_compiled(db_path: Path) -> None:
    skill_id = _insert_verified_skill(
        db_path,
        goal="run the test suite",
        steps=["verify: pytest tests/"],
    )
    _mark_already_compiled(db_path, skill_id, status="compiled")

    cerebellum = Cerebellum(db_path)
    assert cerebellum.try_compile_skill(skill_id) is None


def test_try_compile_all_compiles_multiple_eligible_skills(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the tests",
        steps=["verify: pytest tests/"],
        signature="sig_a",
        sig_v2="sig_v2_a",
    )
    _insert_verified_skill(
        db_path,
        goal="read the config",
        steps=["read_file: config.yaml"],
        signature="sig_b",
        sig_v2="sig_v2_b",
    )
    cerebellum = Cerebellum(db_path)
    compiled = cerebellum.try_compile_all()

    assert compiled == 2
    assert cerebellum.compiled_count() == 2


# --------------------------------------------------------------------------- #
# C. Matching
# --------------------------------------------------------------------------- #
def test_match_finds_relevant_playbook(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the pytest test suite",
        steps=["verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path)
    cerebellum.try_compile_all()

    pb = cerebellum.match("please run the pytest test suite")
    assert pb is not None
    assert pb.goal_pattern == "run the pytest test suite"


def test_match_returns_none_below_threshold(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the pytest test suite",
        steps=["verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path, match_threshold=0.9)
    cerebellum.try_compile_all()

    # Weak lexical overlap should score well under a 0.9 threshold.
    pb = cerebellum.match("what is the weather today")
    assert pb is None


def test_match_returns_none_when_no_playbooks_compiled(db_path: Path) -> None:
    cerebellum = Cerebellum(db_path)
    assert cerebellum.match("run the pytest test suite") is None


def test_match_picks_best_scoring_playbook_among_several(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the pytest test suite",
        steps=["verify: pytest tests/"],
        signature="sig_a",
        sig_v2="sig_v2_a",
    )
    _insert_verified_skill(
        db_path,
        goal="run the pytest test suite now please",
        steps=["verify: pytest tests/ -x"],
        signature="sig_b",
        sig_v2="sig_v2_b",
    )
    cerebellum = Cerebellum(db_path, match_threshold=0.0)
    cerebellum.try_compile_all()

    pb = cerebellum.match("run the pytest test suite now please")
    assert pb is not None
    assert pb.goal_pattern == "run the pytest test suite now please"


def test_match_respects_custom_threshold(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the pytest test suite",
        steps=["verify: pytest tests/"],
    )
    lenient = Cerebellum(db_path, match_threshold=0.01)
    lenient.try_compile_all()
    strict = Cerebellum(db_path, match_threshold=0.99)

    assert lenient.match("pytest") is not None
    assert strict.match("pytest") is None


def test_match_rejects_request_for_a_different_concrete_file(db_path: Path) -> None:
    # A compiled playbook that verifies one specific file must NOT match a
    # request explicitly naming a DIFFERENT file, even when the generic goal
    # prefix scores highly — else it would replay a stale command and fabricate
    # a verdict (the mutation-probe verification-confidence violation).
    _insert_verified_skill(
        db_path,
        goal="use the verify tool to run exactly this command",
        steps=["verify: pytest lab/test_reflex.py -q"],
    )
    cerebellum = Cerebellum(db_path, match_threshold=0.0)
    cerebellum.try_compile_all()

    assert (
        cerebellum.match(
            "use the verify tool to run exactly this command: "
            "pytest lab/test_probe.py -q"
        )
        is None
    )
    # ...but it DOES match a request naming the SAME file it would replay.
    same = cerebellum.match(
        "use the verify tool to run exactly this command: pytest lab/test_reflex.py -q"
    )
    assert same is not None


def test_match_concrete_target_guard_ignores_paraphrases(db_path: Path) -> None:
    # When the request names no concrete file, the guard is inert and lexical
    # goal-matching stands (paraphrase-tolerant recall is preserved).
    _insert_verified_skill(
        db_path,
        goal="run the pytest test suite",
        steps=["verify: pytest lab/test_reflex.py -q"],
    )
    cerebellum = Cerebellum(db_path, match_threshold=0.0)
    cerebellum.try_compile_all()
    assert cerebellum.match("please run the pytest test suite") is not None


def test_compiled_command_strips_workflow_step_key_prefix(db_path: Path) -> None:
    # _workflow_step (aios/api/main.py) serializes tool calls as
    # 'verify: command=<cmd>'; the compiled playbook must replay the BARE
    # command, else the gateway classifies 'command=pytest ...' RED on replay.
    _insert_verified_skill(
        db_path,
        goal="use the verify tool to run exactly this command",
        steps=["verify: command=pytest lab/test_reflex.py -q"],
    )
    cerebellum = Cerebellum(db_path, match_threshold=0.0)
    cerebellum.try_compile_all()
    pb = cerebellum.match(
        "use the verify tool to run exactly this command: pytest lab/test_reflex.py -q"
    )
    assert pb is not None
    assert pb.steps[0].args["command"] == "pytest lab/test_reflex.py -q"


def test_target_extraction_regression_cases() -> None:
    # Cases surfaced by the adversarial-verification pass — each was a
    # false-negative (missed real target) in the first regex-only extractor.
    from aios.core.cerebellum import _target_files

    assert ".env" in _target_files("check .env for the db url")
    assert ".gitignore" in _target_files("update .gitignore please")
    assert "backup.7z" in _target_files("extract backup.7z now")  # digit-leading ext
    assert "dockerfile" in _target_files("rebuild using Dockerfile")  # extensionless
    assert "readme" in _target_files("fix the README wording")
    # ...but bare decimals / plain prose are NOT targets (would be noise).
    assert _target_files("bump confidence to 0.85") == set()
    assert _target_files("please run the pytest test suite") == set()


def test_conflicting_targets_refuses_dotfile_against_test_playbook() -> None:
    from aios.core.cerebellum import _conflicting_targets

    steps = [PlaybookStep("verify", {"command": "pytest tests/test_foo.py -q"})]
    # A request about .env must NOT replay an unrelated test-file playbook.
    assert _conflicting_targets("check .env for the database url", steps) is True
    # A request naming the playbook's own file is fine.
    assert _conflicting_targets("rerun pytest tests/test_foo.py", steps) is False
    # A pure paraphrase (no concrete file) leaves the guard inert.
    assert _conflicting_targets("please run the tests again", steps) is False


def test_conflicting_targets_normalizes_path_spelling() -> None:
    # Adversarial round 2: the SAME file spelled Windows-native or dot-relative
    # must still match its playbook (else a required replay is wrongly refused).
    from aios.core.cerebellum import _conflicting_targets

    steps = [PlaybookStep("verify", {"command": "pytest tests/test_cortex_bus.py -q"})]
    assert _conflicting_targets(
        "run exactly this command: pytest tests\\test_cortex_bus.py -q", steps
    ) is False
    assert _conflicting_targets(
        "run exactly this command: pytest ./tests/test_cortex_bus.py -q", steps
    ) is False
    # ...but a genuinely different file is still a conflict.
    assert _conflicting_targets(
        "run exactly this command: pytest tests/test_other.py -q", steps
    ) is True


def test_step_targets_are_clean_predicate() -> None:
    # Belt-and-suspenders compile guard: clean relative ASCII targets compile;
    # spaced / non-ASCII / quoted / absolute targets do not.
    from aios.core.cerebellum import _step_targets_are_clean

    assert _step_targets_are_clean(
        PlaybookStep("verify", {"command": "pytest lab/test_x.py -q"})
    ) is True
    assert _step_targets_are_clean(
        PlaybookStep("read_file", {"filepath": "lab/notes.md"})
    ) is True
    assert _step_targets_are_clean(
        PlaybookStep("read_file", {"filepath": "sales report.xlsx"})
    ) is False  # space
    assert _step_targets_are_clean(
        PlaybookStep("verify", {"command": "pytest 报告.py -q"})
    ) is False  # non-ASCII
    assert _step_targets_are_clean(
        PlaybookStep("verify", {"command": 'mv "Q1 report.pdf" out/'})
    ) is False  # quoted spaced filename
    assert _step_targets_are_clean(
        PlaybookStep("verify", {"command": "pytest /abs/root/x.py -q"})
    ) is False  # absolute


def test_compile_skips_skill_with_unclean_target(db_path: Path) -> None:
    # A verified skill operating on a spaced filename must NOT compile — the
    # conflict guard cannot disambiguate such a target, so we never replay it.
    _insert_verified_skill(
        db_path,
        goal="read the quarterly report",
        steps=["read_file: filepath=sales report.xlsx"],
    )
    cerebellum = Cerebellum(db_path)
    assert cerebellum.try_compile_all() == 0
    assert cerebellum.compiled_count() == 0


# --------------------------------------------------------------------------- #
# D. Replay
# --------------------------------------------------------------------------- #
def _compile_two_step_playbook(db_path: Path):
    _insert_verified_skill(
        db_path,
        goal="run the tests",
        steps=["read_file: src/foo.py", "verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path)
    cerebellum.try_compile_all()
    [pb] = cerebellum._cache.values()
    return cerebellum, pb


def test_replay_successful_yields_step_and_step_done_events(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)

    events = list(cerebellum.replay(pb, dispatch_fn=_ok_dispatch("output-here")))

    kinds = [e["type"] for e in events]
    assert kinds == [
        "cerebellum_step",
        "cerebellum_step_done",
        "cerebellum_step",
        "cerebellum_step_done",
    ]
    assert events[0]["tool"] == "read_file"
    assert events[0]["step_index"] == 0
    assert events[0]["step_count"] == 2
    assert events[1]["output"] == "output-here"


def test_replay_aborts_on_blocked_step(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)
    dispatch = _scripted_dispatch([("", "blocked", False)])

    events = list(cerebellum.replay(pb, dispatch_fn=dispatch))

    assert events[-1]["type"] == "cerebellum_abort"
    assert events[-1]["reason"] == "blocked"
    assert events[-1]["step_index"] == 0
    # Only the first step's cerebellum_step event plus the abort — replay
    # stops immediately and never dispatches the second step.
    assert [e["type"] for e in events] == ["cerebellum_step", "cerebellum_abort"]


def test_replay_aborts_on_approval_required_step(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)
    dispatch = _scripted_dispatch([("", "approval", False)])

    events = list(cerebellum.replay(pb, dispatch_fn=dispatch))

    assert events[-1]["type"] == "cerebellum_abort"
    assert events[-1]["reason"] == "approval"


def test_replay_aborts_on_execution_failure(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)
    dispatch = _scripted_dispatch([("boom: file not found", "ok", True)])

    events = list(cerebellum.replay(pb, dispatch_fn=dispatch))

    assert events[-1]["type"] == "cerebellum_abort"
    assert events[-1]["reason"] == "execution_failed"
    assert events[-1]["output"] == "boom: file not found"


def test_replay_success_increments_replay_count(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)

    list(cerebellum.replay(pb, dispatch_fn=_ok_dispatch()))

    [pb_after] = cerebellum.playbook_map()
    assert pb_after["replay_count"] == 1
    assert pb_after["consecutive_failures"] == 0


def test_replay_failure_then_success_resets_consecutive_failures(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)

    # First replay fails on step 0.
    list(cerebellum.replay(pb, dispatch_fn=_scripted_dispatch([("", "blocked", False)])))
    [pb_after_failure] = cerebellum.playbook_map()
    assert pb_after_failure["consecutive_failures"] == 1

    # Second replay succeeds fully -> failures reset to zero.
    list(cerebellum.replay(pb, dispatch_fn=_ok_dispatch()))
    [pb_after_success] = cerebellum.playbook_map()
    assert pb_after_success["consecutive_failures"] == 0
    assert pb_after_success["replay_count"] == 1


def test_replay_decompiles_after_max_consecutive_failures(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)
    assert cerebellum.max_consecutive_failures == 2

    list(cerebellum.replay(pb, dispatch_fn=_scripted_dispatch([("", "blocked", False)])))
    assert cerebellum.compiled_count() == 1  # still active after 1 failure

    list(cerebellum.replay(pb, dispatch_fn=_scripted_dispatch([("", "blocked", False)])))
    # Second consecutive failure hits max_consecutive_failures=2 -> decompiled.
    assert cerebellum.compiled_count() == 0

    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT status, consecutive_failures FROM compiled_playbooks WHERE id = ?",
            (pb.id,),
        ).fetchone()
    assert row["status"] == "decompiled"
    assert row["consecutive_failures"] == 2


def test_decompiled_playbook_does_not_match(db_path: Path) -> None:
    cerebellum, pb = _compile_two_step_playbook(db_path)

    for _ in range(2):
        list(cerebellum.replay(pb, dispatch_fn=_scripted_dispatch([("", "blocked", False)])))

    assert cerebellum.match("run the tests") is None


def test_replay_custom_max_consecutive_failures(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the tests",
        steps=["verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path, max_consecutive_failures=1)
    cerebellum.try_compile_all()
    [pb] = cerebellum._cache.values()

    list(cerebellum.replay(pb, dispatch_fn=_scripted_dispatch([("", "blocked", False)])))

    # A single failure already reaches the (lowered) threshold.
    assert cerebellum.compiled_count() == 0


# --------------------------------------------------------------------------- #
# E. Observability
# --------------------------------------------------------------------------- #
def test_compiled_count_reflects_only_active_playbooks(db_path: Path) -> None:
    cerebellum = Cerebellum(db_path)
    assert cerebellum.compiled_count() == 0

    _insert_verified_skill(
        db_path,
        goal="run the tests",
        steps=["verify: pytest tests/"],
    )
    cerebellum.try_compile_all()
    assert cerebellum.compiled_count() == 1


def test_playbook_map_contains_expected_fields(db_path: Path) -> None:
    _insert_verified_skill(
        db_path,
        goal="run the tests",
        steps=["verify: pytest tests/"],
    )
    cerebellum = Cerebellum(db_path)
    cerebellum.try_compile_all()

    [entry] = cerebellum.playbook_map()
    assert set(entry.keys()) == {
        "id",
        "skill_id",
        "goal_pattern",
        "step_count",
        "steps",
        "replay_count",
        "consecutive_failures",
        "status",
    }
    assert entry["status"] == "compiled"
    assert entry["replay_count"] == 0
    assert entry["consecutive_failures"] == 0


def test_playbook_map_empty_when_nothing_compiled(db_path: Path) -> None:
    cerebellum = Cerebellum(db_path)
    assert cerebellum.playbook_map() == []
