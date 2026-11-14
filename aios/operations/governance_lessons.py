"""GAGOS proposes governance lessons from the friction it keeps meeting (2026-11-15).

Organ 46 (:mod:`aios.application.governance.constitutional_learning`) turns an
observed weakness in GAGOS's own governance into a lesson, and a lesson into
an amendment *proposal* -- never further: ratification is the operator's,
behind a real capability (organ 45). Nothing ever proposed a lesson, so the
organ was idle. The operator's word of 2026-11-15, "yes on organ46": GAGOS
proposes them itself.

From its own ledger, with no model: each refusal GAGOS's hour kept is matched
against the frictions below. One recurs when it was met at least
:data:`MIN_OCCURRENCES` times in the last :data:`WINDOW_DAYS` days and at least
once in the last :data:`RECENT_HOURS` hours -- a friction that stopped is not
proposed. A recurring friction becomes one lesson, through organ 46's own
authority and its screen (a lesson may never propose reducing human
authority), into the store its routes read. Proposed once: the next hours say
it is already with organ 46, and a lesson the operator has ruled on is never
proposed again.

Frictions already governed elsewhere are not lessons: a writer at its plan's
usage limit rests and is probed once a batch, and a refused provider likewise
(``DailyLedger.resting_writers``, ``refused_writers``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

#: A friction recurs at this many occurrences in the window...
MIN_OCCURRENCES = 5
#: ...counted over these days...
WINDOW_DAYS = 7
#: ...with at least one in these last hours.
RECENT_HOURS = 24
#: The most ledger rows one lesson names as its evidence, newest first.
MAX_EVIDENCE = 20
#: Every lesson GAGOS proposes is named so.
LESSON_PREFIX = "gagos-friction-"


@dataclass(frozen=True)
class Friction:
    """One kind of friction GAGOS's ledger records, and the lesson it teaches."""

    key: str
    problem_class: str
    pattern: re.Pattern[str]
    #: Where the ledger keeps it: ``proposal`` or ``goal_mission``.
    source: str
    #: What one subject is, for the count: "files", "goals".
    subjects: str
    current_rule: str
    #: What happened, completed with the counts.
    harm: str
    improvement: str

    @property
    def lesson_id(self) -> str:
        return f"{LESSON_PREFIX}{self.key}"


FRICTIONS: tuple[Friction, ...] = (
    Friction(
        key="privacy-withheld-file",
        problem_class="privacy_denial",
        pattern=re.compile(
            r"the privacy filter would redact this file"
            r"|the secret policy would scrub this file"
        ),
        source="proposal",
        subjects="files",
        current_rule=(
            "A file the privacy filter would redact, or the secret policy would "
            "scrub, is never sent to a writer, so its findings are never worked "
            "on, and nothing tells the operator which files they are."
        ),
        harm="A file was withheld from GAGOS's writers by the privacy filter or the secret policy",
        improvement=(
            "List the withheld files for the operator, each with the kind of "
            "match that withheld it, so that he can decide file by file whether "
            "it holds a real secret to move out of the code or a false match. "
            "Nothing is sent to a writer meanwhile, and the filter and the policy "
            "stay as they are."
        ),
    ),
    Friction(
        key="names-scrubbed-as-secrets",
        problem_class="privacy_denial",
        pattern=re.compile(
            r"the answer was scrubbed on its way back from the writer \(HIGH_ENTROPY"
        ),
        source="proposal",
        subjects="files",
        current_rule=(
            "The secret scanner's entropy pass hides any long, varied token, so a "
            "writer's answer that names a long camelCase identifier comes back "
            "altered, and is refused as not what the writer wrote."
        ),
        harm="A writer's answer was scrubbed because the secret scanner took a name in it for a secret",
        improvement=(
            "The operator reviews docs/security/PROPOSAL_ENTROPY_CAMELCASE_NAMES.md, "
            "which describes the false matches and a narrower entropy pass. The "
            "scanner is frozen core: any change to it is his alone, and until he "
            "decides, such answers stay refused."
        ),
    ),
    Friction(
        key="envelope-slots-used",
        problem_class="approval_friction",
        pattern=re.compile(r"the envelope's \d+ missions are used"),
        source="goal_mission",
        subjects="goals",
        current_rule=(
            "Each envelope the operator signs admits a fixed number of missions; "
            "a briefed goal that finds every slot used is refused, and waits for "
            "his next signature."
        ),
        harm="A briefed goal was refused because every mission slot of the operator's envelope was used",
        improvement=(
            "When the operator signs his next envelope, show him how many briefed "
            "goals waited for a slot and since when, so that he can size it to the "
            "work waiting. The envelope stays his signature, and its size his choice."
        ),
    ),
)


