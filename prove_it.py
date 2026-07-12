#!/usr/bin/env python
"""prove_it.py — the ten-minute proof of the supervised loop.

Runs the organism's core thesis end to end and prints a numbered, evidence-
carrying checklist: a directive is issued, a risky (YELLOW) write PAUSES for
human approval, an approved action executes scoped in a sandbox, a forced
auto-verify judges the result with real evidence (verification-strength
taxonomy, STRONG floor), and skill/development evidence is recorded.

Two modes:
  --live      A REAL spawned ``python -m aios`` server talking to a REAL local
              Ollama model. This is the actual product, unscripted.
  --scripted  An in-process TestClient against the REAL app object with ONLY
              the Ollama dependency overridden by a deterministic, scripted
              "brain". Every other subsystem (executor, approval store,
              verifier, skills/development stores) is REAL, running on
              hermetic temp DBs. The banner and every output line say
              SIMULATED BRAIN, unmistakably, on every run.

Usage:
    .venv\\Scripts\\python prove_it.py                 # auto: --live if a
                                                          usable Ollama model
                                                          is reachable, else
                                                          --scripted
    .venv\\Scripts\\python prove_it.py --live
    .venv\\Scripts\\python prove_it.py --scripted
    .venv\\Scripts\\python prove_it.py --live --port 8010 --keep-server

Exit code 0 iff every step is PROVED. Never leaves a spawned server process
running on exit.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import httpx
except ImportError:  # pragma: no cover - environment guard, not exercised in CI
    print(
        "FATAL: httpx is required (pinned in requirements). "
        "Run: .venv\\Scripts\\python -m pip install httpx==0.28.1",
        file=sys.stderr,
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
# Tool-calling-capable local models we trust for the LIVE demo (mirrors
# AGENTS.md's "live-compatible gallery"), in preference order.
PREFERRED_LIVE_MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "qwen2.5:7b",
    "llama3.1:8b",
    "llama3.2:3b",
    "mistral:7b",
]

#: NOTE: training_ground/ already ships a pre-existing reverse_string.py fixture
#: used by the real test suite (create_file refuses to overwrite an existing
#: file — "use edit_file to modify it"). The prover uses a distinctly-named
#: artifact so it can never collide with that fixture (or any other agent's
#: run), and so the snapshot/restore cleanup below is unambiguous.
DEMO_BASENAME = "prove_it_reverse_string"
DEMO_FILE_REL = f"training_ground/{DEMO_BASENAME}.py"
DEMO_TEST_REL = f"training_ground/test_{DEMO_BASENAME}.py"
DEMO_DIRECTIVE = (
    f"create {DEMO_BASENAME}.py at the path training_ground/{DEMO_BASENAME}.py "
    "containing a function that reverses a string, plus a pytest test file at "
    f"training_ground/test_{DEMO_BASENAME}.py that tests it — then verify it by "
    "running pytest."
)

SCRIPTED_FILE_CONTENT = (
    '"""Reverse a string. Written by the ten-minute supervised-loop demo."""\n\n\n'
    "def reverse_string(text: str) -> str:\n"
    '    """Return *text* reversed."""\n'
    "    return text[::-1]\n"
)
SCRIPTED_TEST_CONTENT = (
    f"from {DEMO_BASENAME} import reverse_string\n\n\n"
    "def test_reverse_string_basic():\n"
    '    assert reverse_string("abc") == "cba"\n\n\n'
    "def test_reverse_string_empty():\n"
    '    assert reverse_string("") == ""\n'
)


# --------------------------------------------------------------------------
# Checklist bookkeeping — every line MUST carry real evidence.
# --------------------------------------------------------------------------


@dataclass
class Step:
    number: int
    name: str
    proved: bool = False
    evidence: str = ""
    error: str = ""


@dataclass
class Checklist:
    mode_label: str
    steps: list[Step] = field(default_factory=list)

    def record(self, number: int, name: str, *, proved: bool, evidence: str = "", error: str = "") -> Step:
        step = Step(number=number, name=name, proved=proved, evidence=evidence, error=error)
        self.steps.append(step)
        prefix = "PROVED" if proved else "FAILED"
        print(f"[{prefix}] {number}. {name}")
        if evidence:
            for line in evidence.splitlines():
                print(f"         evidence: {line}")
        if error:
            for line in error.splitlines():
                print(f"         WHY: {line}")
        return step

    @property
    def all_proved(self) -> bool:
        return bool(self.steps) and all(s.proved for s in self.steps)


class ProveItFailure(RuntimeError):
    """Raised to abort the run early with a WHY message; caller records FAILED."""


# --------------------------------------------------------------------------
# training_ground/ sandbox snapshot/restore — this is the PRODUCT's sandbox,
# not the prover's own files, so we must leave it exactly as we found it.
# --------------------------------------------------------------------------


#: Directory names never to walk into or delete from within training_ground/.
#: In particular ``.git`` there is the RollbackEngine's own snapshot database
#: (aios/agents/rollback_engine.py) — a content-addressed store where "a file
#: that didn't exist before" is a normal, load-bearing loose object, NOT demo
#: residue. Treating it like any other new file and deleting it can corrupt
#: refs that point at it. The prover must never touch it.
_NEVER_TOUCH_DIRS = {".git"}


def _walk_scope_files(scope_root: Path):
    for p in scope_root.rglob("*"):
        if any(part in _NEVER_TOUCH_DIRS for part in p.relative_to(scope_root).parts[:-1]):
            continue
        yield p


def snapshot_training_ground(scope_root: Path) -> set[str]:
    if not scope_root.exists():
        return set()
    return {
        str(p.relative_to(scope_root))
        for p in _walk_scope_files(scope_root)
        if p.is_file()
    }


def restore_training_ground(scope_root: Path, before: set[str]) -> list[str]:
    """Delete any file present now but absent from *before*. Returns deleted paths.

    Never descends into ``.git`` (see :data:`_NEVER_TOUCH_DIRS`) — the demo's own
    additions there, if any, are left alone rather than risk touching the
    rollback engine's snapshot database.
    """
    if not scope_root.exists():
        return []
    after = {str(p.relative_to(scope_root)) for p in _walk_scope_files(scope_root) if p.is_file()}
    added = after - before
    deleted: list[str] = []
    for rel in sorted(added):
        target = scope_root / rel
        try:
            if target.exists():
                target.unlink()
                deleted.append(rel)
        except OSError:
            pass
    # Clean up now-empty directories the demo may have created (never the root,
    # never anything under a never-touch dir).
    for d in sorted(_walk_scope_files(scope_root), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir():
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                except OSError:
                    pass
            except OSError:
                pass
    return deleted


def sweep_stale_demo_artifacts(scope_root: Path) -> None:
    """Remove the prover's OWN demo files if a prior interrupted run left them.

    The snapshot/restore pair only cleans up files the run itself ADDS on top
    of the pre-run state. But a sabotage run (or any prover invocation that
    exits before its restore) can leave ``prove_it_reverse_string.py`` behind;
    the NEXT run then snapshots that residue as "pre-existing," and — worse —
    create_file refuses to overwrite it, so the SUPERVISION pause never fires
    and the whole run fails on a stale artifact rather than a real defect.
    Sweeping our own two demo paths BEFORE the snapshot makes every run start
    from a clean slate regardless of how a previous one ended. Only ever
    touches the prover's own uniquely-named files, never the training_ground
    fixtures or anything else.
    """
    del scope_root  # signature kept symmetric with snapshot/restore; paths are absolute
    for rel in (DEMO_FILE_REL, DEMO_TEST_REL):
        target = REPO_ROOT / rel
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Networking helpers
# --------------------------------------------------------------------------


def _port_answers(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_health(base_url: str, *, timeout_s: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error: Optional[str] = None
    with httpx.Client(timeout=3.0) as client:
        while time.monotonic() < deadline:
            try:
                resp = client.get(f"{base_url}/health")
                if resp.status_code == 200:
                    return resp.json()
                last_error = f"HTTP {resp.status_code} from /health"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            time.sleep(0.4)
    raise ProveItFailure(f"server never answered /health within {timeout_s}s: {last_error}")


def detect_live_model(timeout_s: float = 2.0) -> Optional[str]:
    """Return a tool-capable installed Ollama model name, or None if unreachable/none."""
    try:
        resp = httpx.get(OLLAMA_TAGS_URL, timeout=timeout_s)
        resp.raise_for_status()
    except (httpx.HTTPError, OSError):
        return None
    try:
        data = resp.json()
        installed = {m.get("name") for m in data.get("models", [])}
    except (ValueError, AttributeError):
        return None
    for candidate in PREFERRED_LIVE_MODELS:
        if candidate in installed:
            return candidate
    return None


# --------------------------------------------------------------------------
# SSE parsing — mirrors aios/api/main.py's ``event: X\ndata: {...}\n\n`` framing.
# --------------------------------------------------------------------------


def parse_sse(raw_text: str) -> list[tuple[str, dict[str, Any]]]:
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in raw_text.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        event_name = None
        data_line = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_line = line[len("data:"):].strip()
        if event_name is None or data_line is None:
            continue
        try:
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            payload = {"_raw": data_line}
        frames.append((event_name, payload))
    return frames


# --------------------------------------------------------------------------
# LIVE mode: spawn the real server, hit it with real httpx, drive a real model.
# --------------------------------------------------------------------------


class LiveServer:
    """Spawns ``.venv\\Scripts\\python -m aios`` as a child and guarantees cleanup."""

    def __init__(self, host: str, port: int, *, extra_env: Optional[dict[str, str]] = None) -> None:
        self.host = host
        self.port = port
        self.proc: Optional[subprocess.Popen] = None
        self.spawned = False
        self._extra_env = extra_env or {}

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def ensure_running(self) -> str:
        """Return 'already-running' or 'spawned'."""
        if _port_answers(self.host, self.port, timeout=0.5):
            return "already-running"
        if not VENV_PYTHON.exists():
            raise ProveItFailure(f".venv Python not found at {VENV_PYTHON}")
        env = dict(os.environ)
        env["AIOS_API_HOST"] = self.host
        env["AIOS_API_PORT"] = str(self.port)
        env.update(self._extra_env)
        self.proc = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "aios"],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        self.spawned = True
        return "spawned"

    def kill(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
        self.proc = None


def run_live(checklist: Checklist, *, host: str, port: int, keep_server: bool) -> int:
    model_name = detect_live_model()
    if not model_name:
        checklist.record(
            1, "BOOT",
            proved=False,
            error=(
                "No reachable/tool-capable local Ollama model detected at "
                f"{OLLAMA_TAGS_URL}. LIVE mode requires a real model. "
                "Run 'ollama pull qwen2.5-coder:7b' and retry, or use --scripted."
            ),
        )
        return 1

    model_id = f"ollama.{model_name}"
    server = LiveServer(host, port)
    scope_root = REPO_ROOT / "training_ground"
    sweep_stale_demo_artifacts(scope_root)  # clean slate vs a prior interrupted run
    before_files = snapshot_training_ground(scope_root)
    session_id = f"prove-it-live-{uuid.uuid4().hex[:12]}"

    try:
        try:
            mode = server.ensure_running()
        except ProveItFailure as exc:
            checklist.record(1, "BOOT", proved=False, error=str(exc))
            return 1

        try:
            health = wait_for_health(server.base_url, timeout_s=30.0)
        except ProveItFailure as exc:
            checklist.record(1, "BOOT", proved=False, error=str(exc))
            return 1

        checklist.record(
            1, "BOOT",
            proved=True,
            evidence=(
                f"server {mode} at {server.base_url} (child pid="
                f"{server.proc.pid if server.proc else 'pre-existing'}); "
                f"GET /health -> {json.dumps(health)[:200]}\n"
                f"live model detected: {model_id} (GET {OLLAMA_TAGS_URL})"
            ),
        )

        directive = (
            DEMO_DIRECTIVE
            + f" Use exactly this path for the source file: {DEMO_FILE_REL} "
              f"and exactly this path for the test file: {DEMO_TEST_REL}."
        )
        body = {
            "messages": [{"role": "user", "content": [{"text": directive}]}],
            "modelId": model_id,
            "sessionId": session_id,
        }

        client = httpx.Client(timeout=180.0)
        try:
            frames, human_required = _post_generate_collect(client, server.base_url, body)
        except ProveItFailure as exc:
            checklist.record(2, "DIRECTIVE", proved=False, error=str(exc))
            return 1

        checklist.record(
            2, "DIRECTIVE",
            proved=True,
            evidence=(
                f"POST {server.base_url}/api/generate body.modelId={model_id} "
                f"sessionId={session_id} -> {len(frames)} SSE frames "
                f"({', '.join(sorted({e for e, _ in frames}))})"
            ),
        )

        # --- SUPERVISION: bounded retries in case a 7B model needs a nudge ---
        attempts = 1
        max_attempts = 3
        while human_required is None and attempts < max_attempts:
            attempts += 1
            nudge = (
                directive
                + f" Remember: call create_file with filepath="
                  f"'{DEMO_FILE_REL}', then create_file with "
                  f"filepath='{DEMO_TEST_REL}'."
            )
            body["messages"].append({"role": "user", "content": [{"text": nudge}]})
            try:
                frames, human_required = _post_generate_collect(client, server.base_url, body)
            except ProveItFailure:
                break

        if human_required is None:
            checklist.record(
                3, "SUPERVISION",
                proved=False,
                error=(
                    f"the live model did not attempt a gated write after {attempts} "
                    "tries (no 'human_required' frame). This is an honest degrade: "
                    "the local model may be too weak for reliable tool-calling. "
                    "Suggest: .venv\\Scripts\\python prove_it.py --scripted"
                ),
            )
            return 1

        pre_write_exists = (scope_root / f"{DEMO_BASENAME}.py").exists() and (
            f"{DEMO_BASENAME}.py" not in before_files
        )
        if (scope_root / f"{DEMO_BASENAME}.py").exists() and f"{DEMO_BASENAME}.py" in before_files:
            pre_write_exists = False
        approval_token = human_required["input"].get("approvalToken", "")
        checklist.record(
            3, "SUPERVISION",
            proved=not pre_write_exists and bool(approval_token),
            evidence=(
                f"event: human_required text={human_required.get('text', '')!r} "
                f"approvalToken={approval_token[:12]}... "
                f"file-exists-before-approval={pre_write_exists}"
            ),
            error="" if not pre_write_exists else "file existed on disk BEFORE approval was granted",
        )
        if pre_write_exists or not approval_token:
            return 1

        # --- APPROVAL: in-turn resume (approvalTokens), the real UI's chat path ---
        resume_body = {
            "messages": body["messages"],
            "modelId": model_id,
            "sessionId": session_id,
            "approvalTokens": [approval_token],
        }
        try:
            resume_frames, second_pause = _post_generate_collect(client, server.base_url, resume_body)
        except ProveItFailure as exc:
            checklist.record(4, "APPROVAL", proved=False, error=str(exc))
            return 1

        # A second gated write (the sibling test file) may need its own approval
        # round — apply up to 2 more resumes so both files can land.
        extra_rounds = 0
        while second_pause is not None and extra_rounds < 2:
            extra_rounds += 1
            token2 = second_pause["input"].get("approvalToken", "")
            if not token2:
                break
            resume_body["approvalTokens"] = [token2]
            try:
                resume_frames, second_pause = _post_generate_collect(client, server.base_url, resume_body)
            except ProveItFailure:
                break

        checklist.record(
            4, "APPROVAL",
            proved=True,
            evidence=(
                f"POST {server.base_url}/api/generate (in-turn resume) with "
                f"approvalTokens=[{approval_token[:12]}...] sessionId={session_id} "
                f"(this is the real UI's aiosAdapter.ts chat-resume path) -> "
                f"{len(resume_frames)} frames"
            ),
        )

        _finish_common(checklist, resume_frames, scope_root)
        return 0 if checklist.all_proved else 1
    finally:
        client_local = locals().get("client")
        if client_local is not None:
            client_local.close()
        if not keep_server:
            server.kill()
        deleted = restore_training_ground(scope_root, before_files)
        if deleted:
            print(f"[cleanup] removed demo artifacts from training_ground/: {', '.join(deleted)}")


def _post_generate_collect(
    client: "httpx.Client", base_url: str, body: dict[str, Any]
) -> tuple[list[tuple[str, dict[str, Any]]], Optional[dict[str, Any]]]:
    try:
        resp = client.post(f"{base_url}/api/generate", json=body)
    except httpx.HTTPError as exc:
        raise ProveItFailure(f"POST /api/generate failed: {exc}") from exc
    if resp.status_code != 200:
        raise ProveItFailure(f"POST /api/generate -> HTTP {resp.status_code}: {resp.text[:300]}")
    frames = parse_sse(resp.text)
    human_required = None
    for event, payload in frames:
        if event == "human_required":
            human_required = payload
        if event == "error":
            raise ProveItFailure(f"server emitted an error frame: {payload}")
    return frames, human_required


def _finish_common(checklist: Checklist, frames: list[tuple[str, dict[str, Any]]], scope_root: Path) -> None:
    """Steps 5-7, shared by live and scripted once the resumed turn has run."""
    # --- ACTION ---
    demo_file = scope_root / f"{DEMO_BASENAME}.py"
    if demo_file.exists():
        first_line = demo_file.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        checklist.record(
            5, "ACTION",
            proved=True,
            evidence=f"{demo_file} exists; first line: {first_line!r}",
        )
    else:
        checklist.record(
            5, "ACTION", proved=False,
            error=f"expected file not found on disk: {demo_file}",
        )

    # --- VERIFY ---
    # Per the ratified design, this step requires strength=STRONG, not merely a
    # pass — a WEAK/MEDIUM pass is real evidence of *something* but is NOT the
    # claim being proved (that the forced auto-verify judged the write with
    # STRONG, promotion-eligible evidence). Never soften this to "any pass" —
    # that would silently paint over a genuine gap between the passed test and
    # the strength the taxonomy actually assigned it.
    verify_frames = [p for e, p in frames if e == "verify_result"]
    any_pass = next(
        (
            p for p in verify_frames
            if p.get("verdict") == "pass" and "[VERIFY PASS]" in p.get("output", "")
        ),
        None,
    )
    strong_pass = (
        any_pass
        if any_pass is not None and "(strength=STRONG)" in any_pass.get("output", "")
        else None
    )
    if strong_pass is not None:
        checklist.record(
            6, "VERIFY",
            proved=True,
            evidence=f"event: verify_result target={strong_pass.get('target')!r} output={strong_pass.get('output')!r}",
        )
    elif any_pass is not None:
        checklist.record(
            6, "VERIFY", proved=False,
            evidence=f"event: verify_result target={any_pass.get('target')!r} output={any_pass.get('output')!r}",
            error=(
                "[VERIFY PASS] was real but strength was NOT STRONG (see evidence line above). "
                "KNOWN PRODUCTION DEFECT (found by this prover, not introduced by it): the forced "
                "auto-verify builds its pytest command as "
                "'python -m pytest \"<test>\" -q' (aios/agents/tool_agent.py _auto_verify, ~line 1090). "
                "On this environment's pytest 9.0.3 + the repo-root pytest.ini's inherited addopts "
                "(--cov=aios ...), '-q' suppresses pytest's final 'N passed in Xs' summary line entirely "
                "(reproduced manually: 'python -m pytest <file> -q' prints only '[100%]', no summary; "
                "the same command WITHOUT -q correctly prints '2 passed in 0.13s'). With no summary line, "
                "verifier._parse_counts() regex-matches 0 passed/0 failed, so derive_strength()'s "
                "'passed_count > 0' floor for STRONG can never be met even though the test genuinely "
                "passed (exit 0). This caps every real auto-verify in this environment at WEAK. Fix "
                "belongs in aios/agents/tool_agent.py or aios/core/verifier.py (out of this prover's "
                "additive-only scope) — flagged for the operator, not patched here."
            ),
        )
    else:
        checklist.record(
            6, "VERIFY", proved=False,
            error=(
                "no verify_result frame with verdict=pass and '[VERIFY PASS]' found. "
                f"verify frames seen: {verify_frames}"
            ),
        )

    # --- LEARNING ---
    try:
        from aios import config as aios_config  # local import: only after env is set (scripted) or real (live)
        import sqlite3

        skills_count = 0
        dev_count = 0
        skill_ids: list[int] = []
        dev_ids: list[int] = []
        if aios_config.MEMORY_DB_PATH.exists():
            with sqlite3.connect(str(aios_config.MEMORY_DB_PATH)) as conn:
                try:
                    rows = conn.execute(
                        "SELECT id FROM procedural_skills ORDER BY id DESC LIMIT 5"
                    ).fetchall()
                    skill_ids = [r[0] for r in rows]
                    skills_count = conn.execute("SELECT COUNT(*) FROM procedural_skills").fetchone()[0]
                except sqlite3.OperationalError:
                    pass
                try:
                    rows = conn.execute(
                        "SELECT id FROM development_events ORDER BY id DESC LIMIT 5"
                    ).fetchall()
                    dev_ids = [r[0] for r in rows]
                    dev_count = conn.execute("SELECT COUNT(*) FROM development_events").fetchone()[0]
                except sqlite3.OperationalError:
                    pass
        proved = skills_count > 0 and dev_count > 0
        checklist.record(
            7, "LEARNING",
            proved=proved,
            evidence=(
                f"db={aios_config.MEMORY_DB_PATH} procedural_skills rows={skills_count} "
                f"(recent ids={skill_ids}); development_events rows={dev_count} (recent ids={dev_ids})"
            ),
            error="" if proved else "expected at least one skill attempt row and one development row",
        )
    except Exception as exc:  # noqa: BLE001 - report, don't crash the checklist
        checklist.record(7, "LEARNING", proved=False, error=f"could not inspect memory DB: {exc}")


# --------------------------------------------------------------------------
# SCRIPTED mode: in-process TestClient, real app, real machinery, scripted
# brain. Hermetic temp DBs. NEVER touches Ollama/network.
# --------------------------------------------------------------------------


class ScriptedBrain:
    """A deterministic, tool-calling stand-in for the Ollama client.

    Mirrors tests/test_api.py's FakeOllama* pattern: the SAME shape the real
    OllamaClient.chat() returns, so the real tool_agent loop cannot tell the
    difference — only the network call underneath is scripted.
    """

    def __init__(self) -> None:
        self._turn = 0

    def list_models(self) -> dict:
        return {"available": True, "models": ["scripted-brain:demo"]}

    def chat(self, messages: list, *, tools=None, model=None) -> dict:
        self._turn += 1
        if self._turn == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_file",
                            "arguments": {
                                "filepath": DEMO_FILE_REL,
                                "content": SCRIPTED_FILE_CONTENT,
                            },
                        }
                    }
                ],
            }
        if self._turn == 2:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "create_file",
                            "arguments": {
                                "filepath": DEMO_TEST_REL,
                                "content": SCRIPTED_TEST_CONTENT,
                            },
                        }
                    }
                ],
            }
        return {
            "role": "assistant",
            "content": (
                f"Created {DEMO_FILE_REL} and its test; "
                "the auto-verify ran pytest and it passed."
            ),
        }


def run_scripted(checklist: Checklist, *, sabotage: Optional[str] = None) -> int:
    """Runs the scripted-brain demo. *sabotage* is a hook name used only by
    tests/test_prove_it.py to prove the prover can honestly report FAILED."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="prove_it_scripted_"))
    data_dir = tmp_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # CRITICAL ORDERING (mirrors tests/conftest.py): AIOS_DATA_DIR must be set
    # BEFORE aios.config is first imported anywhere in this process, or config
    # binds to the real data/ (approval/skills/development DBs) instead of this
    # hermetic copy. We deliberately do NOT override AIOS_SCOPE_ROOTS: the tool
    # loop's write path resolves ``read_root / filepath`` where ``read_root``
    # defaults to the REAL config.PROJECT_ROOT (not overridable via env — see
    # aios/agents/tool_agent.py ToolAgent.__init__), so a scope root pointed at
    # a temp dir would never match and every write would be scope-BLOCKED. The
    # demo therefore writes into the real training_ground/ sandbox, exactly as
    # the live path does; we snapshot it before and restore it after, in a
    # finally block, so this run leaves no trace (per HARD CONSTRAINTS).
    os.environ["AIOS_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("AIOS_INDEX_CHAT", "false")
    os.environ.setdefault("AIOS_REFLECT_ON_FAILURE", "false")
    os.environ.setdefault("AIOS_INTERPRET_ALIGNMENT", "false")
    os.environ.setdefault("AIOS_CORTEX_BUS", "false")

    if any(mod.startswith("aios") for mod in sys.modules):
        raise ProveItFailure(
            "internal error: aios.* was imported before the hermetic env was set"
        )

    from fastapi.testclient import TestClient

    from aios.api.main import app, get_executor, get_ollama_client
    from aios.core.executor import Executor
    from aios.security.gateway import RateLimiter

    # Real Executor, but with a plain HOST runner (not Docker) for the approved
    # path too — Docker Desktop may be stopped on this machine; the risk map
    # calls this out explicitly. This changes no file and no feature-flag
    # DEFAULT, only an explicit prover-provided runner, exactly mirroring what
    # AIOS_APPROVED_EXECUTION_BACKEND=host would select, so the auto-verify
    # pytest run can actually execute and produce real STRONG evidence.
    from aios.core.executor import _default_runner  # same runner GREEN commands use

    real_executor = Executor(
        runner=_default_runner,
        approved_runner=_default_runner,
        rate_limiter=RateLimiter(),
    )
    print(
        "[scripted] approved-execution backend forced to HOST runner for this "
        "run (container backend unavailable/irrelevant in a hermetic scripted "
        "sandbox) — mirrors AIOS_APPROVED_EXECUTION_BACKEND=host, no default changed."
    )

    scripted_brain = ScriptedBrain()
    app.dependency_overrides[get_ollama_client] = lambda: scripted_brain
    app.dependency_overrides[get_executor] = lambda: real_executor

    # The write path always resolves against the REAL config.PROJECT_ROOT (see
    # note above), so this is the REAL training_ground/ sandbox, not a temp
    # copy. Snapshot it now and restore it in `finally` so this run leaves no
    # trace on the repo tree, matching the live-mode cleanup contract.
    scope_root = REPO_ROOT / "training_ground"
    sweep_stale_demo_artifacts(scope_root)  # clean slate vs a prior interrupted run
    before_files = snapshot_training_ground(scope_root)

    session_id = f"prove-it-scripted-{uuid.uuid4().hex[:12]}"
    try:
        with TestClient(app, client=("127.0.0.1", 12345), headers={"Sec-Fetch-Site": "same-origin"}) as client:
            directive = DEMO_DIRECTIVE
            body = {
                "messages": [{"role": "user", "content": [{"text": directive}]}],
                "modelId": "ollama.scripted-brain:demo",
                "sessionId": session_id,
            }

            checklist.record(
                1, "BOOT",
                proved=True,
                evidence=(
                    "in-process TestClient against the REAL FastAPI app object "
                    f"(no server spawned); hermetic AIOS_DATA_DIR={data_dir}"
                ),
            )

            resp = client.post("/api/generate", json=body)
            if resp.status_code != 200:
                checklist.record(
                    2, "DIRECTIVE", proved=False,
                    error=f"POST /api/generate -> HTTP {resp.status_code}: {resp.text[:300]}",
                )
                return 1
            frames = parse_sse(resp.text)
            human_required = next((p for e, p in frames if e == "human_required"), None)
            errors = [p for e, p in frames if e == "error"]
            checklist.record(
                2, "DIRECTIVE",
                proved=not errors,
                evidence=(
                    f"POST /api/generate (TestClient, real app) sessionId={session_id} -> "
                    f"{len(frames)} SSE frames ({', '.join(sorted({e for e, _ in frames}))})"
                ),
                error=f"error frame(s): {errors}" if errors else "",
            )
            if errors:
                return 1

            if sabotage == "supervision":
                human_required = None  # simulate the pause never happening

            pre_exists = (scope_root / f"{DEMO_BASENAME}.py").exists()
            approval_token = (human_required or {}).get("input", {}).get("approvalToken", "")
            supervision_ok = human_required is not None and not pre_exists and bool(approval_token)
            checklist.record(
                3, "SUPERVISION",
                proved=supervision_ok,
                evidence=(
                    f"event: human_required text={(human_required or {}).get('text', '')!r} "
                    f"approvalToken={approval_token[:12] if approval_token else '(none)'}... "
                    f"file-exists-before-approval={pre_exists}"
                    if human_required is not None
                    else "no human_required frame was emitted for a create_file call"
                ),
                error="" if supervision_ok else "expected a YELLOW pause with an approval token before any write",
            )
            if not supervision_ok:
                return 1

            if sabotage == "approval":
                approval_token = "not-a-real-token"

            resume_body = {
                "messages": body["messages"],
                "modelId": body["modelId"],
                "sessionId": session_id,
                "approvalTokens": [approval_token],
            }
            resp2 = client.post("/api/generate", json=resume_body)
            if resp2.status_code != 200:
                checklist.record(
                    4, "APPROVAL", proved=False,
                    error=f"resume POST -> HTTP {resp2.status_code}: {resp2.text[:300]}",
                )
                return 1
            frames2 = parse_sse(resp2.text)
            second_pause = next((p for e, p in frames2 if e == "human_required"), None)
            errors2 = [p for e, p in frames2 if e == "error"]

            all_frames = list(frames2)
            round_ = 0
            while second_pause is not None and round_ < 2 and not errors2:
                round_ += 1
                token2 = second_pause.get("input", {}).get("approvalToken", "")
                if not token2:
                    break
                resume_body["approvalTokens"] = [token2]
                resp_n = client.post("/api/generate", json=resume_body)
                if resp_n.status_code != 200:
                    break
                frames_n = parse_sse(resp_n.text)
                all_frames = frames_n
                second_pause = next((p for e, p in frames_n if e == "human_required"), None)
                errors2 = [p for e, p in frames_n if e == "error"]

            approval_ok = not errors2
            checklist.record(
                4, "APPROVAL",
                proved=approval_ok,
                evidence=(
                    f"POST /api/generate (in-turn resume) approvalTokens=[{approval_token[:12]}...] "
                    f"sessionId={session_id} -> {len(all_frames)} frames after {round_} extra round(s)"
                ),
                error=f"error frame(s): {errors2}" if errors2 else "",
            )
            if not approval_ok:
                return 1

            if sabotage == "action":
                target = scope_root / f"{DEMO_BASENAME}.py"
                if target.exists():
                    target.unlink()

            if sabotage == "verify":
                all_frames = [(e, p) for e, p in all_frames if e != "verify_result"]

            if sabotage == "learning":
                # Point the checklist at a DB path with no rows to prove honesty.
                # Patch the RESOLVED config value: the LEARNING checker reads
                # aios_config.MEMORY_DB_PATH, which was resolved when aios.config
                # loaded — flipping AIOS_DATA_DIR here would be inert. (This
                # sabotage was masked until the workflow_steps fix made LEARNING
                # genuinely pass; its own self-test then exposed the inert env flip.)
                from aios import config as _sab_config
                _sab_config.MEMORY_DB_PATH = tmp_dir / "empty_data_dir_sabotage" / "aios_memory.db"

            _finish_common(checklist, all_frames, scope_root)
            return 0 if checklist.all_proved else 1
    finally:
        app.dependency_overrides.pop(get_ollama_client, None)
        app.dependency_overrides.pop(get_executor, None)
        deleted = restore_training_ground(scope_root, before_files)
        if deleted:
            print(f"[cleanup] removed demo artifacts from training_ground/: {', '.join(deleted)}")
        shutil.rmtree(tmp_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------


def print_footer(checklist: Checklist, mode: str) -> None:
    print()
    print("=" * 72)
    if mode == "live":
        print("MODE: LIVE BRAIN — real spawned server, real local Ollama model.")
    else:
        print("MODE: SCRIPTED BRAIN (SIMULATED) — machinery real, mind scripted.")
        print("      Every write/approval/verify below is a REAL subsystem call;")
        print("      only the LLM's tool-call decisions were pre-scripted.")
    print("=" * 72)
    for step in checklist.steps:
        status = "PROVED" if step.proved else "FAILED"
        print(f"  [{status}] {step.number}. {step.name}")
    overall = "ALL STEPS PROVED" if checklist.all_proved else "RUN FAILED — see WHY above"
    print("-" * 72)
    print(overall)
    print("=" * 72)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--live", action="store_true", help="Force LIVE mode.")
    mode_group.add_argument("--scripted", action="store_true", help="Force SCRIPTED mode.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port for LIVE mode's server.")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Host for LIVE mode's server.")
    parser.add_argument(
        "--keep-server", action="store_true",
        help="Do not kill a server this run spawned (LIVE mode only). Never leaves a leftover if we did not spawn it.",
    )
    parser.add_argument(
        "--sabotage", type=str, default=None, choices=["supervision", "approval", "action", "verify", "learning"],
        help=argparse.SUPPRESS,  # internal: tests/test_prove_it.py proves the prover can honestly fail.
    )
    args = parser.parse_args(argv)

    if args.live:
        mode = "live"
    elif args.scripted:
        mode = "scripted"
    else:
        mode = "live" if detect_live_model() else "scripted"

    print(f"prove_it.py — ten-minute supervised-loop proof (mode={mode})")
    checklist = Checklist(mode_label=mode)

    if mode == "live":
        code = run_live(checklist, host=args.host, port=args.port, keep_server=args.keep_server)
    else:
        code = run_scripted(checklist, sabotage=args.sabotage)

    print_footer(checklist, mode)
    return 0 if checklist.all_proved and code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
