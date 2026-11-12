"""A proposal's tests, run before review, in the executor's sandbox.

(Since 2026-11-03, later the same day: a task's several files run together,
and so does the frontend. See :func:`run_change_tests`, and the frontend
paragraph at the end of this docstring. What follows describes a Python
proposal, which every other kind of change copies.)

The operator, 2026-11-03, on GAGOS running its own tests before review: "Yes
honestly". Until then nothing a model wrote ran before a reviewer accepted it.
Its checks were static, and its tests ran only at delivery, on the host. That
kept GAGOS to changes a reader can judge by eye.

Here a proposal's tests run before review, and only inside the sandbox the
executor already uses for model-authored commands
(:class:`aios.core.executor.DockerRunner`, whose containment CI exercises in a
real container): no network, a read-only root, every capability dropped,
no-new-privileges, memory, CPU, process and file-size limits, and nothing from
the host's environment. What the container sees:

- a disposable copy of the proposal's base commit, made by ``git archive``:
  tracked files only, so no ``.git``, ``.env`` or ``data/``. It is mounted
  read-only;
- the proposal's file, written into that copy;
- the image ``aios-verify:<sha12 of that commit's requirements.txt>``
  (``Dockerfile.verify``; the name ``tools/daily_backend.py`` derives). When it
  is not built, the step is unavailable and says how to build it: a stale
  image turns a missing package into an ImportError that reads as a failing
  test.

Which tests run: the test files that import the file (the promotion smoke's own
index, :func:`find_exercising_tests`), plus the file itself when it is a test.
At most :data:`MAX_TEST_FILES` run, those named for the module first.

A proposal is judged against its base, never alone. When tests fail with the
proposal, the same tests run on the base. Only a test that passes without the
proposal and fails with it is the proposal's doing. A test that fails on both
belongs to the project: it is reported and never blamed. (2026-11-02: an
accepted change failed its delivery on a test that times out on this laptop,
with or without the change.)

The frontend, and several files (the operator, 2026-11-03, on frontend changes
"only tested at delivery, not before review" and on a task over several
files: "plz honestly do all"). A file under ``frontend/`` runs its tests in
``aios-verify-web:<sha12 of frontend/package-lock.json>``
(``Dockerfile.verify-web``, ``tools/verify_web_run.sh``): the same flags, the
frontend copied to ``/tmp`` with the image's ``node_modules`` linked in, and
``vitest related`` for the changed modules, judged against the base exactly as
above. A change to ``package.json`` or the lock file is not tested there, since
the image holds the base's dependencies. A set of changes is written into the
copy together, its Python files tested in one pytest run and its frontend
files in one vitest run, each against the base with the whole set removed; a
set with both combines the two verdicts (:func:`_combine`).
"""

from __future__ import annotations

import hashlib
from collections import Counter
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol, Sequence

from aios.application.promotion.smoke import (
    FRONTEND_SMOKE_SUFFIXES,
    find_exercising_tests,
)
from aios.core.executor import DockerRunner

#: At most this many test files run for one proposal.
MAX_TEST_FILES = 12
#: Seconds one pytest run may take inside the container before it is killed
#: there (``timeout -s KILL``): a killed client would leave the container running.
TEST_TIMEOUT_S = 300
#: The container's own limits, above the executor's defaults (1 GiB, 1 CPU):
#: a test file that loads the API app needs more than a mission's command.
MEMORY_MB = 2048
CPUS = 2.0
#: pytest's exit when ``timeout -s KILL`` ends it.
_KILLED = 137

PASSED = "passed"
BROKE = "broke"
UNTESTED = "untested"
UNAVAILABLE = "unavailable"
#: How a refusal for broken tests begins (GAGOS's report counts these apart).
BROKE_PREFIX = "the proposal breaks tests that pass without it"

#: The only variables the ``docker`` client is given. The container receives
#: none of them (``docker run`` forwards only its ``--env`` flags); this list
#: is what lets the client find its engine and nothing else.
_CLIENT_ENV = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOME",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
)


class Runner(Protocol):
    def __call__(
        self, command: str, *, cwd: str, env: dict[str, str], timeout_s: int
    ) -> tuple[str, str, int]: ...


class SandboxUnavailable(RuntimeError):
    """The sandbox could not run the tests: no engine, no image, no tree."""


def client_env() -> dict[str, str]:
    """The ``docker`` client's environment: :data:`_CLIENT_ENV` only."""
    wanted = {name.upper() for name in _CLIENT_ENV}
    return {k: v for k, v in os.environ.items() if k.upper() in wanted}


def verify_image(requirements: bytes) -> str:
    """The sandbox image for these requirements (``Dockerfile.verify``)."""
    return f"aios-verify:{hashlib.sha256(requirements).hexdigest()[:12]}"


def build_hint(requirements: bytes) -> str:
    sha = hashlib.sha256(requirements).hexdigest()
    return (
        f"docker build -f Dockerfile.verify --label requirements.sha256={sha} "
        f"-t {verify_image(requirements)} ."
    )


