"""Self-Analysis Tier T3a — the GUARDED apply engine.

This is the highest-risk component in the system: the FIRST automated write to the
OS's own ``aios/`` source. A human-approved T2 proposal (``status='proposed'``) is
applied through one narrow, audited, **reversible** path with a hard safety net:

    snapshot → ``git apply --check`` → **audit the apply intent (fail-closed,
    before the write)** → single-file-confined ``git apply`` → two-snapshot
    integrity check → gated verify (run the suite), with **auto-rollback** on any
    failure. Auditing before the write mirrors ``edit_file``/``create_file``: ``aios/``
    is never written without the intent first recorded on the tamper-evident ledger.

**Fail-closed everywhere:** anything unclear → restore the original bytes and refuse;
never leave a half-applied or unlogged change. Crucially there is **no agent tool to
apply** (the agent has only the T2 *propose* tool), so the agent can never apply its
own proposal — applying is reachable ONLY via the human-called HTTP endpoint that
constructs this engine. That structural gap is the real no-self-approval guard; the
``approved_by != proposed_by`` check here is the defensive second layer (§6.3).

The RED frozen core (``aios/security/*``, AGENTS.md §XI) is refused outright — editing
the gate that guards the agent is T4, not T3.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from filelock import FileLock, Timeout

from aios import config
from aios.core.executor import _bounded_run
from aios.core.verifier import Verifier
from aios.memory.db import get_connection, init_memory_db
from aios.security.audit_logger import log_action
from aios.security.gateway import Zone
from aios.security.secret_scanner import scan_and_redact

#: Identity that authored T2 proposals — a human approver may never equal it (§6.3).
PROPOSER_ID = "self_analysis_agent"

#: The verify command run after an apply. Scoped to ``tests/`` ON PURPOSE — a bare
#: ``pytest`` would also collect the ``training_ground/`` breath seed (which fails by
#: design) and force spurious rollbacks of otherwise-good applies.
DEFAULT_VERIFY_COMMAND = ".venv/Scripts/python -m pytest tests/ -q"


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of an apply attempt."""

    status: str  #: 'applied' | 'rolled_back' | 'refused'
    reason: str
    audit_id: Optional[int] = None
    verify: Optional[str] = None


def classify_target(
    rel_path: str,
    *,
    package: str = "aios",
    frozen_subdirs: tuple[str, ...] = ("security",),
) -> str:
    """Deterministic would-be-apply zone for a project-relative path.

    A file under a frozen subdir of *package* (e.g. ``aios/security/…``, the frozen
    core in AGENTS.md §XI) is **RED** — editing the gate that guards the agent is the
    highest-risk action. Every other path is **YELLOW**. This is the single source of
    truth shared by T2 (records ``proposed_zone``, see
    :mod:`aios.agents.self_analysis_agent`) and T3 (the apply zone gate below), so the
    two can never diverge. Lives in ``core`` (not ``agents``) so agents/, which is
    built on top of core/, can depend on it without core reaching back up into agents/.
    """
    for sub in frozen_subdirs:
        base = f"{package}/{sub}"
        if rel_path == base or rel_path.startswith(base + "/"):
            return "RED"
    return "YELLOW"


def _diff_paths(diff: str) -> set[str]:
    """File paths a unified diff references (``a/``/``b/`` stripped; ``/dev/null`` skipped)."""
    paths: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            p = line[4:].strip().split("\t")[0]  # drop a trailing tab-timestamp
            if p == "/dev/null" or not p:
                continue
            if p.startswith(("a/", "b/")):
                p = p[2:]
            if p:
                paths.add(p)
    return paths


def _resolve_within(root: Path, candidate: str) -> Optional[Path]:
    """Canonicalise *candidate* under *root*; ``None`` if it escapes (``../``/abs/symlink).

    Fail-closed: any resolution error, the root itself, or anything outside the root
    yields ``None``.
    """
    if not candidate:
        return None
    try:
        resolved = (root / candidate).resolve()
    except Exception:  # noqa: BLE001 - fail-closed on any resolution error
        return None
    if resolved == root:
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


