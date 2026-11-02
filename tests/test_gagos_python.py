"""GAGOS's Python work (2026-11-02): its backend and itself, not only its
frontend. The operator: the workshop must be "capable of improving its both
backend and frontend and itself". Pinned here, with the project's real ruff
and no model or network:

* GAGOS may change tracked Python under ``aios/`` and ``tools/``, never the
  frozen security core and never an organ's production entrypoint; without
  the organ ledger it changes no Python at all;
* ruff and the parser judge a text that is not on disk, with ``# noqa``
  honoured and ignored, so a proposal cannot hide a warning;
* removing an import another module takes from this one is refused;
* the writer and the reviewer are told it is Python, and delivery checks it
  with the tests that import it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from aios.maintenance import python_static as ps
from aios.maintenance.frontend_static import StaticCheckUnavailable
from tests.test_gagos_daily import _deliver_args, _git, _repo
from tests.test_gagos_identity_and_day import _both
from tools import gagos_daily as tool

PY_REL = "tools/helper.py"
PY_BEFORE = "import os\nimport sys\n\n\ndef where():\n    return sys.platform\n"
PY_AFTER = "import sys\n\n\ndef where():\n    return sys.platform\n"


def _py_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = _repo(tmp_path / "project")
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode())
    if files:
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "python")
    return root


def test_gagos_may_change_its_backend_and_itself_never_the_frozen_core(
    tmp_path, monkeypatch
) -> None:
    root = _py_repo(
        tmp_path,
        {
            "aios/core/thing.py": "x = 1\n",
            "aios/security/scope_lock.py": "x = 1\n",
            "aios/organ.py": "x = 1\n",
            PY_REL: PY_BEFORE,
            "tools/notes.md": "not python\n",
            "tests/test_x.py": "x = 1\n",
        },
    )
    monkeypatch.setattr(ps, "organ_entrypoints", lambda r: frozenset({"aios/organ.py"}))
    assert ps.editable_python_files(root) == ["aios/core/thing.py", PY_REL]


def test_without_the_organ_ledger_no_python_is_changed(tmp_path) -> None:
    root = _py_repo(tmp_path, {PY_REL: PY_BEFORE})
    with pytest.raises(StaticCheckUnavailable, match="organ ledger"):
        ps.editable_python_files(root)


def test_ruff_and_the_parser_judge_a_text_not_on_disk(tmp_path) -> None:
    root = _py_repo(tmp_path, {})
    hidden = "import os  # noqa: F401\n"
    broken = "def f(:\n"
    results = ps.check_python_texts(
        root,
        {PY_REL: PY_BEFORE, "tools/h.py": hidden, "tools/b.py": broken},
        inline_off=True,
    )
    [unused] = results[PY_REL].warnings("F401")
    assert (unused.line, unused.rule) == (1, "F401") and "os" in unused.message
    assert results["tools/h.py"].warnings() == [], "noqa honoured"
    assert [m.rule for m in results["tools/h.py"].hidden()] == ["F401"], "and seen"
    assert [c.value for c in results["tools/h.py"].comments] == [" noqa: F401"]
    assert results["tools/b.py"].parse_errors and results["tools/b.py"].errors


def _finding(text, root, rule="F401"):
    [result] = ps.check_python_texts(root, {PY_REL: text}).values()
    [f] = dw.findings({PY_REL: result}, rules=[rule])
    return f


def _verdict(root, before, after):
    f = _finding(before, root)
    checked = ps.check_python_texts(root, {PY_REL: before}, inline_off=True)[PY_REL]
    then = ps.check_python_texts(root, {PY_REL: after}, inline_off=True)[PY_REL]
    return dw.static_verdict(f, before, after, checked, then)


def test_the_unattended_checks_on_a_python_fix(tmp_path) -> None:
    root = _py_repo(tmp_path, {})
    assert _verdict(root, PY_BEFORE, PY_AFTER).passed
    silenced = PY_BEFORE.replace("import os\n", "import os  # noqa\n")
    refused = _verdict(root, PY_BEFORE, silenced)
    assert not refused.passed and "disable comment" in refused.reason
    broken = _verdict(root, PY_BEFORE, PY_AFTER + "def (:\n")
    assert not broken.passed and "does not parse" in broken.reason
    worse = _verdict(root, PY_BEFORE, PY_AFTER + "print(undefined_name)\n")
    assert not worse.passed and "adds warnings: F821" in worse.reason


def test_an_import_another_module_takes_from_here_stays(tmp_path) -> None:
    lib = "aios/lib.py"
    before = "import os\nfrom json import dumps\n"
    root = _py_repo(
        tmp_path,
        {lib: before, "aios/user.py": "from aios.lib import (\n    dumps,\n)\n"},
    )
    refusal = ps.import_refusal(root, lib, before, "import os\n")
    assert refusal and "dumps" in refusal and "user.py" in refusal
    assert ps.import_refusal(root, lib, before, "from json import dumps\n") is None
    assert ps.module_of("aios/pkg/__init__.py") == "aios.pkg"


def test_the_writer_and_the_reviewer_are_told_it_is_python(tmp_path) -> None:
    root = _py_repo(tmp_path, {})
    f = _finding(PY_BEFORE, root)
    assert dw.proposer_system(PY_REL) == dw.PYTHON_PROPOSER_SYSTEM
    assert "ruff" in dw.PYTHON_PROPOSER_SYSTEM and "noqa" in dw.PYTHON_PROPOSER_SYSTEM
    prompt = dw.review_prompt(f, PY_BEFORE, "diff")
    assert "backend (Python" in prompt and "ruff warnings" in prompt
    assert "ESLint" not in prompt and "tools/" not in prompt


def test_a_batch_proposes_a_python_fix(tmp_path, monkeypatch) -> None:
    root = _py_repo(tmp_path, {PY_REL: PY_BEFORE})
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "check_texts", lambda r, texts, **kw: {})
    monkeypatch.setattr(ps, "organ_entrypoints", lambda r: frozenset())
    monkeypatch.setattr(tool, "cloud_coding_allowed", lambda: (True, ""))
    systems: list = []

    def completer(model, region):
        def complete(prompt, system, request_id):
            systems.append(system)
            assert "helper.py" in prompt and "tools/" not in prompt
            return f"```python\n{PY_AFTER}```"

        return complete

    monkeypatch.setattr(tool, "governed_completer", completer)
    args = SimpleNamespace(
        project=str(root),
        budget=5,
        model="m",
        region="r",
        rules=["F401"],
        dry_run=False,
    )
    assert tool.cmd_propose(args) == 0
    [p] = led.proposals()
    assert (p["rel"], p["rule"], p["status"]) == (PY_REL, "F401", "proposed")
    assert systems == [dw.PYTHON_PROPOSER_SYSTEM]


@pytest.fixture()
def py_origin_and_worktree(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True
    )
    seed = _py_repo(tmp_path, {PY_REL: PY_BEFORE})
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "master")
    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", "-q", "-c", "core.autocrlf=false", str(origin), str(work)],
        check=True,
    )
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    return work


def test_delivery_checks_python_with_the_tests_that_import_it(
    tmp_path, monkeypatch, py_origin_and_worktree
) -> None:
    work = py_origin_and_worktree
    led = dw.DailyLedger(tmp_path / "l.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    from aios.application.promotion import smoke

    checked: list = []

    def python_smoke(root, targets, **kw):
        checked.append(list(targets))
        return smoke.SmokeReport(True, "ok", list(targets), [])

    monkeypatch.setattr(smoke, "python_smoke", python_smoke)
    monkeypatch.setattr(
        smoke, "frontend_smoke", lambda *a, **kw: pytest.fail("not the frontend's")
    )
    root = Path(work)
    [result] = ps.check_python_texts(root, {PY_REL: PY_BEFORE}).values()
    [f] = dw.findings({PY_REL: result}, rules=["F401"])
    pid = led.record_proposal(
        f,
        base_text=PY_BEFORE,
        base_commit="c" * 40,
        model="m",
        new_text=PY_AFTER,
        verdict=dw.StaticVerdict(True, "ok", 1),
    )
    _both(led, pid)
    assert tool.cmd_deliver(_deliver_args(work)) == 0
    assert checked == [[PY_REL]]
    assert (work / PY_REL).read_text(encoding="utf-8") == PY_AFTER
    message = _git(work, "log", "-1", "--format=%B")
    assert message.startswith(f"GAGOS: fix F401 in {PY_REL}")
    assert "it compiles, and the tests that import it pass" in message
