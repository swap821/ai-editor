"""GAGOS understands itself, step 1: its own honest list of what it is missing.

2026-11-24, the operator: "my jarvis which is GAGOS should understand itself
honestly and then complete itself first as it should be" -- his direction of
2026-11-15 ("honestly understand itself first") and 2026-09-20, restated.
Measured that day: organ 28's passport said only what GAGOS is built with, and
everything GAGOS knew about its own shortcomings lay in separate stores it
never read together. It worked only on lint findings and goals someone else
wrote for it.

The self-model reads those stores and says, in GAGOS's own words, what it is
missing, and whose it is to fix:

* ``gagos`` -- its own to fix: the refusals it keeps meeting in its own work
  (a file too long to propose, answers that do not apply, tests its proposals
  break), files its writers never see, findings it cannot attempt, files with
  no test, a part of it no producer runs;
* ``operator`` -- his: a part that wakes only in his conversations, a mission
  part with no live envelope, an organ waiting on his attestation or his
  choice;
* ``outside`` -- neither: what needs another machine or other people.

Nothing here is a new measurement: every gap is read from a record GAGOS
already keeps (its daily ledger, its hour's own measures, the aliveness pulse,
the organ ledger). It reads and decides nothing; the goals GAGOS takes on
itself from it are step 2.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from aios.application.observability.brief import (
    OWNER_GAGOS as GAGOS,
    OWNER_OPERATOR as OPERATOR,
    OWNER_OUTSIDE as OUTSIDE,
    organ_owner,
    organ_reason,
)

_ORDER = {GAGOS: 0, OPERATOR: 1, OUTSIDE: 2}

#: The refusals GAGOS meets in its own work, by what its records say: the
#: words to look for, and what GAGOS says about itself. Measured on 2026-11-24
#: (44 refusals in 7 days); anything else is counted as "other".
FRICTION = (
    (
        "whole-file",
        ("bound for a whole-file proposal",),
        "I cannot propose a change to a file longer than my whole-file bound",
    ),
    (
        "breaks-tests",
        ("breaks tests that pass without it",),
        "my proposals break tests that pass without them",
    ),
    (
        "own-tests-fail",
        ("own new tests fail",),
        "my proposals' own new tests fail",
    ),
    (
        "placeholder",
        ("placeholder of another file",),
        "my writers' answers carry another file's mask placeholder",
    ),
    (
        "does-not-apply",
        (
            "does not parse",
            "fenced code block",
            "is not in the file",
            "scrubbed on its way back",
        ),
        "my writers' answers do not apply as written",
    ),
    (
        "no-edit",
        ("made no edit",),
        "my writers return no edit",
    ),
    (
        "rejected",
        ("reject",),
        "my reviewer rejects my changes",
    ),
)
#: Refusals already said as withheld files (``writer_withholdings``).
_WITHHELD = ("privacy filter would redact", "secret policy would scrub")
#: How many of the files behind a gap are named.
NAMED = 3


@dataclass(frozen=True)
class Gap:
    """One thing GAGOS is missing, in its own words, and whose it is to fix."""

    key: str
    what: str
    evidence: str
    owner: str
    weight: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "what": self.what,
            "evidence": self.evidence,
            "owner": self.owner,
            "weight": self.weight,
        }


def _names(subjects: Iterable[str]) -> str:
    seen: list[str] = []
    for subject in subjects:
        name = PurePosixPath(str(subject or "").replace("\\", "/")).name
        if name and name not in seen:
            seen.append(name)
    shown = ", ".join(seen[:NAMED])
    more = len(seen) - NAMED
    return shown + (f" and {more} more" if more > 0 else "")


def friction_gaps(rows: Iterable[Mapping[str, Any]], *, days: int) -> list[Gap]:
    """The refusals GAGOS keeps meeting in its own work (its ledger's
    ``friction``), grouped by what they say."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        text = str(row.get("text") or "").lower()
        if any(mark in text for mark in _WITHHELD):
            continue
        key = next(
            (k for k, marks, _ in FRICTION if any(m in text for m in marks)), "other"
        )
        groups.setdefault(key, []).append(row)
    out = []
    for key, marks_said in [(k, s) for k, _, s in FRICTION] + [
        ("other", "my work is refused for other reasons")
    ]:
        found = groups.get(key)
        if not found:
            continue
        names = _names(r.get("subject") for r in found)
        out.append(
            Gap(
                key=f"friction:{key}",
                what=f"{marks_said} ({len(found)} in {days} days"
                + (f": {names})" if names else ")"),
                evidence="daily ledger: friction",
                owner=GAGOS,
                weight=len(found),
            )
        )
    return out


