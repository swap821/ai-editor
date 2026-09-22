"""An unattended driver has to be safe in ways a manual one never needed.

Three properties, each learned from something that actually went wrong:

* **One driver at a time.** Two runs sharing one worktree and one memory store
  produce numbers about neither, and on 2026-09-21 a concurrent writer already
  invalidated one training run mid-flight.
* **A stale lock must not become a permanent outage.** Killed runs happen; if
  their lock survived them, the schedule would go quiet for weeks in exactly
  the way this tool exists to end.
* **Silence is not success.** A batch where nothing ever reached the grader is
  identical, in every counter, to a batch that never ran. It is reported as a
  failure rather than as a quiet zero.
"""

from __future__ import annotations

import json
import os

import pytest

from tools import learning_drive as drive


@pytest.fixture()
def lock(tmp_path):
    return tmp_path / "drive.lock"


class TestOnlyOneDriverAtATime:
    def test_a_live_lock_is_respected(self, lock) -> None:
        drive.acquire_lock(lock)  # held by THIS process, which is alive
        with pytest.raises(drive.DriveLocked, match="another learning drive"):
            drive.acquire_lock(lock)

    def test_a_stale_lock_is_reclaimed(self, lock) -> None:
        """A lock whose owner is gone must not outlive it."""
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            json.dumps({"pid": 999_999_999, "started": "2026-01-01T00:00:00+00:00"}),
            encoding="utf-8",
        )
        drive.acquire_lock(lock)  # must not raise
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()

    def test_a_corrupt_lock_is_reclaimed_not_fatal(self, lock) -> None:
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("{not json", encoding="utf-8")
        drive.acquire_lock(lock)
        assert lock.exists()

    def test_releasing_is_idempotent(self, lock) -> None:
        drive.acquire_lock(lock)
        drive.release_lock(lock)
        drive.release_lock(lock)  # a crashed run may never have held it
        assert not lock.exists()

    def test_the_lock_records_who_holds_it(self, lock) -> None:
        drive.acquire_lock(lock)
        held = json.loads(lock.read_text(encoding="utf-8"))
        assert held["pid"] == os.getpid() and held["started"]


class TestReadingACycleHonestly:
    def _log(self, tmp_path, text: str):
        path = tmp_path / "cycle.log"
        path.write_text(text, encoding="utf-8")
        return path

    def test_transport_failures_do_not_count_as_graded(self, tmp_path) -> None:
        """`graded` is the number that says the run measured anything at all."""
        log = self._log(
            tmp_path,
            "    EARNED earned  m  (try 1, 20s)\n"
            "           model_error  m  (try 1, 300s)\n"
            "           no_code_block  m  (try 2, 5s)\n"
            "           rejected  m  (try 2, 30s)\n",
        )
        earned, attempts, graded, aborted, _ = drive._summarise(log)
        assert (earned, attempts, graded, aborted) == (1, 4, 2, False)

    def test_an_aborted_run_is_detected(self, tmp_path) -> None:
        log = self._log(tmp_path, "FAIL  the suite run produced no output at all\n")
        assert drive._summarise(log)[3] is True

    def test_a_missing_log_is_not_a_crash(self, tmp_path) -> None:
        earned, attempts, graded, aborted, _ = drive._summarise(tmp_path / "nope.log")
        assert (earned, attempts, graded) == (0, 0, 0)


class TestTheBatchStopsWhenTheInstrumentBreaks:
    def _drive(self, monkeypatch, tmp_path, results):
        seen = []

        def fake_cycle(n, **kwargs):
            seen.append(n)
            return results[n - 1]

        monkeypatch.setattr(drive, "run_cycle", fake_cycle)
        monkeypatch.setattr(drive, "LOCK", tmp_path / "l.lock")
        monkeypatch.setattr(drive, "TRAIL", tmp_path / "t.jsonl")
        monkeypatch.setattr(drive, "teardown_worktree", lambda: None)
        return seen

    def _result(self, n, *, aborted=False, graded=4, earned=2):
        return drive.CycleResult(
            cycle=n,
            returncode=1 if aborted else 0,
            earned=earned,
            attempts=graded,
            graded=graded,
            aborted=aborted,
            seconds=1.0,
            tail="",
        )

    def test_an_abort_ends_the_batch(self, monkeypatch, tmp_path) -> None:
        """A machine that just failed to measure should not be asked twice."""
        seen = self._drive(
            monkeypatch,
            tmp_path,
            [self._result(1, aborted=True), self._result(2), self._result(3)],
        )
        rc = drive.main(["--cycles", "3", "--logs", str(tmp_path)])
        assert seen == [1], "cycles 2 and 3 must not have run"
        assert rc == 1

    def test_a_clean_batch_runs_every_cycle(self, monkeypatch, tmp_path) -> None:
        seen = self._drive(monkeypatch, tmp_path, [self._result(n) for n in (1, 2, 3)])
        assert drive.main(["--cycles", "3", "--logs", str(tmp_path)]) == 0
        assert seen == [1, 2, 3]

    def test_zero_graded_attempts_is_a_failure_not_a_quiet_zero(
        self, monkeypatch, tmp_path
    ) -> None:
        """Indistinguishable from never running — so it must not exit 0."""
        self._drive(monkeypatch, tmp_path, [self._result(1, graded=0, earned=0)])
        assert drive.main(["--cycles", "1", "--logs", str(tmp_path)]) == 1

    def test_earning_nothing_is_still_a_success_if_it_was_measured(
        self, monkeypatch, tmp_path
    ) -> None:
        """'The models all failed' is a RESULT. Only 'nothing ran' is a fault."""
        self._drive(monkeypatch, tmp_path, [self._result(1, graded=4, earned=0)])
        assert drive.main(["--cycles", "1", "--logs", str(tmp_path)]) == 0

    def test_a_busy_tree_skips_rather_than_fails(self, monkeypatch, tmp_path) -> None:
        """The schedule firing while a run is live is normal, not an error."""
        lock = tmp_path / "l.lock"
        monkeypatch.setattr(drive, "LOCK", lock)
        drive.acquire_lock(lock)
        assert drive.main(["--cycles", "1", "--logs", str(tmp_path)]) == 0


class TestCredentialsNeverLand:
    def test_the_env_file_is_read_into_memory_only(self, tmp_path) -> None:
        secret = tmp_path / ".env"
        secret.write_text("AIOS_OPENAI_API_KEY=<nvapi-abc123>\n", encoding="utf-8")
        env = drive.load_env(secret)
        assert env["AIOS_OPENAI_API_KEY"] == "nvapi-abc123", (
            "placeholder angle brackets copied in with a key have 401'd this "
            "repo before while the endpoint looked healthy"
        )
        assert env["_AIOS_RE_ENV_LOADED"] == "1", (
            "without this the runner re-execs, and on Windows that detaches the "
            "work while the launcher returns 0 immediately"
        )

    def test_a_missing_env_file_is_not_fatal(self, tmp_path) -> None:
        env = drive.load_env(tmp_path / "absent.env")
        assert env["_AIOS_RE_ENV_LOADED"] == "1"
