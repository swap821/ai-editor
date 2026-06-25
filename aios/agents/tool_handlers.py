"""Tool-action handlers for ToolAgent.

Each handler is a stateless callable that receives the dependencies it needs
from ToolAgent and returns the same (output, status, failed) tuple.
"""
from __future__ import annotations

import difflib
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

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
