"""A task may create a file (2026-11-15, the operator: "624 utilize also as per
GAGOS"). #624's crew could create files; GAGOS's own tasks could not, because a
task's every file had to exist already. Pinned here, without a model:

* a task may name a file that does not exist yet when its folder already holds
  a file GAGOS may edit with the same suffix; never in the frozen core, never in
  a folder GAGOS has no file in;
* the writer is told the file is new, and the new file is recorded as a
  creation (no base text), ending with a newline as a first test does;
* any other missing file refuses the whole task before a model is asked.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_gagos_daily import AFTER, REL
from tests.test_gagos_tasks_many import _answer, _many
from tools import gagos_daily as tool

NEW = "frontend/src/workbench/Fresh.jsx"


def test_a_task_creates_a_file_beside_an_editable_one(tmp_path, monkeypatch) -> None:
    prompts: list = []
    led, asked, args, tid = _many(
        tmp_path,
        monkeypatch,
        _answer((1, "Panel.jsx", AFTER), (2, "Fresh.jsx", AFTER)),
        also=(NEW,),
        prompts=prompts,
    )
    assert tool.cmd_propose(args) == 0
    assert len(asked) == 1
    members = led.group_members(tid)
    assert [(p["rel"], p["op"], p["status"]) for p in members] == [
        (REL, None, "proposed"),
        (NEW, "create", "proposed"),
    ]
    created = members[1]
    assert created["base_text"] == ""
    assert created["new_text"] == AFTER, "a new file ends with a newline"
    ((prompt, _system),) = prompts
    file_2 = prompt.split("File 2: Fresh.jsx", 1)[1]
    assert file_2.lstrip().startswith("This file does not exist yet")
    assert "does not exist yet" not in prompt.split("File 2: Fresh.jsx", 1)[0]


def test_a_missing_file_in_a_folder_gagos_has_no_file_in_refuses_the_task(
    tmp_path, monkeypatch
) -> None:
    elsewhere = "frontend/src/elsewhere/Nope.jsx"
    led, asked, args, tid = _many(tmp_path, monkeypatch, also=(elsewhere,))
    assert tool.cmd_propose(args) == 0
    assert asked == [], "refused before any model is asked"
    task = led.task(tid)
    assert task["status"] == "refused"
    assert "its folder holds no file of its kind" in task["reason"]


def test_what_may_be_created(tmp_path) -> None:
    root = Path(tmp_path)
    (root / "frontend/src/workbench").mkdir(parents=True)
    (root / REL).write_text("x\n", encoding="utf-8")
    allowed = {REL, "aios/security/gateway_helpers.py", "aios/memory/recall.py"}
    assert tool.creatable(root, NEW, allowed)
    assert not tool.creatable(root, REL, allowed), "it exists: an edit, not a creation"
    assert not tool.creatable(root, "frontend/src/workbench/Fresh.css", allowed)
    assert not tool.creatable(root, "frontend/src/other/Fresh.jsx", allowed)
    assert not tool.creatable(root, "aios/security/new_gate.py", allowed)
    assert tool.creatable(root, "aios/memory/new_recall.py", allowed)
    assert not tool.creatable(root, "frontend/src/workbench/README", allowed)
