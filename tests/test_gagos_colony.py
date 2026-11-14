"""The ant colony works a council goal over several files (2026-11-14).

The operator: "writers can be within colony as it was meant". Pinned here,
without a model or a network:

* the decomposer's split is read by the files' numbers, and anything that is
  not a clean split (a number out of range, a file in two parts, noise) leaves
  one part over every file;
* the scout reuses a verified split that names only this goal's files, and the
  decomposer is then not asked;
* every leg is admitted (the decomposer once, one writer per part), the writers
  run side by side, and a writer's failure is raised once every leg finished;
* in the hour, a goal over several files is split, each part written by the
  mission's writer into the task's one group, so verification and review see
  one change; any part refused refuses it all; a goal over one file, or the
  colony switched off, is worked as before;
* after the council decides, the run is recorded and a split lays its trail in
  the swarm's pattern memory, and the report counts the colony's work.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.agents import swarm
from aios.agents.swarm_patterns import SwarmPatternMemory
from aios.core.verification_strength import VerificationStrength
from aios.maintenance import daily_work as dw
from aios.runtime.gagos_writer import WriterRefused
from tests.test_gagos_daily import AFTER, REL, _git
from tests.test_gagos_workforce import OTHER, _batch
from tools import gagos_daily as tool

FILES = [REL, OTHER]
GOAL = "Rename the unused local in both panels to `spare`."
SPLIT = "1. files 1: rename it in the first panel\n2. files 2: rename it in the second"


# ------------------------------------------------------------- the colony itself


def test_the_decomposers_split_is_read_by_the_files_numbers() -> None:
    parts = swarm.parse_colony_parts(SPLIT, FILES, limit=4)
    assert [p.files for p in parts] == [(REL,), (OTHER,)]
    assert parts[0].work == "rename it in the first panel"
    both = swarm.parse_colony_parts("1. files 2, 1: do both", FILES, limit=4)
    assert [p.files for p in both] == [(REL, OTHER)]


@pytest.mark.parametrize(
    "answer",
    [
        "1. files 3: a file the goal does not have",
        "1. files 1: first\n2. files 1,2: the first again",
        "Here is how I would do it, in prose.",
        "",
        "1. files 1: one\n2. files 2: two\n3. files 0: none",
    ],
)
def test_anything_but_a_clean_split_is_no_split(answer: str) -> None:
    assert swarm.parse_colony_parts(answer, FILES, limit=4) == []


def test_a_split_past_the_limit_is_no_split() -> None:
    assert swarm.parse_colony_parts(SPLIT, FILES, limit=1) == []


def _admit(log: list):
    lock = threading.Lock()

    def admit(caste, run):
        with lock:
            log.append(caste)
        return run()

    return admit


def test_the_colony_splits_and_its_writers_work_side_by_side() -> None:
    admitted: list = []
    running, most = [0], [0]
    lock = threading.Lock()

    def write_part(part):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return part.files

    run = swarm.run_writer_colony(
        GOAL,
        FILES,
        decompose=lambda: SPLIT,
        write_part=write_part,
        admit=_admit(admitted),
        concurrency=2,
    )
    assert run.scout == "fresh"
    assert run.results == [(REL,), (OTHER,)], "in the parts' order"
    assert admitted.count("decomposer") == 1 and admitted.count("worker") == 2
    assert most[0] == 2, "the writers ran side by side"


def test_no_clean_split_leaves_one_part_over_every_file() -> None:
    seen: list = []
    run = swarm.run_writer_colony(
        GOAL,
        FILES,
        decompose=lambda: "I would rather not split this.",
        write_part=seen.append,
        admit=_admit([]),
    )
    assert run.scout == "single"
    assert [p.files for p in seen] == [tuple(FILES)] and seen[0].work == GOAL


def test_a_goal_over_one_file_asks_no_decomposer() -> None:
    admitted: list = []
    run = swarm.run_writer_colony(
        GOAL,
        [REL],
        decompose=lambda: pytest.fail("one file is not split"),
        write_part=lambda part: None,
        admit=_admit(admitted),
    )
    assert run.scout == "single" and admitted == ["worker"]


def test_a_writers_failure_is_raised_after_every_leg_finished() -> None:
    finished: list = []

    def write_part(part):
        if part.files == (REL,):
            raise WriterRefused("the first panel's answer was unreadable")
        time.sleep(0.05)
        finished.append(part.files)

    with pytest.raises(WriterRefused, match="unreadable"):
        swarm.run_writer_colony(
            GOAL,
            FILES,
            decompose=lambda: SPLIT,
            write_part=write_part,
            admit=_admit([]),
        )
    assert finished == [(OTHER,)], "the other writer was not abandoned"


def _verified(memory: SwarmPatternMemory, subtasks: list[str]) -> None:
    for _ in range(2):  # two strong successes promote a pattern
        memory.record_attempt(
            GOAL, subtasks, success=True, strength=VerificationStrength.STRONG
        )


def test_the_scout_reuses_a_verified_split_of_this_goals_files(tmp_path) -> None:
    memory = SwarmPatternMemory(tmp_path / "memory.db")
    _verified(memory, [f"{REL}: the first panel", f"{OTHER}: the second panel"])
    admitted: list = []
    run = swarm.run_writer_colony(
        GOAL,
        FILES,
        decompose=lambda: pytest.fail("a verified split is reused"),
        write_part=lambda part: part.files,
        admit=_admit(admitted),
        pattern_memory=memory,
    )
    assert run.scout == "reused" and run.pattern_id is not None
    assert [p.files for p in run.parts] == [(REL,), (OTHER,)]
    assert admitted == ["worker", "worker"]


def test_a_remembered_split_of_other_files_is_not_reused(tmp_path) -> None:
    memory = SwarmPatternMemory(tmp_path / "memory.db")
    _verified(memory, ["frontend/src/elsewhere.jsx: x", f"{OTHER}: y"])
    run = swarm.run_writer_colony(
        GOAL,
        FILES,
        decompose=lambda: SPLIT,
        write_part=lambda part: None,
        admit=_admit([]),
        pattern_memory=memory,
    )
    assert run.scout == "fresh"


# ------------------------------------------------------------- in the hour


def _name(prompt: str) -> str:
    return re.search(r"File 1: (\S+)", prompt).group(1)


def _writer(answers: dict | None = None, *, split: str = SPLIT, asked=None):
    """The mission's model: the decomposer's split, and each writer's answer
    (by the file its prompt shows first; AFTER unless *answers* says else)."""

    def complete(prompt, system, request_id):
        if asked is not None:
            asked.append((system, prompt))
        if system == swarm.COLONY_DECOMPOSER_SYSTEM:
            return split
        name = _name(prompt)
        text = (answers or {}).get(name, AFTER)
        return f"File 1: {name}\n```jsx\n{text}```" if text is not None else "no"

    return complete


def _mission(
    tmp_path, monkeypatch, *, files=(REL, OTHER), complete=None, admitted=None
):
    led, _asked, args, _ids = _batch(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "goals_through_clerk", lambda: False)
    root = Path(args.project)
    tid = led.add_task(files[0], GOAL, said_by="operator", also=tuple(files[1:]))
    memory = SwarmPatternMemory(tmp_path / "memory.db")
    work = tool.MissionWork(
        led,
        root,
        _git(root, "rev-parse", "HEAD"),
        led.task(tid),
        region="r",
        complete=complete or _writer(),
        reviewer=lambda prompt: ("accept", "fine", "claude-opus"),
        admit=_admit(admitted if admitted is not None else []),
        patterns=memory,
    )
    return led, tid, work, memory


CONTRACT = SimpleNamespace(mission_id="mission-0123456789ab")


def test_a_goal_over_two_files_is_split_and_written_by_the_colony(
    tmp_path, monkeypatch
) -> None:
    asked: list = []
    admitted: list = []
    led, tid, work, _memory = _mission(
        tmp_path, monkeypatch, complete=_writer(asked=asked), admitted=admitted
    )
    assert work.write(CONTRACT) == {REL: AFTER, OTHER: AFTER}
    assert work.colony.scout == "fresh"
    assert admitted.count("decomposer") == 1 and admitted.count("worker") == 2
    members = led.group_members(tid)
    assert {r["rel"] for r in members} == set(FILES)
    assert all(r["status"] == "proposed" for r in members), "one group, both parts"
    assert led.task(tid)["status"] == "taken"
    writers = [p for system, p in asked if system != swarm.COLONY_DECOMPOSER_SYSTEM]
    assert len(writers) == 2
    assert all("Your part of this goal" in p for p in writers)
    assert any("rename it in the second" in p for p in writers)
    # Each writer is shown its own file only.
    assert sorted(_name(p) for p in writers) == ["Other.jsx", "Panel.jsx"]
    assert all(len(re.findall(r"^File \d+: ", p, re.M)) == 1 for p in writers)


def test_any_part_refused_refuses_the_colonys_whole_change(
    tmp_path, monkeypatch
) -> None:
    led, tid, work, _memory = _mission(
        tmp_path, monkeypatch, complete=_writer({"Other.jsx": None})
    )
    with pytest.raises(WriterRefused):
        work.write(CONTRACT)
    work.withdraw("the council's mission: a part was refused")
    assert {r["status"] for r in work._rows()} == {"refused"}, "nothing delivered"


def test_a_goal_over_one_file_is_written_as_before(tmp_path, monkeypatch) -> None:
    asked: list = []
    led, tid, work, _memory = _mission(
        tmp_path, monkeypatch, files=(REL,), complete=_writer(asked=asked)
    )

    def single(prompt, system, request_id):
        asked.append((system, prompt))
        return f"```jsx\n{AFTER}```"

    work.complete = single
    assert work.write(CONTRACT) == {REL: AFTER}
    assert work.colony is None
    assert all(system != swarm.COLONY_DECOMPOSER_SYSTEM for system, _ in asked)


def test_with_the_colony_off_one_writer_takes_every_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_GAGOS_COLONY", "0")
    asked: list = []

    def whole(prompt, system, request_id):
        asked.append(system)
        return "\n".join(
            f"File {n}: {name}\n```jsx\n{AFTER}```"
            for n, name in ((1, "Panel.jsx"), (2, "Other.jsx"))
        )

    led, tid, work, _memory = _mission(tmp_path, monkeypatch, complete=whole)
    assert work.write(CONTRACT) == {REL: AFTER, OTHER: AFTER}
    assert work.colony is None and len(asked) == 1


def test_the_trail_is_laid_after_the_council_decides(tmp_path, monkeypatch) -> None:
    led, tid, work, memory = _mission(tmp_path, monkeypatch)
    work.write(CONTRACT)
    tool.colony_trail(led, tid, CONTRACT.mission_id, work, completed=True)
    (run,) = led.colony_runs()
    assert run["scout"] == "fresh" and run["outcome"] == "completed"
    assert run["parts"] == [[REL], [OTHER]]
    # One more strong success verifies the split; the next colony reuses it.
    tool.colony_trail(led, tid, CONTRACT.mission_id, work, completed=True)
    (pattern,) = memory.recall(GOAL)
    assert pattern["subtasks"] == [
        f"{REL}: rename it in the first panel",
        f"{OTHER}: rename it in the second",
    ]
    again = swarm.run_writer_colony(
        GOAL,
        FILES,
        decompose=lambda: pytest.fail("the verified split is reused"),
        write_part=lambda part: None,
        admit=_admit([]),
        pattern_memory=memory,
    )
    assert again.scout == "reused"
    assert "the colony: 1 goal(s) over several files" not in "\n".join(
        tool.mission_section(led)
    ), "no mission rows here: the section is the missions'"
    assert tool.colony_lines(led) == [
        "- the colony: 2 goal(s) over several files; 2 split into parts "
        "(4 parts in all, 0 by a verified split reused), 2 of them completed; "
        "0 worked as one part"
    ]


def test_a_failed_mission_lays_a_failure_and_one_part_lays_nothing(
    tmp_path, monkeypatch
) -> None:
    led, tid, work, memory = _mission(tmp_path, monkeypatch)
    work.write(CONTRACT)
    tool.colony_trail(led, tid, CONTRACT.mission_id, work, completed=False)
    assert led.colony_runs()[0]["outcome"] == "failed"
    assert memory.recall(GOAL) == [], "a failure verifies nothing"
    work.colony = swarm.ColonyRun([swarm.ColonyPart(tuple(FILES), GOAL)], "single")
    tool.colony_trail(led, tid, CONTRACT.mission_id, work, completed=True)
    for _ in range(3):
        tool.colony_trail(led, tid, CONTRACT.mission_id, work, completed=True)
    assert memory.recall(GOAL) == [], "nothing was split, so no trail"


def test_a_work_without_a_colony_records_nothing(tmp_path) -> None:
    led = dw.DailyLedger(tmp_path / "l.db")
    tool.colony_trail(led, "gt-0000000000", "m", SimpleNamespace(), completed=True)
    assert led.colony_runs() == [] and tool.colony_lines(led) == []
