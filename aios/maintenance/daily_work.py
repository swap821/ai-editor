"""GAGOS's daily work on its own frontend: propose, check, review, deliver (D14).

docs/learning/PAYOFF_PREREGISTRATION.md D14 (2026-10-30). The operator decided
that usefulness is starved of real use, not of harnesses, and that he will not
approve every diff: Codex and Claude Code review them, and a change ships only
if both accept. This module is the part that needs no process or network of
its own:

* :func:`findings` -- the day's work: one file and one ESLint rule each, from
  the project's own lint, restricted to rules whose fix is behaviour-preserving
  by nature (:data:`FIRST_RULES`) and to files the lab-to-product port does not
  own;
* :func:`proposal_prompt` and :func:`parse_proposal` -- what the frontier model
  is asked, and the one shape of answer accepted (the whole file, once);
* :func:`static_verdict` -- the unattended checks, which execute nothing the
  model wrote: it parses; the rule's warnings in the file are gone; no other
  warning or error appears; no disable comment is added; the change is bounded;
* :func:`review_prompt` -- what each reviewer reads: the rule, the warnings, the
  whole original file and the diff;
* :class:`DailyLedger` -- every proposal, refusal, review and delivery, durable,
  so the daily report and D14's numbers are read from records, not memory.

A model may propose here; nothing it proposes is applied until both reviewers
accept it, CI passes and the operator merges. That amends the maintenance
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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.maintenance.frontend_static import StaticResult

#: Rules whose fix does not change behaviour by nature: removing what is unused,
#: or naming a type. React-hooks rules change when effects run, and
#: only-export-components needs edits across files; both wait until the review
#: record shows the loop is trustworthy (D14).
FIRST_RULES: tuple[str, ...] = (
    "no-unused-vars",
    "@typescript-eslint/no-unused-vars",
    "@typescript-eslint/no-explicit-any",
)

#: Comments that silence a check instead of fixing it.
_SILENCERS = re.compile(
    r"eslint-disable|@ts-ignore|@ts-nocheck|@ts-expect-error", re.IGNORECASE
)
_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE)

#: Bounds on one proposal's change, in changed (added + removed) lines.
MAX_CHANGED_LINES_BASE = 24
MAX_CHANGED_LINES_PER_WARNING = 8


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


#: A placeholder for a span that may not leave the machine (see :func:`mask_lines`).
MASK_TOKEN = re.compile(r"GAGOSMASK\d{4}")


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
    text: str, redact: Callable[[str], str], *, rounds: int = 4
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
    """
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
            token = f"GAGOSMASK{len(mapping):04d}"
            mapping[token] = body[start:stop]
            out.append(body[:start] + token + body[stop:] + ending)
        current = "".join(out)
    return current, mapping


def unmask(text: str, mapping: Mapping[str, str], *, masked: str) -> str:
    """Restore the placeholders in the model's answer. The answer may drop a
    placeholder (its line was removed) but never invent or duplicate one."""
    for token in set(MASK_TOKEN.findall(text)):
        if token not in mapping:
            raise ProposalRefused(f"the answer invents the placeholder {token}")
        if text.count(token) > masked.count(token):
            raise ProposalRefused(f"the answer duplicates the placeholder {token}")
    for token in reversed(list(mapping)):  # later ones may wrap earlier ones
        text = text.replace(token, mapping[token])
    return text


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


