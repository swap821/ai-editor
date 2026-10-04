#!/usr/bin/env python3
"""The number the ANIMAL is judged by: is what it remembered worth anything?

WHY THIS EXISTS
---------------
The Learning Ledger proves the machinery is real and honestly measured -- a
lesson is recorded from a genuine failure, a skill verifies, a reflex serves a
turn with zero LLM calls, a curriculum level masters. Every one of those is a
MECHANISM, proven on real code.

None of them is a claim that any of it HELPS. LC1..LC12 never asks whether
learning improved an outcome, and on the numbers the payoff looked like roughly
nothing: 7 replays ever, 7 verified lessons out of 103, and a mastered
curriculum level whose skill was "run pytest on a file".

The cage has organ 55 -- a number GAGOS is judged by. The animal had none. This
is it.

THE MEASUREMENT
---------------
One real task, run twice, differing in exactly one thing:

    OFF   the production prompt, alone
    ON    the production prompt plus what this system actually remembered --
          recalled lessons and verified skills, formatted by the SAME
          functions the live turn path uses (`lessons_prompt_block`,
          `skills_prompt_block`), so the ON arm sees the bytes production
          would have shown it and not a benchmark's idea of them.

Same model, same target, same corpus commit, same grader. Both arms graded by
`grade_pin_test` -- passes_clean AND fails_when_mutated AND source_untouched
AND suite_still_green. A test that passes without pinning anything is
`vacuous`, not a win, and that rule is the existing one; nothing here grades
anything its own way.

    payoff = earned_rate(ON) - earned_rate(OFF)

over COMPARABLE pairs. Negative is a legitimate result and is published as-is:
a system that is worse with its memories attached needs to know that far more
urgently than one that is better.

WHAT MAKES A PAIR COMPARABLE, AND WHY IT MATTERS MOST
-----------------------------------------------------
This benchmark's easiest failure is a confident 0.00 that measured nothing --
the vacuous-FAIL class organ 55 already learned the hard way, where 14 failures
turned out to be the benchmark blaming GAGOS for models that never reached the
control. So a pair is SCORED only when:

  * both arms reached the model (a provider outage is not a model failing);
  * the ON arm's prompt actually DIFFERS from the OFF arm's -- i.e. recall
    returned something. If the animal remembered nothing relevant, the two arms
    are the same experiment run twice, and their difference is noise. Reported
    as NOT COMPARABLE, never as "no benefit".

The denominator is always printed: attempted / comparable / scored. A payoff
over 2 pairs is not the same claim as a payoff over 40 and must not read like
one.

ORDER IS CONTROLLED, not assumed away: arms alternate which runs first, by
target index, so a systematic "second run is warmer" effect cannot masquerade
as payoff.

CONTAINMENT is inherited unchanged from `self_corpus()`: a throwaway worktree
pinned to a commit, `AIOS_SCOPE_ROOTS` REPLACED, a green baseline required, and
the live tree fingerprinted before and after.

    python tools/learning_payoff.py --targets 6
    python tools/learning_payoff.py --targets 10 --models ollama.qwen2.5-coder:7b

    # the powered cloud design (research: docs/learning/PAYOFF_POWER_RESEARCH.md)
    python tools/learning_payoff.py --models qwen.qwen3-coder-30b-a3b-v1:0 \\
        --novel-only --samples 3 --placebo --exclude-targets calibration.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# The ladder module re-execs at import when `--env-file` is in argv, and on
# Windows `os.execv` is spawn-then-exit -- which detaches the run and hands the
# launcher a silent exit 0. Its own marker makes that bootstrap return instead.
os.environ.setdefault("_AIOS_RE_ENV_LOADED", "1")

from tools.reverse_engineer_gagos import (  # noqa: E402
    PROMPT,
    SYSTEM,
    _extract_code,
    _import_path,
    _test_filename,
    complete_via,
    resolve_client,
    run_self_check,
)

# The PRODUCTION recall path and the PRODUCTION prompt blocks, imported
# rather than re-derived. A benchmark that recalls differently from the turn
# path measures a system nobody runs -- and the underscore names are exactly
# what `stream_generate` calls, which is why they are the right ones to use.
from aios.api.turn_pipeline import (  # noqa: E402
    _recall_lessons,
    _recall_skills,
    lessons_prompt_block,
    skills_prompt_block,
)
from aios.agents.reflection_agent import ReflectionAgent  # noqa: E402
from aios.memory.db import init_memory_db  # noqa: E402
from aios.memory.mistake import MistakeMemory  # noqa: E402
from aios.memory.skills import SkillMemory  # noqa: E402
from aios.core.llm import LLMError  # noqa: E402
from tools.self_corpus import CorpusError, self_corpus  # noqa: E402
from tools.self_corpus_grading import _is_build_artefact, grade_pin_test  # noqa: E402
from tools.self_corpus_targets import collect_targets  # noqa: E402

TRAIL = REPO_ROOT / ".aios" / "audit" / "learning-payoff.jsonl"
#: How every text file this run cites is hashed (see ``text_sha256``).
HASH_BASIS = "lf-normalised"


def text_sha256(raw: bytes) -> str:
    """SHA-256 of a text file's bytes with CRLF normalised to LF.

    A Windows checkout writes CRLF, but Git stores LF, so hashing the checkout's
    bytes gave a registration hash nobody could reproduce from the commit (the
    cloud baseline's ``2dbd6873`` was the CRLF form of blob ``4d1be969``). This
    hash matches ``git show <sha>:<path> | sha256sum`` on every platform.
    """
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


PREREGISTRATION = REPO_ROOT / "docs" / "learning" / "PAYOFF_PREREGISTRATION.md"
WORKTREE = REPO_ROOT.parent / "ai-editor-selfcorpus"
DB = REPO_ROOT / "data" / "aios_memory.db"
#: The institutional skill library beside it (D3): the SAME data directory as
#: the memory store measured, never a separately configured one.
LIBRARY_DB = DB.with_name("aios_operational_state.db")
GUARD_SELECTION = ["tests/test_code_chunking.py"]


@dataclass
class ArmResult:
    """One arm of one pair: what the model was given, and what it produced."""

    arm: str
    reached_model: bool = False
    earned: bool = False
    outcome: str = "unknown"
    recalled_lessons: int = 0
    recalled_skills: int = 0
    prompt_chars: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)
    #: Transient provider refusals (throttling) retried before any reply
    #: existed. Recorded, because a retry that is not visible is a re-roll.
    transport_retries: int = 0


@dataclass
class Pair:
    """One target measured both ways."""

    target: str
    first: str
    on: Optional[dict] = None
    off: Optional[dict] = None
    comparable: bool = False
    reason: str = ""
    #: A recalled item was recorded on this very target. Reported apart from
    #: NOVEL pairs: "helps on repeats" and "helps on new work" are different
    #: claims and must never be summed into one number.
    seen: bool = False
    #: The PLACEBO arm (`--placebo`, Deviation D5): as many stored lessons as ON
    #: saw, none that recall picked, plus ON's own skills. ON vs PLACEBO asks
    #: whether recall's choice of lessons beats other lessons of the same kind.
    placebo: Optional[dict] = None
    placebo_comparable: bool = False
    placebo_reason: str = ""
    #: Every sample of every arm when `--samples` > 1; `on`/`off`/`placebo`
    #: then hold the first. Empty for a one-sample run, whose shape is unchanged.
    samples: dict = field(default_factory=dict)

    def earned_samples(self, arm: str) -> int:
        """How many of *arm*'s samples earned (one sample: 0 or 1)."""
        runs = self.samples.get(arm) or [getattr(self, arm)]
        return sum(1 for r in runs if r["earned"])

    @property
    def payoff(self) -> Optional[int]:
        """+1 ON won, -1 OFF won, 0 tie. None when the pair is not comparable."""
        if not self.comparable or self.on is None or self.off is None:
            return None
        return int(self.on["earned"]) - int(self.off["earned"])


def _append(row: dict) -> None:
    """Crash-durable. A run that dies with nothing on disk is
    indistinguishable from a run that never started."""
    TRAIL.parent.mkdir(parents=True, exist_ok=True)
    with TRAIL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for paired binary outcomes.

    *b* = pairs only the ON arm earned, *c* = pairs only the OFF arm earned.
    Concordant pairs (both earned, both failed) carry no information about the
    DIFFERENCE between arms and are ignored by construction -- which is exactly
    why a pile of ties cannot manufacture a confident 0%.

    It is the right test for this design: each target is its own control, and
    the question is whether the discordant pairs lean one way more than chance
    would. It is also brutal at small n, which is the point. With every
    discordant pair going ON's way it takes six of them to reach p < 0.05.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def sign_flip_exact(diffs: list[int]) -> float:
    """Two-sided exact sign-flip permutation p-value for paired differences.

    *diffs* are per-target differences in EARNED SAMPLES (ON minus the other
    arm), integers in [-K, K]. Under the null that the arm label does not
    matter, each difference is equally likely to have either sign, so the
    exact distribution of their sum is a convolution, computed here in full
    rather than sampled -- a Monte-Carlo p-value would be a second source of
    noise in a judged number. Zeros carry no information, exactly as ties do
    in McNemar; with every difference in {-1, 0, 1} this IS the exact McNemar
    test, which a test pins.
    """
    magnitudes = [abs(int(d)) for d in diffs if int(d) != 0]
    if not magnitudes:
        return 1.0
    counts = {0: 1}
    for m in magnitudes:
        nxt: dict[int, int] = {}
        for total, ways in counts.items():
            for signed in (total + m, total - m):
                nxt[signed] = nxt.get(signed, 0) + ways
        counts = nxt
    observed = abs(sum(int(d) for d in diffs))
    extreme = sum(ways for total, ways in counts.items() if abs(total) >= observed)
    return min(1.0, extreme / 2 ** len(magnitudes))


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values for a registered family of tests.

    The operator's decision (2026-09-27) judges more than one payoff number.
    Without a family-wise correction, testing several and quoting whichever came
    out best is a free extra shot. A test is significant at family-wise alpha
    iff its adjusted p is below alpha.
    """
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[name] = running
    return adjusted


def about_this_target(item: dict, target) -> bool:
    """Was a recalled item recorded on THIS target function?

    A positive payoff on a target the system has already practised means
    "memory helps on repeats" -- a far weaker claim than "memory helps on new
    work". The two are reported apart and never summed into one number.

    Deliberately biased toward SEEN: a false SEEN only weakens the NOVEL claim,
    whereas a false NOVEL would inflate it. So the full label counts, and so
    does the module path together with the function name as a whole word --
    but a bare function name like `main` does not, because it would match
    unrelated work everywhere.
    """
    text = " ".join(str(v) for v in item.values() if isinstance(v, (str, list)))
    if target.label in text:
        return True
    # The pin test's own filename is in every verify command a lesson about
    # this target records, and it names BOTH module and function.
    if _test_filename(target) in text:
        return True
    # `Target.module` is a repo-relative PATH ("aios/agents/tool_agent.py"),
    # not a dotted module. Match it as written, and ALSO as the dotted import
    # path, because a lesson about a failed import names it that way.
    #
    # (An earlier version did `.replace(".", "/")` on the path, producing
    # "aios/agents/tool_agent/py" -- a string that can never match. It was
    # masked by the raw-path check beside it, which is how a helper can be
    # wrong and still pass.)
    function = str(target.function)
    names_function = bool(re.search(rf"\b{re.escape(function)}\b", text))
    names_module = str(target.module) in text or _import_path(target.module) in text
    if names_module and names_function:
        return True
    # An ORGANIC lesson often names neither path nor label -- "the auto-verify
    # command builder dropped addopts" -- but does name the function. A
    # DISTINCTIVE function name alone therefore counts. This is the safe
    # direction to be wrong in: a false SEEN only weakens the NOVEL claim. A
    # short generic name (`run`, `main`, `parse`) would match unrelated work
    # everywhere, so it still requires the module.
    return names_function and (len(function) >= 12 or function.count("_") >= 2)


def enrich_lessons(db: Path, lessons: list[dict]) -> list[dict]:
    """Add the fields that say WHICH work a recalled lesson came from.

    A recalled lesson carries `lesson_text` and `error_type` -- the part shown
    to the model -- but not `root_cause`, `fix_applied` or `task_id`, which is
    where the target's identity usually lives. SEEN detection that reads only
    the display dict files a genuine repeat as NOVEL, and that is the one
    mistake this split exists to prevent. Looked up read-only by `mistake_id`.

    Used ONLY to classify. The model is shown exactly what production shows.
    """
    import sqlite3

    ids = [int(item["mistake_id"]) for item in lessons if "mistake_id" in item]
    if not ids:
        return lessons
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(ids))
        extra = {
            int(row["id"]): {
                "root_cause": str(row["root_cause"] or ""),
                "fix_applied": str(row["fix_applied"] or ""),
                "task_id": str(row["task_id"] or ""),
            }
            for row in conn.execute(
                f"SELECT id, root_cause, fix_applied, task_id FROM mistake_pool "  # noqa: S608 - placeholders only
                f"WHERE id IN ({placeholders})",
                ids,
            )
        }
    finally:
        conn.close()
    return [
        {**item, **extra.get(int(item.get("mistake_id", -1)), {})} for item in lessons
    ]


def practice_history(db: Path) -> Optional[str]:
    """Every text this system has recorded about work it has done, once.

    Returns None when the history cannot be read, and callers must then treat
    EVERY target as practised: unknown history must never inflate NOVEL.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        parts = [
            str(row[0] or "")
            for row in conn.execute("SELECT goal_pattern FROM procedural_skills")
        ]
        for row in conn.execute(
            "SELECT root_cause, fix_applied, lesson_text, task_id FROM mistake_pool"
        ):
            parts.extend(str(value or "") for value in row)
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    # Since slice 2.4c-B new arcs are learned ONLY in the skill library, and
    # `procedural_skills` is history. A target practised there is practised.
    library = library_goals(db.with_name(LIBRARY_DB.name))
    if library is None:
        return None
    return "\n".join(parts + library)


def library_goals(library_db: Path) -> Optional[list[str]]:
    """Every goal the skill library holds; [] when there is no library.

    None when a library exists but cannot be read: unknown history must never
    inflate NOVEL, so the caller then treats every target as practised.
    """
    import sqlite3

    if not library_db.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{library_db.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='institutional_skills'"
        ).fetchone()
        if present is None:
            return []
        return [
            str(json.loads(row[0]).get("problem_signature") or "")
            for row in conn.execute("SELECT payload_json FROM institutional_skills")
        ]
    except (sqlite3.Error, ValueError):
        return None
    finally:
        conn.close()


def practised(history: Optional[str], target) -> bool:
    """Has this system recorded ANY learning on this target before?

    Used to choose targets, not to classify pairs: `collect_targets` is a
    deterministic, history-blind ranking, so its top N are exactly the targets
    earlier runs already practised, and the NOVEL bucket -- the headline claim
    -- came out structurally empty. Selection now draws from both sides.
    """
    if history is None:
        return True
    return target.label in history or _test_filename(target) in history


def task_prompt(target) -> str:
    """The task exactly as the model is asked it -- and, for the ON arm, the
    text recall is queried with, because in a live turn recall runs against the
    user's own words. One derivation, so the two can never drift apart."""
    return PROMPT.format(
        module=target.module,
        import_path=_import_path(target.module),
        function=target.function,
        source=target.source.rstrip(),
    )


def select_targets(
    candidates: list, n: int, is_practised, *, novel_only: bool = False
) -> tuple[list, int, int]:
    """Up to *n* targets, alternating unpractised and practised.

    Alternating keeps BOTH questions answerable in one run: SEEN needs targets
    the animal has worked on, NOVEL needs ones it has not. Order within each
    side is `collect_targets`' own reproducible ranking, so the choice depends
    on history and never on outcomes.

    *novel_only* takes unpractised targets alone: the judged number is NOVEL,
    and a cohort sized for power spends none of its budget on SEEN context.
    """
    flags = [(t, bool(is_practised(t))) for t in candidates]
    fresh = [t for t, seen in flags if not seen]
    known = [] if novel_only else [t for t, seen in flags if seen]
    chosen: list = []
    n_fresh = n_known = 0
    while len(chosen) < n and (fresh or known):
        if fresh and len(chosen) < n:
            chosen.append(fresh.pop(0))
            n_fresh += 1
        if known and len(chosen) < n:
            chosen.append(known.pop(0))
            n_known += 1
    return chosen, n_fresh, n_known


#: Tables whose contents ARE the animal's memory. If any of them changes
#: during a run, later ON arms were shown different memory than earlier ones
#: and the pairs are no longer measuring the same thing.
MEMORY_TABLES = (
    "mistake_pool",
    "procedural_skills",
    "compiled_playbooks",
    "learning_events",
)

#: The institutional skill library, which the live `skills` slot recalls from
#: (deviation D3; since Phase 2 slice 2.4c-B the only skill store). Frozen for
#: the run exactly like the tables above.
LIBRARY_TABLES = ("institutional_skills", "skill_trails")
#: The store the ON arm recalls skills from, recorded with every run. Runs
#: before slice 2.4c-B recorded "legacy" or "pilot"; "pilot" read this same
#: store.
SKILL_STORE = "library"


def live_skills_slot() -> Any:
    """The `skills` slot the live turn would recall from, built the same way.

    Deviation D3 (docs/learning/PAYOFF_PREREGISTRATION.md): the ON arm used to
    recall through a `SkillMemory` of its own. It recalls through the slot
    production builds, whose recall answers from the institutional library's
    ACTIVE skills only. Since slice 2.4c-B that is the only slot there is:
    what the benchmark measures follows what the turn does.
    """
    from aios.application.memory.institutional_skills import (
        SkillTrailIndex,
        build_skills_slot,
    )
    from aios.domain.learning.repository import SkillRepository

    repository = SkillRepository(LIBRARY_DB)
    return build_skills_slot(
        repository=repository,
        trails=SkillTrailIndex(repository.database),
        history=SkillMemory(db_path=DB, read_only=True),
    )


def library_active_count() -> int:
    """ACTIVE institutional skills: all a pilot-mode ON arm can recall."""
    from aios.application.memory.institutional_skills import library_summary

    return int(library_summary(LIBRARY_DB).get("library_active", 0))


def refuse_if_moved(
    before: dict[str, str], after: dict[str, str], tables: tuple[str, ...], what: str
) -> None:
    """Refuse the run when any fingerprinted table changed during it."""
    moved = {
        table: (before.get(table), after.get(table))
        for table in tables
        if before.get(table) != after.get(table)
    }
    if moved:
        raise CorpusError(
            f"{what} changed during the benchmark ({moved}); the arms were not "
            "measuring the same memory, so no number is reported"
        )


def store_fingerprint(
    db: Path, tables: tuple[str, ...] = MEMORY_TABLES
) -> dict[str, str]:
    """A digest of every row of every memory table, read-only.

    CONTENT, not counts. The first version fingerprinted `COUNT(*)`, which
    catches an INSERT and misses every write that matters most here: a lesson
    flipped to verified, a skill promoted, a playbook decompiled -- UPDATEs,
    which change what recall returns without changing how many rows there are.
    Four independent review lenses found that; a guard blind to the writes
    that change its subject is not a guard.

    Hashed per table so a refusal can say WHICH memory moved.
    """
    import hashlib
    import sqlite3

    out: dict[str, str] = {}
    if not Path(db).is_file():
        return {table: "absent" for table in tables}
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        for table in tables:
            digest = hashlib.sha256()
            try:
                # `table` comes only from the fixed tuple above.
                rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid")  # noqa: S608
                for row in rows:
                    digest.update(repr(tuple(row)).encode("utf-8"))
                out[table] = digest.hexdigest()
            except sqlite3.OperationalError:
                out[table] = "absent"
    finally:
        conn.close()
    return out


def recalled_context(reflector, skills: SkillMemory, query: str, session_id: str):
    """What this system actually remembers about a task like this one.

    Calls `_recall_lessons` and `_recall_skills` -- the same two functions the
    live turn path calls -- and formats with the same two blocks. Nothing here
    is a benchmark's idea of recall.

    The session_id is FRESH for every pair, deliberately. `recall_relevant`
    returns same-session pending lessons plus verified cross-session ones; a
    reused session would let a lesson recorded moments earlier in this very run
    count as "what the animal remembered", which measures short-term echo
    rather than accumulated knowledge. A new session means only VERIFIED
    cross-task lessons survive the filter -- the harder and more honest
    question.

    Both calls are already fail-soft in production (they log and return []), so
    a store error reads here as "recalled nothing" rather than as "memory is
    worthless", and the pair is then reported NOT COMPARABLE.
    """
    # Plan Phase 4c: this harness learns and recalls through raw stores, as
    # no principal, so its rows are unattributed and the store matches them
    # (NULL-safe). It never went through the recall gate; scoping changes
    # nothing it measures.
    lessons = _recall_lessons(reflector, session_id, query, principal=None) or []
    verified = _recall_skills(skills, query) or []
    blocks = [
        block
        for block in (lessons_prompt_block(lessons), skills_prompt_block(verified))
        if block
    ]
    return (chr(10) * 2).join(blocks), lessons, verified


#: Deviation D5 (2026-09-27): the placebo's seed. Fixed, so while the store is
#: unchanged a target draws the same placebo in the baseline and at Phase 8.
PLACEBO_SEED = "payoff-D5-20260927"


def placebo_pool(db: Path) -> list[dict]:
    """Every stored lesson a placebo may draw from, read-only, in id order.

    Verified or pending: real lessons of the kind recall shows. Never
    `superseded` -- those were retired, and a placebo of known-bad lessons would
    flatter ON. Each is shaped like a recalled lesson, with its TRUE status, so
    the production block labels it exactly as it is stored.
    """
    import sqlite3

    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return [
            {
                "mistake_id": int(row[0]),
                "error_type": str(row[1] or ""),
                "lesson_text": str(row[2] or ""),
                "verification_status": str(row[3]),
            }
            for row in conn.execute(
                "SELECT id, error_type, lesson_text, verification_status "
                "FROM mistake_pool WHERE verification_status IN ('verified', 'pending') "
                "ORDER BY id"
            )
        ]
    finally:
        conn.close()


def placebo_context(
    pool: list[dict],
    *,
    own_lessons: list[dict],
    own_skills: list[dict],
    target_label: str,
):
    """The same amount of stored lessons as ON's, but ones recall did NOT pick.

    Deviation D5: the calibration found recall gives every task the same five
    of the store's seven verified lessons, so D4's "recalled for other work"
    placebo could never be drawn. This one takes as many lessons as ON saw,
    none of them ON's, with a fixed seed per target, from `placebo_pool`. It
    keeps ON's skills block unchanged, so ON and PLACEBO differ ONLY in which
    lessons are shown: the question is whether recall's choice beats other
    stored lessons of the same kind.

    Matched means that many such lessons existed. A pair with no recalled
    lesson has nothing to swap, so it is unmatched too, never a copy of ON.
    """
    import random

    own = {int(item["mistake_id"]) for item in own_lessons if "mistake_id" in item}
    candidates = [item for item in pool if item["mistake_id"] not in own]
    wanted = len(own_lessons)
    if wanted == 0 or len(candidates) < wanted:
        return "", [], False
    picked = random.Random(f"{PLACEBO_SEED}:{target_label}").sample(candidates, wanted)
    blocks = [
        block
        for block in (lessons_prompt_block(picked), skills_prompt_block(own_skills))
        if block
    ]
    return "\n\n".join(blocks), picked, True


def restore_pristine(corpus) -> None:
    """Return the corpus to its committed state, and prove it did.

    Every arm is graded by `git status` over the whole corpus, so anything an
    earlier arm left behind is charged to every later one. Removing only the
    test file was not enough: the FIRST official Phase 0 run
    (20260925T045128-40a08711) had a model-written test for `load_ledger`
    create `temp_ledger.json` in the corpus root at arm 23, and from there to
    arm 60 every arm was rejected as "source outside tests/ was modified" --
    a dead instrument manufacturing failures, including for an arm whose own
    test passed clean. The rule itself is unchanged: an arm whose OWN test
    litters the tree is still rejected. What changes is that it cannot be
    rejected for someone else's.

    IGNORED paths are removed too (`clean -fdx`), and the check lists them
    (`--ignored`). The first version kept them, reasoning that the grader
    excuses build artefacts -- but the grader excuses only `__pycache__`,
    `.pytest_cache`, `*.pyc` and `.coverage`, while the corpus's `.gitignore`
    hides far more (`data/`, `.aios/`, `node_modules/`, ...). `clean -fd` never
    removes an ignored path and `git status` never reports one, so a model's
    test writing under `data/` would have carried into every later arm
    invisibly to both checks: the same contamination, relocated (adversarial
    review, 2026-09-25; Deviation D2). Everything a clean corpus needs is
    committed, and everything ignored is regenerated. A corpus that still is
    not pristine afterwards refuses the run rather than grading on it.
    """
    root = str(corpus.root)
    for args in (["checkout", "--", "."], ["clean", "-fdx", "--", "."]):
        subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True, check=False
        )
    status = subprocess.run(
        ["git", "-C", root, "status", "--porcelain=v1", "-uall", "--ignored"],
        capture_output=True,
        text=True,
        check=False,
    )
    leftovers = [
        line
        for line in status.stdout.splitlines()
        if line[3:].strip().strip('"')
        and not _is_build_artefact(line[3:].strip().strip('"'))
    ]
    if status.returncode != 0 or leftovers:
        raise CorpusError(
            "the corpus could not be restored to its committed state before an "
            "arm; grading on it would charge one arm for another's leftovers: "
            + ("; ".join(leftovers[:5]) or status.stderr.strip()[:200])
        )


