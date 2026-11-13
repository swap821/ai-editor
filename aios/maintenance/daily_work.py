"""GAGOS's daily work on its own frontend: propose, check, review, deliver (D14).

docs/learning/PAYOFF_PREREGISTRATION.md D14 (2026-10-30). The operator decided
that usefulness is starved of real use, not of harnesses, and that he will not
approve every diff: a reviewer does, and he merges. Codex and Claude Code both
reviewed until 2026-11-02; since then Claude Code's acceptance is enough (the
operator: "forget codex now we both r available so that's enough"). This module is the part that needs no process or network of
its own:

* :func:`findings` -- the day's work: one file and one ESLint rule each, from
  the project's own lint, restricted to rules whose fix is behaviour-preserving
  by nature (:data:`FIRST_RULES`) and to files the lab-to-product port does not
  own;
* :func:`proposal_prompt` and :func:`parse_proposal` -- what the frontier model
  is asked, and the one shape of answer accepted (the whole file, once);
* :func:`static_verdict` -- the unattended checks, which execute nothing the
  model wrote: it parses; the rule's warnings in the file are gone; no other
  warning or error appears; no disable comment is added, and nothing a disable
  comment silences is touched or newly hidden; the change is bounded;
* the sandbox step (:mod:`aios.maintenance.sandbox_tests`) -- after those checks
  and before review, a Python proposal's tests run in the executor's sandbox and
  are judged against the base (the operator, 2026-11-03: "Yes honestly");
* :func:`review_prompt` -- what each reviewer reads: the rule, the warnings, the
  whole original file and the diff;
* :class:`DailyLedger` -- every proposal, refusal, review and delivery, durable,
  so the daily report and D14's numbers are read from records, not memory.

A model may propose here; nothing it proposes is applied until its reviewer
accepts it, CI passes and the operator merges. That amends the maintenance
principle "a repair never lets a model write code" for this path only, by the
operator's decision of 2026-10-30.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import uuid
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from aios import config
from aios.core.model_availability import is_usage_limit_error
from aios.domain.reviews import REVIEW_SCHEMA as _REVIEW_SCHEMA
from aios.domain.reviews import parse_review as _parse_review
from aios.maintenance.frontend_static import Comment, StaticResult

#: Rules whose fix does not change behaviour by nature: removing what is unused,
#: or naming a type. React-hooks rules change when effects run, and
#: only-export-components needs edits across files; both wait until the review
#: record shows the loop is trustworthy (D14).
FIRST_RULES: tuple[str, ...] = (
    "no-unused-vars",
    "@typescript-eslint/no-unused-vars",
    "@typescript-eslint/no-explicit-any",
)

#: Comments that silence a check instead of fixing it, read from the comments
#: ESLint's own parser found (a string that looks like one is not one), by how
#: much they cover: the comment and the line after it; the comment's own line;
#: a region up to the matching ``eslint-enable`` (or the end of the file); the
#: whole file. A start is read generously (anywhere in a comment), an end
#: strictly (a block comment that IS an ``eslint-enable``): reading wrong can
#: only widen what is protected, never narrow it.
_NEXT_LINE = re.compile(r"eslint-disable-next-line|@ts-ignore|@ts-expect-error", re.I)
_SAME_LINE = re.compile(r"eslint-disable-line", re.I)
_REGION_START = re.compile(r"eslint-disable(?!-)(?P<rules>.*)", re.I | re.S)
#: Case-sensitive, as ESLint's own directive parser is: /* ESLINT-ENABLE */ is
#: not an enable to ESLint, so it must not end protection here (Codex's
#: post-merge review of #574). Starts stay case-blind: generous is safe there.
_REGION_END = re.compile(r"\s*eslint-enable(?:\s(?P<rules>.*)|$)", re.S)
_WHOLE_FILE = re.compile(
    r"@ts-nocheck|^\s*(?:eslint(?:-env)?|globals?|exported)\s", re.I
)
_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)

#: Bounds on one proposal's change, in changed (added + removed) lines.
#: GAGOS's Python work (2026-11-02): its backend and itself, by ruff's codes:
#: an unused import and an unused local. Each fix removes what the file does
#: not use; what other modules take from it is checked apart
#: (:func:`aios.maintenance.python_static.import_refusal`).
PYTHON_RULES: tuple[str, ...] = ("F401", "F841")


def is_python_rule(rule: str) -> bool:
    """Whether *rule* is ruff's (``F401``, ``E741``), not ESLint's.

    By the code's shape, so a ruff rule added to any list is Python work:
    until 2026-11-04 the batch scanned Python only when ``PYTHON_RULES``
    was asked for, and a day narrowed to E741 alone scanned none.
    """
    return re.fullmatch(r"[A-Z]+[0-9]+", rule) is not None


#: GAGOS's harder work on itself (2026-11-04, the operator: "I want GAGOS
#: HONESTLY 100% complete itself"): warnings whose fix can change behaviour.
#: Each fix must still remove its warnings and add none, and it reaches review
#: only when the sandbox ran tests that exercise its file and they passed
#: (frontend or Python, since D14). react-refresh/only-export-components stays
#: out: its fix moves exports into a new file, and a task changes files that exist.
BEHAVIOUR_RULES: tuple[str, ...] = (
    "react-hooks/set-state-in-effect",
    "react-hooks/exhaustive-deps",
    "F821",
    "E402",
    "E741",
)
#: How a refusal begins when such a fix had no test to run.
UNTESTED_BEHAVIOUR = (
    "a fix that can change behaviour needs tests that exercise its file"
)


def is_python(rel: str) -> bool:
    """A Python file is GAGOS's backend or GAGOS itself; anything else here is
    its frontend."""
    return rel.endswith(".py")


def linter_of(rel: str) -> str:
    return "ruff" if is_python(rel) else "ESLint"


MAX_CHANGED_LINES_BASE = 24
MAX_CHANGED_LINES_PER_WARNING = 8
#: How far, in lines of the original, a fix may reach from the nearest warning
#: it fixes. Measured on GAGOS's first day of hourly work (2026-11-02): every
#: change the reviewer accepted stayed on its warnings' lines; the two it
#: rejected for touching what they were not asked to reached 17 and 24 lines
#: away. Refused here, they cost no review and teach the writer why.
MAX_REACH = 3
#: The reach of a behaviour-changing fix: an effect's body or an import block
#: can sit a few lines from where the warning points. A rename (E741) reaches
#: every use in the file: no reach, only the bound on changed lines.
BEHAVIOUR_REACH: dict[str, int | None] = {"E741": None}
BEHAVIOUR_REACH_DEFAULT = 12


def reach_of(rule: str) -> int | None:
    """How many lines from its nearest warning a fix for *rule* may change."""
    if rule in BEHAVIOUR_RULES:
        return BEHAVIOUR_REACH.get(rule, BEHAVIOUR_REACH_DEFAULT)
    return MAX_REACH


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Finding:
    """One day's unit of work: one file, one rule, its warnings in that file."""

    rel: str
    rule: str
    warnings: tuple[tuple[int, int, str], ...]  # (line, column, message)


def findings(
    results: Mapping[str, StaticResult], *, rules: Sequence[str] = FIRST_RULES
) -> list[Finding]:
    """Every (file, rule) pair with warnings, for the allowed rules, in a
    stable order: the rule's place in *rules*, then the path."""
    out = []
    for rel, result in results.items():
        for rule in rules:
            hits = result.warnings(rule)
            if hits:
                out.append(
                    Finding(
                        rel=rel,
                        rule=rule,
                        warnings=tuple((m.line, m.column, m.message) for m in hits),
                    )
                )
    order = {rule: i for i, rule in enumerate(rules)}
    return sorted(out, key=lambda f: (order[f.rule], f.rel))


# --------------------------------------------------------------------- proposing

PROPOSER_SYSTEM = (
    "You are GAGOS's frontend maintainer. You fix exactly the ESLint warnings "
    "you are given in one file of a React + TypeScript codebase, and nothing "
    "else. Your change must not alter behaviour, rendering, exports, public "
    "names or tests. Never add eslint-disable, @ts-ignore, @ts-nocheck or "
    "@ts-expect-error. Do not reformat, reorder or rename anything you were not "
    "asked to fix. Reply with the complete corrected file in ONE fenced code "
    "block and nothing else."
)

PYTHON_PROPOSER_SYSTEM = (
    "You are GAGOS's backend maintainer. You fix exactly the ruff warnings you "
    "are given in one Python file of GAGOS's own code, and nothing else. Your "
    "change must not alter behaviour, return values, exceptions raised, public "
    "names or anything other modules import from this file. When you remove an "
    "unused variable, keep any call on its right-hand side whose effect "
    "matters. Never add noqa, type: ignore, nosec or pragma comments. Do not "
    "reformat, reorder or rename anything you were not asked to fix. Reply "
    "with the complete corrected file in ONE fenced code block and nothing else."
)


def proposer_system(rel: str) -> str:
    return PYTHON_PROPOSER_SYSTEM if is_python(rel) else PROPOSER_SYSTEM


#: The shape of a placeholder for a span that may not leave the machine (see
#: :func:`mask_lines`): a prefix chosen per file so it never occurs in that file
#: (Codex's review of #566: a fixed ``GAGOSMASK0000`` already in a source file
#: was restored as the private span), then a number. The prefix is the first of
#: ``GAGOSMASKQ_``, ``GAGOSMASKQQ_``, ... the file does not contain: never a
#: random one. A random hex part made a placeholder look like a secret to the
#: secret scanner's entropy test, by chance, and the file could not be sent
#: (2026-11-02: gd-a9f57600cf refused 53 times in 60 maskings).
MASK_TOKEN = re.compile(r"GAGOSMASKQ+_\d{4}")


class MaskingFailed(ValueError):
    """The text could not be masked so that it restores exactly."""


def _middle(line: str, redacted: str) -> tuple[int, int]:
    """The span of *line* between its longest common prefix and suffix with
    *redacted*: everything the redaction touched, in one piece."""
    start = 0
    while start < min(len(line), len(redacted)) and line[start] == redacted[start]:
        start += 1
    end = 0
    while (
        end < min(len(line), len(redacted)) - start
        and line[len(line) - 1 - end] == redacted[len(redacted) - 1 - end]
    ):
        end += 1
    return start, len(line) - end


def mask_lines(
    text: str, redact: Callable[[str], str], *, rounds: int = 4, min_width: int = 1
) -> tuple[str, dict[str, str]]:
    """Hide what GAGOS's egress scrubbers would redact behind placeholders the
    model must keep: ``(masked text, {placeholder: original})``.

    *redact* is the scrubbers themselves (the oracle), never a copy of their
    patterns. The whole text is redacted (so every exemption sees its real
    context) and compared line by line; on each line that changed, the span
    between the longest common prefix and suffix becomes one placeholder, so
    the model still sees the code around it. Repeated until the scrubbers
    change nothing, at most *rounds* times; a later placeholder may wrap an
    earlier one, and :func:`unmask` restores them in reverse. Line count never
    changes, so warning line numbers hold. The caller re-checks the whole
    prompt before sending anything.

    *min_width* starts the placeholder prefix at that many ``Q``s: a task over
    several files masks each file under a prefix of its own, so a placeholder
    moved from one file into another is never restored as the wrong span.
    """
    width = max(1, min_width)
    while f"GAGOSMASK{'Q' * width}_" in text:
        width += 1
    prefix = f"GAGOSMASK{'Q' * width}_"
    mapping: dict[str, str] = {}
    current = text
    for _ in range(rounds):
        redacted = redact(current)
        if redacted == current:
            break
        lines = current.splitlines(keepends=True)
        redacted_lines = redacted.splitlines(keepends=True)
        out = []
        for i, line in enumerate(lines):
            body = line.rstrip("\r\n")
            ending = line[len(body) :]
            if len(redacted_lines) == len(lines):
                other = redacted_lines[i].rstrip("\r\n")
            else:  # a redaction joined lines: judge this line alone
                other = redact(body)
            if other == body:
                out.append(line)
                continue
            start, stop = _middle(body, other)
            if start == stop:  # pure insertion: hide the whole line
                start, stop = 0, len(body)
            token = f"{prefix}{len(mapping):04d}"
            mapping[token] = body[start:stop]
            out.append(body[:start] + token + body[stop:] + ending)
        current = "".join(out)
    if mapping and unmask(current, mapping, masked=current) != text:
        raise MaskingFailed("masking does not restore the file exactly")
    return current, mapping


def unmask(
    text: str, mapping: Mapping[str, str], *, masked: str, repeat: bool = False
) -> str:
    """Restore the placeholders in the model's answer. The answer may drop a
    placeholder (its line was removed) but never invent or duplicate one.
    Only this mask's placeholders count: text that merely looks like one, in
    the file itself, is left alone.

    With *repeat*, a known placeholder may appear more often than in *masked*:
    a module's first test reuses its values, each already in the repository,
    and shown to the reviewers under the same mask again. Invented ones are
    refused all the same."""
    if not mapping:
        return text
    prefix = next(iter(mapping))[:-4]
    for token in set(re.findall(re.escape(prefix) + r"\d{4}", text)):
        if token not in mapping:
            raise ProposalRefused(f"the answer invents the placeholder {token}")
        if not repeat and text.count(token) > masked.count(token):
            raise ProposalRefused(f"the answer duplicates the placeholder {token}")
    for token in reversed(list(mapping)):  # later ones may wrap earlier ones
        text = text.replace(token, mapping[token])
    return text


def mask_like(
    text: str, mapping: Mapping[str, str], *, prefer: Collection[str] = ()
) -> str:
    """*text* with every span *mapping* hides replaced by its placeholder: how
    a reviewer is shown a new file under the same mask as its module. Where two
    placeholders hide the same text, one in *prefer* is used."""
    # A later placeholder may wrap earlier ones: match what each finally stands for.
    full = {token: unmask(token, mapping, masked=token) for token in mapping}
    order = sorted(full.items(), key=lambda kv: (-len(kv[1]), kv[0] not in prefer))
    for token, original in order:
        if original:
            text = text.replace(original, token)
    return text