def default_runner(
    image: str,
    process_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> DockerRunner:
    """The executor's runner, unchanged, with the limits above."""
    return DockerRunner(
        image=image, memory_mb=MEMORY_MB, cpus=CPUS, process_runner=process_runner
    )


def _run(
    argv: list[str],
    *,
    timeout: float,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """The one place this module runs a program on the host: ``git archive``
    or ``docker image inspect``, by absolute path, never through a shell.
    What a proposal runs goes through the executor's DockerRunner instead."""
    return subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False
    )


def image_built(image: str) -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        found = _run([docker, "image", "inspect", image], env=client_env(), timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return found.returncode == 0


class BaseTrees:
    """Disposable copies of base commits, one per commit, removed on close."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self._trees: dict[str, Path] = {}

    def get(self, commit: str) -> Path:
        if commit in self._trees:
            return self._trees[commit]
        git = shutil.which("git")
        if git is None:
            raise SandboxUnavailable("git is not on PATH")
        try:
            done = _run(
                [git, "archive", "--format=tar", commit],
                cwd=self.project_root,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxUnavailable(f"git archive {commit[:12]} failed: {exc}")
        if done.returncode != 0:
            why = done.stderr.decode("utf-8", "replace").strip()[:200]
            raise SandboxUnavailable(f"git archive {commit[:12]} failed: {why}")
        # Resolved once, here: a temporary directory's name can differ from
        # its real path (Windows short names, macOS's /var -> /private/var),
        # and the import index answers in real paths.
        tree = Path(tempfile.mkdtemp(prefix="gagos-sbx-")).resolve()
        try:
            with tarfile.open(fileobj=io.BytesIO(done.stdout)) as tar:
                tar.extractall(tree, filter="data")
        except (tarfile.TarError, OSError) as exc:
            shutil.rmtree(tree, ignore_errors=True)
            raise SandboxUnavailable(f"the copy of {commit[:12]} failed: {exc}")
        self._trees[commit] = tree
        return tree

    def close(self) -> None:
        for tree in self._trees.values():
            shutil.rmtree(tree, ignore_errors=True)
        self._trees.clear()

    def __enter__(self) -> BaseTrees:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass(frozen=True)
class PytestRun:
    """One pytest run in the sandbox."""

    timed_out: bool
    exit_code: int
    passed: int
    failing: tuple[str, ...]
    seconds: float


@dataclass(frozen=True)
class SandboxVerdict:
    outcome: str
    summary: str
    tests: tuple[str, ...] = ()
    broken: tuple[str, ...] = ()
    failing_anyway: tuple[str, ...] = ()
    seconds: float = 0.0
    #: The run's own counts, where it reported them (2026-11-12): what organ
    #: 15 grades a mission's verification by. 0 where nothing ran.
    passed_count: int = 0
    failed_count: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True)

    @classmethod
    def from_json(cls, text: str) -> SandboxVerdict:
        data = json.loads(text)
        return cls(
            **{
                k: tuple(v) if isinstance(v, list) else v
                for k, v in data.items()
                if k in cls.__dataclass_fields__
            }
        )

    @property
    def refusal(self) -> str | None:
        """The proposal's refusal when it broke tests, else None."""
        if self.outcome != BROKE:
            return None
        return f"{BROKE_PREFIX}: {self.summary}"

    def for_reviewer(self) -> str:
        """What the reviewer is told: test names only, never paths."""
        if self.outcome in (PASSED, BROKE):
            return (
                "Before this review, GAGOS ran the tests that exercise this file "
                "with the change applied, in an isolated sandbox (no network, "
                f"read-only): {self.summary}."
            )
        if self.outcome == UNTESTED:
            return f"No test ran before this review: {self.summary}."
        return f"Its tests were not run before this review: {self.summary}."


def _name(node: str) -> str:
    """A test id without its directories: paths do not leave the machine."""
    file, sep, rest = node.partition("::")
    return PurePosixPath(file).name + sep + rest


def _names(nodes: Sequence[str], limit: int = 5) -> str:
    shown = ", ".join(_name(n) for n in list(nodes)[:limit])
    more = len(nodes) - limit
    return shown + (f" and {more} more" if more > 0 else "")


_FAILING = re.compile(r"^(?:FAILED|ERROR) (.+?)(?: - .*)?$")
_COUNT = re.compile(r"(\d+) (passed|failed|errors?)\b")


def parse_pytest(output: str) -> tuple[int, tuple[str, ...]]:
    """(tests passed, failing or erroring test ids) from ``-q -rfE`` output."""
    failing = []
    for line in output.splitlines():
        match = _FAILING.match(line.strip())
        if match:
            failing.append(match.group(1).strip())
    passed = 0
    for line in reversed(output.splitlines()):
        counts = dict((kind, int(n)) for n, kind in _COUNT.findall(line))
        if counts:
            passed = counts.get("passed", 0)
            break
    return passed, tuple(dict.fromkeys(failing))


def _pytest(
    runner: Runner, tree: Path, tests: Sequence[str], timeout_s: int
) -> PytestRun:
    command = " ".join(
        [
            "timeout",
            "-s",
            "KILL",
            str(timeout_s),
            "env",
            # tests/conftest.py makes its scratch under the repository unless
            # told otherwise; the copy is read-only, the container's /tmp is not.
            "PYTEST_DEBUG_TEMPROOT=/tmp/gagos-pytest",
            "python",
            "-m",
            "pytest",
            "-q",
            "-rfE",
            "--tb=no",
            "--continue-on-collection-errors",
            *tests,
        ]
    )
    started = time.monotonic()
    try:
        out, err, code = runner(
            command, cwd=str(tree), env=client_env(), timeout_s=timeout_s + 120
        )
    except subprocess.TimeoutExpired:
        return PytestRun(True, _KILLED, 0, (), time.monotonic() - started)
    except (RuntimeError, ValueError, OSError) as exc:
        raise SandboxUnavailable(str(exc)) from exc
    seconds = time.monotonic() - started
    if code == _KILLED:
        if seconds < timeout_s - 5:
            # Killed early: not the clock. The container's memory limit.
            raise SandboxUnavailable(
                f"the tests were killed after {seconds:.0f}s, before the "
                f"{timeout_s}s limit (the container's {MEMORY_MB} MiB, most likely)"
            )
        return PytestRun(True, code, 0, (), seconds)
    if code in (3, 4) or code > 5:
        tail = (err or out).strip().splitlines()[-1:] or [f"exit {code}"]
        raise SandboxUnavailable(f"pytest could not run (exit {code}): {tail[0][:200]}")
    passed, failing = parse_pytest(out)
    if code in (1, 2) and not failing:
        failing = (f"(pytest exit {code})",)
    return PytestRun(False, code, passed, failing, seconds)


#: The frontend sandbox (2026-11-03). The operator, on the face's changes being
#: "only tested at delivery, not before review": "plz honestly do all". A
#: change under ``frontend/`` runs its related tests in ``aios-verify-web``
#: (``Dockerfile.verify-web``), sealed exactly as the Python tests are, then
#: judged against the base the same way.
FRONTEND_DIR = "frontend"
#: Frontend files the sandbox has tests for: ``vitest related`` follows the
#: module graph, so a stylesheet or a JSON file a component imports counts.
FRONTEND_SUFFIXES = FRONTEND_SMOKE_SUFFIXES + (".css", ".json")
#: A change to these is a change to what the image holds: it cannot be tested
#: in an image built from the base's copy.
_WEB_LOCKED = ("frontend/package.json", "frontend/package-lock.json")
#: The runner script baked into the image (tools/verify_web_run.sh), and the
#: line it prints before vitest's JSON report.
WEB_RUNNER = "/opt/verify_web_run.sh"
WEB_MARKER = "GAGOS-VITEST-JSON"
#: The command is parsed by the executor (no ``;&|<>`` or backticks, split on
#: spaces): a path outside this alphabet is not run, never quoted.
_SAFE_REL = re.compile(r"[A-Za-z0-9_@+][A-Za-z0-9_./@+-]*")

#: Why a frontend change's tests do not run before review. No longer returned
#: here: kept for callers that still name it.
NO_FRONTEND_SANDBOX = (
    "the sandbox has no frontend toolchain yet; the tests that import it run at "
    "delivery, on the operator's checkout"
)


#: The runner script Dockerfile.verify-web bakes into the image.
WEB_RUNNER_SOURCE = "tools/verify_web_run.sh"
#: The line the runner prints before ``tsc``'s output (its typecheck mode).
TSC_MARKER = "GAGOS-TSC"
#: Frontend sources TypeScript checks (``allowJs``: JavaScript is compiled too).
TYPED_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
_TSC_ERROR = re.compile(
    r"^(?P<file>[^\s(][^(]*)\(\d+,\d+\): error (?P<code>TS\d+): (?P<msg>.*)$"
)


def web_image(lock: bytes, runner: bytes = b"") -> str:
    """The frontend sandbox image for this ``package-lock.json`` and runner
    script. The runner is baked into the image, so a new runner is a new image
    (2026-11-11, the type check); with no runner the name is the lock's alone,
    as it was."""
    return f"aios-verify-web:{hashlib.sha256(lock + runner).hexdigest()[:12]}"


def web_build_hint(lock: bytes, runner: bytes = b"") -> str:
    sha = hashlib.sha256(lock).hexdigest()
    return (
        f"docker build -f Dockerfile.verify-web --label package-lock.sha256={sha} "
        f"-t {web_image(lock, runner)} ."
    )


@dataclass(frozen=True)
class VitestRun:
    """One vitest run in the sandbox."""

    timed_out: bool
    exit_code: int
    passed: int
    failing: tuple[str, ...]
    files: tuple[str, ...]
    seconds: float


def parse_vitest(output: str) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """(tests passed, failing test ids, test files that ran) from the runner's
    output: its marker line, then vitest's JSON report. Raises ValueError when
    there is no report. Ids are ``file::test name``, the file relative to
    ``frontend/``; a file that failed to load, with no test of its own, is
    named alone."""
    _, marker, rest = output.partition(WEB_MARKER)
    if not marker or not rest.strip():
        raise ValueError("no vitest report in the output")
    try:
        report = json.loads(rest.strip())
        results = report["testResults"]
        passed = int(report.get("numPassedTests", 0))
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"the vitest report is unreadable: {exc}") from exc
    failing: list[str] = []
    files: list[str] = []
    for result in results:
        name = str(result.get("name", "")).replace("\\", "/")
        file = name.split("/web/", 1)[-1]
        files.append(file)
        failed = [
            a for a in result.get("assertionResults", []) if a.get("status") == "failed"
        ]
        failing += [f"{file}::{a.get('fullName') or a.get('title')}" for a in failed]
        if result.get("status") == "failed" and not failed:
            failing.append(file)
    return passed, tuple(dict.fromkeys(failing)), tuple(dict.fromkeys(files))


def _vitest(
    runner: Runner, tree: Path, mode: str, files: Sequence[str], timeout_s: int
) -> VitestRun:
    """*files* are relative to ``frontend/``; *mode* is vitest's ``related``
    (the tests that import them) or ``run`` (these test files)."""
    command = " ".join(
        ["timeout", "-s", "KILL", str(timeout_s), WEB_RUNNER, mode, *files]
    )
    started = time.monotonic()
    try:
        out, err, code = runner(
            command, cwd=str(tree), env=client_env(), timeout_s=timeout_s + 120
        )
    except subprocess.TimeoutExpired:
        return VitestRun(True, _KILLED, 0, (), (), time.monotonic() - started)
    except (RuntimeError, ValueError, OSError) as exc:
        raise SandboxUnavailable(str(exc)) from exc
    seconds = time.monotonic() - started
    if code == _KILLED:
        if seconds < timeout_s - 5:
            raise SandboxUnavailable(
                f"the frontend tests were killed after {seconds:.0f}s, before the "
                f"{timeout_s}s limit (the container's {MEMORY_MB} MiB, most likely)"
            )
        return VitestRun(True, code, 0, (), (), seconds)
    try:
        passed, failing, ran = parse_vitest(out)
    except ValueError as exc:
        tail = (err or out).strip().splitlines()[-1:] or [f"exit {code}"]
        raise SandboxUnavailable(
            f"vitest could not run (exit {code}): {exc}; {tail[0][:200]}"
        ) from exc
    if code not in (0, 1):
        raise SandboxUnavailable(f"vitest could not run (exit {code})")
    if code == 1 and not failing:
        failing = (f"(vitest exit {code})",)
    return VitestRun(False, code, passed, failing, ran, seconds)


@dataclass(frozen=True)
class TscRun:
    """One ``tsc --noEmit`` over the frontend in the sandbox. *errors* counts
    each error by file, code and message (lines shift with any edit, so they
    are not part of an error's identity); *note* says why it could not run."""

    errors: Counter
    seconds: float
    note: str = ""


def parse_tsc(output: str) -> Counter:
    """The errors ``tsc --pretty false`` printed after the runner's marker."""
    _, marker, rest = output.partition(TSC_MARKER)
    if not marker:
        raise ValueError("no tsc output in the sandbox's answer")
    found: Counter = Counter()
    for line in rest.splitlines():
        hit = _TSC_ERROR.match(line.strip())
        if hit:
            found[(hit["file"], hit["code"], hit["msg"].strip())] += 1
    return found


def _typecheck(runner: Runner, tree: Path, timeout_s: int) -> TscRun:
    started = time.monotonic()
    try:
        out, err, code = runner(
            f"timeout -s KILL {timeout_s} {WEB_RUNNER} typecheck",
            cwd=str(tree),
            env=client_env(),
            timeout_s=timeout_s + 30,
        )
    except Exception as exc:  # the container could not be run: said, not hidden
        return TscRun(
            Counter(), time.monotonic() - started, f"tsc could not run: {exc}"
        )
    seconds = time.monotonic() - started
    if code == _KILLED:
        return TscRun(Counter(), seconds, f"tsc did not finish within {timeout_s}s")
    try:
        errors = parse_tsc(out)
    except ValueError as exc:
        return TscRun(Counter(), seconds, f"tsc could not run (exit {code}): {exc}")
    if code != 0 and not errors:
        return TscRun(
            Counter(), seconds, f"tsc exited {code} without reading as errors"
        )
    return TscRun(errors, seconds)


def _type_gate(
    verdict: SandboxVerdict, with_it: TscRun | None, without: TscRun | None
) -> SandboxVerdict:
    """The type check's word on a frontend change (2026-11-11): a change that
    adds TypeScript errors the base does not have is BROKE, whatever its tests
    did. A clean check changes no verdict -- it is not a test, and never turns
    an untested change into a tested one. A check that could not run is said
    and judged by CI."""
    if with_it is None:
        return verdict
    if with_it.note:
        return replace(
            verdict, summary=f"{verdict.summary}; types: not checked, {with_it.note}"
        )
    if not with_it.errors:
        return replace(
            verdict, summary=f"{verdict.summary}; types: tsc --noEmit is clean"
        )
    base = without.errors if without is not None and not without.note else None
    if base is None:
        return replace(
            verdict,
            summary=f"{verdict.summary}; types: {sum(with_it.errors.values())} error(s), "
            "and the base could not be checked to compare",
        )
    new = with_it.errors - base
    if not new:
        return replace(
            verdict,
            summary=f"{verdict.summary}; types: no new type errors "
            f"({sum(base.values())} exist without it too)",
        )
    shown = "; ".join(f"{f} {c}: {m}"[:160] for (f, c, m) in list(new)[:3])
    return SandboxVerdict(
        BROKE,
        f"it adds {sum(new.values())} TypeScript error(s) the base does not have: "
        f"{shown}; then: {verdict.summary}",
        verdict.tests,
        verdict.broken + tuple(f"tsc {f} {c}" for (f, c, _) in new),
        verdict.failing_anyway,
        verdict.seconds,
    )


def _ordered_tests(tree: Path, rel: str) -> list[str]:
    """Every test file that exercises *rel* (or is it), those named for it first."""
    tree = tree.resolve()
    found = [
        p.relative_to(tree).as_posix()
        for p in find_exercising_tests(tree, [tree / rel])
        if p.is_file()
    ]
    own = PurePosixPath(rel)
    if own.name.startswith("test_") and "tests" in own.parts:
        found = [rel, *(t for t in found if t != rel)]
    stem = own.stem.removeprefix("test_")
    named = [t for t in found if stem and stem in PurePosixPath(t).stem]
    return list(dict.fromkeys([*named, *found]))


def select_tests(tree: Path, rel: str) -> tuple[list[str], int]:
    """The test files to run for *rel* (posix, relative to *tree*), and how
    many exercise it in all."""
    ordered = _ordered_tests(tree, rel)
    return ordered[:MAX_TEST_FILES], len(ordered)


def select_tests_for(tree: Path, rels: Sequence[str]) -> tuple[list[str], int]:
    """:func:`select_tests` over several files, one run: the files take turns,
    so that when more tests exercise them than :data:`MAX_TEST_FILES` allows,
    every changed file keeps the tests named for it."""
    lists = [_ordered_tests(tree, rel) for rel in rels]
    merged: list[str] = []
    for rank in range(max((len(x) for x in lists), default=0)):
        merged += [x[rank] for x in lists if rank < len(x)]
    merged = list(dict.fromkeys(merged))
    return merged[:MAX_TEST_FILES], len(merged)


class _Applied:
    """A set of changes written into the base copy, and taken out again.

    ``revert`` restores every file to exactly the bytes the base had (or
    removes it, when the change created it); it is safe to call twice."""

    def __init__(self, tree: Path, changes: dict[str, str]) -> None:
        root = tree.resolve()
        self.originals: dict[Path, bytes | None] = {}
        self.texts: dict[Path, str] = {}
        for rel, text in changes.items():
            path = (tree / rel).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"{rel} is not inside the project")
            self.originals[path] = path.read_bytes() if path.is_file() else None
            self.texts[path] = text

    def apply(self) -> None:
        for path, text in self.texts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))

    def revert(self) -> None:
        for path, original in self.originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)


