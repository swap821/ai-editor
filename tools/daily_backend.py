"""The operator's daily backend, started the same way every time.

Why (2026-10-29, "make the daily animal boring"). Until today his daily
backend's settings lived in an agent's scratch script. Started any other way it
ran under another scope identity, so every reflex he had earned stopped
matching; or without the live learning key, so an activation could not be
signed; or with his user-wide ``AIOS_ROUTER_CLOUD_TASKS=reasoning,coding``,
so a coding turn on ``auto`` went to the cloud first. Each failure is silent.
This is the one way to start it, with every setting he chose:

=============================  ====================================  ==========
setting                        value                                 decided
=============================  ====================================  ==========
AIOS_SCOPE_ROOTS               training_ground;lab;work (that order)  2026-10-28
AIOS_TASK_SCOPE                work/ai-editor                        2026-10-29
AIOS_CONTAINER_IMAGE           aios-verify:<sha12 of requirements>   2026-10-28
AIOS_EXECUTOR_TIMEOUT_S        120                                   2026-10-28
AIOS_REPLAY_APPROVED_COMMANDS  1                                     2026-10-19
AIOS_ROUTER_CLOUD_TASKS        reasoning,coding, or --cloud-tasks    2026-11-03
AIOS_PLAN_CLAUDE_MODELS        claude-sonnet-5-5,claude-haiku-5-5    2026-11-03
AIOS_PLAN_CODEX_MODELS         gpt-6.1-sol,gpt-6.1-terra,gpt-6-luna  2026-11-03
AIOS_PROFILE                   production                            2026-11-09
=============================  ====================================  ==========

On 2026-11-03 the operator connected his own plans to the counter: "connect
codex models to counter also and C" (Claude through Claude Code, the GPT models
through Codex; :mod:`aios.core.plan_cli`). Cloud tasks became his own
user-wide choice, ``reasoning,coding``; general and fast turns stay local.
Opus is left out: it would spend the plan he shares with his own sessions
fastest. ``--cloud-tasks ""`` keeps every turn local.

The face (2026-11-03, D14: "plz honestly do all"). The frontend dev server on
:5173 did not start by itself after a reboot. ``up`` now also makes sure it
answers: if ``http://localhost:5173`` is silent it starts ``npm run dev`` from
``frontend/`` (no window, detached, output to ``data/services/frontend.log``)
and records the pid in the state file; if something already answers, it is left
alone and is not recorded as ours, so ``down`` never stops a server he started
by hand. Without ``frontend/node_modules`` it starts nothing and says to run
``npm ci``. The watchdog that already runs ``up`` every 15 minutes
(``\\GAGOS\\backend``) thereby brings the face back after every reboot, with no
change to his scheduled tasks.

(``docs/operations/WORK_SCOPE.md`` and ``docs/operations/DAILY_BACKEND.md``.)

Commands, from the repository root::

    .venv\\Scripts\\python.exe tools\\daily_backend.py up       # start, then check
    .venv\\Scripts\\python.exe tools\\daily_backend.py check    # would each reflex serve?
    .venv\\Scripts\\python.exe tools\\daily_backend.py status
    .venv\\Scripts\\python.exe tools\\daily_backend.py down

``check`` is read-only and calls no model: it asks ``Cerebellum.readiness``,
under the scope binding the backend uses, whether each learned reflex would
serve its own request now, and why not. Its exit code is 0 only when at least
one reflex is ready.

Keys: the ones the daily backend needs are read from Windows Credential
Manager in memory and handed to the child processes only. No value is printed
or written; the state file names which were loaded.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
SERVICES = REPO / "data" / "services"
STATE = SERVICES / "daily.json"
BACKEND_PORT = 8000
EXECUTOR_PORT = 8081
FACE_PORT = 5173
FRONTEND = REPO / "frontend"
#: The keys the daily backend needs, and no others. Loading every stored key
#: also sets ``AIOS_API_TOKEN``, which turns on token-only auth and refused the
#: operator's own local tools (2026-10-19).
KEYS = (
    "AIOS_VERIFICATION_AUTHORITY_KEY",
    "AIOS_EXECUTOR_TOKEN",
    "AIOS_PROMOTION_AUTHORITY_KEY",
    "AIOS_CHECKPOINT_AUTHORITY_KEY",
    "AIOS_LEARNING_KEY_LIVE",
    # The audit chain's signing seed: without it each start signs with a
    # throwaway key and the chain cannot verify (2026-10-29). Loaded when stored.
    "AIOS_AUDIT_PRIVATE_KEY",
)
_DETACHED = (0x00000008 | 0x00000200) if os.name == "nt" else 0
#: The face runs under cmd.exe (npm is a .cmd): CREATE_NO_WINDOW | NEW_PROCESS_GROUP.
#: DETACHED_PROCESS would let cmd.exe open a console window of its own.
_FACE_FLAGS = (0x08000000 | 0x00000200) if os.name == "nt" else 0


def staged_root() -> Path:
    """Where the backend stages maintenance work, so the executor accepts it.

    The backend's own ``config.DATA_DIR`` (the scope lock pins this staging
    root): until 2026-11-04 the executor was pointed at this checkout's
    ``data`` directory whatever ``AIOS_DATA_DIR`` said, and every staged job
    would have been refused had it been set.
    """
    from aios import config

    return config.DATA_DIR / "staged_maintenance"


def verify_image(repo: Path = REPO) -> str:
    """The sandbox image for *repo*'s requirements (``Dockerfile.verify``): the
    sandbox's own formula, not a copy of it (2026-11-04)."""
    from aios.maintenance.sandbox_tests import verify_image as image_for

    return image_for((repo / "requirements.txt").read_bytes())


