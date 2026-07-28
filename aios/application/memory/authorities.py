"""Organs 27, 28 and 29's named owners.

The ledger has always named `OperatorTasteModelAuthority`,
`ProjectUnderstandingAuthority`, and `CorrectionLineageAuthority` as these
organs' authority owners, but no such classes existed anywhere -- the
ledger's `authority_owner` field was validated by string comparison against
a registry of strings, so a name that matched nothing was structurally
invisible (Decision A, docs/architecture/GAGOS_54_ORGANS.md).

Each mechanism was already real (`OperatorPreferenceStore`,
`ProjectPassportStore`, `CorrectionRecordStore` in
`aios/infrastructure/memory/human_representation_store.py`, each with a
real production HTTP route); only the owner was missing. These classes are
the single place that owns the domain decision each route was previously
making inline -- not a rename of the store, and not a pass-through: each
method here does real work the route used to do itself.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aios.application.memory.human_representation import (
    build_project_passport_v1,
    is_operator_preference_expired,
)
from aios.domain.memory.human_representation import (
    AuthenticatedCorrectionEventV1,
    CorrectionRecordV1,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.infrastructure.memory.human_representation_store import (
    CorrectionRecordStore,
    OperatorPreferenceSaveResult,
    OperatorPreferenceStore,
    ProjectPassportStore,
)
from aios.memory.conversation import ConversationStateStore
from aios.memory.project_passport import ProjectPassport

_LOGGER = logging.getLogger(__name__)


class OperatorTasteModelAuthority:
    """The one authority over explicit, operator-stated preferences.

    Owns `OperatorPreferenceStore`: builds the typed record from raw
    request fields (moved here from the route), and answers "what does
    this operator currently want" -- organ 31's own `active_preferences`
    contract (status == "active" AND not expired), not merely "what rows
    exist".
    """

    def __init__(self, store: OperatorPreferenceStore) -> None:
        self.store = store

    def record_explicit_preference(
        self,
        *,
        preference_id: str,
        domain: str,
        key: str,
        value: Any,
        scope: str,
        confidence: float,
        review_after: str | None,
        operator_identity_digest: str,
    ) -> tuple[OperatorPreferenceSaveResult, OperatorPreferenceV1 | None]:
        """Build and save one explicit preference. `source_type` and
        `status` are fixed here, not taken from the caller -- "explicit
        only" holds structurally, matching the route's own established
        guarantee, now owned by the authority instead of the HTTP layer."""
        pref = OperatorPreferenceV1(
            preference_id=preference_id,
            domain=domain,
            key=key,
            value=value,
            scope=scope,
            confidence=confidence,
            source_type="explicit_user",
            review_after=review_after,
            status="active",
        )
        result = self.store.save(
            pref, operator_identity_digest=operator_identity_digest
        )
        persisted = self.store.get(preference_id) if result.saved else None
        return result, persisted

    def preferences_for_operator_scope(
        self, operator_identity_digest: str, scope: str
    ) -> tuple[OperatorPreferenceV1, ...]:
        return self.store.list_for_operator_scope(operator_identity_digest, scope)

    def active_preferences_for_operator(
        self, operator_identity_digest: str, scope: str
    ) -> tuple[OperatorPreferenceV1, ...]:
        """Organ 31's exact `active_preferences` contract: status ==
        "active" AND not expired -- a real filter this method owns, not a
        pass-through to the store's own weaker "status == active" query."""
        return tuple(
            pref
            for pref in self.store.list_active_for_operator_scope(
                operator_identity_digest, scope
            )
            if not is_operator_preference_expired(pref)
        )

    def withdraw(
        self, preference_id: str, *, operator_identity_digest: str
    ) -> bool:
        return self.store.withdraw(
            preference_id, operator_identity_digest=operator_identity_digest
        )


