"""``tools/daily_backend.py``: the operator's daily backend, started one way.

Pinned here: the settings it launches with are the ones he chose, and an
``AIOS_ROUTER_CLOUD_TASKS`` inherited from his user-wide environment never
decides where a turn goes (2026-10-29: his ``reasoning,coding`` sent the daily
backend's coding turns to Bedrock first). Whether a reflex would serve is
``Cerebellum.readiness``, pinned in ``tests/test_reflex_readiness.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from tools import daily_backend

REPO = Path(daily_backend.__file__).resolve().parents[1]


def test_the_settings_are_the_ones_the_operator_chose() -> None:
    settings = daily_backend.daily_settings()
    roots = settings["AIOS_SCOPE_ROOTS"].split(os.pathsep)
    # training_ground FIRST: commands run from the parent of the first root.
    assert roots == [str(REPO / n) for n in ("training_ground", "lab", "work")]
    assert settings["AIOS_TASK_SCOPE"] == os.path.join("work", "ai-editor")
    assert settings["AIOS_EXECUTOR_TIMEOUT_S"] == "120"
    assert settings["AIOS_REPLAY_APPROVED_COMMANDS"] == "1"
    # 2026-11-03: his own plans at the counter, for his own user-wide classes.
    assert settings["AIOS_ROUTER_CLOUD_TASKS"] == "reasoning,coding"
    assert settings["AIOS_PLAN_CLAUDE_MODELS"] == "claude-sonnet-5-5,claude-haiku-5-5"
    assert settings["AIOS_PLAN_CODEX_MODELS"] == "gpt-6.1-sol,gpt-6.1-terra,gpt-6-luna"
    assert daily_backend.daily_settings(cloud_tasks="")["AIOS_ROUTER_CLOUD_TASKS"] == ""
    # 2026-11-09: his counter runs as production (the private executor).
    assert settings["AIOS_PROFILE"] == "production"


def test_the_sandbox_image_names_the_requirements_it_holds() -> None:
    """Dockerfile.verify's convention: the tag is the first 12 of the sha256 of
    requirements.txt, so a requirements change names an image not yet built."""
    digest = hashlib.sha256((REPO / "requirements.txt").read_bytes()).hexdigest()
    assert daily_backend.verify_image() == f"aios-verify:{digest[:12]}"
    assert (
        daily_backend.daily_settings()["AIOS_CONTAINER_IMAGE"]
        == daily_backend.verify_image()
    )


def test_no_secret_is_a_setting() -> None:
    settings = daily_backend.daily_settings()
    assert not set(settings) & set(daily_backend.KEYS)


def _cloud_tasks_seen(env: dict[str, str]) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from aios.security import limits; "
            "print(json.dumps(list(limits.ROUTER_CLOUD_TASKS)))",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    ("chosen", "expected"),
    [("", []), ("reasoning", ["reasoning"])],
)
def test_an_inherited_cloud_opt_in_never_decides(chosen: str, expected: list) -> None:
    """The operator's user-wide value reaches every process he starts. The
    daily backend always sets its own, so only the launch choice counts."""
    inherited = {**os.environ, "AIOS_ROUTER_CLOUD_TASKS": "reasoning,coding"}
    assert _cloud_tasks_seen(inherited) == ["reasoning", "coding"]
    env = {**inherited, **daily_backend.daily_settings(cloud_tasks=chosen)}
    assert _cloud_tasks_seen(env) == expected


def test_down_stops_nothing_it_did_not_start(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(daily_backend, "STATE", tmp_path / "daily.json")
    assert daily_backend.main(["down"]) == 1
    assert "stopping nothing" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# The face (2026-11-03, D14): `up` makes sure :5173 answers. No real server, no
# real process: Popen, the health probes and taskkill are replaced.
# --------------------------------------------------------------------------- #
class _FakePopen:
    launched: list[dict] = []

    def __init__(self, command, **kwargs) -> None:
        self.pid = 4242
        _FakePopen.launched.append({"command": command, **kwargs})


@pytest.fixture()
def face(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    (frontend / "node_modules").mkdir(parents=True)
    monkeypatch.setattr(daily_backend, "FRONTEND", frontend)
    monkeypatch.setattr(daily_backend, "SERVICES", tmp_path / "services")
    monkeypatch.setattr(daily_backend, "STATE", tmp_path / "services" / "daily.json")
    monkeypatch.setattr(daily_backend.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(daily_backend.time, "sleep", lambda _s: None)
    _FakePopen.launched = []
    killed: list[int] = []
    monkeypatch.setattr(daily_backend, "_kill_tree", killed.append)
    created = {4242: "2026-11-03T13:01:04.8287920Z"}
    monkeypatch.setattr(daily_backend, "_process_created", created.get)
    return SimpleNamespace(
        frontend=frontend, killed=killed, tmp=tmp_path, created=created
    )


def test_up_starts_the_face_when_5173_is_down_and_records_the_pid(
    face, monkeypatch
) -> None:
    answers = iter([None, None, 200])  # silent, then silent, then up
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: next(answers))
    message = daily_backend._ensure_face()
    assert "started on :5173 (pid 4242)" in message
    (launch,) = _FakePopen.launched
    assert launch["cwd"] == str(face.frontend)
    assert launch["command"][-5:] == ["dev", "--", "--port", "5173", "--strictPort"]
    assert launch["stdin"] == subprocess.DEVNULL
    # No window, and it outlives the starter (a process group of its own).
    if os.name == "nt":
        assert launch["creationflags"] & 0x08000000 and launch["creationflags"] & 0x200
    assert (face.tmp / "services" / "frontend.log").exists()
    state = json.loads(daily_backend.STATE.read_text(encoding="utf-8"))
    assert state["face"]["pid"] == 4242 and state["face"]["port"] == 5173
    assert state["face"]["created"] == face.created[4242], "its identity is kept"


def test_up_leaves_an_answering_face_alone_and_does_not_record_it(
    face, monkeypatch
) -> None:
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: 200)
    message = daily_backend._ensure_face()
    assert "already answers" in message and "left alone" in message
    assert _FakePopen.launched == []
    assert not daily_backend.STATE.exists()


def test_up_refuses_the_face_without_node_modules(face, monkeypatch) -> None:
    (face.frontend / "node_modules").rmdir()
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: None)
    message = daily_backend._ensure_face()
    assert "npm ci" in message and "not started" in message
    assert _FakePopen.launched == []
    assert not daily_backend.STATE.exists()


def test_up_ensures_the_face_even_when_the_backend_already_answers(
    face, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: None)
    monkeypatch.setattr(daily_backend, "_health", lambda *a, **k: 200)
    monkeypatch.setattr(daily_backend, "check", lambda args: 0)
    # Answers after the start, so the wait ends.
    seen = {"started": False}
    original = _FakePopen.__init__

    def started(self, command, **kwargs):
        seen["started"] = True
        original(self, command, **kwargs)

    monkeypatch.setattr(_FakePopen, "__init__", started)
    monkeypatch.setattr(
        daily_backend,
        "_face_health",
        lambda *a, **k: 200 if seen["started"] else None,
    )
    assert daily_backend.main(["up"]) == 0
    out = capsys.readouterr().out
    assert "face: started on :5173" in out and "already answers on :8000" in out
    assert len(_FakePopen.launched) == 1


def test_down_stops_only_a_face_it_started(face, monkeypatch, capsys) -> None:
    monkeypatch.setattr(daily_backend, "_health", lambda *a, **k: None)
    # A face started by hand: nothing is recorded, so nothing is stopped.
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: 200)
    assert daily_backend.main(["down"]) == 1
    assert face.killed == []

    # Its own: recorded with the creation time the same pid still has, so the
    # whole tree is stopped.
    daily_backend._write_state(
        {"face": {"pid": 4242, "created": face.created[4242], "port": 5173}}
    )
    answers = iter([200, None])  # while checking, after the kill
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: next(answers))
    assert daily_backend.main(["down"]) == 0
    assert face.killed == [4242]
    assert "stopped face (pid 4242)" in capsys.readouterr().out
    assert not daily_backend.STATE.exists()


def test_down_never_kills_a_recorded_pid_another_program_now_holds(
    face, monkeypatch, capsys
) -> None:
    """Both reviewers of D14: after a reboot the recorded pid can be another
    program's while something else answers on :5173. Answering is not enough."""
    daily_backend._write_state(
        {"face": {"pid": 4242, "created": "2026-11-01T08:00:00.0000000Z", "port": 5173}}
    )
    monkeypatch.setattr(daily_backend, "_health", lambda *a, **k: None)
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: 200)
    assert daily_backend.main(["down"]) == 0
    assert face.killed == []
    assert "not the one this tool started" in capsys.readouterr().out


