"""A proposal's tests, run before review, in the executor's sandbox.

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
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol, Sequence

from aios.application.promotion.smoke import find_exercising_tests
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
        tree = Path(tempfile.mkdtemp(prefix="gagos-sbx-"))
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


def select_tests(tree: Path, rel: str) -> tuple[list[str], int]:
    """The test files to run for *rel* (posix, relative to *tree*), and how
    many exercise it in all."""
    path = tree / rel
    found = [
        p.relative_to(tree).as_posix()
        for p in find_exercising_tests(tree, [path])
        if p.is_file()
    ]
    own = PurePosixPath(rel)
    if own.name.startswith("test_") and "tests" in own.parts:
        found = [rel, *(t for t in found if t != rel)]
    stem = own.stem.removeprefix("test_")
    named = [t for t in found if stem and stem in PurePosixPath(t).stem]
    ordered = list(dict.fromkeys([*named, *found]))
    return ordered[:MAX_TEST_FILES], len(ordered)


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
    started = time.monotonic()
    try:
        tree = trees.get(base_commit)
    except SandboxUnavailable as exc:
        return SandboxVerdict(UNAVAILABLE, str(exc))
    requirements = (tree / "requirements.txt").read_bytes()
    image = image or verify_image(requirements)
    if not image_ready(image):
        return SandboxVerdict(
            UNAVAILABLE,
            f"the sandbox image {image} is not built (or Docker is not running); "
            f"build it with: {build_hint(requirements)}",
        )
    path = (tree / rel).resolve()
    if not path.is_relative_to(tree.resolve()):
        return SandboxVerdict(UNAVAILABLE, f"{rel} is not inside the project")
    original = path.read_bytes() if path.is_file() else None
    try:
        tests, exercising = select_tests(tree, rel)
    except (OSError, SyntaxError, ValueError) as exc:
        return SandboxVerdict(UNAVAILABLE, f"its tests could not be found: {exc}")
    if not tests:
        return SandboxVerdict(UNTESTED, "no test in the project exercises this file")
    of = (
        f" ({len(tests)} of {exercising} test files that exercise it)"
        if (exercising > len(tests))
        else ""
    )
    runner = runner_for(image)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_text.encode("utf-8"))
        with_it = _pytest(runner, tree, tests, timeout_s)
        if not with_it.timed_out and with_it.exit_code == 0:
            return SandboxVerdict(
                PASSED,
                f"{with_it.passed} tests in {len(tests)} files pass{of}",
                tuple(tests),
                seconds=time.monotonic() - started,
            )
        if not with_it.timed_out and with_it.exit_code == 5:
            return SandboxVerdict(
                UNTESTED,
                "the test files that exercise this file collect no test",
                tuple(tests),
                seconds=time.monotonic() - started,
            )
        # Judged against the base: the same tests, without the proposal.
        if original is None:
            path.unlink()
        else:
            path.write_bytes(original)
        base_tests = [t for t in tests if (tree / t).is_file()]
        without = (
            _pytest(runner, tree, base_tests, timeout_s)
            if base_tests
            else PytestRun(False, 0, 0, (), 0.0)
        )
    except SandboxUnavailable as exc:
        return SandboxVerdict(UNAVAILABLE, str(exc), tuple(tests))
    finally:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(original)
    seconds = time.monotonic() - started
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
        )
    return SandboxVerdict(
        PASSED,
        f"{with_it.passed} tests in {len(tests)} files pass{of}; "
        f"{len(anyway)} fail without it too, so not its doing: {_names(anyway)}",
        tuple(tests),
        (),
        anyway,
        seconds,
    )


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
    "build_hint",
    "client_env",
    "default_runner",
    "image_built",
    "parse_pytest",
    "run_proposal_tests",
    "select_tests",
    "verify_image",
]
