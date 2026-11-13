#!/usr/bin/env python3
"""GAGOS's daily work on its own frontend (D14): propose, review, report, deliver.

docs/learning/PAYOFF_PREREGISTRATION.md D14. Each step is its own command, so a
day can stop anywhere and resume, and every outcome is in the ledger
(``<AIOS_DATA_DIR>/gagos_daily/ledger.db``):

  propose   lint the frontend of --project (a clean checkout of master); for up
            to --budget findings (one file, one rule), ask GAGOS's writers
            (Claude Sonnet and Haiku through Claude Code on the operator's plan,
            and Bedrock models within his monthly AWS ceiling, several at once,
            each finding to one, routed by their accepted record)
            through the one gateway for the whole corrected file, and run the
            unattended static checks. Nothing a model wrote is executed.
  test      each proposal awaiting review has its tests run in the executor's
            sandbox (no network, read-only, nothing from the host's
            environment), judged against its base: one that breaks a test
            passing without it is refused before review. Python only, so far.
  review    --reviewer codex|claude: each open proposal is reviewed by a fresh,
            read-only, tool-less session that sees the rule, the warnings, the
            whole original file and the diff, and returns a schema-checked
            verdict. A proposal is accepted when Claude Code accepts (Codex no
            longer, operator 2026-11-02); a reject from either rejects it.
  deliver   apply the accepted proposals to a daily branch in --worktree (reset
            to origin/master), each checked there (parse, no ESLint error, the
            tests that import it) and committed on its own; a check that fails
            on master without the change too says nothing about it, and CI
            judges it. --open-pr pushes and opens one PR. The operator merges;
            CI gates.
  report    the day's work and D14's running numbers, as Markdown.
  score     the completion scoreboard (2026-11-10): what each hour's batch
            measured on master before asking any model -- warnings, those in
            and out of GAGOS's rules, frontend modules with no test, test files
            that can skip, organs green -- the latest against the first hour.
  reflect   D15 (2026-11-11, docs/learning/PAYOFF_PREREGISTRATION.md): settle the
            playbook's credit, then reflect on up to three rules with new
            verdicts: a strong model reads why their proposals were and were not
            accepted (reasons, never code) and the curator keeps its general
            strategies and pitfalls. Run by `daily` after the reviews.
  d15       D15's decided counts per arm; `--final` runs its one pre-registered
            analysis (H1, H1c with Holm, harm), only at the stopping rule.
  task      the operator's own work (2026-11-03): ``task add --file REL TEXT``
            queues a change in his words on one file, or on up to four more
            (``--also REL``, repeatable); propose takes open tasks before any
            lint finding, and they are tested, reviewed against his words and
            delivered like the rest. A task over several files is one writer
            call, one proposal per changed file (grouped, all or nothing), one
            test run, one review and one commit. ``task list``, ``task cancel``.

The model call needs, by GAGOS's own law, the "coding" task allowed to the cloud
(constitution intersected with the runtime profile: AIOS_ROUTER_CLOUD_TASKS), and
for a Bedrock writer Bedrock credentials; without either it refuses and says
which. Run it with
AIOS_DATA_DIR set to the operator's data, so the call is bound to his enrolled
identity and constitution, and is recorded in his model-call ledger.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from aios import config  # noqa: E402
from aios.core import cloud_spend  # noqa: E402
from aios.domain.reviews import queen_review  # noqa: E402
from aios.maintenance import goal_intake  # noqa: E402
from aios.maintenance.daily_work import (  # noqa: E402
    ARM_ON,
    ARM_OFF,
    REFLECT_PER_SIDE,
    REFLECTIONS_PER_BATCH,
    REFLECTOR_SYSTEM,
    ReflectionRefused,
    d15_arm,
    parse_reflection,
    reflection_prompt,
    BEHAVIOUR_RULES,
    UNTESTED_BEHAVIOUR,
    ledger_path,
    FIRST_RULES,
    MISSING_TEST,
    NO_MODEL,
    UNSHOWABLE,
    PYTHON_RULES,
    is_python_rule,
    MASK_TOKEN,
    MAX_TASK_FILE_CHARS,
    MAX_TASK_TOTAL_CHARS,
    REVIEW_SCHEMA,
    REQUIRED_REVIEWERS,
    REVIEWERS,
    MAX_TASK_FILES,
    TASK_RULE,
    TASK_STATUSES,
    TESTER_SYSTEM,
    TaskRefused,
    DailyLedger,
    Direction,
    load_direction,
    set_direction,
    Finding,
    MaskingFailed,
    StaticVerdict,
    ProposalRefused,
    digest,
    findings,
    first_test_prompt,
    first_test_review_prompt,
    first_test_verdict,
    is_python,
    mask_aligned,
    mask_like,
    mask_lines,
    missing_tests,
    is_edit_answer,
    parse_edits,
    parse_proposal,
    parse_review,
    parse_task_edits,
    parse_task_files,
    project_facts,
    proposal_prompt,
    proposer_system,
    review_prompt,
    static_verdict,
    subject_of,
    task_files_prompt,
    task_files_review_prompt,
    task_files_system,
    task_prompt,
    task_review_prompt,
    task_system,
    task_verdict,
    unified_diff,
    unmask,
)
from aios.maintenance.frontend_static import (  # noqa: E402
    PORT_MANIFEST,
    StaticCheckUnavailable,
    check_texts,
    editable_frontend_files,
    port_manifest_after,
)
from aios.maintenance.python_static import (  # noqa: E402
    PYTHON_SCOPE,
    check_python_texts,
    editable_python_files,
    format_python_text,
    import_refusal,
)

# One derivation for the workshop and the counter (2026-11-03): how a Codex
# session is sealed, and where the real Claude Code binary is.
from aios.application.governance.emergency_stop import EmergencyStopError  # noqa: E402
from aios.application.workers.workshop_foundry import (  # noqa: E402
    WorkshopFoundry,
    WriterLeg,
)
from aios.core.plan_cli import CLAUDE_SEALED, CODEX_SEALED  # noqa: E402
from aios.core.plan_cli import claude_executable as _claude_executable  # noqa: E402
from aios.core.plan_cli import codex_executable as _codex_executable  # noqa: E402
from aios.maintenance.sandbox_tests import (  # noqa: E402
    BROKE_PREFIX,
    PASSED,
    UNAVAILABLE,
    BaseTrees,
    SandboxVerdict,
    run_change_tests,
)

DEFAULT_MODEL = "mistral.mistral-large-3-675b-instruct"
#: A whole-file proposal for a longer file would not fit one answer reliably.
MAX_FILE_CHARS = 40_000
#: The longest answer a writer may give, in tokens.
MAX_OUTPUT_TOKENS = 12_000

# --------------------------------------------------------------------- the workforce

#: GAGOS's Claude writers: Sonnet and Haiku through Claude Code on the
#: operator's own plan, with no API key (the operator, 2026-11-03: "GAGOS can
#: use several SONNET AND HAIKU AGENTS", through his plan). Each answered a live
#: call on his plan that day.
CLAUDE_WRITERS = ("claude-sonnet-5-5", "claude-haiku-5-5")
#: At most this many findings a batch go to the Claude writers; the rest wait
#: for a later hour. 4 until 2026-11-11, when the operator raised it: "I have a
#: good plan of Claude don't worry use as many sonnet and haiku models
#: simultaneously at same time (multi-agent)".
PLAN_PROPOSALS_PER_BATCH = 16
#: GAGOS's Codex writers: the two GPT models the operator named, through Codex
#: on his OpenAI plan (2026-11-03: "use its models also like GPT 6.1 terra or
#: GPT 6 Luna ... like using sonnet and haiku"). Each answered a sealed call
#: that day. Claude Code stays the reviewer: a different family judges.
CODEX_WRITERS = ("gpt-6.1-terra", "gpt-6-luna")
#: His OpenAI plan is shared with his own Codex sessions (it hit its usage
#: limit on 2026-11-02), so it too takes at most this many a batch.
CODEX_PROPOSALS_PER_BATCH = 4
PLAN_WRITERS = (*CLAUDE_WRITERS, *CODEX_WRITERS)


def plan_shares() -> tuple[tuple[str, tuple[str, ...], int], ...]:
    """Each of his plans: its name, its writers, and its share of a batch."""
    return (
        ("Claude", CLAUDE_WRITERS, PLAN_PROPOSALS_PER_BATCH),
        ("OpenAI", CODEX_WRITERS, CODEX_PROPOSALS_PER_BATCH),
    )


#: GAGOS's Bedrock writers (the operator, 2026-11-02: "multi models agent
#: simultaneously together"). Each answered a live call on GAGOS's own key in
#: us-east-1 on 2026-11-02; at 20:50 UTC that day AWS refused the account.
BEDROCK_WRITERS = (
    "mistral.devstral-2-123b",
    "qwen.qwen3-coder-next",
    "deepseek.v3.2",
    "mistral.mistral-large-3-675b-instruct",
    "moonshotai.kimi-k2.5",
)
#: GAGOS's writers, several working at once.
WORKFORCE = (*CLAUDE_WRITERS, *CODEX_WRITERS, *BEDROCK_WRITERS)
#: GAGOS's work when the operator names none (2026-11-02): the lint rules
#: whose fix keeps behaviour, in its frontend and in its Python (its backend and
#: itself), then a first test for each frontend module that has none.
WORK_RULES = (*FIRST_RULES, *PYTHON_RULES, *BEHAVIOUR_RULES, MISSING_TEST)
#: An existing test shown to the test writer for this codebase's conventions,
#: when one this short sits beside the module and needs no masking.
MAX_EXAMPLE_CHARS = 6_000

#: Model calls in flight at most: Codex's starting point was 2 (2026-11-02);
#: raised to 4 on 2026-11-11 at the operator's word, from measured capacity:
#: each writer is a Claude Code or Codex process of about 0.4 to 0.6 GB, and the
#: laptop had about 3 GB free beside the backend and the sandbox's VM. Fewer run
#: when less is free (writers_at_once). The ESLint checks still run one at a
#: time, so a batch never holds more than one lint's memory.
WRITERS_AT_ONCE = 4
#: Memory a writer process is given room for, and memory left to everything
#: else, in MB (writers_at_once).
WRITER_MB = 600
SPARE_MB = 1200
#: A writer is tried on this many decided proposals before its record steers
#: how much work it gets.
EXPLORE = 5

#: The operator, 2026-11-02: "$100 a month for AWS". Every Bedrock call holds
#: its worst case against the UTC month's total first, and makes no call past it.
#: One setting with the gateway's ceiling over every metered call
#: (AIOS_CLOUD_MONTHLY_USD, 2026-11-10), which also holds this workshop's calls.
MONTHLY_AWS_USD = config.CLOUD_MONTHLY_USD
#: A deliberately high price for every writer, USD per million tokens (input,
#: output), and characters over-counted as tokens at 3 each where a provider
#: reports no tokens: one source with the gateway's ceiling
#: (aios/core/cloud_spend.py). Since 2026-11-10 a call is settled from the
#: tokens its provider reports; the price is still not AWS's bill.
PRICE_PER_MTOK = cloud_spend.PRICE_PER_MTOK
CHARS_PER_TOKEN = cloud_spend.CHARS_PER_TOKEN


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def estimate_usd(chars_in: int, chars_out: int) -> float:
    price_in, price_out = PRICE_PER_MTOK
    return (chars_in * price_in + chars_out * price_out) / CHARS_PER_TOKEN / 1e6


def worst_case_usd(chars_in: int) -> float:
    price_in, price_out = PRICE_PER_MTOK
    return (chars_in / CHARS_PER_TOKEN * price_in + MAX_OUTPUT_TOKENS * price_out) / 1e6


def allocate(
    n: int, outcomes: dict[str, tuple[int, int]], roster: tuple[str, ...]
) -> list[str]:
    """Which writer takes each of *n* findings. A writer still being tried
    (fewer than EXPLORE decided proposals) gets one first; the rest go to
    every writer in proportion to its record, (accepted + 1) / (decided + 2),
    largest remainder first. GAGOS gives more work to the writers whose work
    is accepted: what it learns from experience is measured, not prompted."""
    if n <= 0 or not roster:
        return []
    record = {m: outcomes.get(m, (0, 0)) for m in roster}
    picks = [m for m in roster if record[m][1] < EXPLORE][:n]
    rest = n - len(picks)
    if rest:
        score = {m: (w + 1) / (d + 2) for m, (w, d) in record.items()}
        quota = {m: rest * score[m] / sum(score.values()) for m in roster}
        share = {m: int(quota[m]) for m in roster}
        by_remainder = sorted(roster, key=lambda m: share[m] - quota[m])
        for m in by_remainder[: rest - sum(share.values())]:
            share[m] += 1
        picks += [m for m in roster for _ in range(share[m])]
    return picks


TASK = "coding"


def _direction_path() -> Path:
    return config.DATA_DIR / "gagos_daily" / "direction.json"


def cmd_direct(args: argparse.Namespace) -> int:
    """Record the operator's direction, relayed by his chief architect. Shows
    the direction in force when given nothing to change."""
    path = _direction_path()
    current = load_direction(path)
    if not any([args.note, args.rules, args.focus, args.avoid, args.clear]):
        print(json.dumps(current.as_dict(), indent=2))
        return 0
    base = Direction() if args.clear else current
    updated = Direction(
        notes=base.notes + tuple(args.note or ()),
        rules=tuple(args.rules) if args.rules else base.rules,
        focus=tuple(args.focus) if args.focus else base.focus,
        avoid=tuple(args.avoid) if args.avoid else base.avoid,
    )
    stamped = set_direction(path, updated, said=args.said or "")
    print(json.dumps(stamped.as_dict(), indent=2))
    return 0


def ledger() -> DailyLedger:
    return DailyLedger(ledger_path())


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    ).stdout.strip()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# --------------------------------------------------------------------- the model


def cloud_coding_allowed() -> tuple[bool, str]:
    """GAGOS's egress law for the "coding" task: the same derivation the router
    uses (constitution intersected with the active runtime profile)."""
    from aios.api.deps import get_policy_kernel
    from aios.core import router

    policy = get_policy_kernel().router_policy()
    probe = router.Provider(
        name="gagos-daily-probe",
        privacy=router.PRIVACY_CLOUD,
        cost=router.COST_HIGH,  # Bedrock's class (aios/core/router_wiring.py)
        available=True,
        models=("bedrock",),
    )
    allowed = router.policy_allows(policy, TASK, probe)
    return allowed, (
        f"cloud tasks in force {sorted(policy.cloud_tasks)}, max cost {policy.max_cost}"
    )


def egress_redact(text: str) -> str:
    """What GAGOS's egress scrubbers would send in place of *text*: the
    gateway's secret policy, then Bedrock's privacy filter. The oracle for
    :func:`mask_lines`, never a copy of their patterns."""
    from aios.core.privacy_filter import PrivacyFilter
    from aios.runtime.secret_policy import SecretPolicy

    scrubbed = SecretPolicy().inspect_text(text).scrubbed
    safe, _audit = PrivacyFilter().filter([{"role": "user", "content": scrubbed}])
    return str(safe[0]["content"]) if safe else ""


#: The secret scanner's sliding window starts at every fifth character of the
#: WHOLE payload (``_sliding_window_entropy_scan``, frozen core), so whether a
#: span is redacted depends on where it lands in the prompt, modulo this.
SCAN_ALIGNMENTS = 5


def mask_redact(text: str) -> str:
    """The oracle masking asks: *text* as the egress scrubbers would leave it
    wherever it lands in a prompt. Each line is taken as redacted at the first
    of the scanner's window alignments that changes it; the whole text is
    redacted at each alignment, so every exemption still sees its context.

    2026-11-12: the operator's goal gt-838f049241 was refused unsent because
    ``ownsWorkSurface(writingTab.id, token)`` is scrubbed at offset 2 mod 5 and
    not at 0 -- the file was masked at one alignment, and the prompt checked at
    another."""
    lines = text.splitlines(keepends=True)
    merged = list(lines)
    changed = [False] * len(lines)
    for shift in range(SCAN_ALIGNMENTS):
        pad = " " * shift
        whole = egress_redact(pad + text)
        found = whole[shift:].splitlines(keepends=True)
        if not whole.startswith(pad) or len(found) != len(lines):
            # A redaction took the padding or joined lines: judge each line
            # alone at this alignment.
            found = []
            for line in lines:
                alone = egress_redact(pad + line)
                found.append(alone[shift:] if alone.startswith(pad) else alone)
        for i, (line, other) in enumerate(zip(lines, found)):
            if not changed[i] and other != line:
                merged[i], changed[i] = other, True
    return "".join(merged)


#: How much of a failed delivery check's own output is kept with its reason.
SMOKE_EXCERPT = 600

#: The lines of a check's output that say what failed.
_FAILED_LINE = re.compile(
    r"FAIL|Error|×|✗|expected|Timeout|timed out|deadline|exit \d+"
)


def smoke_excerpt(steps: list) -> str:
    """The failing step's own last words, scrubbed, to keep beside a delivery
    check's reason: what the hour saw. Empty when no failed step said anything.

    2026-11-12: the UX-05 change failed delivery twice as "the tests related to
    the frontend targets did not pass", passed every reproduction outside the
    hour, and the output that would have said why was gone."""
    failed = next((s for s in steps if not s.passed and (s.detail or "").strip()), None)
    if failed is None:
        return ""
    lines = [
        " ".join(line.split()) for line in failed.detail.splitlines() if line.strip()
    ]
    said = [line for line in lines if _FAILED_LINE.search(line)] or lines
    # Kept in the local log and ledger only: a named credential is scrubbed, the
    # failing test's path is not (it is what says why).
    text = goal_intake.clerk_redact(" | ".join(said[-8:]))
    return f" ({failed.name}: {text[-SMOKE_EXCERPT:]})"


#: How much of a writer's own words a refusal keeps, scrubbed, when it made no edit.
NO_EDIT_EXCERPT = 240


def no_edit_refusal(raw: str) -> str | None:
    """The refusal for a task's answer with no edit and no fenced file: what the
    writer is told to give when a task cannot be done in its files
    (``TASK_SYSTEM``). It keeps the writer's own words, scrubbed and cut short,
    so the operator and the reviewers can see why. None for any other answer.

    2026-11-12: the PERF-04 goal was refused twice as "expected exactly one
    fenced code block, got 0", and what the writer said was lost; it had been
    shown the test file but not the store whose API the test needed."""
    if is_edit_answer(raw) or "```" in (raw or ""):
        return None
    words = egress_redact(" ".join((raw or "").split()))[:NO_EDIT_EXCERPT]
    return "the writer made no edit" + (
        f": {words!r}" if words else " (an empty answer)"
    )


def would_be_altered(prompt: str, system: str) -> str | None:
    """Why the prompt would not reach the model as written, if it would not.
    A file the secret policy or the privacy filter would change is not sent:
    the model would be proposing against a different file."""
    from aios.core.privacy_filter import PrivacyFilter
    from aios.runtime.secret_policy import SecretPolicy

    if SecretPolicy().inspect_text(prompt).scrubbed != prompt:
        return "the secret policy would scrub this file, so it is not sent"
    # An empty system message is not sent (the filter drops it), so it is not
    # checked either: dropping it is not altering the prompt.
    messages = [
        *([{"role": "system", "content": system}] if system else []),
        {"role": "user", "content": prompt},
    ]
    safe, _audit = PrivacyFilter().filter(messages)
    if safe != messages:
        return "the privacy filter would redact this file, so it is not sent"
    return None


#: The longest a plan writer may take over one answer.
WRITER_TIMEOUT_S = 600


def plan_writer(model: str):
    """One of GAGOS's writers on the operator's plans: the counter's own
    :class:`~aios.core.plan_cli.PlanCliClient`, sealed the same way (no tools,
    no session, none of his MCP servers or plugins, an empty directory, the
    privacy filter first). A call that gives no answer raises, and is recorded
    as a failed call, never as the model's work."""
    from aios.core.plan_cli import PlanCliClient

    return PlanCliClient(
        claude_models=(model,) if model in CLAUDE_WRITERS else (),
        codex_models=(model,) if model in CODEX_WRITERS else (),
        timeout_s=WRITER_TIMEOUT_S,
    )


