"""Memory for ant-colony swarm decomposition patterns.

A pattern is a goal shape plus the ordered subtasks a swarm used to satisfy it.
Patterns start as ``candidate`` and are promoted to ``verified`` after repeated
successful outcomes. The scout caste may recall a verified pattern to skip the
expensive decomposer on familiar work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.core.verification_strength import VerificationStrength, meets_promotion_floor
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance, signature


class SwarmPatternMemory:
    """Store, promote, and recall verified swarm decomposition plans."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        min_successes: int = 2,
        min_success_rate: float = 0.6,
        relevance_threshold: float = 0.5,
    ) -> None:
        self.db_path = db_path
        self.min_successes = max(min_successes, 1)
        self.min_success_rate = max(0.0, min(1.0, min_success_rate))
        self.relevance_threshold = max(0.0, min(1.0, relevance_threshold))

    def record_attempt(
        self,
        goal: str,
        subtasks: list[str],
        *,
        success: bool,
        strength: VerificationStrength = VerificationStrength.STRONG,
    ) -> int:
        """Record one swarm outcome for a goal+subtask pattern.

        Returns the pattern id. Promotes candidate -> verified when direct
        evidence crosses the threshold. Only a success at or above the promotion
        floor (default STRONG) counts toward promotion; a below-floor success is
        recorded in ``weak_success_count`` but can never make a pattern
        ``verified`` — a weak green is remembered, never trusted. Defaults to
        STRONG so callers that don't pass strength keep their behavior.
        """
        clean_goal = (goal or "").strip()
        clean_subtasks = [s.strip() for s in subtasks if s.strip()]
        if not clean_goal or not clean_subtasks:
            raise ValueError("pattern requires a goal and at least one subtask")
        eligible = success and meets_promotion_floor(strength)
        weak = success and not eligible
        sig = signature(clean_goal)
        subtasks_json = json.dumps(clean_subtasks, separators=(",", ":"))
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = None
            for candidate in conn.execute(
                "SELECT id, success_count, failure_count, weak_success_count, goal_pattern "
                "FROM swarm_patterns WHERE status != 'superseded'"
            ).fetchall():
                if signature(str(candidate["goal_pattern"])) == sig:
                    row = candidate
                    break
            if row is None:
                cur = conn.execute(
                    "INSERT INTO swarm_patterns "
                    "(goal_pattern, subtasks_json, success_count, failure_count, "
                    "weak_success_count, verification_strength) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        clean_goal,
                        subtasks_json,
                        1 if eligible else 0,
                        0 if success else 1,
                        1 if weak else 0,
                        strength.name if success else None,
                    ),
                )
                pattern_id = int(cur.lastrowid)
                successes, failures = (1 if eligible else 0), (0 if success else 1)
            else:
                pattern_id = int(row["id"])
                successes = int(row["success_count"]) + (1 if eligible else 0)
                failures = int(row["failure_count"]) + (0 if success else 1)
                weak_total = int(row["weak_success_count"] or 0) + (1 if weak else 0)
                conn.execute(
                    "UPDATE swarm_patterns SET success_count = ?, failure_count = ?, "
                    "weak_success_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (successes, failures, weak_total, pattern_id),
                )
                if success:
                    conn.execute(
                        "UPDATE swarm_patterns SET verification_strength = ? WHERE id = ?",
                        (strength.name, pattern_id),
                    )
            rate = successes / max(successes + failures, 1)
            status = (
                "verified"
                if successes >= self.min_successes and rate >= self.min_success_rate
                else "candidate"
            )
            conn.execute(
                "UPDATE swarm_patterns SET status = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = ?",
                (status, pattern_id),
            )
            return pattern_id

    def recall(
        self,
        goal: str,
        *,
        limit: int = 1,
    ) -> list[dict[str, Any]]:
        """Return verified patterns relevant to *goal*.

        Patterns are ranked by lexical relevance then by success rate. Only
        patterns at or above ``relevance_threshold`` are returned.
        """
        if not goal:
            return []
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM swarm_patterns WHERE status = 'verified'"
            ).fetchall()
        ranked: list[dict[str, Any]] = []
        for row in rows:
            score = relevance(goal, str(row["goal_pattern"]))
            if score < self.relevance_threshold:
                continue
            successes = int(row["success_count"])
            failures = int(row["failure_count"])
            rate = successes / max(successes + failures, 1)
            ranked.append(
                {
                    "pattern_id": int(row["id"]),
                    "goal_pattern": str(row["goal_pattern"]),
                    "subtasks": json.loads(str(row["subtasks_json"])),
                    "success_count": successes,
                    "failure_count": failures,
                    "success_rate": round(rate, 6),
                    "relevance": score,
                    "score": round(score * rate, 6),
                }
            )
        ranked.sort(
            key=lambda item: (item["score"], item["success_rate"]), reverse=True
        )
        return ranked[:limit]

    def bump_use(self, pattern_id: int) -> None:
        """Increment the use counter when a scout deploys a pattern."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE swarm_patterns SET use_count = use_count + 1, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (pattern_id,),
            )
