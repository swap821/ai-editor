"""Phase 1 -- the lap counter: observation-only run telemetry.

Records which dispatch path answered each request (playbook replay / native
plan / knowledge-graph / LLM fallback / refused-offline) and whether it was
verified, so the organism's central claim -- "superior every run" -- becomes
measurable instead of a vibe. Per the cortex-bus law this tier carries what
HAPPENED, never what is PERMITTED: :func:`record_run` never raises, so a
telemetry failure can never abort the request that triggered it.

Report: ``python -m aios.core.telemetry`` prints the sovereign hit-rate,
verified-success rate per path, cost per verified success, and the session-by-
session hit-rate curve.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

from aios import config
from aios.logging_config import get_logger
from aios.memory.db import get_connection

logger = get_logger(__name__)

DISPATCH_PLAYBOOK = "playbook"
DISPATCH_NATIVE_PLAN = "native_plan"
DISPATCH_KG = "kg"
DISPATCH_LLM = "llm"
DISPATCH_REFUSED_OFFLINE = "refused_offline"

OUTCOME_PASS = "pass"
OUTCOME_FAIL = "fail"
OUTCOME_UNVERIFIED = "unverified"
OUTCOME_ABORTED = "aborted"

_DECIDED_OUTCOMES = frozenset({OUTCOME_PASS, OUTCOME_FAIL})

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS run_telemetry (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  session_id TEXT,
  task_signature TEXT,
  dispatch_path TEXT NOT NULL CHECK (dispatch_path IN
    ('playbook','native_plan','kg','llm','refused_offline')),
  provider TEXT,
  model TEXT,
  verified_outcome TEXT CHECK (verified_outcome IN
    ('pass','fail','unverified','aborted')),
  latency_ms INTEGER,
  tokens_in INTEGER,
  tokens_out INTEGER,
  max_zone TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_telemetry_session ON run_telemetry(session_id);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)


def record_run(
    *,
    session_id: Optional[str],
    task_signature: Optional[str],
    dispatch_path: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    verified_outcome: Optional[str] = None,
    latency_ms: Optional[int] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    max_zone: Optional[str] = None,
    db_path: Path = config.MEMORY_DB_PATH,
) -> None:
    """Insert one telemetry row. Fail-open: never raises, logs and returns.

    A malformed *dispatch_path*/*verified_outcome* (violating the table's
    CHECK constraints) or an unreachable *db_path* both fail this write only
    -- the caller's request is never aborted by a telemetry defect.
    """
    try:
        with get_connection(db_path) as conn:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO run_telemetry (ts, session_id, task_signature,"
                " dispatch_path, provider, model, verified_outcome, latency_ms,"
                " tokens_in, tokens_out, max_zone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    session_id, task_signature, dispatch_path, provider, model,
                    verified_outcome, latency_ms, tokens_in, tokens_out, max_zone,
                ),
            )
    except Exception:  # noqa: BLE001 - observation must never break a request
        logger.warning("telemetry write failed; request continues", exc_info=True)


def fetch_rows(db_path: Path = config.MEMORY_DB_PATH) -> list[sqlite3.Row]:
    """All recorded rows, oldest first."""
    with get_connection(db_path) as conn:
        _ensure_schema(conn)
        return conn.execute("SELECT * FROM run_telemetry ORDER BY id").fetchall()


def sovereign_hit_rate(rows: Sequence[Mapping[str, object]]) -> float:
    """Fraction of *rows* NOT dispatched to the LLM fallback."""
    if not rows:
        return 0.0
    non_llm = sum(1 for r in rows if r["dispatch_path"] != DISPATCH_LLM)
    return non_llm / len(rows)


def verified_success_rate_by_path(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, float]:
    """Pass rate per dispatch path, among rows with a decided (pass/fail) outcome."""
    by_path: dict[str, list[Mapping[str, object]]] = {}
    for r in rows:
        by_path.setdefault(str(r["dispatch_path"]), []).append(r)
    result: dict[str, float] = {}
    for path, path_rows in by_path.items():
        decided = [r for r in path_rows if r.get("verified_outcome") in _DECIDED_OUTCOMES]
        if not decided:
            result[path] = 0.0
            continue
        passes = sum(1 for r in decided if r["verified_outcome"] == OUTCOME_PASS)
        result[path] = passes / len(decided)
    return result


def cost_per_verified_success(rows: Sequence[Mapping[str, object]]) -> float:
    """Tokens spent per verified success; Ollama rows contribute zero cost (free/local)."""
    passes = sum(1 for r in rows if r.get("verified_outcome") == OUTCOME_PASS)
    if passes == 0:
        return 0.0
    cost_tokens = sum(
        int(r.get("tokens_in") or 0) + int(r.get("tokens_out") or 0)
        for r in rows
        if r.get("provider") != "ollama"
    )
    return cost_tokens / passes


def hit_rate_by_session(
    rows: Sequence[Mapping[str, object]],
) -> list[tuple[str, float]]:
    """Sovereign hit-rate per session, in first-seen order -- the curve."""
    order: list[str] = []
    by_session: dict[str, list[Mapping[str, object]]] = {}
    for r in rows:
        sid = str(r.get("session_id") or "unknown")
        if sid not in by_session:
            order.append(sid)
            by_session[sid] = []
        by_session[sid].append(r)
    return [(sid, sovereign_hit_rate(by_session[sid])) for sid in order]


def print_report(rows: Sequence[Mapping[str, object]]) -> None:
    print(f"[telemetry] {len(rows)} runs recorded")
    print(f"  sovereign hit-rate: {sovereign_hit_rate(rows):.1%}")
    print("  verified-success rate by path:")
    for path, rate in sorted(verified_success_rate_by_path(rows).items()):
        print(f"    {path}: {rate:.1%}")
    print(f"  cost per verified success: {cost_per_verified_success(rows):.1f} tokens")
    print("  hit-rate curve (by session):")
    prev: Optional[float] = None
    for sid, rate in hit_rate_by_session(rows):
        trend = ""
        if prev is not None:
            trend = " (up)" if rate > prev else (" (down)" if rate < prev else " (flat)")
        print(f"    {sid}: {rate:.1%}{trend}")
        prev = rate


def main() -> int:
    rows = fetch_rows()
    if not rows:
        print("[telemetry] no runs recorded yet")
        return 0
    print_report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