def mask_aligned(
    text: str, base: str, masked_base: str, mapping: Mapping[str, str]
) -> str:
    """*text*, a proposal for *base*, under *base*'s mask line by line: a line
    the proposal keeps is shown exactly as in the masked original, and a
    changed line takes the placeholders of the line it replaces first.

    Masking the proposal by value alone gave a value the original holds twice
    one placeholder where the original had two, so the reviewer saw changes
    that were never made. On 2026-11-02 a correct two-line fix
    (gd-a9f57600cf) was rejected for class names it never touched."""
    old = base.splitlines(keepends=True)
    new = text.splitlines(keepends=True)
    shown = masked_base.splitlines(keepends=True)
    if not mapping or len(shown) != len(old):
        return mask_like(text, mapping)
    prefix = re.escape(next(iter(mapping))[:-4]) + r"\d{4}"
    out: list[str] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.extend(shown[i1:i2])
        elif tag == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                near = set(re.findall(prefix, shown[i1 + k]))
                out.append(mask_like(new[j1 + k], mapping, prefer=near))
        else:
            near = set(re.findall(prefix, "".join(shown[i1:i2])))
            out.append(mask_like("".join(new[j1:j2]), mapping, prefer=near))
    return "".join(out)


def project_facts(project_root: Path) -> tuple[str, ...]:
    """True facts about the project that a change's correctness depends on,
    read from its own configuration. Both the proposer and the reviewers see
    them: on 2026-10-30 Codex rightly refused to accept removing `React` from a
    test because nothing it was shown established the JSX runtime."""
    facts = []
    try:
        raw = (Path(project_root) / "frontend" / "tsconfig.json").read_text(
            encoding="utf-8"
        )
        jsx = re.search(r'"jsx"\s*:\s*"([^"]+)"', raw)
    except OSError:
        jsx = None
    if jsx and jsx.group(1) in ("react-jsx", "react-jsxdev"):
        facts.append(
            "JSX uses the automatic runtime (frontend/tsconfig.json compilerOptions.jsx "
            f'= "{jsx.group(1)}"): JSX does not need React in scope.'
        )
    return tuple(facts)


@dataclass(frozen=True)
class Direction:
    """The operator's taste and priorities for GAGOS's work, relayed daily by
    his chief architect (operator, 2026-10-30: "about taste and direction I
    will communicate that with u everyday and u communicate with GAGOS").

    * ``notes`` reach the proposer and both reviewers, as his direction;
    * ``rules``, when given, replace the default rules;
    * ``focus`` path prefixes are worked first; ``avoid`` prefixes never.
    """

    notes: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    focus: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    updated: str | None = None

    def steer(self, work: Sequence[Finding]) -> list[Finding]:
        kept = [f for f in work if not any(f.rel.startswith(a) for a in self.avoid)]
        return sorted(
            kept, key=lambda f: 0 if any(f.rel.startswith(p) for p in self.focus) else 1
        )

    def as_dict(self) -> dict:
        return {
            "notes": list(self.notes),
            "rules": list(self.rules),
            "focus": list(self.focus),
            "avoid": list(self.avoid),
            "updated": self.updated,
        }