#: The operator's plans at the counter (2026-11-03): see the table above.
CLOUD_TASKS = "reasoning,coding"
PLAN_CLAUDE = ("claude-sonnet-5-5", "claude-haiku-5-5")
PLAN_CODEX = ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")


def daily_settings(
    repo: Path = REPO, *, cloud_tasks: str = CLOUD_TASKS
) -> dict[str, str]:
    """The daily backend's launch settings. No secret is among them.

    ``AIOS_ROUTER_CLOUD_TASKS`` is always set, so a value inherited from the
    user's environment never decides where a turn goes: the launch decides
    (``--cloud-tasks``; his choice since 2026-11-03 is the default).
    """
    return {
        # training_ground FIRST: commands run from the parent of the first root.
        "AIOS_SCOPE_ROOTS": os.pathsep.join(
            str(repo / name) for name in ("training_ground", "lab", "work")
        ),
        "AIOS_TASK_SCOPE": os.path.join("work", "ai-editor"),
        "AIOS_CONTAINER_IMAGE": verify_image(repo),
        "AIOS_EXECUTOR_TIMEOUT_S": "120",
        "AIOS_REPLAY_APPROVED_COMMANDS": "1",
        "AIOS_ROUTER_CLOUD_TASKS": cloud_tasks,
        "AIOS_PLAN_CLAUDE_MODELS": ",".join(PLAN_CLAUDE),
        "AIOS_PLAN_CODEX_MODELS": ",".join(PLAN_CODEX),
        # The operator, 2026-11-09: his counter runs as production, so every
        # command crosses the private executor with isolation proof. Unset,
        # GAGOS is development (aios/config.py DEFAULT_PROFILE).
        "AIOS_PROFILE": "production",
    }


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _health(port: int, timeout: float = 3.0) -> Optional[int]:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001 - down is down
        return None