def test_up_drops_a_stale_face_record_when_another_server_answers(
    face, monkeypatch
) -> None:
    daily_backend._write_state(
        {"face": {"pid": 4242, "created": "2026-11-01T08:00:00.0000000Z"}, "pids": {}}
    )
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: 200)
    assert "left alone" in daily_backend._ensure_face()
    assert "face" not in json.loads(daily_backend.STATE.read_text(encoding="utf-8"))


def test_a_process_is_known_by_its_pid_and_creation_time(monkeypatch) -> None:
    """Windows' socket listings missed live listeners on his laptop (2026-11-03),
    so identity is the pid's creation time, read from Win32_Process."""
    asked: list = []

    def run(command, timeout=60):
        asked.append(command)
        out = (
            "2026-11-03T13:01:04.8287920Z\n" if "ProcessId=30324" in command[-1] else ""
        )
        return subprocess.CompletedProcess(command, 0, out, "")

    monkeypatch.setattr(daily_backend, "_run", run)
    if os.name == "nt":
        assert daily_backend._process_created(30324) == "2026-11-03T13:01:04.8287920Z"
        assert daily_backend._process_created(999999) is None
        assert asked[0][0] == "powershell" and "Win32_Process" in asked[0][-1]
    assert not daily_backend._face_is_ours({"pid": 30324}), (
        "an old record is never ours"
    )


