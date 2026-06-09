"""Safe, evidence-gated developmental curriculum.

This module never executes a task. It only records curriculum definitions and
matches authoritative verifier outcomes from the normal supervised agent loop.
Progression requires repeated training success plus a held-out pass.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.security.secret_scanner import scan_and_redact


class CurriculumManager:
    """Manage non-autonomous curriculum tasks and held-out progression."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        training_passes_required: int = 2,
    ) -> None:
        self.db_path = db_path
        self.training_passes_required = max(training_passes_required, 1)

    def add_task(
        self, skill_name: str, level: int, prompt: str, *, held_out: bool = False
    ) -> int:
        """Add a curriculum task; higher levels stay locked until prior mastery."""
        skill_name = scan_and_redact(skill_name.strip()).scrubbed
        prompt = scan_and_redact(prompt.strip()).scrubbed
        if not skill_name or not prompt or level < 1:
            raise ValueError("curriculum task requires skill, prompt, and level >= 1")
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id, held_out FROM curriculum_tasks "
                "WHERE skill_name = ? AND level = ? AND prompt = ?",
                (skill_name, level, prompt),
            ).fetchone()
            if existing is not None:
                if bool(existing["held_out"]) != bool(held_out):
                    raise ValueError("cannot change held-out role of an existing task")
                return int(existing["id"])
            mastered_level = conn.execute(
                "SELECT 1 FROM curriculum_tasks WHERE skill_name = ? AND level = ? "
                "AND status = 'mastered' LIMIT 1",
                (skill_name, level),
            ).fetchone()
            if mastered_level is not None:
                raise ValueError("cannot add a new task to an already mastered level")
            prior = conn.execute(
                "SELECT status FROM curriculum_tasks WHERE skill_name = ? AND level < ?",
                (skill_name, level),
            ).fetchall()
            prior_ready = bool(prior) and all(row["status"] == "mastered" for row in prior)
            status = "available" if level == 1 or prior_ready else "locked"
            cur = conn.execute(
                "INSERT INTO curriculum_tasks "
                "(skill_name, level, prompt, held_out, status) VALUES (?, ?, ?, ?, ?)",
                (skill_name, level, prompt, int(held_out), status),
            )
            return int(cur.lastrowid)

    def record_matching(self, prompt: str, *, passed: bool, evidence: str) -> list[int]:
        """Apply an authoritative verifier result to exactly matching available tasks."""
        if not evidence.startswith("[VERIFY PASS]") and not evidence.startswith("[VERIFY FAIL]"):
            raise ValueError("curriculum progress requires authoritative verifier evidence")
        expected_pass = evidence.startswith("[VERIFY PASS]")
        if bool(passed) != expected_pass:
            raise ValueError("curriculum result conflicts with verifier evidence")
        init_memory_db(self.db_path)
        updated: list[int] = []
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id, skill_name, level FROM curriculum_tasks "
                "WHERE prompt = ? AND status = 'available'",
                (prompt.strip(),),
            ).fetchall()
            if len(rows) > 1:
                raise ValueError("curriculum prompt is ambiguous across available tasks")
            for row in rows:
                task_id = int(row["id"])
                conn.execute(
                    "UPDATE curriculum_tasks SET attempts = attempts + 1, "
                    "successes = successes + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (1 if passed else 0, task_id),
                )
                updated.append(task_id)
                self._refresh_level(conn, str(row["skill_name"]), int(row["level"]))
        return updated

    def _refresh_level(self, conn, skill_name: str, level: int) -> None:
        rows = conn.execute(
            "SELECT held_out, successes FROM curriculum_tasks "
            "WHERE skill_name = ? AND level = ?",
            (skill_name, level),
        ).fetchall()
        training = [row for row in rows if not row["held_out"]]
        held_out = [row for row in rows if row["held_out"]]
        training_passes = sum(int(row["successes"]) for row in training)
        training_covered = bool(training) and all(int(row["successes"]) > 0 for row in training)
        held_out_passed = bool(held_out) and all(int(row["successes"]) > 0 for row in held_out)
        if (
            training_passes < self.training_passes_required
            or not training_covered
            or not held_out_passed
        ):
            return
        conn.execute(
            "UPDATE curriculum_tasks SET status = 'mastered', updated_at = CURRENT_TIMESTAMP "
            "WHERE skill_name = ? AND level = ?",
            (skill_name, level),
        )
        conn.execute(
            "UPDATE curriculum_tasks SET status = 'available', updated_at = CURRENT_TIMESTAMP "
            "WHERE skill_name = ? AND level = ? AND status = 'locked'",
            (skill_name, level + 1),
        )

    def list(self, skill_name: str | None = None) -> list[dict[str, Any]]:
        """Return curriculum state; no task is ever executed here."""
        init_memory_db(self.db_path)
        sql = "SELECT * FROM curriculum_tasks"
        params: tuple[object, ...] = ()
        if skill_name:
            sql += " WHERE skill_name = ?"
            params = (skill_name,)
        sql += " ORDER BY skill_name, level, held_out, id"
        with get_connection(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
