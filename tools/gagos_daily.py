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

The model call needs, by GAGOS's own law, the "coding" task allowed to the cloud
(constitution intersected with the runtime profile: AIOS_ROUTER_CLOUD_TASKS), and
for a Bedrock writer Bedrock credentials; without either it refuses and says
which. Run it with
AIOS_DATA_DIR set to the operator's data, so the call is bound to his enrolled
identity and constitution, and is recorded in his model-call ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from aios import config  # noqa: E402
from aios.maintenance.daily_work import (  # noqa: E402
    FIRST_RULES,
    MISSING_TEST,
    NO_MODEL,
    UNSHOWABLE,
    PYTHON_RULES,
    REVIEW_SCHEMA,
    REQUIRED_REVIEWERS,
    REVIEWERS,
    TESTER_SYSTEM,
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
    parse_proposal,
    parse_review,
    project_facts,
    proposal_prompt,
    proposer_system,
    review_prompt,
    static_verdict,
    subject_of,
    unified_diff,
    unmask,
)
from aios.maintenance.frontend_static import (  # noqa: E402
    StaticCheckUnavailable,
    check_texts,
    editable_frontend_files,
)
from aios.maintenance.python_static import (  # noqa: E402
    PYTHON_SCOPE,
    check_python_texts,
    editable_python_files,
    import_refusal,
)
from aios.maintenance.sandbox_tests import (  # noqa: E402
    BROKE_PREFIX,
    PASSED,
    UNAVAILABLE,
    BaseTrees,
    SandboxVerdict,
    run_proposal_tests,
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
#: His plan's usage is shared with his own sessions and with the chief
#: reviewer's, so at most this many findings a batch go to the Claude writers;
#: the rest wait for a later hour.
PLAN_PROPOSALS_PER_BATCH = 4
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
WORKFORCE = (*CLAUDE_WRITERS, *BEDROCK_WRITERS)
#: GAGOS's work when the operator names none (2026-11-02): the lint rules
#: whose fix keeps behaviour, in its frontend and in its Python (its backend and
#: itself), then a first test for each frontend module that has none.
WORK_RULES = (*FIRST_RULES, *PYTHON_RULES, MISSING_TEST)
#: An existing test shown to the test writer for this codebase's conventions,
#: when one this short sits beside the module and needs no masking.
MAX_EXAMPLE_CHARS = 6_000

#: Model calls in flight at once: Codex's starting point (2026-11-02), to be
#: raised from measured capacity, not a quota. The ESLint checks run one at a
#: time, so a batch never holds more than one lint's memory.
WRITERS_AT_ONCE = 2
#: A writer is tried on this many decided proposals before its record steers
#: how much work it gets.
EXPLORE = 5

#: The operator, 2026-11-02: "$100 a month for AWS". Every Bedrock call holds
#: its worst case against the UTC month's total first, and makes no call past it.
MONTHLY_AWS_USD = 100.0
#: A deliberately high estimate for every writer, USD per million tokens
#: (input, output), with tokens over-counted at 3 characters each. The spend is
#: estimated from what was sent and received, never read from AWS's bill, so
#: it is pitched to over-state the bill.
PRICE_PER_MTOK = (1.00, 4.00)
CHARS_PER_TOKEN = 3


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
    return DailyLedger(config.DATA_DIR / "gagos_daily" / "ledger.db")


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


#: The longest a Claude writer may take over one answer.
WRITER_TIMEOUT_S = 600


class ClaudeCodeWriter:
    """One of GAGOS's Claude writers: ``claude -p`` on the operator's own plan,
    run as the chief reviewer is: no tools, no session kept, none of his MCP
    servers, in an empty directory, with GAGOS's system prompt in place of
    Claude Code's. :meth:`complete` is the provider contract the gateway
    calls; a call that gives no answer raises, and is recorded as a failed
    call, never as the model's work."""

    def __init__(self, model: str, *, timeout_s: float = WRITER_TIMEOUT_S) -> None:
        self.model = model
        self.timeout_s = timeout_s

    def complete(
        self, prompt: str, *, system: str | None = None, json_mode: bool = False
    ) -> str:
        from aios.core.privacy_filter import PrivacyFilter

        del json_mode  # the answer is a fenced file, never JSON
        # What leaves passes the privacy filter Bedrock's client applies.
        messages = [
            *([{"role": "system", "content": system}] if system else []),
            {"role": "user", "content": prompt},
        ]
        safe, _audit = PrivacyFilter().filter(messages)
        safe_system = next((m["content"] for m in safe if m["role"] == "system"), "")
        safe_prompt = next(m["content"] for m in safe if m["role"] == "user")
        claude = _claude_executable()
        if claude is None:
            raise RuntimeError("the Claude Code CLI is not installed")
        argv = [
            claude,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--tools",
            "",
            "--no-session-persistence",
            "--strict-mcp-config",
        ]
        if safe_system:
            argv += ["--system-prompt", safe_system]
        with tempfile.TemporaryDirectory(prefix="gagos-writer-") as tmp:
            try:
                proc = subprocess.run(
                    argv,
                    input=safe_prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=tmp,
                    timeout=self.timeout_s,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Claude Code timed out after {self.timeout_s:.0f}s"
                ) from exc
        try:
            data = json.loads(proc.stdout or "")
        except ValueError:
            data = {}
        answer = data.get("result")
        if proc.returncode != 0 or data.get("is_error") or not isinstance(answer, str):
            # His plan's usage limit is said here: the writer's next batch
            # gives it one finding only, until it answers again.
            said = answer or (proc.stderr or "")[-300:]
            raise RuntimeError(
                f"Claude Code exited {proc.returncode}: {str(said)[:300]}"
            )
        return answer


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

    if model in CLAUDE_WRITERS:
        provider = ClaudeCodeWriter(model)
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
    if any(r in PYTHON_RULES for r in rules):
        # Its backend and itself; unavailable, the frontend's work goes on.
        try:
            py_texts = {
                rel: (root / rel).read_bytes().decode("utf-8")
                for rel in editable_python_files(root)
            }
            results.update(check_python_texts(root, py_texts))
            texts.update(py_texts)
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
            and not led.attempted(f.rel, f.rule, digest(base_of(f)))
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
        for f in work[: args.budget]:
            print(f"  would propose: {f.rule} in {f.rel} ({len(f.warnings)})")
        return 0
    allowed, why = cloud_coding_allowed()
    if not allowed:
        print(
            f"refused by GAGOS's egress law: the '{TASK}' task may not go to the "
            f"cloud ({why}). Run with AIOS_ROUTER_CLOUD_TASKS including {TASK}."
        )
        return 2
    # Each finding is made ready here, one at a time and without a model:
    # what cannot be sent is recorded and costs nothing of the batch.
    jobs = []
    for f in work:
        if len(jobs) >= args.budget:
            break
        text = base_of(f)
        known = notes if is_python(f.rel) else facts
        common = dict(base_text=text, base_commit=head, facts=known)
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
            masked, mapping = mask_lines(text, egress_redact)
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
            )
        else:
            system = proposer_system(f.rel)
            prompt = proposal_prompt(
                f, masked, prior_refusals=refusals, masked=bool(mapping), facts=known
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
        jobs.append((f, text, masked, mapping, prompt, system, common))
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
        roster = tuple(m for m in workforce if m not in refused)
        probe = refused[0] if refused else None
        if refused:
            print(
                f"  their last call was refused: {', '.join(refused)}; "
                f"{probe} is tried on one finding"
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
    if probe and jobs:
        writers[-1] = probe
    # Not proposals: the findings no writer takes stay unattempted for a later
    # hour.
    capped = [i for i, m in enumerate(writers) if m in CLAUDE_WRITERS][
        PLAN_PROPOSALS_PER_BATCH:
    ]
    for i in capped:
        writers[i] = ""
    idle = writers.count("") - len(capped)
    if capped:
        print(
            f"  {len(capped)} finding(s) wait for a later hour: the operator's plan "
            f"takes {PLAN_PROPOSALS_PER_BATCH} a batch"
        )
    if idle:
        print(f"  {idle} finding(s) wait for a later hour: no writer answers")
    jobs, writers = (
        [j for j, m in zip(jobs, writers) if m],
        [m for m in writers if m],
    )
    completers = {m: governed_completer(m, args.region) for m in dict.fromkeys(writers)}
    month, slot, lint = _month(), _slot(), threading.Lock()

    def attempt(n: int, job: tuple, model: str) -> None:
        f, text, masked, mapping, prompt, system, common = job
        common = dict(common, model=model)
        chars_in = len(prompt) + len(system)
        # A call on the operator's plan costs nothing against the AWS ceiling;
        # it is still held and settled, so its request id is its own.
        on_aws = model not in CLAUDE_WRITERS
        hold = led.reserve_spend(
            month=month,
            model=model,
            purpose=f"propose {f.rule} in {f.rel}",
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
        led.settle_spend(
            hold,
            usd=estimate_usd(chars_in, len(raw)) if on_aws else 0.0,
            chars_in=chars_in,
            chars_out=len(raw),
        )
        try:
            # A new test takes its module's line endings, and ends with one.
            shape = (
                text if f.rule != MISSING_TEST else ("\r\n" if "\r\n" in text else "\n")
            )
            new_text = unmask(
                parse_proposal(raw, original=shape),
                mapping,
                masked=masked,
                repeat=f.rule == MISSING_TEST,
            )
        except ProposalRefused as exc:
            pid = led.record_proposal(
                f, **common, new_text=None, verdict=None, refusal=str(exc)
            )
            print(f"  {pid} {f.rel} ({model}): refused: {exc}")
            return
        try:
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
            print(f"  {pid} {f.rel} ({model}): {exc}")
            return
        verdict = (
            first_test_verdict(f, new_text, after)
            if before is None
            else static_verdict(f, text, new_text, before, after)
        )
        if verdict.passed and is_python(f.rel):
            # Ruff sees one file; what other modules take from it is checked here.
            taken = import_refusal(root, f.rel, text, new_text)
            if taken:
                verdict = StaticVerdict(False, taken, verdict.changed_lines)
        pid = led.record_proposal(f, **common, new_text=new_text, verdict=verdict)
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
    with ThreadPoolExecutor(max_workers=WRITERS_AT_ONCE) as pool:
        for done in [
            pool.submit(attempt, n, job, model)
            for n, (job, model) in enumerate(zip(jobs, writers), 1)
        ]:
            done.result()
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
            masked, mapping = mask_lines(texts[rel], egress_redact)
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


#: Codex features that let a session act, all switched off for a reviewer
#: (Codex's review of #566: a read-only sandbox still ran shell commands and
#: the operator's MCP servers, so it could execute a proposal before both had
#: accepted). The review is a judgement of the text it is given, nothing more.
CODEX_ACTING_FEATURES = (
    "shell_tool",
    "unified_exec",
    "unified_exec_tty",
    "apps",
    "plugins",
    "remote_plugin",
    "browser_use",
    "browser_use_external",
    "in_app_browser",
    "skill_search",
    "tool_suggest",
)


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
    codex = shutil.which("codex")
    if codex is None:
        raise ReviewUnavailable("the Codex CLI is not installed")
    settings = codex_settings()
    model = model or settings.get("model")
    with tempfile.TemporaryDirectory(prefix="gagos-review-") as tmp:
        out = Path(tmp, "verdict.json")
        argv = [
            codex,
            "exec",
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            *(
                arg
                for feature in CODEX_ACTING_FEATURES
                for arg in ("--disable", feature)
            ),
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


def _claude_executable() -> str | None:
    """The real binary, never an npm .cmd shim: cmd.exe would mangle the JSON
    schema argument."""
    found = shutil.which("claude")
    if found and found.lower().endswith((".cmd", ".bat")):
        native = (
            Path(found).parent
            / "node_modules"
            / "@anthropic-ai"
            / "claude-code"
            / "bin"
            / "claude.exe"
        )
        return str(native) if native.is_file() else None
    return found


def run_claude(
    prompt: str, *, model: str | None, timeout_s: float
) -> tuple[str, str, str]:
    claude = _claude_executable()
    if claude is None:
        raise ReviewUnavailable("the Claude Code CLI is not installed")
    argv = [
        claude,
        "-p",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(REVIEW_SCHEMA),
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
    ]
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


def review_evidence(p: dict, finding: Finding) -> str:
    """The review prompt, under the same mask as the proposer's (Codex's review
    of #566: reviews sent the unmasked file and diff to two cloud models).
    Raises ``MaskingFailed`` when the change cannot be shown without exposing
    what may not leave the machine."""
    masked_base, mapping = mask_lines(p["base_text"], egress_redact)
    facts = json.loads(p.get("facts") or "[]")
    if finding.rule == MISSING_TEST:
        # The module and the whole new test, under the module's mask.
        masked_new = mask_like(p["new_text"], mapping)
        prompt = first_test_review_prompt(finding, masked_base, masked_new, facts=facts)
    else:
        # Kept lines exactly as in the masked original, so the diff shows
        # only what the proposal changed.
        masked_new = mask_aligned(p["new_text"], p["base_text"], masked_base, mapping)
        # The file's name, never its path: paths do not leave the machine.
        diff = unified_diff(Path(finding.rel).name, masked_base, masked_new)
        prompt = review_prompt(finding, masked_base, diff, facts=facts)
    if mapping:
        prompt += (
            "\n\nSome spans are shown as placeholders (GAGOSMASK...): they hide "
            "paths or values that may not leave this machine. Judge the change "
            "around them; a placeholder is the same text before and after."
        )
    if p.get("sandbox"):
        # GAGOS's own report of its tests, scrubbed like everything else that
        # leaves the machine (2026-11-03: the privacy filter took the test name
        # `test_get_executor_and_rollback_engine_return_real_instances` for
        # something sensitive, and two correct changes could not be shown).
        prompt += "\n\n" + egress_redact(
            SandboxVerdict.from_json(p["sandbox"]).for_reviewer()
        )
    altered = would_be_altered(prompt, "")
    if altered:
        raise MaskingFailed(f"{UNSHOWABLE}: {altered}")
    return prompt


def cmd_review(args: argparse.Namespace) -> int:
    led = ledger()
    again = set(getattr(args, "again", None) or ())
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
        pending = led.awaiting(args.reviewer)[: args.limit]
    if not pending:
        print(f"nothing awaits {args.reviewer}")
        return 0
    # Both reviewers are cloud models: GAGOS's egress law decides, as for the
    # proposer. Revoked, the reviews wait.
    allowed, why = cloud_coding_allowed()
    if not allowed:
        print(f"reviews wait: the '{TASK}' task may not go to the cloud ({why})")
        return 2
    unavailable = 0
    for p in pending:
        finding = Finding(
            rel=p["rel"],
            rule=p["rule"],
            warnings=tuple(tuple(w) for w in json.loads(p["warnings"])),
        )
        try:
            prompt = review_evidence(p, finding)
        except MaskingFailed as exc:
            led.refuse(p["proposal_id"], str(exc))
            print(f"  {p['proposal_id']}: refused: {exc}")
            continue
        try:
            verdict, reason, model = REVIEWER_RUNNERS[args.reviewer](
                prompt, model=args.model, timeout_s=args.timeout
            )
        except (ReviewUnavailable, ValueError) as exc:
            unavailable += 1
            print(f"  {p['proposal_id']}: {args.reviewer} gave no verdict: {exc}")
            continue
        status = led.record_review(
            p["proposal_id"], args.reviewer, model=model, verdict=verdict, reason=reason
        )
        print(
            f"  {p['proposal_id']} {p['rel']}: {args.reviewer} ({model}) {verdict.upper()}: {reason} -> {status}"
        )
    return 1 if unavailable else 0


# --------------------------------------------------------------------- test


#: Why a frontend proposal's tests do not run before review (yet).
NO_FRONTEND_SANDBOX = (
    "the sandbox has no frontend toolchain yet; the tests that import it run "
    "at delivery, on the host"
)


def cmd_test(args: argparse.Namespace) -> int:
    """Each proposal awaiting review has its tests run in the sandbox, judged
    against its base, before any reviewer reads it (the operator, 2026-11-03:
    "Yes honestly"). One at a time: each container takes two CPUs and 2 GiB."""
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
        for p in pending:
            if is_python(p["rel"]):
                verdict = run_proposal_tests(
                    trees,
                    base_commit=p["base_commit"],
                    rel=p["rel"],
                    new_text=p["new_text"],
                )
            else:
                verdict = SandboxVerdict(UNAVAILABLE, NO_FRONTEND_SANDBOX)
            led.record_sandbox(
                p["proposal_id"], verdict.to_json(), refusal=verdict.refusal
            )
            print(
                f"  {p['proposal_id']} {p['rel']}: tests {verdict.outcome.upper()}: "
                f"{verdict.summary} ({verdict.seconds:.0f}s)"
            )
    return 0


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


def commit_message(p: dict, reviews: dict, *, moot: str | None = None) -> str:
    """GAGOS's commit for one delivered change: what it did, how it was
    checked, who reviewed it, and the frontier model credited as co-author.
    *moot*: the delivery check that fails on master without the change too."""
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
    if moot:
        checked = (
            f"this check fails on master without it too ({moot}), so it says "
            "nothing about it; CI judges it."
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
        f"GAGOS: daily improvements {_today()} ({len(ids)} change(s), "
        "each accepted by its reviewer)"
    )
    footer = pr_footer or (PR_FOOTER_APP if app else PR_FOOTER_NO_APP)
    body = report(led, day=_today(), in_pr=ids, footer=footer, scrub=egress_redact)
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

    def check(rel: str, path: Path) -> str | None:
        """The delivery check of *rel* as it now stands: None when it passes."""
        if is_python(rel):
            # It compiles, and the tests that import it pass.
            smoke = python_smoke(root, [rel], timeout_s=args.check_timeout)
            return None if smoke.passed else smoke.reason
        steps: list[SmokeStep] = []
        return frontend_smoke(
            root,
            [path],
            deadline=time.monotonic() + args.check_timeout,
            steps=steps,
        )

    _git(root, "fetch", "-q", "origin", "master")
    _git(root, "checkout", "-q", "-B", branch, "origin/master")
    committed: list[str] = []
    for p in accepted:
        pid, path = p["proposal_id"], root / p["rel"]
        current = path.read_bytes().decode("utf-8") if path.is_file() else None
        if p["rule"] == MISSING_TEST:
            # A first test: still no file of its name, and its module as it was.
            module = root / subject_of(p["rel"])
            base = module.read_bytes().decode("utf-8") if module.is_file() else None
            fresh = current is None and base is not None
            fresh = fresh and digest(base) == p["base_digest"]
        else:
            fresh = current is not None and digest(current) == p["base_digest"]
        if not fresh:
            led.record_delivery(pid, branch=branch, outcome="stale")
            print(
                f"  {pid} {p['rel']}: STALE, the file changed on master since the proposal"
            )
            continue
        path.write_bytes(p["new_text"].encode("utf-8"))
        failure = check(p["rel"], path)
        moot = None
        if failure is not None:
            if current is None:
                path.unlink()
            else:
                path.write_bytes(current.encode("utf-8"))
                # The same check on master without it (2026-11-02: an accepted
                # change failed its delivery on a test that times out on this
                # laptop with or without it). Failing there too, it says
                # nothing about the change.
                if check(p["rel"], path) == failure:
                    moot = failure
            if moot is None:
                led.record_delivery(
                    pid, branch=branch, outcome=f"failed checks: {failure}"
                )
                print(f"  {pid} {p['rel']}: FAILED delivery checks: {failure}")
                continue
            path.write_bytes(p["new_text"].encode("utf-8"))
            print(
                f"  {pid} {p['rel']}: the delivery check fails on master without "
                f"it too ({failure}); not its doing, CI judges it"
            )
        _git(root, "add", "--", p["rel"])
        _git(
            root,
            "-c",
            f"user.name={name}",
            "-c",
            f"user.email={email}",
            "commit",
            "-q",
            "-m",
            commit_message(p, led.reviews(pid), moot=moot),
        )
        sha = _git(root, "rev-parse", "HEAD")
        led.record_delivery(pid, branch=branch, outcome="committed", commit_sha=sha)
        committed.append(pid)
        print(f"  {pid} {p['rel']}: COMMITTED {sha[:12]}")
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


def report(
    led: DailyLedger,
    *,
    day: str | None = None,
    in_pr: list[str] | None = None,
    footer: str = "",
    scrub=None,
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
    ]
    month = _month()
    spent = led.month_spend(month)
    out += [
        f"**The workforce** (AWS {month}, estimated high: "
        f"${sum(spent.values()):.2f} of the operator's ${MONTHLY_AWS_USD:.0f}):",
        *(
            f"- {model_name(m)}: {w} accepted of {d} decided; "
            + (
                "on the operator's plan"
                if m in CLAUDE_WRITERS
                else f"${spent.get(m, 0.0):.2f} this month"
            )
            for m, (w, d) in sorted(led.model_outcomes().items())
        ),
        "",
        *efficiency(every, sum(spent.values())),
    ]
    for p in chosen:
        reviews = led.reviews(p["proposal_id"])
        carried = " (in this PR)" if in_pr and p["proposal_id"] in in_pr else ""
        out += [
            f"### {p['rule']} in `{p['rel']}` — {p['status']}{carried}",
            f"proposal `{p['proposal_id']}`, written by {model_name(p['model'])}, "
            f"base `{p['base_commit'][:12]}`",
        ]
        if p["refusal"]:
            out.append(f"- refused: {s(p['refusal'])}")
        if p.get("sandbox"):
            tests = SandboxVerdict.from_json(p["sandbox"])
            out.append(
                f"- tests in the sandbox: **{tests.outcome}**: {s(tests.summary)}"
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
    text = report(ledger(), day=args.day)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
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
#: hour; 10 is the review limit below, so one review pass covers a batch.
BATCH_PROPOSALS = 10

#: At most this many proposals each reviewer reviews in one run.
REVIEW_LIMIT = 10


def _slot() -> str:
    """This batch's slot: the UTC hour. One batch per slot."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")


def in_flight(led: DailyLedger, open_prs: list[str]) -> set[str]:
    """Files GAGOS's unmerged work touches: under review, accepted, committed
    but unpublished, or in a PR not yet merged or closed. A new proposal on
    one would go stale against GAGOS's own change, so a batch leaves them
    alone until that work merges or is turned down."""
    busy = {
        p["rel"]
        for p in led.proposals()
        if p["status"] in ("proposed", "accepted", "committed")
    }
    return busy | led.rels_in_prs(open_prs)


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

    o = sub.add_parser("report")
    o.add_argument("--day", default=None)
    o.add_argument("--out", default=None)
    o.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