def governed_completer(model: str, region: str):
    """``complete(prompt, system, request_id) -> str`` through organ 32's
    gateway, bound to the enrolled operator and the active constitution."""
    from aios.api.deps import get_constitution_authority, get_emergency_stop
    from aios.application.intelligence.gateway import (
        AdvisoryChatCompletionAdapter,
        GovernedAdvisoryCompletionClient,
    )
    from aios.core.bedrock import BedrockClient, credentials_available
    from aios.infrastructure.identity.sqlite_store import credential_digest

    if model in PLAN_WRITERS:
        provider = plan_writer(model)
    elif not credentials_available(region):
        raise SystemExit(
            f"no Bedrock credentials for {region}: set AWS_BEARER_TOKEN_BEDROCK "
            "(the operator's keystore) before proposing"
        )
    else:
        provider = AdvisoryChatCompletionAdapter(
            BedrockClient(
                model=model,
                region=region,
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.0,
            ),
            model=model,
        )
    snapshot = get_constitution_authority().get_active_snapshot()
    emergency_stop = get_emergency_stop()

    def complete(prompt: str, system: str, request_id: str) -> str:
        client = GovernedAdvisoryCompletionClient(
            provider,
            request_id=request_id,
            operator_identity_digest=credential_digest(
                snapshot.ratified_by_operator_id
            ),
            constitution_digest=snapshot.snapshot_digest,
            target="cloud",
            desired_outcome=(
                "one proposed fix of lint warnings in one file of GAGOS's own code, for "
                "review before the operator merges"
            ),
            emergency_stop=emergency_stop,
        )
        return client.complete(prompt, system=system)

    return complete


# --------------------------------------------------------------------- propose


def task_jobs(
    led: DailyLedger,
    root: Path,
    head: str,
    busy: set[str],
    notes: tuple[str, ...],
    facts: tuple[str, ...],
    budget: int,
) -> list[tuple]:
    """The operator's open tasks made ready, oldest first, as the same jobs the
    batch makes of lint findings (the last two elements are the task's id and,
    for a task over several files, every file's ``(rel, text, masked, mapping,
    facts)``; None for a task over one). What GAGOS cannot do is refused here
    with a reason, and no model is asked. A task one of whose files another
    unmerged GAGOS change or an earlier task of this batch holds waits, open,
    for a later hour. Every file of a task must be one GAGOS may edit, readable,
    within the bound, maskable; the files together within
    ``MAX_TASK_TOTAL_CHARS``: the writer returns every changed file whole in one
    answer."""
    jobs: list[tuple] = []
    editable: dict[bool, set[str] | Exception] = {}
    held: set[str] = set()
    # Goals through the clerk (2026-11-11): the writer reads the clerk's
    # briefing beside the operator's words. The clerk is advisory: a goal it
    # has not briefed (no model qualified yet) is worked on as before.
    intakes = led.intakes() if goals_through_clerk() else {}
    for task in led.tasks(status="open"):
        if len(jobs) >= budget:
            break
        tid = task["task_id"]
        files = task["files"]

        def refuse(reason: str) -> None:
            led.refuse_task(tid, reason)
            print(f"  task {tid} refused: {reason}")

        parts: list[tuple[str, str, str, dict, tuple[str, ...]]] = []
        waits: str | None = None
        refused = False
        # Each file under a prefix of its own: a placeholder moved between
        # files is never restored as the wrong span.
        floor = 1
        for rel in files:
            python = is_python(rel)
            if python not in editable:
                # The same files its lint work may change: never the frozen core
                # nor an organ's entrypoint.
                try:
                    editable[python] = set(
                        editable_python_files(root)
                        if python
                        else editable_frontend_files(root)
                    )
                except (StaticCheckUnavailable, subprocess.CalledProcessError) as exc:
                    editable[python] = exc
            allowed = editable[python]
            if isinstance(allowed, Exception):
                waits = f"which files GAGOS may edit is unknown: {allowed}"
                break
            if rel not in allowed:
                refuse(
                    f"{rel} is not a file GAGOS may edit: it does not exist here, or it "
                    "is frozen core or an organ's entrypoint"
                )
                refused = True
                break
            if rel in busy or rel in held:
                waits = waits or f"another GAGOS change holds {rel}"
                continue
            try:
                text = (root / rel).read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                refuse(f"{rel} cannot be read as text: {exc}")
                refused = True
                break
            if len(text) > MAX_TASK_FILE_CHARS:
                refuse(
                    f"{rel} is {len(text)} characters; the bound for a file a task "
                    f"changes is {MAX_TASK_FILE_CHARS}"
                )
                refused = True
                break
            try:
                masked, mapping = mask_lines(text, mask_redact, min_width=floor)
            except MaskingFailed as exc:
                refuse(str(exc))
                refused = True
                break
            if mapping:
                floor = next(iter(mapping))[:-4].count("Q") + 1
            parts.append((rel, text, masked, mapping, notes if python else facts))
        if refused:
            continue
        if waits:
            print(f"  task {tid} waits: {waits}")
            continue
        if len(files) > 1:
            # Measured as sent: a placeholder can be longer than what it hides,
            # so the masked texts are what must fit one answer (a reviewer of
            # D14, 2026-11-03).
            total = max(
                sum(len(part[1]) for part in parts),
                sum(len(part[2]) for part in parts),
            )
            if total > MAX_TASK_TOTAL_CHARS:
                refuse(
                    f"the task's {len(files)} files are {total} characters together; "
                    f"the bound for a task over several files is "
                    f"{MAX_TASK_TOTAL_CHARS} (what one writer's prompt may carry)"
                )
                continue
        rel, text, masked, mapping, known = parts[0]
        # His words are scrubbed like his direction notes before any model
        # reads them.
        said = egress_redact(task["text"])
        briefing = egress_redact(goal_intake.writer_briefing(intakes.get(tid)))
        if len(files) == 1:
            prompt = task_prompt(
                rel, said, masked, masked=bool(mapping), facts=known, briefing=briefing
            )
            system = task_system(rel)
        else:
            prompt = task_files_prompt(
                said,
                [(p[0], p[2]) for p in parts],
                masked=any(p[3] for p in parts),
                # Facts that fit every file: a mix of kinds gets the frontend's,
                # which hold the operator's notes too.
                facts=notes if all(is_python(p[0]) for p in parts) else facts,
                briefing=briefing,
            )
            system = task_files_system(files)
        altered = would_be_altered(prompt, system)
        if altered:
            refuse(altered)
            continue
        common = dict(base_text=text, base_commit=head, facts=known)
        held.update(files)
        jobs.append(
            (
                Finding(rel, TASK_RULE, ()),
                text,
                masked,
                mapping,
                prompt,
                system,
                common,
                tid,
                parts if len(files) > 1 else None,
            )
        )
    return jobs


def record_task_files(
    led: DailyLedger,
    root: Path,
    lint: threading.Lock,
    job: tuple,
    *,
    model: str,
    raw: str,
    took,
    started: float,
) -> None:
    """A writer's answer to a task over several files, read, checked and
    recorded: one proposal per CHANGED file, each grouped under the task's id,
    and the task taken by the first. All or nothing: when any file's change is
    refused, every file of the group is, saying which and why. An answer that
    cannot be read, or changes nothing, is one refused proposal on the task's
    first file, as for a task over one."""
    f, _text, _masked, _mapping, _prompt, _system, common, task_id, parts = job
    head = common["base_commit"]
    whole = dict(common, model=model)

    def refused(why: str) -> None:
        pid = led.record_proposal(f, **whole, new_text=None, verdict=None, refusal=why)
        took(pid)
        print(f"  {pid} {f.rel} ({model}): refused: {why}")

    try:
        why = no_edit_refusal(raw)
        if why:
            raise ProposalRefused(why)
        answered = (
            parse_task_edits(raw, [p[2] for p in parts])
            if is_edit_answer(raw)
            else parse_task_files(raw, [p[1] for p in parts])
        )
        changed: dict[int, str] = {}
        for i, new in sorted(answered.items()):
            rel, text, masked, mapping, _facts = parts[i]
            new_text = unmask(new, mapping, masked=masked)
            # A placeholder of another file's mask stays in the text, unrestored:
            # the writer moved it, and it would be written into the file.
            strange = set(MASK_TOKEN.findall(new_text)) - set(MASK_TOKEN.findall(text))
            if strange:
                raise ProposalRefused(
                    f"the answer puts a placeholder of another file into {rel}: "
                    f"{sorted(strange)[0]}"
                )
            if new_text != text:
                changed[i] = new_text
    except ProposalRefused as exc:
        refused(str(exc))
        return
    if not changed:
        refused(
            "the writer returned every file unchanged: the task may need more than "
            "these files"
        )
        return
    # Each changed file once more through the static checks, both texts, each
    # also with inline configuration off (see task_verdict).
    verdicts: dict[int, StaticVerdict | None] = {}
    why: dict[int, str] = {}
    for i, new_text in changed.items():
        rel, text, _masked, _mapping, _facts = parts[i]
        try:
            if is_python(rel):
                # The layout the required format gate accepts (2026-11-04).
                new_text = changed[i] = format_python_text(root, rel, new_text)
            check = check_python_texts if is_python(rel) else check_texts
            with lint:
                before = check(root, {rel: text}, inline_off=True)[rel]
                after = check(root, {rel: new_text}, inline_off=True)[rel]
        except StaticCheckUnavailable as exc:
            verdicts[i], why[i] = None, f"static checks unavailable: {exc}"
            continue
        verdict = task_verdict(rel, text, new_text, before, after)
        if verdict.passed and is_python(rel):
            # Ruff sees one file; what other modules take from it is checked here.
            taken = import_refusal(root, rel, text, new_text)
            if taken:
                verdict = StaticVerdict(False, taken, verdict.changed_lines)
        verdicts[i] = verdict
        if not verdict.passed:
            why[i] = verdict.reason
    first = min(why) if why else None
    ids = []
    for i, new_text in changed.items():
        rel, text, _masked, _mapping, known = parts[i]
        own = dict(
            base_text=text,
            base_commit=head,
            model=model,
            facts=known,
            group_id=task_id,
        )
        refusal = None
        if first is not None and i != first:
            refusal = (
                f"{parts[first][0]} was refused ({why[first]}); a task over several "
                "files is all or nothing"
            )
        elif first == i and verdicts[i] is None:
            refusal = why[i]
        ids.append(
            led.record_proposal(
                Finding(rel, TASK_RULE, ()),
                **own,
                new_text=new_text,
                verdict=verdicts[i],
                refusal=refusal,
            )
        )
    took(ids[0])
    state = (
        "PASSED static checks"
        if first is None
        else f"REFUSED: {parts[first][0]}: {why[first]}"
    )
    lines = sum((v.changed_lines if v else 0) for v in verdicts.values())
    print(
        f"  {ids[0]} {TASK_RULE} in {len(changed)} file(s) from {f.rel} ({model}): "
        f"{state} ({lines} lines, {time.monotonic() - started:.0f}s)"
    )


def job_files(job: tuple) -> list[str]:
    """The files one batch job writes: a task's several, or its finding's one."""
    parts = job[8]
    return [part[0] for part in parts] if parts else [job[0].rel]


def writers_foundry() -> WorkshopFoundry:
    """The Worker Foundry the batch's writers are admitted by: under the
    operator's durable emergency stop (the one the gateway already obeys) and on
    the cortex bus's outbox, which the backend reads."""
    from aios.api.deps import get_emergency_stop
    from aios.runtime.cortex_bus import CortexBus

    return WorkshopFoundry(
        emergency_stop=get_emergency_stop(),
        bus=CortexBus() if config.CORTEX_BUS else None,
        writers_at_once=writers_at_once(),
    )


