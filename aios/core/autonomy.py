"""Earned autonomy — the evidence→GREEN bridge.

A YELLOW (human-approval) *action class* graduates to autonomous execution ONLY
after it has accumulated enough VERIFIED-success evidence and is then revoked
instantly by a single verified failure. The design mirrors the rest of this
system's load-bearing invariant — **trust the evidence, not the model**:

* Autonomy is earned by the verifier's authoritative PASS/FAIL, never by the
  model's narration or confidence.
* It is OFF by default (``AIOS_EARNED_AUTONOMY``); supervision stays the norm.
* It only ever acts on YELLOW. RED is *un-earnable*: a RED action is BLOCKED by
  the gateway long before this layer is consulted, and even a granted action is
  re-classified and refused by :func:`Executor.execute_approved` — so a stale or
  malformed earned signature can never escalate into a destructive write.
* A signature is keyed by the *shape* of the action (action type + scope-bound
  target pattern, values stripped and secret-redacted), so "create a ``.py`` in
  ``training_ground``" earns as a bounded class, not per-exact-file — and the
  class never widens past the scope the gateway already enforces.
* One verified failure ⇒ instant revoke (streak reset); re-earning requires a
  fresh run of consecutive verified successes. One failure outweighs any number
  of past successes, exactly as the skill-trail pheromone does.
* Every auto-grant is recorded in the tamper-evident audit chain by its caller
  as actor ``earned-autonomy`` with the evidence (streak) that earned it, and
  the operator can revoke any signature at any time.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from aios import config
from aios.core.verification_strength import VerificationStrength, meets_promotion_floor
from aios.memory.db import get_connection
from aios.security.secret_scanner import scan_and_redact

#: Tool names whose target is a filepath (write actions). Everything else is
#: treated as a command whose first token is the verb.
_WRITE_ACTIONS = frozenset({"create", "edit", "create_file", "edit_file"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AutonomyLedger:
    """Per-action-signature earned-autonomy evidence with instant revocation."""

    def __init__(
        self,
        db_path: Path = config.MEMORY_DB_PATH,
        *,
        min_successes: int = config.EARNED_AUTONOMY_MIN_SUCCESSES,
    ) -> None:
        self.db_path = db_path
        self.min_successes = max(int(min_successes), 1)
        self._ensure_table()

    def _ensure_table(self) -> None:
        with get_connection(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS earned_autonomy (
                    signature TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    target_shape TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'probation',
                    earned_at TEXT,
                    revoked_at TEXT,
                    last_outcome_at TEXT,
                    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
                    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
                );
                """
            )

    # -- signature ---------------------------------------------------------

    @staticmethod
    def _normalize(action_type: str, target: str) -> str:
        """Reduce a concrete action to its scope-bound *shape* (no values).

        Writes collapse to ``<dir>/*<.ext>``; commands collapse to
        ``<verb> <arg-shape>`` where path args keep only their directory + ext,
        flags are kept verbatim, and other values become ``<arg>``. Secrets are
        redacted first so a signature can never embed a credential.
        """
        scrub = scan_and_redact(str(target).strip()).scrubbed
        if action_type in _WRITE_ACTIONS:
            p = PurePosixPath(scrub.replace("\\", "/"))
            parent = "" if str(p.parent) in (".", "") else str(p.parent)
            ext = p.suffix or ""
            return f"{parent}/*{ext}" if parent else f"*{ext}"
        parts = scrub.split()
        if not parts:
            return "<empty>"
        verb = parts[0]
        shape: list[str] = []
        for arg in parts[1:]:
            if "/" in arg or "\\" in arg:
                pp = PurePosixPath(arg.replace("\\", "/"))
                par = "" if str(pp.parent) in (".", "") else str(pp.parent)
                shape.append(f"{par}/*{pp.suffix}" if par else f"*{pp.suffix}")
            elif arg.startswith("-"):
                shape.append(arg)
            else:
                shape.append("<arg>")
        return (verb + " " + " ".join(shape)).strip()

    def signature(self, action_type: str, target: str) -> str:
        norm = self._normalize(action_type, target)
        return hashlib.sha256(f"{action_type}|{norm}".encode("utf-8")).hexdigest()

    # -- query -------------------------------------------------------------

    def is_earned(self, action_type: str, target: str) -> bool:
        """True only if the feature is enabled AND this signature is ``earned``.

        Fail-closed: if the feature flag is off, autonomy is never granted, so a
        deployment that never opts in behaves exactly like today (always YELLOW).
        """
        if not config.EARNED_AUTONOMY_ENABLED:
            return False
        sig = self.signature(action_type, target)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM earned_autonomy WHERE signature = ?", (sig,)
            ).fetchone()
        return row is not None and str(row["status"]) == "earned"

    def record_for(self, action_type: str, target: str) -> dict[str, Any] | None:
        """The ledger row for a signature (status/counts/streak), or None.

        Used by the caller to put the EVIDENCE that earned an auto-grant into the
        audit entry, so the hash-chain explains why a write ran without a human.
        """
        sig = self.signature(action_type, target)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT status, success_count, failure_count, streak "
                "FROM earned_autonomy WHERE signature = ?",
                (sig,),
            ).fetchone()
        return dict(row) if row is not None else None

    # -- evidence ----------------------------------------------------------

    def record_outcome(
        self,
        action_type: str,
        target: str,
        *,
        success: bool,
        strength: VerificationStrength = VerificationStrength.STRONG,
    ) -> dict[str, Any]:
        """Fold one verifier-authoritative outcome into the signature's evidence.

        Only a success at or above the promotion floor extends the streak and can
        promote to ``earned``. A below-floor success is treated as unverifiable
        for autonomy and revokes/reset-streaks fail-closed: YELLOW can graduate
        only from behavior-asserting evidence. A single failure resets the streak
        to 0 and revokes. Returns the resulting record (caller emits/audits it).
        """
        eligible_success = success and meets_promotion_floor(strength)
        sig = self.signature(action_type, target)
        norm = self._normalize(action_type, target)
        now = _now_iso()
        with get_connection(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT success_count, failure_count, streak, status "
                "FROM earned_autonomy WHERE signature = ?",
                (sig,),
            ).fetchone()
            if row is None:
                if eligible_success:
                    succ, fail, streak = 1, 0, 1
                    status = "earned" if streak >= self.min_successes else "probation"
                    earned_at, revoked_at = (now if status == "earned" else None), None
                else:
                    # A failure is always loud: even a first-ever outcome that
                    # fails (or passes only weakly) marks the signature revoked,
                    # never silently neutral.
                    succ, fail, streak, status = 0, 1, 0, "revoked"
                    earned_at, revoked_at = None, now
                conn.execute(
                    "INSERT INTO earned_autonomy "
                    "(signature, action_type, target_shape, success_count, "
                    "failure_count, streak, status, earned_at, revoked_at, "
                    "last_outcome_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (sig, action_type, norm, succ, fail, streak, status,
                     earned_at, revoked_at, now, now),
                )
            elif eligible_success:
                succ = int(row["success_count"]) + 1
                fail = int(row["failure_count"])
                streak = int(row["streak"]) + 1
                status = "earned" if streak >= self.min_successes else "probation"
                newly_earned = status == "earned" and str(row["status"]) != "earned"
                conn.execute(
                    "UPDATE earned_autonomy SET success_count = ?, failure_count = ?, "
                    "streak = ?, status = ?, last_outcome_at = ?, updated_at = ?"
                    + (", earned_at = ?" if newly_earned else "")
                    + " WHERE signature = ?",
                    (succ, fail, streak, status, now, now, now, sig)
                    if newly_earned
                    else (succ, fail, streak, status, now, now, sig),
                )
            else:
                succ = int(row["success_count"])
                fail = int(row["failure_count"]) + 1
                streak = 0
                status = "revoked"
                conn.execute(
                    "UPDATE earned_autonomy SET success_count = ?, failure_count = ?, "
                    "streak = 0, status = 'revoked', revoked_at = ?, last_outcome_at = ?, "
                    "updated_at = ? WHERE signature = ?",
                    (succ, fail, now, now, now, sig),
                )
        return {
            "signature": sig,
            "action_type": action_type,
            "target_shape": norm,
            "status": status,
            "success_count": succ,
            "failure_count": fail,
            "streak": streak,
        }

    # -- operator controls -------------------------------------------------

    def revoke(self, signature: str) -> bool:
        """Operator force-revoke; returns True if a row was affected."""
        now = _now_iso()
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE earned_autonomy SET status = 'revoked', streak = 0, "
                "revoked_at = ?, updated_at = ? WHERE signature = ?",
                (now, now, signature),
            )
            return cur.rowcount > 0

    def ledger_map(self) -> dict[str, Any]:
        """Observable view of the whole ledger for the operator/HUD."""
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT signature, action_type, target_shape, success_count, "
                "failure_count, streak, status, earned_at, revoked_at, last_outcome_at "
                "FROM earned_autonomy ORDER BY status, success_count DESC"
            ).fetchall()
        entries = [dict(row) for row in rows]
        return {
            "enabled": bool(config.EARNED_AUTONOMY_ENABLED),
            "min_successes": self.min_successes,
            "entries": entries,
            "summary": {
                "earned": sum(1 for e in entries if e["status"] == "earned"),
                "probation": sum(1 for e in entries if e["status"] == "probation"),
                "revoked": sum(1 for e in entries if e["status"] == "revoked"),
            },
        }

    def earned_count(self) -> int:
        """Number of signatures currently in the earned state."""
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM earned_autonomy WHERE status = ?", ("earned",)
            ).fetchone()
        return int(row["n"])