def _compare(
    with_it: PytestRun | VitestRun,
    without: PytestRun | VitestRun,
    tests: Sequence[str],
    of: str,
    timeout_s: int,
    seconds: float,
) -> SandboxVerdict:
    """The verdict from the two runs of one kind of test: with the change,
    and without it (the base). Only what passes without and fails with is the
    change's doing."""
    if with_it.timed_out:
        if without.timed_out:
            return SandboxVerdict(
                UNAVAILABLE,
                f"the tests do not finish within {timeout_s}s, with or without it",
                tuple(tests),
                seconds=seconds,
            )
        return SandboxVerdict(
            BROKE,
            f"the tests run past {timeout_s}s with it and finish in "
            f"{without.seconds:.0f}s without it",
            tuple(tests),
            broken=("(timeout)",),
            seconds=seconds,
        )
    if without.timed_out:
        return SandboxVerdict(
            UNAVAILABLE,
            f"the tests fail with it and do not finish within {timeout_s}s without "
            "it, so the two cannot be compared",
            tuple(tests),
            seconds=seconds,
        )
    broken = tuple(t for t in with_it.failing if t not in without.failing)
    anyway = tuple(t for t in with_it.failing if t in without.failing)
    if broken:
        return SandboxVerdict(
            BROKE,
            f"{len(broken)} test(s) pass without it and fail with it: {_names(broken)}",
            tuple(tests),
            broken,
            anyway,
            seconds,
            passed_count=with_it.passed,
            failed_count=len(with_it.failing),
        )
    return SandboxVerdict(
        PASSED,
        f"{with_it.passed} tests in {len(tests)} files pass{of}; "
        f"{len(anyway)} fail without it too, so not its doing: {_names(anyway)}",
        tuple(tests),
        (),
        anyway,
        seconds,
        passed_count=with_it.passed,
        failed_count=len(anyway),
    )