#: A provider saying "not now" before any reply exists. Only these are
#: retried: a timeout or a validation error is the registered "never reached
#: the model", and retrying it would change the exclusion rule.
TRANSIENT_PROVIDER_ERRORS = (
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelNotReadyException",
    "TooManyRequests",
    "Too many requests",
)
TRANSPORT_RETRY_WAITS = (15, 45, 90)


def _transient(exc: Exception) -> bool:
    text = str(exc)
    return any(marker in text for marker in TRANSIENT_PROVIDER_ERRORS)


def run_arm(
    corpus,
    client,
    target,
    *,
    arm: str,
    extra_context: str,
    lessons: int,
    skills_count: int,
) -> ArmResult:
    """One graded attempt. Identical to the other arm but for *extra_context*."""
    restore_pristine(corpus)
    started = time.monotonic()
    result = ArmResult(arm=arm, recalled_lessons=lessons, recalled_skills=skills_count)

    prompt = task_prompt(target)
    if extra_context:
        prompt = f"{extra_context}\n\n{prompt}"
    result.prompt_chars = len(prompt)

    reply = None
    for wait in (*TRANSPORT_RETRY_WAITS, None):
        try:
            reply = complete_via(client, prompt, system=SYSTEM)
            break
        except LLMError as exc:
            if wait is not None and _transient(exc):
                # No reply exists yet, so a retry cannot be chosen by outcome.
                result.transport_retries += 1
                time.sleep(wait)
                continue
            result.outcome = "model_error"
            result.notes.append(str(exc)[:200])
            result.seconds = time.monotonic() - started
            return result

    result.reached_model = True
    code = _extract_code(reply)
    if not code:
        result.outcome = "no_code_block"
        result.seconds = time.monotonic() - started
        return result

    rel = _test_filename(target)
    path = corpus.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code + "\n", encoding="utf-8")
    try:
        verdict = grade_pin_test(
            corpus,
            new_test=[rel],
            target_module=target.module,
            target_function=target.function,
            guard_selection=GUARD_SELECTION,
        )
    finally:
        # The arms must not contaminate each other. Both write the SAME
        # filename, so a leftover from one arm would be graded as the other's
        # work -- and `suite_still_green` would blame the wrong arm. In a
        # `finally` because the grader RAISES on a hollow suite, and that is
        # exactly the path on which "probably overwritten anyway" is false.
        try:
            path.unlink()
        except OSError:
            pass

    result.earned = verdict.earned
    result.outcome = (
        "earned"
        if verdict.earned
        else "vacuous"
        if verdict.passes_clean and not verdict.fails_when_mutated
        else "rejected"
    )
    result.notes.extend(note[:200] for note in verdict.notes[:3])
    result.seconds = time.monotonic() - started
    return result


