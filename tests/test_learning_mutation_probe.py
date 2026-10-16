"""Plan Phase 7: the learning mutation probe is an instrument, so it is tested.

A probe that scored a kill on a crash, mutated the wrong place, left a file
mutated, or counted a guard's untested branch as covered would turn a broken
instrument into evidence. Each of those is pinned here.
"""

from __future__ import annotations

import ast
import json

import pytest

from scripts import learning_mutation_probe as probe


def test_only_a_failing_test_is_a_kill() -> None:
    assert probe.killed(1) is True
    for code in (0, 2, 3, 4, 5, None):
        assert probe.killed(code) is False, code


def _entry(file: str = "guard.py", old: str = "x", new: str = "y", tests=None):
    return probe.Entry(id="t:case", file=file, old=old, new=new, tests=tests or ["t"])


def test_an_anchor_must_be_there_exactly_once() -> None:
    assert probe.apply_mutation("a x b", _entry()) == "a y b"
    with pytest.raises(probe.ProbeError, match="0 times"):
        probe.apply_mutation("a b", _entry())
    with pytest.raises(probe.ProbeError, match="2 times"):
        probe.apply_mutation("x x", _entry())


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(probe, "_dirty", lambda files: [])
    target = tmp_path / "guard.py"
    target.write_bytes(
        b"def admits(row):\r\n    if row.signed:\r\n        return True\r\n    return False\r\n"
    )
    return target


def test_a_dirty_target_refuses_the_run(sandbox, monkeypatch) -> None:
    monkeypatch.setattr(probe, "_dirty", lambda files: ["guard.py"])
    with pytest.raises(probe.ProbeError, match="uncommitted"):
        probe.run([_entry(old="if row.signed:", new="if True:")], runner=lambda n: 1)


def test_a_failing_baseline_refuses_the_run(sandbox) -> None:
    with pytest.raises(probe.ProbeError, match="baseline failed"):
        probe.run([_entry(old="if row.signed:", new="if True:")], runner=lambda n: 1)


def test_kills_survivors_and_restoration(sandbox) -> None:
    original = sandbox.read_bytes()
    calls: list[bytes] = []

    def runner(nodes):
        content = sandbox.read_bytes()
        calls.append(content)
        if content == original:
            return 0  # the baseline, and an unmutated tree, pass
        return 1 if b"if True:" in content else 0

    entries = [
        probe.Entry("t:killed", "guard.py", "if row.signed:", "if True:", ["t"]),
        probe.Entry("t:survives", "guard.py", "return False", "return  False", ["t"]),
        probe.Entry("t:missing", "guard.py", "no such text", "x", ["t"]),
    ]
    results = {r.id: r for r in probe.run(entries, runner=runner)}
    assert results["t:killed"].killed and not results["t:killed"].survived
    assert results["t:survives"].survived and results["t:survives"].returncode == 0
    assert results["t:missing"].survived and not results["t:missing"].applied
    assert sandbox.read_bytes() == original, "the file is restored byte-identically"
    assert any(b"\r\n" in c and b"if True:" in c for c in calls), "CRLF kept"


def test_decisions_and_coverage() -> None:
    text = (
        "def gate(row, principal):\n"
        "    if not principal:\n"
        "        return False\n"
        "    ok = row.a if row.b else row.c\n"
        "    kept = [r for r in row.items if r.signed]\n"
        "    while row.more:\n"
        "        pass\n"
        "    return ok\n"
    )
    decisions = probe.decisions_of(text, "g.py")
    assert [(d.function, d.line) for d in decisions] == [
        ("gate", 2),
        ("gate", 4),
        ("gate", 5),
        ("gate", 6),
    ]


def test_coverage_counts_only_killed_mutations_on_a_condition(tmp_path) -> None:
    (tmp_path / "g.py").write_text(
        "def gate(row, principal):\n"
        "    if not principal:\n"
        "        return False\n"
        "    if row.signed:\n"
        "        return True\n"
        "    return False\n",
        encoding="utf-8",
    )
    entries = [
        probe.Entry("t:a", "g.py", "if not principal:", "if False:", ["t"]),
        probe.Entry("t:b", "g.py", "if row.signed:", "if True:", ["t"]),
        probe.Entry(
            "t:c", "g.py", "        return True\n", "        return 1\n", ["t"]
        ),
    ]
    report = probe.coverage(
        entries, ["t:a", "t:c"], [("g.py", "gate"), ("g.py", "gone")], root=tmp_path
    )
    assert (report["decision_points"], report["attacked"]) == (2, 1)
    assert [u["line"] for u in report["unattacked"]] == [4], "t:b was not killed"
    assert report["missing_guards"] == ["g.py::gone"]


def test_the_committed_catalogue_applies_to_this_tree() -> None:
    """Every entry's anchor is in its file exactly once, ids are unique, every
    entry names a test, and every named guard exists.

    And every mutant is a PROGRAM. An indented anchor that a later change
    re-indents still matches once -- as a substring starting mid-line -- and
    deleting it leaves code that does not parse: pytest exits 2, which is not a
    kill, so the probe reports a guard as untested when the catalogue is what
    broke (found 2026-10-05: 3a's stop check, re-indented by Phase 6e)."""
    data = json.loads(probe.CATALOGUE.read_text(encoding="utf-8"))
    ids = [e["id"] for e in data["entries"]]
    assert len(ids) == len(set(ids))
    for entry in probe.load():
        text = (probe.REPO_ROOT / entry.file).read_bytes().decode("utf-8")
        text = text.replace("\r\n", "\n")
        assert text.count(entry.old) == 1, entry.id
        assert entry.tests, entry.id
        at = text.find(entry.old)
        if entry.old[:1] in " \t":
            assert at == 0 or text[at - 1] == "\n", f"{entry.id}: anchor is mid-line"
        if entry.file.endswith(".py"):
            try:
                ast.parse(text.replace(entry.old, entry.new))
            except SyntaxError as exc:
                pytest.fail(f"{entry.id}: the mutant does not parse ({exc.msg})")
    report = probe.coverage(probe.load(), [], probe.load_guards())
    assert report["missing_guards"] == []
    assert all(r["reason"] for r in data["retired"])