def _of(tests: Sequence[str], exercising: int) -> str:
    return (
        f" ({len(tests)} of {exercising} test files that exercise it)"
        if exercising > len(tests)
        else ""
    )


class _PythonPart:
    """The Python files of a change: one pytest run over the tests that
    exercise any of them, with the change and (if that fails) without it."""

    label = "Python tests"

    def __init__(self, tree, rels, runner_for, image_ready, timeout_s, image) -> None:
        self.tree, self.rels = tree, list(rels)
        self.runner_for, self.image_ready = runner_for, image_ready
        self.timeout_s, self.image = timeout_s, image
        self.tests: list[str] = []
        self.of = ""
        self.with_it: PytestRun | None = None
        self.runner: Runner | None = None

    def check(self) -> SandboxVerdict | None:
        requirements = (self.tree / "requirements.txt").read_bytes()
        image = self.image or verify_image(requirements)
        if not self.image_ready(image):
            return SandboxVerdict(
                UNAVAILABLE,
                f"the sandbox image {image} is not built (or Docker is not "
                f"running); build it with: {build_hint(requirements)}",
            )
        self.runner = self.runner_for(image)
        return None

    def run_with(self) -> SandboxVerdict | None:
        try:
            self.tests, exercising = select_tests_for(self.tree, self.rels)
        except (OSError, SyntaxError, ValueError) as exc:
            return SandboxVerdict(UNAVAILABLE, f"its tests could not be found: {exc}")
        if not self.tests:
            what = "this file" if len(self.rels) == 1 else "these files"
            return SandboxVerdict(UNTESTED, f"no test in the project exercises {what}")
        self.of = _of(self.tests, exercising)
        tests = tuple(self.tests)
        try:
            run = _pytest(self.runner, self.tree, self.tests, self.timeout_s)
        except SandboxUnavailable as exc:
            return SandboxVerdict(UNAVAILABLE, str(exc), tests)
        self.with_it = run
        if not run.timed_out and run.exit_code == 0:
            return SandboxVerdict(
                PASSED,
                f"{run.passed} tests in {len(tests)} files pass{self.of}",
                tests,
                seconds=run.seconds,
                passed_count=run.passed,
            )
        if not run.timed_out and run.exit_code == 5:
            return SandboxVerdict(
                UNTESTED,
                "the test files that exercise this file collect no test"
                if len(self.rels) == 1
                else "the test files that exercise these files collect no test",
                tests,
                seconds=run.seconds,
            )
        return None

    def run_base(self) -> SandboxVerdict:
        """With the change taken out of the tree again."""
        tests = tuple(self.tests)
        base_tests = [t for t in self.tests if (self.tree / t).is_file()]
        try:
            without = (
                _pytest(self.runner, self.tree, base_tests, self.timeout_s)
                if base_tests
                else PytestRun(False, 0, 0, (), 0.0)
            )
        except SandboxUnavailable as exc:
            return SandboxVerdict(UNAVAILABLE, str(exc), tests)
        return _compare(
            self.with_it, without, tests, self.of, self.timeout_s, self.with_it.seconds
        )