def run_benchmark(
    *,
    models: str,
    targets: int,
    model_timeout: int,
    ref: str = "HEAD",
    target_labels: Optional[list[str]] = None,
    samples: int = 1,
    placebo: bool = False,
    novel_only: bool = False,
    exclude_labels: Optional[list[str]] = None,
) -> tuple[list[Pair], str, str]:
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    init_memory_db(DB)
    memory_before = store_fingerprint(DB)
    mistakes = MistakeMemory(db_path=DB)
    # D3: recall through the live slot. Fingerprinted AFTER it is built, so its
    # one-time setup (adopting migrated trail ids) is not read as learning.
    skills = live_skills_slot()
    library_before = store_fingerprint(LIBRARY_DB, LIBRARY_TABLES)

    client = None
    for spec in [m.strip() for m in models.split(",") if m.strip()]:
        try:
            client, _served = resolve_client(spec, timeout_s=model_timeout)
            break
        except CorpusError as exc:
            print(f"  {spec:<40} UNUSABLE — {str(exc)[:70]}")
    if client is None:
        raise CorpusError("no model in the ladder is usable")

    # The store is passed EXPLICITLY -- ReflectionAgent refuses to guess one,
    # so recall can never read from a different database than the one the
    # learning runs wrote to. Built AFTER the client, because it needs one.
    reflector = ReflectionAgent(client, mistakes=mistakes, db_path=DB)

    pairs: list[Pair] = []
    print(f"run id  : {run_id}")

    # `ref` pins WHICH code is measured. Pin it to a commit already on master
    # and the corpus sha the result cites survives a squash merge of whatever
    # branch this harness happens to live on -- the lesson of #359 and #363.
    with self_corpus(REPO_ROOT, WORKTREE, ref=ref) as corpus:
        corpus_sha = corpus.sha
        print(f"corpus  : {corpus.root} @ {corpus.sha[:12]}")

        # THE POSITIVE CONTROL, before any model is asked anything. A
        # known-correct pin test must EARN through the full grader, which also
        # proves the guard suite is green at this ref. Without it a red guard
        # suite fails every arm of every pair, they tie, and the report reads
        # "no measurable difference" -- a confident null from a broken
        # instrument. The docstring claimed a green baseline; nothing ran one.
        ok, detail = run_self_check(corpus)
        if not ok:
            raise CorpusError(f"positive control failed, instrument invalid: {detail}")
        print(f"control : grader earns a known-correct test ({detail[:60]})\n")

        candidates = collect_targets(corpus.root)
        history = practice_history(DB)
        # Calibration targets are EXCLUDED from a judged run, so the numbers
        # used to size it (base rate, repeat variability) were never measured
        # on the work it is judged on.
        excluded = set(exclude_labels or ())
        if target_labels is not None:
            overlap = [label for label in target_labels if label in excluded]
            if overlap:
                raise CorpusError(
                    f"{len(overlap)} frozen target(s) are also excluded (calibration) "
                    f"targets: {overlap[:3]}. The two sets must be disjoint."
                )
            # A FROZEN list. A paired before/after comparison means nothing if
            # the second run picks different targets -- and the selection rule
            # reads practice history, which the intervening learning changes.
            # Every registered label must still exist; a silently shorter list
            # would change the experiment without saying so.
            by_label = {t.label: t for t in candidates}
            missing = [label for label in target_labels if label not in by_label]
            if missing:
                raise CorpusError(
                    f"{len(missing)} registered target(s) no longer exist at this "
                    f"ref: {missing[:3]}. The frozen list cannot be honoured, so "
                    "the paired comparison is refused rather than quietly shrunk."
                )
            chosen = [by_label[label] for label in target_labels]
            n_fresh = sum(1 for t in chosen if not practised(history, t))
            n_known = len(chosen) - n_fresh
        else:
            chosen, n_fresh, n_known = select_targets(
                [t for t in candidates if t.label not in excluded],
                targets,
                lambda t: practised(history, t),
                novel_only=novel_only,
            )
        print(
            f"targets : {len(chosen)} chosen -- {n_fresh} never practised, {n_known} practised\n"
        )

        queries = [task_prompt(t) for t in chosen]
        # Read once, from the store the run has frozen (fingerprinted above).
        pool = placebo_pool(DB) if placebo else []
        for index, target in enumerate(chosen):
            # Alternate which arm goes first. A fixed order would let "the
            # second attempt runs against a warmer cache" look like payoff.
            # With a placebo the three arms rotate.
            if placebo:
                arms = ("on", "off", "placebo")
                order = arms[index % 3 :] + arms[: index % 3]
            else:
                order = ("on", "off") if index % 2 == 0 else ("off", "on")
            first = order[0]
            pair = Pair(target=target.label, first=first)
            print(f"  {target.label}   (first: {first.upper()})")

            # THE QUERY IS THE TASK. A live turn recalls against the user's own
            # text, and for this task the user's text is the task prompt. The
            # first version queried an invented "pin the behaviour of X" label
            # that shares its boilerplate with every pin arc's goal_pattern --
            # manufacturing lexical matches no real turn would get.
            query = queries[index]
            context, lessons, verified = recalled_context(
                reflector, skills, query, f"payoff-{run_id}-{index}"
            )
            n_lessons, n_skills = len(lessons), len(verified)
            # SEEN if ANY recalled item was recorded on this very target, read
            # against the lesson's FULL row. A win there is memory helping on a
            # repeat, not transferring to new work.
            pair.seen = any(
                about_this_target(item, target)
                for item in enrich_lessons(DB, lessons) + verified
            )

            if not context:
                # THE VACUITY GUARD. With nothing recalled the two prompts are
                # byte-identical, so their difference measures model variance,
                # not learning. Counting it as "no benefit" would let an empty
                # memory manufacture a confident 0.00 -- the exact shape of
                # organ 55's vacuous-FAIL class.
                pair.reason = (
                    "recall returned nothing for this task, so both arms would "
                    "see identical prompts"
                )
                print(f"    NOT COMPARABLE — {pair.reason}")
                pairs.append(pair)
                continue

            contexts = {"on": (context, n_lessons, n_skills), "off": ("", 0, 0)}
            if placebo:
                p_text, p_lessons, matched = placebo_context(
                    pool,
                    own_lessons=lessons,
                    own_skills=verified,
                    target_label=target.label,
                )
                if matched:
                    contexts["placebo"] = (p_text, len(p_lessons), n_skills)
                else:
                    pair.placebo_reason = (
                        "no placebo of the same size: ON recalled no lesson, or the "
                        "store holds too few other verified or pending lessons"
                    )
                    order = tuple(arm for arm in order if arm != "placebo")

            runs: dict[str, list[dict]] = {arm: [] for arm in order}
            for _sample in range(samples):
                for arm in order:
                    text, n_l, n_s = contexts[arm]
                    result = run_arm(
                        corpus,
                        client,
                        target,
                        arm=arm,
                        extra_context=text,
                        lessons=n_l,
                        skills_count=n_s,
                    )
                    runs[arm].append(asdict(result))
                    print(
                        f"    {arm.upper():<7} {result.outcome:<14} "
                        f"earned={result.earned} ({result.seconds:.0f}s)"
                    )
            for arm, results in runs.items():
                setattr(pair, arm, results[0])
            if samples > 1:
                pair.samples = runs

            def reached(arm: str) -> bool:
                return all(r["reached_model"] for r in runs.get(arm, []))

            if not (reached("on") and reached("off")):
                pair.reason = (
                    "an arm never reached the model; a provider outage is not a "
                    "model failing and must not be scored as one"
                )
                print(f"    NOT COMPARABLE — {pair.reason}")
            else:
                pair.comparable = True
                pair.reason = (
                    f"ON saw {n_lessons} lesson(s) and {n_skills} verified "
                    f"skill(s) the OFF arm did not"
                )
            if "placebo" in runs:
                if not reached("placebo"):
                    pair.placebo_reason = "the placebo arm never reached the model"
                elif not pair.comparable:
                    pair.placebo_reason = "the ON/OFF pair is not comparable"
                else:
                    pair.placebo_comparable = True
                    pair.placebo_reason = (
                        f"PLACEBO saw {contexts['placebo'][1]} stored lesson(s) recall "
                        f"did not pick, and the same {contexts['placebo'][2]} skill(s) "
                        "as ON"
                    )
            pairs.append(pair)

    # Something wrote to the animal's memory while it was being measured -- a
    # live backend serving turns, a scheduled learning drive, anything. Later
    # ON arms were then shown different memory than earlier ones, so the pairs
    # no longer measure one thing. Refused, not averaged over.
    refuse_if_moved(
        library_before,
        store_fingerprint(LIBRARY_DB, LIBRARY_TABLES),
        LIBRARY_TABLES,
        "the skill library",
    )
    refuse_if_moved(
        memory_before, store_fingerprint(DB), MEMORY_TABLES, "the memory store"
    )

    return pairs, run_id, corpus_sha


