"""A mission's sandbox verification: the workshop's Docker sandbox as its check.

2026-11-12. A council mission is verified by its ``verification_commands``,
which the security gateway classifies; every frontend test command is RED
there (``npx vitest`` and ``node .../vitest.mjs`` are scope violations,
``npm test`` is not allowlisted), and the Planner defers any mission without
one. So the mission path could verify only Python work, while GAGOS's goals are
almost all frontend, and are checked by the sandbox
(:func:`aios.maintenance.sandbox_tests.run_change_tests`), which runs in its own
container and never through the gateway.

A mission may instead declare, in its metadata, the files the sandbox verifies::

    {"sandbox_verification": {"files": ["frontend/src/x.ts", ...]}}

The worker runs the sandbox and records it in its run ledger
(:func:`aios.maintenance.sandbox_tests.ledger_entry`), where the Testing Queen
and promotion (organ 15) read it like any command. The gateway is not
loosened: its commands stay RED. This reader is the one place both the Planner
and the Security Queen ask whether a mission declares it.
"""

from __future__ import annotations

from typing import Any

SANDBOX_KEY = "sandbox_verification"
MAX_SANDBOX_FILES = 20


def declared(contract: Any) -> bool:
    """True when *contract*'s metadata declares a sandbox verification at all,
    well-formed or not (the Security Queen judges its form)."""
    metadata = getattr(contract, "metadata", None) or {}
    return SANDBOX_KEY in metadata


def sandbox_files(contract: Any) -> tuple[str, ...]:
    """The files *contract* declares the sandbox verifies; empty when it
    declares none or the declaration is malformed."""
    metadata = getattr(contract, "metadata", None) or {}
    spec = metadata.get(SANDBOX_KEY)
    if not isinstance(spec, dict):
        return ()
    files = spec.get("files")
    if not isinstance(files, list) or not files or len(files) > MAX_SANDBOX_FILES:
        return ()
    if not all(isinstance(f, str) and f.strip() for f in files):
        return ()
    return tuple(files)


__all__ = ["MAX_SANDBOX_FILES", "SANDBOX_KEY", "declared", "sandbox_files"]