class _WebPart:
    """The frontend files of a change: one vitest run over the tests that
    import any of them (``vitest related``), with the change; if that fails,
    the same test files again without it."""

    label = "frontend tests"

    def __init__(self, tree, rels, runner_for, image_ready, timeout_s) -> None:
        self.tree = tree
        self.rels = [r.removeprefix(FRONTEND_DIR + "/") for r in rels]
        self.runner_for, self.image_ready = runner_for, image_ready
        self.timeout_s = timeout_s
        self.with_it: VitestRun | None = None
        self.runner: Runner | None = None

    def check(self) -> SandboxVerdict | None:
        lock = self.tree / "frontend" / "package-lock.json"
        if not lock.is_file():
            return SandboxVerdict(
                UNAVAILABLE, "the base commit has no frontend/package-lock.json"
            )
        locked = [r for r in _WEB_LOCKED if r.removeprefix("frontend/") in self.rels]
        if locked:
            return SandboxVerdict(
                UNAVAILABLE,
                f"the change edits {locked[0]}, which the frontend sandbox image "
                "was built from; its tests run at delivery, on the operator's "
                "checkout",
            )
        unsafe = [r for r in self.rels if not _SAFE_REL.fullmatch(r)]
        if unsafe:
            return SandboxVerdict(
                UNAVAILABLE,
                f"the path {unsafe[0][:60]!r} cannot be passed to the sandbox",
            )
        data = lock.read_bytes()
        script = self.tree / WEB_RUNNER_SOURCE
        runner = script.read_bytes() if script.is_file() else b""
        image = web_image(data, runner)
        if not self.image_ready(image):
            return SandboxVerdict(
                UNAVAILABLE,
                f"the frontend sandbox image {image} is not built (or Docker is "
                f"not running); build it with: {web_build_hint(data, runner)}",
            )
        self.runner = self.runner_for(image)
        return None

    def run_with(self) -> SandboxVerdict | None:
        try:
            run = _vitest(self.runner, self.tree, "related", self.rels, self.timeout_s)
        except SandboxUnavailable as exc:
            return SandboxVerdict(UNAVAILABLE, str(exc))
        self.with_it = run
        tests = run.files
        if not run.timed_out and not run.files:
            return SandboxVerdict(
                UNTESTED,
                "no test in the frontend imports "
                + ("this file" if len(self.rels) == 1 else "these files"),
                seconds=run.seconds,
            )
        if not run.timed_out and run.exit_code == 0:
            return SandboxVerdict(
                PASSED,
                f"{run.passed} tests in {len(tests)} files pass",
                tests,
                seconds=run.seconds,
                passed_count=run.passed,
            )
        return None

    def run_base(self) -> SandboxVerdict:
        """With the change taken out of the tree again: the same test files
        (or, when the run never finished and they are unknown, the files'
        related tests)."""
        run = self.with_it
        if run.files:
            mode, subjects = "run", list(run.files)
        else:
            mode, subjects = "related", list(self.rels)
        present = [s for s in subjects if (self.tree / FRONTEND_DIR / s).is_file()]
        try:
            without = (
                _vitest(self.runner, self.tree, mode, present, self.timeout_s)
                if present
                else VitestRun(False, 0, 0, (), (), 0.0)
            )
        except SandboxUnavailable as exc:
            return SandboxVerdict(UNAVAILABLE, str(exc), run.files)
        return _compare(run, without, run.files, "", self.timeout_s, run.seconds)


