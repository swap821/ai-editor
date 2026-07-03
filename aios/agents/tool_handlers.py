"""Tool-action handlers for ToolAgent.

Each handler is a stateless callable that receives the dependencies it needs
from ToolAgent and returns the same (output, status, failed) tuple.
"""
from __future__ import annotations

import difflib
import ipaddress
import os
import re
import socket
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.agents.self_analysis_agent import SelfAnalysisAgent
from aios.core.planner import Planner, PlannerError
from aios.security import scope_lock
from aios.security.gateway import Zone
from aios.security.secret_scanner import scan_and_redact


def _resolve_within(root: Path, candidate: str) -> Optional[Path]:
    """Canonicalise *candidate* under *root*; return it only if it stays inside.

    Defeats ``../`` traversal, absolute paths, and symlink escape via
    :meth:`pathlib.Path.resolve`. Fail-closed: any error yields ``None``.
    """
    if not candidate:
        return None
    try:
        resolved = (root / candidate).resolve()
    except Exception:  # noqa: BLE001 - fail-closed on any resolution error
        return None
    if resolved == root:
        return resolved
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _atomic_write_text(target: Path, content: str, *, replace: bool) -> None:
    """Durably stage text beside *target*, then publish it atomically.

    Existing-file edits use ``os.replace`` so a failed publication leaves the
    original intact. New-file creates use a hard link as an atomic no-clobber
    operation, preserving ``create_file``'s refusal to overwrite under races.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(staged, target)
        else:
            os.link(staged, target)
            staged.unlink()
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def read_file(
    filepath: str,
    *,
    read_root: Path,
    file_read_limit: int,
) -> tuple[str, str, bool]:
    """Read a scoped text file, redact secrets, and return its contents."""
    resolved = _resolve_within(read_root, filepath)
    if resolved is None:
        return (f"[BLOCKED] Path '{filepath}' escapes the project root.", "blocked", False)
    if not resolved.is_file():
        return (f"[ERROR] Not a file: {filepath}", "blocked", False)
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - report read failures cleanly
        return (f"[ERROR] Could not read {filepath}: {exc}", "blocked", False)
    # Never let credentials (e.g. from a .env) reach the model or UI.
    return (scan_and_redact(text[:file_read_limit]).scrubbed, "ok", False)


def read_directory(
    path: str,
    *,
    read_root: Path,
) -> tuple[str, str, bool]:
    """List the contents of a scoped directory."""
    resolved = _resolve_within(read_root, path or ".")
    if resolved is None:
        return (f"[BLOCKED] Path '{path}' escapes the project root.", "blocked", False)
    if not resolved.is_dir():
        return (f"[ERROR] Not a directory: {path}", "blocked", False)
    try:
        entries = sorted(
            p.name + ("/" if p.is_dir() else "") for p in resolved.iterdir()
        )
    except Exception as exc:  # noqa: BLE001 - report listing failures cleanly
        return (f"[ERROR] Could not list {path}: {exc}", "blocked", False)
    return ("\n".join(entries) if entries else "(empty)", "ok", False)


def edit_file(
    filepath: str,
    old_string: str,
    new_string: str,
    *,
    read_root: Path,
    approved_edits: dict[str, tuple[str, str]],
    snapshot: Any,
    audit: Any,
) -> tuple[str, str, bool]:
    """Replace a unique snippet in a sandbox file, gated by human approval.

    Scope-checked against the executor's sandbox roots (tighter than reads).
    Produces a unified diff; an unapproved edit pauses the turn (``approval``)
    carrying that diff, and an approved edit (listed in ``approved_edits``) is
    snapshotted first, then written and audited. ``old_string`` must occur
    exactly once — fail-closed on zero/ambiguous matches or any escape.
    """
    approved = approved_edits.get(filepath)
    if approved is not None:
        # Apply EXACTLY what the human approved, not the model's possibly
        # re-generated args on the replayed turn (robust resume for long edits).
        old_string, new_string = approved

    if not old_string:
        return ("[ERROR] old_string must be non-empty.", "blocked", False)
    # Resolve project-relative (like read_file) before the scope check; the absolute
    # path makes is_path_in_scope a pure containment check, so a path that names the
    # sandbox dir (training_ground/x) no longer double-joins to
    # training_ground/training_ground/x. Sandbox confinement is unchanged.
    scope = scope_lock.is_path_in_scope(str(read_root / filepath))
    if not scope.in_scope:
        roots = ", ".join(str(r) for r in scope_lock.get_scope_roots())
        return (
            f"[BLOCKED] '{filepath}' is outside the editable sandbox scope ({roots}).",
            "blocked",
            False,
        )
    target = Path(scope.resolved)
    if not target.is_file():
        return (
            f"[ERROR] No such file in the sandbox scope: {filepath} "
            "(edits are confined to the sandbox, which is separate from where reads are allowed).",
            "blocked",
            False,
        )
    try:
        current = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - report read failures cleanly
        return (f"[ERROR] Could not read {filepath}: {exc}", "blocked", False)

    occurrences = current.count(old_string)
    if occurrences == 0:
        if new_string and new_string in current:
            # Replay tolerance (the edit analog of create_file's no-op): the
            # resumable approval flow re-runs the whole turn, so the model
            # legitimately re-issues an edit an earlier replay already
            # applied. The replacement being present (and the original
            # gone) means there is nothing left to write or approve.
            return (
                f"{filepath} already contains the requested replacement; "
                "nothing to change.",
                "noop",
                False,
            )
        return (f"[ERROR] old_string not found in {filepath}.", "blocked", False)
    if occurrences > 1:
        return (
            f"[ERROR] old_string is not unique in {filepath} "
            f"({occurrences} matches); add surrounding context.",
            "blocked",
            False,
        )

    updated = current.replace(old_string, new_string, 1)
    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{filepath}",
            tofile=f"b/{filepath}",
        )
    )
    scrubbed = scan_and_redact(diff).scrubbed

    if approved is None:
        # Unapproved: pause the turn for human approval, showing the diff.
        return (scrubbed or "(no textual change)", "approval", False)

    # Approved. Capture the pre-edit snapshot and audit the intent FIRST —
    # both fail-closed: if either fails the edit is NOT applied (no
    # unprotected and no unlogged write) — then write.
    if snapshot is not None:
        try:
            snapshot(f"pre-edit: {filepath}")
        except Exception as exc:  # noqa: BLE001 - fail-closed: no snapshot, no edit
            return (
                f"[BLOCKED] Pre-edit snapshot failed; edit not applied: {exc}",
                "blocked",
                False,
            )
    try:
        audit("tool-agent", f"EDIT: {filepath}", Zone.YELLOW)
    except Exception as exc:  # noqa: BLE001 - fail-closed: no audit, no edit
        return (
            f"[BLOCKED] Audit failed; edit not applied: {exc}",
            "blocked",
            False,
        )
    try:
        _atomic_write_text(target, updated, replace=True)
    except Exception as exc:  # noqa: BLE001 - report write failures cleanly
        return (f"[ERROR] Could not write {filepath}: {exc}", "blocked", False)
    return (f"Edited {filepath}:\n{scrubbed}", "ok", False)


def create_file(
    filepath: str,
    content: str,
    *,
    read_root: Path,
    approved_creations: dict[str, str],
    snapshot: Any,
    audit: Any,
) -> tuple[str, str, bool]:
    """Author a NEW file in the sandbox, gated by human approval.

    Mirrors :func:`edit_file`'s security exactly — scope-locked to the sandbox
    roots (a ``../`` / absolute / symlink escape or any out-of-sandbox path is
    refused, never written), an unapproved create pauses the turn (``approval``)
    carrying an all-additions diff preview, and an approved create (listed in
    ``approved_creations``) is snapshotted + audited FIRST (both fail-closed),
    then written. Refuses to overwrite: ``create_file`` is for NEW paths only —
    an existing file must go through ``edit_file``.
    """
    approved = approved_creations.get(filepath)
    if approved is not None:
        # Write EXACTLY the content the human approved, not the model's possibly
        # re-generated content on the replayed turn (robust resume for new files).
        content = approved

    resolved = _resolve_within(read_root, filepath)
    if resolved is None:
        return (f"[BLOCKED] Path '{filepath}' escapes the project root.", "blocked", False)
    # Same containment check edit_file uses: resolve project-relative, then a
    # pure scope test against the sandbox roots (out-of-sandbox -> refused).
    scope = scope_lock.is_path_in_scope(str(read_root / filepath))
    if not scope.in_scope:
        roots = ", ".join(str(r) for r in scope_lock.get_scope_roots())
        return (
            f"[BLOCKED] '{filepath}' is outside the editable sandbox scope ({roots}).",
            "blocked",
            False,
        )
    target = Path(scope.resolved)
    if target.exists():
        try:
            existing: str | None = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = None
        if existing is not None and existing == content:
            # Replay tolerance: the resumable approval flow re-runs the whole
            # turn after each human approval, so the model legitimately
            # re-issues a create for a file an earlier replay already wrote.
            # Byte-identical content means nothing is written (and nothing
            # new needs approving); report success so the loop continues to
            # the task's remaining steps instead of dead-ending.
            # "noop" (not "ok") so the loop reports success without forcing
            # a redundant re-verification: auto-verify exists to verify a
            # write that LANDED, and nothing changed on disk here.
            return (
                f"{filepath} already exists with exactly the requested "
                "content; nothing to write.",
                "noop",
                False,
            )
        return (
            f"[ERROR] {filepath} already exists; use edit_file to modify it "
            "(create_file only authors new files).",
            "blocked",
            False,
        )

    # An all-additions unified diff ("" -> content) for the approval preview.
    diff = "".join(
        difflib.unified_diff(
            [],
            content.splitlines(keepends=True),
            fromfile="/dev/null",
            tofile=f"b/{filepath}",
        )
    )
    scrubbed = scan_and_redact(diff).scrubbed

    if approved is None:
        # Unapproved: pause the turn for human approval, showing the new content.
        return (scrubbed or "(empty file)", "approval", False)

    # Approved. Capture the pre-create snapshot and audit the intent FIRST —
    # both fail-closed: if either fails the file is NOT created (no unprotected
    # and no unlogged write). The snapshot's "before" has the file absent, so a
    # rollback correctly deletes it.
    if snapshot is not None:
        try:
            snapshot(f"pre-create: {filepath}")
        except Exception as exc:  # noqa: BLE001 - fail-closed: no snapshot, no create
            return (
                f"[BLOCKED] Pre-create snapshot failed; file not created: {exc}",
                "blocked",
                False,
            )
    try:
        audit("tool-agent", f"CREATE: {filepath}", Zone.YELLOW)
    except Exception as exc:  # noqa: BLE001 - fail-closed: no audit, no create
        return (
            f"[BLOCKED] Audit failed; file not created: {exc}",
            "blocked",
            False,
        )
    try:
        # The helper creates parents inside the verified-in-scope target and
        # publishes without clobbering a file created during this operation.
        _atomic_write_text(target, content, replace=False)
    except Exception as exc:  # noqa: BLE001 - report write failures cleanly
        return (f"[ERROR] Could not create {filepath}: {exc}", "blocked", False)
    n_lines = content.count("\n") + (0 if content.endswith("\n") or not content else 1)
    return (
        f"Created {filepath} ({len(content)} bytes, {n_lines} line(s)):\n{scrubbed}",
        "ok",
        False,
    )


# --------------------------------------------------------------------------- verify

def _normalise_sandbox_paths(command: str) -> str:
    """Strip a redundant sandbox-root prefix from path tokens in *command*.

    Verify commands run FROM the sandbox cwd (``SCOPE_ROOTS[0]``), so a path the
    model wrote repo-relative — e.g. ``pytest training_ground/test_x.py`` — would
    double-nest (``training_ground/training_ground/...``), collect 0 tests, and
    exit 4, surfacing a spurious ``[VERIFY FAIL]`` that wastes a model turn. The
    forced auto-verify already expresses its path sandbox-relative; do the same
    for the model's OWN command so its check actually runs.

    Conservative by construction: only the EXACT sandbox-root basename used as a
    leading path segment (after whitespace, a quote, or string start) is removed,
    so unrelated tokens are left byte-for-byte. Idempotent — a no-op on the
    already-correct forced command and on a plain ``pytest -q``.
    """
    roots = config.SCOPE_ROOTS
    name = roots[0].name if roots else ""
    if not name or name not in command:
        return command
    pattern = re.compile(rf"(?<![\w./])(?:\./)?{re.escape(name)}/")
    return pattern.sub("", command)


def verify_command(
    command: str,
    *,
    approved: bool,
    approved_commands: set[str],
    verifier: Any,
    session_id: Optional[str],
) -> tuple[str, str, bool]:
    """Run *command* as a verification through the Verifier; map its verdict.

    Closes the execute -> verify -> reflect loop (blueprint stage 8). The
    Verifier runs *command* through the SAME gated, sandboxed Executor — so a
    RED / out-of-scope verify command is refused by the gateway and never run;
    we do NOT bypass it — and judges pass/fail by exit code + parsed counts,
    fail-closed. The Verifier fires the reflection hook itself on a genuine
    failure, so this dispatch path must NOT reflect again.
    """
    from aios.core.verifier import VerifierResult  # local to avoid import cycles

    command = _normalise_sandbox_paths(command)
    is_approved = approved or command in approved_commands
    result = verifier.verify(
        command,
        session_id=session_id,
        approved=is_approved,
    )

    if result.status == "REQUIRE_APPROVAL":
        return (result.summary, "approval", False)
    if result.status == "BLOCKED":
        return (
            result.summary or f"[BLOCKED] Verification command refused: {command}",
            "blocked",
            False,
        )

    # The Verifier already fired on_failure on a genuine failure; run() reflects
    # only for execute_terminal, so `failed` here is informational (it cannot
    # re-trigger reflection) — carried for the loop's tool-result shape.
    from aios.agents import tool_loop_helpers  # local to avoid import cycles

    return tool_loop_helpers.format_verifier_result(result)


# --------------------------------------------------------------------------- execute

def _format_exec_result(result: Any) -> tuple[str, str, bool]:
    """Map a *resolved* ExecutionResult to ``(output, status, failed)``.

    Handles every terminal status (OK/BLOCKED/TIMEOUT/ERROR) — i.e. a command
    that actually ran or was refused — but never ``REQUIRE_APPROVAL``, which
    the caller intercepts so the turn can pause for a human.
    """
    if result.status == "OK":
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        scrubbed = scan_and_redact(output or "(no output)").scrubbed
        # Ran, but a non-zero exit code is a real failure to learn from.
        return (scrubbed, "ok", bool(result.exit_code))
    if result.status in ("TIMEOUT", "ERROR"):
        return (f"[{result.status}] {result.reason}", "blocked", True)
    # BLOCKED — a security decision (incl. RED refused under approval), not a
    # mistake to reflect on.
    return (f"[{result.status}] {result.reason}", "blocked", False)


def execute_terminal(
    command: str,
    *,
    approved_commands: set[str],
    executor: Any,
    session_id: Optional[str],
) -> tuple[str, str, bool]:
    """Run a command, returning ``(output, status, failed)``.

    A command the human has authorised this turn runs through
    ``execute_approved`` (GREEN/YELLOW run; RED is still refused). Otherwise
    it goes through the normal gateway: a YELLOW escalation surfaces as the
    ``"approval"`` status so the caller can pause and ask.
    """
    if command in approved_commands:
        return _format_exec_result(executor.execute_approved(command))
    result = executor.execute(command, session_id=session_id)
    if result.status == "REQUIRE_APPROVAL":
        return (result.reason, "approval", False)
    return _format_exec_result(result)


# --------------------------------------------------------------------------- browse

def browse_url(
    url: str,
    *,
    approved_commands: set[str],
) -> tuple[str, str, bool]:
    """Fetch a public URL and return extracted main text.

    This is a YELLOW tool: it leaves the local machine, so each URL requires
    explicit human approval (tracked via ``approved_commands``). The approval
    key is ``"browse <url>"`` so the UI can show a clear command.
    Only ``http`` and ``https`` schemes are allowed; private/local addresses
    and non-public hostnames are refused.
    """
    approval_key = f"browse {url}"
    if approval_key not in approved_commands:
        return (
            f"Browsing {url} requires human approval because it accesses the "
            "public internet.",
            "approval",
            False,
        )

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return (f"[BLOCKED] URL scheme '{parsed.scheme}' is not allowed.", "blocked", False)
    if not parsed.hostname:
        return ("[BLOCKED] URL has no hostname.", "blocked", False)
    hostname = parsed.hostname.lower()
    # Block common non-public / local targets.
    if hostname in ("localhost", "127.0.0.1", "::1") or hostname.endswith(".local"):
        return (f"[BLOCKED] {hostname} is a local target.", "blocked", False)
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return (f"[BLOCKED] {hostname} resolves to a non-public address.", "blocked", False)
    except Exception as exc:  # noqa: BLE001 - DNS failure is not a mistake
        return (f"[ERROR] could not resolve {hostname}: {exc}", "ok", True)

    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "GAGOS browse tool"},
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        else:
            text = resp.text
        limit = 8000
        if len(text) > limit:
            text = text[:limit] + "\n[truncated]"
        return (text, "ok", False)
    except Exception as exc:  # noqa: BLE001 - network fetch failure is not a mistake
        return (f"[ERROR] browse failed: {exc}", "ok", True)


# --------------------------------------------------------------------------- plan

def plan_task(
    goal: str,
    *,
    planner: Optional[Planner],
    threshold: Optional[float] = None,
) -> tuple[str, str, bool]:
    """Decompose *goal* into a confidence-gated plan (blueprint Q4); ADVISORY.

    Runs the Planner over the injected COMPLETION client (never the chat
    client, which may be cloud Bedrock with no ``.complete()``) and the 0.72
    confidence gate, then surfaces an ordered, confidence-scored summary so the
    model can plan before acting. The plan NEVER executes and is NEVER reflected
    on: real actions still pass through the security gate + approval, and a bad
    goal / unusable LLM output is a normal advisory result, not a mistake.

      * no planner configured -> a graceful "unavailable" result (never crash);
      * ``PlannerError`` (empty goal / junk LLM output) -> a clean error result;
      * success -> the ordered steps with confidences + an explicit human-review
        section listing every step the gate escalated (confidence < threshold).

    Always returns status ``ok`` with ``failed=False`` — planning is advisory,
    so it surfaces as a normal ``tool_result`` and is never a reflectable failure.
    """
    if planner is None:
        return ("[plan unavailable] no planner configured", "ok", False)
    try:
        plan = planner.plan(goal)
    except PlannerError as exc:
        return (f"[plan error] could not produce a plan: {exc}", "ok", False)
    except Exception as exc:  # noqa: BLE001 - advisory tool must never abort the turn
        # A planner-LLM failure (e.g. LLMError when the local completion model is
        # down while chatting on Bedrock) must degrade to a graceful advisory result.
        return (f"[plan error] planner failed: {exc}", "ok", False)

    lines = [f"Plan for: {plan.goal}", ""]
    for step in plan.steps:
        lines.append(
            f"  {step.step_id}. {step.description} (confidence {step.confidence:.2f})"
        )
    if plan.requires_human:
        lines.append("")
        lines.append(
            f"{len(plan.escalate)} step(s) need human review "
            f"(confidence < {planner.threshold:.2f}):"
        )
        for item in plan.escalate:
            step = item["step"]
            lines.append(
                f"  - step {step.step_id}: {step.description} ({step.confidence:.2f})"
            )
    return ("\n".join(lines), "ok", False)


# --------------------------------------------------------------------------- self-analysis

def self_analyze(
    path: str,
    *,
    read_root: Path,
    tests_root: Path,
    path_root: Path,
) -> tuple[str, str, bool]:
    """Read + diagnose the project's own code (Self-Analysis T0/T1); READ-ONLY.

    Confines *path* to the project root with the SAME read-side resolver as
    ``read_file`` (defeating ``../`` traversal / absolute-path / symlink
    escape), runs the deterministic :class:`SelfAnalysisAgent` over it, writes
    the findings to the report table, and returns a concise summary (counts by
    finding_type + the top findings). It never edits source, runs a command, or
    loads a model — so it always returns status ``ok`` with ``failed=False``
    and is never a reflectable failure (a read-only audit is correct behaviour).
    """
    resolved = _resolve_within(read_root, path)
    if resolved is None:
        return (f"[BLOCKED] Path '{path}' escapes the project root.", "blocked", False)
    if not resolved.is_dir():
        return (f"[ERROR] Not a directory: {path}", "blocked", False)

    agent = SelfAnalysisAgent(
        scope_root=resolved,
        tests_root=tests_root,
        path_root=path_root,
    )
    try:
        report = agent.analyze()
        res = agent.write_report(list(report.findings))
    except Exception as exc:  # noqa: BLE001 - read-only analysis must never abort the turn
        return (f"[ERROR] Self-analysis failed: {exc}", "blocked", False)

    counts: dict[str, int] = {}
    for f in report.findings:
        counts[f.finding_type] = counts.get(f.finding_type, 0) + 1
    by_type = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "none"

    lines = [
        f"Self-analysis of '{path}': {len(report.modules)} module(s), "
        f"{len(report.findings)} finding(s) [{by_type}]; "
        f"{res.open_total} open in report ({res.inserted} new, {res.closed} resolved).",
    ]
    for f in report.findings[:8]:
        lines.append(f"  - [{f.finding_type}] {f.target_path}: {f.evidence}")
    if len(report.findings) > 8:
        lines.append(f"  … and {len(report.findings) - 8} more.")
    return ("\n".join(lines), "ok", False)


def propose_fixes(
    limit: Any,
    *,
    read_root: Path,
    tests_root: Path,
    path_root: Path,
    self_analysis_llm: Optional[Any],
) -> tuple[str, str, bool]:
    """Self-Analysis T2: draft + store fix proposals for open findings; READ-ONLY.

    Runs :meth:`SelfAnalysisAgent.propose_open` over the own-code report (the
    same MEMORY_DB the report lives in), using the injected COMPLETION client
    (never the chat client). It reads source + writes proposals
    (``proposed_diff``, ``open->proposed``) but NEVER edits source and NEVER
    applies a diff (apply is T3, behind the full gate). Always status ``ok`` /
    ``failed=False`` — proposing is advisory, never a security block and never
    reflected on. No client -> a graceful "unavailable" result.
    """
    if self_analysis_llm is None:
        return ("[propose unavailable] no completion model configured.", "ok", False)
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 25
    try:
        agent = SelfAnalysisAgent(
            scope_root=read_root / "aios",
            tests_root=tests_root,
            path_root=path_root,
            llm=self_analysis_llm,
        )
        count = agent.propose_open(limit=n)
    except Exception as exc:  # noqa: BLE001 - advisory tool must never abort the turn
        return (f"[propose error] could not propose fixes: {exc}", "ok", False)
    return (
        f"Proposed fixes for {count} finding(s) (status open→proposed); "
        "review with status='proposed' before any apply (T3).",
        "ok",
        False,
    )
