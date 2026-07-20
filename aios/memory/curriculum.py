"""Safe, evidence-gated developmental curriculum.

This module never executes a task. It only records curriculum definitions and
matches authoritative verifier outcomes from the normal supervised agent loop.
Progression requires repeated training success plus a held-out pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from aios import config
from aios.core.verification_strength import (
    VerificationStrength,
    meets_promotion_floor,
    strength_from_text,
)
from aios.memory.db import get_connection, init_memory_db
from aios.memory.relevance import relevance
from aios.security.secret_scanner import scan_and_redact


class CurriculumManager:
    """Manage non-autonomous curriculum tasks and held-out progression."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        training_passes_required: int = 2,
        fuzzy_matching: bool | None = None,
        fuzzy_threshold: float | None = None,
    ) -> None:
        self.db_path = db_path
        self.training_passes_required = max(training_passes_required, 1)
        self.fuzzy_matching = (
            config.CURRICULUM_FUZZY if fuzzy_matching is None else bool(fuzzy_matching)
        )
        threshold = (
            config.CURRICULUM_FUZZY_THRESHOLD
            if fuzzy_threshold is None
            else float(fuzzy_threshold)
        )
        self.fuzzy_threshold = min(max(threshold, 0.0), 1.0)

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
            prior_ready = bool(prior) and all(
                row["status"] == "mastered" for row in prior
            )
            status = "available" if level == 1 or prior_ready else "locked"
            cur = conn.execute(
                "INSERT INTO curriculum_tasks "
                "(skill_name, level, prompt, held_out, status) VALUES (?, ?, ?, ?, ?)",
                (skill_name, level, prompt, int(held_out), status),
            )
            return int(cur.lastrowid)

    def record_matching(
        self,
        prompt: str,
        *,
        passed: bool,
        evidence: str,
        strength: VerificationStrength | None = None,
        on_mastered: Optional[Callable[[str, int], None]] = None,
    ) -> list[int]:
        """Apply an authoritative verifier result to matching available tasks.

        Exact prompt equality has absolute priority (byte-compatible with the
        historical behavior, including the ambiguity error). When no exact row
        exists and fuzzy matching is enabled, a deterministic lexical fallback
        attributes the outcome iff exactly ONE available task clears the
        relevance threshold — zero or several candidates attribute nothing, so
        an ambiguous turn can never credit the wrong task.

        *strength* lets the caller supply the turn's already-resolved authoritative
        strength (the weakest passing target) so mastery cannot be laundered by a
        later advisory verify embedding a stronger token in *evidence*. When omitted
        (direct callers/tests) the strength is derived from *evidence*.
        """
        if not evidence.startswith("[VERIFY PASS]") and not evidence.startswith(
            "[VERIFY FAIL]"
        ):
            raise ValueError(
                "curriculum progress requires authoritative verifier evidence"
            )
        expected_pass = evidence.startswith("[VERIFY PASS]")
        if bool(passed) != expected_pass:
            raise ValueError("curriculum result conflicts with verifier evidence")
        # A pass advances mastery only if it was STRONGLY verified (roadmap Phase 1):
        # a weak green is still recorded as an attempt but contributes no success, so
        # it can never unlock the next level.
        eff_strength = (
            strength if strength is not None else strength_from_text(evidence)
        )
        counts_as_success = passed and meets_promotion_floor(eff_strength)
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
                raise ValueError(
                    "curriculum prompt is ambiguous across available tasks"
                )
            if not rows and self.fuzzy_matching:
                rows = self._fuzzy_rows(conn, prompt.strip())
            for row in rows:
                task_id = int(row["id"])
                conn.execute(
                    "UPDATE curriculum_tasks SET attempts = attempts + 1, "
                    "successes = successes + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (1 if counts_as_success else 0, task_id),
                )
                updated.append(task_id)
                skill_name = str(row["skill_name"])
                level = int(row["level"])
                if (
                    self._refresh_level(conn, skill_name, level)
                    and on_mastered is not None
                ):
                    # Fires only on the transition to mastered (a mastered
                    # level's tasks leave 'available', so it cannot re-fire).
                    on_mastered(skill_name, level)
        return updated

    def _fuzzy_rows(self, conn, prompt: str) -> list:
        """Deterministic near-match fallback when no exact prompt row exists.

        Fail-closed: a zero relevance score never attributes (even at threshold
        0.0), and more than one clearing candidate attributes nothing rather
        than guessing between them.
        """
        available = conn.execute(
            "SELECT id, skill_name, level, prompt FROM curriculum_tasks "
            "WHERE status = 'available'",
        ).fetchall()
        candidates = [
            row
            for row in available
            if (score := relevance(prompt, str(row["prompt"]))) >= self.fuzzy_threshold
            and score > 0.0
        ]
        return candidates if len(candidates) == 1 else []

    def _refresh_level(self, conn, skill_name: str, level: int) -> bool:
        """Master the level when its evidence thresholds are met.

        Returns ``True`` only when this call performs the mastery transition,
        so callers can announce growth without ever double-firing.
        """
        rows = conn.execute(
            "SELECT held_out, successes FROM curriculum_tasks "
            "WHERE skill_name = ? AND level = ?",
            (skill_name, level),
        ).fetchall()
        training = [row for row in rows if not row["held_out"]]
        held_out = [row for row in rows if row["held_out"]]
        training_passes = sum(int(row["successes"]) for row in training)
        training_covered = bool(training) and all(
            int(row["successes"]) > 0 for row in training
        )
        held_out_passed = bool(held_out) and all(
            int(row["successes"]) > 0 for row in held_out
        )
        if (
            training_passes < self.training_passes_required
            or not training_covered
            or not held_out_passed
        ):
            return False
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
        return True

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
