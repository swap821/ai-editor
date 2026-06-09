"""Verification-backed procedural skill memory.

A workflow is never trusted because the model described it or because it ran
once. It becomes ``verified`` only after repeated verification-backed success,
and can be demoted again when later verified failures reduce its success rate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance, tokens
from aios.security.secret_scanner import scan_and_redact


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
        """Record one verification-backed attempt and recalculate trust status."""
        clean_steps = [scan_and_redact(step.strip()).scrubbed for step in steps if step.strip()]
        goal = scan_and_redact(goal.strip()).scrubbed
        if not goal or not clean_steps:
            raise ValueError("skill attempt requires a goal and workflow steps")
        sig = self._signature(goal, clean_steps)
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, success_count, failure_count FROM procedural_skills "
                "WHERE signature = ?",
                (sig,),
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    "INSERT INTO procedural_skills "
                    "(signature, goal_pattern, steps_json, success_count, failure_count) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        sig,
                        goal,
                        json.dumps(clean_steps, separators=(",", ":")),
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

    def relevant_verified(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Return verified procedures relevant to a future goal."""
        if not query or limit <= 0:
            return []
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
            ranked.append(
                {
                    "skill_id": int(row["id"]),
                    "goal_pattern": str(row["goal_pattern"]),
                    "steps": json.loads(str(row["steps_json"])),
                    "success_count": successes,
                    "failure_count": failures,
                    "success_rate": round(successes / max(successes + failures, 1), 6),
                    "relevance": score,
                }
            )
        ranked.sort(
            key=lambda item: (
                item["relevance"],
                item["success_rate"],
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
