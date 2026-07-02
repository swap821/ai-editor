"""Disk-based coordination CLI for Claude, Codex, Kimi, and future coding agents.

The control plane is deliberately local and explicit. It cannot wake an agent
or replace human approval. It prevents simultaneous writers, balances builder
assignments equally, records messages, and hash-pins handoffs so reviews cannot
approve a different tree than the one they inspected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / ".aios" / "state" / "coordination.db"
AGENTS = ("codex", "claude", "kimi")
ROLES = ("builder", "reviewer")
CATEGORIES = (
    "implementation",
    "debugging",
    "testing",
    "maintenance",
    "architecture",
    "security",
    "policy",
    "review",
    "release-gate",
    "mixed",
)
_CATEGORY_KEYWORDS = (
    ("release-gate", ("release gate", "release", "ship gate")),
    ("security", ("security", "threat", "auth", "guardrail", "vulnerability")),
    ("policy", ("policy", "governance", "rulebook", "instructions")),
    ("architecture", ("architecture", "architect", "system design")),
    ("review", ("review", "audit", "assess")),
    ("testing", ("test", "coverage", "regression")),
    ("debugging", ("debug", "bug", "fix", "failure")),
    ("maintenance", ("maintain", "refactor", "cleanup", "upgrade")),
    ("implementation", ("implement", "build", "create", "add")),
)


class CoordinationError(RuntimeError):
    """A fail-closed coordination protocol violation."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            preferred_builder TEXT NOT NULL,
            assigned_builder TEXT,
            assigned_reviewer TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leases (
            resource TEXT PRIMARY KEY,
            agent TEXT NOT NULL,
            task_id TEXT NOT NULL,
            role TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(task_id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            kind TEXT NOT NULL,
            body TEXT NOT NULL,
            snapshot TEXT,
            created_at TEXT NOT NULL,
            read_at TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(task_id)
        );
        CREATE TABLE IF NOT EXISTS verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            verdict TEXT NOT NULL,
            summary TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(task_id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            agent TEXT NOT NULL,
            event TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    return conn


def _git(args: Iterable[str], *, root: Path = ROOT) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise CoordinationError(
            f"git {' '.join(args)} failed: {completed.stderr.decode(errors='replace').strip()}"
        )
    return completed.stdout


def worktree_dirty(*, root: Path = ROOT) -> bool:
    return bool(_git(["status", "--porcelain=v1"], root=root).strip())


def tree_snapshot(*, root: Path = ROOT) -> str:
    """Hash HEAD, tracked diffs, and untracked file contents."""
    digest = hashlib.sha256()
    digest.update(_git(["rev-parse", "HEAD"], root=root))
    digest.update(_git(["diff", "--binary", "HEAD", "--", "."], root=root))
    untracked = _git(
        ["ls-files", "--others", "--exclude-standard", "-z"], root=root
    ).split(b"\0")
    for raw in sorted(item for item in untracked if item):
        relative = raw.decode("utf-8", errors="surrogateescape")
        target = root / relative
        digest.update(raw)
        if target.is_file():
            digest.update(target.read_bytes())
    return digest.hexdigest()


def _reviewer_for(conn: sqlite3.Connection, builder: str) -> str:
    """Pick the least-loaded reviewer among the other agents."""
    candidates = [agent for agent in AGENTS if agent != builder]
    counts = {agent: 0 for agent in candidates}
    for row in conn.execute(
        "SELECT assigned_reviewer, COUNT(*) AS count FROM tasks GROUP BY assigned_reviewer"
    ):
        agent = str(row["assigned_reviewer"])
        if agent in counts:
            counts[agent] = int(row["count"])
    return min(candidates, key=lambda agent: (counts[agent], AGENTS.index(agent)))


def route(conn: sqlite3.Connection, category: str) -> tuple[str, str]:
    """Balance automatic builder assignments equally across supported agents."""
    if category not in CATEGORIES:
        raise CoordinationError(f"unsupported category: {category}")
    counts = {agent: 0 for agent in AGENTS}
    for row in conn.execute(
        "SELECT preferred_builder, COUNT(*) AS count FROM tasks GROUP BY preferred_builder"
    ):
        agent = str(row["preferred_builder"])
        if agent in counts:
            counts[agent] = int(row["count"])
    builder = min(AGENTS, key=lambda agent: (counts[agent], AGENTS.index(agent)))
    reviewer = _reviewer_for(conn, builder)
    return builder, reviewer


def recommend_category(title: str) -> str:
    """Suggest a deterministic routing category from a task title."""
    lowered = " ".join(title.lower().split())
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "mixed"


def create_task(
    conn: sqlite3.Connection,
    task_id: str,
    title: str,
    category: str | None,
    *,
    builder_override: str | None = None,
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        category = category or recommend_category(title)
        builder, reviewer = route(conn, category)
        if builder_override is not None:
            if builder_override not in AGENTS:
                raise CoordinationError(f"unsupported builder override: {builder_override}")
            builder = builder_override
            reviewer = _reviewer_for(conn, builder)
        now = _iso()
        conn.execute(
            "INSERT INTO tasks (task_id, title, category, preferred_builder, "
            "assigned_reviewer, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, category, builder, reviewer, now, now),
        )
        _event(
            conn, task_id, "operator", "routed", f"builder={builder}; reviewer={reviewer}"
        )
        conn.commit()
        return {
            "task_id": task_id,
            "builder": builder,
            "reviewer": reviewer,
            "status": "queued",
        }
    except Exception:
        conn.rollback()
        raise


def _task(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if row is None:
        raise CoordinationError(f"unknown task: {task_id}")
    return row


def _active_writer(
    conn: sqlite3.Connection, *, commit_expiry: bool = False
) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM leases WHERE resource = 'worktree'").fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(str(row["expires_at"])) > _now():
        return row
    conn.execute("DELETE FROM leases WHERE resource = 'worktree'")
    _event(
        conn,
        str(row["task_id"]),
        str(row["agent"]),
        "lease_expired",
        "writer lease expired",
    )
    if commit_expiry:
        conn.commit()
    return None


def claim(
    conn: sqlite3.Connection,
    task_id: str,
    agent: str,
    role: str,
    *,
    ttl_minutes: int = 30,
    adopt_dirty: bool = False,
    override_routing: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = _task(conn, task_id)
        if agent not in AGENTS or role not in ROLES:
            raise CoordinationError("agent/role is unsupported")
        if role == "reviewer":
            result = _claim_reviewer(
                conn, task, task_id, agent, override_routing=override_routing
            )
        else:
            result = _claim_builder(
                conn,
                task,
                task_id,
                agent,
                ttl_minutes=ttl_minutes,
                adopt_dirty=adopt_dirty,
                override_routing=override_routing,
                root=root,
            )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _claim_reviewer(
    conn: sqlite3.Connection,
    task: sqlite3.Row,
    task_id: str,
    agent: str,
    *,
    override_routing: bool,
) -> dict[str, Any]:
    assigned = str(task["assigned_reviewer"] or "")
    if str(task["assigned_builder"] or "") == agent:
        raise CoordinationError("builder cannot review their own task")
    if assigned and assigned != agent and not override_routing:
        raise CoordinationError(
            f"review assigned to {assigned}; explicit --override-routing is required"
        )
    conn.execute(
        "UPDATE tasks SET assigned_reviewer = ?, updated_at = ? WHERE task_id = ?",
        (agent, _iso(), task_id),
    )
    _event(conn, task_id, agent, "reviewer_claimed", "read-only review role")
    return {"task_id": task_id, "agent": agent, "role": "reviewer", "read_only": True}


def _claim_builder(
    conn: sqlite3.Connection,
    task: sqlite3.Row,
    task_id: str,
    agent: str,
    *,
    ttl_minutes: int,
    adopt_dirty: bool,
    override_routing: bool,
    root: Path,
) -> dict[str, Any]:
    preferred = str(task["preferred_builder"])
    if preferred != agent and not override_routing:
        raise CoordinationError(
            f"build assigned to {preferred}; explicit --override-routing is required"
        )
    active = _active_writer(conn)
    if active is not None and (
        str(active["agent"]) != agent or str(active["task_id"]) != task_id
    ):
        raise CoordinationError(
            f"worktree writer lease held by {active['agent']} for {active['task_id']}"
        )
    if active is None and worktree_dirty(root=root) and not adopt_dirty:
        raise CoordinationError("worktree is dirty; explicit --adopt-dirty is required")
    now = _now()
    expires = now + timedelta(minutes=max(1, min(240, ttl_minutes)))
    conn.execute(
        "INSERT INTO leases (resource, agent, task_id, role, acquired_at, heartbeat_at, "
        "expires_at) VALUES ('worktree', ?, ?, 'builder', ?, ?, ?) "
        "ON CONFLICT(resource) DO UPDATE SET agent=excluded.agent, task_id=excluded.task_id, "
        "role=excluded.role, acquired_at=excluded.acquired_at, "
        "heartbeat_at=excluded.heartbeat_at, expires_at=excluded.expires_at",
        (agent, task_id, _iso(now), _iso(now), _iso(expires)),
    )
    conn.execute(
        "UPDATE tasks SET assigned_builder = ?, status = 'building', updated_at = ? "
        "WHERE task_id = ?",
        (agent, _iso(now), task_id),
    )
    detail = (
        f"ttl_minutes={ttl_minutes}; adopted_dirty={adopt_dirty}; "
        f"override_routing={override_routing}"
    )
    _event(conn, task_id, agent, "builder_claimed", detail)
    return {
        "task_id": task_id,
        "agent": agent,
        "role": "builder",
        "expires_at": _iso(expires),
        "preferred_builder": preferred,
    }


def heartbeat(
    conn: sqlite3.Connection, agent: str, *, ttl_minutes: int = 30
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        active = _active_writer(conn)
        if active is None or str(active["agent"]) != agent:
            raise CoordinationError(f"{agent} does not hold the writer lease")
        expires = _now() + timedelta(minutes=max(1, min(240, ttl_minutes)))
        conn.execute(
            "UPDATE leases SET heartbeat_at = ?, expires_at = ? "
            "WHERE resource = 'worktree' AND agent = ?",
            (_iso(), _iso(expires), agent),
        )
        conn.commit()
        return {
            "agent": agent,
            "task_id": str(active["task_id"]),
            "expires_at": _iso(expires),
        }
    except Exception:
        conn.rollback()
        raise


def release(
    conn: sqlite3.Connection,
    task_id: str,
    agent: str,
    *,
    allow_dirty: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Release the writer lease without a review handoff."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        active = _active_writer(conn)
        if (
            active is None
            or str(active["agent"]) != agent
            or str(active["task_id"]) != task_id
        ):
            raise CoordinationError("release requires the task's active writer lease")
        if worktree_dirty(root=root) and not allow_dirty:
            raise CoordinationError("worktree is dirty; use handoff or explicit --allow-dirty")
        conn.execute(
            "DELETE FROM leases WHERE resource = 'worktree' AND agent = ? AND task_id = ?",
            (agent, task_id),
        )
        conn.execute(
            "UPDATE tasks SET status = 'queued', updated_at = ? WHERE task_id = ?",
            (_iso(), task_id),
        )
        _event(conn, task_id, agent, "lease_released", f"allow_dirty={allow_dirty}")
        conn.commit()
        return {"task_id": task_id, "agent": agent, "status": "queued"}
    except Exception:
        conn.rollback()
        raise


def send_message(
    conn: sqlite3.Connection,
    task_id: str,
    sender: str,
    recipient: str,
    kind: str,
    body: str,
    *,
    snapshot: str | None = None,
) -> int:
    _task(conn, task_id)
    if sender not in AGENTS or recipient not in AGENTS or sender == recipient:
        raise CoordinationError("messages require two distinct supported agents")
    message_id = _insert_message(
        conn, task_id, sender, recipient, kind, body, snapshot=snapshot
    )
    _event(conn, task_id, sender, "message_sent", f"to={recipient}; kind={kind}")
    conn.commit()
    return message_id


def _insert_message(
    conn: sqlite3.Connection,
    task_id: str,
    sender: str,
    recipient: str,
    kind: str,
    body: str,
    *,
    snapshot: str | None = None,
) -> int:
    cleaned = body.strip()
    if not cleaned:
        raise CoordinationError("message body is required")
    if len(cleaned) > 8000:
        raise CoordinationError("message body exceeds 8000 characters")
    cur = conn.execute(
        "INSERT INTO messages (task_id, sender, recipient, kind, body, snapshot, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (task_id, sender, recipient, kind, cleaned, snapshot, _iso()),
    )
    return int(cur.lastrowid)


def handoff(
    conn: sqlite3.Connection,
    task_id: str,
    sender: str,
    recipient: str,
    summary: str,
    evidence: str,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    if sender == recipient:
        raise CoordinationError("handoff requires an independent reviewer")
    conn.execute("BEGIN IMMEDIATE")
    try:
        active = _active_writer(conn)
        if (
            active is None
            or str(active["agent"]) != sender
            or str(active["task_id"]) != task_id
        ):
            raise CoordinationError("handoff requires the task's active writer lease")
        snapshot = tree_snapshot(root=root)
        body = f"{summary.strip()}\n\nEvidence:\n{evidence.strip()}"
        message_id = _insert_message(
            conn, task_id, sender, recipient, "handoff", body, snapshot=snapshot
        )
        _event(conn, task_id, sender, "message_sent", f"to={recipient}; kind=handoff")
        conn.execute("DELETE FROM leases WHERE resource = 'worktree'")
        conn.execute(
            "UPDATE tasks SET assigned_reviewer = ?, status = 'review', updated_at = ? "
            "WHERE task_id = ?",
            (recipient, _iso(), task_id),
        )
        _event(conn, task_id, sender, "handoff", f"to={recipient}; snapshot={snapshot}")
        conn.commit()
        return {"message_id": message_id, "snapshot": snapshot, "status": "review"}
    except Exception:
        conn.rollback()
        raise


def record_verdict(
    conn: sqlite3.Connection,
    task_id: str,
    reviewer: str,
    verdict: str,
    summary: str,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    if verdict not in {"approve", "changes_requested", "blocked"}:
        raise CoordinationError("unsupported verdict")
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = _task(conn, task_id)
        if str(task["assigned_reviewer"] or "") != reviewer:
            raise CoordinationError(f"{reviewer} is not the assigned reviewer")
        handoff_row = conn.execute(
            "SELECT snapshot, sender FROM messages WHERE task_id = ? AND kind = 'handoff' "
            "ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if handoff_row is None or not handoff_row["snapshot"]:
            raise CoordinationError("no handoff snapshot exists")
        if str(handoff_row["sender"]) == reviewer:
            raise CoordinationError("builder cannot approve their own handoff")
        current = tree_snapshot(root=root)
        if current != str(handoff_row["snapshot"]):
            raise CoordinationError("worktree changed after handoff; reviewer verdict refused")
        conn.execute(
            "INSERT INTO verdicts (task_id, reviewer, verdict, summary, snapshot, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, reviewer, verdict, summary.strip(), current, _iso()),
        )
        task_status = {
            "approve": "approved",
            "changes_requested": "changes_requested",
            "blocked": "blocked",
        }[verdict]
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (task_status, _iso(), task_id),
        )
        _insert_message(
            conn,
            task_id,
            reviewer,
            str(handoff_row["sender"]),
            "verdict",
            f"{verdict}: {summary.strip()}",
            snapshot=current,
        )
        _event(
            conn,
            task_id,
            reviewer,
            "message_sent",
            f"to={handoff_row['sender']}; kind=verdict",
        )
        _event(conn, task_id, reviewer, "verdict", verdict)
        conn.commit()
        return {
            "task_id": task_id,
            "verdict": verdict,
            "snapshot": current,
            "status": task_status,
        }
    except Exception:
        conn.rollback()
        raise


def inbox(
    conn: sqlite3.Connection, agent: str, *, unread_only: bool = False, mark_read: bool = False
) -> list[dict[str, Any]]:
    query = "SELECT * FROM messages WHERE recipient = ?"
    params: list[Any] = [agent]
    if unread_only:
        query += " AND read_at IS NULL"
    query += " ORDER BY id"
    rows = conn.execute(query, params).fetchall()
    if mark_read and rows:
        conn.executemany(
            "UPDATE messages SET read_at = ? WHERE id = ?",
            [(_iso(), int(row["id"])) for row in rows],
        )
        conn.commit()
    return [dict(row) for row in rows]


def status(conn: sqlite3.Connection, *, root: Path = ROOT) -> dict[str, Any]:
    active = _active_writer(conn, commit_expiry=True)
    tasks = [dict(row) for row in conn.execute("SELECT * FROM tasks ORDER BY created_at")]
    return {
        "active_writer": dict(active) if active is not None else None,
        "worktree_dirty": worktree_dirty(root=root),
        "tasks": tasks,
        "unread": {
            agent: int(
                conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE recipient = ? AND read_at IS NULL",
                    (agent,),
                ).fetchone()[0]
            )
            for agent in AGENTS
        },
    }


def brief(conn: sqlite3.Connection, agent: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Return the minimum coordination state an agent needs at bootstrap."""
    return {
        "agent": agent,
        "coordination": status(conn, root=root),
        "inbox": inbox(conn, agent, unread_only=True),
    }


def _event(
    conn: sqlite3.Connection, task_id: str | None, agent: str, event: str, detail: str
) -> None:
    conn.execute(
        "INSERT INTO events (task_id, agent, event, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, agent, event, detail, _iso()),
    )


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    # The git worktree whose tree is hash-pinned on handoff/verdict and checked
    # for dirtiness on claim/release. Defaults to this repo; override for a
    # separate worktree (true parallel lanes) or to isolate a test from the
    # live tree (a CLI test must not depend on the real repo staying frozen).
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")
    route_cmd = sub.add_parser("route")
    route_cmd.add_argument("task_id")
    route_cmd.add_argument("title")
    route_cmd.add_argument("--category", choices=CATEGORIES)
    route_cmd.add_argument("--builder", choices=AGENTS)

    claim_cmd = sub.add_parser("claim")
    claim_cmd.add_argument("task_id")
    claim_cmd.add_argument("--agent", choices=AGENTS, required=True)
    claim_cmd.add_argument("--role", choices=ROLES, required=True)
    claim_cmd.add_argument("--ttl-minutes", type=int, default=30)
    claim_cmd.add_argument("--adopt-dirty", action="store_true")
    claim_cmd.add_argument("--override-routing", action="store_true")

    heartbeat_cmd = sub.add_parser("heartbeat")
    heartbeat_cmd.add_argument("--agent", choices=AGENTS, required=True)
    heartbeat_cmd.add_argument("--ttl-minutes", type=int, default=30)

    release_cmd = sub.add_parser("release")
    release_cmd.add_argument("task_id")
    release_cmd.add_argument("--agent", choices=AGENTS, required=True)
    release_cmd.add_argument("--allow-dirty", action="store_true")

    message_cmd = sub.add_parser("message")
    message_cmd.add_argument("task_id")
    message_cmd.add_argument("--from", dest="sender", choices=AGENTS, required=True)
    message_cmd.add_argument("--to", dest="recipient", choices=AGENTS, required=True)
    message_cmd.add_argument("--kind", default="note")
    message_cmd.add_argument("--body", required=True)

    handoff_cmd = sub.add_parser("handoff")
    handoff_cmd.add_argument("task_id")
    handoff_cmd.add_argument("--from", dest="sender", choices=AGENTS, required=True)
    handoff_cmd.add_argument("--to", dest="recipient", choices=AGENTS, required=True)
    handoff_cmd.add_argument("--summary", required=True)
    handoff_cmd.add_argument("--evidence", required=True)

    verdict_cmd = sub.add_parser("verdict")
    verdict_cmd.add_argument("task_id")
    verdict_cmd.add_argument("--reviewer", choices=AGENTS, required=True)
    verdict_cmd.add_argument(
        "--verdict", choices=("approve", "changes_requested", "blocked"), required=True
    )
    verdict_cmd.add_argument("--summary", required=True)

    inbox_cmd = sub.add_parser("inbox")
    inbox_cmd.add_argument("--agent", choices=AGENTS, required=True)
    inbox_cmd.add_argument("--unread-only", action="store_true")
    inbox_cmd.add_argument("--mark-read", action="store_true")

    brief_cmd = sub.add_parser("brief")
    brief_cmd.add_argument("--agent", choices=AGENTS, required=True)

    sub.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        conn = _connect(args.db)
        if args.command == "init":
            result: object = {"db": str(args.db), "status": "initialized"}
        elif args.command == "route":
            result = create_task(
                conn,
                args.task_id,
                args.title,
                args.category,
                builder_override=args.builder,
            )
        elif args.command == "claim":
            result = claim(
                conn,
                args.task_id,
                args.agent,
                args.role,
                ttl_minutes=args.ttl_minutes,
                adopt_dirty=args.adopt_dirty,
                override_routing=args.override_routing,
                root=args.root,
            )
        elif args.command == "heartbeat":
            result = heartbeat(conn, args.agent, ttl_minutes=args.ttl_minutes)
        elif args.command == "release":
            result = release(
                conn, args.task_id, args.agent, allow_dirty=args.allow_dirty, root=args.root
            )
        elif args.command == "message":
            result = {
                "message_id": send_message(
                    conn, args.task_id, args.sender, args.recipient, args.kind, args.body
                )
            }
        elif args.command == "handoff":
            result = handoff(
                conn,
                args.task_id,
                args.sender,
                args.recipient,
                args.summary,
                args.evidence,
                root=args.root,
            )
        elif args.command == "verdict":
            result = record_verdict(
                conn, args.task_id, args.reviewer, args.verdict, args.summary, root=args.root
            )
        elif args.command == "inbox":
            result = inbox(
                conn, args.agent, unread_only=args.unread_only, mark_read=args.mark_read
            )
        elif args.command == "brief":
            result = brief(conn, args.agent, root=args.root)
        else:
            result = status(conn, root=args.root)
        _print(result)
        return 0
    except CoordinationError as exc:
        print(f"coordination error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
