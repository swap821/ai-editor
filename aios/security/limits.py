"""Guardrail constants, defined behind the freeze.

Inventory item 5. These values decide how far the system may reach and how much
it may do without a human:

* ``SCOPE_ROOTS`` -- where it may act at all
* ``EARNED_AUTONOMY_ENABLED`` / ``EARNED_AUTONOMY_MIN_SUCCESSES`` -- whether, and
  after how much verified evidence, it may act without asking
* ``ROUTER_CLOUD_TASKS`` -- what may leave the machine
* ``MAX_RED_ACTIONS_PER_SESSION`` -- how much destructive work one session may
  even propose
* ``AUDIT_GENESIS_HASH`` -- the anchor the whole tamper-evident chain hangs from

They lived in ``aios/config.py``, which is not frozen, so an agent with
ordinary edit rights could widen its own sandbox, lower its own evidence bar, or
re-anchor the audit chain -- with only a human PR review as the backstop and no
automated one. AGENTS.md §XI names the frozen core as the *security spine*;
these constants are part of that spine in substance while living outside it in
fact. This module closes that gap by moving the DEFINITION inside
``aios/security/``, which `scripts/check_frozen_core.py` guards at the merge
boundary and `ConstitutionEnforcer` guards at runtime.

``aios.config`` re-exports every name below, so no caller changes and
``config.SCOPE_ROOTS`` keeps working exactly as before.

## Why this module imports nothing from `aios.config`

``aios.config`` imports *from here*. Reaching back would be a cycle. The env
helpers below are therefore local, and ``PROJECT_ROOT`` is derived from this
file's own location rather than borrowed.

That second derivation of ``PROJECT_ROOT`` is the one real cost of this move, so
it is pinned rather than trusted: ``tests/test_guardrail_limits.py`` asserts it
equals ``config.PROJECT_ROOT``. Path arithmetic that silently disagreed would
mean the scope roots the checks use and the ones the docs describe are rooted in
different places -- and a base/roots mismatch has already been a real containment
escape in this repo once.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

#: This file is ``<root>/aios/security/limits.py``; the project root is three
#: parents up. `aios/config.py` derives the same directory two parents up from
#: itself. Pinned equal by test -- see the module docstring.
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        # Fail to the DEFAULT, never to a permissive guess: a typo in
        # AIOS_MAX_RED_ACTIONS must not raise the ceiling.
        return default


def _env_scope_roots(name: str, default: tuple[Path, ...]) -> tuple[Path, ...]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return tuple(
        Path(part).expanduser().resolve() for part in raw.split(os.pathsep) if part
    )


#: Router task classes eligible for cloud routing. An unrecognised entry is
#: DROPPED rather than accepted, so a typo cannot widen egress.
_VALID_ROUTER_TASKS: Final[frozenset[str]] = frozenset(
    {"coding", "reasoning", "research", "vision", "long_context"}
)


def _env_router_tasks(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    if raw == "":
        return ()
    return tuple(
        t.strip().lower()
        for t in raw.split(",")
        if t.strip().lower() in _VALID_ROUTER_TASKS
    )


# --------------------------------------------------------------------------- #
# The guardrails themselves
# --------------------------------------------------------------------------- #

#: Where the system may act at all. Widening this is the single most
#: consequential configuration change in the product.
SCOPE_ROOTS: Final[tuple[Path, ...]] = _env_scope_roots(
    "AIOS_SCOPE_ROOTS", (PROJECT_ROOT / "training_ground", PROJECT_ROOT / "lab")
)

#: Off by default. Supervision is the norm; opting in is a deliberate operator
#: act (``AIOS_EARNED_AUTONOMY=1``).
EARNED_AUTONOMY_ENABLED: Final[bool] = _env_bool("AIOS_EARNED_AUTONOMY", False)

#: Consecutive VERIFIED successes before an action class may run unattended.
EARNED_AUTONOMY_MIN_SUCCESSES: Final[int] = _env_int(
    "AIOS_EARNED_AUTONOMY_MIN_SUCCESSES", 5
)

#: Empty by default: nothing is cloud-eligible unless an operator says so.
ROUTER_CLOUD_TASKS: Final[tuple[str, ...]] = _env_router_tasks(
    "AIOS_ROUTER_CLOUD_TASKS", ()
)

#: Ceiling on destructive proposals per session.
MAX_RED_ACTIONS_PER_SESSION: Final[int] = _env_int("AIOS_MAX_RED_ACTIONS", 3)

#: The anchor of the tamper-evident audit chain. Deliberately NOT env-derived:
#: a genesis hash an operator could set from the environment is a genesis hash an
#: attacker with env access could set, and re-anchoring the chain is precisely
#: how a rewritten history is made to verify.
AUDIT_GENESIS_HASH: Final[str] = "0" * 64


__all__ = [
    "AUDIT_GENESIS_HASH",
    "EARNED_AUTONOMY_ENABLED",
    "EARNED_AUTONOMY_MIN_SUCCESSES",
    "MAX_RED_ACTIONS_PER_SESSION",
    "PROJECT_ROOT",
    "ROUTER_CLOUD_TASKS",
    "SCOPE_ROOTS",
]
