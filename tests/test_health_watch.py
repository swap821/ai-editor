"""The health watch notices, fixes what is safe, and tells the operator once."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "_health_watch", REPO_ROOT / "tools" / "health_watch.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: dataclasses resolve their module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hw = _load()


class Ollama:
    """A scripted runtime: answers per call from `states`, then the last one."""

    def __init__(self, *states: bool, models: int = 3) -> None:
        self.states = list(states)
        self.models = models
        self.calls = 0

    def probe(self) -> tuple[bool, int]:
        self.calls += 1
        up = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return up, self.models if up else 0


def _check(ollama: Ollama, *, command=("ollama app.exe",)):
    started: list[list[str]] = []
    result = hw.check_ollama(
        probe=ollama.probe,
        launch_command=lambda: list(command) if command else None,
        start=started.append,
        sleep=lambda _s: None,
        wait_s=9.0,
    )
    return result, started


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #
def test_an_up_runtime_is_left_alone() -> None:
    (state, findings), started = _check(Ollama(True))
    assert state["up"] and state["action"] == "none"
    assert findings == [] and started == []


def test_a_down_runtime_is_restarted_and_reported() -> None:
    (state, findings), started = _check(Ollama(False, False, True))
    assert started == [["ollama app.exe"]]
    assert state["action"] == "restarted" and state["up"]
    assert [f.title for f in findings] == ["Ollama was down -- restarted"]


def test_a_restart_that_does_not_answer_is_an_alert_not_silence() -> None:
    (state, findings), started = _check(Ollama(False))
    assert len(started) == 1
    assert state == {"up": False, "action": "restart_did_not_answer", "waited_s": 9.0}
    assert findings and "did not bring it back" in findings[0].title


def test_not_installed_is_reported_and_nothing_is_started() -> None:
    (state, findings), started = _check(Ollama(False), command=None)
    assert started == [] and state["action"] == "not_installed"
    assert findings and "not installed" in findings[0].title


def test_a_probe_that_raises_counts_as_down() -> None:
    def boom():
        raise ConnectionError("refused")

    state, findings = hw.check_ollama(
        probe=boom,
        launch_command=lambda: None,
        start=lambda c: None,
        sleep=lambda s: None,
    )
    assert state["up"] is False and state["error"] == "refused"
    assert findings


def test_a_start_that_fails_is_reported() -> None:
    def cannot(_cmd):
        raise OSError("access denied")

    state, findings = hw.check_ollama(
        probe=Ollama(False).probe,
        launch_command=lambda: ["ollama app.exe"],
        start=cannot,
        sleep=lambda s: None,
    )
    assert state["action"] == "start_failed"
    assert findings and "restart failed" in findings[0].title


# --------------------------------------------------------------------------- #
# CI
# --------------------------------------------------------------------------- #
def _run(rid, conclusion, status="completed", name="CI", hours_ago=1.0):
    from datetime import datetime, timedelta, timezone

    created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "databaseId": rid,
        "workflowName": name,
        "conclusion": conclusion,
        "status": status,
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": f"https://example/runs/{rid}",
        "headSha": "abcdef0123",
    }


def test_a_red_workflow_is_reported_once() -> None:
    runs = [
        _run(1, "failure", name="Nightly"),
        _run(5, "", status="in_progress", name="CI"),
        _run(4, "timed_out", name="CI"),
        _run(3, "success", name="CodeQL"),
    ]
    state, findings, reported = hw.check_ci(set(), runs=lambda: runs)
    assert reported == {1, 4}
    assert sorted(f.title for f in findings) == [
        "CI failed on master: CI",
        "CI failed on master: Nightly",
    ]
    _state, again, _ = hw.check_ci(reported, runs=lambda: runs)
    assert again == [], "a failure already reported was reported again"


def test_a_failure_a_later_green_run_superseded_is_not_an_alert() -> None:
    """Newest first: CI went red, then green again -- master is not red now."""
    runs = [_run(12, "success"), _run(11, "failure"), _run(10, "startup_failure")]
    _state, findings, reported = hw.check_ci(set(), runs=lambda: runs)
    assert findings == [] and reported == set()


def test_each_new_red_run_of_a_workflow_is_its_own_alert() -> None:
    """Red, reported; still red on a NEW run -- that is news again."""
    _s, first, reported = hw.check_ci(set(), runs=lambda: [_run(20, "failure")])
    runs = [_run(21, "failure"), _run(20, "failure")]
    _s, second, reported = hw.check_ci(reported, runs=lambda: runs)
    assert len(first) == 1 and len(second) == 1 and reported == {20, 21}


def test_not_being_able_to_look_is_logged_not_notified() -> None:
    def gh_missing():
        raise FileNotFoundError("gh")

    state, findings, reported = hw.check_ci({9}, runs=gh_missing)
    assert state["checked"] is False and findings == [] and reported == {9}


# --------------------------------------------------------------------------- #
# One cycle: notify, state, log
# --------------------------------------------------------------------------- #
def _cycle(tmp_path: Path, runs, *, quiet=False, ollama=(True,)):
    shown: list[tuple[str, str]] = []
    report = hw.run_once(
        data_dir=tmp_path,
        notify=lambda t, b: shown.append((t, b)) or True,
        quiet=quiet,
        ollama_check=lambda: _check(Ollama(*ollama))[0],
        ci_runs=lambda: runs,
    )
    return report, shown


def test_a_cycle_notifies_new_findings_and_remembers_them(tmp_path: Path) -> None:
    runs = [_run(7, "failure")]
    report, shown = _cycle(tmp_path, runs, ollama=(False, True))
    assert [t for t, _ in shown] == [
        "Ollama was down -- restarted",
        "CI failed on master: CI",
    ]
    report, shown = _cycle(tmp_path, runs)
    assert shown == [], "the second cycle re-notified"
    lines = (tmp_path / "health_watch.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["notified"] == [True, True]
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8")) == {
        "reported_ci": [7]
    }


def test_quiet_logs_without_notifying(tmp_path: Path) -> None:
    _report, shown = _cycle(tmp_path, [_run(8, "failure")], quiet=True)
    assert shown == []
    logged = json.loads((tmp_path / "health_watch.jsonl").read_text(encoding="utf-8"))
    assert [f["title"] for f in logged["findings"]] == ["CI failed on master: CI"]


def test_a_corrupt_state_file_re_reports_rather_than_hides(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    _report, shown = _cycle(tmp_path, [_run(10, "failure")])
    assert [t for t, _ in shown] == ["CI failed on master: CI"]


def test_the_toast_escapes_markup_and_quotes(monkeypatch) -> None:
    seen = {}

    class Done:
        returncode = 0

    def fake_run(argv, **kwargs):
        import base64

        seen["script"] = base64.b64decode(argv[-1]).decode("utf-16-le")
        return Done()

    monkeypatch.setattr(hw.os, "name", "nt")
    monkeypatch.setattr(hw.subprocess, "run", fake_run)
    assert hw.windows_toast("a <b> & 'c'", "x") is True
    assert "a &lt;b&gt; &amp; ''c''" in seen["script"]


def test_the_scheduled_task_is_printed_not_created() -> None:
    command = hw.task_command()
    assert command.startswith("schtasks /Create") and "--once" in command
    assert "/SC MINUTE /MO 30" in command


def test_main_without_a_mode_does_nothing() -> None:
    assert hw.main([]) == 2


@pytest.mark.parametrize("conclusion", ["success", "cancelled", "skipped", "neutral"])
def test_non_failures_are_never_reported(conclusion) -> None:
    _state, findings, reported = hw.check_ci(set(), runs=lambda: [_run(11, conclusion)])
    assert findings == [] and reported == set()


def test_the_first_run_does_not_replay_old_history(tmp_path: Path) -> None:
    """Installing the watch must not burst weeks of old failures at once."""
    runs = [
        _run(21, "failure", hours_ago=2, name="Nightly"),
        _run(20, "failure", hours_ago=72, name="CI"),
    ]
    _report, shown = _cycle(tmp_path, runs)
    assert [t for t, _ in shown] == ["CI failed on master: Nightly"]
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state == {"reported_ci": [20, 21]}, (
        "the old failure was not recorded as seen"
    )


def test_after_the_first_run_every_new_failure_is_reported_whatever_its_age(
    tmp_path: Path,
) -> None:
    """The lookback applies to the first run only: a later cycle that finds an
    unseen failure reports it even if it is old (a laptop asleep for days)."""
    _cycle(tmp_path, [])
    _report, shown = _cycle(tmp_path, [_run(30, "failure", hours_ago=96)])
    assert [t for t, _ in shown] == ["CI failed on master: CI"]