def withheld_gaps(rows: Iterable[Mapping[str, Any]], *, days: int) -> list[Gap]:
    """Files GAGOS's writers never see as written (its ledger's
    ``writer_withholdings``). The privacy filter's masking is GAGOS's own to
    improve; the secret policy is the frozen core's, so it is his."""
    out = []
    for row in rows:
        kind = str(row.get("kind") or "")
        name = PurePosixPath(str(row.get("rel") or "").replace("\\", "/")).name
        secret = "secret policy" in kind
        out.append(
            Gap(
                key=f"withheld:{row.get('rel')}",
                what=(
                    f"my writers never see {name} as written ({kind.removeprefix('withheld: ')}, "
                    f"{row.get('times', 0)} times in {days} days)"
                ),
                evidence="daily ledger: writer_withholdings",
                owner=OPERATOR if secret else GAGOS,
                weight=int(row.get("times") or 0),
            )
        )
    return out


def measure_gaps(values: Mapping[str, Any] | None) -> list[Gap]:
    """What the hour's own measures say GAGOS cannot reach (its ledger's
    ``measures``, written by the batch each hour)."""
    if not values:
        return []
    out = []
    waiting = int(values.get("waiting") or 0)
    if waiting:
        out.append(
            Gap(
                key="measure:waiting",
                what=(
                    f"{waiting} lint findings are beyond my workshop: their fix "
                    "spans files or needs a new file, and I cannot create files"
                ),
                evidence="daily ledger: measures.waiting",
                owner=GAGOS,
                weight=waiting,
            )
        )
    untested = int(values.get("untested") or 0)
    if untested:
        out.append(
            Gap(
                key="measure:untested",
                what=f"{untested} of my files have no test",
                evidence="daily ledger: measures.untested",
                owner=GAGOS,
                weight=untested,
            )
        )
    return out


def dormant_gaps(
    readings: Iterable[Any],
    *,
    turn_events: tuple[str, ...],
    mission: str,
    mission_envelope_live: bool,
) -> list[Gap]:
    """Parts of GAGOS that never ran or have gone silent (the aliveness pulse),
    owned by what wakes them as the pulse's own map declares: a part seen in
    turns wakes only in his conversations; a mission part needs his live
    envelope; any other is GAGOS's own to run, or to find out why it is
    silent."""
    out = []
    for reading in readings:
        if reading.status not in ("never", "stale"):
            continue
        part = reading.part
        when = (
            "never ran"
            if reading.status == "never"
            else f"silent since {reading.last.date().isoformat()}"
            if reading.last
            else "silent"
        )
        wakes = getattr(part, "wakes", "")
        if wakes == "operator":
            owner, why = OPERATOR, "it wakes only on your own act"
        elif (
            wakes == "turn"
            or set(part.events) & set(turn_events)
            or part.key == "counter"
        ):
            owner, why = OPERATOR, "it wakes only in your conversations"
        elif mission in part.workers:
            owner = GAGOS if mission_envelope_live else OPERATOR
            why = (
                "it runs in my missions"
                if mission_envelope_live
                else "it runs in my missions, and no mission envelope is live"
            )
        else:
            owner, why = GAGOS, "nothing of mine runs it"
        out.append(
            Gap(
                key=f"dormant:{part.key}",
                what=f"{part.name} {when}: {why}",
                evidence="aliveness pulse",
                owner=owner,
            )
        )
    return out


