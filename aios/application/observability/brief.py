"""GAGOS speaks first: the brief it gives the operator when he opens the face.

2026-11-24, the operator: "remember GAGOS ~ jarvis, it should honestly behave
like one". Measured that day, most of GAGOS's being only woke inside a turn he
started, and he had stopped starting them; nothing told him what GAGOS had done,
what waited on him, or what had broken. A Jarvis says so unasked.

The brief is three short lists of facts, each read from GAGOS's own stores:

* **did** -- since he last looked: the pull requests GAGOS delivered, its
  changes accepted, rejected and refused by their reviewers, the goals it took;
* **waiting** -- now: GAGOS's pull requests not yet seen merged, an envelope
  that has ended, organs whose evidence waits on his attestation;
* **broke** -- now: the emergency stop engaged, an hour that was blocked or
  failed, the hourly job gone silent.

It is facts only, composed here without a model, so a line is never a guess.
:func:`compose` is pure; :func:`gather` reads the stores read-only (organ 52,
Observability and Health, beside the aliveness pulse) and changes nothing.
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

#: The hourly job runs every hour; this long without a recorded hour is silence.
SILENT_AFTER = timedelta(hours=3)
#: At most this many lines in a list; the rest are counted, never dropped silently.
MAX_LINES = 6
_PR_NUMBER = re.compile(r"/pull/(\d+)$")


def _pr(url: str) -> str:
    match = _PR_NUMBER.search(url or "")
    return f"#{match.group(1)}" if match else url


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


@dataclass(frozen=True)
class Brief:
    """What GAGOS tells him first: facts, in three lists."""

    since: str
    now: str
    did: tuple[str, ...] = ()
    waiting: tuple[str, ...] = ()
    broke: tuple[str, ...] = ()

    @property
    def quiet(self) -> bool:
        return not (self.did or self.waiting or self.broke)

    def as_dict(self) -> dict[str, Any]:
        return {
            "since": self.since,
            "now": self.now,
            "did": list(self.did),
            "waiting": list(self.waiting),
            "broke": list(self.broke),
            "quiet": self.quiet,
        }


def _capped(lines: list[str]) -> tuple[str, ...]:
    if len(lines) <= MAX_LINES:
        return tuple(lines)
    rest = len(lines) - (MAX_LINES - 1)
    return tuple(lines[: MAX_LINES - 1]) + (f"and {rest} more",)


@dataclass(frozen=True)
class Facts:
    """The facts a brief is composed from; every field is read from a store."""

    since: datetime
    now: datetime
    #: GAGOS's deliveries: ``pr_url``, ``created_at`` (ISO).
    deliveries: tuple[Mapping[str, Any], ...] = ()
    #: The pull requests GAGOS has seen merged.
    merged: frozenset[str] = frozenset()
    #: Its proposals since *since*: ``status`` of each.
    proposal_statuses: tuple[str, ...] = ()
    #: Goals it took since *since*.
    goals_taken: int = 0
    #: ``status()`` of the mission envelope and of the skill envelope.
    mission_envelope: Mapping[str, Any] = field(default_factory=dict)
    skill_envelope: Mapping[str, Any] = field(default_factory=dict)
    #: Organs whose live evidence waits on his attestation: (id, name).
    attestation_waits: tuple[tuple[int, str], ...] = ()
    stop_engaged: bool = False
    #: Its hours: ``day`` (slot), ``status``, ``reason``, ``updated_at``.
    hours: tuple[Mapping[str, Any], ...] = ()


def _when(value: Any) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def compose(facts: Facts) -> Brief:
    """The brief, from *facts* alone: deterministic, no model, no store."""
    did: list[str] = []
    recent = [
        d
        for d in facts.deliveries
        if (w := _when(d.get("created_at"))) is not None and w >= facts.since
    ]
    delivered = sorted({_pr(d["pr_url"]) for d in recent if d.get("pr_url")})
    if delivered:
        did.append(
            f"Delivered {_plural(len(delivered), 'pull request')}: {', '.join(delivered)}."
        )
    counts: dict[str, int] = {}
    for status in facts.proposal_statuses:
        counts[status] = counts.get(status, 0) + 1
    judged = [
        (counts.get("delivered", 0) + counts.get("accepted", 0), "accepted"),
        (counts.get("rejected", 0), "rejected by its reviewer"),
        (counts.get("refused", 0), "refused before review"),
    ]
    parts = [f"{n} {what}" for n, what in judged if n]
    if parts:
        did.append(f"Its changes: {', '.join(parts)}.")
    if facts.goals_taken:
        did.append(f"Took {_plural(facts.goals_taken, 'goal')}.")

    waiting: list[str] = []
    open_prs = sorted(
        {
            d["pr_url"]
            for d in facts.deliveries
            if d.get("pr_url") and d["pr_url"] not in facts.merged
        },
        key=lambda u: int(m.group(1)) if (m := _PR_NUMBER.search(u)) else 0,
    )
    for url in open_prs:
        waiting.append(f"GAGOS's pull request {_pr(url)} is not yet seen merged.")
    mission = facts.mission_envelope
    if not mission.get("live"):
        waiting.append(
            "No mission envelope is live"
            + (f" ({mission['reason']})" if mission.get("reason") else "")
            + ", so GAGOS starts no council missions."
        )
    skill = facts.skill_envelope
    if skill and not skill.get("live"):
        waiting.append(
            "No skill envelope is live"
            + (f" ({skill['reason']})" if skill.get("reason") else "")
            + ", so GAGOS activates no skills."
        )
    for organ_id, name in facts.attestation_waits:
        waiting.append(f"Organ {organ_id} ({name}) waits on your attestation.")

    broke: list[str] = []
    if facts.stop_engaged:
        broke.append(
            "The emergency stop is engaged; GAGOS does nothing until you clear it."
        )
    for hour in facts.hours:
        when = _when(hour.get("updated_at"))
        if when is None or when < facts.since:
            continue
        if hour.get("status") != "ran":
            broke.append(
                f"Hour {hour.get('day')} was {hour.get('status')}: {hour.get('reason')}."
            )
        elif hour.get("reason"):
            broke.append(f"Hour {hour.get('day')} failed: {hour.get('reason')}.")
    last = max(
        (w for h in facts.hours if (w := _when(h.get("updated_at"))) is not None),
        default=None,
    )
    if last is None:
        broke.append("GAGOS's hourly job has no recorded hour.")
    elif facts.now - last > SILENT_AFTER:
        hours = int((facts.now - last).total_seconds() // 3600)
        broke.append(
            f"GAGOS's hourly job has been silent for {hours} hours "
            f"(last at {last.strftime('%Y-%m-%d %H:%M')} UTC)."
        )

    return Brief(
        since=facts.since.isoformat(),
        now=facts.now.isoformat(),
        did=_capped(did),
        waiting=_capped(waiting),
        broke=_capped(broke),
    )


# -- reading the stores (read-only) ---------------------------------------------


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def ledger_facts(ledger_db: Path, since: datetime) -> dict[str, Any]:
    """Deliveries, merges, proposals, goals and hours from GAGOS's daily ledger."""
    if not ledger_db.is_file():
        return {}
    cutoff = since.isoformat()
    conn = _readonly(ledger_db)
    try:
        deliveries = tuple(
            dict(r)
            for r in conn.execute(
                "SELECT pr_url, created_at FROM deliveries "
                "WHERE outcome = 'delivered' AND pr_url IS NOT NULL AND pr_url != ''"
            )
        )
        merged = frozenset(r[0] for r in conn.execute("SELECT pr_url FROM merged_prs"))
        statuses = tuple(
            r[0]
            for r in conn.execute(
                "SELECT status FROM proposals WHERE created_at >= ?", (cutoff,)
            )
        )
        taken = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'taken' AND updated_at >= ?",
            (cutoff,),
        ).fetchone()[0]
        hours = tuple(
            dict(r)
            for r in conn.execute(
                "SELECT day, status, reason, updated_at FROM days "
                "ORDER BY updated_at DESC LIMIT 48"
            )
        )
    finally:
        conn.close()
    return {
        "deliveries": deliveries,
        "merged": merged,
        "proposal_statuses": statuses,
        "goals_taken": int(taken),
        "hours": hours,
    }