_RANK = {BROKE: 0, UNAVAILABLE: 1, PASSED: 2, UNTESTED: 3}


def _combine(
    results: Sequence[tuple[str, SandboxVerdict]], others: int, seconds: float
) -> SandboxVerdict:
    """One verdict from each part's. BROKE if either part broke. Otherwise
    UNAVAILABLE if a part could not run (a pass in the other part is not a
    pass for the change). PASSED only if every part passed or had nothing to
    test; UNTESTED if none had anything."""
    if len(results) == 1 and not others:
        return replace(results[0][1], seconds=seconds)
    outcome = min((v.outcome for _, v in results), key=_RANK.__getitem__)
    summary = "; ".join(f"{label}: {v.summary}" for label, v in results)
    if others:
        summary += f"; {others} changed file(s) of other kinds have no test"
    return SandboxVerdict(
        outcome,
        summary,
        tuple(t for _, v in results for t in v.tests),
        tuple(t for _, v in results for t in v.broken),
        tuple(t for _, v in results for t in v.failing_anyway),
        seconds,
        passed_count=sum(v.passed_count for _, v in results),
        failed_count=sum(v.failed_count for _, v in results),
    )


def _is_frontend(rel: str) -> bool:
    return (
        rel.startswith(FRONTEND_DIR + "/")
        and "node_modules" not in rel.split("/")
        and rel.endswith(FRONTEND_SUFFIXES)
    )


