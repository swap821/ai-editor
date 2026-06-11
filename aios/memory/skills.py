"""Verification-backed procedural skill memory.

A workflow is never trusted because the model described it or because it ran
once. It becomes ``verified`` only after repeated verification-backed success,
and can be demoted again when later verified failures reduce its success rate.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance, skill_signature_v2, tokens
from aios.security.secret_scanner import scan_and_redact

#: SQLite ``CURRENT_TIMESTAMP`` formats emitted for ``updated_at``. Parsed
#: locally rather than importing the twin helper in retrieval.py so this module
#: stays free of the heavy rank-bm25/embeddings import graph.
_TIMESTAMP_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
)


def _hours_since(timestamp: str, now: datetime) -> float:
    """Hours between a SQLite UTC timestamp and *now* (clamped to >= 0)."""
    parsed: Optional[datetime] = None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(timestamp, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return 0.0
    return max((now - parsed).total_seconds() / 3600.0, 0.0)


class SkillMemory:
    """Store, promote, retrieve, and regress reusable verified workflows."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        min_successes: int = 3,
        min_success_rate: float = 0.8,
    ) -> None:
        self.db_path = db_path
        self.min_successes = max(min_successes, 1)
        self.min_success_rate = max(0.0, min(1.0, min_success_rate))

    @staticmethod
    def _signature(goal: str, steps: list[str]) -> str:
        goal_tokens = " ".join(sorted(tokens(goal))[:12])
        workflow = "|".join(step.strip().lower() for step in steps if step.strip())
        return hashlib.sha256(f"{goal_tokens}|{workflow}".encode("utf-8")).hexdigest()

    def record_attempt(self, goal: str, steps: list[str], *, success: bool) -> int:
        """Record one verification-backed attempt and recalculate trust status.

        Trail identity is the arc-level ``signature_v2`` (goal tokens + tool
        sequence, arguments ignored), so near-identical arcs — e.g. the same
        workflow with redaction noise in a filepath argument — reinforce ONE
        trail instead of fragmenting. The exact legacy ``signature`` is still
        stored on insert as lineage.
        """
        clean_steps = [scan_and_redact(step.strip()).scrubbed for step in steps if step.strip()]
        goal = scan_and_redact(goal.strip()).scrubbed
        if not goal or not clean_steps:
            raise ValueError("skill attempt requires a goal and workflow steps")
        sig = self._signature(goal, clean_steps)
        sig_v2 = skill_signature_v2(goal, clean_steps)
        steps_json = json.dumps(clean_steps, separators=(",", ":"))
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, success_count, failure_count, steps_json "
                "FROM procedural_skills "
                "WHERE signature_v2 = ? AND status != 'superseded'",
                (sig_v2,),
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    "INSERT INTO procedural_skills "
                    "(signature, signature_v2, goal_pattern, steps_json, "
                    "success_count, failure_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sig,
                        sig_v2,
                        goal,
                        steps_json,
                        1 if success else 0,
                        0 if success else 1,
                    ),
                )
                skill_id = int(cur.lastrowid)
                successes, failures = (1, 0) if success else (0, 1)
            else:
                skill_id = int(row["id"])
                successes = int(row["success_count"]) + (1 if success else 0)
                failures = int(row["failure_count"]) + (0 if success else 1)
                conn.execute(
                    "UPDATE procedural_skills SET success_count = ?, failure_count = ?, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (successes, failures, skill_id),
                )
                # Recipe-quality refresh only (counts are never rewritten): a
                # successful walk whose steps carry fewer redaction artifacts
                # replaces the stored recipe, because recalled steps are
                # injected verbatim into future agent context and a
                # "<REDACTED:…>.py" step is a useless instruction.
                if success and steps_json.count("<REDACTED:") < str(
                    row["steps_json"]
                ).count("<REDACTED:"):
                    conn.execute(
                        "UPDATE procedural_skills SET steps_json = ? WHERE id = ?",
                        (steps_json, skill_id),
                    )
            rate = successes / max(successes + failures, 1)
            status = (
                "verified"
                if successes >= self.min_successes and rate >= self.min_success_rate
                else "candidate"
            )
            conn.execute(
                "UPDATE procedural_skills SET status = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (status, skill_id),
            )
            return skill_id

    @staticmethod
    def _reuse_factor(reuse_successes: int, reuse_failures: int) -> float:
        """Multiplicative ranking factor from reuse pheromone (pure function).

        Saturating in both directions and asymmetric by design: with default
        constants one failure bites roughly as hard as seven successes reward
        (``_reuse_factor(0,1) ≈ 0.708`` vs ``_reuse_factor(1,0) ≈ 1.043``),
        and failures saturate twice as fast. Clamps on the config reads keep
        env tuning from inverting the asymmetry or dividing by zero; the hard
        floor keeps a stained trail rankable (weakened, never zeroed).
        """
        boost = min(max(config.SKILL_REUSE_BOOST_MAX, 0.0), 1.0)
        penalty = min(max(config.SKILL_REUSE_PENALTY_MAX, 0.0), 1.0)
        k_success = max(config.SKILL_REUSE_SUCCESS_K, 0.1)
        k_failure = max(config.SKILL_REUSE_FAILURE_K, 0.1)
        floor = min(max(config.SKILL_REUSE_FACTOR_FLOOR, 0.01), 1.0)
        sat_s = 1.0 - math.exp(-max(reuse_successes, 0) / k_success)
        sat_f = 1.0 - math.exp(-max(reuse_failures, 0) / k_failure)
        factor = 1.0 + boost * sat_s - penalty * sat_f
        return min(max(factor, floor), 1.0 + boost)

    def record_reuse(
        self,
        skill_ids: Sequence[int],
        *,
        success: bool,
        now: Optional[datetime] = None,
    ) -> list[int]:
        """Credit (or stain) recalled trails after a verifier-judged turn.

        Reuse evidence influences RANKING only: this method never writes
        ``success_count``/``failure_count`` and its only permitted status
        transition is the quarantine ``verified -> candidate``. Only currently
        ``verified`` rows are credited — candidates cannot launder reuse into
        promotion, and superseded fragments are silently skipped. A reuse
        SUCCESS refreshes the evaporation clock (``updated_at``); a reuse
        FAILURE deliberately does not — a misleading trail weakens AND keeps
        evaporating; it cannot stay fresh by failing. *now* is injectable for
        deterministic tests.
        """
        ids = [int(skill_id) for skill_id in skill_ids]
        if not ids:
            return []
        moment = (
            (now or datetime.now(timezone.utc))
            .replace(tzinfo=None)
            .strftime("%Y-%m-%d %H:%M:%S")
        )
        credited: list[int] = []
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for skill_id in ids:
                row = conn.execute(
                    "SELECT id, status, reuse_success_count, reuse_failure_count "
                    "FROM procedural_skills WHERE id = ? AND status = 'verified'",
                    (skill_id,),
                ).fetchone()
                if row is None:
                    continue
                if success:
                    conn.execute(
                        "UPDATE procedural_skills SET "
                        "reuse_success_count = reuse_success_count + 1, "
                        "updated_at = ?, last_reused_at = ? WHERE id = ?",
                        (moment, moment, skill_id),
                    )
                else:
                    reuse_failures = int(row["reuse_failure_count"]) + 1
                    conn.execute(
                        "UPDATE procedural_skills SET "
                        "reuse_failure_count = ?, last_reused_at = ? WHERE id = ?",
                        (reuse_failures, moment, skill_id),
                    )
                    net = reuse_failures - int(row["reuse_success_count"])
                    if net >= config.SKILL_REUSE_DEMOTE_NET_FAILURES:
                        # Quarantine: a trail repeatedly co-present in verified
                        # failures is actively harmful context. Direct counts
                        # stay untouched; recovery requires a fresh DIRECT
                        # verified success through record_attempt.
                        conn.execute(
                            "UPDATE procedural_skills SET status = 'candidate' "
                            "WHERE id = ?",
                            (skill_id,),
                        )
                credited.append(skill_id)
        return credited

    def relevant_verified(
        self,
        query: str,
        limit: int = 3,
        *,
        now: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Return verified procedures relevant to a future goal.

        Ranking blends lexical relevance with a pheromone-style strength term:
        ``strength = success_rate * freshness``, where ``freshness`` decays
        exponentially with the hours since the skill was last reinforced
        (``updated_at``). :meth:`record_attempt` bumps ``updated_at`` on every
        attempt, so re-use keeps a trail fresh while disuse lets it evaporate
        down the ranking — verified skills are never deleted, only out-competed
        by fresher, higher-success peers. *now* is injectable for deterministic
        tests.
        """
        if not query or limit <= 0:
            return []
        moment = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM procedural_skills WHERE status = 'verified'"
            ).fetchall()
        ranked: list[dict[str, Any]] = []
        for row in rows:
            score = relevance(query, str(row["goal_pattern"]))
            if score <= 0:
                continue
            successes = int(row["success_count"])
            failures = int(row["failure_count"])
            success_rate = successes / max(successes + failures, 1)
            age_hours = _hours_since(str(row["updated_at"]), moment)
            freshness = math.exp(-config.SKILL_LAMBDA_DECAY_PER_HOUR * age_hours)
            reuse_successes = int(row["reuse_success_count"] or 0)
            reuse_failures = int(row["reuse_failure_count"] or 0)
            reuse_factor = self._reuse_factor(reuse_successes, reuse_failures)
            # min(1.0, …) is load-bearing: reuse boost can offset evaporation
            # and re-rank imperfect trails, but can never exceed a perfect
            # fresh direct trail. Untouched trails (reuse counts 0,0 => factor
            # exactly 1.0) keep strength == success_rate * freshness.
            ranked.append(
                {
                    "skill_id": int(row["id"]),
                    "goal_pattern": str(row["goal_pattern"]),
                    "steps": json.loads(str(row["steps_json"])),
                    "success_count": successes,
                    "failure_count": failures,
                    "success_rate": round(success_rate, 6),
                    "freshness": round(freshness, 6),
                    "reuse_success_count": reuse_successes,
                    "reuse_failure_count": reuse_failures,
                    "reuse_factor": round(reuse_factor, 6),
                    "strength": round(
                        min(1.0, success_rate * freshness * reuse_factor), 6
                    ),
                    "relevance": score,
                }
            )
        ranked.sort(
            key=lambda item: (
                item["relevance"],
                item["strength"],
                item["success_count"],
            ),
            reverse=True,
        )
        return ranked[:limit]

    def list(self, *, status: str | None = None) -> list[dict[str, Any]]:
        """Return skill rows as JSON-safe dictionaries."""
        init_memory_db(self.db_path)
        sql = "SELECT * FROM procedural_skills"
        params: tuple[object, ...] = ()
        if status is not None:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY updated_at DESC, id DESC"
        with get_connection(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                **dict(row),
                "steps": json.loads(str(row["steps_json"])),
            }
            for row in rows
        ]