def organ_gaps(organs: Iterable[Mapping[str, Any]]) -> list[Gap]:
    """Organs of the ledger not green, with the reason they record, owned by
    what that reason asks for."""
    out = []
    for organ in organs:
        if organ.get("status") == "green":
            continue
        blocker = organ_reason(organ)
        owner = organ_owner(blocker)  # the one rule the brief reads too
        out.append(
            Gap(
                key=f"organ:{organ.get('organ_id')}",
                what=(
                    f"organ {organ.get('organ_id')} ({organ.get('name')}) is "
                    f"{organ.get('status')}: {blocker[:160]}"
                ),
                evidence="organ ledger",
                owner=owner,
            )
        )
    return out


@dataclass(frozen=True)
class SelfModel:
    gaps: tuple[Gap, ...]

    def owned(self, owner: str) -> tuple[Gap, ...]:
        return tuple(g for g in self.gaps if g.owner == owner)

    def as_dict(self) -> dict[str, Any]:
        return {"gaps": [g.as_dict() for g in self.gaps]}


def consistency_gaps(summary: Mapping[str, Any] | None) -> list[Gap]:
    """Where GAGOS's parts may not agree, by its own consistency audit
    (2026-11-24, the operator: cross-system consistency is what makes GAGOS
    run in harmony). *summary* is the audit's result (``rows``, ``covered``,
    ``open`` ids, ``errors``), or None when it could not be run."""
    if summary is None:
        return [
            Gap(
                key="consistency:unread",
                what="I could not run my consistency audit, so I cannot say my parts agree",
                evidence="consistency audit",
                owner=GAGOS,
            )
        ]
    out = []
    unheld = list(summary.get("open") or ())
    if unheld:
        out.append(
            Gap(
                key="consistency:open",
                what=(
                    f"{len(unheld)} fact(s) my parts share are neither held to one "
                    f"source nor guarded: {', '.join(unheld[:4])}"
                ),
                evidence="consistency register",
                owner=GAGOS,
                weight=len(unheld),
            )
        )
    errors = list(summary.get("errors") or ())
    if errors:
        out.append(
            Gap(
                key="consistency:errors",
                what=(
                    f"my consistency register is wrong in {len(errors)} place(s), "
                    f"first: {str(errors[0])[:140]}"
                ),
                evidence="consistency audit",
                owner=GAGOS,
                weight=len(errors),
            )
        )
    return out


def compose(*groups: Iterable[Gap]) -> SelfModel:
    """Every gap, GAGOS's own first, the heaviest first within an owner."""
    gaps = [g for group in groups for g in group]
    gaps.sort(key=lambda g: (_ORDER.get(g.owner, 9), -g.weight, g.key))
    return SelfModel(tuple(gaps))


def report_lines(model: SelfModel, *, shown: int = 8) -> list[str]:
    """The hour's lines: the count by owner, then GAGOS's own gaps."""
    mine = model.owned(GAGOS)
    lines = [
        f"self-model: {len(mine)} gap(s) I can work on, "
        f"{len(model.owned(OPERATOR))} that need the operator, "
        f"{len(model.owned(OUTSIDE))} outside us"
    ]
    lines += [f"  - {g.what}" for g in mine[:shown]]
    if len(mine) > shown:
        lines.append(f"  - and {len(mine) - shown} more")
    return lines


def latest_measures(ledger: Any) -> Mapping[str, Any] | None:
    rows = ledger.measures()
    return rows[-1]["values"] if rows else None


def organ_ledger(path: Any) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


__all__ = [
    "FRICTION",
    "GAGOS",
    "Gap",
    "OPERATOR",
    "OUTSIDE",
    "SelfModel",
    "compose",
    "dormant_gaps",
    "friction_gaps",
    "latest_measures",
    "measure_gaps",
    "organ_gaps",
    "organ_ledger",
    "report_lines",
    "withheld_gaps",
]