def writers_at_once(free_mb: float | None = None) -> int:
    """How many writers run at once now: :data:`WRITERS_AT_ONCE`, fewer when
    the laptop has less free memory than they and :data:`SPARE_MB` need, and
    never fewer than one (2026-11-11)."""
    if free_mb is None:
        try:
            import psutil

            free_mb = psutil.virtual_memory().available / 2**20
        except Exception:  # unknown: the configured bound stands
            return WRITERS_AT_ONCE
    room = int((free_mb - SPARE_MB) // WRITER_MB)
    return max(1, min(WRITERS_AT_ONCE, room))


def cmd_propose(args: argparse.Namespace) -> int:
    root = Path(args.project).resolve()
    led = ledger()
    head = _git(root, "rev-parse", "HEAD")
    direction = load_direction(_direction_path())
    # The operator's taste reaches the proposer and both reviewers, scrubbed
    # like everything else that leaves the machine.
    notes = tuple(
        f"The operator's direction: {egress_redact(note)}" for note in direction.notes
    )
    facts = project_facts(root) + notes
    if _git(root, "status", "--porcelain", "--", "frontend/src", *PYTHON_SCOPE):
        print(f"refused: GAGOS's files have uncommitted changes in {root}")
        return 2
    rules = tuple(args.rules or direction.rules or WORK_RULES)
    texts = {
        rel: (root / rel).read_bytes().decode("utf-8")
        for rel in editable_frontend_files(root)
    }
    try:
        results = check_texts(root, texts)
    except StaticCheckUnavailable as exc:
        print(f"refused: {exc}")
        return 2
    python_checked = False
    if any(is_python_rule(r) for r in rules):
        # Its backend and itself; unavailable, the frontend's work goes on.
        try:
            py_texts = {
                rel: (root / rel).read_bytes().decode("utf-8")
                for rel in editable_python_files(root)
            }
            results.update(check_python_texts(root, py_texts))
            texts.update(py_texts)
            python_checked = True
        except (StaticCheckUnavailable, subprocess.CalledProcessError) as exc:
            print(f"Python work skipped this batch: {exc}")
    every = Counter(m.rule for r in results.values() for m in r.warnings())
    busy = set(getattr(args, "skip", None) or ())

    def base_of(f: Finding) -> str:
        # A first test's base is its module: a changed module is new work.
        return texts[subject_of(f.rel)] if f.rule == MISSING_TEST else texts[f.rel]

    candidates = findings(results, rules=[r for r in rules if r != MISSING_TEST])
    if MISSING_TEST in rules:
        candidates += missing_tests(texts, lambda rel: (root / rel).exists())
    work = direction.steer(
        [
            f
            for f in candidates
            if f.rel not in busy
            and led.may_attempt(f.rel, f.rule, digest(base_of(f)))
            # D16: an attempt is not spent before its rule's playbook exists.
            and not led.awaits_first_reflection(f.rule)
        ]
    )
    if busy:
        print(f"left alone, GAGOS's unmerged work touches them: {len(busy)} file(s)")
    print(
        f"{root} @ {head[:12]}: {len(texts)} editable files, "
        f"{sum(every.values())} warnings; {len(work)} findings not yet attempted "
        f"for {', '.join(rules)}"
    )
    waiting = {rule: n for rule, n in every.items() if rule not in rules}
    if waiting:
        print(
            "not attempted (their fix can change behaviour or spans files): "
            + ", ".join(f"{rule} {n}" for rule, n in sorted(waiting.items(), key=str))
        )
    if args.dry_run:
        for t in led.tasks(status="open")[: args.budget]:
            print(f"  would take task {t['task_id']} in {t['rel']}")
        for f in work[: args.budget]:
            print(f"  would propose: {f.rule} in {f.rel} ({len(f.warnings)})")
        return 0
    # Measured here, on master and before any model: whether the cloud may be
    # asked this hour or not, the scoreboard has its hour.
    led.record_measures(
        _slot(),
        head,
        completion_measures(root, texts, every, rules, python_checked=python_checked),
    )
    allowed, why = cloud_coding_allowed()
    if not allowed:
        print(
            f"refused by GAGOS's egress law: the '{TASK}' task may not go to the "
            f"cloud ({why}). Run with AIOS_ROUTER_CLOUD_TASKS including {TASK}."
        )
        return 2
    # Each finding is made ready here, one at a time and without a model:
    # what cannot be sent is recorded and costs nothing of the batch. The
    # operator's tasks come first (2026-11-03), oldest first.
    jobs = task_jobs(led, root, head, busy, notes, facts, args.budget)
    # A file a task takes this batch is the task's: a lint fix on it would be a
    # second proposal on the same base, and one of the two would go stale
    # (both reviewers of the tasks build, 2026-11-03).
    tasked = {
        rel
        for job in jobs
        for rel in ([part[0] for part in job[8]] if job[8] else [job[0].rel])
    }
    for f in work:
        if len(jobs) >= args.budget:
            break
        if f.rel in tasked:
            continue
        text = base_of(f)
        known = notes if is_python(f.rel) else facts
        common = dict(base_text=text, base_commit=head, facts=known)
        # D15: the finding's arm is fixed by its path, rule and base; the ON
        # arm's writer is shown the rule's playbook, the OFF arm's is not.
        arm = d15_arm(f.rel, f.rule, digest(text))
        active = led.playbook(f.rule)
        shown = active if arm == ARM_ON else []
        if len(text) > MAX_FILE_CHARS:
            led.record_proposal(
                f,
                **common,
                model=NO_MODEL,
                new_text=None,
                verdict=None,
                refusal=f"file is {len(text)} characters; the bound for a "
                f"whole-file proposal is {MAX_FILE_CHARS}",
            )
            continue
        # What the scrubbers would redact stays here, behind placeholders.
        try:
            masked, mapping = mask_lines(text, mask_redact)
        except MaskingFailed as exc:
            led.record_proposal(
                f,
                **common,
                model=NO_MODEL,
                new_text=None,
                verdict=None,
                refusal=str(exc),
            )
            print(f"  skipped {f.rel}: {exc}")
            continue
        refusals = [egress_redact(r) for r in led.refusal_reasons(f.rule)]
        if f.rule == MISSING_TEST:
            system = TESTER_SYSTEM
            prompt = first_test_prompt(
                f,
                masked,
                example=_example_test(texts, f.rel),
                prior_refusals=refusals,
                masked=bool(mapping),
                facts=known,
                playbook=shown,
            )
        else:
            system = proposer_system(f.rel)
            prompt = proposal_prompt(
                f,
                masked,
                prior_refusals=refusals,
                masked=bool(mapping),
                facts=known,
                playbook=shown,
            )
        common.update(
            arm=arm,
            playbook_seen=[e["entry_id"] for e in shown],
            playbook_active=len(active),
        )
        altered = would_be_altered(prompt, system)
        if altered:
            led.record_proposal(
                f,
                **common,
                model=NO_MODEL,
                new_text=None,
                verdict=None,
                refusal=altered,
            )
            print(f"  skipped {f.rel}: {altered}")
            continue
        jobs.append((f, text, masked, mapping, prompt, system, common, None, None))
    if args.model:
        roster, probe = (args.model,), None
    else:
        workforce = WORKFORCE
        if any(m in BEDROCK_WRITERS for m in workforce):
            from aios.core.bedrock import credentials_available

            # With no key, the Bedrock writers cannot be asked; the others can.
            if not credentials_available(args.region):
                print("  the Bedrock writers wait: no Bedrock key")
                workforce = tuple(m for m in workforce if m not in BEDROCK_WRITERS)
        # A writer whose last call its provider refused (AWS refused the
        # account on 2026-11-02; the operator's plan has usage limits) is given
        # one finding a batch, the longest refused first, until it answers: the
        # rest of the work goes to writers that answer.
        refused = led.refused_writers(workforce)
        # A writer at its plan's usage limit is not refused: each such writer
        # is tried on one finding a batch, so it rejoins when the limit lifts.
        resting = led.resting_writers(workforce)
        roster = tuple(m for m in workforce if m not in refused and m not in resting)
        probe = refused[0] if refused else None
        if refused:
            print(
                f"  their last call was refused: {', '.join(refused)}; "
                f"{probe} is tried on one finding"
            )
        if resting:
            print(
                f"  at a usage limit: {', '.join(resting)}; each is tried on one finding"
            )
    # Writers are compared within one rule, never across rules of different
    # difficulty (Codex's review of #580).
    by_rule: dict[str, list[int]] = {}
    for i, job in enumerate(jobs):
        by_rule.setdefault(job[0].rule, []).append(i)
    writers = [""] * len(jobs)
    for rule, idx in by_rule.items():
        for i, m in zip(idx, allocate(len(idx), led.model_outcomes(rule=rule), roster)):
            writers[i] = m
    if not args.model:
        tried = [probe] if probe else []
        tried += resting
        # A writer that may not answer never takes the last finding a writer
        # that answers could: found 2026-11-09, when one finding was left and
        # went to a refused Bedrock writer for seven runs in a row while the
        # plans' writers stood idle.
        spare = len(jobs) - 1 if roster else len(jobs)
        for k, writer in enumerate(tried[: max(0, spare)]):
            writers[len(jobs) - 1 - k] = writer
    elif probe and jobs:
        writers[-1] = probe
    # Not proposals: the findings no writer takes stay unattempted for a later
    # hour.
    capped = []
    for name, plan, cap in plan_shares():
        over = [i for i, m in enumerate(writers) if m in plan][cap:]
        for i in over:
            writers[i] = ""
        if over:
            print(
                f"  {len(over)} finding(s) wait for a later hour: the operator's "
                f"{name} plan takes {cap} a batch"
            )
        capped += over
    idle = writers.count("") - len(capped)
    if idle:
        print(f"  {idle} finding(s) wait for a later hour: no writer answers")
    jobs, writers = (
        [j for j, m in zip(jobs, writers) if m],
        [m for m in writers if m],
    )
    month, slot, lint = _month(), _slot(), threading.Lock()
    # Each job's files are claimed before any writer is asked, all of a job's
    # or none, durably and across processes: two batches running at once (an
    # hourly one and one started by hand) never write the same file
    # (Codex's design conditions, 2026-11-02; built 2026-11-10).
    holder = f"batch:{slot}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    claimed = [
        (job, model)
        for job, model in zip(jobs, writers)
        if led.claim_files(job_files(job), holder)
    ]
    if len(claimed) < len(jobs):
        print(
            f"  {len(jobs) - len(claimed)} finding(s) left alone: another batch "
            "has claimed their files"
        )
    jobs, writers = [j for j, _ in claimed], [m for _, m in claimed]
    completers = {m: governed_completer(m, args.region) for m in dict.fromkeys(writers)}

    def attempt(n: int, job: tuple, model: str) -> None:
        f, text, masked, mapping, prompt, system, common, task_id, parts = job
        common = dict(common, model=model)

        def took(pid: str) -> None:
            # A proposal with a model's answer takes the operator's task, passed
            # or refused by the checks; one for a failed call does not, so the
            # task is tried again next hour.
            if task_id:
                led.take_task(task_id, pid)

        chars_in = len(prompt) + len(system)
        # A call on the operator's plan costs nothing against the AWS ceiling;
        # it is still held and settled, so its request id is its own.
        on_aws = model not in PLAN_WRITERS
        hold = led.reserve_spend(
            month=month,
            model=model,
            purpose=f"propose {f.rule} in {f.rel}"
            + (f" and {len(parts) - 1} more" if parts else ""),
            usd=worst_case_usd(chars_in) if on_aws else 0.0,
            ceiling=MONTHLY_AWS_USD if on_aws else float("inf"),
        )
        if hold is None:
            # Not a proposal: the finding stays unattempted for a later month.
            print(
                f"  not asked: {f.rel} would pass this month's AWS ceiling "
                f"(${MONTHLY_AWS_USD:.0f}, the operator's)"
            )
            return
        started = time.monotonic()
        cloud_spend.forget_last_usage()
        try:
            raw = completers[model](prompt, system, f"gagos:{slot}:spend-{hold}")
        except (
            Exception
        ) as exc:  # the model or the gateway refused; recorded, never hidden
            led.settle_spend(
                hold,
                usd=estimate_usd(chars_in, 0) if on_aws else 0.0,
                chars_in=chars_in,
                chars_out=0,
            )
            pid = led.record_proposal(
                f,
                **common,
                new_text=None,
                verdict=None,
                refusal=f"model call failed: {type(exc).__name__}: {exc}"[:600],
            )
            print(f"  {pid} {f.rel} ({model}): model call failed: {exc}")
            return
        # What the provider reported the call used, where it reported it
        # (2026-11-10); the character estimate only where it did not.
        used = cloud_spend.last_usage()
        reported = used is not None and used.get("model") == model
        led.settle_spend(
            hold,
            usd=(
                (float(used["usd"]) if reported else estimate_usd(chars_in, len(raw)))
                if on_aws
                else 0.0
            ),
            chars_in=chars_in,
            chars_out=len(raw),
        )
        if parts:
            record_task_files(
                led, root, lint, job, model=model, raw=raw, took=took, started=started
            )
            return
        try:
            # A new test takes its module's line endings, and ends with one.
            shape = (
                text if f.rule != MISSING_TEST else ("\r\n" if "\r\n" in text else "\n")
            )
            why = no_edit_refusal(raw) if f.rule == TASK_RULE else None
            if why:
                raise ProposalRefused(why)
            answer = (
                parse_edits(raw, original=masked)
                if f.rule == TASK_RULE and is_edit_answer(raw)
                else parse_proposal(raw, original=shape)
            )
            new_text = unmask(
                answer, mapping, masked=masked, repeat=f.rule == MISSING_TEST
            )
        except ProposalRefused as exc:
            pid = led.record_proposal(
                f, **common, new_text=None, verdict=None, refusal=str(exc)
            )
            took(pid)
            print(f"  {pid} {f.rel} ({model}): refused: {exc}")
            return
        try:
            if is_python(f.rel):
                # The layout the required format gate accepts (2026-11-04).
                new_text = format_python_text(root, f.rel, new_text)
            # Both texts once more, each also with inline configuration off,
            # so what disable comments hide can be compared (static_verdict).
            check = check_python_texts if is_python(f.rel) else check_texts
            with lint:
                if f.rule == MISSING_TEST:
                    before = None
                else:
                    before = check(root, {f.rel: text}, inline_off=True)[f.rel]
                after = check(root, {f.rel: new_text}, inline_off=True)[f.rel]
        except StaticCheckUnavailable as exc:
            pid = led.record_proposal(
                f,
                **common,
                new_text=new_text,
                verdict=None,
                refusal=f"static checks unavailable: {exc}",
            )
            took(pid)
            print(f"  {pid} {f.rel} ({model}): {exc}")
            return
        if task_id:
            verdict = task_verdict(f.rel, text, new_text, before, after)
        elif before is None:
            verdict = first_test_verdict(f, new_text, after)
        else:
            verdict = static_verdict(f, text, new_text, before, after)
        if verdict.passed and is_python(f.rel):
            # Ruff sees one file; what other modules take from it is checked here.
            taken = import_refusal(root, f.rel, text, new_text)
            if taken:
                verdict = StaticVerdict(False, taken, verdict.changed_lines)
        pid = led.record_proposal(f, **common, new_text=new_text, verdict=verdict)
        took(pid)
        state = (
            "PASSED static checks" if verdict.passed else f"REFUSED: {verdict.reason}"
        )
        print(
            f"  {pid} {f.rule} in {f.rel} ({model}): {state} "
            f"({verdict.changed_lines} lines, {time.monotonic() - started:.0f}s)"
        )

    if jobs:
        print(
            f"  {len(jobs)} finding(s) to {len(set(writers))} writer(s): "
            + ", ".join(f"{m} {writers.count(m)}" for m in dict.fromkeys(writers))
        )
    # Each writer is a worker the Worker Foundry admits (the consistency plan's
    # "one engine for work", 2026-11-10): the operator's emergency stop at
    # admission, WRITERS_AT_ONCE at a time, its lifecycle on the cortex bus.
    try:
        outcomes = writers_foundry().run_batch(
            f"gagos-{slot}",
            [
                WriterLeg(
                    model,
                    tuple(job_files(job)),
                    functools.partial(attempt, n, job, model),
                )
                for n, (job, model) in enumerate(zip(jobs, writers), 1)
            ],
        )
    finally:
        led.release_claims(holder)
    stopped = [o for o in outcomes if isinstance(o, EmergencyStopError)]
    if stopped:
        print(
            f"  {len(stopped)} writer(s) not admitted: {stopped[0]}; their findings "
            "stay for a later hour"
        )
    failed = [o for o in outcomes if o is not None and o not in stopped]
    if failed:
        raise failed[0]
    return 0


def _example_test(texts: dict[str, str], test_rel: str) -> str | None:
    """The shortest existing test beside *test_rel*, for the writer to follow
    this codebase's conventions; only one with nothing to mask, so no other
    file's placeholders reach the answer."""
    folder = str(Path(test_rel).parent.as_posix())
    near = sorted(
        (len(text), rel)
        for rel, text in texts.items()
        if Path(rel).parent.as_posix() == folder
        and (".test." in Path(rel).name or ".spec." in Path(rel).name)
        and len(text) <= MAX_EXAMPLE_CHARS
    )
    for _size, rel in near:
        try:
            masked, mapping = mask_lines(texts[rel], mask_redact)
        except MaskingFailed:
            continue
        if not mapping:
            return masked
    return None


# --------------------------------------------------------------------- review