def _face_health(timeout: float = 3.0) -> Optional[int]:
    """The dev server answers ``/`` (any HTTP status counts as answering)."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:{FACE_PORT}", timeout=timeout
        ) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001 - down is down
        return None


def _face_command() -> list[str]:
    # --strictPort: never drift to :5174 and leave :5173 silent.
    run = ["npm", "run", "dev", "--", "--port", str(FACE_PORT), "--strictPort"]
    return ["cmd.exe", "/c", *run] if os.name == "nt" else run


def _write_state(state: dict[str, Any]) -> None:
    SERVICES.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _ensure_face(wait_s: float = 60) -> str:
    """Make sure the face answers. Starts it only when :5173 is silent."""
    status = _face_health()
    if status is not None:
        state = _read_state()
        face = state.get("face")
        if face and not _face_is_ours(face):
            # Not the one this tool started: its record is stale.
            del state["face"]
            _write_state(state)
        return f"already answers on :{FACE_PORT} (HTTP {status}); left alone"
    if not (FRONTEND / "node_modules").is_dir():
        return (
            f"not started: {FRONTEND / 'node_modules'} is missing; "
            f"run npm ci in {FRONTEND}"
        )
    SERVICES.mkdir(parents=True, exist_ok=True)
    with (SERVICES / "frontend.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            _face_command(),
            cwd=str(FRONTEND),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=_FACE_FLAGS,
        )
    state = _read_state()
    state["face"] = {
        "pid": process.pid,
        # Its identity: a pid with this creation time is this process and no
        # other, even after the pid is reused.
        "created": _process_created(process.pid),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "port": FACE_PORT,
    }
    _write_state(state)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _face_health() is not None:
            return f"started on :{FACE_PORT} (pid {process.pid})"
        time.sleep(1)
    return (
        f"started (pid {process.pid}) but :{FACE_PORT} did not answer; "
        f"see {SERVICES / 'frontend.log'}"
    )


def _process_created(pid: int) -> Optional[str]:
    """When the process *pid* was created (UTC, to the 100 ns Windows keeps),
    or None when no such process runs."""
    if os.name != "nt":  # pragma: no cover - the operator's laptop is Windows
        return None
    try:
        out = _run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' | "
                "ForEach-Object { $_.CreationDate.ToUniversalTime().ToString('o') }",
            ],
            timeout=60,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - unknown is not ours
        return None
    return out or None


def _face_is_ours(face: dict[str, Any]) -> bool:
    """Whether the recorded face process is still the one this tool started:
    the same pid created at the same instant. A recorded pid outlives a reboot
    and can be another program's by then (both reviewers of D14, 2026-11-03);
    a reused pid never has the same creation time. Measured that day: Windows'
    own socket listings (netstat, Get-NetTCPConnection) missed live listeners on
    this laptop, so the port's owner is not what decides."""
    pid, created = face.get("pid"), face.get("created")
    return bool(pid and created) and _process_created(int(pid)) == created


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        # /T: cmd.exe -> npm -> node; the whole tree goes.
        _run(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=30)
    else:  # pragma: no cover - the operator's laptop is Windows
        try:
            os.kill(int(pid), 15)
        except OSError:
            pass


#: How long a backend this tool started, still running, may take to answer
#: before it is taken for hung (a paged-out backend on a full laptop is slow).
SLOW_BACKEND_WAIT_S = 120


def _running_ours(state: dict[str, Any], name: str) -> Optional[int]:
    """The pid of the service *name* this tool started, when that very process
    still runs: recorded with its creation time, and the same pid still has it.
    A record without one (written before 2026-11-12) is never taken for ours:
    after a reboot its pid can be any program's."""
    pid = (state.get("pids") or {}).get(name)
    created = (state.get("created") or {}).get(name)
    if not pid or not created:
        return None
    return int(pid) if _process_created(int(pid)) == created else None


def _wait_health(port: int, seconds: float) -> Optional[int]:
    deadline = time.time() + seconds
    while time.time() < deadline:
        status = _health(port)
        if status is not None:
            return status
        time.sleep(2)
    return None


def _run(command: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        command, capture_output=True, text=True, timeout=timeout, check=False
    )


def _git(*args: str, cwd: Path = REPO) -> str:
    try:
        return _run(["git", "-C", str(cwd), *args]).stdout.strip()
    except Exception:  # noqa: BLE001 - informational only
        return ""


