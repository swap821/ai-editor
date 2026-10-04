"""Plan Phase 7: the learning mutation probe is an instrument, so it is tested.

A probe that scored a kill on a crash, mutated the wrong place, left a file
mutated, or counted a guard's untested branch as covered would turn a broken
instrument into evidence. Each of those is pinned here.
"""

from __future__ import annotations

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
    entry names a test, and every named guard exists."""
    data = json.loads(probe.CATALOGUE.read_text(encoding="utf-8"))
    ids = [e["id"] for e in data["entries"]]
    assert len(ids) == len(set(ids))
    for entry in probe.load():
        text = (probe.REPO_ROOT / entry.file).read_bytes().decode("utf-8")
        assert text.replace("\r\n", "\n").count(entry.old) == 1, entry.id
        assert entry.tests, entry.id
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
