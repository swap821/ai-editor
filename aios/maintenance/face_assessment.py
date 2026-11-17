"""GAGOS's own assessment of its face (the operator, 2026-11-17: "let GAGOS
make its frontend 10/10 and also understand itself honestly"; GAGOS writes
its own goals).

Each hour GAGOS reads three things it already keeps, never a model's guess:

1. its acceptance ledger: the frozen 100-point denominator and what each
   criterion has earned. Points are awarded by acceptance, so GAGOS reads them
   and never writes them;
2. its journeys' design (which journey proves which criterion), and which of
   those journeys its runner has built;
3. its journey records, the newest run of each journey on master.

From them it says, criterion by criterion, what stands between it and the
points:
- a journey it has not built: its own work, so a goal;
- a run that needs the operator signed in, headed, on the build that ships;
- his review;
- people other than him;
- phones or named devices;
- nothing GAGOS has planned yet.

Only the first is work GAGOS can do by itself; the rest it says plainly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LEDGER = "docs/frontend/LIVING_BEING_ACCEPTANCE_LEDGER_2026-09-24.md"
DESIGN = "docs/frontend/JOURNEYS_PHASE2_DESIGN_2026-11-16.md"
RECORDS = "docs/frontend/evidence/journeys"
#: The file a journey is built in: the goal's file.
RUNNER = "tools/gagos_journeys.py"
#: Who writes the goals this files, in the goal ledger.
SAID_BY = "GAGOS (its own face assessment)"
#: The ledger's frozen denominator.
DENOMINATOR = 100

#: What stands between a criterion and its points, in the order said.
EARNED = "earned"
BUILD = "a journey GAGOS has not built"
RUN = "your signed-in, headed run on the build that ships"
YOURS = "your review or sign-off"
PEOPLE = "people other than you"
DEVICES = "phones or named devices"
UNPLANNED = "nothing GAGOS has planned yet"
NEEDS = (EARNED, BUILD, RUN, YOURS, PEOPLE, DEVICES, UNPLANNED)

_CRITERION = re.compile(r"\b[A-Z][A-Z0-9]*-\d{2}\b")
_JOURNEY = re.compile(r"`([a-z]+-\d{2})`")
# The ledger's own words for who must see a criterion, tried in this order.
_PEOPLE = re.compile(r"\bHuman\b|[Nn]on-builder")
_DEVICES = re.compile(r"[Pp]hysical|Android|iPhone|[Nn]amed[- ]devices?\b")
_YOURS = re.compile(r"[Oo]perator|\bReviewed\b")


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    weight: int
    earned: int
    stage: str
    proof: str


@dataclass(frozen=True)
class PlannedJourney:
    id: str
    criteria: tuple[str, ...]
    operator_does: str
    proves: str


@dataclass
class Gap:
    criterion: Criterion
    needs: str
    journeys: list[str] = field(default_factory=list)
    newest: dict[str, Any] | None = None


@dataclass
class Assessment:
    criteria: list[Criterion]
    gaps: list[Gap]
    to_build: list[PlannedJourney]
    problems: list[str]

    @property
    def earned(self) -> int:
        return sum(c.earned for c in self.criteria)

    @property
    def weight(self) -> int:
        return sum(c.weight for c in self.criteria)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def read_ledger(text: str) -> list[Criterion]:
    """The acceptance ledger's criteria: ``| ID | name (weight) | proof |
    evidence ... `stage`; **earned**. |``."""
    out = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) != 4 or not re.fullmatch(r"[A-Z][A-Z0-9]*-\d{2}", cells[0]):
            continue
        named = re.fullmatch(r"(.+?)\s*\((\d+)\)", cells[1])
        if not named:
            continue
        earned = re.findall(r"\*\*(\d+)\*\*", cells[3])
        stages = re.findall(r"`([a-z]+(?:-[a-z]+)*)`", cells[3])
        out.append(
            Criterion(
                id=cells[0],
                name=named.group(1),
                weight=int(named.group(2)),
                earned=int(earned[-1]) if earned else 0,
                stage=stages[-1] if stages else "unknown",
                proof=cells[2],
            )
        )
    return out


def read_design(text: str) -> list[PlannedJourney]:
    """The design's journeys, in the order its "Order" section builds them
    (any it does not name follow, in table order)."""
    table = []
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = _cells(line)
        named = _JOURNEY.fullmatch(cells[0]) if cells else None
        if len(cells) != 4 or not named:
            continue
        table.append(
            PlannedJourney(
                id=named.group(1),
                criteria=tuple(_CRITERION.findall(cells[1])),
                operator_does=cells[2],
                proves=cells[3],
            )
        )
    order: list[str] = []
    if "## Order" in text:
        for found in _JOURNEY.findall(text.split("## Order", 1)[1]):
            if found not in order:
                order.append(found)
    rank = {jid: i for i, jid in enumerate(order)}
    return sorted(table, key=lambda j: rank.get(j.id, len(order)))


def newest_records(folder: Path) -> dict[str, dict[str, Any]]:
    """The newest record of each journey in *folder*, by its start."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(folder).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        jid = str(record.get("journey") or "")
        if jid and str(record.get("started_at") or "") >= str(
            out.get(jid, {}).get("started_at") or ""
        ):
            out[jid] = record
    return out