def _read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stored_keys() -> dict[str, str]:
    """The daily keys from the operator's keystore, in memory. Empty when there
    is no keystore (the backend then runs without them, as it would anyway)."""
    sys.path.insert(0, str(REPO))
    try:
        from aios.operations.keystore import (
            KeystoreUnavailable,
            default_keystore,
            production_environment,
        )
    except Exception:  # noqa: BLE001
        return {}
    try:
        stored = production_environment(default_keystore())
    except KeystoreUnavailable:
        return {}
    return {name: value for name, value in stored.items() if name in KEYS}


# --------------------------------------------------------------------------- #
# Preconditions
# --------------------------------------------------------------------------- #
def _ensure_ollama() -> str:
    sys.path.insert(0, str(REPO))
    from tools.health_watch import (
        ollama_available,
        ollama_launch_command,
        start_ollama,
    )

    if ollama_available()[0]:
        return "up"
    command = ollama_launch_command()
    if command is None:
        return "not installed"
    start_ollama(command)
    deadline = time.time() + 60
    while time.time() < deadline:
        if ollama_available()[0]:
            return "started"
        time.sleep(2)
    return "did not come up"


def _ensure_docker() -> bool:
    def reachable() -> bool:
        try:
            return _run(["docker", "info"], timeout=20).returncode == 0
        except Exception:  # noqa: BLE001
            return False

    if reachable():
        return True
    try:
        _run(["docker", "desktop", "start"], timeout=180)
    except Exception:  # noqa: BLE001
        pass
    deadline = time.time() + 180
    while time.time() < deadline:
        if reachable():
            return True
        time.sleep(5)
    return False


def _image_present(tag: str) -> bool:
    try:
        return _run(["docker", "image", "inspect", tag], timeout=30).returncode == 0
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def up(args: argparse.Namespace) -> int:
    # The face does not depend on the backend, so it is made sure of first: a
    # refusal below (Docker, image) must not leave him without a face.
    print("face:", _ensure_face())
    if _health(BACKEND_PORT) is not None:
        print(f"a backend already answers on :{BACKEND_PORT}; not starting another.")
        status(args)
        return check(args)

    # 2026-11-12: the watchdog read a 3-second silence as "down" and started a
    # second backend beside a slow one, never stopping it; five were running,
    # each ~1.85 GB committed, on a 16 GB laptop. A backend this tool started
    # that still runs is waited for; one that stays silent is stopped, its
    # whole tree, before anything new starts. Never two.
    previous = _read_state()
    backend = _running_ours(previous, "backend")
    if backend is not None:
        if _wait_health(BACKEND_PORT, SLOW_BACKEND_WAIT_S) is not None:
            print(
                f"the backend this tool started (pid {backend}) answered after a wait; "
                "not starting another."
            )
            status(args)
            return check(args)
        print(
            f"the backend this tool started (pid {backend}) runs but has not answered "
            f"for {SLOW_BACKEND_WAIT_S}s: stopping it before starting a new one"
        )
        for name in ("backend", "executor"):
            pid = _running_ours(previous, name)
            if pid is not None:
                _kill_tree(pid)
                print(f"stopped {name} (pid {pid})")
        time.sleep(2)

    settings = daily_settings(cloud_tasks=args.cloud_tasks)
    work = REPO / "work" / "ai-editor"
    if not work.is_dir():
        print(
            f"refused: the work checkout {work} does not exist (docs/operations/WORK_SCOPE.md)"
        )
        return 2
    print("ollama:", _ensure_ollama())
    if not _ensure_docker():
        print("refused: Docker is not reachable, and the sandbox needs it")
        return 2
    image = settings["AIOS_CONTAINER_IMAGE"]
    if not _image_present(image):
        sha = image.split(":", 1)[1]
        print(
            f"refused: the sandbox image {image} is not built. Build it with:\n"
            f"  docker build -f Dockerfile.verify --label requirements.sha256=<sha256 of "
            f"requirements.txt> -t {image} .   (sha12 {sha})"
        )
        return 2

    keys = _stored_keys()
    token = keys.get("AIOS_EXECUTOR_TOKEN") or secrets.token_hex(32)
    base = {**os.environ, **keys, "AIOS_EXECUTOR_TOKEN": token}
    SERVICES.mkdir(parents=True, exist_ok=True)

    def spawn(name: str, command: list[str], env: dict[str, str]) -> int:
        log = (SERVICES / f"{name}.log").open("w", encoding="utf-8")
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            command,
            cwd=str(REPO),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED,
        )
        return process.pid

    executor_env = {
        **base,
        "AIOS_EXECUTOR_WORKSPACE_ROOT": str(staged_root()),
        "AIOS_EXECUTOR_HOST": "127.0.0.1",
        "AIOS_EXECUTOR_PORT": str(EXECUTOR_PORT),
    }
    backend_env = {
        **base,
        **settings,
        "AIOS_EXECUTOR_URL": f"http://127.0.0.1:{EXECUTOR_PORT}",
    }
    if args.maintenance_root:
        backend_env["AIOS_MAINTENANCE_PROJECT_ROOT"] = args.maintenance_root

    pids = {
        "executor": spawn(
            "executor",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "aios.executor_service:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(EXECUTOR_PORT),
            ],
            executor_env,
        ),
        "backend": spawn("backend", [sys.executable, "-m", "aios"], backend_env),
    }
    state = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pids": pids,
        # Which processes these pids are: the next `up` stops only these.
        "created": {name: _process_created(pid) for name, pid in pids.items()},
        "code": _git("rev-parse", "HEAD"),
        "work_head": _git("rev-parse", "HEAD", cwd=work),
        "work_clean": _git("status", "--porcelain", cwd=work) == "",
        "settings": settings,
        "maintenance_root": args.maintenance_root,
        "keys_loaded": sorted(keys),
        "executor_health": _wait_health(EXECUTOR_PORT, 90),
        "backend_health": _wait_health(BACKEND_PORT, 240),
    }
    # The state file is rewritten here; the face's record (if ours) must survive.
    face = _read_state().get("face")
    if face:
        state["face"] = face
    _write_state(state)
    print(json.dumps({k: v for k, v in state.items() if k != "settings"}, indent=2))
    missing = sorted(set(KEYS) - set(keys))
    if missing:
        print("not in the keystore, so not loaded:", ", ".join(missing))
    if state["backend_health"] != 200:
        print(f"the backend did not answer healthy; see {SERVICES / 'backend.log'}")
        return 1
    return check(args)


