"""Builders for the Slice 28 human-representation contracts.

Each builder wraps an existing subsystem rather than duplicating it:
`build_project_passport_v1` wraps `aios.memory.project_passport.
harvest_project_passport`; `build_correction_record_v1` wraps the frame
dicts `aios.memory.conversation.ConversationStateStore.record_correction`
already produces; `classify_human_state` is a small, deterministic,
regex-based classifier in the same style as
`aios.core.alignment.infer_communication_mode` -- advisory only, never a
trusted model call.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aios.domain.memory.human_representation import (
    CorrectionRecordV1,
    HumanStateHypothesis,
    ProjectPassportV1,
)
from aios.memory.conversation import ConversationStateStore
from aios.memory.project_passport import ProjectPassport, harvest_project_passport


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _project_passport_digest_payload(
    *,
    project_id: str,
    goal: str,
    architecture_summary: str,
    invariants: Sequence[str],
    important_paths: Sequence[str],
    commands: Mapping[str, Sequence[str]],
    environments: Sequence[str],
    current_phase: str,
    known_risks: Sequence[str],
    explicit_human_decisions: Sequence[str],
    verified_at_commit: str | None,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "goal": goal,
        "architecture_summary": architecture_summary,
        "invariants": sorted(invariants),
        "important_paths": sorted(important_paths),
        "commands": {name: sorted(values) for name, values in commands.items()},
        "environments": sorted(environments),
        "current_phase": current_phase,
        "known_risks": sorted(known_risks),
        "explicit_human_decisions": sorted(explicit_human_decisions),
        "verified_at_commit": verified_at_commit,
    }


def build_project_passport_v1(
    root: Path | str,
    *,
    project_id: str,
    verified_at_commit: str | None = None,
    passport: ProjectPassport | None = None,
    invariants: Sequence[str] = (),
    explicit_human_decisions: Sequence[str] = (),
) -> ProjectPassportV1:
    """Wrap `harvest_project_passport` with identity and a stable digest.

    `known_risks` combines the existing scanner's `risky_actions` (actions the
    passport itself flags as risky) and `known_issues` (TODO/FIXME/BUG hits)
    -- both already computed by the wrapped scanner, not re-derived here.
    `explicit_human_decisions` and `invariants` are not mechanically
    derivable from the existing scanner (neither is expressible as a
    syntactic/static-analysis signal without risking a fabricated-looking
    heuristic) -- they default empty, matching the honest absence-of-source
    this organ's own blocker already documented, but are now real
    parameters a caller WITH a genuine source (an operator-supplied form, a
    structured project doc) can actually pass through. Previously these were
    hardcoded to `()` inside this function, so no caller could ever supply
    them even if they had real values -- that ceiling is the part this
    removes.
    """
    scanned = passport if passport is not None else harvest_project_passport(root)
    commands = {
        "install": tuple(scanned.install_commands),
        "run": tuple(scanned.run_commands),
        "build": tuple(scanned.build_commands),
        "test": tuple(scanned.test_commands),
    }
    known_risks = tuple(scanned.risky_actions) + tuple(scanned.known_issues)
    architecture_summary = (
        f"stack: {', '.join(scanned.stack)}; folders: {', '.join(scanned.folder_map)}"
        if scanned.stack or scanned.folder_map
        else ""
    )
    goal = scanned.purpose or (
        scanned.current_goals[0] if scanned.current_goals else ""
    )
    invariants_tuple = tuple(invariants)
    decisions_tuple = tuple(explicit_human_decisions)

    digest_payload = _project_passport_digest_payload(
        project_id=project_id,
        goal=goal,
        architecture_summary=architecture_summary,
        invariants=invariants_tuple,
        important_paths=tuple(scanned.key_files),
        commands=commands,
        environments=tuple(scanned.env_vars),
        current_phase="",
        known_risks=known_risks,
        explicit_human_decisions=decisions_tuple,
        verified_at_commit=verified_at_commit,
    )

    return ProjectPassportV1(
        project_id=project_id,
        goal=goal,
        architecture_summary=architecture_summary,
        invariants=invariants_tuple,
        important_paths=tuple(scanned.key_files),
        commands=commands,
        environments=tuple(scanned.env_vars),
        known_risks=known_risks,
        explicit_human_decisions=decisions_tuple,
        verified_at_commit=verified_at_commit,
        passport_digest=_canonical_digest(digest_payload),
    )


def is_project_passport_stale(
    passport: ProjectPassportV1, *, current_commit_sha: str | None
) -> bool:
    """A passport verified at a different commit than the one under
    evaluation is stale. A passport with no recorded commit at all is
    conservatively treated as stale -- it was never bound to a commit."""
    if passport.verified_at_commit is None or current_commit_sha is None:
        return True
    return passport.verified_at_commit != current_commit_sha


def build_correction_record_v1(
    *,
    correction_id: str,
    session_id: str,
    base_revision: int | None,
    correction_revision: int,
    corrected_fields: Sequence[str],
    before_frame: Mapping[str, Any],
    after_frame: Mapping[str, Any],
) -> CorrectionRecordV1:
    """Wrap the frame dicts `ConversationStateStore.record_correction` already
    persists into a typed, digested record. Does not re-persist anything --
    the store remains the durable owner; this is the typed read/audit view."""
    return CorrectionRecordV1(
        correction_id=correction_id,
        session_id=session_id,
        base_revision=base_revision or 0,
        correction_revision=correction_revision,
        corrected_fields=tuple(corrected_fields),
        prior_interpretation_digest=_canonical_digest(dict(before_frame)),
        current_interpretation_digest=_canonical_digest(dict(after_frame)),
    )


def record_correction_and_build_v1(
    store: ConversationStateStore,
    session_id: str,
    *,
    before_frame: Mapping[str, Any],
    after_frame: Mapping[str, Any],
    corrections: Mapping[str, Any],
    corrected_fields: Sequence[str],
    expected_revision: int | None = None,
) -> tuple[int, dict[str, Any], CorrectionRecordV1]:
    """Record a correction and return the typed `CorrectionRecordV1` alongside it.

    Composes `ConversationStateStore.record_correction` (unchanged, reused
    exactly as every existing caller uses it) with `build_correction_record_v1`
    -- closing organ 29's stated gap ("callers must build one from its raw
    dict output") without touching the store's existing return contract or
    any of its current callers."""
    revision, persisted_after = store.record_correction(
        session_id,
        before_frame=dict(before_frame),
        after_frame=dict(after_frame),
        corrections=dict(corrections),
        corrected_fields=list(corrected_fields),
        expected_revision=expected_revision,
    )
    record = build_correction_record_v1(
        correction_id=f"correction:{session_id}:{revision}",
        session_id=session_id,
        base_revision=expected_revision,
        correction_revision=revision,
        corrected_fields=corrected_fields,
        before_frame=before_frame,
        after_frame=persisted_after,
    )
    return revision, persisted_after, record


def correction_lineage_v1(
    store: ConversationStateStore, session_id: str, limit: int = 20
) -> tuple[CorrectionRecordV1, ...]:
    """The typed read-model query surface organ 29's ledger entry names.

    Reads `ConversationStateStore.correction_lineage_frames` (a new,
    read-only method that adds before/after frames to the existing
    `correction_history` query) and maps each row through
    `build_correction_record_v1`, newest-first -- the same ordering
    `correction_history` already uses."""
    frames = store.correction_lineage_frames(session_id, limit)
    chronological = list(reversed(frames))
    records: list[CorrectionRecordV1] = []
    previous_revision: int | None = None
    for row in chronological:
        revision = int(row["revision"])
        record = build_correction_record_v1(
            correction_id=f"correction:{session_id}:{revision}",
            session_id=session_id,
            base_revision=previous_revision,
            correction_revision=revision,
            corrected_fields=row["corrected_fields"],
            before_frame=row["before_frame"],
            after_frame=row["after_frame"],
        )
        records.append(record)
        previous_revision = revision
    return tuple(reversed(records))


#: Deterministic, human-auditable keyword signals. Order matters: frustration
#: and rushed markers are checked before softer signals so an urgent,
#: frustrated message is not misread as merely "decisive".
_FRUSTRATED_MARKERS = re.compile(
    r"\b(ugh+|argh+|still (broken|not working|failing)|why (is|does)n'?t|"
    r"i('| a)?ve (already |told you )?(said|asked)|this is (wrong|broken)|"
    r"not again|again\?+|come on)\b",
    re.IGNORECASE,
)
_RUSHED_MARKERS = re.compile(
    r"\b(asap|quickly|hurry|right now|no time|urgent(ly)?|fast as|need this now)\b",
    re.IGNORECASE,
)
_DECISIVE_MARKERS = re.compile(
    r"\b(just do|do it|go ahead|proceed|ship it|make it happen|do this now|"
    r"i want you to|i need you to)\b",
    re.IGNORECASE,
)
_UNCERTAIN_MARKERS = re.compile(
    r"\b(not sure|maybe|i think|perhaps|could be|might be|not certain|unsure)\b",
    re.IGNORECASE,
)
_EXPLORATORY_MARKERS = re.compile(
    r"\b(what if|could we|thinking about|exploring|curious|what about|"
    r"how about|let'?s try)\b",
    re.IGNORECASE,
)


def classify_human_state(text: str) -> HumanStateHypothesis:
    """A small, deterministic, advisory guess -- never a model call.

    Checked in a fixed priority order (frustrated/rushed outrank the softer
    signals) so a short, urgent, frustrated message doesn't get classified
    as merely "decisive". Falls back to "neutral" with low confidence when
    nothing matches -- an honest "no signal", not a fabricated one.
    """
    stripped = text.strip()
    if _FRUSTRATED_MARKERS.search(stripped):
        return HumanStateHypothesis(
            state="frustrated",
            confidence=0.6,
            visible_reason="message contains repeated-complaint or frustration markers",
        )
    if _RUSHED_MARKERS.search(stripped):
        return HumanStateHypothesis(
            state="rushed",
            confidence=0.6,
            visible_reason="message contains urgency markers (asap/quickly/hurry)",
        )
    if _DECISIVE_MARKERS.search(stripped):
        return HumanStateHypothesis(
            state="decisive",
            confidence=0.55,
            visible_reason="message contains direct-instruction markers",
        )
    if _UNCERTAIN_MARKERS.search(stripped):
        return HumanStateHypothesis(
            state="uncertain",
            confidence=0.5,
            visible_reason="message contains hedging markers (not sure/maybe/perhaps)",
        )
    if _EXPLORATORY_MARKERS.search(stripped):
        return HumanStateHypothesis(
            state="exploratory",
            confidence=0.5,
            visible_reason="message contains open-ended/what-if markers",
        )
    return HumanStateHypothesis(
        state="neutral",
        confidence=0.3,
        visible_reason="no distinguishing state markers matched",
    )


__all__ = [
    "build_project_passport_v1",
    "is_project_passport_stale",
    "build_correction_record_v1",
    "record_correction_and_build_v1",
    "correction_lineage_v1",
    "classify_human_state",
]
