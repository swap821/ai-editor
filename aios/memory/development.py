"""Development evidence and measurable behavioral progress.

The tracker records outcomes without pretending that an unverified answer was a
success. Only verification-backed outcomes may calibrate future planning.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance, signature
from aios.security.secret_scanner import scan_and_redact

_OUTCOMES = frozenset({"verified_success", "verified_failure", "unverified", "paused"})


@dataclass(frozen=True)
class OutcomeEvidence:
    """Historical verified outcomes relevant to a future task."""

    attempts: int
    success_rate: float
    relevance: float


class DevelopmentTracker:
    """Persist task outcomes and compute evidence-backed development metrics."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def record(
        self,
        task_text: str,
        outcome: str,
        *,
        tool_calls: int = 0,
        human_interventions: int = 0,
        blocked_actions: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Record one task outcome. Unknown outcomes are refused."""
        if outcome not in _OUTCOMES:
            raise ValueError(f"unsupported development outcome: {outcome}")
        task_text = scan_and_redact(task_text.strip()).scrubbed
        if not task_text:
            raise ValueError("development event requires task text")
        payload = scan_and_redact(
            json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True)
        ).scrubbed
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO development_events "
                "(task_text, task_signature, outcome, tool_calls, human_interventions, "
                "blocked_actions, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    task_text,
                    signature(task_text),
                    outcome,
                    max(int(tool_calls), 0),
                    max(int(human_interventions), 0),
                    max(int(blocked_actions), 0),
                    payload,
                ),
            )
            return int(cur.lastrowid)

    def relevant_success_rate(
        self, query: str, *, min_attempts: int = 3, limit: int = 50
    ) -> Optional[OutcomeEvidence]:
        """Return weighted verified success evidence for tasks similar to *query*."""
        if not query or not query.strip():
            return None
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT task_text, outcome FROM development_events "
                "WHERE outcome IN ('verified_success','verified_failure') "
                "ORDER BY id DESC LIMIT ?",
                (max(limit, min_attempts),),
            ).fetchall()
        weighted_success = weighted_total = max_relevance = 0.0
        attempts = 0
        for row in rows:
            score = relevance(query, str(row["task_text"]))
            if score <= 0:
                continue
            attempts += 1
            weighted_total += score
            max_relevance = max(max_relevance, score)
            if row["outcome"] == "verified_success":
                weighted_success += score
        if attempts < min_attempts or weighted_total <= 0:
            return None
        return OutcomeEvidence(
            attempts=attempts,
            success_rate=round(weighted_success / weighted_total, 6),
            relevance=round(max_relevance, 6),
        )

    def model_task_success_rates(
        self, *, min_attempts: int = 3, limit: int = 5000
    ) -> dict[tuple[str, str, str], float]:
        """Verified-success rate per ``(provider, model, task)`` from the evidence.

        Reads the verified outcomes, parses each event's ``metadata`` for the
        ``provider``/``model``/``task`` that produced it, and returns the success
        rate for every signature with at least *min_attempts* verified attempts.
        This is exactly the ``metrics`` map the cross-provider router blends in for
        **evidence-calibrated routing** — so the router learns which model actually
        performs on *this* workload. Cold-start signatures simply don't appear, so
        the router falls back to its heuristic for them (no calibration ever fires
        on too little evidence). Pure read; deterministic given the stored events.
        """
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT outcome, metadata_json FROM development_events "
                "WHERE outcome IN ('verified_success','verified_failure') "
                "ORDER BY id DESC LIMIT ?",
                (max(int(limit), 1),),
            ).fetchall()
        tally: dict[tuple[str, str, str], list[int]] = {}  # key -> [successes, total]
        for row in rows:
            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            provider = str(meta.get("provider") or "").strip()
            model = str(meta.get("model") or "").strip()
            task = str(meta.get("task") or "").strip()
            if not (provider and model and task):
                continue
            agg = tally.setdefault((provider, model, task), [0, 0])
            agg[1] += 1
            if row["outcome"] == "verified_success":
                agg[0] += 1
        floor = max(int(min_attempts), 1)
        return {
            key: round(succ / total, 6)
            for key, (succ, total) in tally.items()
            if total >= floor
        }

    def summary(self) -> dict[str, Any]:
        """Return high-signal developmental metrics over all recorded tasks."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            counts = {
                str(row["outcome"]): int(row["n"])
                for row in conn.execute(
                    "SELECT outcome, COUNT(*) AS n FROM development_events GROUP BY outcome"
                )
            }
            totals = conn.execute(
                "SELECT COUNT(*) AS tasks, COALESCE(SUM(tool_calls),0) AS tools, "
                "COALESCE(SUM(human_interventions),0) AS interventions, "
                "COALESCE(SUM(blocked_actions),0) AS blocked FROM development_events"
            ).fetchone()
            mistake = conn.execute(
                "SELECT COUNT(*) AS lessons, "
                "COALESCE(SUM(CASE WHEN occurrence_count > 1 THEN occurrence_count - 1 ELSE 0 END),0) "
                "AS repeats FROM mistake_pool"
            ).fetchone()
        verified = counts.get("verified_success", 0) + counts.get("verified_failure", 0)
        tasks = int(totals["tasks"])
        return {
            "tasks": tasks,
            "outcomes": counts,
            "verified_success_rate": (
                round(counts.get("verified_success", 0) / verified, 6) if verified else None
            ),
            "verification_coverage": round(verified / tasks, 6) if tasks else 0.0,
            "human_intervention_rate": (
                round(int(totals["interventions"]) / tasks, 6) if tasks else 0.0
            ),
            "average_tool_calls": round(int(totals["tools"]) / tasks, 6) if tasks else 0.0,
            "blocked_actions": int(totals["blocked"]),
            "lessons": int(mistake["lessons"]),
            "repeated_mistakes": int(mistake["repeats"]),
        }
