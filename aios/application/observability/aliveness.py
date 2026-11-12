"""The aliveness pulse: which parts of GAGOS do real work, measured daily.

2026-11-12, the operator: "are we using SWARM infra... there can be many things
like this honestly". Measured that day, only the workshop's writers, the clerk
and the gateway's governed calls did real work; whole organs had last run in a
proof harness or never. It had been found by accident, one part at a time.
This pulse makes it a standing measurement (organ 52, Observability and Health):

* every store GAGOS keeps -- each table's rows and newest timestamp, across the
  databases in its data directory (backups and probes left out);
* the cortex bus -- each event type's last occurrence, and which kind of work
  the Worker Foundry ran (the workshop, the swarm, a mission);
* a map of what each organ and subsystem leaves behind when it works
  (:data:`PARTS`). Every organ of the ledger must declare it -- a test holds
  that -- so a new organ cannot go silent unseen.

Read-only: it opens every database read-only and changes nothing. A guard that
only checks and never fires, the face, and evaluation organs leave nothing to
measure; they are named as such, never counted as alive or dead.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LIVE_DAYS = 2
RECENT_DAYS = 14

#: Kinds of part that leave nothing to measure.
GUARD, FACE, EVALUATION = "guard", "face", "evaluation"

#: Worker sources the Foundry's events carry (``missionId`` / ``sessionId``).
WORKSHOP, SWARM, MISSION = "workshop", "swarm", "mission"

#: Turns: what every turn-scoped organ is last seen in.
TURN = ("turn.started", "turn.completed")


@dataclass(frozen=True)
class Part:
    """One organ or subsystem and the evidence it leaves when it works."""

    key: str
    name: str
    tables: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    workers: tuple[str, ...] = ()
    kind: str = ""  # GUARD / FACE / EVALUATION when nothing is measurable


def _organ(n: int, name: str, **kw: Any) -> Part:
    return Part(f"organ-{n}", f"{n} {name}", **kw)


#: What each part leaves behind (measured 2026-11-12, "GAGOS aliveness map").
PARTS: tuple[Part, ...] = (
    _organ(1, "Security Gateway", tables=("security_rate_limits",), events=TURN),
    _organ(2, "Scope Lock", events=TURN),
    _organ(3, "Secret Scanner", tables=("proposals",), events=TURN),
    _organ(4, "Tamper-Evident Audit Logger", tables=("tamper_audit_trail",)),
    _organ(5, "Prompt Injection Shield", events=TURN),
    _organ(6, "Edge Trust Boundary", kind=GUARD),
    _organ(7, "Policy Kernel", events=TURN),
    _organ(8, "Action Broker", events=TURN),
    _organ(9, "Exact Capability Authority", tables=("approval_grants",), events=TURN),
    _organ(10, "Mission Authority", tables=("missions",), workers=(MISSION,)),
    _organ(11, "Turn Coordinator", events=TURN),
    _organ(12, "Worker Foundry", workers=(WORKSHOP, SWARM, MISSION)),
    _organ(13, "Isolated Executor Service", workers=(MISSION,)),
    _organ(14, "Staged Workspace Manager", workers=(MISSION,)),
    _organ(15, "Evidence and Verification Authority", tables=("verification_results",)),
    _organ(16, "Promotion Authority", tables=("promotion_records",)),
    _organ(17, "Cortex Observation Bus", tables=("cortex_events",)),
    _organ(
        18,
        "Memory Authority",
        tables=("memory_authority_records", "memory_authority_proposals"),
    ),
    _organ(19, "Emergency Stop Controller", kind=GUARD),
    _organ(20, "Living Mirror Reaction Registry", kind=FACE),
    _organ(21, "Queen Council Orchestrator", tables=("council_events", "reviews")),
    _organ(22, "V1 Release Declaration", kind=EVALUATION),
    _organ(23, "Release Conformance Organ", kind=EVALUATION),
    _organ(24, "Human Sovereign Identity", kind=GUARD),
    _organ(25, "Constitutional Kernel", tables=("representative_contexts",)),
    _organ(26, "Emergency Stop Organ", kind=GUARD),
    _organ(
        27,
        "Operator Taste Model",
        tables=("alignment_observations",),
        events=("alignment",),
    ),
    _organ(28, "Project Understanding Organ", tables=("project_passports",)),
    _organ(29, "Correction and Interpretation-Lineage", tables=("correction_records",)),
    _organ(
        30,
        "Communication and Human-State Interpreter",
        tables=("human_state_hypotheses",),
    ),
    _organ(
        31, "Human Representative Context Compiler", tables=("representative_contexts",)
    ),
    _organ(
        32,
        "Universal Intelligence Gateway",
        tables=("representative_contexts",),
        events=("route.selected",),
    ),
    _organ(
        33, "Model Registry and Capability Passport", tables=("local_worker_models",)
    ),
    _organ(34, "Cloud Budget and Provider-Health", tables=("spend",)),
    _organ(35, "Local Clerk Runtime", tables=("local_job_requests",)),
    _organ(36, "Clerical Job Contract and Dispatcher", tables=("local_job_requests",)),
    _organ(37, "Local Model Qualification and Health", tables=("local_worker_models",)),
    _organ(38, "Durable Local-Clerk Provenance", tables=("local_model_calls",)),
    _organ(
        39, "Multi-Model Deliberation and Dissent", tables=("deliberation_records",)
    ),
    _organ(40, "Isolated Workspace and Executor (live proof)", workers=(MISSION,)),
    _organ(41, "Promotion, Checkpoint and Rollback", tables=("promotion_records",)),
    _organ(42, "Recovery and Resumption", tables=("mission_execution_transitions",)),
    _organ(
        43,
        "Local Skill Reuse, Confidence and Demotion",
        tables=("skill_trails", "reuse_outcomes"),
    ),
    _organ(44, "Golden Mission and Endurance Evaluation", kind=EVALUATION),
    _organ(
        45,
        "Constitutional Amendment Authority",
        tables=("constitution_snapshots", "governance_amendment_proposals"),
    ),
    _organ(
        46,
        "Constitutional Learning Organ",
        tables=("governance_lessons", "governance_amendment_proposals"),
    ),
    _organ(
        47,
        "Read-Model and Projection Organ",
        tables=("active_turns", "active_missions", "active_workers"),
    ),
    _organ(48, "Truthful Living Mirror", kind=FACE),
    _organ(
        49,
        "Approval and Decision Surface",
        tables=("approval_pending", "approval_grants"),
    ),
    _organ(50, "Provenance and Explanation Surface", kind=FACE),
    _organ(51, "Sovereign Control and Heartbeat Surface", kind=FACE),
    _organ(52, "Observability and Health", kind=GUARD),
    _organ(
        53,
        "Installation, Configuration and Key Authority",
        tables=("api_token_rotation",),
    ),
    _organ(54, "Backup and Disaster-Recovery", kind=GUARD),
    _organ(55, "Governance Conformance Evaluation", kind=EVALUATION),
    _organ(56, "Learning Integrity and Provenance", tables=("learning_events",)),
    _organ(
        57, "Reflex Authority", events=("cerebellum.replayed", "cerebellum.abstained")
    ),
    _organ(58, "Recall Isolation", events=("memory.recalled",)),
    _organ(59, "Learning Freeze", kind=GUARD),
    Part("swarm", "Swarm (ant colony)", tables=("swarm_patterns",), workers=(SWARM,)),
    Part("workshop", "Workshop writers", workers=(WORKSHOP,)),
    Part(
        "workshop-learning",
        "Workshop learning (playbook, reflections)",
        tables=("playbook", "reflections"),
    ),
    Part("clerk-intake", "Clerk's goal intake", tables=("goal_intake",)),
    Part("counter", "The counter (conversation turns)", events=("turn.completed",)),
    Part(
        "memory",
        "Memory (episodic, semantic, mistake pool)",
        tables=("episodic_memory", "semantic_memory", "mistake_pool"),
    ),
    Part(
        "reflex",
        "Reflex (cerebellum)",
        events=("cerebellum.replayed", "cerebellum.abstained"),
    ),
    Part("skill-trails", "Skill trails (stigmergy)", tables=("skill_trails",)),
    Part(
        "skills",
        "Procedural and institutional skills",
        tables=("procedural_skills", "reuse_outcomes", "expert_trajectories"),
    ),
    Part(
        "knowledge-base",
        "Knowledge base for CRAG",
        tables=("knowledge_sources", "knowledge_chunks"),
    ),
    Part(
        "council-planning",
        "Council planning",
        tables=("council_events", "deliberation_records"),
    ),
    Part("curriculum", "Curriculum", tables=("curriculum_tasks",)),
    Part("self-analysis", "Self-analysis", tables=("self_analysis_report",)),
)

_TS = re.compile(
    r"(created|updated|time|_at$|^at$|^ts$|seen|date|recorded|started|ended|deposit|last)",
    re.I,
)
_SKIP = re.compile(r"backup|rehearsal|probe", re.I)


def _when(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = float(value) / (1000 if float(value) > 1e12 else 1)
            return (
                datetime.fromtimestamp(seconds, timezone.utc) if seconds > 1e9 else None
            )
        text = str(value).strip().replace("Z", "+00:00")[:32]
        moment = datetime.fromisoformat(text)
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


@dataclass
class Evidence:
    """What the stores and the bus show: per table ``(rows, newest)``, per
    event type its newest occurrence, per worker source its newest run."""

    tables: dict[str, tuple[int, datetime | None]] = field(default_factory=dict)
    events: dict[str, datetime] = field(default_factory=dict)
    workers: dict[str, datetime] = field(default_factory=dict)


def _ident(name: str) -> str:
    """An SQL identifier, quoted: the scan's table and column names come from
    each database's own catalog (``sqlite_master``, ``PRAGMA table_info``),
    never from a caller, and any ``"`` in one is doubled."""
    return '"' + name.replace('"', '""') + '"'


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def scan(data_dir: Path, *, now: datetime | None = None) -> Evidence:
    """Every table's rows and newest timestamp, the most active copy winning
    when a schema repeats across databases; then the cortex bus. Read-only."""
    now = now or datetime.now(timezone.utc)
    seen = Evidence()
    for db in sorted(Path(data_dir).rglob("*.db")):
        if _SKIP.search(str(db.relative_to(data_dir))):
            continue
        try:
            con = _readonly(db)
            tables = [
                r[0]
                for r in con.execute(
                    "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
                )
            ]
        except sqlite3.Error:
            continue
        for table in tables:
            try:
                rows = con.execute(f"select count(*) from {_ident(table)}").fetchone()[
                    0
                ]
                newest = None
                for (col,) in (
                    (c[1],) for c in con.execute(f"PRAGMA table_info({_ident(table)})")
                ):
                    if not _TS.search(col):
                        continue
                    moment = _when(
                        con.execute(
                            f"select max({_ident(col)}) from {_ident(table)}"
                        ).fetchone()[0]
                    )
                    if moment and moment <= now and (newest is None or moment > newest):
                        newest = moment
            except sqlite3.Error:
                continue
            had = seen.tables.get(table)
            if (
                had is None
                or (newest and (had[1] is None or newest > had[1]))
                or rows > had[0]
            ):
                seen.tables[table] = (
                    max(rows, had[0] if had else 0),
                    newest or (had[1] if had else None),
                )
        con.close()
    bus = Path(data_dir) / "cortex_bus.db"
    if bus.is_file():
        try:
            con = _readonly(bus)
            for kind, last in con.execute(
                "select event_type, max(created_at) from cortex_events group by event_type"
            ):
                moment = _when(last)
                if moment:
                    seen.events[kind] = moment
            for created, payload in con.execute(
                "select created_at, payload from cortex_events where event_type='worker.requested'"
            ):
                source = worker_source(payload)
                moment = _when(created)
                if moment and (
                    source not in seen.workers or moment > seen.workers[source]
                ):
                    seen.workers[source] = moment
            con.close()
        except sqlite3.Error:
            pass
    return seen


