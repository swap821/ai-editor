"""Exact write decisions a human already made, and the bytes they approved.

Learning loop, stage 2 slice 1.

Stage 1 made a compiled write step *confirmable*: the playbook carries a digest,
and replay succeeds only when the target already holds exactly those bytes. It
can never write. That is safe, and it is also limited to files that are already
correct.

Stage 2 lets a replay re-perform a write, under one narrow rule chosen by the
operator:

    a human approved writing EXACTLY these bytes to EXACTLY this path
    -> an identical replay reuses that decision
    anything else -> a fresh approval

Two pieces are needed for that, and this module owns both.

WHY NOT `earned_autonomy`
-------------------------
It is the obvious place and it is the wrong one. `AutonomyLedger` answers "has
this action CLASS proved safe over N trials?", and its write signatures collapse
a target to its directory and extension::

    create_file src/util.py   ->   signature over   src/*.py

So once `src/*.py` is earned, *any* content to *any* `.py` under `src/` runs
unattended. Both :meth:`AutonomyLedger.signature` and
:meth:`AutonomyLedger.scoped_signature` normalise that way, so neither can
express "exact path, exact bytes" even if the streak requirement were removed.

Reusing it would have silently granted far more than was asked for, and the
grant would have looked identical in the ledger. Hence a separate table, a
separate flag, and :func:`decision_signature` below, which commits the full
content digest and the untruncated path.

WHY CONTENT IS STORED SEPARATELY
--------------------------------
The playbook deliberately carries no content: step summaries flow into L3
semantic memory, so file bodies there would be a standing secret-leak surface
with the scrubber as the only thing in the way. Replaying a write nonetheless
needs the bytes, so they live here, addressed by digest, and *only* when the
secret scanner finds nothing in them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from aios import config
from aios.core.autonomy import workspace_id
from aios.memory.db import get_connection, init_memory_db
from aios.security.secret_scanner import scan_and_redact


def content_digest(content: str | bytes) -> str:
    """SHA-256 of write content, over the bytes that would be written."""
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(raw).hexdigest()


def decision_signature(
    path: str, digest: str, *, workspace: Optional[str] = None
) -> str:
    """Key for one exact write decision: this workspace, this path, these bytes.

    Deliberately commits the FULL path and the FULL content digest. There is no
    normalisation step, because normalisation is exactly what makes
    `earned_autonomy`'s key too wide for this purpose -- a `<dir>/*<.ext>` shape
    cannot distinguish the file a human approved from its neighbour.

    Keyed by workspace for the reason `AutonomyLedger.signature` learned on
    2026-08-31: a decision made in one project must not grant anything in
    another.
    """
    ws = workspace if workspace is not None else workspace_id()
    return hashlib.sha256(f"{ws}|{path}|{digest}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StoreResult:
    """Outcome of offering content to the blob store."""

    stored: bool
    digest: str
    reason: str


def store_content(content: str, *, db_path) -> StoreResult:
    """Record write content addressed by its digest, unless it carries secrets.

    A detection means NO ROW, and the caller must fall back to stage 1's
    confirm-only behaviour. That is a fallback, not an error: a playbook whose
    content cannot be stored is still perfectly usable as a check.

    Refusing here rather than redacting is deliberate. Storing the *scrubbed*
    text would produce a blob whose digest no longer matches the file the human
    approved, so a later replay would either write the wrong bytes or fail its
    own digest check. Both are worse than not storing.
    """
    digest = content_digest(content)
    scan = scan_and_redact(content)
    if scan.detected:
        return StoreResult(False, digest, "content carries secrets; not stored")

    raw = content.encode("utf-8")
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO playbook_blobs (sha256, content, byte_length) "
            "VALUES (?, ?, ?)",
            (digest, raw, len(raw)),
        )
    return StoreResult(True, digest, "stored")


def load_content(digest: str, *, db_path) -> Optional[bytes]:
    """Return the bytes for *digest*, or None if they were never stored."""
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT content FROM playbook_blobs WHERE sha256 = ?", (digest,)
        ).fetchone()
    return bytes(row["content"]) if row is not None else None


def record_approval(
    path: str,
    content: str,
    *,
    db_path,
    approval_ref: Optional[str] = None,
) -> StoreResult:
    """Remember that a human approved writing *content* to *path*.

    Stores the bytes first and records the decision ONLY if that succeeded: a
    decision pointing at content nobody kept is not a decision anything can act
    on, and leaving the row behind would mean a later replay finds an approval
    with no bytes and has to guess what to do.
    """
    result = store_content(content, db_path=db_path)
    if not result.stored:
        return result

    signature = decision_signature(path, result.digest)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO approved_write_decisions "
            "(signature, workspace, path, content_sha256, approval_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            (signature, workspace_id(), path, result.digest, approval_ref),
        )
    return result


def is_approved_write(
    path: str,
    digest: str,
    *,
    db_path,
    enabled: Optional[bool] = None,
    emergency_stop=None,
) -> bool:
    """Has a human already approved exactly these bytes at exactly this path?

    Fail-closed on every axis:

    * the flag is off by default, so a deployment that never opts in behaves
      exactly like stage 1;
    * an engaged emergency stop denies, because "the human said stop" must
      outrank "the human said yes earlier" -- the whole purpose of the latch is
      to halt work that was previously authorised;
    * any drift in path or content simply misses the row. There is no glob to
      widen and no streak to accumulate.
    """
    if enabled is None:
        enabled = config.REPLAY_APPROVED_WRITES_ENABLED
    if not enabled:
        return False

    if emergency_stop is not None:
        try:
            emergency_stop.assert_operational()
        except Exception:  # noqa: BLE001 - an engaged or unreadable latch denies
            return False

    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM approved_write_decisions WHERE signature = ?",
            (decision_signature(path, digest),),
        ).fetchone()
    return row is not None


# --------------------------------------------------------------------------- #
# Edits (stage 2 slice 4)
# --------------------------------------------------------------------------- #
#
# An edit is a different claim from a create. A create says "this file should
# contain these bytes"; an edit says "this exact snippet should become that
# exact snippet, in this file". The resulting whole-file content is not
# knowable from a compiled step, so approving an edit by a whole-file digest
# would approve it by a value that does not describe it.


def edit_signature(
    path: str,
    old_digest: str,
    new_digest: str,
    *,
    workspace: Optional[str] = None,
) -> str:
    """Key for one exact edit decision: this workspace, this path, this change.

    Commits BOTH digests, in order. Committing only the replacement would let
    the same approved `new_string` be applied over a different `old_string` --
    a different edit to a different part of the file, wearing an approval it
    never received.
    """
    ws = workspace if workspace is not None else workspace_id()
    return hashlib.sha256(
        f"{ws}|{path}|{old_digest}|{new_digest}".encode("utf-8")
    ).hexdigest()


def record_edit_approval(
    path: str,
    old_string: str,
    new_string: str,
    *,
    db_path,
    approval_ref: Optional[str] = None,
) -> StoreResult:
    """Remember that a human approved this exact edit at this exact path.

    BOTH snippets must store cleanly. If either carries secrets the decision is
    not recorded at all -- a half-stored edit is unreplayable, and recording it
    anyway would leave an approval whose other half cannot be found.
    """
    old_result = store_content(old_string, db_path=db_path)
    if not old_result.stored:
        return old_result
    new_result = store_content(new_string, db_path=db_path)
    if not new_result.stored:
        return new_result

    signature = edit_signature(path, old_result.digest, new_result.digest)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO approved_edit_decisions "
            "(signature, workspace, path, old_sha256, new_sha256, approval_ref) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                signature,
                workspace_id(),
                path,
                old_result.digest,
                new_result.digest,
                approval_ref,
            ),
        )
    return new_result


def is_approved_edit(
    path: str,
    old_digest: str,
    new_digest: str,
    *,
    db_path,
    enabled: Optional[bool] = None,
    emergency_stop=None,
) -> bool:
    """Has a human already approved exactly this edit at exactly this path?

    Fail-closed on the same axes as :func:`is_approved_write`, and gated by the
    same flag: enabling replayed writes and replayed edits separately would
    imply they carry different risk, and they do not -- both put bytes on disk
    that no human is looking at right now.
    """
    if enabled is None:
        enabled = config.REPLAY_APPROVED_WRITES_ENABLED
    if not enabled:
        return False

    if emergency_stop is not None:
        try:
            emergency_stop.assert_operational()
        except Exception:  # noqa: BLE001 - an engaged or unreadable latch denies
            return False

    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM approved_edit_decisions WHERE signature = ?",
            (edit_signature(path, old_digest, new_digest),),
        ).fetchone()
    return row is not None


# --------------------------------------------------------------------------- #
# Revocation
# --------------------------------------------------------------------------- #
#
# WHY THIS EXISTS AT ALL.
#
# Write authorisation used to run through `AutonomyLedger`, where the forced
# auto-verify after every write is described in-code as the ONLY writer of
# autonomy evidence -- "the verifier's word, never the model's". A PASS
# extended the streak; a FAIL revoked the class instantly.
#
# Moving write authorisation onto these exact-decision records is a narrowing
# in every respect but one: the records had no revocation. Without these
# functions the convergence would LOOK like a tightening while quietly
# deleting the mechanism that pulls authorisation back when a write turns out
# to break the tests. A human approving bytes once is not a standing promise
# that those bytes still work.


def revoke_write_decision(path: str, digest: str, *, db_path) -> bool:
    """Forget that a write to *path* with *digest* was ever approved.

    Returns True when a decision was actually removed, so a caller can tell a
    revocation from a no-op rather than assuming one happened.

    The blob is deliberately left in place. Other decisions may reference the
    same bytes, and content in the store authorises nothing on its own -- it is
    the decision that grants, and the decision is what is being withdrawn.
    """
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM approved_write_decisions WHERE signature = ?",
            (decision_signature(path, digest),),
        )
        return cur.rowcount > 0


def revoke_edit_decision(
    path: str, old_digest: str, new_digest: str, *, db_path
) -> bool:
    """Forget that this exact edit to *path* was ever approved."""
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM approved_edit_decisions WHERE signature = ?",
            (edit_signature(path, old_digest, new_digest),),
        )
        return cur.rowcount > 0


def revoke_decisions_for_path(path: str, *, db_path) -> int:
    """Withdraw EVERY write and edit decision for *path* in this workspace.

    Used by the auto-verify sink, which knows the file it just verified but not
    which digest the write carried -- the verdict arrives after the write, and
    re-deriving the digest from the file on disk would revoke based on what the
    file happens to contain now rather than on what was approved.

    Revoking the whole path is the fail-safe direction. Too-narrow revocation
    leaves a broken write replayable, which is the failure that matters; a
    too-wide one costs a human approval that was going to be asked for anyway.
    """
    init_memory_db(db_path)
    ws = workspace_id()
    with get_connection(db_path) as conn:
        removed = conn.execute(
            "DELETE FROM approved_write_decisions WHERE workspace = ? AND path = ?",
            (ws, path),
        ).rowcount
        removed += conn.execute(
            "DELETE FROM approved_edit_decisions WHERE workspace = ? AND path = ?",
            (ws, path),
        ).rowcount
    return removed
