"""Policy engine — additive-only constraints with queen voting."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class PolicyStatus(str, Enum):
    PROPOSED = "proposed"
    ENACTED = "enacted"
    SUSPENDED = "suspended"


@dataclass(frozen=True)
class PolicyVote:
    queen: str
    approve: bool
    reason: str


@dataclass(frozen=True)
class Policy:
    policy_id: str
    version: int
    constraint: str
    status: PolicyStatus
    proposed_by: str
    proposed_at: str
    enacted_at: str | None
    votes: list[PolicyVote]


_ADDITIVE_KEYWORDS = ("must", "require", "shall", "forbid", "prevent", "always", "never")
_REMOVAL_KEYWORDS = ("allow", "permit", "remove restriction", "relax", "disable", "exempt")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyEngine:
    """Additive-only graduated policy engine with queen voting."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS policies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        policy_id TEXT NOT NULL UNIQUE,
        version INTEGER NOT NULL,
        constraint_text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'proposed',
        proposed_by TEXT NOT NULL,
        proposed_at TEXT NOT NULL,
        enacted_at TEXT,
        votes_json TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_policy_status ON policies(status);
    CREATE INDEX IF NOT EXISTS idx_policy_version ON policies(version);
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or Path(":memory:")
        self._init_db()

    def _init_db(self) -> None:
        if str(self._db_path) != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(self._SCHEMA)
        self._connection.commit()

    def _conn(self) -> sqlite3.Connection:
        return self._connection

    def _next_version(self) -> int:
        row = self._conn().execute("SELECT MAX(version) AS v FROM policies").fetchone()
        value = row["v"] if row is not None else None
        return int(value) + 1 if value is not None else 1

    def _fetch_row(self, policy_id: str) -> sqlite3.Row | None:
        return self._conn().execute(
            "SELECT * FROM policies WHERE policy_id = ?", (policy_id,)
        ).fetchone()

    def _row_to_policy(self, row: sqlite3.Row) -> Policy:
        votes = [PolicyVote(**vote) for vote in json.loads(row["votes_json"])]
        return Policy(
            policy_id=row["policy_id"],
            version=int(row["version"]),
            constraint=row["constraint_text"],
            status=PolicyStatus(row["status"]),
            proposed_by=row["proposed_by"],
            proposed_at=row["proposed_at"],
            enacted_at=row["enacted_at"],
            votes=votes,
        )

    def propose(self, constraint: str, proposed_by: str) -> str:
        if not self.validate_additive(constraint):
            raise ValueError(f"constraint is not additive-only: {constraint!r}")
        proposed_at = _utcnow()
        policy_id = hashlib.sha256(
            f"{constraint}{proposed_by}{proposed_at}".encode("utf-8")
        ).hexdigest()[:12]
        version = self._next_version()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO policies "
                "(policy_id, version, constraint_text, status, proposed_by, proposed_at, enacted_at, votes_json) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, '[]')",
                (
                    policy_id,
                    version,
                    constraint,
                    PolicyStatus.PROPOSED.value,
                    proposed_by,
                    proposed_at,
                ),
            )
        return policy_id

    def vote(self, policy_id: str, queen: str, approve: bool, reason: str = "") -> None:
        row = self._fetch_row(policy_id)
        if row is None:
            raise ValueError(f"unknown policy_id: {policy_id}")
        votes = json.loads(row["votes_json"])
        if any(existing["queen"] == queen for existing in votes):
            raise ValueError(f"queen {queen!r} already voted on {policy_id}")
        votes.append({"queen": queen, "approve": approve, "reason": reason})
        with self._conn() as conn:
            conn.execute(
                "UPDATE policies SET votes_json = ? WHERE policy_id = ?",
                (json.dumps(votes), policy_id),
            )

    def enact(self, policy_id: str, required_approvals: int = 3) -> Policy:
        row = self._fetch_row(policy_id)
        if row is None:
            raise ValueError(f"unknown policy_id: {policy_id}")
        votes = json.loads(row["votes_json"])
        approvals = sum(1 for v in votes if v["approve"])
        if approvals < required_approvals:
            raise ValueError(
                f"not enough approvals for {policy_id}: {approvals} < {required_approvals}"
            )
        enacted_at = _utcnow()
        with self._conn() as conn:
            conn.execute(
                "UPDATE policies SET status = ?, enacted_at = ? WHERE policy_id = ?",
                (PolicyStatus.ENACTED.value, enacted_at, policy_id),
            )
        return self.get(policy_id)

    def suspend(self, policy_id: str, suspended_by: str) -> Policy:
        row = self._fetch_row(policy_id)
        if row is None:
            raise ValueError(f"unknown policy_id: {policy_id}")
        if row["status"] != PolicyStatus.ENACTED.value:
            raise ValueError(f"policy {policy_id} is not enacted")
        with self._conn() as conn:
            conn.execute(
                "UPDATE policies SET status = ? WHERE policy_id = ?",
                (PolicyStatus.SUSPENDED.value, policy_id),
            )
        suspension_constraint = f"SUSPEND: {policy_id}"
        proposed_at = _utcnow()
        suspension_id = hashlib.sha256(
            f"{suspension_constraint}{suspended_by}{proposed_at}".encode("utf-8")
        ).hexdigest()[:12]
        version = self._next_version()
        enacted_at = _utcnow()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO policies "
                "(policy_id, version, constraint_text, status, proposed_by, proposed_at, enacted_at, votes_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '[]')",
                (
                    suspension_id,
                    version,
                    suspension_constraint,
                    PolicyStatus.ENACTED.value,
                    suspended_by,
                    proposed_at,
                    enacted_at,
                ),
            )
        return self.get(policy_id)

    def current_policies(self) -> list[Policy]:
        rows = self._conn().execute(
            "SELECT * FROM policies WHERE status = ? ORDER BY version",
            (PolicyStatus.ENACTED.value,),
        ).fetchall()
        return [self._row_to_policy(row) for row in rows]

    def policy_chain(self) -> list[Policy]:
        rows = self._conn().execute("SELECT * FROM policies ORDER BY version").fetchall()
        return [self._row_to_policy(row) for row in rows]

    def get(self, policy_id: str) -> Policy | None:
        row = self._fetch_row(policy_id)
        return self._row_to_policy(row) if row is not None else None

    def validate_additive(self, constraint: str) -> bool:
        if not constraint or not constraint.strip():
            return False
        text = constraint.lower()
        if any(keyword in text for keyword in _REMOVAL_KEYWORDS):
            return False
        return any(keyword in text for keyword in _ADDITIVE_KEYWORDS)