def summarise(pairs: list[Pair]) -> dict:
    """The numbers, computed once, so the printed report and the recorded trail
    can never disagree about what was measured."""

    def arm_stats(group: list[Pair], arm: str = "on", other: str = "off") -> dict:
        # Per TARGET, in earned samples: with one sample these are the familiar
        # McNemar counts, and with K they are integers in [-K, K]. The target is
        # the unit either way, so K samples of one target are never counted as
        # K independent pairs.
        mine = [p.earned_samples(arm) for p in group]
        theirs = [p.earned_samples(other) for p in group]
        diffs = [a - b for a, b in zip(mine, theirs)]
        k = max((len(p.samples.get(arm) or [None]) for p in group), default=1)
        n = len(group)
        wins = sum(1 for d in diffs if d > 0)
        losses = sum(1 for d in diffs if d < 0)
        return {
            "arms": [arm, other],
            "pairs": n,
            "samples": k,
            "on_earned": sum(mine),
            "off_earned": sum(theirs),
            "payoff": (sum(mine) - sum(theirs)) / (n * k) if n else None,
            "on_only": wins,
            "off_only": losses,
            "p_value": mcnemar_exact(wins, losses)
            if k == 1
            else sign_flip_exact(diffs),
        }

    comparable = [p for p in pairs if p.comparable]
    summary = {
        "attempted": len(pairs),
        "comparable": len(comparable),
        "not_comparable": [
            {"target": p.target, "reason": p.reason} for p in pairs if not p.comparable
        ],
        "all": arm_stats(comparable),
        "novel": arm_stats([p for p in comparable if not p.seen]),
        "seen": arm_stats([p for p in comparable if p.seen]),
        "transport_retries": sum(
            int(result.get("transport_retries", 0))
            for p in pairs
            for results in (
                p.samples.values()
                if p.samples
                else [[r] for r in (p.on, p.off, p.placebo) if r]
            )
            for result in results
        ),
    }
    if any(p.placebo is not None or p.placebo_reason for p in pairs):
        # H1c: does what memory SAYS help, beyond a placebo of the same size?
        summary["content_novel"] = arm_stats(
            [p for p in comparable if p.placebo_comparable and not p.seen],
            "on",
            "placebo",
        )
        summary["placebo_not_comparable"] = [
            {"target": p.target, "reason": p.placebo_reason}
            for p in pairs
            if p.comparable and not p.placebo_comparable
        ]
    return summary


