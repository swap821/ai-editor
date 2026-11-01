#!/usr/bin/env python3
"""GAGOS's daily work on its own frontend (D14): propose, review, report, deliver.

docs/learning/PAYOFF_PREREGISTRATION.md D14. Each step is its own command, so a
day can stop anywhere and resume, and every outcome is in the ledger
(``<AIOS_DATA_DIR>/gagos_daily/ledger.db``):

  propose   lint the frontend of --project (a clean checkout of master); for up
            to --budget findings (one file, one rule), ask the frontier model
            through the one gateway for the whole corrected file, and run the
            unattended static checks. Nothing the model wrote is executed.
  review    --reviewer codex|claude: each open proposal is reviewed by a fresh,
            read-only, tool-less session that sees the rule, the warnings, the
            whole original file and the diff, and returns a schema-checked
            verdict. A proposal is accepted only when BOTH reviewers accept.
  deliver   apply the accepted proposals to a daily branch in --worktree (reset
            to origin/master), each checked there (parse, no ESLint error, the
            tests that import it) and committed on its own; --open-pr pushes
            and opens one PR. The operator merges; CI gates.
  report    the day's work and D14's running numbers, as Markdown.

The model call needs, by GAGOS's own law, the "coding" task allowed to the cloud
(constitution intersected with the runtime profile: AIOS_ROUTER_CLOUD_TASKS) and
Bedrock credentials; without either it refuses and says which. Run it with
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
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from aios import config  # noqa: E402
from aios.maintenance.daily_work import (  # noqa: E402
    FIRST_RULES,
    PROPOSER_SYSTEM,
    REVIEW_SCHEMA,
    REVIEWERS,
    DailyLedger,
    Direction,
    load_direction,
    set_direction,
    Finding,
    MaskingFailed,
    ProposalRefused,
    digest,
    findings,
    mask_like,
    mask_lines,
    parse_proposal,
    parse_review,
    project_facts,
    proposal_prompt,
    review_prompt,
    static_verdict,
    unified_diff,
    unmask,
)
from aios.maintenance.frontend_static import (  # noqa: E402
    StaticCheckUnavailable,
    check_texts,
    editable_frontend_files,
)

DEFAULT_MODEL = "mistral.mistral-large-3-675b-instruct"
#: A whole-file proposal for a longer file would not fit one answer reliably.
MAX_FILE_CHARS = 40_000
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

    if not credentials_available(region):
        raise SystemExit(
            f"no Bedrock credentials for {region}: set AWS_BEARER_TOKEN_BEDROCK "
            "(the operator's keystore) before proposing"
        )
    snapshot = get_constitution_authority().get_active_snapshot()
    provider = AdvisoryChatCompletionAdapter(
        BedrockClient(model=model, region=region, max_tokens=12_000, temperature=0.0),
        model=model,
    )
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
                "one proposed fix of ESLint warnings in one frontend file, for "
                "independent review by two reviewers"
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
    facts = project_facts(root) + tuple(
        f"The operator's direction: {egress_redact(note)}" for note in direction.notes
    )
    if _git(root, "status", "--porcelain", "--", "frontend/src"):
        print(f"refused: frontend/src has uncommitted changes in {root}")
        return 2
    rules = tuple(args.rules or direction.rules or FIRST_RULES)
    texts = {
        rel: (root / rel).read_bytes().decode("utf-8")
        for rel in editable_frontend_files(root)
    }
    try:
        results = check_texts(root, texts)
    except StaticCheckUnavailable as exc:
        print(f"refused: {exc}")
        return 2
    every = Counter(m.rule for r in results.values() for m in r.warnings())
    work = direction.steer(
        [
            f
            for f in findings(results, rules=rules)
            if not led.attempted(f.rel, f.rule, digest(texts[f.rel]))
        ]
    )
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
    complete = governed_completer(args.model, args.region)
    asked = 0
    for f in work:
        if asked >= args.budget:
            break
        text = texts[f.rel]
        common = dict(base_text=text, base_commit=head, model=args.model, facts=facts)
        if len(text) > MAX_FILE_CHARS:
            led.record_proposal(
                f,
                **common,
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
                f, **common, new_text=None, verdict=None, refusal=str(exc)
            )
            print(f"  skipped {f.rel}: {exc}")
            continue
        prompt = proposal_prompt(
            f,
            masked,
            prior_refusals=[egress_redact(r) for r in led.refusal_reasons(f.rule)],
            masked=bool(mapping),
            facts=facts,
        )
        altered = would_be_altered(prompt, PROPOSER_SYSTEM)
        if altered:
            led.record_proposal(
                f, **common, new_text=None, verdict=None, refusal=altered
            )
            print(f"  skipped {f.rel}: {altered}")
            continue
        asked += 1
        started = time.monotonic()
        try:
            raw = complete(prompt, PROPOSER_SYSTEM, f"gagos-daily:{_today()}:{asked}")
        except (
            Exception
        ) as exc:  # the model or the gateway refused; recorded, never hidden
            pid = led.record_proposal(
                f,
                **common,
                new_text=None,
                verdict=None,
                refusal=f"model call failed: {type(exc).__name__}: {exc}"[:600],
            )
            print(f"  {pid} {f.rel}: model call failed: {exc}")
            continue
        try:
            new_text = unmask(
                parse_proposal(raw, original=text), mapping, masked=masked
            )
        except ProposalRefused as exc:
            pid = led.record_proposal(
                f, **common, new_text=None, verdict=None, refusal=str(exc)
            )
            print(f"  {pid} {f.rel}: refused: {exc}")
            continue
        try:
            after = check_texts(root, {f.rel: new_text})[f.rel]
        except StaticCheckUnavailable as exc:
            pid = led.record_proposal(
                f,
                **common,
                new_text=new_text,
                verdict=None,
                refusal=f"static checks unavailable: {exc}",
            )
            print(f"  {pid} {f.rel}: {exc}")
            continue
        verdict = static_verdict(f, text, new_text, results[f.rel], after)
        pid = led.record_proposal(f, **common, new_text=new_text, verdict=verdict)
        state = (
            "PASSED static checks" if verdict.passed else f"REFUSED: {verdict.reason}"
        )
        print(
            f"  {pid} {f.rule} in {f.rel}: {state} "
            f"({verdict.changed_lines} lines, {time.monotonic() - started:.0f}s)"
        )
    return 0


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
    masked_new = mask_like(p["new_text"], mapping)
    # The file's name, never its path: paths do not leave the machine.
    diff = unified_diff(Path(finding.rel).name, masked_base, masked_new)
    prompt = review_prompt(
        finding, masked_base, diff, facts=json.loads(p.get("facts") or "[]")
    )
    if mapping:
        prompt += (
            "\n\nSome spans are shown as placeholders (GAGOSMASK...): they hide "
            "paths or values that may not leave this machine. Judge the change "
            "around them; a placeholder is the same text before and after."
        )
    altered = would_be_altered(prompt, "")
    if altered:
        raise MaskingFailed(f"the change cannot be shown to a reviewer: {altered}")
    return prompt


def cmd_review(args: argparse.Namespace) -> int:
    led = ledger()
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
    "us.anthropic.claude-sonnet-4-6": "Claude Sonnet 4.6 (Anthropic, on Amazon Bedrock)",
    "gpt-6.1-sol": "GPT-6.1 sol (OpenAI, via Codex)",
    "claude-opus-5-5": "Claude Opus 5.5 (Anthropic, via Claude Code)",
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
    "here is authored by GAGOS. Reviewers: Claude Code (chief) and Codex, "
    "independently; a change ships only if both accept. The operator merges."
)
#: Accurate about merging (Codex's post-merge review of #566): GitHub would let
#: the App's token merge a PR whose checks pass; that GAGOS never merges is a
#: rule of its code, not a GitHub restriction.
PR_FOOTER_APP = (
    "Opened by GAGOS itself, through its own GitHub App. GAGOS pushes its "
    "branch and opens the PR; it has no code that merges, and only the "
    "operator merges (GitHub itself would allow the App to merge once the "
    "checks pass: that is a rule GAGOS keeps, not a lock). Reviewers: Claude "
    "Code (chief) and Codex, independently; a change ships only if both accept."
)
#: Kept for callers of the first version.
PR_FOOTER = PR_FOOTER_NO_APP


def commit_message(p: dict, reviews: dict) -> str:
    """GAGOS's commit for one delivered change: what it did, how it was
    checked, who reviewed it, and the frontier model credited as co-author."""
    warnings = json.loads(p["warnings"])
    return "\n".join(
        [
            f"GAGOS: fix {p['rule']} in {p['rel']}",
            "",
            f"GAGOS found {len(warnings)} {p['rule']} warning(s) in this file and "
            f"proposed this change (proposal {p['proposal_id']}); "
            f"{model_name(p['model'])} wrote it. Unattended checks passed: it "
            "parses, the warnings are gone, nothing new. Checked again on master: "
            "it parses, has no ESLint error, and the tests that import it pass.",
            "",
            *(
                f"{REVIEWER_LABELS[r]}, {model_name(reviews[r]['model'])}, accepted: "
                f"{reviews[r]['reason']}"
                for r in REVIEW_ORDER
            ),
            "",
            "Proposed-by: GAGOS",
            f"Co-authored-by: {model_name(p['model'])} <{credit_email(p['model'])}>",
            *(
                f"Reviewed-by: {REVIEWER_LABELS[r]}, {model_name(reviews[r]['model'])}"
                for r in REVIEW_ORDER
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
        "each accepted by both of its reviewers)"
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
    from aios.application.promotion.smoke import SmokeStep, frontend_smoke

    root = Path(args.worktree).resolve()
    led = ledger()
    accepted = led.proposals(status="accepted")
    if not accepted:
        print("nothing accepted by both reviewers awaits delivery")
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
    _git(root, "fetch", "-q", "origin", "master")
    _git(root, "checkout", "-q", "-B", branch, "origin/master")
    committed: list[str] = []
    for p in accepted:
        pid, path = p["proposal_id"], root / p["rel"]
        current = path.read_bytes().decode("utf-8") if path.is_file() else None
        if current is None or digest(current) != p["base_digest"]:
            led.record_delivery(pid, branch=branch, outcome="stale")
            print(
                f"  {pid} {p['rel']}: STALE, the file changed on master since the proposal"
            )
            continue
        path.write_bytes(p["new_text"].encode("utf-8"))
        steps: list[SmokeStep] = []
        failure = frontend_smoke(
            root, [path], deadline=time.monotonic() + args.check_timeout, steps=steps
        )
        if failure is not None:
            path.write_bytes(current.encode("utf-8"))
            led.record_delivery(pid, branch=branch, outcome=f"failed checks: {failure}")
            print(f"  {pid} {p['rel']}: FAILED delivery checks: {failure}")
            continue
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
            commit_message(p, led.reviews(pid)),
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
        f"- reviewed by both: {len(both)}; accepted by both: "
        f"{sum(1 for r in both if all(r[x]['verdict'] == 'accept' for x in REVIEWERS))}; "
        f"reviewers disagreed: {len(disagree)}",
        f"- delivered: {by['delivered']}; stale: {by['stale']}; failed delivery checks: {by['failed']}",
        f"- days blocked: {len(blocked)}",
        "- merged and reverted are not tracked automatically yet; read them from master.",
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
        if p["refusal"]:
            out.append(f"- refused: {s(p['refusal'])}")
        for r in REVIEW_ORDER:
            if r in reviews:
                rv = reviews[r]
                out.append(
                    f"- {REVIEWER_LABELS[r]} ({model_name(rv['model'])}): "
                    f"**{rv['verdict']}**: {s(rv['reason'])}"
                )
            elif p["status"] in ("proposed", "rejected"):
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

#: What the clerk returns for a disagreement.
CLERK_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "crux": {"type": "string"}},
    "required": ["summary", "crux"],
}


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

#: At most this many proposals per UTC day, rejections included (agreed with
#: Codex, 2026-10-30: "two proposals is a ceiling, not a delivery target").
DAILY_PROPOSALS = 2


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
    """GAGOS's day, run by its own scheduler, needing no one to start it:
    the rules agreed with Codex (2026-10-30) decide whether there is work."""
    root = Path(args.project).resolve()
    led = ledger()
    today = _today()
    # Work an earlier day committed but could not publish comes first: it is
    # published (or its PR found) before anything new, and blocks until then.
    blocked = publish_pending(led, root)
    if blocked is None:
        open_prs = [
            u for u in led.pr_urls() if _pr_state(u) not in ("MERGED", "CLOSED")
        ]
        if open_prs:
            blocked = (
                f"GAGOS's previous PR is not merged or closed: {', '.join(open_prs)}"
            )
    proposed_today = len(led.proposals(day=today))
    if blocked:
        led.record_day(today, "blocked", blocked)
        print(f"{today}: blocked -- {blocked}")
    elif proposed_today or not led.reserve_day(today):
        # The day is claimed atomically before any proposal: two overlapping
        # runs can never both propose (Codex's review of #566).
        print(f"{today}: today's batch already ran or is running")
    else:
        if _git(root, "status", "--porcelain"):
            led.record_day(today, "blocked", f"{root} has uncommitted changes")
            print(f"refused: {root} has uncommitted changes")
            return 2
        _git(root, "fetch", "-q", "origin", "master")
        _git(root, "checkout", "-q", "--detach", "origin/master")
        rc = cmd_propose(
            argparse.Namespace(
                project=str(root),
                budget=DAILY_PROPOSALS,
                model=args.model,
                region=args.region,
                rules=None,
                dry_run=False,
            )
        )
        # The claim stands whatever propose did: a failed batch is not a
        # reason to run a second one today.
        led.record_day(today, "ran", None if rc == 0 else f"propose exited {rc}")
    # Finishing today's reviews is not a new batch.
    for reviewer in REVIEW_ORDER:
        cmd_review(
            argparse.Namespace(reviewer=reviewer, limit=10, model=None, timeout=900)
        )
    cmd_clerk(argparse.Namespace())
    if not blocked:
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
        "--budget", type=int, default=2, help="model calls today (default 2)"
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
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
    r.set_defaults(func=cmd_review)

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
        "daily", help="GAGOS's whole day, by the rules agreed with Codex"
    )
    y.add_argument("--project", required=True, help="GAGOS's own dedicated worktree")
    y.add_argument("--model", default=DEFAULT_MODEL)
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