def worker_source(payload: str) -> str:
    """Which kind of work a ``worker.requested`` event belongs to, from the
    worker's own strategy and contract -- never from the files it touches
    (2026-11-12: workshop writers editing ``swarm_patterns.py`` and
    ``SwarmHUD.test.tsx`` had been counted as swarm runs)."""
    try:
        data = json.loads(payload or "{}")
    except ValueError:
        data = {}
    inner = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    strategy = str(inner.get("strategy") or data.get("strategy") or "").lower()
    contract = str(inner.get("contract_digest") or "").lower()
    mission = str(data.get("missionId") or "").lower()
    if strategy == "swarm" or contract.startswith("swarm"):
        return SWARM
    if contract.startswith("workshop-writer") or mission.startswith("gagos-"):
        return WORKSHOP
    if mission:
        return MISSION
    return "other"


@dataclass(frozen=True)
class Reading:
    part: Part
    status: str  # live / recent / stale / never / undated / guard / face / evaluation
    last: datetime | None
    why: str


def read(part: Part, seen: Evidence, *, now: datetime) -> Reading:
    """One part's status from its evidence."""
    if part.kind:
        return Reading(part, part.kind, None, "leaves nothing to measure")
    moments: list[tuple[datetime, str]] = []
    known = False
    for table in part.tables:
        if table in seen.tables:
            known = True
            rows, newest = seen.tables[table]
            if rows and newest:
                moments.append((newest, f"{table} ({rows} rows)"))
    for kind in part.events:
        if kind in seen.events:
            moments.append((seen.events[kind], f"event {kind}"))
    for source in part.workers:
        if source in seen.workers:
            moments.append((seen.workers[source], f"{source} workers"))
    if not moments:
        undated = [t for t in part.tables if seen.tables.get(t, (0, None))[0]]
        if undated:
            rows = sum(seen.tables[t][0] for t in undated)
            return Reading(
                part,
                "undated",
                None,
                f"{rows} rows in {', '.join(undated)}, no timestamp",
            )
        why = (
            "its stores have never held a row"
            if known
            else "nothing of it was ever recorded"
        )
        return Reading(part, "never", None, why)
    last, what = max(moments)
    age = now - last
    status = (
        "live"
        if age <= timedelta(days=LIVE_DAYS)
        else "recent"
        if age <= timedelta(days=RECENT_DAYS)
        else "stale"
    )
    return Reading(part, status, last, what)


