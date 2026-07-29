"""Application-level proof for PR2 authenticated representative chat."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from aios.application.intelligence.authenticated_chat import (
    AuthenticatedChatRepresentation,
)
from aios.application.turns.turn_context import TurnContext, TurnMode
from aios.domain.identity.models import Principal, PrincipalType
from aios.domain.memory.human_representation import (
    HumanStateHypothesis,
    OperatorPreferenceV1,
    ProjectPassportV1,
)
from aios.infrastructure.identity.sqlite_store import credential_digest


class _ReceiptStore:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.bundle: tuple[Any, Any] | None = None

    def save_bundle(self, context: Any, receipt: Any) -> None:
        self.order.append("receipt")
        self.bundle = (context, receipt)


class _PreferenceStore:
    def __init__(self, global_prefs: tuple[Any, ...], project_prefs: tuple[Any, ...]) -> None:
        self.global_prefs = global_prefs
        self.project_prefs = project_prefs

    def list_for_operator_scope(self, owner: str, scope: str) -> tuple[Any, ...]:
        assert owner == credential_digest("operator-a")
        return self.global_prefs if scope == "global" else self.project_prefs


class _PreferenceAuthority:
    def __init__(
        self,
        selected: tuple[Any, ...],
        exclusions: tuple[tuple[Any, str], ...] = (),
    ) -> None:
        self.selected = selected
        self.exclusions = exclusions
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def active_preferences_for_scopes(
        self, owner_digest: str, scopes: tuple[str, ...]
    ) -> SimpleNamespace:
        self.calls.append((owner_digest, scopes))
        return SimpleNamespace(included=self.selected, exclusions=self.exclusions)


class _PassportStore:
    def __init__(self, passport: ProjectPassportV1) -> None:
        self.passport = passport

    def get_active_for_operator(self, owner_digest: str) -> tuple[str, dict[str, object]]:
        assert owner_digest == credential_digest("operator-a")
        return self.passport.project_id, {"root": "project:chat-proof"}

    def get_current_with_revision(self, project_id: str) -> tuple[int, ProjectPassportV1]:
        assert project_id == self.passport.project_id
        return 7, self.passport


class _ProjectPassportAuthority:
    def __init__(self, passport: ProjectPassportV1) -> None:
        self.passport = passport
        self.calls: list[tuple[str, object]] = []

    def active_project_for_operator(
        self, owner_digest: str, *, current_commit_lookup: object
    ) -> SimpleNamespace:
        assert owner_digest == credential_digest("operator-a")
        assert callable(current_commit_lookup)
        self.calls.append((owner_digest, current_commit_lookup))
        return SimpleNamespace(
            project_id=self.passport.project_id,
            revision=7,
            passport=self.passport,
        )


class _CorrectionStore:
    def verified_active_projection(self, **kwargs: Any):
        assert kwargs["active_revision"] == 44
        return (
            SimpleNamespace(event_id="authenticated-correction:44"),
            {"goal": "Review only the public API"},
        )


class _CorrectionAuthority:
    def __init__(self, projection: Any) -> None:
        self.projection = projection
        self.calls: list[dict[str, Any]] = []

    def authenticated_active_projection(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.projection


class _ConversationState:
    def active_correction_revision(self, session_id: str) -> int:
        assert session_id == "trusted-session"
        return 44


class _ConstitutionAuthority:
    def get_active_snapshot(self, operator_id: str):
        assert operator_id == "operator-a"
        return SimpleNamespace(
            snapshot_digest="c" * 64,
            ratified_by_operator_id="operator-a",
        )


class _EmergencyStop:
    def assert_operational(self) -> None:
        return None


def _principal() -> Principal:
    return Principal(
        principal_id="operator-a",
        principal_type=PrincipalType.OPERATOR,
        display_name="Operator A",
        session_id="trusted-session",
        authentication_level="privileged",
        authenticated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        authentication_event_id="auth-event-a",
        constitution_digest="c" * 64,
    )


def _preference(preference_id: str, *, scope: str, value: object) -> OperatorPreferenceV1:
    return OperatorPreferenceV1(
        preference_id=preference_id,
        domain="communication",
        key="style",
        value=value,
        scope=scope,
        confidence=1.0,
        source_type="explicit_user",
        status="active",
    )


def _context() -> TurnContext:
    return TurnContext(
        turn_id="turn-authenticated",
        session_id="trusted-session",
        operator_id="operator-a",
        project_id=None,
        directive="ugh, this is still broken; keep it concise",
        mode=TurnMode.CONVERSATION,
        model_id=None,
        approval_tokens=(),
    )


def test_authenticated_chat_uses_only_representative_context_and_persists_receipt() -> None:
    order: list[str] = []
    receipts = _ReceiptStore(order)
    preference_authority = _PreferenceAuthority(
        selected=(_preference("pref-project", scope="project:chat-proof", value="concise"),),
        exclusions=(
            (
                _preference("pref-global", scope="global", value="verbose"),
                "superseded",
            ),
        ),
    )
    passport = ProjectPassportV1(
        project_id="project:chat-proof",
        goal="Keep the chat representation trustworthy",
        architecture_summary="authenticated conversational adapter",
        current_phase="PR2",
        verified_at_commit="commit-current",
        passport_digest="p" * 64,
    )
    project_authority = _ProjectPassportAuthority(passport)
    correction_authority = _CorrectionAuthority(
        (
            SimpleNamespace(event_id="authenticated-correction:44"),
            {"goal": "Review only the public API"},
        )
    )
    service = AuthenticatedChatRepresentation(
        principal=_principal(),
        constitution_authority=_ConstitutionAuthority(),
        preference_store=_PreferenceStore(
            (_preference("pref-global", scope="global", value="verbose"),),
            (_preference("pref-project", scope="project:chat-proof", value="concise"),),
        ),
        preference_authority=preference_authority,
        project_passport_authority=project_authority,
        project_passport_store=_PassportStore(passport),
        correction_authority=correction_authority,
        correction_store=_CorrectionStore(),
        conversation_state=_ConversationState(),
        representative_context_store=receipts,
        emergency_stop=_EmergencyStop(),
        now=lambda: datetime.now(timezone.utc),
        current_commit_lookup=lambda _root: "commit-current",
    )
    provider_messages: list[list[dict[str, object]]] = []

    def _stream_chunks(client: object, messages: list[dict[str, object]], *, model: str):
        assert order == ["receipt"]
        provider_messages.append(messages)
        order.append("provider")
        yield "governed reply"

    result = service.stream(
        context=_context(),
        user_text="ugh, this is still broken; keep it concise",
        task="conversation",
        provider="ollama",
        chat_client=SimpleNamespace(host="http://127.0.0.1:11434"),
        model="local-model",
        human_state=HumanStateHypothesis(
            state="frustrated",
            confidence=0.6,
            visible_reason="frustration markers present",
        ),
        human_state_hypothesis_id=73,
        stream_chat_chunks=_stream_chunks,
        chat_system_prompt="Base chat policy.",
    )

    assert receipts.bundle == (result.context, result.receipt)
    assert preference_authority.calls == [
        (credential_digest("operator-a"), ("global", "project:project:chat-proof"))
    ]
    assert len(project_authority.calls) == 1
    assert len(correction_authority.calls) == 1
    assert correction_authority.calls[0]["active_revision"] == 44
    assert result.receipt.included_preference_ids == ("pref-project",)
    assert result.receipt.included_correction_ids == ("authenticated-correction:44",)
    assert result.receipt.active_project_revision == 7
    assert result.receipt.human_state_hypothesis_id == 73
    assert result.receipt.human_state_disposition == "included"
    assert list(result.chunks) == ["governed reply"]
    assert order == ["receipt", "provider"]

    rendered = str(provider_messages)
    assert "concise" in rendered
    assert "verbose" not in rendered
    assert passport.passport_digest in rendered
    assert "Review only the public API" in rendered
    assert "frustrated" in rendered
    assert "operator_facts" not in rendered


def test_authenticated_chat_abstains_from_low_confidence_human_state() -> None:
    receipts = _ReceiptStore([])
    preference_authority = _PreferenceAuthority(selected=())
    passport = ProjectPassportV1(
        project_id="project:chat-proof",
        goal="Keep the chat representation trustworthy",
        architecture_summary="authenticated conversational adapter",
        verified_at_commit="commit-current",
        passport_digest="p" * 64,
    )
    project_authority = _ProjectPassportAuthority(passport)
    correction_authority = _CorrectionAuthority(None)
    service = AuthenticatedChatRepresentation(
        principal=_principal(),
        constitution_authority=_ConstitutionAuthority(),
        preference_store=_PreferenceStore((), ()),
        preference_authority=preference_authority,
        project_passport_authority=project_authority,
        project_passport_store=_PassportStore(passport),
        correction_authority=correction_authority,
        correction_store=_CorrectionStore(),
        conversation_state=_ConversationState(),
        representative_context_store=receipts,
        emergency_stop=_EmergencyStop(),
        now=lambda: datetime.now(timezone.utc),
        current_commit_lookup=lambda _root: "commit-current",
    )

    result = service.stream(
        context=_context(),
        user_text="please help",
        task="conversation",
        provider="ollama",
        chat_client=SimpleNamespace(host="http://127.0.0.1:11434"),
        model="local-model",
        human_state=HumanStateHypothesis(
            state="uncertain", confidence=0.59, visible_reason="weak marker"
        ),
        human_state_hypothesis_id=74,
        stream_chat_chunks=lambda *args, **kwargs: iter(("reply",)),
        chat_system_prompt="Base chat policy.",
    )

    assert result.receipt.human_state_disposition == "abstained"
    assert result.receipt.human_state_hypothesis_id == 74
    assert any(
        exclusion.reason == "below_confidence_threshold"
        for exclusion in result.receipt.exclusions
    )