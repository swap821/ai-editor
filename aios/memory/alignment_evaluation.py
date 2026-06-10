"""Durable human-alignment evaluation evidence.

Each generated understanding frame creates one observation that can later be
labelled by the operator. The store is diagnostic only: observations do not
authorize actions, establish facts, or automatically modify alignment policy.
Caller-supplied session identifiers are persisted only as SHA-256 digests.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from aios import config
from aios.memory.db import get_connection, init_memory_db
from aios.security.secret_scanner import scan_and_redact

ALLOWED_OUTCOMES = frozenset(
    {"aligned", "misaligned", "correction_helped", "correction_not_helpful"}
)
ALLOWED_ISSUES = frozenset(
    {
        "wrong_goal",
        "wrong_intent",
        "unnecessary_question",
        "risky_assumption",
        "wrong_mode",
        "other",
    }
)
_ALLOWED_INTENTS = frozenset(
    {"discuss", "teach", "plan", "execute", "review", "decide", "correct", "unknown"}
)
_ALLOWED_MODES = frozenset({"direct", "collaborative", "explanatory"})
_ALLOWED_ACTIONS = frozenset({"proceed", "state_assumptions", "ask"})
_MAX_NOTES = 500
_MAX_FIELDS = 20


def _session_key(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _allowed(value: object, choices: frozenset[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in choices else fallback


def _count(value: object) -> int:
    return min(100, len(value)) if isinstance(value, (list, tuple)) else 0


def _confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(1.0, number)), 3)


def _clean_choices(
    values: Iterable[object], choices: frozenset[str], *, limit: int = _MAX_FIELDS
) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized in choices and normalized not in cleaned:
            cleaned.append(normalized)
        if len(cleaned) >= limit:
            break
    return cleaned


def _clean_fields(values: Iterable[object]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized and normalized.replace("_", "").isalnum() and normalized not in cleaned:
            cleaned.append(normalized[:80])
        if len(cleaned) >= _MAX_FIELDS:
            break
    return cleaned


def _json_list(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


class AlignmentEvaluationStore:
    """Record and summarize operator-labelled alignment observations."""

    def __init__(self, db_path: Path = config.MEMORY_DB_PATH) -> None:
        self.db_path = db_path

    def record(self, session_id: str, frame: dict[str, Any]) -> int:
        """Record the final advisory frame shown for one generated turn."""
        if not session_id:
            raise ValueError("alignment observation requires a session id")
        if not isinstance(frame, dict):
            raise ValueError("alignment observation frame must be an object")
        communication = frame.get("communication")
        communication = communication if isinstance(communication, dict) else {}
        correction = frame.get("correction")
        correction = correction if isinstance(correction, dict) else {}
        corrected_fields = _clean_fields(correction.get("corrected_fields", []))
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO alignment_observations "
                "(session_id, intent, communication_mode, ambiguity_action, confidence, "
                "assumptions_count, unknowns_count, corrected, corrected_fields_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _session_key(session_id),
                    _allowed(frame.get("intent"), _ALLOWED_INTENTS, "unknown"),
                    _allowed(communication.get("mode"), _ALLOWED_MODES, "direct"),
                    _allowed(communication.get("ambiguity_action"), _ALLOWED_ACTIONS, "proceed"),
                    _confidence(frame.get("confidence")),
                    _count(frame.get("assumptions")),
                    _count(frame.get("unknowns")),
                    1 if correction.get("active") else 0,
                    _json_list(corrected_fields),
                ),
            )
            return int(cur.lastrowid)

    def latest_observation_id(self, session_id: str) -> int | None:
        """Return the latest observation id for a session without exposing its key."""
        if not session_id:
            return None
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM alignment_observations WHERE session_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (_session_key(session_id),),
            ).fetchone()
        return int(row["id"]) if row is not None else None

    def mark_latest_corrected(
        self,
        session_id: str,
        fields: Iterable[object],
        *,
        observation_id: int | None = None,
    ) -> bool:
        """Attach correction evidence to a session-owned observation."""
        if not session_id:
            return False
        cleaned = _clean_fields(fields)
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            if observation_id is None:
                row = conn.execute(
                    "SELECT id, corrected_fields_json FROM alignment_observations "
                    "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                    (_session_key(session_id),),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id, corrected_fields_json FROM alignment_observations "
                    "WHERE session_id = ? AND id = ?",
                    (_session_key(session_id), int(observation_id)),
                ).fetchone()
            if row is None:
                return False
            try:
                existing = json.loads(str(row["corrected_fields_json"]))
            except json.JSONDecodeError:
                existing = []
            merged = _clean_fields([*(existing if isinstance(existing, list) else []), *cleaned])
            conn.execute(
                "UPDATE alignment_observations SET corrected = 1, corrected_fields_json = ? "
                "WHERE id = ?",
                (_json_list(merged), int(row["id"])),
            )
        return True

    def record_feedback(
        self,
        session_id: str,
        *,
        outcome: str,
        issues: Iterable[object] = (),
        notes: str = "",
        observation_id: int | None = None,
    ) -> int:
        """Label one session-owned observation with explicit human feedback."""
        normalized_outcome = _allowed(outcome, ALLOWED_OUTCOMES, "")
        if not normalized_outcome:
            raise ValueError("unsupported alignment outcome")
        cleaned_issues = _clean_choices(issues, ALLOWED_ISSUES)
        cleaned_notes = scan_and_redact(" ".join(str(notes or "").split())).scrubbed[:_MAX_NOTES]
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            if observation_id is None:
                row = conn.execute(
                    "SELECT id FROM alignment_observations WHERE session_id = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (_session_key(session_id),),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM alignment_observations WHERE session_id = ? AND id = ?",
                    (_session_key(session_id), int(observation_id)),
                ).fetchone()
            if row is None:
                raise ValueError("no alignment observation exists for session")
            observation_id = int(row["id"])
            conn.execute(
                "UPDATE alignment_observations SET human_outcome = ?, issues_json = ?, "
                "notes = ? WHERE id = ?",
                (
                    normalized_outcome,
                    _json_list(cleaned_issues),
                    cleaned_notes or None,
                    observation_id,
                ),
            )
        return observation_id

    def summary(self, *, recent_limit: int = 20) -> dict[str, Any]:
        """Return aggregate and recent evidence without exposing session ids."""
        init_memory_db(self.db_path)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, created_at, intent, communication_mode, ambiguity_action, "
                "confidence, assumptions_count, unknowns_count, corrected, "
                "corrected_fields_json, human_outcome, issues_json "
                "FROM alignment_observations ORDER BY id DESC"
            ).fetchall()

        total = len(rows)
        corrected = sum(int(row["corrected"]) for row in rows)
        feedback_rows = [row for row in rows if row["human_outcome"]]
        outcomes = Counter(str(row["human_outcome"]) for row in feedback_rows)
        intents = Counter(str(row["intent"]) for row in rows)
        modes = Counter(str(row["communication_mode"]) for row in rows)
        actions = Counter(str(row["ambiguity_action"]) for row in rows)
        corrected_fields: Counter[str] = Counter()
        issues: Counter[str] = Counter()
        recent: list[dict[str, Any]] = []
        for row in rows:
            try:
                row_fields = json.loads(str(row["corrected_fields_json"]))
            except json.JSONDecodeError:
                row_fields = []
            try:
                row_issues = json.loads(str(row["issues_json"]))
            except json.JSONDecodeError:
                row_issues = []
            corrected_fields.update(item for item in row_fields if isinstance(item, str))
            issues.update(item for item in row_issues if isinstance(item, str))
            if len(recent) < max(1, min(100, int(recent_limit))):
                recent.append(
                    {
                        "id": int(row["id"]),
                        "created_at": str(row["created_at"]),
                        "intent": str(row["intent"]),
                        "communication_mode": str(row["communication_mode"]),
                        "ambiguity_action": str(row["ambiguity_action"]),
                        "confidence": float(row["confidence"]),
                        "assumptions_count": int(row["assumptions_count"]),
                        "unknowns_count": int(row["unknowns_count"]),
                        "corrected": bool(row["corrected"]),
                        "corrected_fields": row_fields if isinstance(row_fields, list) else [],
                        "human_outcome": str(row["human_outcome"]) if row["human_outcome"] else None,
                        "issues": row_issues if isinstance(row_issues, list) else [],
                    }
                )
        aligned = outcomes["aligned"] + outcomes["correction_helped"]
        repeated = [
            {"kind": "issue", "name": name, "count": count}
            for name, count in issues.most_common()
            if count >= 3
        ] + [
            {"kind": "corrected_field", "name": name, "count": count}
            for name, count in corrected_fields.most_common()
            if count >= 3
        ]
        repeated.sort(key=lambda item: (-int(item["count"]), str(item["kind"]), str(item["name"])))
        return {
            "total_turns": total,
            "corrected_turns": corrected,
            "correction_rate": _rate(corrected, total),
            "human_feedback_count": len(feedback_rows),
            "positive_feedback_rate": _rate(aligned, len(feedback_rows)),
            "ask_rate": _rate(actions["ask"], total),
            "state_assumptions_rate": _rate(actions["state_assumptions"], total),
            "outcomes": dict(outcomes),
            "by_intent": dict(intents),
            "by_communication_mode": dict(modes),
            "by_ambiguity_action": dict(actions),
            "corrected_fields": dict(corrected_fields),
            "issues": dict(issues),
            "repeated_patterns": repeated,
            "recent": recent,
            "automatic_policy_updates": False,
        }