def attestation_waits(
    organs: Iterable[Mapping[str, Any]],
) -> tuple[tuple[int, str], ...]:
    """Yellow organs whose live-evidence condition (C10) waits on his attestation."""
    waits = []
    for organ in organs:
        if organ.get("status") != "yellow":
            continue
        c10 = str((organ.get("condition_verdicts") or {}).get("C10", ""))
        if c10.upper().startswith("WAITING") and "attestation" in c10.lower():
            waits.append((int(organ["organ_id"]), str(organ.get("name", ""))))
    return tuple(waits)


def organ_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def gather(
    *,
    since: datetime,
    now: datetime,
    ledger_db: Path,
    organ_ledger_path: Path,
    mission_envelope: Mapping[str, Any],
    skill_envelope: Mapping[str, Any],
    stop_engaged: bool,
) -> Brief:
    """The brief from the stores as they are now; reads only."""
    found = ledger_facts(ledger_db, since)
    return compose(
        Facts(
            since=since,
            now=now,
            mission_envelope=mission_envelope,
            skill_envelope=skill_envelope,
            attestation_waits=attestation_waits(organ_ledger(organ_ledger_path)),
            stop_engaged=stop_engaged,
            **found,
        )
    )


__all__ = [
    "Brief",
    "Facts",
    "MAX_LINES",
    "SILENT_AFTER",
    "attestation_waits",
    "compose",
    "gather",
    "ledger_facts",
]