def _needs_by_words(proof: str) -> str:
    if _PEOPLE.search(proof):
        return PEOPLE
    if _DEVICES.search(proof):
        return DEVICES
    if _YOURS.search(proof):
        return YOURS
    return UNPLANNED


def assess(
    ledger: str,
    design: str,
    built: Mapping[str, str],
    records: Mapping[str, Mapping[str, Any]],
) -> Assessment:
    """GAGOS's face, criterion by criterion. *built* is its runner's journeys
    (id -> the criteria text it names)."""
    criteria = read_ledger(ledger)
    planned = read_design(design)
    problems = []
    if not criteria:
        problems.append(f"no criterion could be read from {Path(LEDGER).name}")
    elif sum(c.weight for c in criteria) != DENOMINATOR:
        problems.append(
            f"the ledger's criteria weigh {sum(c.weight for c in criteria)}, "
            f"not its frozen {DENOMINATOR}"
        )
    covers_built: dict[str, list[str]] = {}
    for jid, text in built.items():
        for cid in _CRITERION.findall(text):
            covers_built.setdefault(cid, []).append(jid)
    covers_planned: dict[str, list[str]] = {}
    for journey in planned:
        if journey.id in built:
            continue
        for cid in journey.criteria:
            covers_planned.setdefault(cid, []).append(journey.id)
    gaps = []
    for c in criteria:
        if c.earned >= c.weight:
            continue
        if c.id in covers_built:
            jids = covers_built[c.id]
            newest = max(
                (dict(records[j], journey=j) for j in jids if j in records),
                key=lambda r: str(r.get("started_at") or ""),
                default=None,
            )
            gaps.append(Gap(c, RUN, jids, newest))
        elif c.id in covers_planned:
            gaps.append(Gap(c, BUILD, covers_planned[c.id]))
        else:
            gaps.append(Gap(c, _needs_by_words(c.proof)))
    to_build = [j for j in planned if j.id not in built]
    return Assessment(criteria, gaps, to_build, problems)


def _run_said(record: Mapping[str, Any] | None) -> str:
    if not record:
        return "never run"
    measured = record.get("measured") or {}
    how = [
        "signed in" if record.get("signed_in") else "signed out",
        str(measured.get("window") or "window not recorded"),
        str(measured.get("build") or "build not recorded"),
    ]
    return (
        f"{record.get('journey')} {record.get('outcome')} on "
        f"{str(record.get('started_at') or '')[:10]} ({', '.join(how)})"
    )


def lines(a: Assessment) -> list[str]:
    """The assessment as GAGOS says it in its hour."""
    out = [
        f"face: {a.earned} of {a.weight} points accepted "
        f"(the acceptance ledger; points are the operator's to award)"
    ]
    out += [f"face: cannot read itself: {p}" for p in a.problems]
    for need in NEEDS[1:]:
        gaps = [g for g in a.gaps if g.needs == need]
        if not gaps:
            continue
        points = sum(g.criterion.weight - g.criterion.earned for g in gaps)
        named = ", ".join(g.criterion.id for g in gaps)
        out.append(f"face: {points} points need {need}: {named}")
        if need == RUN:
            out += [f"face:   {g.criterion.id}: {_run_said(g.newest)}" for g in gaps]
    if a.to_build:
        out.append(
            "face: journeys GAGOS designed and has not built: "
            + ", ".join(j.id for j in a.to_build)
        )
    return out


