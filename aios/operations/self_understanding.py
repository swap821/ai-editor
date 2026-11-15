"""GAGOS understands itself through organ 28 (2026-11-15).

The operator: "every organ can be used by GAGOS to make itself better and
honestly understand itself first". Organ 28, the Project Understanding Organ,
scans a project into a passport (its stack, folders, how it is built and
tested) and keeps its history. Until now only the operator's own scans fed
it, and none ever ran. Here GAGOS scans its own code, once per commit, as the
hour's checkout of master has it, and the council plans each mission knowing
it: the passport's summary is in the council's trail, beside what GAGOS
remembers of the files (organ 18) and the skills that guide the goal.

The passport is recorded, never made the active project: organ 28 keeps one
active project, the operator's, which his conversations are bound to. It is
evidence for the council's planning, advisory like the rest of the trail; it
decides nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

#: GAGOS's own project in organ 28's store.
GAGOS_PROJECT_ID = "gagos-self"
#: Whose active project GAGOS's passport is: GAGOS's own identity, a digest of
#: a fixed name, so it is never the operator's.
GAGOS_SELF = hashlib.sha256(b"gagos:self-understanding").hexdigest()
#: How much of the passport's architecture summary the council's trail holds.
SUMMARY_CHARS = 400


def _authority():
    from aios.api.deps import (
        get_project_passport_store,
        get_project_understanding_authority,
    )

    return get_project_understanding_authority(get_project_passport_store())


def own_passport(*, authority: Any = None) -> Any | None:
    """GAGOS's latest passport of itself, or None before its first scan."""
    authority = authority or _authority()
    current = authority.store.get_current_with_revision(GAGOS_PROJECT_ID)
    return current[1] if current is not None else None


def understand_self(
    root: Path, head: str, *, authority: Any = None
) -> tuple[Any, bool]:
    """GAGOS's passport of its code at *head* (the checkout in *root*): scanned
    through organ 28 when it has none for *head*, else the one it has. Returns
    ``(passport, scanned)``."""
    from aios.memory.project_passport import harvest_project_passport

    authority = authority or _authority()
    current = own_passport(authority=authority)
    if current is not None and current.verified_at_commit == head:
        return current, False
    scanned = harvest_project_passport(root)
    authority.record_scan(
        root,
        project_id=GAGOS_PROJECT_ID,
        verified_at_commit=head,
        passport=scanned,
        operator_identity_digest=GAGOS_SELF,
        # Recorded, never made the active project: the store keeps ONE active
        # project, and it is the operator's (2026-11-15, found by this test's
        # first run: a scan here replaced his).
        activate=False,
        scan_summary={
            "root": str(root),
            "generatedAt": scanned.generated_at,
            "stack": list(scanned.stack),
        },
    )
    return own_passport(authority=authority), True


def passport_hints(passport: Any | None) -> list[str]:
    """The passport as lines of the council's trail: what GAGOS is made of, and
    how it is built and tested, at the commit it was scanned on."""
    if passport is None:
        return []
    at = (passport.verified_at_commit or "an unknown commit")[:12]
    lines = [
        f"GAGOS's own passport (organ 28, its code at {at}): "
        f"{passport.architecture_summary[:SUMMARY_CHARS]}"
    ]
    for kind, label in (("test", "tested"), ("build", "built")):
        commands = passport.commands.get(kind) or ()
        if commands:
            lines.append(f"GAGOS is {label} with: {'; '.join(commands[:4])}")
    return lines


__all__ = [
    "GAGOS_PROJECT_ID",
    "GAGOS_SELF",
    "own_passport",
    "passport_hints",
    "understand_self",
]