class SelfApplyEngine:
    """Apply one approved proposal to ``aios/`` — gated, verified, reversible (T3a)."""

    def __init__(
        self,
        *,
        verifier: Verifier,
        db_path: Path = config.MEMORY_DB_PATH,
        project_root: Path = config.PROJECT_ROOT,
        audit_log: Callable[..., Any] = log_action,
        verify_command: str = DEFAULT_VERIFY_COMMAND,
        proposer_id: str = PROPOSER_ID,
        frozen_subdirs: tuple[str, ...] = ("security",),
        lock_path: Optional[Path] = None,
    ) -> None:
        self.verifier = verifier
        self.db_path = db_path
        self.project_root = Path(project_root).resolve()
        self._audit = audit_log
        self.verify_command = verify_command
        self.proposer_id = proposer_id
        self.frozen_subdirs = frozen_subdirs
        self._apply_lock = FileLock(
            str(lock_path or (config.DATA_DIR / "self_apply.lock")),
            timeout=0,
        )

    def apply(self, proposal_id: int, *, approved_by: str) -> ApplyResult:
        """Serialize self-apply across local workers and fail closed when busy."""
        try:
            with self._apply_lock.acquire(timeout=0):
                return self._apply_serialized(proposal_id, approved_by=approved_by)
        except Timeout:
            return ApplyResult("refused", "another self-apply operation is already in progress")

    def _apply_serialized(self, proposal_id: int, *, approved_by: str) -> ApplyResult:
        """Apply proposal *proposal_id* on behalf of human *approved_by*.

        Implements snapshot → confine → ``git apply`` → integrity → verify → audit
        with auto-rollback. Every refusal/rollback leaves the tree exactly as it was.
        """
        init_memory_db(self.db_path)

        # 1. Load the row; it must exist and be 'proposed' (never re-apply a decided one).
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, target_path, proposed_diff, proposed_by, status "
                "FROM self_analysis_report WHERE id = ?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            return ApplyResult("refused", f"no proposal with id {proposal_id}")
        if row["status"] != "proposed":
            return ApplyResult(
                "refused", f"proposal {proposal_id} is '{row['status']}', not 'proposed'"
            )

        target_path = row["target_path"]
        diff = row["proposed_diff"] or ""
        proposed_by = row["proposed_by"] or ""

        # 2. No-self-approval (§6.3, defensive). A human id is required and must differ
        #    from the proposer — the agent can never authorise its own proposal.
        approver = (approved_by or "").strip()
        if not approver:
            return ApplyResult("refused", "approved_by is required (a human approver)")
        if len(approver) > 128:
            return ApplyResult("refused", "approved_by is too long")
        if scan_and_redact(approver).detected:
            return ApplyResult("refused", "approved_by must be an identity, not credential-like data")
        if approver == proposed_by or approver == self.proposer_id:
            return ApplyResult(
                "refused", "the proposer may not approve its own proposal (no self-approval)"
            )

        # 3. Zone gate — RE-DERIVE from target_path; never trust the stored zone alone.
        if classify_target(target_path, frozen_subdirs=self.frozen_subdirs) == "RED":
            return ApplyResult(
                "refused", f"{target_path} is frozen core (RED); applying it is T4, refused"
            )

        # 4. Single-file confinement: the diff must touch exactly the target file, and
        #    the target must resolve inside the project root (no ../ / abs / symlink).
        if not diff.strip():
            return ApplyResult("refused", "proposal has no diff to apply")
        paths = _diff_paths(diff)
        if paths != {target_path}:
            return ApplyResult(
                "refused",
                f"diff must touch exactly '{target_path}'; it references {sorted(paths)}",
            )
        resolved = _resolve_within(self.project_root, target_path)
        if resolved is None or not resolved.is_file():
            return ApplyResult(
                "refused", f"target '{target_path}' escapes the project root or is not a file"
            )

        # 5. Snapshot #1 — the original bytes we can always restore to.
        try:
            before_bytes = resolved.read_bytes()
        except OSError as exc:
            return ApplyResult("refused", f"could not read target file: {exc}")

        # 6. git apply --check (clean-apply gate) — proves the diff applies before we
        #    audit or write. A failed check leaves the row 'proposed' and nothing changed.
        ok, out = self._git_apply(diff, self.project_root, check=True)
        if not ok:
            return ApplyResult(
                "refused", f"diff does not apply cleanly (row stays proposed): {out.strip()[:200]}"
            )

        # 7. Audit the APPLY intent BEFORE the write — fail-closed (mirrors
        #    edit_file/create_file): never write aios/ without first recording the
        #    intent on the tamper-evident ledger. An audit error/no-id → refuse and
        #    do NOT write (nothing has changed on disk yet). `applied_audit_id` = this id.
        try:
            apply_entry = self._audit(
                self.proposer_id, f"APPLY: {target_path} approved_by={approver}", Zone.YELLOW
            )
        except Exception as exc:  # noqa: BLE001 - fail-closed: no audit, no write
            return ApplyResult("refused", f"audit failed; not applied: {exc}")
        apply_audit_id = _entry_id(apply_entry)
        if apply_audit_id is None:
            return ApplyResult("refused", "audit failed (no entry id); not applied")

        # 8. Apply for real.
        ok, out = self._git_apply(diff, self.project_root, check=False)
        if not ok:
            restore_error = self._restore(resolved, before_bytes)
            suffix = f"; restore failed: {restore_error}" if restore_error else "; restored"
            return ApplyResult("refused", f"git apply failed{suffix}: {out.strip()[:200]}")

        # 9. Two-snapshot integrity check (§6.3): the on-disk result must equal the
        #    original with EXACTLY the approved diff applied (computed independently
        #    in an isolated copy) — catching any unintended/extra change to the file.
        try:
            after_bytes = resolved.read_bytes()
        except OSError as exc:
            restore_error = self._restore(resolved, before_bytes)
            suffix = f"; restore failed: {restore_error}" if restore_error else "; restored"
            return ApplyResult("refused", f"could not re-read target after apply: {exc}{suffix}")
        expected = self._expected_after(before_bytes, diff, target_path)
        if expected is None or after_bytes != expected:
            restore_error = self._restore(resolved, before_bytes)
            suffix = f"; restore failed: {restore_error}" if restore_error else "; restored"
            return ApplyResult("refused", f"two-snapshot integrity check failed{suffix}")

        # 10. Verify through the gated Verifier (run the suite). A fail/timeout/blocked
        #     verdict → auto-rollback to the snapshot, status='rolled_back'. The restore
        #     already happened, so the ROLLBACK audit is best-effort (a ledger hiccup
        #     there must not crash — the row is rolled_back regardless).
        result = self.verifier.verify(self.verify_command, approved=True)
        if not result.passed:
            restore_error = self._restore(resolved, before_bytes)
            if restore_error:
                return ApplyResult(
                    "refused",
                    f"verify failed and rollback failed: {restore_error}. {result.summary[:200]}",
                    audit_id=apply_audit_id,
                    verify=result.summary,
                )
            self._safe_audit(f"ROLLBACK (verify failed): {target_path}")
            try:
                self._set_status(proposal_id, "rolled_back", approved_by=approver)
            except Exception as exc:  # noqa: BLE001 - bytes are restored; report DB drift honestly
                return ApplyResult(
                    "rolled_back",
                    f"verify failed; bytes restored, but status persistence failed: {exc}",
                    audit_id=apply_audit_id,
                    verify=result.summary,
                )
            return ApplyResult(
                "rolled_back",
                f"verify failed; restored to the pre-apply bytes. {result.summary[:200]}",
                audit_id=apply_audit_id,
                verify=result.summary,
            )

        # 11. Verified pass — keep the change; status='applied', applied_audit_id ties
        #     the row to the apply ledger entry.
        try:
            self._set_status(
                proposal_id, "applied", approved_by=approver, applied_audit_id=apply_audit_id
            )
        except Exception as exc:  # noqa: BLE001 - never keep an untracked applied change
            restore_error = self._restore(resolved, before_bytes)
            if restore_error:
                return ApplyResult(
                    "refused",
                    f"status persistence failed and rollback failed: {exc}; {restore_error}",
                    audit_id=apply_audit_id,
                    verify=result.summary,
                )
            self._safe_audit(f"ROLLBACK (status persistence failed): {target_path}")
            return ApplyResult(
                "refused",
                f"status persistence failed; restored pre-apply bytes: {exc}",
                audit_id=apply_audit_id,
                verify=result.summary,
            )
        return ApplyResult(
            "applied",
            f"applied and verified: {target_path}",
            audit_id=apply_audit_id,
            verify=result.summary,
        )

    # ------------------------------------------------------------------ helpers
    def _set_status(
        self,
        proposal_id: int,
        status: str,
        *,
        approved_by: str,
        applied_audit_id: Optional[int] = None,
    ) -> None:
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE self_analysis_report "
                "SET status = ?, approved_by = ?, applied_audit_id = ? WHERE id = ?",
                (status, approved_by, applied_audit_id, proposal_id),
            )

    def _safe_audit(self, payload: str) -> Any:
        """Append to the tamper-evident ledger; never let an audit error abort the flow.

        The change is already applied/reverted by the time we audit, so a ledger
        hiccup must not crash — it returns ``None`` (no id), surfaced in the result.
        """
        try:
            return self._audit(self.proposer_id, payload, Zone.YELLOW)
        except Exception:  # noqa: BLE001 - audit failure must not break the apply outcome
            return None

    @staticmethod
    def _restore(path: Path, before_bytes: bytes) -> Optional[str]:
        """Atomically restore and verify original bytes; return any failure."""
        staged: Optional[Path] = None
        try:
            fd, staged_name = tempfile.mkstemp(
                prefix=f".{path.name}.restore.",
                suffix=".tmp",
                dir=path.parent,
            )
            staged = Path(staged_name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(before_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, path)
            if path.read_bytes() != before_bytes:
                return "restored bytes did not match the snapshot"
        except OSError as exc:
            return str(exc)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
        return None

    def _expected_after(self, before_bytes: bytes, diff: str, rel_path: str) -> Optional[bytes]:
        """Apply *diff* to a fresh copy of *before_bytes* in an isolated temp dir.

        Returns the resulting bytes (the independently-computed "expected" content),
        or ``None`` if the isolated apply fails — used only to confirm the real write
        equals a clean application of the approved diff.
        """
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            target = tdp / rel_path
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(before_bytes)
            except OSError:
                return None
            ok, _ = self._git_apply(diff, tdp, check=False)
            if not ok:
                return None
            try:
                return target.read_bytes()
            except OSError:
                return None

    @staticmethod
    def _git_apply(diff: str, cwd: Path, *, check: bool) -> tuple[bool, str]:
        """Run ``git apply [--check] <diff>`` with *cwd* as the work tree.

        ``git apply`` works outside a repository and strips the ``a/``/``b/`` prefixes
        (``-p1``), so a single-file diff patches ``cwd/<path>``. Returns
        ``(ok, output)``; fail-closed (any error → ``ok=False``).
        """
        text = diff if diff.endswith("\n") else diff + "\n"
        with tempfile.NamedTemporaryFile(
            "w", suffix=".diff", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(text)
            diff_file = tf.name
        try:
            args = ["git", "apply"]
            if check:
                args.append("--check")
            args.append(diff_file)
            proc = _bounded_run(
                args, cwd=str(cwd), capture_output=True, text=True, timeout=30
            )
            return proc.returncode == 0, (proc.stdout + proc.stderr)
        except Exception as exc:  # noqa: BLE001 - fail-closed on any launch/timeout error
            return False, str(exc)
        finally:
            try:
                os.unlink(diff_file)
            except OSError:
                pass


def _entry_id(entry: Any) -> Optional[int]:
    """The audit entry id, or ``None`` for a fake/failed audit sink."""
    value = getattr(entry, "entry_id", None)
    return int(value) if isinstance(value, int) else None
