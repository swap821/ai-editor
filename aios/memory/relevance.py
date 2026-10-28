"""Deterministic lexical relevance helpers for developmental memory.

These helpers deliberately avoid an LLM judge. They are used for lesson, skill,
and outcome retrieval where a transparent, stable score is preferable to a
probabilistic decision about whether past evidence should change behavior.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable

_TOKEN = re.compile(r"[a-z0-9_./-]+")
_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "this",
        "to",
        "use",
        "with",
    }
)


def tokens(text: str) -> set[str]:
    """Return normalized, low-noise tokens from *text*."""
    return {
        token for token in _TOKEN.findall((text or "").lower()) if token not in _STOP
    }


def relevance(query: str, document: str) -> float:
    """Cosine-style set overlap in ``[0, 1]``; zero means no lexical evidence."""
    query_tokens = tokens(query)
    document_tokens = tokens(document)
    if not query_tokens or not document_tokens:
        return 0.0
    overlap = len(query_tokens & document_tokens)
    if not overlap:
        return 0.0
    return round(overlap / math.sqrt(len(query_tokens) * len(document_tokens)), 6)


#: Vocabulary any coding or testing task may contain, so sharing it says
#: nothing about WHICH code a task and a lesson are about. Built from general
#: sources -- English function words, Python keywords and builtins, and the
#: generic words of writing and testing code -- and never naming a module,
#: function, file or domain. Fixed 2026-10-12, before any run it affects
#: (docs/learning/PAYOFF_PREREGISTRATION.md, D9).
_GENERIC_WORDS = frozenset(
    """
    about above after again against all also although am any anything because
    been before being below between both but can cannot could did does doing
    done down during each either else even ever every few further had has have
    having here if into its itself just least less may might more most much
    must my never no nor not now off once only other others our out over own
    per rather same several shall should since so some such than that their
    them then there these they those though through thus too under until up
    upon very via was we were what whatever when where whether which while who
    whom whose why will within without would yet you your
    actual actually always argument arguments assert assertion assertions
    behavior behaviour build call called calling calls case cases change
    changed changes check checked checks code correct correctly create created
    ensure ensured error errors example examples exception exceptions expect
    expected expects fail failed failing fails failure file files fix fixed
    function functions get given import imported imports input inputs line
    lines make makes match matches method methods module modules name names
    new object objects output outputs parameter parameters pass passed passes
    path paths properly result results return returned returning returns run
    running runs should source sure test tested testing tests type types
    update updated use used uses using value values variable variables verify
    verified write writes writing written wrong pytest unittest
    access accessed accessing attribute attributes character characters
    content contents data default defaults empty exist existing exists field
    fields global item items key keys like local message messages number
    numbers option options string strings text
    already another around attempt attempted attempts break breaking breaks
    choose chose complete completely concrete construct constructed contain
    contained containing contains depend depends exactly first following
    genuinely guess guessed instead last next one ones part parts possible
    previous read reading reads real really referenced remove removed
    requirement requirements show shown shows simple simply specific
    specifically still thing things two unless way ways whole yourself
    anywhere assign assigned avoid checking define defined non-empty
    nonempty presence present
    fixture fixtures mock mocked mocking mocks patch patched patching
    constant constants literal literals python raise raised raises symbol
    symbols
    """.split()
)


def _python_vocabulary() -> frozenset[str]:
    import builtins
    import keyword

    return frozenset(
        {word.lower() for word in keyword.kwlist}
        | {name.lower() for name in dir(builtins) if not name.startswith("_")}
    )


GENERIC = _STOP | _GENERIC_WORDS | _python_vocabulary()


def specific_tokens(text: str) -> set[str]:
    """Tokens of *text* that can say which code it is about: not generic
    vocabulary, not a bare number, longer than two characters.

    Edge punctuation is dropped first: ``tokens`` keeps ``.``, ``/`` and ``-``
    so paths survive whole, which also makes a sentence-final "it." a word
    of its own -- one that matched every task (found 2026-10-12). Inner
    punctuation stays: ``aios/x.py`` and ``config.value`` are one name each.
    ``tokens`` itself is unchanged; skill identity hashes are built on it.
    """
    found: set[str] = set()
    for raw in tokens(text):
        token = raw.strip("./-")
        if token and token not in GENERIC and not token.isdigit() and len(token) > 2:
            found.add(token)
    return found


def specific_relevance(query: str, document: str) -> float:
    """``relevance`` over specific tokens only, in ``[0, 1]``.

    Zero unless the two share at least one specific term. Plain ``relevance``
    counts any shared word, so a long task and a long lesson nearly always
    overlap on generic vocabulary -- which is how lesson recall came to return
    the same lessons for every task (calibration run, 2026-09-27).
    """
    query_tokens = specific_tokens(query)
    document_tokens = specific_tokens(document)
    shared = query_tokens & document_tokens
    if not shared:
        return 0.0
    return round(len(shared) / math.sqrt(len(query_tokens) * len(document_tokens)), 6)


# --------------------------------------------------------------------------- #
# Which code a lesson is about (D13, 2026-10-28)
# --------------------------------------------------------------------------- #

#: Where practice records a lesson's code: ``<kind>:<run>:<module>.py::<function>``.
#: Searched, not anchored: a redacted run id can itself contain colons.
_TASK_HOME = re.compile(r"(?P<module>[\w./-]*\w\.py)?::(?P<function>[A-Za-z_]\w*)")
#: A module path (``aios/council/reasoning.py``). Only one with a directory
#: counts: a bare ``auth.py`` in prose, or the ``ce.py`` the secret scanner
#: left of ``…/provenance.py``, names no particular code.
_PATH = re.compile(r"[\w./-]*\w\.py\b")
#: A dotted name a lesson's text names (``aios.agents.tool_handlers.verify_command``).
_TEXT_DOTTED = re.compile(r"\baios(?:\.\w+)+")


def _paths(text: str) -> set[str]:
    found = (path.lstrip("./") for path in _PATH.findall(text or ""))
    return {path for path in found if "/" in path}


def _mentions(text: str, name: str) -> bool:
    """Is *name* in *text* whole: not inside a longer name (``x.py`` in
    ``service_x.py``, ``aios.a.b`` in ``aios.a.b_c``)?"""
    return re.search(rf"(?<![\w.]){re.escape(name)}(?!\w)", text) is not None


def distinctive_name(name: str) -> bool:
    """Is *name* specific enough to identify code on its own?

    A short generic name (``run``, ``main``, ``parse``) would match unrelated
    code everywhere; a long or multi-part one (``reconcile_plan_steps``,
    ``learning_public_key``) does not.
    """
    return len(name) >= 12 or name.count("_") >= 2


def lesson_homes(task_id: str, texts: Iterable[str]) -> tuple[set[str], set[str]]:
    """The code a lesson names: ``(module paths and dotted names, functions)``.

    From the task it was learned on, when practice recorded one, and from the
    module paths and ``aios.`` names its own text gives. A lesson that names
    no code has no home.
    """
    modules: set[str] = set()
    functions: set[str] = set()
    match = _TASK_HOME.search(task_id or "")
    if match:
        modules.update(_paths(match["module"] or ""))
        functions.add(match["function"])
    for text in texts:
        modules.update(_paths(text))
        modules.update(_TEXT_DOTTED.findall(text or ""))
    return modules, functions


def names_code(text: str) -> bool:
    """Does *text* name code: a module path or an ``aios.`` dotted name?"""
    return bool(_paths(text) or _TEXT_DOTTED.search(text or ""))


def names_the_same_code(query: str, task_id: str, texts: Iterable[str]) -> bool:
    """Does *query* name code that this lesson is about?

    True when the query names one of the lesson's modules, as a path or as a
    dotted import path (or, for a dotted name like ``aios.pkg.mod.func``, a
    prefix of at least three parts), or one of its functions, if that name is
    distinctive. Measured 2026-10-28 (PAYOFF_D12_RESULT.md): recall by shared
    words showed 150 judged targets lessons that were rarely about their code,
    one of them on 109 targets. A lesson is now recalled across tasks only when
    the task names its code.
    """
    if not query:
        return False
    modules, functions = lesson_homes(task_id, texts)
    for module in modules:
        if module.endswith(".py"):
            if _mentions(query, module) or _mentions(
                query, module[:-3].replace("/", ".")
            ):
                return True
            continue
        parts = module.split(".")
        for size in range(len(parts), 2, -1):
            if _mentions(query, ".".join(parts[:size])):
                return True
    return any(
        distinctive_name(function) and re.search(rf"\b{re.escape(function)}\b", query)
        for function in functions
    )


def signature(text: str) -> str:
    """Stable non-secret signature for grouping similar normalized task text."""
    normalized = " ".join(sorted(tokens(text)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    """Hash text after whitespace/case normalization for exact consolidation."""
    normalized = " ".join((text or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def skill_signature_v2(goal: str, steps: list[str]) -> str:
    """Arc-level identity for a procedural skill: goal tokens + tool sequence.

    Two workflow attempts reinforce ONE trail iff this key matches: identical
    goal-token key (same construction as the goal half of the legacy exact
    signature) AND identical tool-name sequence — order and multiplicity
    preserved, all step ARGUMENTS ignored. Live evidence motivated both halves:
    secret-scanner redaction noise lives only in argument tails (so exact-step
    signatures fragment trails that are the same arc), while arc LENGTH is
    verdict signal (flail arcs with extra repeated steps are failure records;
    collapsing them into clean siblings would launder failures into verified
    trails). ``||`` separates the halves so v2 keys can never collide with the
    legacy single-``|`` signature space.
    """
    goal_key = " ".join(sorted(tokens(goal))[:12])
    arc = "|".join(
        step.split(":", 1)[0].strip().lower() for step in steps if step.strip()
    )
    return hashlib.sha256(f"{goal_key}||{arc}".encode("utf-8")).hexdigest()