@dataclass(frozen=True)
class Recurrence:
    """A friction that recurs: how often, on how many subjects, and when last."""

    friction: Friction
    count: int
    subjects: int
    last: str
    #: Its ledger rows, newest first, at most :data:`MAX_EVIDENCE`.
    refs: tuple[str, ...]


def _when(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["created_at"]))


def recurring(rows: Sequence[Mapping[str, Any]], *, now: datetime) -> list[Recurrence]:
    """The frictions among the ledger's refusal *rows* that recur at *now*, in
    :data:`FRICTIONS`' order. Each row: ``source``, ``ref``, ``subject``,
    ``text`` and ``created_at``."""
    since, lately = (
        now - timedelta(days=WINDOW_DAYS),
        now - timedelta(hours=RECENT_HOURS),
    )
    found = []
    for friction in FRICTIONS:
        seen = sorted(
            (
                r
                for r in rows
                if r["source"] == friction.source
                and friction.pattern.search(str(r["text"] or ""))
                and since <= _when(r) <= now
            ),
            key=_when,
            reverse=True,
        )
        if len(seen) < MIN_OCCURRENCES or _when(seen[0]) < lately:
            continue
        found.append(
            Recurrence(
                friction=friction,
                count=len(seen),
                subjects=len({r["subject"] for r in seen}),
                last=str(seen[0]["created_at"]),
                refs=tuple(
                    f"gagos-ledger:{r['source'].replace('_', '-')}:{r['ref']}"
                    for r in seen[:MAX_EVIDENCE]
                ),
            )
        )
    return found


def lesson_store() -> Any:
    """Organ 46's store, the one its routes read and the operator drafts from."""
    from aios import config
    from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore

    return GovernanceAmendmentStore(config.GOVERNANCE_AMENDMENT_DB_PATH)


def propose_lessons(
    rows: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    store: Any | None = None,
    authority: Any | None = None,
) -> list[tuple[Recurrence, str]]:
    """Each recurring friction proposed to organ 46 once: ``(recurrence,
    outcome)`` where outcome is ``proposed``, ``already with organ 46
    (<status>)`` or ``refused by organ 46's screen: <why>``."""
    from aios.application.governance.constitutional_learning import (
        ConstitutionalLearningAuthority,
        ConstitutionalLearningError,
    )

    store = store if store is not None else lesson_store()
    authority = (
        authority if authority is not None else ConstitutionalLearningAuthority()
    )
    out = []
    for found in recurring(rows, now=now):
        friction = found.friction
        held = store.get_current_lesson(friction.lesson_id)
        if held is not None:
            out.append((found, f"already with organ 46 ({held.status})"))
            continue
        harm = (
            f"{friction.harm}: {found.count} times in the last {WINDOW_DAYS} days, "
            f"on {found.subjects} {friction.subjects}, the last at {found.last}."
        )
        try:
            for text in (friction.current_rule, harm, friction.improvement):
                authority.assert_never_reduces_human_authority(text)
        except ConstitutionalLearningError as exc:
            out.append((found, f"refused by organ 46's screen: {exc}"))
            continue
        lesson = authority.propose_lesson(
            lesson_id=friction.lesson_id,
            problem_class=friction.problem_class,
            evidence_refs=found.refs,
            observed_harm=harm,
            current_rule=friction.current_rule,
            proposed_improvement=friction.improvement,
            # More occurrences, more confidence; never certainty from counting.
            confidence=round(min(0.9, 0.5 + found.count / 50), 2),
        )
        store.save_lesson(lesson)
        out.append((found, "proposed"))
    return out


__all__ = [
    "FRICTIONS",
    "Friction",
    "LESSON_PREFIX",
    "MAX_EVIDENCE",
    "MIN_OCCURRENCES",
    "RECENT_HOURS",
    "Recurrence",
    "WINDOW_DAYS",
    "lesson_store",
    "propose_lessons",
    "recurring",
]