def document(a: Assessment, *, commit: str) -> str:
    """The assessment as a document in GAGOS's knowledge base, so the counter
    answers from it ("how is your face?")."""
    rows = "\n".join(
        f"| {g.criterion.id} | {g.criterion.name} | {g.criterion.weight} | "
        f"{g.needs} | {_run_said(g.newest) if g.needs == RUN else ''} |"
        for g in a.gaps
    )
    return (
        f"# GAGOS's face, as GAGOS assesses it (master {commit[:12]})\n\n"
        f"{a.earned} of {a.weight} points are accepted in the acceptance ledger. "
        "Points are awarded by acceptance, never by GAGOS. "
        "This is what stands between each criterion and its points, read from "
        "the ledger, the journeys' design, the runner and the journey records.\n\n"
        + "".join(f"- Cannot read itself: {p}\n" for p in a.problems)
        + "\n| Criterion | Name | Points | Needs | Newest run |\n| --- | --- | --- | --- | --- |\n"
        + rows
        + "\n"
    )


def _plain(text: str) -> str:
    """Design text a goal can carry past the privacy filter: no slash-joined
    words (they read as paths and are redacted), no code marks."""
    text = text.replace("`", "")
    return re.sub(r"(?<=\S)\s*/\s*(?=\S)", " or ", text)


def goal_marker(journey_id: str) -> str:
    return f"[face {journey_id}]"


def goal_text(journey: PlannedJourney, rule: str) -> str:
    """A goal for one journey GAGOS designed and has not built."""
    return (
        f"{goal_marker(journey.id)} Build the {journey.id} journey in "
        f"{Path(RUNNER).name}, for {', '.join(journey.criteria)}, as its design "
        "says. Follow how ask-01 is built (watch, watch_turn, the record and "
        "its boundary) and add it to WATCHES. "
        f"The operator does: {_plain(journey.operator_does)}. "
        f"The runner proves: {_plain(journey.proves)}. "
        f"The rule that does not move: {_plain(rule)}"
    )


def design_rule(design: str) -> str:
    """The design's fixed rule, as one sentence a goal can carry."""
    rows = []
    if "## The rule that does not move" in design:
        part = design.split("## The rule that does not move", 1)[1].split("\n## ", 1)[0]
        for line in part.splitlines():
            cells = _cells(line) if line.startswith("|") else []
            if (
                len(cells) == 2
                and not set(cells[1]) <= {"-", " "}
                and cells[1] != "The runner does"
            ):
                rows.append(f"when the operator {cells[0]}, the runner {cells[1]}")
    return "; ".join(rows) + "." if rows else ""


#: How long a taken goal's journey is waited for (its proposal, review and
#: merge) before GAGOS asks for the next one beside it.
IN_FLIGHT_DAYS = 7


def asked(tasks: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """GAGOS's own journey goals, by journey, the newest of each."""
    out: dict[str, Mapping[str, Any]] = {}
    for t in tasks:
        text = str(t.get("text") or "")
        if str(t.get("said_by") or "") != SAID_BY or not text.startswith("[face "):
            continue
        jid = text[len("[face ") :].split("]", 1)[0]
        if str(t.get("created_at") or "") >= str(
            out.get(jid, {}).get("created_at") or ""
        ):
            out[jid] = t
    return out


def next_goal(
    a: Assessment, design: str, tasks: Iterable[Mapping[str, Any]], *, now: str
) -> tuple[PlannedJourney, str] | None:
    """The one journey to ask for now, or None. The first unbuilt journey in
    the design's order that was never asked for, while none of GAGOS's own
    goals is in flight: open, or taken within IN_FLIGHT_DAYS for a journey
    still unbuilt. *now* is an ISO time, as the ledger stamps."""
    from datetime import datetime, timedelta

    mine = asked(tasks)
    unbuilt = {j.id for j in a.to_build}
    since = (datetime.fromisoformat(now) - timedelta(days=IN_FLIGHT_DAYS)).isoformat()
    for jid, t in mine.items():
        if t.get("status") == "open" or (
            t.get("status") == "taken"
            and jid in unbuilt
            and str(t.get("updated_at") or t.get("created_at") or "") >= since
        ):
            return None
    rule = design_rule(design)
    for journey in a.to_build:
        if journey.id not in mine:
            return journey, goal_text(journey, rule)
    return None


__all__ = [
    "Assessment",
    "Criterion",
    "Gap",
    "NEEDS",
    "PlannedJourney",
    "RUNNER",
    "SAID_BY",
    "assess",
    "document",
    "goal_text",
    "lines",
    "newest_records",
    "next_goal",
    "read_design",
    "read_ledger",
]