def check(args: argparse.Namespace) -> int:
    """Run the readiness report in a child process that has the daily settings,
    so configuration is read exactly as the backend reads it at import."""
    settings = daily_settings(cloud_tasks=args.cloud_tasks)
    env = {**os.environ, **_stored_keys(), **settings}
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(Path(__file__).resolve()), "_report"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode not in (0, 1):
        print(result.stdout[-2000:], result.stderr[-4000:])
        return 2
    report = json.loads(result.stdout.strip().splitlines()[-1])
    image = settings["AIOS_CONTAINER_IMAGE"]
    report["sandbox_image"] = image
    report["sandbox_image_present"] = _image_present(image)
    _print_report(report)
    return 0 if report["ready"] and report["sandbox_image_present"] else 1


def _report() -> int:
    """(child) The readiness report as one JSON line. Reads; writes nothing."""
    sys.path.insert(0, str(REPO))
    from contextlib import nullcontext

    from aios import config
    from aios.api import deps
    from aios.application.memory import reflex_contract
    from aios.application.turns.task_scope import resolve_task_scope
    from aios.core.autonomy import workspace_id
    from aios.core.cerebellum import Cerebellum
    from aios.security import scope_lock

    scope = resolve_task_scope(None)
    adapter = deps.get_memory_authority().adapters.get("cerebellum")
    cerebellum = getattr(adapter, "store", None)
    if not isinstance(cerebellum, Cerebellum):
        raise RuntimeError("the memory authority has no cerebellum")
    binding = scope_lock.scope_context(scope.roots) if scope else nullcontext()
    with binding:
        rows = cerebellum.readiness(emergency_stop=deps.get_emergency_stop())
        identity = reflex_contract.scope_identity()
        workspace = workspace_id()
    report = {
        "task_scope": [str(r) for r in scope.roots] if scope else None,
        "scope_identity": identity,
        "workspace": workspace,
        "auto_routing": (
            "local only"
            if not config.ROUTER_CLOUD_TASKS
            else "cloud-eligible for " + ",".join(config.ROUTER_CLOUD_TASKS)
        ),
        "bedrock_offered": deps.get_bedrock_client() is not None,
        "reflexes": rows,
        "ready": sum(1 for row in rows if row["ready"]),
    }
    print(json.dumps(report))
    return 0 if report["ready"] else 1


