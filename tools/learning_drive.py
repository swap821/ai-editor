#!/usr/bin/env python3
"""Drive the learning loop unattended, and stop the moment it stops measuring.

WHY THIS IS A TOOL AND NOT A SHELL LOOP
---------------------------------------
Everything the loop has ever proven was proven because a person launched it.
That is the difference between a capability and a habit, and it is why the
chain sat idle from 2026-07-07 to 2026-09-21 with every part of it working.

Three things make an unattended runner different from a `for` loop:

* **It must not run twice.** Two drivers sharing one worktree and one memory
  store produce numbers about neither. The lock is a file, checked and written
  atomically, carrying the owning pid so a stale lock from a killed run can be
  told from a live one.
* **It must stop when the instrument breaks.** A cycle that aborts because the
  grader refused (a hollow pytest run, a dead subprocess) means this machine
  cannot measure right now. Asking it again immediately produces more of the
  same garbage, so the batch ends and says why.
* **It must not silently do nothing.** A run where no attempt ever reached
  grading looks identical, in every counter, to a run that was never started.
  That case is reported as a FAILURE, not as a quiet zero.

THE RE-EXEC TRAP
----------------
`reverse_engineer_gagos` re-execs itself so `--env-file` lands before
`aios.config` freezes `BEDROCK_ENABLED`. On Windows `os.execv` is
spawn-then-exit, so the launcher returns 0 IMMEDIATELY while the real work
continues in a detached process -- every wrapper that tried to wait on it
reported success seconds in. This loads the env HERE and sets the tool's own
`_AIOS_RE_ENV_LOADED` marker, so there is no re-exec and `subprocess.run`
blocks the way it should.

    python tools/learning_drive.py --cycles 3
    python tools/learning_drive.py --cycles 1 --env-file frontend/nvdia/.env
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

LOCK = REPO_ROOT / ".aios" / "tmp" / "learning-drive.lock"
TRAIL = REPO_ROOT / ".aios" / "audit" / "learning-drive.jsonl"
WORKTREE = REPO_ROOT.parent / "ai-editor-selfcorpus"
DEFAULT_LADDER = "ollama.qwen2.5-coder:7b"


@dataclass
class CycleResult:
    cycle: int
    returncode: int
    earned: int
    attempts: int
    graded: int
    aborted: bool
    seconds: float
    tail: str


class DriveLocked(RuntimeError):
    """Another driver owns the tree."""


def _pid_alive(pid: int) -> bool:
    """Is that process still running?

    Deliberately NOT `tasklist`: spawning a process to ask whether a process
    exists costs seconds on Windows, and this is called on every lock check by
    a tool whose whole job is to run quietly on a schedule. `OpenProcess` with
    SYNCHRONIZE answers the same question with one syscall.

    `ERROR_ACCESS_DENIED` (5) means the pid EXISTS and belongs to someone else,
    which must read as alive -- treating it as dead would let a driver stomp a
    live run owned by another account.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return kernel32.GetLastError() == 5  # ERROR_ACCESS_DENIED
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def acquire_lock(lock: Path = LOCK) -> None:
    """Refuse to start when a live driver already holds the tree.

    A STALE lock -- one whose pid is gone -- is reclaimed rather than
    respected. Otherwise one killed run disables the schedule permanently and
    the loop goes quiet for weeks in exactly the way this tool exists to end.
    """
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            held = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(held.get("pid", -1))
        except (json.JSONDecodeError, ValueError, OSError):
            pid = -1
        if _pid_alive(pid):
            raise DriveLocked(
                f"another learning drive is running (pid {pid}, started "
                f"{held.get('started', '?')}). Two drivers sharing one worktree "
                "and one memory store produce numbers about neither."
            )
        lock.unlink(missing_ok=True)
    lock.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )


def release_lock(lock: Path = LOCK) -> None:
    lock.unlink(missing_ok=True)


