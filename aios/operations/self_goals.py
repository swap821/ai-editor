"""GAGOS completes itself, step 2: the goals it takes on itself from its own gaps.

2026-11-24, the operator chose: after GAGOS's self-model (step 1), GAGOS takes
goals on itself from what it is missing, inside his envelope, through its
writers, sandbox and reviewer, and he merges.

Only one gap of the self-model is grounded enough to become a goal without a
person writing it: **findings refused because their file is longer than the
whole-file bound** (18 refusals in the 7 days to 2026-11-24, GAGOS's largest
gap). The ledger keeps each refused finding's rule, lines and messages, and a
goal is applied as edits, so it reaches a file a whole-file proposal cannot.
Until now someone else wrote that bridge by hand (Claude's goals
gt-9f7f3e477e, gt-589ae403b1). The other gaps -- broken tests, placeholders,
answers that do not apply, a withheld file -- need a judgment no record holds,
and stay reported, not taken on.

A finding becomes a goal only when:

* its file is byte-for-byte the one it was refused on (``base_digest`` equals
  the file's digest now), so the finding is still true;
* a mission envelope is live and the file is inside its folders and kinds --
  GAGOS originates nothing on its own outside the operator's signed grant;
* no goal for that file is open, none was set since the refusal, and GAGOS has
  not already taken this same base on itself.

It writes nothing here; the hour adds the goal through the daily ledger.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

#: What a refusal for size says (tools/gagos_daily.py, cmd_propose).
SIZE_REFUSAL = "bound for a whole-file proposal"
#: Who sets a goal GAGOS takes on itself; its base digest follows.
SAID_BY = "GAGOS (its own self-model)"
#: At most this many findings are listed in one goal; the rest are counted.
MAX_LISTED = 8
#: How much of a finding's message a goal carries.
MESSAGE_CHARS = 200


@dataclass(frozen=True)
class Candidate:
    """One file's still-true findings, refused for size."""

    rel: str
    base_digest: str
    refused_at: str
    findings: tuple[tuple[str, int, str], ...]  # (rule, line, message)

    @property
    def marker(self) -> str:
        return f"base {self.base_digest[:12]}"


def _message(text: Any) -> str:
    first = str(text or "").strip().splitlines()[0] if str(text or "").strip() else ""
    return first[:MESSAGE_CHARS]


def candidates(
    refusals: Iterable[Mapping[str, Any]],
    *,
    digest_now: Callable[[str], str | None],
    rules: Iterable[str],
) -> list[Candidate]:
    """Size-refused findings still true now, one candidate per file.

    *refusals* are proposal rows (``rel``, ``rule``, ``refusal``, ``warnings``
    JSON, ``base_digest``, ``created_at``); only the latest refusal of each
    (file, rule) counts. *digest_now(rel)* is the file's digest now, or None
    when it no longer exists."""
    allowed = set(rules)
    latest: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in refusals:
        if SIZE_REFUSAL not in str(row.get("refusal") or ""):
            continue
        if row.get("rule") not in allowed:
            continue
        key = (str(row.get("rel")), str(row.get("rule")))
        if key not in latest or str(row.get("created_at")) > str(
            latest[key].get("created_at")
        ):
            latest[key] = row
    by_file: dict[str, list[Mapping[str, Any]]] = {}
    for (rel, _rule), row in latest.items():
        now = digest_now(rel)
        if now is None or now != row.get("base_digest"):
            continue  # the file changed since: the finding may no longer hold
        by_file.setdefault(rel, []).append(row)
    out = []
    for rel, rows in sorted(by_file.items()):
        found: list[tuple[str, int, str]] = []
        for row in sorted(rows, key=lambda r: str(r.get("rule"))):
            try:
                warnings = json.loads(row.get("warnings") or "[]")
            except ValueError:
                warnings = []
            for item in warnings:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    found.append((str(row["rule"]), int(item[0]), _message(item[2])))
        if not found:
            continue
        out.append(
            Candidate(
                rel=rel,
                base_digest=str(rows[0]["base_digest"]),
                refused_at=max(str(r.get("created_at")) for r in rows),
                findings=tuple(found),
            )
        )
    return out


def _task_files(task: Mapping[str, Any]) -> set[str]:
    """Every file a goal names: the ledger's ``files`` (its file and ``also``),
    or, from a raw row, ``rel`` and the ``also`` JSON."""
    files = task.get("files")
    if isinstance(files, (list, tuple)):
        return {str(f) for f in files}
    out = {str(task.get("rel"))}
    also = task.get("also")
    if isinstance(also, (list, tuple)):
        out |= {str(f) for f in also}
    elif isinstance(also, str):
        try:
            out |= {str(f) for f in json.loads(also or "[]")}
        except ValueError:
            pass
    return out


def unclaimed(candidate: Candidate, tasks: Iterable[Mapping[str, Any]]) -> bool:
    """No goal for the file is open, none was set since its refusal, and GAGOS
    has not already taken this same base on itself."""
    for task in tasks:
        if candidate.rel not in _task_files(task):
            continue
        if task.get("status") == "open":
            return False
        if str(task.get("created_at")) >= candidate.refused_at:
            return False
        if candidate.marker in str(task.get("said_by") or ""):
            return False
    return True


def goal_text(candidate: Candidate, *, size: int, bound: int) -> str:
    """The goal, in GAGOS's own words: the findings, what to keep, what not to do."""
    name = PurePosixPath(candidate.rel).name
    lines = [
        f"Clear {len(candidate.findings)} lint finding(s) in {name} without changing "
        f"what it does. My whole-file proposals cannot reach this file ({size} "
        f"characters, over my {bound}-character bound), so I take it on as a goal, "
        "which is applied as edits.",
        "",
    ]
    for rule, line, message in candidate.findings[:MAX_LISTED]:
        lines.append(f"- {rule}, near line {line}: {message}")
    more = len(candidate.findings) - MAX_LISTED
    if more > 0:
        lines.append(f"- and {more} more of the same rules")
    lines += [
        "",
        "Change only what these findings need and keep every other line as it is. "
        "Do not silence a rule with a disable comment or rename a name to dodge it. "
        "If a fix would change what the file does, make no edit and say why.",
    ]
    return "\n".join(lines)


def within(
    envelope_status: Mapping[str, Any], rel: str, *, terms_from, is_test
) -> bool:
    """Whether *rel* is inside the live envelope's folders and kinds."""
    if not envelope_status.get("live"):
        return False
    try:
        terms = terms_from(envelope_status["terms"])
    except (KeyError, TypeError, ValueError):
        return False
    kind = "tests" if is_test(rel) else "code"
    return terms.refusal([rel], kind) is None


__all__ = [
    "Candidate",
    "MAX_LISTED",
    "SAID_BY",
    "SIZE_REFUSAL",
    "candidates",
    "goal_text",
    "unclaimed",
    "within",
]