class ProjectUnderstandingAuthority:
    """The one authority over what this system durably knows about the
    active project.

    Owns `ProjectPassportStore`: builds the typed passport from a raw scan
    (moved here from the route), records the append-only history + diff,
    and answers "what project is active, and what do we durably know about
    it" as one combined status -- previously assembled inline in the route
    from three separate store calls.
    """

    def __init__(self, store: ProjectPassportStore) -> None:
        self.store = store

    def record_scan(
        self,
        root: Path | str,
        *,
        project_id: str,
        verified_at_commit: str | None,
        passport: ProjectPassport,
        operator_identity_digest: str,
        scan_summary: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        typed_passport: ProjectPassportV1 = build_project_passport_v1(
            root,
            project_id=project_id,
            verified_at_commit=verified_at_commit,
            passport=passport,
        )
        revision, passport_diff = self.store.save_and_diff(typed_passport)
        self.store.set_active(
            project_id,
            scan_summary,
            operator_identity_digest=operator_identity_digest,
        )
        return revision, passport_diff

    def active_project_status(
        self, operator_identity_digest: str
    ) -> dict[str, Any] | None:
        """The exact three-call assembly `project_passport_status()` used
        to do inline in the route: which project is active, its last scan
        summary, and -- if durable history exists -- the revision count,
        passport digest and verified commit. Returns None only when no
        project has ever been marked active for this operator."""
        active = self.store.get_active_for_operator(operator_identity_digest)
        if active is None:
            return None
        project_id, last_scan = active
        durable: dict[str, Any] | None = None
        current = self.store.get_current(project_id)
        if current is not None:
            history = self.store.get_history(project_id)
            durable = {
                "revisionCount": len(history),
                "passportDigest": current.passport_digest,
                "verifiedAtCommit": current.verified_at_commit,
            }
        return {
            "projectId": project_id,
            "lastScan": last_scan,
            "durable": durable,
        }


class CorrectionLineageAuthority:
    """The one authority over corrected interpretations of what a human
    said or meant.

    Owns `CorrectionRecordStore` (the immutable, operator-attributed
    ledger), and owns the compensating-transaction pattern this organ's
    two real routes (correct, clear) each independently needed: append to
    the immutable ledger, and if that fails, roll back the separate,
    mutable `ConversationStateStore` transition that already happened so
    the two stores never disagree about what is "active" -- then re-raise
    the ledger failure, never swallow it. Previously this exact pattern was
    duplicated inline in both routes.
    """

    def __init__(self, store: CorrectionRecordStore) -> None:
        self.store = store

    def append_authenticated_correction(
        self,
        state: ConversationStateStore,
        session_id: str,
        typed_record: CorrectionRecordV1,
        *,
        revision: int,
        corrected_values: dict[str, Any],
        reason: str,
        operator_id: str,
        operator_identity_digest: str,
        authentication_event_id: str,
    ) -> AuthenticatedCorrectionEventV1:
        return self._append_with_rollback(
            state,
            session_id,
            expected_revision=revision,
            expected_status="active",
            rollback_log_message="Authenticated correction rollback failed",
            ledger_log_message="Authenticated correction ledger write failed",
            append=lambda: self.store.append_authenticated(
                typed_record,
                corrected_values=corrected_values,
                reason=reason,
                operator_id=operator_id,
                operator_identity_digest=operator_identity_digest,
                authentication_event_id=authentication_event_id,
            ),
        )

    def append_authenticated_clear(
        self,
        state: ConversationStateStore,
        session_id: str,
        typed_record: CorrectionRecordV1,
        *,
        revision: int,
        reason: str,
        operator_id: str,
        operator_identity_digest: str,
        authentication_event_id: str,
    ) -> AuthenticatedCorrectionEventV1:
        return self._append_with_rollback(
            state,
            session_id,
            expected_revision=revision,
            expected_status="cleared",
            rollback_log_message="Authenticated correction clear rollback failed",
            ledger_log_message="Authenticated correction clear ledger write failed",
            append=lambda: self.store.append_authenticated_clear(
                typed_record,
                reason=reason,
                operator_id=operator_id,
                operator_identity_digest=operator_identity_digest,
                authentication_event_id=authentication_event_id,
            ),
        )

    def _append_with_rollback(
        self,
        state: ConversationStateStore,
        session_id: str,
        *,
        expected_revision: int,
        expected_status: str,
        rollback_log_message: str,
        ledger_log_message: str,
        append: Callable[[], AuthenticatedCorrectionEventV1],
    ) -> AuthenticatedCorrectionEventV1:
        try:
            return append()
        except Exception as exc:  # noqa: BLE001 - preserve the safe local rollback
            try:
                state.rollback_correction_transition(
                    session_id,
                    expected_revision=expected_revision,
                    expected_status=expected_status,
                )
            except Exception as rollback_exc:  # noqa: BLE001 - fail closed on both stores
                _LOGGER.error(rollback_log_message, exc_info=rollback_exc)
            _LOGGER.error(ledger_log_message, exc_info=exc)
            raise

    def lineage_for_session(
        self, session_id: str
    ) -> tuple[CorrectionRecordV1, ...]:
        return self.store.get_lineage(session_id)


__all__ = [
    "CorrectionLineageAuthority",
    "OperatorTasteModelAuthority",
    "ProjectUnderstandingAuthority",
]