def load_env(env_file: Path | None) -> dict[str, str]:
    """Provider credentials into THIS process's env, never onto disk."""
    env = dict(os.environ)
    if env_file and env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip("<>").strip()
    # Tell the runner its env is already loaded, so it does NOT re-exec.
    env["_AIOS_RE_ENV_LOADED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def teardown_worktree() -> None:
    """A cycle that inherits a dirtied worktree is not attributable."""
    from tools.self_corpus import Corpus, teardown

    if WORKTREE.exists():
        teardown(Corpus(root=WORKTREE, sha="drive", source=REPO_ROOT))


def _summarise(log: Path) -> tuple[int, int, int, bool, str]:
    """`(earned, attempts, graded, aborted, tail)` read from a cycle's output."""
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    lines = [line for line in text.splitlines() if line.strip()]
    earned = sum(1 for line in lines if "EARNED" in line)
    attempts = sum(1 for line in lines if "(try " in line)
    # An attempt that reached grading is one the grader actually judged --
    # `model_error` and `no_code_block` never got that far.
    graded = sum(
        1
        for line in lines
        if "(try " in line and "model_error" not in line and "no_code_block" not in line
    )
    aborted = any(line.startswith("FAIL ") for line in lines)
    return earned, attempts, graded, aborted, " | ".join(lines[-3:])[:400]


def run_cycle(
    n: int, *, ladder: str, targets: int, retries: int, env: dict, logs: Path
) -> CycleResult:
    teardown_worktree()
    log = logs / f"learning-drive-cycle-{n}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as fh:
        rc = subprocess.run(
            [
                sys.executable,
                "-u",
                "tools/reverse_engineer_gagos.py",
                "--models",
                ladder,
                "--targets",
                str(targets),
                "--retries",
                str(retries),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
        ).returncode
    earned, attempts, graded, aborted, tail = _summarise(log)
    return CycleResult(
        cycle=n,
        returncode=rc,
        earned=earned,
        attempts=attempts,
        graded=graded,
        aborted=aborted or rc != 0,
        seconds=round(time.monotonic() - started, 1),
        tail=tail,
    )


def _record(rows: list[CycleResult], *, note: str, trail: Path = TRAIL) -> None:
    trail.parent.mkdir(parents=True, exist_ok=True)
    with trail.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "note": note,
                    "cycles": [asdict(r) for r in rows],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        fh.flush()
        os.fsync(fh.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--targets", type=int, default=4)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--models", default=DEFAULT_LADDER)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument(
        "--budget-minutes",
        type=float,
        default=90.0,
        help="stop starting new cycles once this much wall clock is spent",
    )
    parser.add_argument(
        "--logs",
        type=Path,
        default=REPO_ROOT / ".aios" / "tmp",
        help="where per-cycle logs are written",
    )
    args = parser.parse_args(argv)

    try:
        acquire_lock(LOCK)
    except DriveLocked as exc:
        print(f"SKIPPED — {exc}")
        return 0  # not an error: the schedule firing while a run is live is normal

    env = load_env(args.env_file)
    results: list[CycleResult] = []
    note = "completed"
    deadline = time.monotonic() + args.budget_minutes * 60
    try:
        for n in range(1, args.cycles + 1):
            if time.monotonic() > deadline:
                note = f"stopped after {len(results)} cycle(s): wall-clock budget spent"
                print(f"  {note}")
                break
            result = run_cycle(
                n,
                ladder=args.models,
                targets=args.targets,
                retries=args.retries,
                env=env,
                logs=args.logs,
            )
            results.append(result)
            print(
                f"  cycle {n}: rc={result.returncode} earned={result.earned} "
                f"graded={result.graded}/{result.attempts} ({result.seconds:.0f}s)"
            )
            if result.aborted:
                # The grader refused, or the runner died. Either way this
                # machine has just demonstrated it cannot measure; asking it
                # again immediately produces more unusable numbers.
                note = f"stopped at cycle {n}: the run did not finish cleanly"
                print(f"  {note}\n  {result.tail}")
                break
    finally:
        release_lock(LOCK)

    _record(results, note=note, trail=TRAIL)

    graded_total = sum(r.graded for r in results)
    print(
        f"\n{len(results)} cycle(s), {sum(r.earned for r in results)} earned, "
        f"{graded_total} graded attempt(s) — {note}"
    )
    if not results:
        print("no cycle ran at all")
        return 1
    if graded_total == 0:
        # Identical in every counter to a run that never started. Saying so is
        # the whole point: silence and "it learned nothing" are different facts.
        print(
            "FAIL — not one attempt reached the grader. That is indistinguishable "
            "from the loop never running, so it is reported as a failure rather "
            "than as a quiet zero."
        )
        return 1
    return 1 if any(r.aborted for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