def pulse(
    data_dir: Path, *, now: datetime | None = None, parts: Iterable[Part] = PARTS
) -> list[Reading]:
    """Every part's reading, measured now."""
    now = now or datetime.now(timezone.utc)
    seen = scan(data_dir, now=now)
    return [read(p, seen, now=now) for p in parts]


def summary(readings: Iterable[Reading]) -> Mapping[str, list[Reading]]:
    out: dict[str, list[Reading]] = {}
    for r in readings:
        out.setdefault(r.status, []).append(r)
    return out


def report_lines(readings: Iterable[Reading]) -> list[str]:
    """The pulse as the daily report's lines: counts, then every part that is
    not alive by name, with its last real activity."""
    by = summary(list(readings))
    order = (
        "live",
        "recent",
        "stale",
        "never",
        "undated",
        "guard",
        "face",
        "evaluation",
    )
    out = [
        "**Aliveness** (what each part last did, from its own stores and the "
        "cortex bus): "
        + ", ".join(f"{s} {len(by[s])}" for s in order if by.get(s))
        + ".",
    ]
    for status, label in (
        ("never", "never ran"),
        ("stale", f"silent over {RECENT_DAYS} days"),
        ("recent", f"silent {LIVE_DAYS + 1}-{RECENT_DAYS} days"),
    ):
        group = by.get(status) or []
        if group:
            names = "; ".join(
                f"{r.part.name}"
                + (f" (last {r.last.date().isoformat()})" if r.last else "")
                for r in group
            )
            out.append(f"- {label}: {names}")
    return [*out, ""]


__all__ = [
    "Evidence",
    "PARTS",
    "Part",
    "Reading",
    "pulse",
    "read",
    "report_lines",
    "scan",
    "summary",
    "worker_source",
]


if __name__ == "__main__":  # python -m aios.application.observability.aliveness
    from aios import config

    for r in pulse(Path(config.DATA_DIR)):
        when = r.last.isoformat()[:16] if r.last else "-"
        print(f"{r.status:10s} {when:17s} {r.part.name}  [{r.why}]")
