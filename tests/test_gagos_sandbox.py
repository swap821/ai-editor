"""GAGOS's proposals run their tests before review, in the executor's sandbox.

The operator, 2026-11-03: "Yes honestly" to GAGOS running its own tests before
review. These tests drive :mod:`aios.maintenance.sandbox_tests` with a fake
container on a real git repository, and the daily tool's ``test`` step on a
real ledger. That the container itself contains what runs in it is proven in a
real one by tests/test_gagos_sandbox_containment.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.maintenance import daily_work as dw
from aios.maintenance import sandbox_tests as st
from tools import gagos_daily as tool

MODULE = "pkg/mod.py"
TESTS = "tests/test_mod.py"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture()
def project(tmp_path) -> tuple[Path, str]:
    root = tmp_path / "project"
    files = {
        "requirements.txt": "pytest\n",
        "pkg/__init__.py": "",
        MODULE: "def f():\n    return 1\n",
        "pkg/lonely.py": "X = 1\n",
        TESTS: (
            "from pkg.mod import f\n\n\ndef test_f():\n    assert f() == 1\n\n\n"
            "def test_flaky():\n    assert False\n"
        ),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "master", str(root)], check=True)
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-qm",
        "seed",
    )
    return root, _git(root, "rev-parse", "HEAD")


class FakeContainer:
    """Runs nothing: reads the tree it is given and answers as pytest would.
    ``test_f`` fails when the module says BROKEN; ``test_flaky`` always fails;
    a new test fails when it asserts False."""

    def __init__(self, *, killed: bool = False) -> None:
        self.killed = killed
        self.calls: list[list[str]] = []
        self.seen: list[str] = []

    def __call__(self, command, *, cwd, env, timeout_s):
        tree = Path(cwd)
        tests = command.split("--continue-on-collection-errors", 1)[1].split()
        self.calls.append(tests)
        self.seen.append((tree / MODULE).read_text(encoding="utf-8"))
        if self.killed:
            return "", "", 137
        failed, passed = [], 0
        for t in tests:
            if t == TESTS:
                broken = "BROKEN" in (tree / MODULE).read_text(encoding="utf-8")
                failed += [f"{t}::test_flaky"] + ([f"{t}::test_f"] if broken else [])
                passed += 0 if broken else 1
            elif "assert False" in (tree / t).read_text(encoding="utf-8"):
                failed.append(f"{t}::test_new")
            else:
                passed += 1
        lines = [f"FAILED {f} - AssertionError" for f in failed]
        summary = ", ".join(
            x
            for x in (f"{len(failed)} failed" if failed else "", f"{passed} passed")
            if x
        )
        return "\n".join([*lines, f"{summary} in 0.10s"]), "", 1 if failed else 0


def _run(project, text, rel=MODULE, *, container=None, ready=True, **kw):
    root, commit = project
    container = container or FakeContainer()
    with st.BaseTrees(root) as trees:
        verdict = st.run_proposal_tests(
            trees,
            base_commit=commit,
            rel=rel,
            new_text=text,
            runner_for=lambda image: container,
            image_ready=lambda image: ready,
            **kw,
        )
    return verdict, container


def test_a_proposal_that_breaks_a_passing_test_is_caught_and_named(project) -> None:
    verdict, container = _run(project, "def f():\n    return 2  # BROKEN\n")
    assert verdict.outcome == st.BROKE
    assert verdict.broken == (f"{TESTS}::test_f",)
    assert verdict.refusal.startswith(st.BROKE_PREFIX)
    # Judged against the base: the second run saw the original module.
    assert "BROKEN" in container.seen[0] and "BROKEN" not in container.seen[1]
    # Only names leave the machine, never directories.
    assert "tests/" not in verdict.summary and "test_mod.py::test_f" in verdict.summary


def test_a_test_that_fails_without_the_proposal_too_is_never_blamed(project) -> None:
    verdict, container = _run(project, "def f():\n    return 1\n\n\nY = 0\n")
    assert verdict.outcome == st.PASSED and verdict.refusal is None
    assert verdict.failing_anyway == (f"{TESTS}::test_flaky",)
    assert "not its doing" in verdict.summary
    assert len(container.calls) == 2


def test_the_copy_is_left_as_the_base_had_it(project) -> None:
    root, commit = project
    container = FakeContainer()
    with st.BaseTrees(root) as trees:
        st.run_proposal_tests(
            trees,
            base_commit=commit,
            rel=MODULE,
            new_text="def f():\n    return 2  # BROKEN\n",
            runner_for=lambda image: container,
            image_ready=lambda image: True,
        )
        tree = trees.get(commit)
        assert (tree / MODULE).read_text(encoding="utf-8") == "def f():\n    return 1\n"
        assert not (tree / ".git").exists() and (tree / TESTS).is_file()
    assert not tree.exists(), "the disposable copy is removed"


def test_a_new_test_runs_itself_and_its_failure_is_its_own(project) -> None:
    rel = "tests/test_lonely.py"
    passing, _ = _run(
        project, "from pkg.lonely import X\n\n\ndef test_x():\n    assert X == 1\n", rel
    )
    assert passing.outcome == st.PASSED and rel in passing.tests
    failing, _ = _run(project, "def test_new():\n    assert False\n", rel)
    assert failing.outcome == st.BROKE and failing.broken == (f"{rel}::test_new",)


def test_tests_are_found_however_the_copy_is_named(project) -> None:
    """CI, 2026-11-02: a temporary directory named otherwise than its real
    path (Windows' RUNNER~1, macOS's /var -> /private/var) found no test,
    because the import index answers in real paths."""
    root, commit = project
    with st.BaseTrees(root) as trees:
        tree = trees.get(commit)
        assert tree == tree.resolve()
        aside = tree / "pkg" / ".."
        assert st.select_tests(aside, MODULE) == ([TESTS], 1)


def test_a_file_no_test_exercises_is_untested(project) -> None:
    verdict, container = _run(project, "X = 2\n", "pkg/lonely.py")
    assert verdict.outcome == st.UNTESTED and not container.calls


def test_without_its_image_the_step_says_how_to_build_it(project) -> None:
    verdict, container = _run(project, "def f():\n    return 1\n", ready=False)
    assert verdict.outcome == st.UNAVAILABLE and not container.calls
    committed = (project[0] / "requirements.txt").read_bytes()
    assert st.verify_image(committed) in verdict.summary
    assert "docker build -f Dockerfile.verify" in verdict.summary


def test_tests_that_never_finish_are_not_blamed_on_either(project) -> None:
    verdict, _ = _run(
        project,
        "def f():\n    return 1\n",
        container=FakeContainer(killed=True),
        timeout_s=1,
    )
    assert verdict.outcome == st.UNAVAILABLE
    assert "with or without it" in verdict.summary


def test_pytest_output_is_read_for_counts_and_failing_ids() -> None:
    out = (
        "....F.E\n"
        "FAILED tests/a/test_x.py::TestY::test_z[a b] - assert 1 == 2\n"
        "ERROR tests/test_w.py - ImportError: nope\n"
        "1 failed, 5 passed, 1 error in 3.21s\n"
    )
    assert st.parse_pytest(out) == (
        5,
        ("tests/a/test_x.py::TestY::test_z[a b]", "tests/test_w.py"),
    )


def test_the_runner_is_the_executors_locked_down_container(
    project, monkeypatch
) -> None:
    """The argv GAGOS's tests run under. Its effect, in a real container, is
    tests/test_gagos_sandbox_containment.py."""
    monkeypatch.setenv("GAGOS_PROBE_TOKEN", "never-in-the-sandbox")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "never-either")
    seen: dict = {}

    def docker(argv, **kw):
        seen.setdefault("argv", argv)
        seen.setdefault("env", kw.get("env"))
        return subprocess.CompletedProcess(argv, 0, "1 passed in 0.10s\n", "")

    root, commit = project
    with st.BaseTrees(root) as trees:
        verdict = st.run_proposal_tests(
            trees,
            base_commit=commit,
            rel=MODULE,
            new_text="def f():\n    return 1\n",
            runner_for=lambda image: st.default_runner(image, process_runner=docker),
            image_ready=lambda image: True,
        )
    assert verdict.outcome == st.PASSED
    argv = seen["argv"]
    pairs = list(zip(argv, argv[1:]))
    assert ("--network", "none") in pairs and "--read-only" in argv
    assert ("--cap-drop", "ALL") in pairs
    assert ("--security-opt", "no-new-privileges") in pairs
    assert ("--memory", f"{st.MEMORY_MB}m") in pairs and (
        "--cpus",
        str(st.CPUS),
    ) in pairs
    mounts = [b for a, b in pairs if a == "--mount"]
    assert len(mounts) == 1 and "readonly=true" in mounts[0], "nothing writable"
    assert not any("never" in b for a, b in pairs if a == "--env")
    assert "GAGOS_PROBE_TOKEN" not in seen["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in seen["env"]
    image = next(a for a in argv if a.startswith("aios-verify:"))
    assert argv[argv.index(image) + 1 : argv.index(image) + 4] == [
        "timeout",
        "-s",
        "KILL",
    ]


# --------------------------------------------------------------------- the daily step


def _python_proposal(led, rel="aios/x.py"):
    finding = dw.Finding(rel=rel, rule="F401", warnings=((1, 1, "`os` unused"),))
    return led.record_proposal(
        finding,
        base_text="import os\n\nX = 1\n",
        base_commit="c" * 40,
        model="m",
        new_text="X = 1\n",
        verdict=dw.StaticVerdict(True, "ok", 2),
    )


class _Trees:
    def __init__(self, root) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        pass


def test_a_proposal_that_broke_its_tests_never_reaches_a_reviewer(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(
        tool,
        "run_proposal_tests",
        lambda trees, **kw: st.SandboxVerdict(
            st.BROKE,
            "1 test(s) pass without it and fail with it: test_x.py::test_a",
            ("tests/test_x.py",),
            ("tests/test_x.py::test_a",),
        ),
    )
    pid = _python_proposal(led)
    assert tool.cmd_test(SimpleNamespace(project=str(tmp_path), again=None)) == 0
    p = led.proposals()[0]
    assert p["proposal_id"] == pid and p["status"] == "refused"
    assert p["refusal"].startswith(st.BROKE_PREFIX)
    assert tool.lost_at(p) == "the sandbox tests"
    assert led.awaiting("claude") == [] and led.awaiting_tests() == []
    # The writers learn why (refusal_reasons feeds the next proposals).
    assert any(st.BROKE_PREFIX in r for r in led.refusal_reasons("F401"))


def test_the_reviewer_reads_what_the_tests_did(tmp_path, monkeypatch) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(
        tool,
        "run_proposal_tests",
        lambda trees, **kw: st.SandboxVerdict(st.PASSED, "9 tests in 2 files pass"),
    )
    _python_proposal(led)
    frontend = dw.Finding(rel="frontend/src/A.jsx", rule="no-unused-vars", warnings=())
    led.record_proposal(
        frontend,
        base_text="const a = 1;\n",
        base_commit="c" * 40,
        model="m",
        new_text="\n",
        verdict=dw.StaticVerdict(True, "ok", 1),
    )
    assert tool.cmd_test(SimpleNamespace(project=str(tmp_path), again=None)) == 0
    by = {p["rel"]: p for p in led.proposals()}
    assert {p["status"] for p in by.values()} == {"proposed"}
    py = by["aios/x.py"]
    finding = dw.Finding(rel=py["rel"], rule=py["rule"], warnings=((1, 1, "x"),))
    prompt = tool.review_evidence(py, finding)
    assert "in an isolated sandbox" in prompt and "9 tests in 2 files pass" in prompt
    front = st.SandboxVerdict.from_json(by["frontend/src/A.jsx"]["sandbox"])
    assert front.outcome == st.UNAVAILABLE and "no frontend toolchain" in front.summary
    assert "tests in the sandbox: **passed**" in tool.report(led)
    message = tool.commit_message(py, {})
    assert (
        "Before review, its tests ran in the sandbox: 9 tests in 2 files pass."
        in message
    )