def test_down_does_not_kill_a_recorded_pid_when_the_face_is_silent(
    face, monkeypatch
) -> None:
    """After a reboot the recorded pid can be another process's."""
    daily_backend._write_state({"face": {"pid": 4242, "port": 5173}})
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: None)
    assert daily_backend.main(["down"]) == 0
    assert face.killed == []


def test_status_reports_the_face_health_and_pid(face, monkeypatch, capsys) -> None:
    monkeypatch.setattr(daily_backend, "_health", lambda *a, **k: None)
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: 200)
    daily_backend.main(["status"])
    assert (
        "face :5173 health: 200 (not started by this tool)" in capsys.readouterr().out
    )
    daily_backend._write_state({"face": {"pid": 4242, "port": 5173}})
    daily_backend.main(["status"])
    assert (
        "face :5173 health: 200 (started by this tool, pid 4242)"
        in capsys.readouterr().out
    )


# --------------------------------------------------------------------------- #
# Never two backends (2026-11-12): the watchdog read a 3-second silence as
# "down" and started a second backend beside a slow one, never stopping it;
# five ran at once, ~1.85 GB committed each. A backend this tool started that
# still runs is waited for; one that stays silent is stopped before anything
# new starts; a record that cannot prove the pid is ours is never killed.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def backend_up(face, monkeypatch):
    work = face.tmp / "repo" / "work" / "ai-editor"
    work.mkdir(parents=True)
    monkeypatch.setattr(daily_backend, "REPO", face.tmp / "repo")
    monkeypatch.setattr(daily_backend, "_face_health", lambda *a, **k: 200)
    monkeypatch.setattr(daily_backend, "_health", lambda *a, **k: None)
    monkeypatch.setattr(daily_backend, "_ensure_ollama", lambda: "answers")
    monkeypatch.setattr(daily_backend, "_ensure_docker", lambda: True)
    monkeypatch.setattr(daily_backend, "_image_present", lambda tag: True)
    monkeypatch.setattr(daily_backend, "_stored_keys", lambda: {})
    monkeypatch.setattr(daily_backend, "staged_root", lambda: face.tmp / "staged")
    monkeypatch.setattr(daily_backend, "_git", lambda *a, **k: "")
    monkeypatch.setattr(daily_backend, "status", lambda args: 0)
    monkeypatch.setattr(daily_backend, "check", lambda args: 0)
    events: list[tuple] = []
    monkeypatch.setattr(
        daily_backend, "_kill_tree", lambda pid: events.append(("kill", pid))
    )
    original = _FakePopen.__init__

    def spawned(self, command, **kwargs):
        events.append(("spawn", command[-1]))
        original(self, command, **kwargs)

    monkeypatch.setattr(_FakePopen, "__init__", spawned)
    face.created.update(
        {5151: "2026-11-12T11:05:35.0000000Z", 5150: "2026-11-12T11:05:34.0000000Z"}
    )
    face.events = events
    return face


def _recorded(created: bool = True) -> dict:
    state = {"pids": {"executor": 5150, "backend": 5151}}
    if created:
        state["created"] = {
            "executor": "2026-11-12T11:05:34.0000000Z",
            "backend": "2026-11-12T11:05:35.0000000Z",
        }
    return state


def test_a_slow_backend_it_started_is_waited_for_never_doubled(
    backend_up, monkeypatch, capsys
) -> None:
    daily_backend._write_state(_recorded())
    monkeypatch.setattr(daily_backend, "_wait_health", lambda port, s: 200)
    assert daily_backend.main(["up"]) == 0
    assert backend_up.events == []
    assert "answered after a wait; not starting another" in capsys.readouterr().out


def test_a_hung_backend_is_stopped_before_a_new_one_starts(
    backend_up, monkeypatch, capsys
) -> None:
    daily_backend._write_state(_recorded())
    waits = iter([None, 200, 200])  # the slow wait, then the new executor and backend
    monkeypatch.setattr(daily_backend, "_wait_health", lambda port, s: next(waits))
    daily_backend.main(["up"])
    kinds = [kind for kind, _ in backend_up.events]
    assert backend_up.events[:2] == [("kill", 5151), ("kill", 5150)]
    assert kinds.count("spawn") == 2 and kinds.index("spawn") > 1
    assert "has not answered for 120s: stopping it" in capsys.readouterr().out
    # The new record says which processes the next `up` may stop.
    assert set(daily_backend._read_state()["created"]) == {"executor", "backend"}


@pytest.mark.parametrize("record", ["no creation time", "pid now another program's"])
def test_a_pid_it_cannot_prove_is_ours_is_never_killed(
    backend_up, monkeypatch, record
) -> None:
    state = _recorded(created=record != "no creation time")
    if record == "pid now another program's":
        backend_up.created[5151] = "2026-11-12T17:10:02.0000000Z"  # after a reboot
    daily_backend._write_state(state)
    monkeypatch.setattr(daily_backend, "_wait_health", lambda port, s: 200)
    daily_backend.main(["up"])
    assert [e for e in backend_up.events if e[0] == "kill"] == []
