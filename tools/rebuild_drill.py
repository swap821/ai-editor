"""Rebuild drill: recover GAGOS on this laptop from GitHub + a data backup, timing each step.

Follows README "Quick Start" as written. Records every step's command, exit
code, duration and output tail to drill.json; stops at the first failing
REQUIRED step (and says so) rather than papering over it.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DRILL = Path(sys.argv[1])  # e.g. C:/drill (must not exist)
LIVE = Path(sys.argv[2])  # the operator's main checkout (data source)
REPO_URL = "https://github.com/swap821/ai-editor.git"
PORT = "8010"
results = []
started = time.time()


def step(name, cmd, cwd, *, env=None, required=True, timeout=3600, shell=False):
    t0 = time.time()
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
            encoding="utf-8",
            errors="replace",
        )
        code, out = r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired as exc:
        code, out = "timeout", str(exc)
    except OSError as exc:
        code, out = "oserror", str(exc)
    rec = {
        "step": name,
        "cmd": cmd if isinstance(cmd, str) else " ".join(map(str, cmd)),
        "exit": code,
        "seconds": round(time.time() - t0, 1),
        "tail": out[-1500:],
    }
    results.append(rec)
    (DRILL / "drill.json").write_text(
        json.dumps({"results": results}, indent=2), encoding="utf-8"
    )
    print(f"[{rec['seconds']:>7}s] {name}: exit {code}", flush=True)
    if required and code != 0:
        raise SystemExit(f"REQUIRED STEP FAILED: {name}")
    return rec


DRILL.mkdir(parents=False, exist_ok=False)
clone = DRILL / "ai-editor"
backup = DRILL / "gagos-data-backup.tar.gz"
live_py = sys.executable

try:
    # 1. backup of the live data (read-only snapshot; the live checkout's own venv/python)
    step(
        "backup create (live data)",
        [live_py, "-m", "aios", "backup", "create", "--output", str(backup)],
        LIVE,
    )
    step(
        "backup verify",
        [live_py, "-m", "aios", "backup", "verify", "--input", str(backup)],
        LIVE,
        required=False,
    )

    # 2. clone
    step("git clone", ["git", "clone", "--quiet", REPO_URL, str(clone)], DRILL)

    # 3. venv + install (README: py -3 -m venv .venv; pip install -e ".[test]")
    step("venv (py -3)", ["py", "-3", "-m", "venv", ".venv"], clone)
    vpy = clone / ".venv" / "Scripts" / "python.exe"
    step(
        "pip upgrade",
        [str(vpy), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        clone,
    )
    step(
        "pip install -e .[test]",
        [str(vpy), "-m", "pip", "install", "--quiet", "-e", ".[test]"],
        clone,
        timeout=5400,
    )

    # 4. .env with the one required value (README step 3)
    shutil.copy(clone / ".env.example", clone / ".env")
    with (clone / ".env").open("a", encoding="utf-8") as fh:
        fh.write(f"\nAIOS_VERIFICATION_AUTHORITY_KEY={secrets.token_hex(32)}\n")
    results.append(
        {
            "step": ".env from .env.example + generated AIOS_VERIFICATION_AUTHORITY_KEY",
            "exit": 0,
            "seconds": 0,
        }
    )

    # 5. restore the backup into the clone's data dir
    env = dict(os.environ, AIOS_API_PORT=PORT)
    env.pop("AIOS_ROUTER_CLOUD_TASKS", None)
    step(
        "backup restore (into clone)",
        [str(vpy), "-m", "aios", "backup", "restore", "--input", str(backup)],
        clone,
        env=env,
    )

    # 6. doctor + backend + health
    step(
        "doctor",
        [str(vpy), "-m", "aios", "doctor", "--json"],
        clone,
        env=env,
        required=False,
        timeout=600,
    )
    log = (DRILL / "backend.log").open("w", encoding="utf-8")
    backend = subprocess.Popen(
        [str(vpy), "-m", "aios"],
        cwd=str(clone),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=0x00000200,
    )
    t0, health = time.time(), None
    while time.time() - t0 < 240:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/health", timeout=5
            ) as resp:
                health = (resp.status, resp.read(400).decode("utf-8", "replace"))
                break
        except Exception:
            time.sleep(3)
    results.append(
        {
            "step": "backend /health",
            "exit": 0 if health and health[0] == 200 else 1,
            "seconds": round(time.time() - t0, 1),
            "tail": str(health),
        }
    )
    backend.terminate()
    try:
        backend.wait(timeout=20)
    except subprocess.TimeoutExpired:
        backend.kill()

    # restored memory matches the live one?
    import sqlite3

    def counts(db):
        c = sqlite3.connect(str(db))
        try:
            return {
                t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in (
                    "procedural_skills",
                    "mistake_pool",
                    "semantic_memory",
                    "compiled_playbooks",
                )
            }
        finally:
            c.close()

    live_counts = counts(LIVE / "data" / "aios_memory.db")
    clone_counts = counts(clone / "data" / "aios_memory.db")
    results.append(
        {
            "step": "restored memory == live memory",
            "exit": 0 if live_counts == clone_counts else 1,
            "seconds": 0,
            "tail": json.dumps({"live": live_counts, "restored": clone_counts}),
        }
    )

    # 7. frontend (README step 6, built rather than served)
    npm = shutil.which("npm") or "npm"
    step(
        "npm ci",
        f'"{npm}" ci --no-audit --no-fund',
        clone / "frontend",
        shell=True,
        required=False,
        timeout=2400,
    )
    step(
        "npm run build",
        f'"{npm}" run build',
        clone / "frontend",
        shell=True,
        required=False,
        timeout=2400,
    )
finally:
    total = round(time.time() - started, 1)
    (DRILL / "drill.json").write_text(
        json.dumps({"results": results, "total_seconds": total}, indent=2),
        encoding="utf-8",
    )
    print(f"TOTAL {total}s", flush=True)