#: Below this a difference is reported as a direction, never as a finding.
SIGNIFICANCE = 0.05


def _stat_lines(stats: dict) -> list[str]:
    first, second = (a.upper() for a in stats.get("arms", ["on", "off"]))
    k = stats.get("samples", 1)
    out = [
        f"    {first} earned {stats['on_earned']}/{stats['pairs'] * k}   "
        f"{second} earned {stats['off_earned']}/{stats['pairs'] * k}   "
        f"payoff {stats['payoff']:+.0%}"
        + (f"   ({k} samples per arm per target)" if k > 1 else "")
    ]
    if k == 1:
        out.append(
            f"    discordant: {first}-only {stats['on_only']}, "
            f"{second}-only {stats['off_only']}"
        )
    else:
        out.append(
            f"    targets where {first} earned more: {stats['on_only']}, "
            f"fewer: {stats['off_only']} (exact sign-flip test)"
        )
    return out


def _verdict(stats: dict, *, family: bool = False, subject: str = "MEMORY") -> str:
    if not stats["pairs"]:
        return "no pairs"
    discordant = stats["on_only"] + stats["off_only"]
    if discordant == 0:
        return (
            "NO MEASURABLE DIFFERENCE -- every pair came out the same both ways. "
            "That is a result, not a failure to measure."
        )
    if family:
        direction = "positive" if stats["payoff"] > 0 else "negative or zero"
        return (
            f"raw p={stats['p_value']:.3f}, direction {direction}. NOT a verdict on "
            "its own: significance is Holm over the registered family of judged "
            "tests, applied in the result document once every member exists."
        )
    if stats["p_value"] >= SIGNIFICANCE:
        return (
            f"NOT DISTINGUISHABLE FROM NOISE (p={stats['p_value']:.2f}, "
            f"{discordant} discordant pair(s)). A direction, not a finding."
        )
    if stats["payoff"] > 0:
        return f"{subject} HELPED (p={stats['p_value']:.3f})"
    return (
        f"{subject} HURT (p={stats['p_value']:.3f}). The most useful number here; "
        "it must not be explained away."
    )