def proposal_prompt(
    finding: Finding,
    text: str,
    *,
    prior_refusals: Sequence[str] = (),
    masked: bool = False,
    facts: Sequence[str] = (),
) -> str:
    """The proposer's prompt. It names the file, never its path: paths do not
    leave the machine."""
    lines = [
        f"File: {Path(finding.rel).name}",
        f"Rule: {finding.rule}",
        "Warnings to fix (line:column message):",
        *(f"  {line}:{col} {msg}" for line, col, msg in finding.warnings),
    ]
    if facts:
        lines += ["", "Facts about this project:", *(f"  - {fact}" for fact in facts)]
    if masked:
        lines += [
            "",
            "Some spans are replaced by placeholders such as GAGOSMASK0000: they "
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
            f"the proposal has an ESLint error: {first.rule}: {first.message}",
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
    if len(_SILENCERS.findall(after_text)) > len(_SILENCERS.findall(before_text)):
        return StaticVerdict(False, "the proposal adds a disable comment", changed)
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
    return StaticVerdict(True, "parses; the warnings are gone; nothing new", changed)


# --------------------------------------------------------------------- reviewing

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["accept", "reject"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


def review_prompt(
    finding: Finding, before_text: str, diff: str, *, facts: Sequence[str] = ()
) -> str:
    """What each reviewer reads. The same text for both, so they judge the
    same evidence independently."""
    warnings = "\n".join(f"  {line}:{col} {msg}" for line, col, msg in finding.warnings)
    known = (
        ["", "Facts about this project, read from its configuration:"]
        + [f"  - {fact}" for fact in facts]
        if facts
        else []
    )
    return "\n".join(
        [
            "You are reviewing a change GAGOS (an AI system) proposed to its own "
            "frontend. You are one of two independent reviewers; the change "
            "ships only if both accept. Be strict and honest.",
            "",
            "ACCEPT only if ALL hold:",
            "- it fixes the listed ESLint warnings and nothing else;",
            "- behaviour, rendering, exports, public names and tests are unchanged;",
            "- nothing is silenced (no disable or ts-ignore comments) and no "
            "type is weakened to hide a problem;",
            "- removed code was truly unused, and nothing it did is lost "
            "(e.g. a side effect, a hook call, an argument position).",
            "Otherwise REJECT, and say exactly why in one or two sentences.",
            "Automated checks already passed: it parses, the listed warnings "
            "are gone, and no other ESLint warning or error was added.",
            "",
            f"File: {finding.rel}",
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


def parse_review(raw: object) -> tuple[str, str]:
    """``(verdict, reason)`` from a reviewer's structured output, or
    ``ValueError`` when it is not one."""
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict):
        raise ValueError("review is not an object")
    verdict, reason = value.get("verdict"), value.get("reason")
    if verdict not in ("accept", "reject") or not isinstance(reason, str):
        raise ValueError(f"review has no valid verdict: {value!r}"[:300])
    return verdict, reason.strip()


# --------------------------------------------------------------------- the ledger

REVIEWERS: tuple[str, ...] = ("codex", "claude")

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
    facts TEXT
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
"""

#: Proposal statuses. ``refused`` = failed the unattended checks or the model
#: gave no usable answer; ``proposed`` = awaiting reviews; ``accepted`` = both
#: reviewers accepted; ``rejected`` = a reviewer rejected; ``delivered`` = on a
#: daily branch; ``stale`` = the file changed before delivery; ``failed`` = the
#: delivery checks (parse, ESLint, the tests that import it) failed on master.
STATUSES = (
    "refused",
    "proposed",
    "accepted",
    "rejected",
    "delivered",
    "stale",
    "failed",
)


def _now() -> str:
    # Microseconds: refusal reasons are ordered by time, and seconds tie.
    return datetime.now(timezone.utc).isoformat()


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
    ) -> str:
        proposal_id = f"gd-{uuid.uuid4().hex[:10]}"
        passed = verdict is not None and verdict.passed and refusal is None
        reason = refusal or (None if passed else (verdict.reason if verdict else None))
        diff = (
            unified_diff(finding.rel, base_text, new_text)
            if new_text is not None
            else None
        )
        with self._db() as db:
            db.execute(
                "INSERT INTO proposals (proposal_id, day, created_at, rel, rule, "
                "warnings, base_digest, base_commit, base_text, model, status, "
                "refusal, new_text, new_digest, diff, changed_lines, facts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                ),
            )
        return proposal_id

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
            elif all(verdicts.get(r) == "accept" for r in REVIEWERS):
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
                    outcome if outcome in ("delivered", "stale") else "failed",
                    proposal_id,
                ),
            )

    def set_pr(self, proposal_ids: Iterable[str], pr_url: str) -> None:
        with self._db() as db:
            db.executemany(
                "UPDATE deliveries SET pr_url = ? WHERE proposal_id = ?",
                [(pr_url, pid) for pid in proposal_ids],
            )

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
        the same work is never asked of the model twice."""
        with self._db() as db:
            return (
                db.execute(
                    "SELECT 1 FROM proposals WHERE rel = ? AND rule = ? AND "
                    "base_digest = ?",
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
        days are recorded and never caught up (agreed with Codex, 2026-10-30)."""
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO days VALUES (?,?,?,?)",
                (day, status, reason, _now()),
            )

    def days(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM days ORDER BY day")]

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


__all__ = [
    "DailyLedger",
    "FIRST_RULES",
    "Finding",
    "MASK_TOKEN",
    "PROPOSER_SYSTEM",
    "ProposalRefused",
    "REVIEWERS",
    "REVIEW_SCHEMA",
    "StaticVerdict",
    "digest",
    "findings",
    "mask_lines",
    "parse_proposal",
    "parse_review",
    "project_facts",
    "proposal_prompt",
    "review_prompt",
    "static_verdict",
    "unified_diff",
    "unmask",
]