def run_change_tests(
    trees: BaseTrees,
    *,
    base_commit: str,
    changes: dict[str, str],
    runner_for: Callable[[str], Runner] = default_runner,
    image_ready: Callable[[str], bool] = image_built,
    timeout_s: int = TEST_TIMEOUT_S,
) -> SandboxVerdict:
    """The one entry point (2026-11-03): the tests of a set of changes
    (``{rel: new_text}``, one file or a task's several), all in place in the
    base copy at once, judged against the base with all of them removed, and
    every file restored afterwards.

    Python files run in ``aios-verify`` (one pytest run over the tests that
    exercise any of them, at most :data:`MAX_TEST_FILES`); files under
    ``frontend/`` run in ``aios-verify-web`` (one vitest run, ``related``). A
    set with both runs both and combines the verdicts (:func:`_combine`)."""
    if not changes:
        return SandboxVerdict(UNTESTED, "no change to test")
    if len(changes) == 1:
        [(rel, new_text)] = changes.items()
        if rel.endswith(".py"):
            return run_proposal_tests(
                trees,
                base_commit=base_commit,
                rel=rel,
                new_text=new_text,
                runner_for=runner_for,
                image_ready=image_ready,
                timeout_s=timeout_s,
            )
    return _run_set(
        trees,
        base_commit=base_commit,
        changes=changes,
        runner_for=runner_for,
        image_ready=image_ready,
        timeout_s=timeout_s,
    )


def run_proposal_tests(
    trees: BaseTrees,
    *,
    base_commit: str,
    rel: str,
    new_text: str,
    runner_for: Callable[[str], Runner] = default_runner,
    image_ready: Callable[[str], bool] = image_built,
    timeout_s: int = TEST_TIMEOUT_S,
    image: str | None = None,
) -> SandboxVerdict:
    """Run *rel*'s tests with *new_text* in place, judged against the base.
    *image*: another sandbox image than the base's ``aios-verify`` (tests)."""
    return _run_set(
        trees,
        base_commit=base_commit,
        changes={rel: new_text},
        runner_for=runner_for,
        image_ready=image_ready,
        timeout_s=timeout_s,
        python_image=image,
    )