class ReviewUnavailable(RuntimeError):
    """The reviewer did not return a verdict; the proposal stays open."""


def _schema_file(tmp: str) -> Path:
    path = Path(tmp, "verdict.schema.json")
    path.write_text(json.dumps(REVIEW_SCHEMA), encoding="utf-8")
    return path


def codex_settings() -> dict[str, str]:
    """The operator's chosen Codex model and effort, read from his config, so a
    reviewer that ignores the rest of that config (its MCP servers) still runs
    on his model."""
    import tomllib

    path = Path.home() / ".codex" / "config.toml"
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        key: str(raw[key])
        for key in ("model", "model_reasoning_effort")
        if isinstance(raw.get(key), str)
    }


def run_codex(
    prompt: str, *, model: str | None, timeout_s: float
) -> tuple[str, str, str]:
    # The plan client's lookup: a .cmd shim is refused, since cmd.exe would
    # re-read its arguments (2026-11-04: this used shutil.which alone).
    codex = _codex_executable()
    if codex is None:
        raise ReviewUnavailable(
            "the Codex CLI is not installed (a .cmd shim is refused)"
        )
    settings = codex_settings()
    model = model or settings.get("model")
    with tempfile.TemporaryDirectory(prefix="gagos-review-") as tmp:
        out = Path(tmp, "verdict.json")
        argv = [
            codex,
            *CODEX_SEALED,
            "--output-schema",
            str(_schema_file(tmp)),
            "-o",
            str(out),
        ]
        if model:
            argv += ["-m", model]
        if settings.get("model_reasoning_effort"):
            argv += [
                "-c",
                f"model_reasoning_effort={settings['model_reasoning_effort']}",
            ]
        try:
            proc = subprocess.run(
                [*argv, "-"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=tmp,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise ReviewUnavailable(f"Codex timed out after {timeout_s}s") from exc
        log = (proc.stdout or "") + (proc.stderr or "")
        used = re.search(r"^model: (\S+)", log, re.MULTILINE)
        if (
            proc.returncode != 0
            or not out.is_file()
            or not out.read_text(encoding="utf-8").strip()
        ):
            errors = [
                line
                for line in log.splitlines()
                if "ERROR" in line and "rmcp::transport" not in line
            ]
            raise ReviewUnavailable(
                (errors[-1] if errors else f"Codex exited {proc.returncode}")[:400]
            )
        verdict, reason = parse_review(out.read_text(encoding="utf-8"))
        return (
            verdict,
            reason,
            used.group(1) if used else (model or "codex (configured)"),
        )


def run_claude(
    prompt: str, *, model: str | None, timeout_s: float
) -> tuple[str, str, str]:
    claude = _claude_executable()
    if claude is None:
        raise ReviewUnavailable("the Claude Code CLI is not installed")
    argv = [claude, *CLAUDE_SEALED, "--json-schema", json.dumps(REVIEW_SCHEMA)]
    if model:
        argv += ["--model", model]
    with tempfile.TemporaryDirectory(prefix="gagos-review-") as tmp:
        try:
            proc = subprocess.run(
                argv,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=tmp,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise ReviewUnavailable(
                f"Claude Code timed out after {timeout_s}s"
            ) from exc
    # A failed process gives no verdict, whatever it printed (Codex's
    # post-merge review of #566); the proposal keeps waiting for Claude.
    if proc.returncode != 0:
        raise ReviewUnavailable(
            f"Claude Code exited {proc.returncode}: {(proc.stderr or '')[-300:]}"
        )
    try:
        data = json.loads(proc.stdout or "")
    except ValueError as exc:
        raise ReviewUnavailable(
            f"Claude Code exited {proc.returncode}: {(proc.stderr or '')[-300:]}"
        ) from exc
    if data.get("is_error") or data.get("structured_output") is None:
        raise ReviewUnavailable(
            f"Claude Code returned no verdict: {str(data.get('result'))[:300]}"
        )
    verdict, reason = parse_review(data["structured_output"])
    used = ",".join(data.get("modelUsage") or {}) or model or "claude (configured)"
    return verdict, reason, used


REVIEWER_RUNNERS = {"codex": run_codex, "claude": run_claude}


def _mask_floor(mapping: dict[str, str], floor: int) -> int:
    """The prefix width the next file's mask starts at, after one that used
    *mapping*: each file of a task masks under a prefix of its own."""
    return next(iter(mapping))[:-4].count("Q") + 1 if mapping else floor


def _group_evidence(p: dict, facts: list) -> tuple[str, bool, bool]:
    """The review prompt of a task over several files: the task and every
    changed file's masked original and diff, each file under a mask of its own
    and masked like a single file's (what the writer added too). Returns
    ``(prompt, some span hidden, some added span hidden)``."""
    led = ledger()
    task = led.task(p["group_id"])
    if task is None:
        raise MaskingFailed(f"{UNSHOWABLE}: the task of this proposal is unknown")
    parts, floor, hidden, hid_added = [], 1, False, False
    for m in led.group_members(p["group_id"]):
        masked_base, mapping = mask_lines(m["base_text"], mask_redact, min_width=floor)
        floor = _mask_floor(mapping, floor)
        masked_new = mask_aligned(m["new_text"], m["base_text"], masked_base, mapping)
        masked_new, added = mask_lines(masked_new, mask_redact, min_width=floor)
        floor = _mask_floor(added, floor)
        diff = unified_diff(Path(m["rel"]).name, masked_base, masked_new)
        parts.append((m["rel"], masked_base, diff))
        hidden, hid_added = hidden or bool(mapping), hid_added or bool(added)
    prompt = task_files_review_prompt(egress_redact(task["text"]), parts, facts=facts)
    return prompt, hidden, hid_added


def review_evidence(p: dict, finding: Finding) -> str:
    """The review prompt, under the same mask as the proposer's (Codex's review
    of #566: reviews sent the unmasked file and diff to two cloud models).
    Raises ``MaskingFailed`` when the change cannot be shown without exposing
    what may not leave the machine. A proposal of a task over several files is
    shown with the whole task: one review is of the group, never of a member."""
    facts = json.loads(p.get("facts") or "[]")
    if p.get("group_id"):
        # Every member's facts, in order, once each.
        for m in ledger().group_members(p["group_id"]):
            facts += [f for f in json.loads(m.get("facts") or "[]") if f not in facts]
        prompt, mapping, added = _group_evidence(p, facts)
        return _review_notes(prompt, p, mapping, added)
    masked_base, mapping = mask_lines(p["base_text"], mask_redact)
    if finding.rule == MISSING_TEST:
        # The module and the whole new test, under the module's mask.
        masked_new = mask_like(p["new_text"], mapping)
    else:
        # Kept lines exactly as in the masked original, so the diff shows
        # only what the proposal changed.
        masked_new = mask_aligned(p["new_text"], p["base_text"], masked_base, mapping)
    # What the writer added that the scrubbers would redact is hidden too, behind
    # placeholders of its own (2026-11-03: three new test files by Sonnet and
    # Haiku could not be shown, for a relative import, a regex the filter took
    # for a path, and a fixed test UUID, none of them in the module). Under a
    # prefix of their own: with the module's, the first added span took the
    # module's GAGOSMASKQ_0000, one placeholder for two values, and on
    # 2026-11-13 a correct first test (gd-f98e938baf) was rejected for
    # importing what the reviewer read as the name in the module's comment.
    masked_new, added = mask_lines(
        masked_new, mask_redact, min_width=_mask_floor(mapping, 1)
    )
    if finding.rule == MISSING_TEST:
        prompt = first_test_review_prompt(finding, masked_base, masked_new, facts=facts)
    elif finding.rule == TASK_RULE:
        # The reviewer is shown the operator's task, scrubbed, in place of a
        # rule and its warnings.
        task = ledger().task_of_proposal(p["proposal_id"])
        if task is None:
            raise MaskingFailed(f"{UNSHOWABLE}: the task of this proposal is unknown")
        diff = unified_diff(Path(finding.rel).name, masked_base, masked_new)
        prompt = task_review_prompt(
            finding.rel, egress_redact(task["text"]), masked_base, diff, facts=facts
        )
    else:
        # The file's name, never its path: paths do not leave the machine.
        diff = unified_diff(Path(finding.rel).name, masked_base, masked_new)
        prompt = review_prompt(finding, masked_base, diff, facts=facts)
    return _review_notes(prompt, p, mapping, added)


def _review_notes(prompt: str, p: dict, mapping, added) -> str:
    """What every review prompt ends with: how the placeholders read, the
    sandbox's report, and the last check that nothing would be altered."""
    if mapping or added:
        prompt += (
            "\n\nSome spans are shown as placeholders (GAGOSMASK...): they hide "
            "paths or values that may not leave this machine. Judge the change "
            "around them; a placeholder is the same text before and after."
        )
    if added:
        prompt += (
            " A placeholder that appears only in the change hides something the "
            "writer added (a path, a long name, an id); judge the code around it."
        )
    if p.get("sandbox"):
        # GAGOS's own report of its tests, scrubbed like everything else that
        # leaves the machine (2026-11-03: the privacy filter took the test name
        # `test_get_executor_and_rollback_engine_return_real_instances` for
        # something sensitive, and two correct changes could not be shown).
        prompt += "\n\n" + egress_redact(
            SandboxVerdict.from_json(p["sandbox"]).for_reviewer()
        )
    if p.get("prescreen"):
        word = json.loads(p["prescreen"])
        prompt += "\n\n" + egress_redact(
            "The council's Critique queen, a deterministic check of whether the "
            "tests' pass was earned (advisory; it decides nothing), says "
            f"{word.get('verdict')}: {word.get('reason')}"
        )
    altered = would_be_altered(prompt, "")
    if altered:
        raise MaskingFailed(f"{UNSHOWABLE}: {altered}")
    return prompt


def whole_tasks(led: DailyLedger, rows: list[dict]) -> list[list[dict]]:
    """*rows* as the units the work goes by: a proposal of a task over several
    files stands for its whole group (every member, in order), once; any other
    is a unit of its own. A group is tested and reviewed once, never by member."""
    units: list[list[dict]] = []
    seen: set[str] = set()
    for p in rows:
        gid = p.get("group_id")
        if not gid:
            units.append([p])
        elif gid not in seen:
            seen.add(gid)
            units.append(led.group_members(gid))
    return units


def awaits_tests(p: dict) -> bool:
    """A behaviour-changing fix whose tests have not yet run and passed."""
    if p["rule"] not in BEHAVIOUR_RULES:
        return False
    if not p.get("sandbox"):
        return True
    return SandboxVerdict.from_json(p["sandbox"]).outcome != PASSED


def cmd_review(args: argparse.Namespace) -> int:
    led = ledger()
    again = set(getattr(args, "again", None) or ())
    # A task over several files is reviewed again whole.
    every = {p["proposal_id"]: p for p in led.proposals()}
    for pid in sorted(again):
        gid = (every.get(pid) or {}).get("group_id")
        if gid:
            again |= {m["proposal_id"] for m in led.group_members(gid)}
    for pid in sorted(again):
        if led.reopen(pid):
            print(f"  {pid}: reopened; it was refused only for how it was shown")
    if again:
        # A verdict given on wrong evidence is given again, by a fresh session
        # on the evidence as it is shown now; the new verdict replaces it.
        pending = [
            p
            for p in led.proposals()
            if p["proposal_id"] in again
            and p["status"] in ("proposed", "accepted", "rejected")
        ]
    else:
        # A fix that can change behaviour is read only after its tests ran in
        # the sandbox and passed (2026-11-04).
        pending = [p for p in led.awaiting(args.reviewer) if not awaits_tests(p)]
    units = whole_tasks(led, pending)
    if not again:
        units = units[: args.limit]
    if not units:
        print(f"nothing awaits {args.reviewer}")
        return 0
    # Both reviewers are cloud models: GAGOS's egress law decides, as for the
    # proposer. Revoked, the reviews wait.
    allowed, why = cloud_coding_allowed()
    if not allowed:
        print(f"reviews wait: the '{TASK}' task may not go to the cloud ({why})")
        return 2
    unavailable = 0
    live = ("proposed", "accepted", "rejected")
    for unit in units:
        p = unit[0]
        ids = ", ".join(m["proposal_id"] for m in unit)
        files = ", ".join(m["rel"] for m in unit)
        gone = [m for m in unit if m["status"] not in live]
        if gone:
            # All or nothing: a group with a member out of the work is out.
            for m in unit:
                if m["status"] in live:
                    led.refuse(
                        m["proposal_id"],
                        f"{gone[0]['rel']} of the same task was refused; a task over "
                        "several files is all or nothing",
                    )
            print(f"  {ids}: refused with {gone[0]['rel']}, its task's other file")
            continue
        finding = Finding(
            rel=p["rel"],
            rule=p["rule"],
            warnings=tuple(tuple(w) for w in json.loads(p["warnings"])),
        )
        try:
            prompt = review_evidence(p, finding)
        except MaskingFailed as exc:
            for m in unit:
                led.refuse(m["proposal_id"], str(exc))
            print(f"  {ids}: refused: {exc}")
            continue
        try:
            verdict, reason, model = REVIEWER_RUNNERS[args.reviewer](
                prompt, model=args.model, timeout_s=args.timeout
            )
        except (ReviewUnavailable, ValueError) as exc:
            unavailable += 1
            print(f"  {ids}: {args.reviewer} gave no verdict: {exc}")
            continue
        # One verdict for the whole task, recorded on every file of it.
        for m in unit:
            status = led.record_review(
                m["proposal_id"],
                args.reviewer,
                model=model,
                verdict=verdict,
                reason=reason,
            )
        print(
            f"  {ids} {files}: {args.reviewer} ({model}) {verdict.upper()}: {reason} -> {status}"
        )
    return 1 if unavailable else 0


# --------------------------------------------------------------------- test


def cmd_test(args: argparse.Namespace) -> int:
    """Each proposal awaiting review has its tests run in the sandbox, judged
    against its base, before any reviewer reads it (the operator, 2026-11-03:
    "Yes honestly"). One at a time: each container takes two CPUs and 2 GiB. A
    task over several files is tested once, all its changes in place together,
    and the verdict is recorded on every file of it. Every change goes through
    :func:`run_change_tests`, which says why when it cannot run (the frontend
    has no sandbox yet)."""
    root = Path(args.project).resolve()
    led = ledger()
    again = set(getattr(args, "again", None) or ())
    pending = (
        [p for p in led.proposals(status="proposed") if p["proposal_id"] in again]
        if again
        else led.awaiting_tests()
    )
    if not pending:
        print("no proposal awaits its tests")
        return 0
    with BaseTrees(root) as trees:
        for unit in whole_tasks(led, pending):
            # Those still awaiting review: a member already out of the work
            # leaves the group's tests with nothing to judge.
            unit = [m for m in unit if m["status"] == "proposed"]
            if not unit:
                continue
            p = unit[0]
            verdict = run_change_tests(
                trees,
                base_commit=p["base_commit"],
                changes={m["rel"]: m["new_text"] for m in unit},
            )
            refusal = verdict.refusal
            if (
                refusal is None
                and verdict.outcome != PASSED
                and any(m["rule"] in BEHAVIOUR_RULES for m in unit)
            ):
                # A fix that can change behaviour reaches review only with
                # tests that ran and passed (2026-11-04, GAGOS completing
                # itself). The sandbox not running is not its fault: it waits.
                if verdict.outcome == UNAVAILABLE:
                    print(
                        f"  {', '.join(m['proposal_id'] for m in unit)}: waits, "
                        f"its tests could not run: {verdict.summary}"
                    )
                    continue
                refusal = f"{UNTESTED_BEHAVIOUR}: {verdict.summary}"
            for m in unit:
                led.record_sandbox(m["proposal_id"], verdict.to_json(), refusal=refusal)
            print(
                f"  {', '.join(m['proposal_id'] for m in unit)} "
                f"{', '.join(m['rel'] for m in unit)}: tests "
                f"{verdict.outcome.upper()}: {verdict.summary} "
                f"({verdict.seconds:.0f}s)"
            )
            if refusal is None:
                word = council_prescreen(unit, verdict)
                for m in unit:
                    led.record_prescreen(m["proposal_id"], json.dumps(word))
                print(f"    the council's Critique queen (advisory): {word['verdict']}")
    return 0


def council_prescreen(unit: list[dict], verdict: SandboxVerdict) -> dict[str, str]:
    """The council's Critique queen on a proposal's tests, before any reviewer
    reads it (Codex's design conditions, 2026-11-02: a council pre-screen,
    advisory; built 2026-11-10). Deterministic, no model, nothing leaves the
    machine: was the pass earned -- did a test runner assert behaviour, and did
    what ran exercise the change? Its word is in the review vocabulary
    (aios/domain/reviews.py) and is shown to the reviewer and the operator; it
    decides nothing."""
    from aios.council.queens.critique import CritiqueQueen
    from aios.runtime.contracts import MissionContract, QueenVerdict

    rels = [m["rel"] for m in unit]
    ran = verdict.outcome == PASSED and bool(verdict.tests)
    testing = QueenVerdict(
        queen="testing",
        verdict="allow",
        risk="GREEN" if ran else "YELLOW",
        reason=verdict.summary,
        metadata={"verification_strength": "STRONG" if ran else "NONE"},
    )
    contract = MissionContract(
        mission_id=f"gagos-{unit[0]['proposal_id']}",
        goal="a proposal of GAGOS's workshop",
        worker_type="code",
        created_by="gagos",
        workspace_root=".",
        allowed_files=rels,
        # What ran, and why it was chosen: the sandbox runs the tests that
        # import the changed files (and a new test, itself).
        verification_commands=(
            [f"the tests that exercise {', '.join(rels)}: " + ", ".join(verdict.tests)]
            if ran
            else []
        ),
    )
    word, reason = queen_review(
        CritiqueQueen().review(contract=contract, testing_verdict=testing)
    )
    return {"queen": "critique", "verdict": word, "reason": reason}


# --------------------------------------------------------------------- deliver


#: GAGOS's own work is committed as GAGOS: it proposed it. Its reviewers are
#: named in the message, never as authors (operator, 2026-10-30: "GAGOS only
#: make its own PR for its own work, u and codex are reviewer and u r chief").
#: With its GitHub App stored, GAGOS commits and opens PRs as the App's bot.
GAGOS_IDENTITY = ("GAGOS", "gagos@localhost")
REVIEWER_LABELS = {"claude": "Claude Code, chief reviewer", "codex": "Codex"}
#: The chief first, wherever reviews are listed.
REVIEW_ORDER = ("claude", "codex")
#: The frontier models are credited by name for what they wrote and judged
#: (operator, 2026-10-30: "give frontier models their credit").
MODEL_NAMES = {
    "mistral.mistral-large-3-675b-instruct": "Mistral Large 3 (Mistral AI, on Amazon Bedrock)",
    "mistral.devstral-2-123b": "Devstral 2 (Mistral AI, on Amazon Bedrock)",
    "deepseek.v3.2": "DeepSeek V3.2 (DeepSeek, on Amazon Bedrock)",
    "qwen.qwen3-coder-next": "Qwen3 Coder Next (Qwen, on Amazon Bedrock)",
    "moonshotai.kimi-k2.5": "Kimi K2.5 (Moonshot AI, on Amazon Bedrock)",
    "us.anthropic.claude-sonnet-4-6": "Claude Sonnet 4.6 (Anthropic, on Amazon Bedrock)",
    "gpt-6.1-sol": "GPT-6.1 sol (OpenAI, via Codex)",
    "claude-opus-5-5": "Claude Opus 5.5 (Anthropic, via Claude Code)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 (Anthropic, via Claude Code)",
    "claude-haiku-5-5": "Claude Haiku 5.5 (Anthropic, via Claude Code)",
    "gpt-6.1-terra": "GPT-6.1 terra (OpenAI, via Codex)",
    "gpt-6-luna": "GPT-6 luna (OpenAI, via Codex)",
}


def model_name(model_id: str | None) -> str:
    return MODEL_NAMES.get(model_id or "", model_id or "unknown model")


def credit_email(model_id: str) -> str:
    """A credit address that is plainly not a person's or a company's inbox."""
    slug = re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")
    return f"{slug}@models.invalid"


PR_FOOTER_NO_APP = (
    "Opened by GAGOS's delivery step. GAGOS has no GitHub identity of its own "
    "yet, so GitHub shows the operator's account as the opener; every commit "
    "here is authored by GAGOS. Every change here was accepted by its "
    "reviewer, Claude Code. The operator merges."
)
#: Accurate about merging (Codex's post-merge review of #566): GitHub would let
#: the App's token merge a PR whose checks pass; that GAGOS never merges is a
#: rule of its code, not a GitHub restriction.
PR_FOOTER_APP = (
    "Opened by GAGOS itself, through its own GitHub App. GAGOS pushes its "
    "branch and opens the PR; it has no code that merges, and only the "
    "operator merges (GitHub itself would allow the App to merge once the "
    "checks pass: that is a rule GAGOS keeps, not a lock). Every change here "
    "was accepted by its reviewer, Claude Code."
)
#: Kept for callers of the first version.
PR_FOOTER = PR_FOOTER_NO_APP


def commit_message(
    p: dict,
    reviews: dict,
    *,
    moot: str | None = None,
    task: dict | None = None,
    group: list[dict] | None = None,
) -> str:
    """GAGOS's commit for one delivered change: what it did, how it was
    checked, who reviewed it, and the frontier model credited as co-author.
    *moot*: the delivery check that fails on master without the change too.
    *task*: the operator's task, for a proposal made for one. *group*: every
    proposal of a task over several files, delivered as the one commit this
    message is, which names every file."""
    warnings = json.loads(p["warnings"])
    sandbox = SandboxVerdict.from_json(p["sandbox"]) if p.get("sandbox") else None
    tested = (
        [f"Before review, its tests ran in the sandbox: {sandbox.summary}."]
        if sandbox is not None and sandbox.outcome == PASSED
        else []
    )
    checked = (
        "it compiles, and the tests that import it pass."
        if is_python(p["rel"])
        else "it parses, has no ESLint error, and the tests that import it pass."
    )
    if group:
        kinds = {is_python(m["rel"]) for m in group}
        checked = (
            "they compile, and the tests that import them pass."
            if kinds == {True}
            else "they parse, have no ESLint error, and the tests that import "
            "them pass."
            if kinds == {False}
            else "the Python files compile, the frontend files parse and have no "
            "ESLint error, and the tests that import them pass."
        )
    if moot:
        it = "them" if group else "it"
        checked = (
            f"this check fails on master without {it} too ({moot}), so it says "
            f"nothing about {it}; CI judges it."
        )
    if p["rule"] == MISSING_TEST:
        head = [
            f"GAGOS: a first test for {subject_of(p['rel'])}",
            "",
            f"GAGOS found that this module had no test and wrote one (proposal "
            f"{p['proposal_id']}); {model_name(p['model'])} wrote it. Unattended "
            "checks passed: it parses, has no ESLint message, imports its module "
            "and reaches nothing outside itself. Checked on master: it parses, has "
            "no ESLint error, and it passes.",
        ]
    elif p["rule"] == TASK_RULE and group:
        n_files = f"{len(group)} file{'s' if len(group) > 1 else ''}"
        said = egress_redact((task or {}).get("text", "").strip())
        first = (said.splitlines() or [""])[0]
        title = first if len(first) <= 60 else first[:57].rstrip() + "..."
        head = [
            f"GAGOS: the operator's task in {n_files}: {title}",
            "",
            f"The operator wrote this task in plain words (task "
            f"{(task or {}).get('task_id', 'unknown')}): {first}",
            f"GAGOS proposed this change over {n_files} (proposals "
            f"{', '.join(m['proposal_id'] for m in group)}); "
            f"{model_name(p['model'])} wrote it. Unattended checks passed: each "
            "file parses and adds no lint message. Checked again on master, all "
            "together: " + checked,
            "",
            "Files:",
            *(f"  - {m['rel']}" for m in group),
        ]
    elif p["rule"] == TASK_RULE:
        # His words, scrubbed like everything else that leaves the machine.
        said = egress_redact((task or {}).get("text", "").strip())
        first = (said.splitlines() or [""])[0]
        title = first if len(first) <= 60 else first[:57].rstrip() + "..."
        head = [
            f"GAGOS: the operator's task in {p['rel']}: {title}",
            "",
            f"The operator wrote this task in plain words (task "
            f"{(task or {}).get('task_id', 'unknown')}): {first}",
            f"GAGOS proposed this change (proposal {p['proposal_id']}); "
            f"{model_name(p['model'])} wrote it. Unattended checks passed: it "
            "parses and adds no lint message. Checked again on master: " + checked,
        ]
    else:
        head = [
            f"GAGOS: fix {p['rule']} in {p['rel']}",
            "",
            f"GAGOS found {len(warnings)} {p['rule']} warning(s) in this file and "
            f"proposed this change (proposal {p['proposal_id']}); "
            f"{model_name(p['model'])} wrote it. Unattended checks passed: it "
            "parses, the warnings are gone, nothing new. Checked again on master: "
            + checked,
        ]
    return "\n".join(
        [
            *head,
            *([""] + tested if tested else []),
            "",
            "",
            *(
                f"{REVIEWER_LABELS[r]}, {model_name(reviews[r]['model'])}, accepted: "
                f"{reviews[r]['reason']}"
                for r in REVIEW_ORDER
                if r in reviews
            ),
            "",
            "Proposed-by: GAGOS",
            f"Co-authored-by: {model_name(p['model'])} <{credit_email(p['model'])}>",
            *(
                f"Reviewed-by: {REVIEWER_LABELS[r]}, {model_name(reviews[r]['model'])}"
                for r in REVIEW_ORDER
                if r in reviews
            ),
        ]
    )


def _owner_repo(root: Path) -> tuple[str, str]:
    url = _git(root, "remote", "get-url", "origin")
    path = url.split("github.com", 1)[1].lstrip(":/").removesuffix(".git")
    owner, repo = path.split("/")[:2]
    return owner, repo


class PublishFailed(RuntimeError):
    """The branch could not be pushed or its PR not opened; the work stays
    committed and the next day retries before anything new is proposed."""


def _github_app(root: Path):
    """``(token, (name, email), owner, repo)`` when GAGOS's App is stored and
    installed here; None when no App is stored: then GAGOS uses the
    operator's ``gh`` login (authorised before the App existed) and its PR
    says so. A stored App that cannot act, a partly stored one, or a store
    that cannot be read raises ``PublishFailed``: a broken identity never
    quietly becomes the operator's (Codex's reviews of #566 and #567)."""
    from aios.operations import github_app as gha
    from aios.operations.keystore import default_keystore

    try:
        store = default_keystore()
        creds = gha.stored_credentials(store)
        partly = creds is None and gha.stored_any(store)
    except Exception as exc:  # noqa: BLE001 - an unreadable store is not "no App"
        raise PublishFailed(
            f"GAGOS's key store cannot be read: {type(exc).__name__}: {exc}"[:300]
        ) from exc
    if partly:
        raise PublishFailed(
            "GAGOS's App is only partly stored (its id, slug and key must all be there)"
        )
    if creds is None:
        return None
    owner, repo = _owner_repo(root)
    try:
        token = gha.installation_token(creds, owner=owner, repo=repo)
        identity = gha.bot_identity(creds)
    except Exception as exc:  # noqa: BLE001 - any failure is a broken identity
        raise PublishFailed(
            f"GAGOS's App cannot act here: {type(exc).__name__}: {exc}"[:300]
        ) from exc
    return token, identity, owner, repo


def _branch_prs(root: Path, branch: str, app) -> list[dict]:
    """Every PR GitHub has for *branch*, in any state, each as ``{url, state,
    head}`` (state OPEN, CLOSED or MERGED; head the commit it holds)."""
    if app:
        import httpx

        token, _identity, owner, repo = app
        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            params={"head": f"{owner}:{branch}", "state": "all"},
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        )
        if response.status_code >= 300:
            raise PublishFailed(f"cannot list PRs: {response.status_code}")
        return [
            {
                "url": str(pr["html_url"]),
                "state": "MERGED"
                if pr.get("merged_at")
                else str(pr.get("state", "")).upper(),
                "head": str(pr["head"]["sha"]),
            }
            for pr in response.json()
        ]
    proc = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "url,state,headRefOid",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise PublishFailed(f"cannot list PRs: {(proc.stderr or '').strip()[:200]}")
    try:
        found = json.loads(proc.stdout or "[]")
        return [
            {
                "url": str(pr["url"]),
                "state": str(pr["state"]),
                "head": str(pr["headRefOid"]),
            }
            for pr in found
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise PublishFailed(f"cannot read the PR list: {exc}") from exc


#: GitHub refuses a PR body over 65,536 characters (measured 2026-11-11: three
#: hours of accepted work could not be published); this leaves room.
PR_BODY_LIMIT = 60_000


def aliveness_lines() -> list[str]:
    """The aliveness pulse's report lines (aios.application.observability
    .aliveness), measured now on GAGOS's data; none, said, when it cannot be."""
    try:
        from aios.application.observability import aliveness

        return aliveness.report_lines(aliveness.pulse(Path(config.DATA_DIR)))
    except Exception as exc:  # the report goes out without it, saying why
        return [f"**Aliveness**: not measured ({type(exc).__name__}: {exc})"[:300], ""]


def pr_body(led: DailyLedger, ids: list[str], footer: str) -> str:
    """The PR's body: the day's whole report while it fits GitHub's limit;
    else this PR's own proposals in full and the day's others counted; cut at
    the limit, saying so, only if even that is too long."""
    day = _today()
    alive = aliveness_lines()
    body = report(
        led, day=day, in_pr=ids, footer=footer, scrub=egress_redact, aliveness=alive
    )
    if len(body) <= PR_BODY_LIMIT:
        return body
    body = report(
        led,
        day=day,
        in_pr=ids,
        footer=footer,
        scrub=egress_redact,
        only=ids,
        aliveness=alive,
    )
    if len(body) <= PR_BODY_LIMIT:
        return body
    cut = (
        "\n\n(cut here at GitHub's limit for a PR body; the full report is "
        f"`reports/{day}.md` in GAGOS's data on the operator's laptop)\n\n"
    )
    keep = PR_BODY_LIMIT - len(cut) - len(footer)
    return body[:keep] + cut + footer


def publish(
    led: DailyLedger,
    root: Path,
    branch: str,
    ids: list[str],
    app,
    *,
    pr_footer: str = "",
) -> str:
    """Push the exact commit that holds *ids* and open its PR, or find the PR
    that already holds that commit. Only then are they delivered (Codex's
    review of #566).

    Bound to the commit, not the branch (Codex's post-merge review of #566):
    a PR on the branch at another commit, such as an earlier delivery's that
    was merged or closed, never absorbs new work; the work stays committed
    and the day waits."""
    head = led.commit_of(ids[-1])
    if not head:
        raise PublishFailed(f"no commit is recorded for {ids[-1]}")
    prs = _branch_prs(root, branch, app)
    holding = [pr for pr in prs if pr["head"] == head]
    if holding:
        # Created before its response was lost (or merged since): found,
        # never opened twice.
        led.set_pr(ids, holding[0]["url"])
        return holding[0]["url"]
    if prs:
        raise PublishFailed(
            f"{branch} already has a PR at another commit ({prs[0]['url']}, "
            f"{prs[0]['state']}); {head[:12]} is not in it"
        )
    # The exact commit is pushed: a push that succeeds means GitHub's branch
    # now holds it, and a branch that moved elsewhere refuses (no force).
    refspec = f"{head}:refs/heads/{branch}"
    title = (
        f"GAGOS: daily improvements {_today()} "
        f"({len({led.commit_of(i) for i in ids})} change(s), "
        "each accepted by its reviewer)"
    )
    footer = pr_footer or (PR_FOOTER_APP if app else PR_FOOTER_NO_APP)
    body = pr_body(led, ids, footer)
    try:
        if app:
            from aios.operations import github_app as gha

            token, _identity, owner, repo = app
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "push",
                    "-q",
                    f"https://github.com/{owner}/{repo}.git",
                    refspec,
                ],
                env={**os.environ, **gha.git_auth_env(token)},
                check=True,
                capture_output=True,
                text=True,
            )
            url = gha.open_pull_request(
                token,
                owner=owner,
                repo=repo,
                head=branch,
                base="master",
                title=title,
                body=body,
            )
        else:
            _git(root, "push", "-q", "origin", refspec)
            with tempfile.NamedTemporaryFile(
                "w", suffix=".md", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(body)
            try:
                url = (
                    subprocess.run(
                        [
                            "gh",
                            "pr",
                            "create",
                            "--base",
                            "master",
                            "--head",
                            branch,
                            "--title",
                            title,
                            "--body-file",
                            fh.name,
                        ],
                        cwd=str(root),
                        capture_output=True,
                        text=True,
                        check=True,
                        encoding="utf-8",
                    )
                    .stdout.strip()
                    .splitlines()[-1]
                )
            finally:
                os.unlink(fh.name)
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        raise PublishFailed(f"{type(exc).__name__}: {exc}"[:300]) from exc
    led.set_pr(ids, url)
    return url


def delivery_branch(led: DailyLedger) -> str:
    """Today's branch, or a fresh one when a delivery already committed to it
    today: a branch whose PR may be merged or closed never takes later work
    (Codex's post-merge review of #566). Only one PR is open at a time; the
    day blocks while one is."""
    base = f"gagos/daily-{_today()}"
    used = led.delivery_branches()
    if base not in used:
        return base
    n = 2
    while f"{base}-{n}" in used:
        n += 1
    return f"{base}-{n}"


def publish_pending(led: DailyLedger, root: Path) -> str | None:
    """Publish what an earlier day committed but could not publish. Returns
    why the day must wait, or None when nothing is left unpublished."""
    pending = led.pending_publication()
    if not pending:
        return None
    try:
        app = _github_app(root)
    except PublishFailed as exc:
        return f"GAGOS's committed work is not published yet: {exc}"
    for branch, ids in pending.items():
        try:
            url = publish(led, root, branch, ids, app)
            print(f"published {branch}: {url}")
        except PublishFailed as exc:
            return f"GAGOS's committed work on {branch} is not published yet: {exc}"
    return None


def cmd_deliver(args: argparse.Namespace) -> int:
    """Apply what reviewers accepted to a daily branch, each change checked
    there and committed. A task over several files is one change: delivered only
    when every file of it is accepted, applied together, checked together, ONE
    commit naming every file; stale, or failed, together."""
    from aios.application.promotion.smoke import (
        SmokeStep,
        frontend_smoke,
        python_smoke,
    )

    root = Path(args.worktree).resolve()
    led = ledger()
    accepted = led.proposals(status="accepted")
    if not accepted:
        print("nothing accepted by its reviewer awaits delivery")
        return 0
    if _git(root, "status", "--porcelain"):
        print(f"refused: {root} has uncommitted changes")
        return 2
    try:
        app = _github_app(root) if args.open_pr else None
    except PublishFailed as exc:
        print(f"not delivered, still accepted: {exc}")
        return 1
    name, email = app[1] if app else GAGOS_IDENTITY
    branch = args.branch or delivery_branch(led)

    def check(rels: list[str]) -> str | None:
        """The delivery check of *rels* as they now stand, together: None when
        it passes. Python files compile and the tests that import them pass;
        frontend files parse, have no ESLint error and their tests pass."""
        reasons: list[str] = []
        python = [rel for rel in rels if is_python(rel)]
        if python:
            smoke = python_smoke(root, python, timeout_s=args.check_timeout)
            if not smoke.passed:
                reasons.append(smoke.reason)
        frontend = [root / rel for rel in rels if not is_python(rel)]
        if frontend:
            steps: list[SmokeStep] = []
            failure = frontend_smoke(
                root,
                frontend,
                deadline=time.monotonic() + args.check_timeout,
                steps=steps,
            )
            if failure is not None:
                reasons.append(failure + smoke_excerpt(steps))
        return "; ".join(reasons) if reasons else None

    manifest = root / PORT_MANIFEST

    def put_new(unit: list[dict]) -> list[str]:
        """Write the unit's new texts, and the port's manifest with them when
        any is a file the port carries (2026-11-11, "GAGOS through the port"):
        the paths to commit."""
        for p in unit:
            (root / p["rel"]).write_bytes(p["new_text"].encode("utf-8"))
        ported = port_manifest_after(root, {p["rel"]: p["new_text"] for p in unit})
        if ported is None:
            return [p["rel"] for p in unit]
        manifest.write_bytes(ported.encode("utf-8"))
        return [p["rel"] for p in unit] + [PORT_MANIFEST]

    # The changes to deliver: a proposal alone, or a task's every file together.
    units: list[list[dict]] = []
    seen: set[str] = set()
    for p in accepted:
        gid = p.get("group_id")
        if not gid:
            units.append([p])
        elif gid not in seen:
            seen.add(gid)
            members = led.group_members(gid)
            if all(m["status"] == "accepted" for m in members):
                units.append(members)
            else:
                print(
                    f"  {', '.join(m['proposal_id'] for m in members)}: waits, a "
                    "task over several files is delivered only when every file "
                    "of it is accepted"
                )

    _git(root, "fetch", "-q", "origin", "master")
    _git(root, "checkout", "-q", "-B", branch, "origin/master")
    committed: list[str] = []
    for unit in units:
        rels = [p["rel"] for p in unit]
        currents: dict[str, str | None] = {}
        fresh: dict[str, bool] = {}
        for p in unit:
            path = root / p["rel"]
            current = path.read_bytes().decode("utf-8") if path.is_file() else None
            currents[p["proposal_id"]] = current
            if p["rule"] == MISSING_TEST:
                # A first test: still no file of its name, and its module as it was.
                module = root / subject_of(p["rel"])
                base = module.read_bytes().decode("utf-8") if module.is_file() else None
                ok = current is None and base is not None
                fresh[p["proposal_id"]] = ok and digest(base) == p["base_digest"]
            else:
                fresh[p["proposal_id"]] = (
                    current is not None and digest(current) == p["base_digest"]
                )
        if not all(fresh.values()):
            first_stale = next(p for p in unit if not fresh[p["proposal_id"]])
            for p in unit:
                led.record_delivery(p["proposal_id"], branch=branch, outcome="stale")
                if not fresh[p["proposal_id"]]:
                    print(
                        f"  {p['proposal_id']} {p['rel']}: STALE, the file changed "
                        "on master since the proposal"
                    )
                else:
                    print(
                        f"  {p['proposal_id']} {p['rel']}: STALE with "
                        f"{first_stale['rel']}, the files of one task go together"
                    )
            continue

        manifest_before = manifest.read_bytes() if manifest.is_file() else None
        staged = put_new(unit)
        failure = check(rels)
        moot = None
        if failure is not None:
            for p in unit:
                path, current = root / p["rel"], currents[p["proposal_id"]]
                if current is None:
                    path.unlink()
                else:
                    path.write_bytes(current.encode("utf-8"))
            if manifest_before is not None:
                manifest.write_bytes(manifest_before)
            if all(c is not None for c in currents.values()):
                # The same check on master without it (2026-11-02: an accepted
                # change failed its delivery on a test that times out on this
                # laptop with or without it). Failing there too, it says
                # nothing about the change.
                if check(rels) == failure:
                    moot = failure
            if moot is None:
                for p in unit:
                    led.record_delivery(
                        p["proposal_id"],
                        branch=branch,
                        outcome=f"failed checks: {failure}",
                    )
                    print(
                        f"  {p['proposal_id']} {p['rel']}: FAILED delivery checks: "
                        f"{failure}"
                    )
                continue
            staged = put_new(unit)
            for p in unit:
                print(
                    f"  {p['proposal_id']} {p['rel']}: the delivery check fails on "
                    f"master without it too ({failure}); not its doing, CI judges it"
                )
        _git(root, "add", "--", *staged)
        first = unit[0]
        _git(
            root,
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "commit",
            "-q",
            "-m",
            commit_message(
                first,
                led.reviews(first["proposal_id"]),
                moot=moot,
                task=led.task_of_proposal(first["proposal_id"]),
                group=unit if first.get("group_id") else None,
            ),
        )
        sha = _git(root, "rev-parse", "HEAD")
        for p in unit:
            led.record_delivery(
                p["proposal_id"], branch=branch, outcome="committed", commit_sha=sha
            )
            committed.append(p["proposal_id"])
            print(f"  {p['proposal_id']} {p['rel']}: COMMITTED {sha[:12]}")
    if not (committed and args.open_pr):
        return 0
    try:
        url = publish(led, root, branch, committed, app, pr_footer=args.pr_footer)
    except PublishFailed as exc:
        print(f"not published, kept committed for the next day: {exc}")
        return 1
    print(f"PR: {url}")
    return 0


# --------------------------------------------------------------------- report


def _fence(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


def credits(led: DailyLedger, ids: list[str]) -> list[str]:
    """Who did the work in these proposals, by name: the frontier models that
    wrote and judged it, and GAGOS's clerk where it summarised."""
    writers: Counter = Counter()
    judges: dict[str, set] = {r: set() for r in REVIEW_ORDER}
    clerks: set = set()
    for pid in ids:
        [p] = [x for x in led.proposals() if x["proposal_id"] == pid]
        writers[model_name(p["model"])] += 1
        for r, review in led.reviews(pid).items():
            judges[r].add(model_name(review["model"]))
        job = led.clerk_job(pid)
        if job and job["status"] == "completed":
            clerks.add(job["model"])
    lines = ["**Credits**"]
    lines += [f"- written by {name} ({n} change(s))" for name, n in writers.items()]
    lines += [
        f"- reviewed by {REVIEWER_LABELS[r]}: {', '.join(sorted(judges[r]))}"
        for r in REVIEW_ORDER
        if judges[r]
    ]
    if clerks:
        lines.append(
            f"- disagreements summarised by GAGOS's clerk: {', '.join(sorted(clerks))}"
        )
    lines.append("- orchestrated, checked and delivered by GAGOS")
    return lines


#: Where a proposal can be lost, in the order the work meets them.
LOSSES = (
    "not sent (privacy filter or size)",
    "the model call failed",
    "the answer's form",
    "the static checks",
    "the sandbox tests",
    "the reviewer",
)


def lost_at(p: dict) -> str | None:
    """Where *p* was lost, one of :data:`LOSSES`, or None while it lives."""
    if p["status"] == "rejected":
        return "the reviewer"
    if p["status"] != "refused":
        return None
    why = p["refusal"] or ""
    if why.startswith(BROKE_PREFIX):
        return "the sandbox tests"
    if why.startswith("model call failed"):
        return "the model call failed"
    if p["model"] == NO_MODEL or "cannot be shown to a reviewer" in why:
        return "not sent (privacy filter or size)"
    if any(
        k in why
        for k in ("fenced code block", "file is empty", "placeholder", "duplicates")
    ):
        return "the answer's form"
    return "the static checks"


def efficiency(every: list[dict], spent: float) -> list[str]:
    """What GAGOS's work costs per change that survives review, and where the
    rest is lost: the numbers its efficiency is judged by (the operator,
    2026-11-02: "cross-system efficiency"). Descriptive, from the ledger."""
    kept = [
        p
        for p in every
        if p["status"] in ("accepted", "committed", "delivered", "stale", "failed")
    ]
    lost = Counter(lost_at(p) for p in every)
    per = f"${spent / len(kept):.3f}" if kept else "none yet"
    return [
        "**Efficiency** (this month's estimated spend; every proposal in the ledger):",
        f"- accepted by review: {len(kept)} of {len(every)} proposals; "
        f"cost per accepted change: {per}",
        "- lost at: "
        + "; ".join(f"{where} {lost[where]}" for where in LOSSES)
        + f"; awaiting review {lost[None] - len(kept)}",
        "",
    ]


#: Goals the clerk takes in, at most, in one hour (each is three local jobs).
GOALS_PER_HOUR = 3


def goals_through_clerk() -> bool:
    """Whether open tasks go to the clerk first (the one-system plan, phase 1):
    on unless ``AIOS_GAGOS_GOALS_THROUGH_CLERK=0``."""
    return os.environ.get("AIOS_GAGOS_GOALS_THROUGH_CLERK", "1").strip() != "0"


def goals_hour(led: DailyLedger, root: Path, *, service=None) -> None:
    """The clerk's part of the hour: up to GOALS_PER_HOUR open tasks not yet
    briefed go through the clerk's context check, triage and briefing
    (aios.maintenance.goal_intake). Each job is recorded in the clerk's own
    provenance by its service; the outcome is recorded here. A clerk that
    cannot answer leaves the goal waiting, saying why."""
    if not goals_through_clerk():
        return
    todo = goal_intake.pending(led.tasks(status="open"), led.intakes())[:GOALS_PER_HOUR]
    if not todo:
        return
    if service is None:
        from aios.operations.clerk_admin import default_service

        service = default_service()
    for task in todo:
        try:
            outcome = goal_intake.intake(
                task, service, project_root=str(root), redact=goal_intake.clerk_redact
            )
        except Exception as exc:  # said, never hidden; the goal waits
            outcome = {
                "state": goal_intake.AWAITING_CLERK,
                "clerk": {},
                "reason": f"the clerk could not be asked: {type(exc).__name__}: {exc}"[
                    :400
                ],
                "mission_request": None,
            }
        led.record_intake(task["task_id"], outcome)
        print(
            f"  goal {task['task_id']}: {outcome['state']}"
            + (f" -- {outcome['reason']}" if outcome.get("reason") else "")
        )


#: Goals originated as council missions per hour: each convenes the council
#: (its King and Planner on the local model).
MISSIONS_PER_HOUR = 2
#: Origination outcomes that spent an envelope slot: never tried again.
SLOT_SPENT = ("awaiting_approval", "blocked", "failed")


def missions_hour(
    led: DailyLedger, root: Path, *, envelope=None, originate=None
) -> None:
    """The council's part of the hour (move A2b, 2026-11-12): up to
    MISSIONS_PER_HOUR goals the clerk briefed are originated as council
    missions inside the operator's daily envelope
    (aios.operations.council_origination). Without a live envelope nothing is
    asked, and the hour says why. Nothing here approves or runs a mission."""
    if not goals_through_clerk():
        return
    from aios.operations import council_origination

    if envelope is None:
        from aios.application.capabilities.envelope import EnvelopeAuthority
        from aios.api.deps import get_emergency_stop

        envelope = EnvelopeAuthority(
            db_path=config.CAPABILITY_DB_PATH, emergency_stop=get_emergency_stop()
        )
    intakes, done = led.intakes(), led.originations()
    todo = [
        t
        for t in led.tasks()
        if intakes.get(t["task_id"], {}).get("state") == goal_intake.BRIEFED
        and done.get(t["task_id"], {}).get("state") not in SLOT_SPENT
        and t["status"] in ("open", "taken")
    ][:MISSIONS_PER_HOUR]
    if not todo:
        return
    status = envelope.status()
    if not status.get("live"):
        print(f"  missions: none originated -- {status.get('reason')}")
        return
    if originate is None:
        workspace = council_origination.gagos_workspace(config.COUNCIL_WORKSPACE_ROOT)
        config.COUNCIL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

        def originate(task, seen):
            return council_origination.originate_goal(
                task,
                seen,
                envelope=envelope,
                workspace_root=workspace,
                runtime_root=config.COUNCIL_RUNTIME_DIR,
            )

    for task in todo:
        try:
            outcome = originate(task, intakes[task["task_id"]])
        except Exception as exc:  # said, never hidden; tried again next hour
            outcome = {
                "state": "refused",
                "reason": f"origination failed: {type(exc).__name__}: {exc}"[:400],
            }
        led.record_origination(task["task_id"], outcome)
        print(
            f"  mission for {task['task_id']}: {outcome['state']}"
            + (f" {outcome['mission_id']}" if outcome.get("mission_id") else "")
            + (f" -- {outcome['reason']}" if outcome.get("reason") else "")
        )


def task_section(led: DailyLedger, scrub=lambda text: text) -> list[str]:
    """The report's lines on the operator's tasks: counts by status, and each
    task still moving (open, or taken and not yet delivered). Never his words."""
    progress = led.task_progress()
    if not progress:
        return []
    by = Counter(t["status"] for t in progress)
    out = [
        "**Tasks** (the operator's, in his words; "
        + ", ".join(f"{s} {by[s]}" for s in TASK_STATUSES)
        + "):"
    ]
    intakes = led.intakes()
    missions = led.originations()
    for t in progress:
        # A task over several files names each, and each one's proposal.
        files = ", ".join(f"`{scrub(rel)}`" for rel in t["files"])
        if t["status"] == "open" and t["task_id"] in intakes:
            seen = intakes[t["task_id"]]
            why = f" ({scrub(seen['reason'])})" if seen.get("reason") else ""
            out.append(
                f"- `{t['task_id']}` in {files}: with the clerk, {seen['state']}{why}"
            )
        elif t["status"] == "open":
            out.append(f"- `{t['task_id']}` in {files}: open")
        elif t["status"] == "taken":
            p = t["proposal"]
            if len(t["proposals"]) > 1:
                made = ", proposals " + ", ".join(
                    f"`{m['proposal_id']}` ({scrub(m['rel'])}) {m['status']}"
                    for m in t["proposals"]
                )
            else:
                made = f", proposal `{p['proposal_id']}` {p['status']}" if p else ""
            out.append(f"- `{t['task_id']}` in {files}: taken" + made)
        if t["task_id"] in missions:
            m = missions[t["task_id"]]
            why = f" ({scrub(m['reason'])})" if m.get("reason") else ""
            what = f"mission `{m['mission_id']}` " if m.get("mission_id") else ""
            out.append(f"  - with the council: {what}{m['state']}{why}")
    return [*out, ""]


def report(
    led: DailyLedger,
    *,
    day: str | None = None,
    in_pr: list[str] | None = None,
    footer: str = "",
    scrub=None,
    only: list[str] | None = None,
    aliveness: list[str] | None = None,
) -> str:
    """The day's work, every proposal and what happened to it (refused and
    rejected ones too: an honest day shows its misses), then D14's running
    numbers and the credits. *in_pr* marks the proposals a daily PR carries.
    *scrub* is applied to every free text -- the operator's direction, refusals,
    reasons, the clerk's words -- before a report leaves the machine (Codex's
    review of #566: a PR body carried his raw direction notes to GitHub)."""
    s = scrub or (lambda text: text)
    every = led.proposals()
    chosen = [p for p in every if day is None or p["day"] == day]
    # *only*: the per-proposal sections of these alone, the rest counted (a PR
    # body over GitHub's limit, 2026-11-11).
    others = [p for p in chosen if only is not None and p["proposal_id"] not in only]
    if only is not None:
        chosen = [p for p in chosen if p["proposal_id"] in only]
    by = Counter(p["status"] for p in every)
    reviewed = [led.reviews(p["proposal_id"]) for p in every]
    done = [r for r in reviewed if all(x in r for x in REQUIRED_REVIEWERS)]
    # Codex reviewed too until 2026-11-02; how often the two disagreed stays.
    both = [r for r in reviewed if all(x in r for x in REVIEWERS)]
    disagree = [r for r in both if r["codex"]["verdict"] != r["claude"]["verdict"]]
    blocked = [d for d in led.days() if d["status"] == "blocked"]
    out = [f"## GAGOS daily work{f' — {day}' if day else ''}", ""]
    direction = load_direction(_direction_path())
    if direction.notes or direction.rules or direction.focus or direction.avoid:
        out += [
            f"**The operator's direction in force** (updated {direction.updated}):",
            *(f"- {s(note)}" for note in direction.notes),
            *([f"- rules: {', '.join(direction.rules)}"] if direction.rules else []),
            *(
                [f"- focus first: {', '.join(direction.focus)}"]
                if direction.focus
                else []
            ),
            *([f"- never: {', '.join(direction.avoid)}"] if direction.avoid else []),
            "",
        ]
    out += [
        "**D14 so far** (every proposal in the ledger; descriptive, not a test):",
        f"- proposals: {len(every)}; refused by the unattended checks or the model: "
        f"{by['refused']}; awaiting review: {by['proposed']}",
        f"- reviewed: {len(done)}; accepted: "
        f"{sum(1 for r in done if all(r[x]['verdict'] == 'accept' for x in REQUIRED_REVIEWERS))}; "
        f"Codex and Claude Code disagreed (while both reviewed, until 2026-11-02): "
        f"{len(disagree)}",
        f"- delivered: {by['delivered']}; stale: {by['stale']}; failed delivery checks: {by['failed']}",
        f"- batches blocked (days until 2026-11-02, hours since): {len(blocked)}",
        "- merged and reverted are not tracked automatically yet; read them from master.",
        "",
        "**D15** (a playbook per rule; counts only until the stopping rule): "
        + ", ".join(f"{arm.upper()} {n}" for arm, n in d15_counts(led).items())
        + " decided in the population",
        "",
        "**Completion** (GAGOS's own measures each hour on master; `score` prints "
        "them):",
        *score_lines(led.measures()),
        "",
    ]
    out += task_section(led, s)
    # 2026-11-12: which parts of GAGOS did real work (organ 52's pulse), so a
    # silent organ is seen every day, not found by accident.
    out += [s(line) for line in aliveness or []]
    month = _month()
    spent = led.month_spend(month)
    out += [
        f"**The workforce** (AWS {month}, from the tokens reported, priced high: "
        f"${sum(spent.values()):.2f} of the operator's ${MONTHLY_AWS_USD:.0f}):",
        *(
            f"- {model_name(m)}: {w} accepted of {d} decided; "
            + (
                "on the operator's plan"
                if m in PLAN_WRITERS
                else f"${spent.get(m, 0.0):.2f} this month"
            )
            for m, (w, d) in sorted(led.model_outcomes().items())
        ),
        "",
        *efficiency(every, sum(spent.values())),
    ]
    if others:
        kinds = Counter(p["status"] for p in others)
        out += [
            f"**This day's {len(others)} other proposal(s)** ("
            + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
            + f") are in the day's full report, `reports/{day}.md` in GAGOS's data "
            "on the operator's laptop: listed here they would pass GitHub's limit.",
            "",
        ]
    for p in chosen:
        reviews = led.reviews(p["proposal_id"])
        carried = " (in this PR)" if in_pr and p["proposal_id"] in in_pr else ""
        out += [
            f"### {p['rule']} in `{p['rel']}` — {p['status']}{carried}",
            f"proposal `{p['proposal_id']}`, written by {model_name(p['model'])}, "
            f"base `{p['base_commit'][:12]}`",
        ]
        if p.get("group_id"):
            out.append(
                f"- one of the files of task `{p['group_id']}`: judged, tested and "
                "delivered with the others"
            )
        if p["refusal"]:
            out.append(f"- refused: {s(p['refusal'])}")
        if p.get("sandbox"):
            tests = SandboxVerdict.from_json(p["sandbox"])
            out.append(
                f"- tests in the sandbox: **{tests.outcome}**: {s(tests.summary)}"
            )
        if p.get("prescreen"):
            word = json.loads(p["prescreen"])
            out.append(
                f"- the council's Critique queen (advisory): **{word.get('verdict')}**: "
                f"{s(str(word.get('reason') or ''))}"
            )
        for r in REVIEW_ORDER:
            if r in reviews:
                rv = reviews[r]
                out.append(
                    f"- {REVIEWER_LABELS[r]} ({model_name(rv['model'])}): "
                    f"**{rv['verdict']}**: {s(rv['reason'])}"
                )
            elif r in REQUIRED_REVIEWERS and p["status"] in ("proposed", "rejected"):
                out.append(f"- {REVIEWER_LABELS[r]}: not yet reviewed")
        job = led.clerk_job(p["proposal_id"])
        if job:
            if job["status"] == "completed":
                out.append(
                    f"- GAGOS's clerk ({job['model']}) on the disagreement: "
                    f"{s(job['summary'] or '')} Crux: {s(job['crux'] or '')}"
                )
            else:
                out.append(
                    f"- GAGOS's clerk could not summarise: {s(job['reason'] or '')}"
                )
        if p["diff"]:
            out += [
                "",
                "<details><summary>diff</summary>",
                "",
                _fence(p["diff"], "diff"),
                "",
                "</details>",
            ]
        out.append("")
    if in_pr:
        out += [*credits(led, in_pr), ""]
    if footer:
        out += ["", footer]
    return "\n".join(out)


def cmd_report(args: argparse.Namespace) -> int:
    text = report(ledger(), day=args.day, aliveness=aliveness_lines())
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


# --------------------------------------------------------------------- D15: the reflector

#: The reflector's model (D15): Claude Sonnet through Claude Code on the
#: operator's plan, through the one gateway, sealed and tool-less.
REFLECTOR = CLAUDE_WRITERS[0]


def reflection_evidence(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Why a rule's recent proposals were or were not accepted, newest first,
    up to :data:`REFLECT_PER_SIDE` a side: reviewer reasons, check refusals and
    sandbox summaries, never code, scrubbed for egress."""
    accepted: list[str] = []
    other: list[str] = []
    for p in rows:
        side = accepted if p["outcome"] else other
        if len(side) >= REFLECT_PER_SIDE:
            continue
        said = [f"reviewer: {rv['reason']}" for rv in (p.get("reviews") or {}).values()]
        if p.get("refusal"):
            said.append(f"refused: {p['refusal']}")
        if p.get("sandbox"):
            said.append(f"tests: {SandboxVerdict.from_json(p['sandbox']).summary}")
        if said:
            side.append(egress_redact(" | ".join(said))[:600])
    return accepted, other


def reflect(led: DailyLedger, rule: str, complete) -> str:
    """One reflection on *rule* (D15): the reflector reads its playbook and the
    reasons behind recent outcomes, and the curator keeps what it may. Marked
    reflected only when it ran; a failed call changes nothing."""
    accepted, other = reflection_evidence(led.decided_for(rule))
    entries = led.playbook(rule)
    prompt = reflection_prompt(rule, entries, accepted, other)
    altered = would_be_altered(prompt, REFLECTOR_SYSTEM)
    if altered:
        led.mark_reflected(rule)
        return f"{rule}: not sent, {altered}"
    try:
        raw = complete(
            prompt,
            REFLECTOR_SYSTEM,
            f"gagos:{_slot()}:reflect:{rule}:{uuid.uuid4().hex[:8]}",
        )
        adds, retires = parse_reflection(raw)
    except ReflectionRefused as exc:
        # Read nothing: tried again next batch, like a failed call (D16).
        return f"{rule}: {exc}, tried next batch"
    except Exception as exc:  # the call failed: tried again next batch
        return f"{rule}: the reflector's call failed, tried next batch: {exc}"[:300]
    # An entry the privacy filter would alter would keep its ON arm's writers
    # from being asked at all: it is not kept.
    keep = [(k, t) for k, t in adds if would_be_altered(t, "") is None]
    added, _ = led.add_playbook_entries(
        rule,
        keep,
        sources=[
            p["proposal_id"] for p in led.decided_for(rule)[: 2 * REFLECT_PER_SIDE]
        ],
    )
    known = {e["entry_id"] for e in entries}
    retired = [
        r
        for r in retires
        if r in known and led.retire_playbook_entry(r, "the reflector")
    ]
    led.mark_reflected(rule)
    return (
        f"{rule}: {len(added)} added, {len(retired)} retired, "
        f"{len(adds) - len(added)} not kept"
    )


def cmd_reflect(args: argparse.Namespace) -> int:
    """D15's reflections for this batch: at most :data:`REFLECTIONS_PER_BATCH`
    rules, the longest waiting first; then the credit is settled."""
    led = ledger()
    credited = led.settle_playbook_credit()
    if credited:
        print(f"  D15: {credited} proposal(s) credited to the entries they were shown")
    waiting = led.rules_awaiting_reflection()[
        : getattr(args, "limit", None) or REFLECTIONS_PER_BATCH
    ]
    if not waiting:
        print("  D15: no rule awaits a reflection")
        return 0
    allowed, why = cloud_coding_allowed()
    if not allowed:
        print(f"  D15: no reflection, the egress law refuses the cloud ({why})")
        return 0
    complete = governed_completer(
        REFLECTOR, getattr(args, "region", None) or config.BEDROCK_REGION
    )
    for rule in waiting:
        print(f"  D15 reflection, {reflect(led, rule, complete)}")
    return 0


def d15_counts(led: DailyLedger) -> dict[str, int]:
    """Decided proposals in D15's population, per arm (counts only)."""
    population = led.d15_population()
    return {
        arm: sum(1 for p in population if p["arm"] == arm) for arm in (ARM_ON, ARM_OFF)
    }


#: D15's stopping rule: this many decided proposals in the population, or this
#: many days after the first batch.
D15_STOP_N = 240
D15_STOP_DAYS = 30


def d15_analysis(population: list[dict]) -> dict:
    """D15's one analysis (H1, H1c, harm), as pre-registered."""
    from scipy.stats import fisher_exact

    def table(rows, key):
        on = [key(r) for r in rows if r["arm"] == ARM_ON]
        off = [key(r) for r in rows if r["arm"] == ARM_OFF]
        return [[sum(on), len(on) - sum(on)], [sum(off), len(off) - sum(off)]], on, off

    t1, on, off = table(population, lambda r: r["outcome"])
    findings: dict[tuple, dict] = {}
    for r in population:
        k = (r["rel"], r["rule"], r["base_digest"])
        findings.setdefault(k, {"arm": r["arm"], "outcome": 0})
        findings[k]["outcome"] |= r["outcome"]
    t2, _, _ = table(list(findings.values()), lambda r: r["outcome"])
    p1 = fisher_exact(t1, alternative="greater").pvalue
    p2 = fisher_exact(t2, alternative="greater").pvalue
    harm = fisher_exact(t1, alternative="less").pvalue
    ordered = sorted([("H1", p1), ("H1c", p2)], key=lambda x: x[1])
    holm, running = {}, 0.0
    for i, (name, pv) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - i) * pv))
        holm[name] = running

    def rate(xs: list[int]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    return {
        "on": {"n": len(on), "accepted": sum(on), "rate": rate(on)},
        "off": {"n": len(off), "accepted": sum(off), "rate": rate(off)},
        "H1": {"p": p1, "holm": holm["H1"], "met": holm["H1"] < 0.05},
        "H1c": {
            "p": p2,
            "holm": holm["H1c"],
            "met": holm["H1c"] < 0.05,
            "findings": len(findings),
        },
        "harm": {"p": harm, "seen": harm < 0.05},
    }


def cmd_d15(args: argparse.Namespace) -> int:
    """D15's counts; with --final, its one analysis (only at the stopping rule)."""
    led = ledger()
    counts = d15_counts(led)
    print(f"D15 decided in the population: ON {counts[ARM_ON]}, OFF {counts[ARM_OFF]}")
    if not args.final:
        print("  (rates and tests are computed once, at the stopping rule: --final)")
        return 0
    print(json.dumps(d15_analysis(led.d15_population()), indent=2))
    return 0


# --------------------------------------------------------------------- completion

#: GAGOS's completion scoreboard (the operator said yes on 2026-11-03; built
#: 2026-11-10): each hour's batch measures, on master, how far GAGOS is from
#: complete by its own measures. Name -> (what it counts, +1 when more is
#: better, -1 when fewer is, 0 when neither).
MEASURES: dict[str, tuple[str, int]] = {
    "warnings": ("warnings the checks find in GAGOS's editable files", -1),
    "in_reach": ("of them, of the rules GAGOS works on", -1),
    "waiting": ("of them, of rules whose fix can change behaviour or spans files", -1),
    "untested": ("frontend modules with no test beside them", -1),
    "can_skip": ("test files with a skip in them (a skip may be conditional)", -1),
    "organs_green": ("organs green in the organ ledger", 1),
    "organs": ("organs in the organ ledger", 0),
}
#: A skip in a test file, Python's or the frontend's.
_SKIP_MARK = re.compile(
    r"\bpytest\.mark\.skip(?:if)?\b|\bpytest\.skip\(|"
    r"\b(?:it|test|describe)\.(?:skip|skipIf|todo)\("
)
_FRONTEND_TEST = re.compile(r"\.(?:test|spec)\.[jt]sx?$")


def skipping_test_files(root: Path) -> list[str]:
    """Test files that can skip: the backend's ``tests/test_*.py`` and the
    frontend's ``*.test.*``/``*.spec.*`` under ``frontend/src``."""
    found = [
        *sorted((root / "tests").rglob("test_*.py")),
        *sorted(
            p
            for p in (root / "frontend" / "src").rglob("*")
            if p.is_file() and _FRONTEND_TEST.search(p.name)
        ),
    ]
    return [
        p.relative_to(root).as_posix()
        for p in found
        if _SKIP_MARK.search(p.read_text(encoding="utf-8", errors="replace"))
    ]


def organ_counts(root: Path) -> tuple[int, int] | None:
    """(green, all) from the organ ledger at *root*, or None when it cannot be
    read: an organ count is never guessed."""
    try:
        organs = json.loads(
            (root / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        return None
    if not isinstance(organs, list):
        return None
    rows = [o for o in organs if isinstance(o, dict)]
    return sum(1 for o in rows if o.get("status") == "green"), len(rows)


def completion_measures(
    root: Path,
    texts: dict[str, str],
    every: Counter,
    rules: tuple[str, ...] | list[str],
    *,
    python_checked: bool,
) -> dict[str, int]:
    """This hour's measures at *root*. *every* counts the checks' warnings by
    rule; *rules* are the rules GAGOS works on this hour. ``python`` records
    whether the Python checks ran, so a count without them is known as one."""
    warnings = sum(every.values())
    in_reach = sum(n for rule, n in every.items() if rule in rules)
    out = {
        "warnings": warnings,
        "in_reach": in_reach,
        "waiting": warnings - in_reach,
        "untested": len(missing_tests(texts, lambda rel: (root / rel).exists())),
        "can_skip": len(skipping_test_files(root)),
        "python": int(python_checked),
    }
    organs = organ_counts(root)
    if organs:
        out["organs_green"], out["organs"] = organs
    return out


def score_lines(rows: list[dict]) -> list[str]:
    """The scoreboard: each measure now, against the first hour and the hour
    before."""
    if not rows:
        return ["- not measured yet: GAGOS's next hourly batch records the first"]
    first, latest = rows[0], rows[-1]
    before = rows[-2] if len(rows) > 1 else None
    out = [
        f"- measured {len(rows)} time(s): first {first['slot']} at "
        f"`{first['head'][:12]}`, latest {latest['slot']} at `{latest['head'][:12]}`"
    ]
    for name, (what, better) in MEASURES.items():
        now = latest["values"].get(name)
        if now is None:
            out.append(f"- {what}: not measured")
            continue
        line = f"- {what}: {now}"
        then = first["values"].get(name)
        if before is not None and then is not None:
            change = now - then
            trend = (
                ""
                if change == 0 or better == 0
                else (", better" if (change > 0) == (better > 0) else ", worse")
            )
            line += f" (first {then}, {change:+d}{trend})"
            last = before["values"].get(name)
            if last is not None and last != now:
                line += f"; the hour before: {last}"
        out.append(line)
    if not latest["values"].get("python"):
        out.append(
            "- the Python checks did not run in the latest hour: its warnings are "
            "the frontend's alone"
        )
    return out


def cmd_score(args: argparse.Namespace) -> int:
    print("GAGOS's completion, by its own measures each hour on master:")
    print("\n".join(score_lines(ledger().measures())))
    return 0


# --------------------------------------------------------------------- the clerk

#: What the clerk returns for a disagreement, in the form the local workforce
#: service reads: field name -> type. The service takes this mapping's keys as
#: the exact set of fields, so a JSON-Schema object here ("type", "properties",
#: "required") made it reject the right answer as extra fields. That was
#: GAGOS's first day, 2026-11-02: "Extra fields rejected: ['crux', 'summary']".
CLERK_SCHEMA = {"summary": "str", "crux": "str"}


def clerk_summarise(p: dict, reviews: dict, *, service=None) -> dict:
    """GAGOS's clerk -- a local model, nothing leaves the machine -- summarises
    for the operator why the two reviewers disagreed. Advisory only: it decides
    nothing (a disagreement never ships). With no model the operator admitted,
    the clerk's service refuses, and that refusal is recorded as honestly."""
    from datetime import timedelta

    from aios.domain.local_workforce.contracts import LocalJobProfile, LocalJobRequest

    if service is None:
        from aios.operations.clerk_admin import default_service

        service = default_service()
    payload = "\n".join(
        [
            f"A proposed change to {p['rel']} (ESLint rule {p['rule']}).",
            "Two independent reviewers disagreed about it:",
            *(
                f"- {REVIEWER_LABELS[r]}: {reviews[r]['verdict']}: {reviews[r]['reason']}"
                for r in REVIEW_ORDER
            ),
            "",
            "The change:",
            p["diff"] or "",
            "",
            "In two sentences, summarise the disagreement for the operator, and "
            "name its crux: the one fact that would settle it.",
        ]
    )
    request = LocalJobRequest(
        job_id=f"gagos-daily-{p['proposal_id']}",
        job_profile=LocalJobProfile.SUMMARISE_DISAGREEMENT,
        input_schema_version="1.0",
        evidence_references=frozenset({p["proposal_id"]}),
        redacted_payload=payload,
        token_budget=400,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=180),
        required_output_schema=CLERK_SCHEMA,
    )
    result = service.run_advisory_job(request)
    output = dict(result.structured_output or {})
    return {
        "status": result.status,
        "model": result.model_id,
        "summary": output.get("summary"),
        "crux": output.get("crux"),
        "reason": result.failure_reason,
    }


def cmd_clerk(args: argparse.Namespace) -> int:
    led = ledger()
    for p in led.disagreements_without_clerk():
        try:
            job = clerk_summarise(p, led.reviews(p["proposal_id"]))
        except Exception as exc:  # recorded, never hidden
            job = {
                "status": "failed",
                "model": None,
                "reason": f"{type(exc).__name__}: {exc}"[:300],
            }
        led.record_clerk(
            p["proposal_id"],
            model=job.get("model"),
            status=job["status"],
            summary=job.get("summary"),
            crux=job.get("crux"),
            reason=job.get("reason"),
        )
        print(
            f"  {p['proposal_id']}: clerk {job['status']}"
            + (f" ({job.get('reason')})" if job["status"] != "completed" else "")
        )
    return 0


# --------------------------------------------------------------------- the day

#: At most this many proposals in one hour's batch, rejections included. A
#: ceiling, not a delivery target (Codex, 2026-10-30). Until 2026-11-02 GAGOS
#: ran one batch of 2 a day: the hourly interval Codex and Claude Code agreed
#: was meant for their own review loop, not for GAGOS's work. The operator
#: corrected it: "GAGOS will work 24/7 continously". It now runs a batch every
#: hour; one review pass covers a batch. 10 until 2026-11-11, raised with the
#: Claude writers' share at the operator's word.
BATCH_PROPOSALS = 20

#: At most this many proposals each reviewer reviews in one run.
REVIEW_LIMIT = 20


def _slot() -> str:
    """This batch's slot: the UTC hour. One batch per slot."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def in_flight(led: DailyLedger, open_prs: list[str]) -> set[str]:
    """Files GAGOS's unmerged work touches: under review, accepted, committed
    but unpublished, or in a PR not yet merged or closed. A new proposal on
    one would go stale against GAGOS's own change, so a batch leaves them
    alone until that work merges or is turned down. Files another batch has
    claimed and not yet released are left alone too."""
    busy = {
        p["rel"]
        for p in led.proposals()
        if p["status"] in ("proposed", "accepted", "committed")
    }
    return busy | led.rels_in_prs(open_prs) | led.claimed_files()


def _pr_state(url: str) -> str:
    """OPEN, MERGED or CLOSED; UNKNOWN when GitHub cannot be asked (which
    blocks the day: fail closed)."""
    try:
        return (
            subprocess.run(
                ["gh", "pr", "view", url, "--json", "state", "-q", ".state"],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            ).stdout.strip()
            or "UNKNOWN"
        )
    except Exception:
        return "UNKNOWN"


def cmd_daily(args: argparse.Namespace) -> int:
    """GAGOS's hour, run by its own scheduler around the clock, needing no one
    to start it: one batch, then the reviews, then delivery. An open GAGOS PR
    holds back only delivery; proposing and reviewing go on, on files no
    unmerged GAGOS work touches (the operator, 2026-11-02)."""
    root = Path(args.project).resolve()
    led = ledger()
    today = _today()
    slot = _slot()
    # Work an earlier hour committed but could not publish comes first: it is
    # published (or its PR found) before anything new is delivered.
    held = publish_pending(led, root)
    # Asked whether publishing failed or not: the files of every PR not known
    # to be merged or closed stay GAGOS's, whatever else went wrong (Codex's
    # review of #580: a failed publication left an open PR's files unguarded).
    open_prs = [u for u in led.pr_urls() if _pr_state(u) not in ("MERGED", "CLOSED")]
    if held is None and open_prs:
        held = f"GAGOS's previous PR is not merged or closed: {', '.join(open_prs)}"
    if held:
        print(f"{slot}: delivery waits -- {held}")
    if not led.reserve_day(slot):
        # The hour is claimed atomically before any proposal: two overlapping
        # runs can never both propose (Codex's review of #566).
        print(f"{slot}: this hour's batch already ran or is running")
    else:
        if _git(root, "status", "--porcelain"):
            led.record_day(slot, "blocked", f"{root} has uncommitted changes")
            print(f"refused: {root} has uncommitted changes")
            return 2
        _git(root, "fetch", "-q", "origin", "master")
        _git(root, "checkout", "-q", "--detach", "origin/master")
        # Goals first through the clerk (the one-system plan, phase 1).
        try:
            goals_hour(led, root)
        except Exception as exc:  # the hour's other work goes on; said
            print(
                f"  goals: the clerk's intake failed: {type(exc).__name__}: {exc}"[:400]
            )
        # Then briefed goals to the council, inside his envelope (move A2b).
        try:
            missions_hour(led, root)
        except Exception as exc:  # the hour's other work goes on; said
            print(f"  missions: origination failed: {type(exc).__name__}: {exc}"[:400])
        rc = cmd_propose(
            argparse.Namespace(
                project=str(root),
                budget=BATCH_PROPOSALS,
                model=args.model,
                region=args.region,
                rules=None,
                dry_run=False,
                skip=in_flight(led, open_prs),
            )
        )
        # The claim stands whatever propose did: a failed batch is not a
        # reason to run a second one this hour.
        led.record_day(slot, "ran", None if rc == 0 else f"propose exited {rc}")
    # Before any reviewer reads a proposal, its tests run in the sandbox.
    cmd_test(argparse.Namespace(project=str(root), again=None))
    # Finishing earlier reviews is not a new batch.
    for reviewer in REQUIRED_REVIEWERS:
        cmd_review(
            argparse.Namespace(
                reviewer=reviewer, limit=REVIEW_LIMIT, model=None, timeout=900
            )
        )
    for pid in led.resettle():
        print(f"  {pid}: decided by the reviews already recorded")
    # D15: credit the decided proposals, then reflect on rules with new verdicts.
    cmd_reflect(argparse.Namespace(region=args.region, limit=None))
    cmd_clerk(argparse.Namespace())
    if not held:
        cmd_deliver(
            argparse.Namespace(
                worktree=str(root),
                branch=None,
                check_timeout=600,
                open_pr=True,
                pr_footer="",
            )
        )
    reports = config.DATA_DIR / "gagos_daily" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{today}.md").write_text(report(led, day=today), encoding="utf-8")
    return 0


# --------------------------------------------------------------------- tasks


def cmd_task(args: argparse.Namespace) -> int:
    """The operator's tasks (2026-11-03): add one, list them, cancel an open one."""
    led = ledger()
    if args.task_command == "add":
        try:
            tid = led.add_task(
                args.file,
                args.text,
                said_by="the operator (command line)",
                also=getattr(args, "also", None) or (),
            )
        except TaskRefused as exc:
            print(f"refused: {exc}")
            return 2
        print(tid)
        return 0
    if args.task_command == "cancel":
        if led.cancel_task(args.task_id):
            print(f"{args.task_id}: cancelled")
            return 0
        task = led.task(args.task_id)
        print(
            f"{args.task_id}: not cancelled, "
            + (f"it is {task['status']}, not open" if task else "no such task")
        )
        return 2
    for t in led.task_progress():
        p = t["proposal"]
        state = t["status"]
        if p and len(t["proposals"]) > 1:
            state += " -> proposals " + ", ".join(
                f"{m['proposal_id']} {m['status']}" for m in t["proposals"]
            )
            if p["pr_url"]:
                state += f" {p['pr_url']}"
        elif p:
            state += f" -> proposal {p['proposal_id']} {p['status']}"
            if p["pr_url"]:
                state += f" {p['pr_url']}"
        elif t["status"] == "refused" and t["reason"]:
            state += f" ({t['reason']})"
        first = (t["text"].splitlines() or [""])[0]
        print(f"{t['task_id']} {state} {','.join(t['files'])}: {first}")
    return 0


# --------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose")
    p.add_argument("--project", required=True, help="a clean checkout of master")
    p.add_argument(
        "--budget", type=int, default=2, help="model calls in this batch (default 2)"
    )
    p.add_argument(
        "--model", default=None, help="one writer; default: GAGOS's workforce"
    )
    p.add_argument(
        "--region",
        default=os.environ.get("AIOS_BEDROCK_REGION") or config.BEDROCK_REGION,
    )
    p.add_argument("--rules", nargs="*", help=f"default: {' '.join(FIRST_RULES)}")
    p.add_argument("--dry-run", action="store_true", help="list the work; ask no model")
    p.set_defaults(func=cmd_propose)

    r = sub.add_parser("review")
    r.add_argument("--reviewer", required=True, choices=REVIEWERS)
    r.add_argument(
        "--model", default=None, help="default: the reviewer's own configured model"
    )
    r.add_argument("--limit", type=int, default=10)
    r.add_argument("--timeout", type=float, default=900)
    r.add_argument(
        "--again",
        nargs="+",
        metavar="PROPOSAL",
        help="review these proposals again (a verdict given on wrong evidence)",
    )
    r.set_defaults(func=cmd_review)

    t = sub.add_parser("test", help="run proposals' tests in the sandbox")
    t.add_argument(
        "--project", required=True, help="a checkout holding the proposals' bases"
    )
    t.add_argument(
        "--again",
        nargs="+",
        metavar="PROPOSAL",
        help="run these proposals' tests again",
    )
    t.set_defaults(func=cmd_test)

    d = sub.add_parser("deliver")
    d.add_argument(
        "--worktree",
        required=True,
        help="a dedicated, clean worktree; reset to origin/master",
    )
    d.add_argument("--branch", default=None)
    d.add_argument("--check-timeout", type=float, default=600)
    d.add_argument("--open-pr", action="store_true")
    d.add_argument("--pr-footer", default="")
    d.set_defaults(func=cmd_deliver)

    c = sub.add_parser("clerk", help="the clerk summarises today's disagreements")
    c.set_defaults(func=cmd_clerk)

    y = sub.add_parser(
        "daily", help="GAGOS's hour: a batch, the reviews, delivery (run hourly)"
    )
    y.add_argument("--project", required=True, help="GAGOS's own dedicated worktree")
    y.add_argument(
        "--model", default=None, help="one writer; default: GAGOS's workforce"
    )
    y.add_argument(
        "--region",
        default=os.environ.get("AIOS_BEDROCK_REGION") or config.BEDROCK_REGION,
    )
    y.set_defaults(func=cmd_daily)

    g = sub.add_parser(
        "direct", help="record the operator's direction (taste, priorities)"
    )
    g.add_argument(
        "--note", action="append", help="a direction in his words; repeatable"
    )
    g.add_argument("--rules", nargs="+")
    g.add_argument("--focus", nargs="+", help="path prefixes to work first")
    g.add_argument("--avoid", nargs="+", help="path prefixes never to touch")
    g.add_argument("--clear", action="store_true", help="start from no direction")
    g.add_argument("--said", default="", help="what he said, verbatim, for the history")
    g.set_defaults(func=cmd_direct)

    k = sub.add_parser(
        "task",
        help="the operator's tasks: a change in his words, over one to five files",
    )
    ksub = k.add_subparsers(dest="task_command", required=True)
    ka = ksub.add_parser("add", help="queue a task for GAGOS's writers")
    ka.add_argument("--file", required=True, help="the project-relative file")
    ka.add_argument(
        "--also",
        action="append",
        default=[],
        metavar="FILE",
        help=f"one more file the task changes together with the first (repeat; at "
        f"most {MAX_TASK_FILES - 1})",
    )
    ka.add_argument("text", help="the change, in plain words")
    ksub.add_parser("list", help="every task and what became of it")
    kc = ksub.add_parser("cancel", help="withdraw a task no writer has taken")
    kc.add_argument("task_id")
    k.set_defaults(func=cmd_task)

    o = sub.add_parser("report")
    o.add_argument("--day", default=None)
    o.add_argument("--out", default=None)
    o.set_defaults(func=cmd_report)

    s = sub.add_parser(
        "score", help="how complete GAGOS is by its own measures, first hour to latest"
    )
    s.set_defaults(func=cmd_score)

    rf = sub.add_parser(
        "reflect", help="D15: reflect on the rules with new verdicts, and settle credit"
    )
    rf.add_argument("--limit", type=int, default=None)
    rf.add_argument(
        "--region",
        default=os.environ.get("AIOS_BEDROCK_REGION") or config.BEDROCK_REGION,
    )
    rf.set_defaults(func=cmd_reflect)

    d15 = sub.add_parser("d15", help="D15's counts; --final runs its one analysis")
    d15.add_argument("--final", action="store_true")
    d15.set_defaults(func=cmd_d15)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
