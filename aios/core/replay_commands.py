"""Exact COMMAND decisions a human already made (learning plan, Phase 5).

The command twin of :mod:`aios.core.replay_writes`. A compiled reflex whose step
is a command that needs approval (a YELLOW ``pytest``) used to be withheld at
replay, always: no record said a human had ever approved it, so the reflex fell
through to the model and no turn could be served without one. That was the
right default (plan Phase 0b) and it is still the default. This module adds the
one exception the operator decided on 2026-09-25:

    a reflex may auto-approve only a step a human approved, in a compatible scope

So a replayed command runs unattended only when ALL of these hold:

* the deployment opted in (``AIOS_REPLAY_APPROVED_COMMANDS``, default OFF -- a
  path that runs commands with no human does not turn itself on);
* the emergency stop is wired and not engaged;
* the gateway classifies the command YELLOW. GREEN never needed this, and RED is
  never approvable (the executor refuses it again regardless);
* the SAME principal approved EXACTLY this command string, in the SAME workspace
  (the active scope roots, ``autonomy.workspace_id``). No normalisation: one
  extra space is a different command and asks again.

WHERE A DECISION COMES FROM
---------------------------
Only from a command that ran because a server-issued capability token was
consumed for it (``generate_pipeline``: raw ``approvedCommands`` are rejected
with 400; tokens are bound to the authenticated principal and broker-checked),
and only when it then ran clean. The tool agent records it at that moment; it
is the only writer.

REVOCATION
----------
A human approving a command once is not a standing promise that it still
works. A replay of a recorded command that fails withdraws the decision, so the
next replay asks again -- the same fail-safe direction as
``replay_writes.revoke_decisions_for_path``.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from aios import config
from aios.core.autonomy import workspace_id
from aios.core.replay_writes import UNGOVERNED_FIXTURE, _stop_permits_writing
from aios.memory.db import get_connection, init_memory_db
from aios.security.gateway import Zone, classify
from aios.security.secret_scanner import scan_and_redact

__all__ = [
    "UNGOVERNED_FIXTURE",
    "command_signature",
    "is_approved_command",
    "record_command_approval",
    "revoke_command_decision",
]


def command_signature(
    command: str, principal: str, *, workspace: Optional[str] = None
) -> str:
    """Key for one exact command decision: this workspace, this principal, this
    exact string. Nothing is normalised -- normalising is what made
    `earned_autonomy`'s keys too wide to say "this, and only this"."""
    ws = workspace if workspace is not None else workspace_id()
    return hashlib.sha256(f"{ws}|{principal}|{command}".encode("utf-8")).hexdigest()


def _approvable(command: str) -> bool:
    """Only a YELLOW command is ever recorded or authorised here."""
    return bool(command.strip()) and classify(command).zone is Zone.YELLOW


def record_command_approval(
    command: str,
    *,
    principal: Optional[str],
    db_path,
    emergency_stop,
    approval_ref: Optional[str] = None,
) -> bool:
    """Remember that *principal* approved running exactly *command* here.

    Returns True when the decision is on record afterwards. Refuses -- records
    nothing, returns False -- when there is no principal (an anonymous approval
    would authorise every anonymous replay), when the stop is engaged or unwired
    (a learning write during a stop is RT-07's finding), when the command is not
    YELLOW, or when it carries a secret (the command text is stored verbatim).
    """
    if not principal or not _approvable(command):
        return False
    if not _stop_permits_writing(emergency_stop):
        return False
    if scan_and_redact(command).detected:
        return False
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO approved_command_decisions "
            "(signature, workspace, principal, command, approval_ref) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                command_signature(command, principal),
                workspace_id(),
                principal,
                command,
                approval_ref,
            ),
        )
    return True


def is_approved_command(
    command: str,
    *,
    principal: Optional[str],
    db_path,
    enabled: Optional[bool] = None,
    emergency_stop=None,
) -> bool:
    """Did *principal* already approve exactly this command, in this workspace?

    Fail-closed on every axis: the flag (off by default), the stop (absent is a
    refusal, as for replayed writes), the principal, the zone (YELLOW only), and
    any drift in the string or the workspace simply misses the row.
    """
    if enabled is None:
        enabled = config.REPLAY_APPROVED_COMMANDS_ENABLED
    if not enabled or not principal:
        return False
    if not _stop_permits_writing(emergency_stop):
        return False
    if not _approvable(command):
        return False
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM approved_command_decisions WHERE signature = ?",
            (command_signature(command, principal),),
        ).fetchone()
    return row is not None


def revoke_command_decision(command: str, *, principal: Optional[str], db_path) -> bool:
    """Withdraw the decision for exactly this command. True if one was removed."""
    if not principal:
        return False
    init_memory_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM approved_command_decisions WHERE signature = ?",
            (command_signature(command, principal),),
        )
        return cur.rowcount > 0