def _run_set(
    trees: BaseTrees,
    *,
    base_commit: str,
    changes: dict[str, str],
    runner_for: Callable[[str], Runner],
    image_ready: Callable[[str], bool],
    timeout_s: int,
    python_image: str | None = None,
) -> SandboxVerdict:
    started = time.monotonic()

    def took() -> float:
        return time.monotonic() - started

    try:
        tree = trees.get(base_commit)
    except SandboxUnavailable as exc:
        return SandboxVerdict(UNAVAILABLE, str(exc))
    py = [r for r in changes if r.endswith(".py")]
    web = [r for r in changes if _is_frontend(r)]
    others = len(changes) - len(py) - len(web)
    parts: list = []
    if py:
        parts.append(
            _PythonPart(tree, py, runner_for, image_ready, timeout_s, python_image)
        )
    if web:
        parts.append(_WebPart(tree, web, runner_for, image_ready, timeout_s))
    if not parts:
        return SandboxVerdict(
            UNTESTED, "no test covers a file of this kind (Python or frontend only)"
        )
    try:
        applied = _Applied(tree, changes)
    except ValueError as exc:
        return SandboxVerdict(UNAVAILABLE, str(exc))
    done: dict[str, SandboxVerdict] = {}
    for part in parts:
        early = part.check()
        if early is not None:
            done[part.label] = early
    # The frontend's sources are type-checked too, in the same image, when the
    # set changes any (2026-11-11).
    web_part = next((p for p in parts if isinstance(p, _WebPart)), None)
    typed = web_part is not None and any(r.endswith(TYPED_SUFFIXES) for r in web)
    types_with: TscRun | None = None
    types_without: TscRun | None = None
    try:
        applied.apply()
        for part in parts:
            if part.label not in done:
                verdict = part.run_with()
                if verdict is not None:
                    done[part.label] = verdict
        if typed and web_part.runner is not None:
            types_with = _typecheck(web_part.runner, tree, timeout_s)
        pending = [p for p in parts if p.label not in done]
        recheck = types_with is not None and bool(types_with.errors)
        if pending or recheck:
            # Judged against the base: the same tests, without the change.
            applied.revert()
            for part in pending:
                done[part.label] = part.run_base()
            if recheck:
                types_without = _typecheck(web_part.runner, tree, timeout_s)
    finally:
        applied.revert()
    combined = _combine([(p.label, done[p.label]) for p in parts], others, took())
    return _type_gate(combined, types_with, types_without)


#: The runners the sandbox's images start, as their own command lines
#: (``tools/verify_web_run.sh`` runs vitest so; the Python image runs pytest
#: so). Organ 15 grades a verification by its real runner
#: (:mod:`aios.core.verification_strength`), so a mission's sandbox check is
#: recorded under the runner that actually ran, never a wrapper's name.
WEB_TEST_COMMAND = "node node_modules/vitest/vitest.mjs related"
PY_TEST_COMMAND = "python -m pytest -q"
#: Exit codes a ledger entry carries for a sandbox that asserted nothing.
UNTESTED_EXIT = 5
UNAVAILABLE_EXIT = 125


def ledger_entry(verdict: SandboxVerdict, *, rels: Sequence[str]) -> dict:
    """A sandbox verdict as one verification command of a worker's run ledger
    (2026-11-12): what the council's Testing queen reads, and what promotion
    records with organ 15. Nothing in it is better than the run was:

    * ``command`` is the runner's own command line in the sandbox, over the
      changed files (vitest's ``related`` takes paths under ``frontend/``; the
      Python run, the test files it chose). A change spanning both kinds gets
      a ``sandbox:`` command no runner rule recognises, so it can never be
      graded above WEAK: its counts cannot be told apart by runner;
    * ``returncode`` is 0 only for a PASSED verdict; an untested change (no
      test exercises it) and an unavailable sandbox are not passes;
    * ``stdout`` states the counts in the runner's words ("N passed",
      "M failed") and the verdict's summary. Tests that fail without the
      change too are failures here: a STRONG grade needs none at all.
    """
    frontend = [r for r in rels if _is_frontend(r)]
    others = [r for r in rels if r not in frontend]
    if frontend and not others:
        prefix = FRONTEND_DIR + "/"
        command = " ".join(
            [WEB_TEST_COMMAND, *(r[len(prefix) :] for r in frontend), "--run"]
        )
    elif others and not frontend:
        command = " ".join([PY_TEST_COMMAND, *(verdict.tests or others)])
    else:
        command = "sandbox: " + " ".join(rels)
    returncode = {
        PASSED: 0,
        BROKE: 1,
        UNTESTED: UNTESTED_EXIT,
    }.get(verdict.outcome, UNAVAILABLE_EXIT)
    lines = [
        f"{verdict.passed_count} passed",
        f"{verdict.failed_count} failed",
        f"sandbox {verdict.outcome}: {verdict.summary}",
    ]
    return {
        "command": command,
        "returncode": returncode,
        "stdout": "\n".join(lines),
        "stderr": "",
        "tool_version": "gagos-sandbox",
    }


__all__ = [
    "BROKE",
    "BROKE_PREFIX",
    "BaseTrees",
    "MAX_TEST_FILES",
    "PASSED",
    "SandboxUnavailable",
    "SandboxVerdict",
    "TEST_TIMEOUT_S",
    "PytestRun",
    "UNAVAILABLE",
    "UNTESTED",
    "VitestRun",
    "PY_TEST_COMMAND",
    "WEB_RUNNER",
    "WEB_TEST_COMMAND",
    "build_hint",
    "client_env",
    "default_runner",
    "image_built",
    "ledger_entry",
    "parse_pytest",
    "parse_vitest",
    "run_change_tests",
    "run_proposal_tests",
    "select_tests",
    "select_tests_for",
    "verify_image",
    "web_build_hint",
    "web_image",
]