def load_direction(path: Path) -> Direction:
    """The direction in force; none on file is no direction, never a guess."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Direction()
    return Direction(
        notes=tuple(str(n) for n in raw.get("notes") or ()),
        rules=tuple(str(r) for r in raw.get("rules") or ()),
        focus=tuple(str(p) for p in raw.get("focus") or ()),
        avoid=tuple(str(p) for p in raw.get("avoid") or ()),
        updated=raw.get("updated"),
    )


def set_direction(path: Path, direction: Direction, *, said: str) -> Direction:
    """Write the direction and append the change to its history, so every
    day's work can be traced to the direction it was given."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = dataclasses.replace(direction, updated=_now())
    path.write_text(json.dumps(stamped.as_dict(), indent=2) + "\n", encoding="utf-8")
    with open(path.with_name("direction_history.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({**stamped.as_dict(), "said": said}) + "\n")
    return stamped


def proposal_prompt(
    finding: Finding,
    text: str,
    *,
    prior_refusals: Sequence[str] = (),
    masked: bool = False,
    facts: Sequence[str] = (),
    playbook: Sequence[Mapping[str, str]] = (),
) -> str:
    """The proposer's prompt. It names the file, never its path: paths do not
    leave the machine. *playbook*: D15's entries for the rule, for a finding in
    its ON arm."""
    lines = [
        f"File: {Path(finding.rel).name}",
        f"Rule: {finding.rule}",
        "Warnings to fix (line:column message):",
        *(f"  {line}:{col} {msg}" for line, col, msg in finding.warnings),
    ]
    if finding.rule in BEHAVIOUR_RULES:
        lines += [
            "",
            "This rule's fix can change what the code does. Keep its behaviour "
            "for its users exactly as it is; the tests that exercise this file "
            "run before any reviewer reads your change, and it is refused if "
            "one of them breaks.",
        ]
    if facts:
        lines += [
            "",
            "Facts about this project, and the operator's direction:",
            *(f"  - {fact}" for fact in facts),
        ]
    if masked:
        lines += [
            "",
            "Some spans are replaced by placeholders (GAGOSMASK followed by letters, digits and an underscore): they "
            "hide paths or values that may not leave this machine. Keep every "
            "placeholder you keep exactly as written; never invent one.",
        ]
    if prior_refusals:
        lines += [
            "",
            "Earlier proposals for this rule were refused for these reasons. "
            "Do not repeat them:",
            *(f"  - {reason}" for reason in prior_refusals),
        ]
    lines += playbook_lines(playbook)
    lines += ["", "The file:", "```", text, "```"]
    return "\n".join(lines)


class ProposalRefused(ValueError):
    """The model's answer is not a usable proposal."""


def parse_proposal(raw: str, *, original: str) -> str:
    """The whole corrected file from the model's answer, in the original's
    line endings and final-newline convention."""
    blocks = _FENCE.findall(raw or "")
    if len(blocks) != 1:
        raise ProposalRefused(
            f"expected exactly one fenced code block, got {len(blocks)}"
        )
    body = blocks[0].replace("\r\n", "\n")
    newline = "\r\n" if "\r\n" in original else "\n"
    body = body.rstrip("\n")
    if original.endswith(("\n", "\r\n")):
        body += "\n"
    if not body.strip():
        raise ProposalRefused("the proposed file is empty")
    return body.replace("\n", newline)


def unified_diff(rel: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.replace("\r\n", "\n").splitlines(keepends=True),
            after.replace("\r\n", "\n").splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )


def _changed_lines(diff: str) -> int:
    return sum(
        1
        for line in diff.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    )


@dataclass(frozen=True)
class StaticVerdict:
    passed: bool
    reason: str
    changed_lines: int = 0


def _directive_rules(tail: str) -> frozenset[str]:
    """The rules a directive names (none: all), before any ``--`` reason."""
    tail = tail.split("--")[0]
    return frozenset(r.strip() for r in tail.split(",") if r.strip())


def _silenced_regions(lines: int, comments: Sequence[Comment]) -> list[tuple[int, int]]:
    """Every line range a silencing comment covers, first line to last
    (0-based, inclusive), in order, for a text of *lines* lines."""
    last = lines - 1
    ordered = sorted(comments, key=lambda c: (c.start, c.end))
    out = []
    for k, c in enumerate(ordered):
        start, end = c.start - 1, c.end - 1
        if _WHOLE_FILE.search(c.value):
            out.append((0, last))
        elif _NEXT_LINE.search(c.value):
            out.append((start, min(end + 1, last)))
        elif _SAME_LINE.search(c.value):
            out.append((start, end))
        elif found := _REGION_START.search(c.value):
            rules = _directive_rules(found.group("rules"))
            close = last
            for later in ordered[k + 1 :]:
                ends = _REGION_END.match(later.value) if later.kind == "Block" else None
                if ends:
                    named = _directive_rules(ends.group("rules") or "")
                    if not named or (rules and rules <= named):
                        close = later.end - 1
                        break
            out.append((start, close))
    return sorted(out)


_PY_FILE_SILENCER = re.compile(r"^\s*(ruff|flake8)\s*:\s*noqa", re.I)
_PY_SILENCER = re.compile(
    r"noqa|type:\s*ignore|nosec|pragma\b|fmt:\s*(off|skip)|pylint:\s*disable"
    r"|pyright:\s*ignore",
    re.I,
)


def _python_silenced_regions(
    lines: int, comments: Sequence[Comment]
) -> list[tuple[int, int]]:
    """What Python's silencers cover: a ``# ruff: noqa`` the whole file, any
    other its own line (0-based, inclusive), in order."""
    out = set()
    for c in comments:
        if _PY_FILE_SILENCER.match(c.value):
            out.add((0, max(lines - 1, 0)))
        elif _PY_SILENCER.search(c.value):
            out.add((c.start - 1, c.end - 1))
    return sorted(out)


def silencing_refusal(
    before_text: str,
    after_text: str,
    before: StaticResult,
    after: StaticResult,
    *,
    python: bool = False,
) -> str | None:
    """Why a proposal may not pass for what disable comments silence, or None.

    The lines of the original and the proposal are aligned (difflib). Every
    silenced region must survive whole: the same lines, unchanged, paired
    line for line through unchanged text with the region in the same place
    in the order. So nothing can be edited, added, removed or moved into or
    out of anything silenced; a silencer cannot be retargeted, widened or
    narrowed; and anything the alignment cannot pair this way is refused.
    Then, from ESLint run again with inline configuration off: everything the
    proposal's comments hide must already have been hidden, with the same rule
    and message, on the aligned original line. Counting could not do this,
    nor matching by rule and message alone (Codex's reviews of #567)."""
    old, new = before_text.splitlines(), after_text.splitlines()
    to_old: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            to_old.update({j1 + k: i1 + k for k in range(i2 - i1)})
    linter, regions = (
        ("ruff", _python_silenced_regions) if python else ("ESLint", _silenced_regions)
    )
    if before.comments is None or after.comments is None:
        return (
            f"what the disable comments silence is unknown: {linter} did not run "
            "with inline configuration off"
        )
    was = regions(len(old), before.comments)
    now = regions(len(new), after.comments)
    if len(was) != len(now):
        return "the proposal adds or removes a disable comment, or changes what one silences"
    for (s0, e0), (s1, e1) in zip(was, now):
        if old[s0 : e0 + 1] != new[s1 : e1 + 1] or any(
            to_old.get(s1 + k) != s0 + k for k in range(e1 - s1 + 1)
        ):
            return (
                "the proposal changes code a disable comment silences, or what "
                f"one silences (line {s1 + 1})"
            )
    hidden_before, hidden_after = before.hidden(), after.hidden()
    if hidden_before is None or hidden_after is None:
        return (
            f"what the disable comments hide is unknown: {linter} did not run "
            "with inline configuration off"
        )
    already = Counter((m.rule, m.message, m.line) for m in hidden_before)
    for m in hidden_after:
        line = to_old.get(m.line - 1)
        key = (m.rule, m.message, None if line is None else line + 1)
        if line is None or already[key] <= 0:
            return (
                f"the proposal hides a {m.rule or 'parse'} message under a "
                f"disable comment (line {m.line}: {m.message})"
            )
        already[key] -= 1
    return None


def static_verdict(
    finding: Finding,
    before_text: str,
    after_text: str,
    before: StaticResult,
    after: StaticResult,
) -> StaticVerdict:
    """The unattended checks. Nothing the model wrote is executed."""
    if after_text == before_text:
        return StaticVerdict(False, "the proposal changes nothing")
    diff = unified_diff(finding.rel, before_text, after_text)
    changed = _changed_lines(diff)
    if after.parse_errors:
        return StaticVerdict(
            False, f"the proposal does not parse: {after.parse_errors[0]}", changed
        )
    if after.errors:
        first = after.errors[0]
        return StaticVerdict(
            False,
            f"the proposal has an {linter_of(finding.rel)} error: "
            f"{first.rule}: {first.message}",
            changed,
        )
    left = after.warnings(finding.rule)
    if left:
        return StaticVerdict(
            False,
            f"{len(left)} of the {finding.rule} warnings remain "
            f"(line {left[0].line}: {left[0].message})",
            changed,
        )
    was = Counter(m.rule for m in before.warnings() if m.rule != finding.rule)
    now = Counter(m.rule for m in after.warnings())
    new = {rule: now[rule] - was[rule] for rule in now if now[rule] > was[rule]}
    if new:
        return StaticVerdict(
            False,
            "the proposal adds warnings: "
            + ", ".join(f"{rule} +{n}" for rule, n in sorted(new.items(), key=str)),
            changed,
        )
    # Nothing silenced may change, and nothing may be newly hidden: counting
    # silencers let a changed one through (Codex's post-merge review of #566);
    # an unchanged one could be retargeted, and a bounded region could take
    # in a warning moved into it (Codex's reviews of #567).
    refusal = silencing_refusal(
        before_text, after_text, before, after, python=is_python(finding.rel)
    )
    if refusal:
        return StaticVerdict(False, refusal, changed)
    limit = MAX_CHANGED_LINES_BASE + MAX_CHANGED_LINES_PER_WARNING * len(
        finding.warnings
    )
    if changed > limit:
        return StaticVerdict(
            False,
            f"the proposal changes {changed} lines; the bound for "
            f"{len(finding.warnings)} warning(s) is {limit}",
            changed,
        )
    reach = reach_of(finding.rule)
    far = (
        beyond_reach(diff, [line for line, _col, _msg in finding.warnings], reach)
        if reach is not None
        else []
    )
    if far:
        line, distance = far[0]
        return StaticVerdict(
            False,
            f"the proposal changes line {line}, {distance} lines from the nearest "
            f"warning; a fix stays within {reach} lines of what it fixes",
            changed,
        )
    return StaticVerdict(True, "parses; the warnings are gone; nothing new", changed)


def beyond_reach(
    diff: str, warning_lines: Sequence[int], reach: int = MAX_REACH
) -> list[tuple[int, int]]:
    """Every line of the original a unified *diff* removes, or inserts at,
    that is more than *reach* lines from the nearest warning line, with its
    distance, once each, in order. Lines inserted in place of removed ones
    are placed at the first line they replace."""
    if not warning_lines:
        return []
    out: dict[int, int] = {}
    old = None
    replaced = None
    for row in diff.splitlines():
        hunk = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+", row)
        if hunk:
            old, replaced = int(hunk.group(1)), None
            continue
        if old is None or row.startswith(("---", "+++")):
            continue
        if row.startswith("-"):
            replaced = old if replaced is None else replaced
            at, old = old, old + 1
        elif row.startswith("+"):
            at = old if replaced is None else replaced
        else:
            old, replaced = old + 1, None
            continue
        distance = min(abs(at - w) for w in warning_lines)
        if distance > reach:
            out.setdefault(at, distance)
    return sorted(out.items())


# --------------------------------------------------------------------- tasks

#: The writer's instruction for a task the operator wrote (2026-11-03): his
#: change in one file, and nothing around it. The answer has the proposer's
#: form, so :func:`parse_proposal` and :func:`unmask` read it unchanged.
#: How a task's writer answers (2026-11-11): exact edits, not whole files, so a
#: file of any size can be worked on and nothing the edits do not name can
#: change. :func:`parse_edits` applies them; an answer with no edit block is
#: still read as a whole file in one fenced block, as before. One line, like
#: every writer's instruction: on Windows ``claude`` is a .cmd launcher and
#: cmd.exe cuts its ``--system-prompt`` argument at the first line break.
EDIT_FORMAT = (
    "Reply with edits, not the whole file. Each edit is: a line <<<<<<< SEARCH, "
    "then lines copied EXACTLY from the file (enough to match ONE place), then a "
    "line =======, then the lines that replace them, then a line >>>>>>> REPLACE. "
    "Edits apply in order, each to the file as the ones before left it. Copy the "
    "SEARCH lines character for character, with their indentation; keep each "
    "edit small. Write nothing outside the edits."
)

TASK_SYSTEM = (
    "You are GAGOS's frontend maintainer. The operator has asked for one change "
    "to one file of a React + TypeScript codebase. Make exactly that change and "
    "nothing else: keep everything else in the file as it is, and do not "
    "reformat, reorder or rename anything the task does not need changed. Your "
    "change must add no ESLint warning or error. Never add eslint-disable, "
    "@ts-ignore, @ts-nocheck or @ts-expect-error. If the task cannot be done "
    "in this file alone, reply with no edit at all. " + EDIT_FORMAT
)

PYTHON_TASK_SYSTEM = (
    "You are GAGOS's backend maintainer. The operator has asked for one change "
    "to one Python file of GAGOS's own code. Make exactly that change and "
    "nothing else: keep everything else in the file as it is, and do not "
    "reformat, reorder or rename anything the task does not need changed. Keep "
    "every public name other modules import from this file. Your change must "
    "add no ruff warning or error. Never add noqa, type: ignore, nosec or "
    "pragma comments. If the task cannot be done in this file alone, reply "
    "with no edit at all. " + EDIT_FORMAT
)


def task_system(rel: str) -> str:
    return PYTHON_TASK_SYSTEM if is_python(rel) else TASK_SYSTEM


def task_prompt(
    rel: str,
    task_text: str,
    text: str,
    *,
    masked: bool = False,
    facts: Sequence[str] = (),
    briefing: str = "",
) -> str:
    """The task writer's prompt. *task_text* must already be scrubbed; the file
    is named, never its path. *briefing*, already scrubbed, is the local
    clerk's (goal_intake.writer_briefing), when it has briefed the goal."""
    lines = [f"File: {Path(rel).name}", "The operator's task:", task_text]
    if briefing:
        lines += [
            "",
            "The local clerk's briefing (advisory; the operator's task above decides):",
            briefing,
        ]
    if facts:
        lines += [
            "",
            "Facts about this project, and the operator's direction:",
            *(f"  - {fact}" for fact in facts),
        ]
    if masked:
        lines += [
            "",
            "Some spans are replaced by placeholders (GAGOSMASK followed by letters, digits and an underscore): they "
            "hide paths or values that may not leave this machine. Keep every "
            "placeholder you keep exactly as written; never invent one.",
        ]
    lines += ["", "The file:", "```", text, "```"]
    return "\n".join(lines)


def task_verdict(
    rel: str,
    before_text: str,
    after_text: str,
    before: StaticResult,
    after: StaticResult,
) -> StaticVerdict:
    """The unattended checks of a task's change. Whether it does what the
    operator asked is the reviewer's to say; these only keep the file sound:
    it parses, no rule's count of warnings and errors rises over the base, no
    disable comment is added or moved (and no change touches code one
    silences), and it changes something. No reach check and no bound on the
    lines: a task is not a lint fix. Nothing the model wrote is executed."""
    if after_text == before_text:
        # The writer is told to return the file unchanged when the task needs
        # more than this one file.
        return StaticVerdict(
            False,
            "the writer returned the file unchanged: the task may need more than "
            "this one file",
        )
    changed = _changed_lines(unified_diff(rel, before_text, after_text))
    if after.parse_errors:
        return StaticVerdict(
            False, f"the proposal does not parse: {after.parse_errors[0]}", changed
        )
    was = Counter(m.rule for m in before.messages)
    now = Counter(m.rule for m in after.messages)
    new = {rule: now[rule] - was[rule] for rule in now if now[rule] > was[rule]}
    if new:
        return StaticVerdict(
            False,
            f"the proposal adds {linter_of(rel)} messages: "
            + ", ".join(f"{rule} +{n}" for rule, n in sorted(new.items(), key=str)),
            changed,
        )
    refusal = silencing_refusal(
        before_text, after_text, before, after, python=is_python(rel)
    )
    if refusal:
        return StaticVerdict(False, refusal, changed)
    return StaticVerdict(True, "parses; nothing new", changed)


def task_review_prompt(
    rel: str,
    task_text: str,
    before_text: str,
    diff: str,
    *,
    facts: Sequence[str] = (),
) -> str:
    """What each reviewer reads for a task: the operator's words (already
    scrubbed), the file and the change. The same verdict schema as a lint fix."""
    python = is_python(rel)
    part = "backend (Python; GAGOS's own code)" if python else "frontend"
    linter = "ruff" if python else "ESLint"
    known = (
        [
            "",
            "Facts about this project (from its configuration) and the operator's direction:",
        ]
        + [f"  - {fact}" for fact in facts]
        if facts
        else []
    )
    return "\n".join(
        [
            "You are reviewing a change GAGOS (an AI system) made to its own "
            f"{part} because its operator asked for it in plain words. You are "
            "its reviewer: if you accept, it goes to the operator to merge; if "
            "you reject, it does not ship. Be strict and honest.",
            "",
            "ACCEPT only if ALL hold:",
            "- the change does what the operator's task asks;",
            "- it does only that: nothing else in the file is changed, "
            "reformatted or removed;",
            "- it breaks nothing: behaviour and public names the task did not "
            "ask to change are as before, and nothing is silenced (no disable, "
            "ts-ignore, noqa or type: ignore comments);",
            "- the code is correct and would pass review in this codebase.",
            "Otherwise REJECT, and say exactly why in one or two sentences.",
            f"Automated checks already passed: it parses and adds no {linter} message.",
            "",
            f"File: {Path(rel).name}",
            "The operator's task:",
            task_text,
            *known,
            "",
            "The whole original file:",
            "```",
            before_text,
            "```",
            "",
            "The proposed change:",
            "```diff",
            diff,
            "```",
        ]
    )


# ------------------------------------------------------- a task over several files

#: The most characters of file text a task over several files may send: the
#: writer returns every file it changes whole, in ONE answer, and an answer holds
#: at most 12,000 tokens (about 36,000 characters at three a token). Thirty
#: thousand leaves room for the labels and for a change that grows the files; a
#: task over more is refused with the number, never cut short. Since 2026-11-11 a
#: task's writer answers with edits, so the bound is what one prompt may carry:
#: the files read, not the files written.
MAX_TASK_TOTAL_CHARS = 240_000
#: The longest file a task may change (2026-11-11): edits, not whole files,
#: come back, so a task reaches files over the whole-file bound.
MAX_TASK_FILE_CHARS = 160_000

#: How a writer labels each file it returns, and how it is told to: the file's
#: index in the task, and its name, never its path.
_FILE_LABEL = re.compile(r"^[ \t#*=_-]*File[ \t]+(\d+)\b[^\n]*$", re.MULTILINE)


def file_label(index: int, rel: str) -> str:
    """The label of file *index* (from 1) of a task: shown to the writer and the
    reviewer, never a path."""
    return f"File {index}: {Path(rel).name}"


def task_files_system(rels: Sequence[str]) -> str:
    """The writer's instruction for a task over several files."""
    kinds = {is_python(rel) for rel in rels}
    what = (
        "Python files of GAGOS's own code"
        if kinds == {True}
        else "files of a React + TypeScript codebase"
        if kinds == {False}
        else "files of GAGOS's own code, Python and React + TypeScript"
    )
    rules = []
    if False in kinds:
        rules.append(
            "a frontend file must add no ESLint warning or error and never gain "
            "eslint-disable, @ts-ignore, @ts-nocheck or @ts-expect-error"
        )
    if True in kinds:
        rules.append(
            "a Python file must add no ruff warning or error, keep every public "
            "name other modules import from it, and never gain noqa, type: "
            "ignore, nosec or pragma comments"
        )
    return (
        f"You are GAGOS's maintainer. The operator has asked for one change that "
        f"spans several {what}. Make exactly that change and nothing else: keep "
        "everything else in every file as it is, and do not reformat, reorder or "
        "rename anything the task does not need changed. "
        + "; ".join(rules)[:1].upper()
        + "; ".join(rules)[1:]
        + ". For each file you change, write a line `File N: name` exactly as "
        "the file is labelled, then that file's edits. Leave out every file you "
        "do not change. If the task cannot be done in these files, reply with no "
        "edit at all. " + EDIT_FORMAT
    )


def task_files_prompt(
    task_text: str,
    files: Sequence[tuple[str, str]],
    *,
    masked: bool = False,
    facts: Sequence[str] = (),
    briefing: str = "",
) -> str:
    """The writer's prompt for a task over several files: *task_text* already
    scrubbed, and *files* as ``(rel, text)`` (the text already masked), each
    under its :func:`file_label`; *briefing* as in :func:`task_prompt`."""
    lines = ["The operator's task:", task_text]
    if briefing:
        lines += [
            "",
            "The local clerk's briefing (advisory; the operator's task above decides):",
            briefing,
        ]
    if facts:
        lines += [
            "",
            "Facts about this project, and the operator's direction:",
            *(f"  - {fact}" for fact in facts),
        ]
    if masked:
        lines += [
            "",
            "Some spans are replaced by placeholders (GAGOSMASK followed by letters, digits and an underscore): they "
            "hide paths or values that may not leave this machine. Each file has "
            "placeholders of its own; keep every placeholder you keep exactly as "
            "written, in the file it is in; never invent one.",
        ]
    for n, (rel, text) in enumerate(files, 1):
        lines += ["", f"{file_label(n, rel)}", "```", text, "```"]
    return "\n".join(lines)


def parse_task_files(raw: str, originals: Sequence[str]) -> dict[int, str]:
    """The files a writer changed, from its answer to a task over several:
    ``{index from 0: whole file}``, each in its original's line endings and
    final-newline convention. A file left out is unchanged; an answer with no
    fenced block changes nothing. Refused: a block with no ``File N`` label
    before it, a label with no block after it, a label of a file the task does
    not have, a file given twice."""
    out: dict[int, str] = {}
    pending: int | None = None
    at = 0

    def labels(chunk: str) -> None:
        nonlocal pending
        for label in _FILE_LABEL.finditer(chunk):
            if pending is not None:
                raise ProposalRefused(
                    f"File {pending} is labelled but has no fenced code block"
                )
            pending = int(label.group(1))
            if not 1 <= pending <= len(originals):
                raise ProposalRefused(
                    f"the answer labels File {pending}; the task has "
                    f"{len(originals)} file(s)"
                )

    for block in _FENCE.finditer(raw or ""):
        labels(raw[at : block.start()])
        if pending is None:
            raise ProposalRefused("a fenced code block has no `File N` label before it")
        index = pending - 1
        if index in out:
            raise ProposalRefused(f"File {pending} is given twice")
        out[index] = parse_proposal(
            f"```\n{block.group(1)}```", original=originals[index]
        )
        pending, at = None, block.end()
    labels((raw or "")[at:])
    if pending is not None:
        raise ProposalRefused(
            f"File {pending} is labelled but has no fenced code block"
        )
    return out


_EDIT = re.compile(
    r"^<<<<<<< SEARCH[ \t]*\n(.*?)^=======[ \t]*\n(.*?)^>>>>>>> REPLACE[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
_EDIT_MARK = re.compile(
    r"^(?:<<<<<<< SEARCH|=======|>>>>>>> REPLACE)[ \t]*$", re.MULTILINE
)


def is_edit_answer(raw: str) -> bool:
    """Whether a writer answered with edits (2026-11-11) rather than whole files."""
    return re.search(r"^<<<<<<< SEARCH[ \t]*$", raw or "", re.MULTILINE) is not None


def _edits(chunk: str) -> list[tuple[str, str]]:
    """The ``(search, replace)`` pairs of *chunk*, LF-normalised; refused when
    a marker stands outside a complete edit."""
    chunk = chunk.replace("\r\n", "\n")
    pairs, at = [], 0
    for m in _EDIT.finditer(chunk):
        if _EDIT_MARK.search(chunk, at, m.start()):
            raise ProposalRefused(
                "an edit is not complete: SEARCH, ======= and REPLACE"
            )
        pairs.append((m.group(1), m.group(2)))
        at = m.end()
    if _EDIT_MARK.search(chunk, at):
        raise ProposalRefused("an edit is not complete: SEARCH, ======= and REPLACE")
    return pairs


def apply_edits(original: str, pairs: Sequence[tuple[str, str]]) -> str:
    """*original* with each ``(search, replace)`` applied in order, each to the
    text the ones before left. A SEARCH must occur exactly once; an empty one
    only in an empty file (a new file's whole text). The original's line
    endings and final-newline convention are kept."""
    crlf = "\r\n" in original
    text = original.replace("\r\n", "\n")
    for n, (search, replace) in enumerate(pairs, 1):
        if not search:
            if text:
                raise ProposalRefused(
                    f"edit {n} has an empty SEARCH in a file that has text"
                )
            text = replace
            continue
        found = text.count(search)
        if found != 1:
            first = search.strip().splitlines()[0][:80] if search.strip() else ""
            raise ProposalRefused(
                f"edit {n}'s SEARCH "
                + ("is not in the file" if not found else f"matches {found} places")
                + (f" (it begins {first!r})" if first else "")
            )
        text = text.replace(search, replace, 1)
    return text.replace("\n", "\r\n") if crlf else text


def parse_edits(raw: str, original: str) -> str:
    """A one-file task's answer given as edits: *original* (the text the
    writer saw) with them applied. Refused: no edit, or an edit that does not
    match exactly one place."""
    pairs = _edits(raw or "")
    if not pairs:
        raise ProposalRefused("the answer has no edit")
    return apply_edits(original, pairs)


def parse_task_edits(raw: str, originals: Sequence[str]) -> dict[int, str]:
    """A task over several files answered with edits: ``{index from 0: new
    text}`` for each file labelled ``File N`` with edits after it, each applied
    to that file's text as shown. Refused: an edit before any label, a label
    with no edit, a label of a file the task does not have, a file twice."""
    text = (raw or "").replace("\r\n", "\n")
    labels = list(_FILE_LABEL.finditer(text))
    first_label = labels[0].start() if labels else len(text)
    if _edits(text[:first_label]):
        raise ProposalRefused("an edit has no `File N` label before it")
    out: dict[int, str] = {}
    for k, label in enumerate(labels):
        n = int(label.group(1))
        if not 1 <= n <= len(originals):
            raise ProposalRefused(
                f"the answer labels File {n}; the task has {len(originals)} file(s)"
            )
        if n - 1 in out:
            raise ProposalRefused(f"File {n} is given twice")
        end = labels[k + 1].start() if k + 1 < len(labels) else len(text)
        pairs = _edits(text[label.end() : end])
        if not pairs:
            raise ProposalRefused(f"File {n} is labelled but has no edit")
        out[n - 1] = apply_edits(originals[n - 1], pairs)
    return out


def task_files_review_prompt(
    task_text: str,
    parts: Sequence[tuple[str, str, str]],
    *,
    facts: Sequence[str] = (),
) -> str:
    """What a reviewer reads for a task over several files: the operator's words
    (already scrubbed), then each changed file as ``(rel, masked original,
    diff)`` under its label. One verdict is asked for the whole change."""
    kinds = {is_python(rel) for rel, _base, _diff in parts}
    part = (
        "backend (Python; GAGOS's own code)"
        if kinds == {True}
        else "frontend"
        if kinds == {False}
        else "backend and frontend"
    )
    linters = " and ".join(
        name for name, on in (("ruff", True in kinds), ("ESLint", False in kinds)) if on
    )
    known = (
        [
            "",
            "Facts about this project (from its configuration) and the operator's direction:",
        ]
        + [f"  - {fact}" for fact in facts]
        if facts
        else []
    )
    lines = [
        "You are reviewing a change GAGOS (an AI system) made to its own "
        f"{part} because its operator asked for it in plain words. The change "
        f"spans {len(parts)} files and is accepted or rejected as a whole. You "
        "are its reviewer: if you accept, it goes to the operator to merge; if "
        "you reject, it does not ship. Be strict and honest.",
        "",
        "ACCEPT only if ALL hold:",
        "- the change, across the files together, does what the operator's task "
        "asks, and the files agree with one another;",
        "- it does only that: nothing else in any file is changed, reformatted "
        "or removed;",
        "- it breaks nothing: behaviour and public names the task did not ask "
        "to change are as before, and nothing is silenced (no disable, "
        "ts-ignore, noqa or type: ignore comments);",
        "- the code is correct and would pass review in this codebase.",
        "Otherwise REJECT, and say exactly why in one or two sentences.",
        f"Automated checks already passed: every file parses and adds no {linters} message.",
        "",
        "The operator's task:",
        task_text,
        *known,
    ]
    for n, (rel, base, diff) in enumerate(parts, 1):
        lines += [
            "",
            file_label(n, rel),
            "The whole original file:",
            "```",
            base,
            "```",
            "",
            "The proposed change:",
            "```diff",
            diff,
            "```",
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------- tests

#: GAGOS's second kind of work (2026-11-02): a first test for a module of its
#: frontend that has none. The finding's file is the new test; its subject is
#: the module beside it with the same name. Nothing in the module changes.
MISSING_TEST = "gagos/missing-test"
_TESTABLE = (".jsx", ".tsx", ".js", ".ts")
_IS_TEST = re.compile(r"\.(test|spec)\.[jt]sx?$")
_EXPORTS = re.compile(r"^\s*export\s", re.M)
#: A new test longer than this is not a first test; it is a project.
MAX_TEST_LINES = 200
#: What a test GAGOS writes may not reach. It runs only at delivery, after
#: review, but then it runs on the operator's machine.
_TEST_FORBIDDEN = re.compile(
    r"\brequire\s*\(|\bimport\s*\(|\bprocess\s*\.|\beval\s*\(|\bFunction\s*\("
    r"|\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b|\bchild_process\b"
    r"|from\s+['\"](?:node:[^'\"]*|fs|fs/promises|net|http|https|os|vm|dgram"
    r"|tls|cluster|worker_threads|child_process)['\"]"
)
_SILENCER = re.compile(r"eslint-disable|@ts-ignore|@ts-nocheck|@ts-expect-error", re.I)

TESTER_SYSTEM = (
    "You are GAGOS's frontend test writer. You write ONE new Vitest test file "
    "for the module you are given, of a React + TypeScript codebase. Import the "
    "module from './<its name>' and test only what its exports do, with "
    "@testing-library/react for components. Assert real behaviour, never "
    "something that would pass whatever the module did. Mock anything the "
    "module would fetch or reach outside the test; never mock the module "
    "itself. No network, no filesystem, no process, no Node built-ins, no "
    "eval, no dynamic import, no real timers or randomness you do not control. "
    "Never add eslint-disable or ts-ignore comments. Every import and variable "
    "must be used. Keep it to a few focused tests, under "
    f"{MAX_TEST_LINES} lines. A placeholder (GAGOSMASK...) stands for a hidden "
    "span of the module: use it only where that span could appear, never as a "
    "name of your own. Reply with the complete test file in ONE fenced code "
    "block and nothing else."
)


def first_test_path(rel: str) -> str | None:
    """Where a first test for the module *rel* goes, or None when *rel* is not
    a module GAGOS writes tests for."""
    path = PurePosixPath(rel)
    if (
        path.suffix not in _TESTABLE
        or _IS_TEST.search(path.name)
        or path.name.endswith(".d.ts")
        or path.stem in ("index", "main", "setupTests")
        or ".stories" in path.name
    ):
        return None
    return str(path.with_name(f"{path.stem}.test{path.suffix}"))


def subject_of(test_rel: str) -> str:
    """The module a first test written by GAGOS is for."""
    path = PurePosixPath(test_rel)
    return str(path.with_name(path.name.replace(".test.", ".", 1)))


def missing_tests(
    texts: Mapping[str, str], exists: Callable[[str], bool]
) -> list[Finding]:
    """A finding for every module with exports and no test file of its name
    beside it (``X.test.*`` or ``X.spec.*``, in any of the four extensions)."""
    out = []
    for rel in sorted(texts):
        test = first_test_path(rel)
        if test is None or not _EXPORTS.search(texts[rel]):
            continue
        path = PurePosixPath(rel)
        siblings = [
            str(path.with_name(f"{path.stem}.{kind}{ext}"))
            for kind in ("test", "spec")
            for ext in _TESTABLE
        ]
        if any(s in texts or exists(s) for s in siblings):
            continue
        out.append(Finding(rel=test, rule=MISSING_TEST, warnings=()))
    return out


def first_test_prompt(
    finding: Finding,
    subject: str,
    *,
    example: str | None = None,
    prior_refusals: Sequence[str] = (),
    masked: bool = False,
    facts: Sequence[str] = (),
    playbook: Sequence[Mapping[str, str]] = (),
) -> str:
    """The test writer's prompt: the module, its test's name and, when one is
    near, another test of this codebase for its conventions. Names, never
    paths."""
    module = PurePosixPath(subject_of(finding.rel)).name
    lines = [
        f"Module: {module}",
        f"Write its first test file: {PurePosixPath(finding.rel).name}",
    ]
    if facts:
        lines += [
            "",
            "Facts about this project, and the operator's direction:",
            *(f"  - {fact}" for fact in facts),
        ]
    if masked:
        lines += [
            "",
            "Some spans are replaced by placeholders (GAGOSMASK followed by "
            "letters, digits and an underscore): they hide paths or values that "
            "may not leave this machine. Never invent one.",
        ]
    if prior_refusals:
        lines += [
            "",
            "Earlier tests were refused for these reasons. Do not repeat them:",
            *(f"  - {reason}" for reason in prior_refusals),
        ]
    lines += playbook_lines(playbook)
    if example:
        lines += [
            "",
            "Another test in this codebase, for its conventions:",
            "```",
            example,
            "```",
        ]
    lines += ["", f"The module {module}:", "```", subject, "```"]
    return "\n".join(lines)


def first_test_verdict(
    finding: Finding, new_text: str, after: StaticResult
) -> StaticVerdict:
    """The unattended checks on a new test. Nothing the model wrote is
    executed here: before review it runs only in the sandbox
    (:mod:`aios.maintenance.sandbox_tests`), and again at delivery."""
    lines = len(new_text.splitlines())
    if not new_text.strip():
        return StaticVerdict(False, "the test is empty", 0)
    if after.parse_errors:
        return StaticVerdict(
            False, f"the test does not parse: {after.parse_errors[0]}", lines
        )
    if after.errors:
        first = after.errors[0]
        return StaticVerdict(
            False, f"the test has an ESLint error: {first.rule}: {first.message}", lines
        )
    if after.warnings():
        first = after.warnings()[0]
        return StaticVerdict(
            False,
            f"a new test must have no ESLint warning: {first.rule}: {first.message}",
            lines,
        )
    if _SILENCER.search(new_text):
        return StaticVerdict(False, "the test silences a check", lines)
    reach = _TEST_FORBIDDEN.search(new_text)
    if reach:
        return StaticVerdict(
            False, f"the test reaches outside itself: {reach.group(0)!r}", lines
        )
    stem = re.escape(PurePosixPath(subject_of(finding.rel)).stem)
    if not re.search(rf"""from\s+['"]\./{stem}(?:\.[jt]sx?)?['"]""", new_text):
        return StaticVerdict(False, "the test does not import its module", lines)
    if not (re.search(r"\b(?:it|test)\s*\(", new_text) and "expect(" in new_text):
        return StaticVerdict(False, "the test has no test with an expectation", lines)
    if lines > MAX_TEST_LINES:
        return StaticVerdict(
            False, f"the test is {lines} lines; the bound is {MAX_TEST_LINES}", lines
        )
    return StaticVerdict(
        True, "parses; no ESLint message; imports its module; reaches nothing", lines
    )


# --------------------------------------------------------------------- reviewing

#: The schema a reviewer answers in: one for the workshop and the council
#: (aios/domain/reviews.py, 2026-11-10).
REVIEW_SCHEMA = _REVIEW_SCHEMA


def review_prompt(
    finding: Finding, before_text: str, diff: str, *, facts: Sequence[str] = ()
) -> str:
    """What each reviewer reads. The same text for both, so they judge the
    same evidence independently."""
    warnings = "\n".join(f"  {line}:{col} {msg}" for line, col, msg in finding.warnings)
    known = (
        [
            "",
            "Facts about this project (from its configuration) and the operator's direction:",
        ]
        + [f"  - {fact}" for fact in facts]
        if facts
        else []
    )
    if is_python(finding.rel):
        part, linter = "backend (Python; GAGOS's own code)", "ruff"
        holds = [
            "- behaviour, return values, exceptions raised, public names and "
            "tests are unchanged;",
            "- nothing is silenced (no noqa, type: ignore, nosec or pragma comments);",
            "- removed code was truly unused, and nothing it did is lost (e.g. "
            "an import's side effect, a call on the right of a removed "
            "assignment, a name other code reads through this module).",
        ]
        checked = (
            "Automated checks already passed: it parses, the listed warnings are "
            "gone, no other ruff warning or error was added, and no other "
            "tracked module imports a removed name from this one."
        )
    else:
        part, linter = "frontend", "ESLint"
        holds = [
            "- behaviour, rendering, exports, public names and tests are unchanged;",
            "- nothing is silenced (no disable or ts-ignore comments) and no "
            "type is weakened to hide a problem;",
            "- removed code was truly unused, and nothing it did is lost "
            "(e.g. a side effect, a hook call, an argument position).",
        ]
        checked = (
            "Automated checks already passed: it parses, the listed warnings "
            "are gone, and no other ESLint warning or error was added."
        )
    return "\n".join(
        [
            "You are reviewing a change GAGOS (an AI system) proposed to its own "
            f"{part}. You are its reviewer: if you accept, it goes to the "
            "operator to merge; if you reject, it does not ship. Be strict and "
            "honest.",
            "",
            "ACCEPT only if ALL hold:",
            f"- it fixes the listed {linter} warnings and nothing else;",
            *holds,
            "Otherwise REJECT, and say exactly why in one or two sentences.",
            checked,
            "",
            f"File: {Path(finding.rel).name}",
            f"Rule: {finding.rule}",
            "Warnings it should fix (line:column message):",
            warnings,
            *known,
            "",
            "The whole original file:",
            "```",
            before_text,
            "```",
            "",
            "The proposed change:",
            "```diff",
            diff,
            "```",
        ]
    )


def first_test_review_prompt(
    finding: Finding, subject: str, test: str, *, facts: Sequence[str] = ()
) -> str:
    """What each reviewer reads for a new test: the module and the test, the
    same text for both."""
    known = (
        [
            "",
            "Facts about this project (from its configuration) and the operator's direction:",
        ]
        + [f"  - {fact}" for fact in facts]
        if facts
        else []
    )
    module = PurePosixPath(subject_of(finding.rel)).name
    return "\n".join(
        [
            "You are reviewing a NEW test file GAGOS (an AI system) wrote for a "
            "module of its own frontend that had no test. You are its reviewer: "
            "if you accept, it goes to the operator to merge; if you reject, it "
            "does not ship. Be strict and honest.",
            "",
            "ACCEPT only if ALL hold:",
            "- it imports the module below and tests what its exports do; every "
            "assertion checks real behaviour, and none would pass whatever the "
            "module did;",
            "- judged assertion by assertion against the module exactly as shown, "
            "it would pass;",
            "- it is deterministic: no real timers, randomness, dates or ordering "
            "it does not control;",
            "- it reaches no network, filesystem, process or global state it does "
            "not set up and restore; whatever the module would fetch is mocked, "
            "and the module itself is not mocked;",
            "- it adds a test and changes nothing else.",
            "Otherwise REJECT, and say exactly why in one or two sentences.",
            "Automated checks already passed: it parses, has no ESLint error or "
            "warning, imports its module, has an expectation, uses no Node "
            "built-in, network, eval, dynamic import or process, and silences "
            "nothing. It has NOT been run: it runs only after you accept, and "
            "must pass then.",
            *known,
            "",
            f"The module {module}:",
            "```",
            subject,
            "```",
            "",
            f"The new test {PurePosixPath(finding.rel).name}:",
            "```",
            test,
            "```",
        ]
    )


#: A reviewer's structured output, read the one way (aios/domain/reviews.py).
parse_review = _parse_review


# --------------------------------------------------------------------- the ledger

#: Who may review. A reject from any of them rejects the proposal.
REVIEWERS: tuple[str, ...] = ("codex", "claude")
#: Whose acceptance a change needs. Both, until the operator's word of
#: 2026-11-02 ("forget codex now we both r available so that's enough"):
#: Claude Code reviews and the operator merges; Codex is no longer asked.
REQUIRED_REVIEWERS: tuple[str, ...] = ("claude",)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rel TEXT NOT NULL,
    rule TEXT NOT NULL,
    warnings TEXT NOT NULL,
    base_digest TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    base_text TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    refusal TEXT,
    new_text TEXT,
    new_digest TEXT,
    diff TEXT,
    changed_lines INTEGER,
    facts TEXT,
    sandbox TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    proposal_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    model TEXT,
    verdict TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (proposal_id, reviewer)
);
CREATE TABLE IF NOT EXISTS deliveries (
    proposal_id TEXT PRIMARY KEY,
    branch TEXT NOT NULL,
    commit_sha TEXT,
    pr_url TEXT,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clerk_jobs (
    proposal_id TEXT PRIMARY KEY,
    model TEXT,
    status TEXT NOT NULL,
    summary TEXT,
    crux TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS days (
    day TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    reason TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS day_claims (
    day TEXT PRIMARY KEY,
    claimed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    usd REAL NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    chars_in INTEGER,
    chars_out INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    rel TEXT NOT NULL,
    text TEXT NOT NULL,
    said_by TEXT NOT NULL,
    status TEXT NOT NULL,
    proposal_id TEXT,
    reason TEXT,
    updated_at TEXT NOT NULL,
    also TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS goal_intake (
    task_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    clerk TEXT NOT NULL,
    reason TEXT,
    mission_request TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goal_missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT,
    mission_id TEXT,
    envelope_id TEXT,
    slot INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playbook (
    entry_id TEXT PRIMARY KEY,
    rule TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]',
    helpful INTEGER NOT NULL DEFAULT 0,
    harmful INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    retired_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reflections (
    rule TEXT PRIMARY KEY,
    decided_seen INTEGER NOT NULL,
    reflected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    rel TEXT PRIMARY KEY,
    holder TEXT NOT NULL,
    claimed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measures (
    slot TEXT PRIMARY KEY,
    head TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    data TEXT NOT NULL
);
"""

#: A task the operator wrote (2026-11-03, asked for "bigger work" in GAGOS's
#: workshop, counter and face): his words and one file GAGOS may edit. Its
#: proposal is recorded under this rule and judged like any other: the checks,
#: the sandbox's tests, the chief reviewer, CI, and his merge.
TASK_RULE = "gagos/task"
#: The longest task text accepted.
MAX_TASK_CHARS = 4_000
#: The most files one task may change (2026-11-03, the operator: "plz honestly
#: do all than we will be ready for D14"): its own file and up to four more,
#: changed together, tested together, reviewed and delivered as one.
MAX_TASK_FILES = 5
#: Task statuses. ``open`` = waiting for a writer; ``taken`` = a writer's
#: proposal is recorded (``proposal_id``), whose own status is the progress;
#: ``refused`` = GAGOS cannot do it (``reason``: a file it may not edit, too
#: long, or one that cannot leave the machine); ``cancelled`` = withdrawn by
#: the operator before a writer took it.
TASK_STATUSES = ("open", "taken", "refused", "cancelled")


def _task_dict(row) -> dict:
    """A task row as a dict, with ``also`` decoded and ``files`` (its own file
    first) added."""
    task = dict(row)
    try:
        also = json.loads(task.get("also") or "[]")
    except ValueError:
        also = []
    task["also"] = [str(r) for r in also] if isinstance(also, list) else []
    task["files"] = [task["rel"], *task["also"]]
    return task


class TaskRefused(ValueError):
    """A task that cannot be queued as given; the message says why."""


def task_path(rel: str) -> str:
    """*rel* as a project-relative POSIX path, or :class:`TaskRefused`. Only
    its shape is judged here; whether GAGOS may edit the file is judged
    against the project when a writer would take it."""
    raw = (rel or "").strip().replace("\\", "/")
    parts = raw.split("/")
    if (
        not raw
        or len(raw) > 512
        or raw.startswith("/")
        or ":" in raw
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise TaskRefused(f"not a project-relative file path: {rel!r}")
    return raw


#: Proposal statuses. ``refused`` = failed the unattended checks or the model
#: gave no usable answer; ``proposed`` = awaiting reviews; ``accepted`` = both
#: reviewers accepted; ``rejected`` = a reviewer rejected; ``committed`` = on a
#: daily branch, its push or PR not yet confirmed; ``delivered`` = in a PR that
#: exists; ``stale`` = the file changed before delivery; ``failed`` = the
#: delivery checks (parse, ESLint, the tests that import it) failed on master.
#: The model recorded on a proposal no model was asked for (a file too long to
#: send, or one that cannot leave the machine).
NO_MODEL = "none"
#: How a refusal after the unattended checks begins: the change could not be
#: shown to a reviewer without exposing what may not leave the machine.
UNSHOWABLE = "the change cannot be shown to a reviewer"

STATUSES = (
    "refused",
    "proposed",
    "accepted",
    "rejected",
    "committed",
    "delivered",
    "stale",
    "failed",
)


# --------------------------------------------------------------------- D15: a playbook per rule
#
# docs/learning/PAYOFF_PREREGISTRATION.md D15 (2026-11-11). Each rule GAGOS works
# on keeps a short playbook of strategies and pitfalls, learned by a reflector
# from its own reviewers' verdicts, curated here without a model, credited by
# later outcomes, and shown to the writers of findings in the ON arm only.

#: The two arms, and the arm of the operator's tasks (not randomised).
ARM_ON, ARM_OFF = "on", "off"
#: Active entries a rule's playbook holds at most.
PLAYBOOK_MAX_ACTIVE = 8
#: The longest entry, in characters.
PLAYBOOK_ENTRY_CHARS = 240
#: Entries one reflection may add.
PLAYBOOK_ADDS_PER_REFLECTION = 3
#: Proposals per side (accepted, not accepted) a reflection reads.
REFLECT_PER_SIDE = 6
#: Rules reflected on per batch, the longest waiting first.
REFLECTIONS_PER_BATCH = 3
#: Entry kinds.
PLAYBOOK_KINDS = ("strategy", "pitfall")
#: Supply (D15): a finding never accepted may be tried again, at most this many
#: model-answered attempts in all, the last this long before.
MAX_ATTEMPTS = 3
RETRY_AFTER_HOURS = 24
#: An entry this harmful is retired: harmful at least 3, and at least twice
#: helpful plus one.
RETIRE_HARMFUL_AT = 3

_PATHLIKE = re.compile(r"[\/]|\b[\w.-]+\.(?:py|jsx?|tsx?|json|md|css|ya?ml|toml)\b")
_WORD = re.compile(r"[a-z0-9]+")


def d15_arm(rel: str, rule: str, base_digest: str) -> str:
    """A finding's arm, fixed by its path, rule and base (D15): ON when the
    first byte of SHA-256 of ``d15|<path>|<rule>|<base digest>`` is even."""
    first = hashlib.sha256(f"d15|{rel}|{rule}|{base_digest}".encode("utf-8")).digest()[
        0
    ]
    return ARM_ON if first % 2 == 0 else ARM_OFF


def outcome_of(p: Mapping[str, Any]) -> int | None:
    """One proposal's outcome, the one rule for the writers' records and D15:
    1 accepted (accepted, committed or delivered); 0 rejected by a reviewer,
    failed by the delivery checks, or refused for what the model wrote; None
    when nothing was decided (a failed call, no model asked, still awaiting,
    or stale)."""
    if p.get("model") == NO_MODEL:
        return None
    status, refusal = p.get("status"), p.get("refusal") or ""
    if status in ("accepted", "committed", "delivered"):
        return 1
    if status in ("rejected", "failed") or (
        status == "refused" and not refusal.startswith("model call failed")
    ):
        return 0
    return None


def playbook_lines(entries: Sequence[Mapping[str, str]]) -> list[str]:
    """The writer's prompt section for a rule's playbook (D15's ON arm)."""
    if not entries:
        return []
    return [
        "",
        "What GAGOS has learned about this rule from its reviewers' earlier "
        "verdicts (strategies to follow, pitfalls to avoid):",
        *(f"  - [{e['kind']}] {e['text']}" for e in entries),
    ]


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def entry_refusal(kind: str, text: str) -> str | None:
    """Why a proposed playbook entry is not kept, or None."""
    if kind not in PLAYBOOK_KINDS:
        return f"kind {kind!r} is not one of {PLAYBOOK_KINDS}"
    if not text or len(text) > PLAYBOOK_ENTRY_CHARS:
        return f"entries are 1 to {PLAYBOOK_ENTRY_CHARS} characters"
    if _PATHLIKE.search(text):
        return "an entry names no file and no path"
    return None


def repeats(text: str, others: Iterable[str]) -> bool:
    """Whether *text* says what one of *others* says: most of its words again."""
    mine = _words(text)
    for other in others:
        theirs = _words(other)
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= 0.8:
            return True
    return False


#: What the reflector is told (D15). Tool-less and sealed, like the writers.
REFLECTOR_SYSTEM = (
    "You keep a short playbook for one kind of code change that an automated "
    "workshop makes to its own repository. You read why earlier changes of this "
    "kind were accepted or not by their reviewer, their tests and their checks, "
    "and you write general strategies to follow and pitfalls to avoid: advice "
    "that would make the next change of this kind accepted. Never name a file, a "
    "path, a function or a variable; write about the kind of change, not about "
    "one case. Each entry is one sentence of at most "
    f"{PLAYBOOK_ENTRY_CHARS} characters. Reply with ONE JSON object and nothing "
    'else: {"add": [{"kind": "strategy" or "pitfall", "text": "..."}], '
    '"retire": ["<id of an entry the evidence shows is wrong or useless>"]}. '
    f"Add at most {PLAYBOOK_ADDS_PER_REFLECTION}; add nothing that repeats an "
    "entry already kept."
)


def reflection_prompt(
    rule: str,
    entries: Sequence[Mapping[str, Any]],
    accepted: Sequence[str],
    not_accepted: Sequence[str],
) -> str:
    """The reflector's prompt: the rule, its playbook, and the reasons behind
    recent outcomes on each side (no code)."""
    lines = [f"The kind of change: {rule}", "", "The playbook kept so far:"]
    lines += [
        f"  - {e['entry_id']} [{e['kind']}] {e['text']} "
        f"(helped {e['helpful']}, harmed {e['harmful']})"
        for e in entries
    ] or ["  (empty)"]
    lines += ["", "Accepted changes, and why:"]
    lines += [f"  - {r}" for r in accepted] or ["  (none yet)"]
    lines += ["", "Changes not accepted, and why:"]
    lines += [f"  - {r}" for r in not_accepted] or ["  (none yet)"]
    return "\n".join(lines)


class ReflectionRefused(ValueError):
    """A reflector's answer that is not the object it was asked for."""


_PAIR = re.compile(
    r'"kind"\s*:\s*"(strategy|pitfall)"\s*,\s*"text"\s*:\s*"((?:[^"\\]|\\.)*)"', re.S
)
_RETIRE_LIST = re.compile(r'"retire"\s*:\s*\[([^\]]*)\]', re.S)
_ENTRY_ID = re.compile(r"pb-[0-9a-f]{8}")


def parse_reflection(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """``(adds, retires)`` from the reflector's answer: adds as (kind, text).

    Strict JSON first. Deviation D16 (2026-11-11): the first seed found the
    reflector's JSON malformed in 7 of 9 answers (a stray ``","`` after the
    first entry), so an answer that is not JSON is read pair by pair, each
    ``"kind": ..., "text": ...`` whole or not at all."""
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(raw[start : end + 1])
        except ValueError:
            value = None
        if isinstance(value, dict):
            adds = [
                (str(a.get("kind", "")).strip().lower(), str(a.get("text", "")).strip())
                for a in value.get("add") or []
                if isinstance(a, dict)
            ][:PLAYBOOK_ADDS_PER_REFLECTION]
            retires = [str(r) for r in value.get("retire") or [] if isinstance(r, str)]
            return adds, retires
    adds = []
    for kind, text in _PAIR.findall(raw):
        try:
            adds.append((kind, json.loads(f'"{text}"').strip()))
        except ValueError:
            continue
    found = _RETIRE_LIST.search(raw)
    retires = _ENTRY_ID.findall(found.group(1)) if found else []
    if not adds and not retires:
        raise ReflectionRefused("no entry could be read in the reflector's answer")
    return adds[:PLAYBOOK_ADDS_PER_REFLECTION], retires


#: How long a claim on a file lives: a batch that has not released its claims
#: by then died holding them (the hourly job's own limit is three hours).
CLAIM_TTL_S = 3 * 3600


def _now() -> str:
    # Microseconds: refusal reasons are ordered by time, and seconds tie.
    return datetime.now(timezone.utc).isoformat()


def ledger_path() -> Path:
    """GAGOS's daily ledger, for the workshop and the counter alike."""
    return Path(config.DATA_DIR) / "gagos_daily" / "ledger.db"


class DailyLedger:
    """Every proposal and what happened to it. SQLite, one file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(_SCHEMA)
            # Additive migrations for a ledger created by an earlier version.
            have = {r["name"] for r in db.execute("PRAGMA table_info(proposals)")}
            if "facts" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN facts TEXT")
            if "sandbox" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN sandbox TEXT")
            # The council's advisory word on a proposal's tests (2026-11-10).
            if "prescreen" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN prescreen TEXT")
            # D15 (2026-11-11): the proposal's arm, the playbook entries its
            # writer was shown, how many were active, and whether they were
            # credited with its outcome.
            if "arm" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN arm TEXT")
            if "playbook_seen" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN playbook_seen TEXT")
            if "playbook_active" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN playbook_active INTEGER")
            if "credited" not in have:
                db.execute(
                    "ALTER TABLE proposals ADD COLUMN credited INTEGER NOT NULL DEFAULT 0"
                )
            # A task over several files records one proposal per file, grouped.
            if "group_id" not in have:
                db.execute("ALTER TABLE proposals ADD COLUMN group_id TEXT")
            task_cols = {r["name"] for r in db.execute("PRAGMA table_info(tasks)")}
            if "also" not in task_cols:
                db.execute(
                    "ALTER TABLE tasks ADD COLUMN also TEXT NOT NULL DEFAULT '[]'"
                )
            # A day an earlier version recorded as run keeps its claim.
            db.execute(
                "INSERT OR IGNORE INTO day_claims SELECT day, updated_at FROM days "
                "WHERE status = 'ran'"
            )

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    # writes
    def record_proposal(
        self,
        finding: Finding,
        *,
        base_text: str,
        base_commit: str,
        model: str,
        new_text: str | None,
        verdict: StaticVerdict | None,
        refusal: str | None = None,
        day: str | None = None,
        facts: Sequence[str] = (),
        group_id: str | None = None,
        arm: str | None = None,
        playbook_seen: Sequence[str] = (),
        playbook_active: int = 0,
    ) -> str:
        """*group_id*: the task whose several files this proposal is one of;
        the group is tested, reviewed and delivered together. *arm*,
        *playbook_seen* and *playbook_active*: D15's record (the finding's arm,
        the entries its writer was shown, how many were active)."""
        proposal_id = f"gd-{uuid.uuid4().hex[:10]}"
        passed = verdict is not None and verdict.passed and refusal is None
        reason = refusal or (None if passed else (verdict.reason if verdict else None))
        # A new test's base is its module, kept for the reviewers; its diff is
        # the whole new file.
        diff = (
            unified_diff(
                finding.rel,
                "" if finding.rule == MISSING_TEST else base_text,
                new_text,
            )
            if new_text is not None
            else None
        )
        with self._db() as db:
            db.execute(
                "INSERT INTO proposals (proposal_id, day, created_at, rel, rule, "
                "warnings, base_digest, base_commit, base_text, model, status, "
                "refusal, new_text, new_digest, diff, changed_lines, facts, group_id, "
                "arm, playbook_seen, playbook_active) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    day or datetime.now(timezone.utc).date().isoformat(),
                    _now(),
                    finding.rel,
                    finding.rule,
                    json.dumps(finding.warnings),
                    digest(base_text),
                    base_commit,
                    base_text,
                    model,
                    "proposed" if passed else "refused",
                    reason,
                    new_text,
                    digest(new_text) if new_text is not None else None,
                    diff,
                    verdict.changed_lines if verdict else None,
                    json.dumps(list(facts)),
                    group_id,
                    arm,
                    json.dumps(list(playbook_seen)),
                    int(playbook_active),
                ),
            )
        return proposal_id

    def group_members(self, group_id: str) -> list[dict]:
        """The proposals of one task over several files, in the order recorded."""
        with self._db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM proposals WHERE group_id = ? ORDER BY created_at",
                    (group_id,),
                )
            ]

    def resettle(self) -> list[str]:
        """Proposals awaiting review that the reviews already recorded now
        decide, under today's required reviewers; returns them. When Codex left
        the chain (2026-11-02), proposals Claude Code had accepted were still
        waiting for Codex, and no new review would ever touch them again."""
        moved = []
        with self._db() as db:
            for row in db.execute(
                "SELECT proposal_id FROM proposals WHERE status = 'proposed'"
            ).fetchall():
                verdicts = {
                    r["reviewer"]: r["verdict"]
                    for r in db.execute(
                        "SELECT reviewer, verdict FROM reviews WHERE proposal_id = ?",
                        (row["proposal_id"],),
                    )
                }
                if "reject" in verdicts.values():
                    status = "rejected"
                elif all(verdicts.get(r) == "accept" for r in REQUIRED_REVIEWERS):
                    status = "accepted"
                else:
                    continue
                db.execute(
                    "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                    (status, row["proposal_id"]),
                )
                moved.append(row["proposal_id"])
        return moved

    def record_review(
        self, proposal_id: str, reviewer: str, *, model: str, verdict: str, reason: str
    ) -> str:
        """Record one reviewer's verdict; returns the proposal's new status."""
        if reviewer not in REVIEWERS:
            raise ValueError(f"unknown reviewer {reviewer!r}")
        if verdict not in ("accept", "reject"):
            raise ValueError(f"unknown verdict {verdict!r}")
        with self._db() as db:
            row = db.execute(
                "SELECT status FROM proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            if row is None:
                raise KeyError(proposal_id)
            if row["status"] not in ("proposed", "accepted", "rejected"):
                raise ValueError(f"{proposal_id} is {row['status']}, not reviewable")
            db.execute(
                "INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?)",
                (proposal_id, reviewer, model, verdict, reason, _now()),
            )
            verdicts = {
                r["reviewer"]: r["verdict"]
                for r in db.execute(
                    "SELECT reviewer, verdict FROM reviews WHERE proposal_id = ?",
                    (proposal_id,),
                )
            }
            if "reject" in verdicts.values():
                status = "rejected"
            elif all(verdicts.get(r) == "accept" for r in REQUIRED_REVIEWERS):
                status = "accepted"
            else:
                status = "proposed"
            db.execute(
                "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                (status, proposal_id),
            )
        return status

    def record_delivery(
        self,
        proposal_id: str,
        *,
        branch: str,
        outcome: str,
        commit_sha: str | None = None,
        pr_url: str | None = None,
    ) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO deliveries VALUES (?,?,?,?,?,?)",
                (proposal_id, branch, commit_sha, pr_url, outcome, _now()),
            )
            db.execute(
                "UPDATE proposals SET status = ? WHERE proposal_id = ?",
                (
                    outcome
                    if outcome in ("committed", "delivered", "stale")
                    else "failed",
                    proposal_id,
                ),
            )

    def set_pr(self, proposal_ids: Iterable[str], pr_url: str) -> None:
        """The PR exists: only now are its changes delivered (Codex's review
        of #566: a failed push must not leave work marked delivered)."""
        ids = list(proposal_ids)
        with self._db() as db:
            db.executemany(
                "UPDATE deliveries SET pr_url = ?, outcome = 'delivered' WHERE proposal_id = ?",
                [(pr_url, pid) for pid in ids],
            )
            db.executemany(
                "UPDATE proposals SET status = 'delivered' WHERE proposal_id = ?",
                [(pid,) for pid in ids],
            )

    def pending_publication(self) -> dict[str, list[str]]:
        """Committed work whose push or PR is not confirmed, by branch."""
        out: dict[str, list[str]] = {}
        with self._db() as db:
            for row in db.execute(
                "SELECT d.branch, d.proposal_id FROM deliveries d JOIN proposals p "
                "ON p.proposal_id = d.proposal_id WHERE p.status = 'committed' "
                "ORDER BY d.created_at"
            ):
                out.setdefault(row["branch"], []).append(row["proposal_id"])
        return out

    def commit_of(self, proposal_id: str) -> str | None:
        """The commit a delivery made for *proposal_id*, if any."""
        with self._db() as db:
            row = db.execute(
                "SELECT commit_sha FROM deliveries WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return row["commit_sha"] if row else None

    def delivery_branches(self) -> set[str]:
        """Every branch a delivery committed to: such a branch never takes
        later work (its PR may already be merged or closed)."""
        with self._db() as db:
            return {
                r["branch"]
                for r in db.execute(
                    "SELECT DISTINCT branch FROM deliveries WHERE commit_sha IS NOT NULL"
                )
            }

    def refuse(self, proposal_id: str, reason: str) -> None:
        """Refuse a proposal after the fact (it cannot be shown to the
        reviewers without exposing what may not leave the machine)."""
        with self._db() as db:
            db.execute(
                "UPDATE proposals SET status = 'refused', refusal = ? WHERE proposal_id = ?",
                (reason, proposal_id),
            )

    def record_sandbox(
        self, proposal_id: str, verdict: str, *, refusal: str | None = None
    ) -> None:
        """What the proposal's tests did in the sandbox (a
        :class:`~aios.maintenance.sandbox_tests.SandboxVerdict` as JSON); a
        *refusal* when they show the proposal broke what passes without it."""
        with self._db() as db:
            db.execute(
                "UPDATE proposals SET sandbox = ? WHERE proposal_id = ?",
                (verdict, proposal_id),
            )
            if refusal is not None:
                db.execute(
                    "UPDATE proposals SET status = 'refused', refusal = ? "
                    "WHERE proposal_id = ? AND status = 'proposed'",
                    (refusal, proposal_id),
                )

    def record_prescreen(self, proposal_id: str, prescreen: str) -> None:
        """The council's advisory pre-screen of a proposal's tests, as JSON
        (``queen``, ``verdict`` in the review vocabulary, ``reason``). It
        decides nothing: the proposal's status is the reviewers'."""
        with self._db() as db:
            db.execute(
                "UPDATE proposals SET prescreen = ? WHERE proposal_id = ?",
                (prescreen, proposal_id),
            )

    def awaiting_tests(self) -> list[dict]:
        """Proposals awaiting review whose tests have not run in the sandbox."""
        with self._db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM proposals WHERE status = 'proposed' AND "
                    "sandbox IS NULL ORDER BY created_at"
                )
            ]

    def reopen(self, proposal_id: str) -> bool:
        """Put back for review a proposal refused only because it could not be
        shown to a reviewer: it passed the unattended checks, and the cause
        was how it was shown (2026-11-02: GAGOS's own placeholders looked like
        secrets). Any other refusal stays. True when it was reopened."""
        with self._db() as db:
            done = db.execute(
                "UPDATE proposals SET status = 'proposed', refusal = NULL "
                "WHERE proposal_id = ? AND status = 'refused' AND refusal LIKE ?",
                (proposal_id, f"{UNSHOWABLE}%"),
            )
            return done.rowcount == 1

    def reserve_day(self, day: str) -> bool:
        """Claim *day* for GAGOS's one batch, atomically across processes
        (Codex's review of #566: two overlapping runs each proposed two).
        True for exactly one caller per day; a day only blocked can still be
        claimed later the same day, never twice, and never caught up.

        The claim is its own row, written once and never replaced: a later
        report of how the day went cannot clear it (Codex's post-merge review
        of #566: a ``blocked`` record over ``ran`` let a second batch run)."""
        db = self._db()
        db.isolation_level = None  # this transaction is managed by hand
        try:
            db.execute("BEGIN IMMEDIATE")
            claimed = db.execute(
                "INSERT OR IGNORE INTO day_claims VALUES (?, ?)", (day, _now())
            ).rowcount
            if claimed != 1:
                db.execute("ROLLBACK")
                return False
            db.execute(
                "INSERT INTO days VALUES (?, 'ran', NULL, ?) ON CONFLICT(day) DO "
                "UPDATE SET status = 'ran', reason = NULL, updated_at = excluded.updated_at",
                (day, _now()),
            )
            db.execute("COMMIT")
            return True
        finally:
            db.close()

    def claim_files(self, rels: Iterable[str], holder: str) -> bool:
        """Claim every file in *rels* for *holder*, all or none, atomically
        across processes (Codex's design conditions, 2026-11-02: durable atomic
        claims; built 2026-11-10). False when any of them is claimed by another
        holder whose claim is still live. A holder may claim again what it
        holds."""
        wanted = sorted(set(rels))
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_S)
        ).isoformat()
        db = self._db()
        db.isolation_level = None  # this transaction is managed by hand
        try:
            db.execute("BEGIN IMMEDIATE")
            # A claim older than a batch can live is a batch that died with it.
            db.execute("DELETE FROM claims WHERE claimed_at < ?", (cutoff,))
            for rel in wanted:
                row = db.execute(
                    "SELECT holder FROM claims WHERE rel = ?", (rel,)
                ).fetchone()
                if row is not None and row["holder"] != holder:
                    db.execute("ROLLBACK")
                    return False
            now = _now()
            db.executemany(
                "INSERT OR REPLACE INTO claims VALUES (?, ?, ?)",
                [(rel, holder, now) for rel in wanted],
            )
            db.execute("COMMIT")
            return True
        finally:
            db.close()

    def release_claims(self, holder: str) -> int:
        """Release every file *holder* claimed; how many."""
        with self._db() as db:
            return db.execute("DELETE FROM claims WHERE holder = ?", (holder,)).rowcount

    def claimed_files(self) -> set[str]:
        """Files a live claim holds, whoever holds it."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL_S)
        ).isoformat()
        with self._db() as db:
            return {
                r["rel"]
                for r in db.execute(
                    "SELECT rel FROM claims WHERE claimed_at >= ?", (cutoff,)
                )
            }

    # reads
    def proposals(
        self, *, status: str | None = None, day: str | None = None
    ) -> list[dict]:
        query, args = "SELECT * FROM proposals WHERE 1=1", []
        if status:
            query += " AND status = ?"
            args.append(status)
        if day:
            query += " AND day = ?"
            args.append(day)
        with self._db() as db:
            return [dict(r) for r in db.execute(query + " ORDER BY created_at", args)]

    def reviews(self, proposal_id: str) -> dict[str, dict]:
        with self._db() as db:
            return {
                r["reviewer"]: dict(r)
                for r in db.execute(
                    "SELECT * FROM reviews WHERE proposal_id = ?", (proposal_id,)
                )
            }

    def awaiting(self, reviewer: str) -> list[dict]:
        """Proposals that passed the unattended checks and *reviewer* has not
        reviewed. A proposal the other reviewer already rejected is still
        reviewed: D14 reports how often the two disagree, which needs both
        verdicts on every proposal."""
        with self._db() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT p.* FROM proposals p WHERE p.status IN "
                    "('proposed', 'rejected') AND NOT "
                    "EXISTS (SELECT 1 FROM reviews r WHERE r.proposal_id = "
                    "p.proposal_id AND r.reviewer = ?) ORDER BY p.created_at",
                    (reviewer,),
                )
            ]

    def attempted(self, rel: str, rule: str, base_digest: str) -> bool:
        """Whether this exact file content was already proposed for this rule:
        the same work is never asked of the model twice. A call the provider
        refused asked nothing of a model, so it is not an attempt (2026-11-02,
        20:50 UTC: Bedrock refused the account, and each failed hour would
        otherwise have used up ten findings no model ever saw)."""
        with self._db() as db:
            return (
                db.execute(
                    "SELECT 1 FROM proposals WHERE rel = ? AND rule = ? AND "
                    "base_digest = ? AND NOT (status = 'refused' AND "
                    "refusal LIKE 'model call failed%')",
                    (rel, rule, base_digest),
                ).fetchone()
                is not None
            )

    def refusal_reasons(self, rule: str, *, limit: int = 3) -> list[str]:
        """The most recent reasons this rule's proposals were refused, by the
        checks or by a reviewer: what GAGOS learns from real refusals."""
        with self._db() as db:
            rows = db.execute(
                "SELECT reason, created_at FROM ("
                " SELECT p.refusal AS reason, p.created_at FROM proposals p"
                "  WHERE p.rule = ? AND p.status = 'refused' AND p.refusal IS NOT NULL"
                " UNION ALL"
                " SELECT r.reviewer || ': ' || r.reason, r.created_at FROM reviews r"
                "  JOIN proposals p ON p.proposal_id = r.proposal_id"
                "  WHERE p.rule = ? AND r.verdict = 'reject'"
                ") ORDER BY created_at DESC LIMIT ?",
                (rule, rule, limit),
            ).fetchall()
        return [r["reason"] for r in rows]

    # the clerk and the days
    def record_clerk(
        self,
        proposal_id: str,
        *,
        model: str | None,
        status: str,
        summary: str | None = None,
        crux: str | None = None,
        reason: str | None = None,
    ) -> None:
        """What GAGOS's clerk did with a disagreement: its summary, or why it
        could not (no admitted model is recorded as honestly as a summary)."""
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO clerk_jobs VALUES (?,?,?,?,?,?,?)",
                (proposal_id, model, status, summary, crux, reason, _now()),
            )

    def clerk_job(self, proposal_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM clerk_jobs WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
        return dict(row) if row else None

    def disagreements_without_clerk(self) -> list[dict]:
        """Proposals both reviewers judged differently that the clerk has not
        yet summarised."""
        out = []
        for p in self.proposals(status="rejected"):
            reviews = self.reviews(p["proposal_id"])
            if (
                all(r in reviews for r in REVIEWERS)
                and len({reviews[r]["verdict"] for r in REVIEWERS}) == 2
                and self.clerk_job(p["proposal_id"]) is None
            ):
                out.append(p)
        return out

    def record_day(self, day: str, status: str, reason: str | None = None) -> None:
        """How a day went: ``ran``, ``blocked`` (and why) or ``idle``. Blocked
        days are recorded and never caught up (agreed with Codex, 2026-10-30).
        A day whose batch ran stays ``ran``: a later blocked hour does not
        unsay it (the claim itself lives in ``day_claims``)."""
        with self._db() as db:
            db.execute(
                "INSERT INTO days VALUES (?,?,?,?) ON CONFLICT(day) DO UPDATE SET "
                "status = excluded.status, reason = excluded.reason, "
                "updated_at = excluded.updated_at "
                "WHERE days.status != 'ran' OR excluded.status = 'ran'",
                (day, status, reason, _now()),
            )

    def days(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM days ORDER BY day")]

    def record_measures(self, slot: str, head: str, values: Mapping[str, int]) -> None:
        """How complete GAGOS measured itself in this hour's batch, on master at
        *head* (the completion scoreboard, 2026-11-10). A second measure in the
        same hour replaces the first."""
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO measures VALUES (?,?,?,?)",
                (slot, head, _now(), json.dumps(dict(values), sort_keys=True)),
            )

    def measures(self) -> list[dict]:
        """Every hour's measures, oldest first: ``slot``, ``head``,
        ``measured_at`` and ``values`` (measure name -> count)."""
        with self._db() as db:
            rows = db.execute(
                "SELECT slot, head, measured_at, data FROM measures ORDER BY slot"
            ).fetchall()
        return [
            {
                "slot": r["slot"],
                "head": r["head"],
                "measured_at": r["measured_at"],
                "values": json.loads(r["data"]),
            }
            for r in rows
        ]

    def pr_urls(self) -> list[str]:
        """Every PR a delivery opened, newest first (whether still open is
        GitHub's to say)."""
        with self._db() as db:
            return [
                r["pr_url"]
                for r in db.execute(
                    "SELECT pr_url, MAX(created_at) AS t FROM deliveries WHERE "
                    "pr_url IS NOT NULL GROUP BY pr_url ORDER BY t DESC"
                )
            ]

    def reserve_spend(
        self, *, month: str, model: str, purpose: str, usd: float, ceiling: float
    ) -> int | None:
        """Hold *usd*, a call's worst case, against *month*'s ceiling,
        atomically across threads and processes. Returns the hold's id, or
        None when it would pass the ceiling; then no call may be made."""
        db = self._db()
        db.isolation_level = None  # this transaction is managed by hand
        try:
            db.execute("BEGIN IMMEDIATE")
            (spent,) = db.execute(
                "SELECT COALESCE(SUM(usd), 0) FROM spend WHERE month = ?", (month,)
            ).fetchone()
            if spent + usd > ceiling:
                db.execute("ROLLBACK")
                return None
            hold = db.execute(
                "INSERT INTO spend (month, model, purpose, usd, settled, created_at) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (month, model, purpose, usd, _now()),
            ).lastrowid
            db.execute("COMMIT")
            return hold
        finally:
            db.close()

    def settle_spend(
        self, hold: int, *, usd: float, chars_in: int, chars_out: int
    ) -> None:
        """Replace a hold's worst case with the call's estimated cost."""
        with self._db() as db:
            db.execute(
                "UPDATE spend SET usd = ?, settled = 1, chars_in = ?, chars_out = ? "
                "WHERE id = ?",
                (usd, chars_in, chars_out, hold),
            )

    def month_spend(self, month: str) -> dict[str, float]:
        """Estimated spend per model in *month*, holds included."""
        with self._db() as db:
            return {
                r["model"]: r["usd"]
                for r in db.execute(
                    "SELECT model, SUM(usd) AS usd FROM spend WHERE month = ? "
                    "GROUP BY model ORDER BY model",
                    (month,),
                )
            }

    def model_outcomes(self, *, rule: str | None = None) -> dict[str, tuple[int, int]]:
        """Per writing model, for one *rule* or all: (proposals both reviewers
        accepted, proposals decided). Decided: accepted, rejected by a
        reviewer, failed the delivery checks, or refused for what the model
        wrote. A failed call (the provider's refusal, not the model's work), or
        a proposal no model was asked for, decides nothing."""
        out: dict[str, list[int]] = {}
        for p in self.proposals():
            if rule and p["rule"] != rule:
                continue
            won = outcome_of(p)
            if won is None:
                continue
            tally = out.setdefault(p["model"], [0, 0])
            tally[0] += won
            tally[1] += 1
        return {m: (w, d) for m, (w, d) in out.items()}

    def refused_writers(self, models: Iterable[str]) -> list[str]:
        """The writers among *models* whose most recent call failed (the
        provider refused it, or it gave no answer), the longest refused first.
        A writer never asked, or whose last call was answered, is not one."""
        wanted = set(models)
        last: dict[str, dict] = {}
        for p in self.proposals():
            if p["model"] in wanted:
                last[p["model"]] = p
        failed = [
            p
            for p in last.values()
            if p["status"] == "refused"
            and (p["refusal"] or "").startswith("model call failed")
            and not is_usage_limit_error(p["refusal"])
        ]
        return [p["model"] for p in sorted(failed, key=lambda p: p["created_at"])]

    def resting_writers(self, models: Iterable[str]) -> list[str]:
        """The writers among *models* whose most recent call hit a usage limit
        (a plan's session or weekly limit), the longest resting first.

        Not refused: a limit lifts by itself, so each is tried on one finding
        a batch and rejoins the moment it answers. Until 2026-11-09 a limit
        counted as a refusal, and the one probe a batch went to the longest
        refused writer first, so a plan writer waited behind every writer AWS
        had refused. Classified as the router classifies failures
        (aios/core/model_availability.py)."""
        wanted = set(models)
        last: dict[str, dict] = {}
        for p in self.proposals():
            if p["model"] in wanted:
                last[p["model"]] = p
        resting = [
            p
            for p in last.values()
            if p["status"] == "refused" and is_usage_limit_error(p["refusal"] or "")
        ]
        return [p["model"] for p in sorted(resting, key=lambda p: p["created_at"])]

    # tasks the operator writes
    def add_task(
        self, rel: str, text: str, *, said_by: str, also: Sequence[str] = ()
    ) -> str:
        """Queue the operator's task on one file, and on up to
        ``MAX_TASK_FILES - 1`` more (*also*); returns its id. Refuses an empty
        or over-long text, a path that is not project-relative, a file named
        twice, or more files than the bound."""
        body = (text or "").strip()
        if not body:
            raise TaskRefused("a task needs words")
        if len(body) > MAX_TASK_CHARS:
            raise TaskRefused(
                f"a task is at most {MAX_TASK_CHARS} characters; this is {len(body)}"
            )
        who = (said_by or "").strip()
        if not who:
            raise TaskRefused("a task says who wrote it")
        first = task_path(rel)
        more = [task_path(r) for r in also]
        files = [first, *more]
        if len(set(files)) != len(files):
            raise TaskRefused("a file is named twice in the task")
        if len(files) > MAX_TASK_FILES:
            raise TaskRefused(
                f"a task changes at most {MAX_TASK_FILES} files; this names {len(files)}"
            )
        task_id = f"gt-{uuid.uuid4().hex[:10]}"
        now = _now()
        with self._db() as db:
            db.execute(
                "INSERT INTO tasks (task_id, created_at, rel, text, said_by, status, "
                "proposal_id, reason, updated_at, also) "
                "VALUES (?, ?, ?, ?, ?, 'open', NULL, NULL, ?, ?)",
                (task_id, now, first, body, who[:200], now, json.dumps(more)),
            )
        return task_id

    # Goals through the clerk (2026-11-11, the one-system plan's phase 1).
    def record_intake(self, task_id: str, outcome: Mapping[str, Any]) -> None:
        """The clerk's intake of the task *task_id* (goal_intake.intake's
        outcome), replacing an earlier one (a goal that waited for the clerk is
        taken in again)."""
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO goal_intake (task_id, state, clerk, reason, "
                "mission_request, updated_at) VALUES (?,?,?,?,?,?)",
                (
                    task_id,
                    outcome["state"],
                    json.dumps(outcome.get("clerk") or {}),
                    outcome.get("reason") or None,
                    json.dumps(outcome["mission_request"])
                    if outcome.get("mission_request")
                    else None,
                    _now(),
                ),
            )

    def record_origination(self, task_id: str, outcome: Mapping[str, Any]) -> None:
        """One attempt to originate the goal *task_id* as a council mission
        (aios.operations.council_origination.originate_goal's outcome). Every
        attempt is kept: a refusal spends no slot and is tried again."""
        with self._db() as db:
            db.execute(
                "INSERT INTO goal_missions (task_id, state, reason, mission_id, "
                "envelope_id, slot, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    task_id,
                    outcome["state"],
                    outcome.get("reason") or None,
                    outcome.get("mission_id"),
                    outcome.get("envelope_id"),
                    outcome.get("slot"),
                    _now(),
                ),
            )

    def originations(self) -> dict[str, dict]:
        """Each goal's latest origination attempt, by task id."""
        with self._db() as db:
            out: dict[str, dict] = {}
            for r in db.execute("SELECT * FROM goal_missions ORDER BY id"):
                out[r["task_id"]] = dict(r)
            return out

    def intakes(self) -> dict[str, dict]:
        """Every goal's intake, by task id."""
        with self._db() as db:
            out = {}
            for r in db.execute("SELECT * FROM goal_intake"):
                row = dict(r)
                row["clerk"] = json.loads(row["clerk"] or "{}")
                row["mission_request"] = (
                    json.loads(row["mission_request"])
                    if row["mission_request"]
                    else None
                )
                out[row["task_id"]] = row
            return out

    def task(self, task_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _task_dict(row) if row else None

    def tasks(self, *, status: str | None = None) -> list[dict]:
        """Tasks, oldest first; with *status*, only those."""
        query, args = "SELECT * FROM tasks", []
        if status:
            query += " WHERE status = ?"
            args.append(status)
        with self._db() as db:
            return [
                _task_dict(r) for r in db.execute(query + " ORDER BY created_at", args)
            ]

    def _move_task(
        self,
        task_id: str,
        to: str,
        *,
        proposal_id: str | None = None,
        reason: str | None = None,
    ) -> bool:
        # Only an open task moves, and only once: a writer and a cancel cannot
        # both take it.
        with self._db() as db:
            done = db.execute(
                "UPDATE tasks SET status = ?, proposal_id = ?, reason = ?, "
                "updated_at = ? WHERE task_id = ? AND status = 'open'",
                (to, proposal_id, reason, _now(), task_id),
            )
            return done.rowcount == 1

    def take_task(self, task_id: str, proposal_id: str) -> bool:
        """A writer's proposal for the task is recorded. True when it was open."""
        return self._move_task(task_id, "taken", proposal_id=proposal_id)

    def refuse_task(self, task_id: str, reason: str) -> bool:
        """GAGOS cannot do the task; *reason* says why. True when it was open."""
        return self._move_task(task_id, "refused", reason=reason)

    def cancel_task(self, task_id: str) -> bool:
        """The operator withdraws an open task. True when it was open."""
        return self._move_task(task_id, "cancelled", reason="withdrawn by the operator")

    def task_progress(self) -> list[dict]:
        """Every task, oldest first, with what became of its proposal: the one
        read the counter and the face show. ``proposal`` is None until a writer
        takes the task."""
        out = []
        with self._db() as db:
            for t in db.execute("SELECT * FROM tasks ORDER BY created_at"):
                task = _task_dict(t)
                task["proposal"] = None
                task["proposals"] = []
                if task["proposal_id"]:
                    p = db.execute(
                        "SELECT proposal_id, model, status, refusal, changed_lines, "
                        "sandbox FROM proposals WHERE proposal_id = ?",
                        (task["proposal_id"],),
                    ).fetchone()
                    if p:
                        sandbox = None
                        if p["sandbox"]:
                            try:
                                sandbox = json.loads(p["sandbox"]).get("outcome")
                            except (ValueError, AttributeError):
                                sandbox = None
                        delivered = db.execute(
                            "SELECT pr_url FROM deliveries WHERE proposal_id = ?",
                            (p["proposal_id"],),
                        ).fetchone()
                        task["proposal"] = {
                            "proposal_id": p["proposal_id"],
                            "model": p["model"],
                            "status": p["status"],
                            "refusal": p["refusal"],
                            "changed_lines": p["changed_lines"],
                            "sandbox": sandbox,
                            "reviews": {
                                r["reviewer"]: {
                                    "verdict": r["verdict"],
                                    "reason": r["reason"],
                                }
                                for r in db.execute(
                                    "SELECT reviewer, verdict, reason FROM reviews "
                                    "WHERE proposal_id = ?",
                                    (p["proposal_id"],),
                                )
                            },
                            "pr_url": delivered["pr_url"] if delivered else None,
                        }
                        task["proposals"] = [task["proposal"]]
                # A task over several files: every file's proposal, in order.
                members = db.execute(
                    "SELECT proposal_id, rel, status, refusal, changed_lines FROM "
                    "proposals WHERE group_id = ? ORDER BY created_at",
                    (task["task_id"],),
                ).fetchall()
                if len(members) > 1:
                    task["proposals"] = [dict(m) for m in members]
                out.append(task)
        return out

    def task_of_proposal(self, proposal_id: str) -> dict | None:
        """The task a proposal was made for, or None (a lint fix has none). A
        task over several files is found from any one of its proposals."""
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            if row is None:
                row = db.execute(
                    "SELECT t.* FROM tasks t JOIN proposals p ON p.group_id = "
                    "t.task_id WHERE p.proposal_id = ?",
                    (proposal_id,),
                ).fetchone()
        return dict(row) if row else None

    def rels_in_prs(self, pr_urls: Iterable[str]) -> set[str]:
        """The files the proposals delivered in these PRs change."""
        wanted = set(pr_urls)
        if not wanted:
            return set()
        with self._db() as db:
            return {
                r["rel"]
                for r in db.execute(
                    "SELECT p.rel, d.pr_url FROM proposals p JOIN deliveries d ON "
                    "p.proposal_id = d.proposal_id WHERE d.pr_url IS NOT NULL"
                )
                if r["pr_url"] in wanted
            }

    # D15: supply, the playbook, credit and the population
    def may_attempt(self, rel: str, rule: str, base_digest: str) -> bool:
        """Whether a writer may take this finding now (D15's supply): never
        attempted on this base, or never accepted, with fewer than
        :data:`MAX_ATTEMPTS` model-answered attempts, none still awaiting a
        decision, and the last at least :data:`RETRY_AFTER_HOURS` before."""
        with self._db() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT model, status, refusal, created_at FROM proposals "
                    "WHERE rel = ? AND rule = ? AND base_digest = ?",
                    (rel, rule, base_digest),
                )
            ]
        answered = [
            r
            for r in rows
            if not (
                r["status"] == "refused"
                and (r["refusal"] or "").startswith("model call failed")
            )
        ]
        if not answered:
            return True
        if any(outcome_of(r) == 1 for r in answered) or any(
            r["status"] in ("proposed", "accepted", "committed") for r in answered
        ):
            return False
        if len(answered) >= MAX_ATTEMPTS:
            return False
        last = max(datetime.fromisoformat(r["created_at"]) for r in answered)
        return datetime.now(timezone.utc) - last >= timedelta(hours=RETRY_AFTER_HOURS)

    def playbook(self, rule: str, *, active_only: bool = True) -> list[dict]:
        """A rule's playbook entries, oldest first: by time, then in the order
        they were kept. Two entries kept within one tick of the clock tie on
        time, and the tie was broken by their random ids, so "oldest" was a
        coin toss (CI on Windows, 2026-11-13), and with it which entry the
        curator retires first."""
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM playbook WHERE rule = ? ORDER BY created_at, rowid",
                (rule,),
            ).fetchall()
        return [
            {**dict(r), "sources": json.loads(r["sources"] or "[]")}
            for r in rows
            if not active_only or r["status"] == "active"
        ]

    def add_playbook_entries(
        self, rule: str, entries: Iterable[tuple[str, str]], *, sources: Sequence[str]
    ) -> tuple[list[str], list[str]]:
        """The curator (no model): each (kind, text) is kept whole unless it is
        malformed, names a path, or repeats an active entry; past
        :data:`PLAYBOOK_MAX_ACTIVE`, the lowest-scoring active entry is retired.
        Nothing is ever rewritten. Returns (ids added, reasons dropped)."""
        added, dropped = [], []
        active = self.playbook(rule)
        for kind, text in list(entries)[:PLAYBOOK_ADDS_PER_REFLECTION]:
            why = entry_refusal(kind, text)
            if why is None and repeats(text, [e["text"] for e in active]):
                why = "it repeats an entry already kept"
            if why:
                dropped.append(f"{text[:60]!r}: {why}")
                continue
            entry_id = f"pb-{uuid.uuid4().hex[:8]}"
            now = _now()
            with self._db() as db:
                db.execute(
                    "INSERT INTO playbook (entry_id, rule, kind, text, sources, "
                    "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                    (entry_id, rule, kind, text, json.dumps(list(sources)), now, now),
                )
            added.append(entry_id)
            active = self.playbook(rule)
        while len(active) > PLAYBOOK_MAX_ACTIVE:
            worst = min(
                active, key=lambda e: (e["helpful"] - e["harmful"], e["created_at"])
            )
            self.retire_playbook_entry(
                worst["entry_id"],
                f"over {PLAYBOOK_MAX_ACTIVE} active: the lowest score",
            )
            active = self.playbook(rule)
        return added, dropped

    def retire_playbook_entry(self, entry_id: str, reason: str) -> bool:
        with self._db() as db:
            return (
                db.execute(
                    "UPDATE playbook SET status = 'retired', retired_reason = ?, "
                    "updated_at = ? WHERE entry_id = ? AND status = 'active'",
                    (reason, _now(), entry_id),
                ).rowcount
                == 1
            )

    def settle_playbook_credit(self) -> int:
        """Credit each decided ON-arm proposal's outcome to the entries its
        writer was shown, once; retire an entry harmful at least
        :data:`RETIRE_HARMFUL_AT` times and at least twice helpful plus one.
        Returns how many proposals were credited."""
        credited = 0
        for p in self.proposals():
            if p.get("arm") != ARM_ON or p.get("credited"):
                continue
            seen = json.loads(p.get("playbook_seen") or "[]")
            won = outcome_of(p)
            if not seen or won is None:
                continue
            with self._db() as db:
                for entry_id in seen:
                    if won:
                        db.execute(
                            "UPDATE playbook SET helpful = helpful + 1, updated_at = ? "
                            "WHERE entry_id = ?",
                            (_now(), entry_id),
                        )
                    else:
                        db.execute(
                            "UPDATE playbook SET harmful = harmful + 1, updated_at = ? "
                            "WHERE entry_id = ?",
                            (_now(), entry_id),
                        )
                db.execute(
                    "UPDATE proposals SET credited = 1 WHERE proposal_id = ?",
                    (p["proposal_id"],),
                )
            credited += 1
        with self._db() as db:
            harmful = db.execute(
                "SELECT entry_id FROM playbook WHERE status = 'active' AND "
                "harmful >= ? AND harmful >= 2 * (helpful + 1)",
                (RETIRE_HARMFUL_AT,),
            ).fetchall()
        for row in harmful:
            self.retire_playbook_entry(row["entry_id"], "harmed more than it helped")
        return credited

    def decided_for(self, rule: str) -> list[dict]:
        """A rule's decided proposals, newest first, each with ``outcome`` and
        its reviewers' verdicts."""
        out = []
        for p in sorted(
            (p for p in self.proposals() if p["rule"] == rule),
            key=lambda p: p["created_at"],
            reverse=True,
        ):
            won = outcome_of(p)
            if won is None:
                continue
            out.append({**p, "outcome": won, "reviews": self.reviews(p["proposal_id"])})
        return out

    def rules_awaiting_reflection(self) -> list[str]:
        """Rules with a proposal decided since their last reflection, the
        longest waiting first (never reflected on, first of all). The
        operator's tasks have no playbook."""
        counts: dict[str, int] = {}
        for p in self.proposals():
            if p["rule"] == TASK_RULE or outcome_of(p) is None:
                continue
            counts[p["rule"]] = counts.get(p["rule"], 0) + 1
        with self._db() as db:
            seen = {
                r["rule"]: (r["decided_seen"], r["reflected_at"])
                for r in db.execute("SELECT * FROM reflections")
            }
        waiting = [rule for rule, n in counts.items() if n > seen.get(rule, (0, ""))[0]]
        return sorted(waiting, key=lambda rule: (seen.get(rule, (0, ""))[1], rule))

    def awaits_first_reflection(self, rule: str) -> bool:
        """Whether *rule* has decided proposals but was never reflected on
        (deviation D16): its findings wait, so no attempt is spent before its
        playbook exists."""
        with self._db() as db:
            if db.execute(
                "SELECT 1 FROM reflections WHERE rule = ?", (rule,)
            ).fetchone():
                return False
        return any(
            p["rule"] == rule and outcome_of(p) is not None for p in self.proposals()
        )

    def mark_reflected(self, rule: str) -> None:
        decided = sum(
            1
            for p in self.proposals()
            if p["rule"] == rule and outcome_of(p) is not None
        )
        with self._db() as db:
            db.execute(
                "INSERT INTO reflections VALUES (?,?,?) ON CONFLICT(rule) DO UPDATE "
                "SET decided_seen = excluded.decided_seen, "
                "reflected_at = excluded.reflected_at",
                (rule, decided, _now()),
            )

    def d15_population(self) -> list[dict]:
        """D15's analysis population: decided proposals with an arm (not tasks),
        whose rule had at least one active entry when they were assigned."""
        return [
            {**p, "outcome": outcome_of(p)}
            for p in self.proposals()
            if p.get("arm") in (ARM_ON, ARM_OFF)
            and (p.get("playbook_active") or 0) >= 1
            and outcome_of(p) is not None
        ]


__all__ = [
    "DailyLedger",
    "FIRST_RULES",
    "Direction",
    "Finding",
    "MASK_TOKEN",
    "MAX_REACH",
    "MAX_TASK_FILE_CHARS",
    "EDIT_FORMAT",
    "MAX_TASK_TOTAL_CHARS",
    "MAX_TEST_LINES",
    "MISSING_TEST",
    "NO_MODEL",
    "UNSHOWABLE",
    "MaskingFailed",
    "PROPOSER_SYSTEM",
    "PYTHON_PROPOSER_SYSTEM",
    "PYTHON_RULES",
    "is_python_rule",
    "ProposalRefused",
    "REQUIRED_REVIEWERS",
    "REVIEWERS",
    "REVIEW_SCHEMA",
    "StaticVerdict",
    "TASK_SYSTEM",
    "TESTER_SYSTEM",
    "digest",
    "beyond_reach",
    "findings",
    "is_python",
    "linter_of",
    "load_direction",
    "mask_aligned",
    "mask_like",
    "mask_lines",
    "missing_tests",
    "apply_edits",
    "is_edit_answer",
    "parse_edits",
    "parse_proposal",
    "parse_review",
    "parse_task_edits",
    "parse_task_files",
    "file_label",
    "project_facts",
    "proposal_prompt",
    "proposer_system",
    "review_prompt",
    "set_direction",
    "static_verdict",
    "subject_of",
    "task_files_prompt",
    "task_files_review_prompt",
    "task_files_system",
    "task_prompt",
    "task_review_prompt",
    "task_system",
    "task_verdict",
    "first_test_path",
    "first_test_prompt",
    "first_test_review_prompt",
    "first_test_verdict",
    "unified_diff",
    "unmask",
]