def _print_report(report: dict[str, Any]) -> None:
    print(f"scope: {report['scope_identity']}  (task scope {report['task_scope']})")
    print(
        f"auto routing: {report['auto_routing']}; Bedrock offered: {report['bedrock_offered']}"
    )
    print(
        f"sandbox image: {report['sandbox_image']} "
        + ("present" if report["sandbox_image_present"] else "MISSING")
    )
    for row in report["reflexes"]:
        mark = "READY" if row["ready"] else "NOT READY"
        print(
            f"  [{mark}] playbook {row['playbook_id']} (replayed {row['replay_count']}x): {row['goal'][:100]}"
        )
        for reason in row["reasons"]:
            print(f"      - {reason}")
    print(f"{report['ready']} of {len(report['reflexes'])} reflex(es) ready")


def status(args: argparse.Namespace) -> int:
    state = _read_state()
    print(f"backend :{BACKEND_PORT} health: {_health(BACKEND_PORT)}")
    print(f"executor :{EXECUTOR_PORT} health: {_health(EXECUTOR_PORT)}")
    face = state.get("face") or {}
    print(
        f"face :{FACE_PORT} health: {_face_health()} "
        + (
            f"(started by this tool, pid {face['pid']})"
            if face.get("pid")
            else "(not started by this tool)"
        )
    )
    if state:
        print(json.dumps(state, indent=2))
    else:
        print("no state file: this tool has not started a daily backend here")
    return 0


def down(args: argparse.Namespace) -> int:
    state = _read_state()
    pids = (state.get("pids") or {}) if state else {}
    face = (state.get("face") or {}) if state else {}
    if not pids and not face.get("pid"):
        print("no state file: nothing this tool started is recorded; stopping nothing")
        return 1
    for name, pid in pids.items():
        # /T: the venv launcher re-execs the real interpreter as a child.
        _kill_tree(pid)
        print(f"stopped {name} (pid {pid})")
    ours = False
    if face.get("pid"):
        # A recorded pid outlives a reboot and can be another process's by now:
        # it is stopped only when the server on the port descends from it.
        if _face_health() is None:
            print(f"face (pid {face['pid']}) is not answering; nothing to stop")
        elif not _face_is_ours(face):
            print(
                f"the face answering on :{FACE_PORT} is not the one this tool "
                f"started (pid {face['pid']}); not stopped"
            )
        else:
            ours = True
            _kill_tree(face["pid"])
            print(f"stopped face (pid {face['pid']})")
    time.sleep(2)
    still = [
        p for p in (BACKEND_PORT, EXECUTOR_PORT) if pids and _health(p) is not None
    ]
    if ours and _face_health() is not None:
        still.append(FACE_PORT)
    if still:
        print("still answering on", still)
        return 1
    STATE.unlink(missing_ok=True)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("command", choices=("up", "check", "status", "down", "_report"))
    parser.add_argument(
        "--cloud-tasks",
        default=CLOUD_TASKS,
        help=f'task classes auto may send to the cloud; default "{CLOUD_TASKS}", "" for none',
    )
    parser.add_argument(
        "--maintenance-root",
        default=None,
        help="a clean worktree for self-repair (AIOS_MAINTENANCE_PROJECT_ROOT)",
    )
    args = parser.parse_args(argv)
    if args.command == "_report":
        return _report()
    return {"up": up, "check": check, "status": status, "down": down}[args.command](
        args
    )


if __name__ == "__main__":
    raise SystemExit(main())