def render(pairs: list[Pair]) -> str:
    summary = summarise(pairs)
    out = ["", "LEARNING PAYOFF -- is what the animal remembered worth anything?", ""]
    out.append(
        f"  {summary['attempted']} attempted / {summary['comparable']} comparable"
    )
    out.append("")
    if not summary["comparable"]:
        out.append("  NO NUMBER. Nothing was comparable, so nothing was measured.")
        out.append(
            "  This is not a payoff of zero. A benchmark that reports 0% having "
            "reached no control is the failure it exists to catch."
        )
        for row in summary["not_comparable"]:
            out.append(f"    - {row['target'][:60]}: {row['reason']}")
        return "\n".join(out)

    # ONE judged number, ONE significance test. Three McNemar tests at
    # uncorrected alpha over overlapping data would let whichever came out best
    # be quoted -- so NOVEL, the only claim that memory helps on work the animal
    # has not already done, carries the verdict. SEEN and ALL are printed as
    # context and deliberately carry no significance language at all.
    # With more than one judged test (the placebo design), no raw p decides
    # anything on its own: significance is Holm over the registered family,
    # which includes tests from other runs.
    family = "content_novel" in summary
    for key, title, judged in (
        (
            "novel",
            "THE JUDGED NUMBER -- NOVEL targets (transfer to unpractised work)",
            True,
        ),
        (
            "seen",
            "context only -- SEEN targets (recall included this very target)",
            False,
        ),
        ("all", "context only -- ALL comparable pairs", False),
    ):
        stats = summary[key]
        out.append(f"  {title}")
        if not stats["pairs"]:
            out.append(
                "    (none) -- NO JUDGED NUMBER this run" if judged else "    (none)"
            )
            out.append("")
            continue
        out.extend(_stat_lines(stats))
        if judged:
            out.append(f"    {_verdict(stats, family=family)}")
        out.append("")

    if "content_novel" in summary:
        stats = summary["content_novel"]
        out.append(
            "  JUDGED -- CONTENT: ON vs PLACEBO on NOVEL targets (does what memory "
            "says help, beyond memory of the same size selected for other work?)"
        )
        if not stats["pairs"]:
            out.append("    (none) -- NO CONTENT NUMBER this run")
        else:
            out.extend(_stat_lines(stats))
            out.append(
                f"    {_verdict(stats, family=family, subject='MEMORY CONTENT')}"
            )
        out.append("")

    # WHAT THIS MEASURED, AND WHAT IT DID NOT. Printed with every number so the
    # scope of the claim travels with it.
    out.append("  scope:")
    out.append(
        "    channels exercised: recalled lessons + verified skills. NOT exercised: "
        "semantic memory, facts/graph recall, self-model."
    )
    out.append(
        "    recall is PREPENDED to the task. ON vs OFF alone does not separate a "
        "content effect from a prompt-length/position effect"
        + (
            "; ON vs PLACEBO does."
            if "content_novel" in summary
            else " (run with --placebo for that)."
        )
    )
    out.append(
        "    SEEN is detected from text (label, pin-test filename, module + "
        "function, or a distinctive function name). A lesson that names none of "
        "those is filed NOVEL -- so NOVEL is an upper bound on transfer."
    )
    out.append("")

    if summary["not_comparable"]:
        out.append(f"  {len(summary['not_comparable'])} pair(s) not comparable:")
        for row in summary["not_comparable"]:
            out.append(f"    - {row['target'][:60]}: {row['reason']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    def _at_least_one(value: str) -> int:
        # `collect_targets(limit=0)` means "no cap", so a --targets 0 dry run
        # would have silently asked the model about EVERY function in aios/.
        number = int(value)
        if number < 1:
            raise argparse.ArgumentTypeError("--targets must be at least 1")
        return number

    parser.add_argument("--targets", type=_at_least_one, default=10)
    parser.add_argument("--models", default="ollama.qwen2.5-coder:7b")
    # 240s lost 2 of 6 preview pairs to timeouts. A timeout makes a pair NOT
    # COMPARABLE rather than a loss, so it costs data, not honesty -- but the
    # ON prompt is longer, so a tight budget would thin ON's pairs first.
    parser.add_argument("--model-timeout", type=int, default=420)
    parser.add_argument(
        "--ref",
        default="origin/master",
        help=(
            "the commit whose code is measured. Defaults to origin/master so the "
            "corpus sha a result cites survives a squash merge of the branch "
            "this harness happens to be on."
        ),
    )
    parser.add_argument(
        "--target-labels",
        type=Path,
        default=None,
        help=(
            "a file of target labels (one `module::function` per line) to run "
            "INSTEAD of selecting. Used to re-run a pre-registered, frozen list "
            "so a before/after comparison measures the same work."
        ),
    )

    def _positive(value: str) -> int:
        number = int(value)
        if number < 1:
            raise argparse.ArgumentTypeError("--samples must be at least 1")
        return number

    parser.add_argument(
        "--samples",
        type=_positive,
        default=1,
        help="samples per arm per target; the target stays the unit of analysis",
    )
    parser.add_argument(
        "--placebo",
        action="store_true",
        help="add a PLACEBO arm: as many stored lessons as ON saw, not recall's picks",
    )
    parser.add_argument(
        "--novel-only",
        action="store_true",
        help="select never-practised targets only (the judged NOVEL question)",
    )
    parser.add_argument(
        "--exclude-targets",
        type=Path,
        default=None,
        help="a file of target labels never to select (e.g. calibration targets)",
    )
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=PREREGISTRATION,
        help="the pre-registration this run is bound to; its sha256 is recorded.",
    )
    args = parser.parse_args(argv)

    labels: Optional[list[str]] = None
    if args.target_labels is not None:
        labels = [
            line.strip()
            for line in args.target_labels.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not labels:
            parser.error(f"{args.target_labels} lists no targets")

    excluded: Optional[list[str]] = None
    excluded_sha: Optional[str] = None
    if args.exclude_targets is not None:
        raw = args.exclude_targets.read_bytes()
        excluded_sha = text_sha256(raw)
        excluded = [
            line.strip()
            for line in raw.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    # Bind the result to the hypothesis it was run under. A number whose
    # registration can be edited after the fact is not pre-registered.
    prereg_sha = (
        text_sha256(args.preregistration.read_bytes())
        if args.preregistration.is_file()
        else None
    )

    # A remote-tracking ref resolves against whatever this clone last FETCHED,
    # so an unfetched clone would measure days-old code and cite it correctly.
    # Fetch first; offline is reported, not fatal -- the corpus sha printed
    # below is still exact, it just may not be current.
    if args.ref.startswith("origin/"):
        fetched = subprocess.run(
            ["git", "fetch", "--quiet", "origin", args.ref.split("/", 1)[1]],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if fetched.returncode != 0:
            print(
                f"WARNING: could not fetch {args.ref}; measuring the last fetched "
                f"copy. {fetched.stderr.strip()[:120]}"
            )

    # The harness is recorded separately from the measured code: a reader must
    # be able to tell "the code under test" from "the tool that tested it",
    # and after a squash only the first is guaranteed to stay reachable.
    harness_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()

    try:
        pairs, run_id, corpus_sha = run_benchmark(
            models=args.models,
            targets=args.targets,
            model_timeout=args.model_timeout,
            ref=args.ref,
            target_labels=labels,
            samples=args.samples,
            placebo=args.placebo,
            novel_only=args.novel_only,
            exclude_labels=excluded,
        )
    except CorpusError as exc:
        print(f"\nREFUSED — {exc}")
        _append(
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": "run",
                "outcome": "aborted",
                "error": str(exc),
            }
        )
        return 1

    print(render(pairs))
    _append(
        {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "run",
            "run_id": run_id,
            "outcome": "completed",
            "corpus_sha": corpus_sha,
            "harness_sha": harness_sha,
            "preregistration_sha256": prereg_sha,
            # Hashes of text files are of LF-normalised bytes: what Git stores,
            # so `git show <sha>:<path>` reproduces them on any platform. Rows
            # without this key hashed the checkout's bytes, CRLF on Windows.
            "hash_basis": HASH_BASIS,
            # Always recorded, in run order: this is how a run's list is frozen
            # for the paired re-run (`--target-labels`).
            "target_labels": [p.target for p in pairs],
            "target_list_frozen": labels is not None,
            "models": args.models,
            "samples": args.samples,
            "placebo": args.placebo,
            "novel_only": args.novel_only,
            "excluded_targets": (
                {"count": len(excluded or []), "sha256": excluded_sha}
                if excluded_sha
                else None
            ),
            # D3: which store the ON arm recalled skills from, and how much of
            # it the operator had activated -- all it can recall.
            "skill_store_mode": SKILL_STORE,
            "library_active_at_start": library_active_count(),
            "summary": summarise(pairs),
            "pairs": [asdict(p) for p in pairs],
        }
    )
    print(f"\ntrail: {TRAIL.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