def test_a_run_killed_mid_mutation_is_restored_and_voided(sandbox) -> None:
    """On Windows a killed process runs no handler, so the in-flight journal
    is what puts the file back -- and the killed run's results are void."""
    import base64

    original = sandbox.read_bytes()
    sandbox.write_bytes(b"mutated")
    journal = probe._journal()
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        json.dumps(
            {
                "file": "guard.py",
                "id": "t:x",
                "original": base64.b64encode(original).decode(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(probe.ProbeError, match="killed mid-mutation"):
        probe.run([_entry(old="if row.signed:", new="if True:")], runner=lambda n: 0)
    assert sandbox.read_bytes() == original
    assert not journal.exists()


def test_every_catalogue_target_must_be_clean(sandbox, monkeypatch) -> None:
    """Not just this batch's: another file left mutated would skew its tests."""
    seen: list[set] = []
    monkeypatch.setattr(probe, "_dirty", lambda files: seen.append(set(files)) or [])
    monkeypatch.setattr(probe, "load", lambda path=None: [_entry(file="elsewhere.py")])
    probe.run([_entry(old="if row.signed:", new="if True:")], runner=lambda n: 0)
    assert seen and {"guard.py", "elsewhere.py"} <= seen[0]


# -------------------------------------------------------------- the ledger


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def _three(tmp_path):
    return [
        probe.Entry(f"t:{name}", "guard.py", "if row.signed:", "if True:", ["t"])
        for name in ("one", "two", "three")
    ]


def test_a_ledger_resumes_and_starts_nothing_after_its_budget(
    sandbox, tmp_path, monkeypatch
) -> None:
    clock = _Clock()
    monkeypatch.setattr(probe, "time", clock)
    original = sandbox.read_bytes()
    calls: list[str] = []

    def runner(nodes):
        mutated = sandbox.read_bytes() != original
        calls.append("mutation" if mutated else "baseline")
        if mutated and calls.count("mutation") == 2:
            clock.now = 100.0  # the budget runs out DURING the second mutation
        return 1 if mutated else 0

    ledger = tmp_path / "ledger.json"
    entries = _three(tmp_path)
    state = probe.run_ledger(
        entries, ledger, budget=50.0, runner=runner, identity=lambda: "tree-a"
    )
    assert calls == ["baseline", "mutation", "mutation"]
    assert sorted(state["results"]) == ["t:one", "t:two"]
    assert sandbox.read_bytes() == original

    calls.clear()
    clock.now = 0.0
    state = probe.run_ledger(
        entries, ledger, budget=50.0, runner=runner, identity=lambda: "tree-a"
    )
    assert calls == ["mutation"], "no baseline again, nothing recorded re-run"
    assert sorted(state["results"]) == ["t:one", "t:three", "t:two"]
    assert all(r["killed"] for r in state["results"].values())


def test_a_ledger_from_another_tree_is_refused(sandbox, tmp_path) -> None:
    ledger = tmp_path / "ledger.json"
    probe.run_ledger(
        _three(tmp_path),
        ledger,
        budget=0.0,
        runner=lambda nodes: 0,
        identity=lambda: "tree-a",
    )
    with pytest.raises(probe.ProbeError, match="start a new ledger"):
        probe.run_ledger(
            _three(tmp_path),
            ledger,
            budget=0.0,
            runner=lambda nodes: 0,
            identity=lambda: "tree-b",
        )


def test_a_ledger_needs_a_clean_tree(monkeypatch) -> None:
    monkeypatch.setattr(probe, "_dirty", lambda paths: ["tests/test_x.py"])
    with pytest.raises(probe.ProbeError, match="clean tree"):
        probe.tree_identity()


def test_the_cli_reports_only_a_complete_ledger(tmp_path, monkeypatch) -> None:
    entries = _three(tmp_path)
    monkeypatch.setattr(probe, "load", lambda path=probe.CATALOGUE: entries)
    monkeypatch.setattr(probe, "load_guards", lambda path=probe.CATALOGUE: {})
    monkeypatch.setattr(probe, "tree_identity", lambda: "tree-a")
    killed = {"applied": True, "returncode": 1, "killed": True}
    partial = {"t:one": {"id": "t:one", "file": "guard.py", **killed}}
    monkeypatch.setattr(probe, "run_ledger", lambda *a, **k: {"results": dict(partial)})
    assert probe.main(["--ledger", str(tmp_path / "l.json")]) == 3

    full = {e.id: {"id": e.id, "file": "guard.py", **killed} for e in entries}
    monkeypatch.setattr(probe, "run_ledger", lambda *a, **k: {"results": full})
    monkeypatch.setattr(
        probe,
        "coverage",
        lambda *a, **k: {"attacked": 0, "decision_points": 0, "guard_functions": 0},
    )
    out = tmp_path / "report.json"
    assert probe.main(["--ledger", str(tmp_path / "l.json"), "--json", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["mutations_killed"] == 3 and report["tree"] == "tree-a"
