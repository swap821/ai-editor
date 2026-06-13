"""Watch the router's evidence calibration build as you work.

Reads the SAME `development_events` the cross-provider router calibrates on — the
verified per-(provider, model, task) outcomes — and prints a snapshot whenever it
changes. Read-only (a separate process from the backend; safe to run alongside it).

  .venv\\Scripts\\python tools\\watch_calibration.py            # live watch (loops)
  .venv\\Scripts\\python tools\\watch_calibration.py --once     # one snapshot, exit

Note: only VERIFIED outcomes calibrate (turns that run a check/auto-verify). A pure
chat turn records as `unverified` and never moves the per-model rate — that is the
router being conservative (it trusts evidence, not narration). A signature needs
>= MIN_ATTEMPTS (3, the router default) verified attempts before it goes ACTIVE and
actually re-ranks the route.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
import time

# Run from anywhere: put the repo root (this file's parent's parent) on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Import ONLY config (light: dotenv + paths) — not aios.memory, so the watcher
# never loads the embedding model. We read the SQLite DB directly, read-only.
from aios import config  # noqa: E402

MIN_ATTEMPTS = 3  # matches model_task_success_rates(min_attempts=3)
POLL_S = 4


def snapshot() -> tuple[dict, dict]:
    """Return (tally, outcomes): per-(provider,model,task) verified [succ,total] + outcome counts."""
    conn = sqlite3.connect(f"file:{config.MEMORY_DB_PATH}?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT outcome, metadata_json FROM development_events ORDER BY id DESC LIMIT 5000"
        ).fetchall()
    finally:
        conn.close()
    tally: dict[tuple[str, str, str], list[int]] = {}
    outcomes: dict[str, int] = {}
    for row in rows:
        o = str(row["outcome"])
        outcomes[o] = outcomes.get(o, 0) + 1
        if o not in ("verified_success", "verified_failure"):
            continue
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue
        p = str(meta.get("provider") or "").strip()
        m = str(meta.get("model") or "").strip()
        t = str(meta.get("task") or "").strip()
        if not (p and m and t):
            continue
        agg = tally.setdefault((p, m, t), [0, 0])
        agg[1] += 1
        if o == "verified_success":
            agg[0] += 1
    return tally, outcomes


def render(tally: dict, outcomes: dict) -> str:
    lines = ["[calib] router evidence (verified per provider/model/task):"]
    if not tally:
        lines.append("  (none yet — verified turns tag {provider, model, task}; chat-only turns stay 'unverified')")
    for (p, m, t), (s, n) in sorted(tally.items()):
        pct = round(100 * s / n) if n else 0
        flag = " ✓ ACTIVE (re-ranks the route)" if n >= MIN_ATTEMPTS else f" ({MIN_ATTEMPTS - n} more to activate)"
        lines.append(f"  {t} · {p}:{m} · {s}/{n} verified ({pct}%)" + flag)
    oc = ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())) or "none"
    lines.append(f"  events so far: {oc}")
    return "\n".join(lines)


def sig_of(tally: dict, outcomes: dict) -> str:
    return (
        json.dumps({f"{p}|{m}|{t}": v for (p, m, t), v in sorted(tally.items())})
        + "||"
        + json.dumps(outcomes, sort_keys=True)
    )


def main() -> None:
    once = "--once" in sys.argv
    last = None
    while True:
        try:
            tally, outcomes = snapshot()
        except Exception as exc:  # noqa: BLE001 - wait for the backend to create the DB
            msg = f"[calib] waiting for backend DB… ({str(exc)[:80]})"
            if msg != last:
                print(msg, flush=True)
                last = msg
            if once:
                return
            time.sleep(POLL_S)
            continue
        sig = sig_of(tally, outcomes)
        if sig != last:
            print(render(tally, outcomes), flush=True)
            last = sig
        if once:
            return
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
