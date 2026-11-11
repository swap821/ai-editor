"""GAGOS's proposals run their tests before review, in the executor's sandbox.

The operator, 2026-11-03: "Yes honestly" to GAGOS running its own tests before
review. These tests drive :mod:`aios.maintenance.sandbox_tests` with a fake
container on a real git repository, and the daily tool's ``test`` step on a
real ledger. That the container itself contains what runs in it is proven in a
real one by tests/test_gagos_sandbox_containment.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
import json
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


# --------------------------------------------------- the frontend, and several files

LOCK = b'{"lockfileVersion": 3}\n'
WEB_MODULE = "frontend/src/util.js"
WEB_OTHER = "frontend/src/other.js"
WEB_TEST = "frontend/src/util.test.js"


@pytest.fixture()
def webproject(project) -> tuple[Path, str]:
    """The Python project plus a small frontend: ``util.js`` with a test that
    passes and one that always fails, ``other.js`` that no test imports."""
    root, _ = project
    files = {
        "frontend/package.json": "{}\n",
        "frontend/package-lock.json": "",
        WEB_MODULE: "export const f = () => 1\n",
        WEB_OTHER: "export const g = 1\n",
        WEB_TEST: "import { f } from './util'\n// test_works test_flaky\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    # Bytes, as committed: the image's tag is the hash of exactly these.
    (root / "frontend/package-lock.json").write_bytes(LOCK)
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-qm",
        "web",
    )
    return root, _git(root, "rev-parse", "HEAD")


def _report(files: dict[str, list[tuple[str, str]]], status: str | None = None) -> str:
    import json

    results = []
    for file, tests in files.items():
        results.append(
            {
                "name": f"/tmp/web/{file}",
                "status": status
                or ("failed" if any(s == "failed" for _, s in tests) else "passed"),
                "assertionResults": [
                    {"fullName": n, "title": n, "status": s} for n, s in tests
                ],
            }
        )
    passed = sum(s == "passed" for ts in files.values() for _, s in ts)
    return f"noise\n{st.WEB_MARKER}\n" + json.dumps(
        {"numPassedTests": passed, "testResults": results}
    )


class FakeWeb:
    """Runs no vitest: reads the tree and answers as the runner script would.
    ``works`` fails when util.js says BROKEN; ``flaky`` always fails."""

    def __init__(self, *, killed: bool = False, no_report: bool = False) -> None:
        self.killed, self.no_report = killed, no_report
        self.calls: list[tuple[str, list[str]]] = []
        self.seen: list[str] = []

    def __call__(self, command, *, cwd, env, timeout_s):
        tree = Path(cwd)
        words = command.split(st.WEB_RUNNER)[1].split()
        mode, files = words[0], words[1:]
        self.calls.append((mode, files))
        module = tree / WEB_MODULE
        self.seen.append(module.read_text(encoding="utf-8") if module.is_file() else "")
        if self.killed:
            return "", "", 137
        if self.no_report:
            return "", "Error: cannot find module", 1
        if mode == "typecheck":
            # tsc's own lines: a TYPEERROR in util.js is one error; one in
            # other.js is an error the base has too when the base has it.
            out = f"noise\n{st.TSC_MARKER}\n"
            src = tree / "frontend" / "src"
            errors = [
                f"src/{name}(1,1): error TS2322: Type 'string' is not assignable to type 'number'."
                for name in ("util.js", "other.js")
                if (src / name).is_file()
                and "TYPEERROR" in (src / name).read_text(encoding="utf-8")
            ]
            if not (src / "util.js").is_file():
                # A deleted module: its importer no longer resolves.
                errors.append(
                    "src/util.test.js(1,19): error TS2307: Cannot find module './util'."
                )
            return out + "\n".join(errors) + "\n", "", 2 if errors else 0
        if mode == "related":
            ran = [WEB_TEST[len("frontend/") :]] if "src/util.js" in files else []
        else:
            ran = files
        broken = not (tree / WEB_MODULE).is_file() or "BROKEN" in (
            tree / WEB_MODULE
        ).read_text(encoding="utf-8")
        report = {
            f: [("works", "failed" if broken else "passed"), ("flaky", "failed")]
            for f in ran
        }
        out = _report(report) if ran or True else ""
        failed = any(s == "failed" for ts in report.values() for _, s in ts)
        return out, "", 1 if failed else 0


def _set(project, changes, *, py=None, web=None, ready=lambda image: True):
    root, commit = project
    py = py or FakeContainer()
    web = web or FakeWeb()
    images: list[str] = []

    def runner_for(image):
        images.append(image)
        return web if image.startswith("aios-verify-web:") else py

    with st.BaseTrees(root) as trees:
        verdict = st.run_change_tests(
            trees,
            base_commit=commit,
            changes=changes,
            runner_for=runner_for,
            image_ready=ready,
        )
    return verdict, py, web, images


def test_a_frontend_change_runs_its_related_tests_in_the_web_image(webproject) -> None:
    verdict, py, web, images = _set(
        webproject, {WEB_MODULE: "export const f = () => 1\nexport const h = 2\n"}
    )
    # The test that always fails fails without the change too: not its doing.
    assert verdict.outcome == st.PASSED
    assert verdict.failing_anyway == ("src/util.test.js::flaky",)
    assert web.calls == [
        ("related", ["src/util.js"]),
        ("typecheck", []),
        ("run", ["src/util.test.js"]),
    ]
    assert images == [st.web_image(LOCK)] and not py.calls
    assert "types: tsc --noEmit is clean" in verdict.summary


def test_a_frontend_change_that_breaks_a_test_names_it(webproject) -> None:
    verdict, _, web, _ = _set(
        webproject, {WEB_MODULE: "export const f = () => 2 // BROKEN\n"}
    )
    assert verdict.outcome == st.BROKE
    assert verdict.broken == ("src/util.test.js::works",)
    assert verdict.refusal.startswith(st.BROKE_PREFIX)
    # Judged against the base: the second run saw the original module.
    assert "BROKEN" in web.seen[0] and "BROKEN" not in web.seen[-1]
    assert "frontend/" not in verdict.summary


def test_a_frontend_file_no_test_imports_is_untested(webproject) -> None:
    verdict, _, web, _ = _set(webproject, {WEB_OTHER: "export const g = 2\n"})
    assert verdict.outcome == st.UNTESTED
    assert [mode for mode, _ in web.calls] == ["related", "typecheck"]
    assert "types: tsc --noEmit is clean" in verdict.summary


def test_without_the_web_image_the_step_says_how_to_build_it(webproject) -> None:
    verdict, _, web, _ = _set(
        webproject,
        {WEB_MODULE: "export const f = () => 1\n"},
        ready=lambda image: False,
    )
    assert verdict.outcome == st.UNAVAILABLE and not web.calls
    assert st.web_image(LOCK) in verdict.summary
    assert "docker build -f Dockerfile.verify-web" in verdict.summary
    assert "package-lock.sha256=" in verdict.summary


def _dockerignore_excludes(path: str, patterns: list[str]) -> bool:
    """Docker's rule, for plain paths: a pattern that matches the path or one
    of its parent directories excludes it, a ``!`` pattern brings it back, and
    the last pattern that matches decides."""

    def regex(pattern: str) -> re.Pattern[str]:
        out, i = "", 0
        while i < len(pattern):
            if pattern.startswith("**/", i):
                out, i = out + "(?:.*/)?", i + 3
            elif pattern.startswith("**", i):
                out, i = out + ".*", i + 2
            else:
                ch = pattern[i]
                out += {"*": "[^/]*", "?": "[^/]"}.get(ch, re.escape(ch))
                i += 1
        return re.compile(out)

    parts = path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    excluded = False
    for raw in patterns:
        keep = raw.startswith("!")
        pattern = raw[1:].strip().strip("/") if keep else raw.strip().strip("/")
        if any(regex(pattern).fullmatch(prefix) for prefix in prefixes):
            excluded = not keep
    return excluded


def test_the_web_build_hint_has_the_files_its_dockerfile_copies() -> None:
    """The command the step prints builds from the repository root, and BuildKit
    reads ``Dockerfile.verify-web.dockerignore`` in place of ``.dockerignore``
    when it exists. Found 2026-11-09: the root one excludes ``frontend/``, so
    the printed command failed at its first COPY."""
    repo = Path(__file__).resolve().parents[1]
    hint = st.web_build_hint(LOCK)
    assert "-f Dockerfile.verify-web " in hint and hint.endswith(" .")
    ignore = repo / "Dockerfile.verify-web.dockerignore"
    if not ignore.exists():
        ignore = repo / ".dockerignore"
    patterns = [
        line.strip()
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    copied = [
        source
        for line in (repo / "Dockerfile.verify-web")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("COPY ") and "--from" not in line
        for source in line.split()[1:-1]
    ]
    assert copied, "Dockerfile.verify-web copies nothing: this test reads it wrong"
    for source in copied:
        assert (repo / source).is_file(), source
        assert not _dockerignore_excludes(source, patterns), (
            f"{ignore.name} keeps {source} out of the build context"
        )


def test_frontend_tests_that_never_finish_are_not_blamed_on_either(webproject) -> None:
    root, commit = webproject
    with st.BaseTrees(root) as trees:
        verdict = st.run_change_tests(
            trees,
            base_commit=commit,
            changes={WEB_MODULE: "export const f = () => 1\n"},
            runner_for=lambda image: FakeWeb(killed=True),
            image_ready=lambda image: True,
            timeout_s=1,
        )
    assert verdict.outcome == st.UNAVAILABLE
    assert "with or without it" in verdict.summary


def test_a_vitest_that_fails_to_start_is_unavailable_not_a_pass(webproject) -> None:
    verdict, *_ = _set(
        webproject,
        {WEB_MODULE: "export const f = () => 1\n"},
        web=FakeWeb(no_report=True),
    )
    assert verdict.outcome == st.UNAVAILABLE
    assert "vitest could not run" in verdict.summary


def test_a_change_to_the_lock_file_is_not_tested_in_an_image_built_from_it(
    webproject,
) -> None:
    verdict, _, web, _ = _set(webproject, {"frontend/package.json": '{"a": 1}\n'})
    # package.json is not a source suffix of its own: json is tested by import.
    assert verdict.outcome == st.UNAVAILABLE and not web.calls
    assert "package.json" in verdict.summary


def test_the_vitest_report_is_read_for_counts_files_and_failures() -> None:
    out = _report(
        {"src/a.test.js": [("ok", "passed"), ("bad", "failed")], "src/b.test.js": []},
    )
    # A file that failed to load has no test of its own and is named alone.
    out = out.replace(
        '"status": "passed", "assertionResults": []',
        '"status": "failed", "assertionResults": []',
    )
    passed, failing, files = st.parse_vitest(out)
    assert passed == 1
    assert failing == ("src/a.test.js::bad", "src/b.test.js")
    assert files == ("src/a.test.js", "src/b.test.js")
    for text in ("", f"{st.WEB_MARKER}\n", f"{st.WEB_MARKER}\n{{not json", "no marker"):
        with pytest.raises(ValueError):
            st.parse_vitest(text)


def test_several_python_files_run_in_one_pytest_and_every_file_is_restored(
    project,
) -> None:
    root, commit = project
    other = "pkg/lonely.py"
    container = FakeContainer()
    with st.BaseTrees(root) as trees:
        verdict = st.run_change_tests(
            trees,
            base_commit=commit,
            changes={MODULE: "def f():\n    return 2  # BROKEN\n", other: "X = 2\n"},
            runner_for=lambda image: container,
            image_ready=lambda image: True,
        )
        tree = trees.get(commit)
        assert (tree / MODULE).read_text(encoding="utf-8") == "def f():\n    return 1\n"
        assert (tree / other).read_text(encoding="utf-8") == "X = 1\n"
    assert verdict.outcome == st.BROKE and verdict.broken == (f"{TESTS}::test_f",)
    # One run with every change in place, one without.
    assert len(container.calls) == 2


def test_a_file_the_change_creates_is_removed_again_even_after_a_failure(
    project,
) -> None:
    root, commit = project
    new = "pkg/brand_new.py"

    def boom(command, *, cwd, env, timeout_s):
        assert (Path(cwd) / new).is_file(), "the change is in place while it runs"
        raise OSError("docker went away")

    with st.BaseTrees(root) as trees:
        verdict = st.run_change_tests(
            trees,
            base_commit=commit,
            changes={MODULE: "def f():\n    return 1\n", new: "Z = 1\n"},
            runner_for=lambda image: boom,
            image_ready=lambda image: True,
        )
        assert not (trees.get(commit) / new).exists()
    assert verdict.outcome == st.UNAVAILABLE


def test_a_mixed_set_runs_both_kinds_and_broke_if_either_broke(webproject) -> None:
    py_ok = "def f():\n    return 1\n\n\nY = 0\n"
    verdict, py, web, images = _set(
        webproject, {MODULE: py_ok, WEB_MODULE: "export const f = () => 2 // BROKEN\n"}
    )
    assert verdict.outcome == st.BROKE
    assert verdict.broken == ("src/util.test.js::works",)
    assert py.calls and web.calls and len(images) == 2
    assert "Python tests:" in verdict.summary and "frontend tests:" in verdict.summary


def test_a_mixed_set_passes_only_if_each_part_passed_or_had_nothing(webproject) -> None:
    py_ok = "def f():\n    return 1\n\n\nY = 0\n"
    ok, *_ = _set(webproject, {MODULE: py_ok, WEB_OTHER: "export const g = 2\n"})
    assert ok.outcome == st.PASSED
    nothing, *_ = _set(
        webproject, {"pkg/lonely.py": "X = 2\n", WEB_OTHER: "export const g = 2\n"}
    )
    assert nothing.outcome == st.UNTESTED
    # A part that could not run is not a pass for the change.
    cannot, *_ = _set(
        webproject,
        {MODULE: py_ok, WEB_MODULE: "export const f = () => 1\n"},
        ready=lambda image: image.startswith("aios-verify:"),
    )
    assert cannot.outcome == st.UNAVAILABLE and "docker build" in cannot.summary


def test_a_path_outside_the_project_is_refused_and_a_kind_without_tests_is_untested(
    project,
) -> None:
    root, commit = project
    with st.BaseTrees(root) as trees:
        out = st.run_change_tests(
            trees, base_commit=commit, changes={"../escape.py": "x", MODULE: "y"}
        )
        assert out.outcome == st.UNAVAILABLE
        docs = st.run_change_tests(
            trees, base_commit=commit, changes={"README.md": "x", "a.txt": "y"}
        )
    assert docs.outcome == st.UNTESTED


def test_the_web_runner_is_the_executors_locked_down_container(webproject) -> None:
    seen: dict = {}

    def docker(argv, **kw):
        seen.setdefault("argv", argv)
        return subprocess.CompletedProcess(argv, 0, _report({}), "")

    root, commit = webproject
    with st.BaseTrees(root) as trees:
        st.run_change_tests(
            trees,
            base_commit=commit,
            changes={WEB_MODULE: "export const f = () => 1\n"},
            runner_for=lambda image: st.default_runner(image, process_runner=docker),
            image_ready=lambda image: True,
        )
    argv = seen["argv"]
    pairs = list(zip(argv, argv[1:]))
    assert ("--network", "none") in pairs and "--read-only" in argv
    assert ("--cap-drop", "ALL") in pairs
    assert len([b for a, b in pairs if a == "--mount"]) == 1
    image = next(a for a in argv if a.startswith("aios-verify-web:"))
    tail = argv[argv.index(image) + 1 :]
    assert tail[:4] == ["timeout", "-s", "KILL", str(st.TEST_TIMEOUT_S)]
    assert tail[4:] == [st.WEB_RUNNER, "related", "src/util.js"]


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
        st,
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
        st,
        "run_proposal_tests",
        lambda trees, **kw: st.SandboxVerdict(st.PASSED, "9 tests in 2 files pass"),
    )
    # The frontend sandbox exists since D14; here its image is not built, so
    # the frontend proposal's verdict says that.
    monkeypatch.setattr(st, "image_built", lambda image: False)
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_Trees, "get", lambda self, commit: tmp_path, raising=False)
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
    assert front.outcome == st.UNAVAILABLE and "not built" in front.summary
    assert "tests in the sandbox: **passed**" in tool.report(led)
    message = tool.commit_message(py, {})
    assert (
        "Before review, its tests ran in the sandbox: 9 tests in 2 files pass."
        in message
    )


def test_a_test_name_the_privacy_filter_hides_does_not_hide_the_change(
    tmp_path,
) -> None:
    """2026-11-03, GAGOS's first hour with Claude writers: two correct changes
    were refused as unshowable, because the privacy filter took the name of a
    test that fails on master too for something sensitive. The real filters,
    no stand-ins."""
    led = dw.DailyLedger(tmp_path / "ledger.db")
    pid = _python_proposal(led)
    name = "test_api_main_gaps.py::test_get_executor_and_rollback_engine_return_real_instances"
    verdict = st.SandboxVerdict(
        st.PASSED,
        f"195 tests in 2 files pass; 1 fail without it too, so not its doing: {name}",
        failing_anyway=(name,),
    )
    assert tool.would_be_altered(verdict.for_reviewer(), ""), (
        "the case itself: the filter would change this name"
    )
    led.record_sandbox(pid, verdict.to_json())
    [p] = led.proposals()
    finding = dw.Finding(rel=p["rel"], rule=p["rule"], warnings=((1, 1, "x"),))
    prompt = tool.review_evidence(p, finding)
    assert "195 tests in 2 files pass" in prompt
    assert "test_get_executor_and_rollback_engine_return_real_instances" not in prompt


def test_the_councils_critique_queen_pre_screens_each_tested_proposal(
    tmp_path, monkeypatch
) -> None:
    """Codex's design conditions (2026-11-02): a council pre-screen, advisory.
    The Critique queen says whether the pass was earned; the reviewer and the
    report read it; the proposal's status stays the reviewers' to decide."""
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    verdicts = iter(
        [
            st.SandboxVerdict(
                st.PASSED, "4 tests in 1 files pass", ("tests/test_x.py",)
            ),
            st.SandboxVerdict(st.UNTESTED, "no test imports aios/y.py"),
        ]
    )
    monkeypatch.setattr(st, "run_proposal_tests", lambda trees, **kw: next(verdicts))
    _python_proposal(led, "aios/x.py")
    _python_proposal(led, "aios/y.py")
    assert tool.cmd_test(SimpleNamespace(project=str(tmp_path), again=None)) == 0
    by = {p["rel"]: p for p in led.proposals()}
    assert {p["status"] for p in by.values()} == {"proposed"}, "it decides nothing"
    earned = json.loads(by["aios/x.py"]["prescreen"])
    hollow = json.loads(by["aios/y.py"]["prescreen"])
    assert earned["queen"] == "critique" and earned["verdict"] == "accept"
    assert hollow["verdict"] == "defer" and "NONE" in hollow["reason"]
    finding = dw.Finding(rel="aios/y.py", rule="F401", warnings=((1, 1, "x"),))
    prompt = tool.review_evidence(by["aios/y.py"], finding)
    assert "Critique queen" in prompt and "advisory; it decides nothing" in prompt
    assert "the council's Critique queen (advisory): **defer**" in tool.report(led)


def test_a_proposal_the_sandbox_refused_gets_no_pre_screen(
    tmp_path, monkeypatch
) -> None:
    led = dw.DailyLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(tool, "ledger", lambda: led)
    monkeypatch.setattr(tool, "BaseTrees", _Trees)
    monkeypatch.setattr(
        st,
        "run_proposal_tests",
        lambda trees, **kw: st.SandboxVerdict(
            st.BROKE, "1 test(s) break", ("tests/test_x.py",), ("tests/test_x.py::t",)
        ),
    )
    _python_proposal(led)
    assert tool.cmd_test(SimpleNamespace(project=str(tmp_path), again=None)) == 0
    [p] = led.proposals()
    assert p["status"] == "refused" and p["prescreen"] is None


# --------------------------------------------------------------------- the type check (2026-11-11)


def test_a_change_that_adds_type_errors_is_broke_whatever_its_tests_did(
    webproject,
) -> None:
    verdict, _, web, _ = _set(
        webproject, {WEB_MODULE: "export const f = () => 1 // TYPEERROR\n"}
    )
    assert verdict.outcome == st.BROKE
    assert verdict.summary.startswith(
        "it adds 1 TypeScript error(s) the base does not have"
    )
    assert "TS2322" in verdict.summary and "tsc src/util.js TS2322" in verdict.broken
    assert [mode for mode, _ in web.calls].count("typecheck") == 2, (
        "with it, then without"
    )
    assert verdict.refusal.startswith(st.BROKE_PREFIX)


def test_type_errors_the_base_has_too_are_not_the_changes_doing(webproject) -> None:
    root, _ = webproject
    (root / WEB_OTHER).write_text("export const g = 1 // TYPEERROR\n", encoding="utf-8")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-qam",
        "e",
    )
    commit = _git(root, "rev-parse", "HEAD")
    verdict, _, _, _ = _set(
        (root, commit), {WEB_MODULE: "export const f = () => 1\nexport const h = 2\n"}
    )
    assert verdict.outcome == st.PASSED
    assert "no new type errors (1 exist without it too)" in verdict.summary


def test_a_clean_type_check_never_makes_an_untested_change_tested(webproject) -> None:
    verdict, _, _, _ = _set(webproject, {WEB_OTHER: "export const g = 2\n"})
    assert verdict.outcome == st.UNTESTED


def test_a_type_check_that_cannot_run_is_said_and_decides_nothing(webproject) -> None:
    class NoTsc(FakeWeb):
        def __call__(self, command, *, cwd, env, timeout_s):
            if "typecheck" in command:
                return "", "node: not found", 127
            return super().__call__(command, cwd=cwd, env=env, timeout_s=timeout_s)

    verdict, _, _, _ = _set(
        webproject,
        {WEB_MODULE: "export const f = () => 1\nexport const h = 2\n"},
        web=NoTsc(),
    )
    assert verdict.outcome == st.PASSED
    assert "types: not checked, tsc could not run" in verdict.summary


def test_the_web_image_is_named_by_its_lock_and_its_runner() -> None:
    import hashlib

    assert (
        st.web_image(LOCK) == f"aios-verify-web:{hashlib.sha256(LOCK).hexdigest()[:12]}"
    )
    assert st.web_image(LOCK, b"#!/bin/sh\n") != st.web_image(LOCK)
    runner = (Path(__file__).resolve().parents[1] / st.WEB_RUNNER_SOURCE).read_bytes()
    assert st.web_image(LOCK, runner) in st.web_build_hint(LOCK, runner)


def test_the_runner_script_has_the_typecheck_mode_the_step_calls() -> None:
    script = (Path(__file__).resolve().parents[1] / st.WEB_RUNNER_SOURCE).read_text(
        encoding="utf-8"
    )
    assert '"$mode" = "typecheck"' in script and f"echo {st.TSC_MARKER}" in script
    assert "tsc --noEmit -p tsconfig.json --pretty false" in script.replace(
        "node_modules/typescript/bin/", ""
    )


def test_tscs_lines_are_read_by_file_code_and_message() -> None:
    out = (
        f"warn\n{st.TSC_MARKER}\n"
        "src/a.ts(3,7): error TS2322: Type 'x' is not assignable.\n"
        "src/a.ts(9,1): error TS2322: Type 'x' is not assignable.\n"
        "Found 2 errors.\n"
    )
    found = st.parse_tsc(out)
    assert found == {("src/a.ts", "TS2322", "Type 'x' is not assignable."): 2}
    with pytest.raises(ValueError):
        st.parse_tsc("no marker")


# --------------------------------------------------------------------- deletions (2026-11-11)


def test_deleting_a_module_others_import_is_broke_by_the_type_check(webproject) -> None:
    root, commit = webproject
    verdict, _, web, _ = _set(webproject, {WEB_MODULE: None})
    assert verdict.outcome == st.BROKE
    assert "TS2307" in verdict.summary and "Cannot find module" in verdict.summary
    assert [mode for mode, _ in web.calls][0] == "typecheck", (
        "no related run for a deletion"
    )
    assert (root / WEB_MODULE).is_file(), "the operator's checkout is never touched"


def test_deleting_a_file_nothing_imports_is_untested_and_type_clean(webproject) -> None:
    verdict, _, web, _ = _set(webproject, {WEB_OTHER: None})
    assert verdict.outcome == st.UNTESTED
    assert "only deletes 1 frontend file" in verdict.summary
    assert "types: tsc --noEmit is clean" in verdict.summary


def test_a_deleted_file_is_back_in_the_base_copy_afterwards(tmp_path) -> None:
    tree = tmp_path / "tree"
    (tree / "src").mkdir(parents=True)
    a = b"export const a = 1;\n"
    (tree / "src/a.js").write_bytes(a)
    applied = st._Applied(tree, {"src/a.js": None, "src/b.js": "export const b = 2;\n"})
    applied.apply()
    assert not (tree / "src/a.js").exists() and (tree / "src/b.js").is_file()
    applied.revert()
    assert (tree / "src/a.js").read_bytes() == a
    assert not (tree / "src/b.js").exists()
