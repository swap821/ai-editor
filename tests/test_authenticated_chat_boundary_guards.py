"""Safety-boundary proofs for PR2 authenticated representative chat."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from aios.application.intelligence.authenticated_chat import (
    AuthenticatedChatRepresentation,
    AuthenticatedChatRepresentationError,
)
from aios.application.turns.turn_context import TurnContext, TurnMode
from aios.core.failover import FailoverChatClient
from aios.core.llm import OllamaClient
from aios.domain.identity.models import Principal, PrincipalType
from aios.domain.memory.human_representation import (
    HumanStateHypothesis,
    ProjectPassportV1,
)
from aios.infrastructure.identity.sqlite_store import credential_digest

_LOOPBACK_OLLAMA_HOST = "http://127.0.0.1:11434"


class _ReceiptStore:
    def __init__(self) -> None:
        self.bundle: tuple[Any, Any] | None = None

    def save_bundle(self, context: Any, receipt: Any) -> None:
        self.bundle = (context, receipt)


class _PreferenceStore:
    def list_for_operator_scope(self, owner_digest: str, scope: str) -> tuple[Any, ...]:
        assert owner_digest == credential_digest("operator-a")
        return ()


class _PassportStore:
    def __init__(self, passport: ProjectPassportV1, summary: dict[str, object]) -> None:
        self.passport = passport
        self.summary = summary

    def get_active_for_operator(
        self, owner_digest: str
    ) -> tuple[str, dict[str, object]] | None:
        assert owner_digest == credential_digest("operator-a")
        return self.passport.project_id, self.summary

    def get_current_with_revision(
        self, project_id: str
    ) -> tuple[int, ProjectPassportV1]:
        assert project_id == self.passport.project_id
        return 7, self.passport


class _NoActivePassportStore:
    def get_active_for_operator(
        self, owner_digest: str
    ) -> tuple[str, dict[str, object]] | None:
        assert owner_digest == credential_digest("operator-a")
        return None


class _CorrectionStore:
    def verified_active_projection(self, **kwargs: Any) -> None:
        return None


class _ConversationState:
    def active_correction_revision(self, session_id: str) -> None:
        assert session_id == "trusted-session"
        return None


class _ConstitutionAuthority:
    def get_active_snapshot(self, operator_id: str) -> SimpleNamespace:
        assert operator_id == "operator-a"
        return SimpleNamespace(
            snapshot_digest="c" * 64,
            ratified_by_operator_id="operator-a",
        )


class _EmergencyStop:
    def assert_operational(self) -> None:
        return None


class _NeverCalledClient:
    def __init__(
        self, calls: list[str], label: str, *, host: str = _LOOPBACK_OLLAMA_HOST
    ) -> None:
        self.calls = calls
        self.label = label
        self.host = host

    def stream_chat(self, *args: Any, **kwargs: Any):
        self.calls.append(self.label)
        raise AssertionError("authenticated boundary must refuse before provider call")


class _RecordingClient:
    """A client that DOES serve, for cases where the turn should proceed.

    Transport classification is no longer a refusal, so these cases must
    assert on the recorded target rather than on an exception.
    """

    def __init__(
        self, calls: list[str], label: str, *, host: str = _LOOPBACK_OLLAMA_HOST
    ) -> None:
        self.calls = calls
        self.label = label
        self.host = host

    def stream_chat(self, *args: Any, **kwargs: Any):
        self.calls.append(self.label)
        yield "ok"


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


def _context() -> TurnContext:
    return TurnContext(
        turn_id="turn-boundary",
        session_id="trusted-session",
        operator_id="operator-a",
        project_id=None,
        directive="keep it concise",
        mode=TurnMode.CONVERSATION,
        model_id=None,
        approval_tokens=(),
    )


def _passport(
    *, verified_at_commit: str | None = "commit-current"
) -> ProjectPassportV1:
    return ProjectPassportV1(
        project_id="project:chat-proof",
        goal="Keep the chat representation trustworthy",
        architecture_summary="authenticated conversational adapter",
        current_phase="PR2",
        verified_at_commit=verified_at_commit,
        passport_digest="p" * 64,
    )


def _service(
    receipts: _ReceiptStore,
    *,
    passport: ProjectPassportV1 | None = None,
    current_commit: str | None = "commit-current",
) -> AuthenticatedChatRepresentation:
    store: Any
    if passport is None:
        store = _NoActivePassportStore()
    else:
        store = _PassportStore(passport, {"root": "C:/project/chat-proof"})
    return AuthenticatedChatRepresentation(
        principal=_principal(),
        constitution_authority=_ConstitutionAuthority(),
        preference_store=_PreferenceStore(),
        project_passport_store=store,
        correction_store=_CorrectionStore(),
        conversation_state=_ConversationState(),
        representative_context_store=receipts,
        emergency_stop=_EmergencyStop(),
        current_commit_lookup=lambda _root: current_commit,
    )


def _stream(
    service: AuthenticatedChatRepresentation,
    *,
    provider: str,
    chat_client: Any,
    stream_chat_chunks: Any,
):
    return service.stream(
        context=_context(),
        user_text="keep it concise",
        task="conversation",
        provider=provider,
        chat_client=chat_client,
        model="test-model",
        human_state=HumanStateHypothesis(
            state="neutral", confidence=0.8, visible_reason="direct test"
        ),
        human_state_hypothesis_id=1,
        stream_chat_chunks=stream_chat_chunks,
        chat_system_prompt="Base chat policy.",
    )


# --------------------------------------------------------------------------- #
# Transport classification.
#
# These four cases previously asserted that anything other than loopback Ollama
# was REFUSED. That refusal is fatal in the pipeline (it yields an error frame
# and ends the turn), so an authenticated operator asking a coding or reasoning
# question -- both of which AIOS_ROUTER_CLOUD_TASKS permits to route to a cloud
# provider by DEFAULT -- got an error instead of a reply.
#
# The boundary is now a truthful classification rather than a refusal: cloud
# turns still go through the gateway, but the compiler's real cloud path scrubs
# every free-text field, sends only the passport DIGEST, and withholds memory
# refs. The privacy property is kept; the outage is not.
# --------------------------------------------------------------------------- #


def _target_of(receipts: _ReceiptStore) -> str:
    assert receipts.bundle is not None, "a receipt bundle must always be persisted"
    _, receipt = receipts.bundle
    return receipt.target


def test_a_cloud_provider_is_classified_cloud_not_refused() -> None:
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())

    def _provider(*args: Any, **kwargs: Any):
        yield "hello"

    result = _stream(
        service,
        provider="openai",
        chat_client=SimpleNamespace(host=_LOOPBACK_OLLAMA_HOST),
        stream_chat_chunks=_provider,
    )

    assert list(result.chunks) == ["hello"]
    assert _target_of(receipts) == "cloud"
    assert result.receipt.consent_status == "policy_permitted_cloud"
    # The compiled context must agree -- the label is what downstream privacy
    # auditing reads, so a mislabelled local/cloud turn would be a lie.
    assert result.context.privacy_classification == "cloud"


def test_mixed_provider_failover_is_classified_by_its_weakest_link() -> None:
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())
    calls: list[str] = []
    failover = FailoverChatClient(
        [
            (_RecordingClient(calls, "local"), "local-model", "ollama"),
            (_RecordingClient(calls, "cloud"), "cloud-model", "openai"),
        ]
    )

    result = _stream(
        service,
        provider="ollama",
        chat_client=failover,
        stream_chat_chunks=lambda client, messages, *, model: client.stream_chat(
            messages, model=model
        ),
    )
    list(result.chunks)

    # A cloud fallback anywhere in the chain can serve this turn, so the turn
    # is cloud even though the primary is loopback ollama.
    assert _target_of(receipts) == "cloud"


def test_a_remote_ollama_is_real_egress_and_classified_cloud() -> None:
    """The provider label says "ollama", but the bytes leave the machine."""
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())

    def _provider(*args: Any, **kwargs: Any):
        yield "hi"

    result = _stream(
        service,
        provider="ollama",
        chat_client=OllamaClient(host="http://198.51.100.7:11434"),
        stream_chat_chunks=_provider,
    )
    list(result.chunks)

    assert _target_of(receipts) == "cloud"


@pytest.mark.parametrize(
    "host",
    (
        "http://198.51.100.7:11434",
        "http://[2001:db8::1]:11434",
        "http://127.0.0.1:0",  # invalid port -- not provably local
    ),
)
def test_non_loopback_ollama_failover_is_classified_cloud(host: str) -> None:
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())
    calls: list[str] = []
    failover = FailoverChatClient(
        [
            (_RecordingClient(calls, "local"), "local-model", "ollama"),
            (_RecordingClient(calls, "remote", host=host), "remote-model", "ollama"),
        ]
    )

    result = _stream(
        service,
        provider="ollama",
        chat_client=failover,
        stream_chat_chunks=lambda client, messages, *, model: client.stream_chat(
            messages, model=model
        ),
    )
    list(result.chunks)

    assert _target_of(receipts) == "cloud"


def test_localhost_resolving_to_loopback_is_local_not_cloud() -> None:
    """`OLLAMA_HOST=http://localhost:11434` is an entirely ordinary local
    setup. Under the old literal-IP-only rule it was refused outright, which
    broke authenticated chat for anyone using the hostname. It is accepted now
    only because every address it resolves to is loopback -- a `localhost`
    repointed at a remote host still resolves non-loopback and is cloud."""
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())

    def _provider(*args: Any, **kwargs: Any):
        yield "hi"

    result = _stream(
        service,
        provider="ollama",
        chat_client=OllamaClient(host="http://localhost:11434"),
        stream_chat_chunks=_provider,
    )
    list(result.chunks)

    assert _target_of(receipts) == "local"
    assert result.receipt.consent_status == "not_required_local"


def test_a_hostname_resolving_off_box_is_classified_cloud() -> None:
    """The security property the literal-IP rule was protecting: a name that
    resolves somewhere else must not be trusted as local."""
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())

    def _provider(*args: Any, **kwargs: Any):
        yield "hi"

    result = _stream(
        service,
        provider="ollama",
        # example.com is reserved by RFC 2606 and never resolves to loopback;
        # if resolution fails entirely we also fail closed to "cloud".
        chat_client=OllamaClient(host="http://example.com:11434"),
        stream_chat_chunks=_provider,
    )
    list(result.chunks)

    assert _target_of(receipts) == "cloud"


@pytest.mark.parametrize("host", (_LOOPBACK_OLLAMA_HOST, "http://[::1]:11434"))
def test_authenticated_chat_accepts_literal_loopback_ollama_endpoint(host: str) -> None:
    receipts = _ReceiptStore()
    service = _service(receipts, passport=_passport())
    calls: list[str] = []

    def _provider(client: Any, *args: Any, **kwargs: Any):
        calls.append(client.host)
        yield "governed reply"

    result = _stream(
        service,
        provider="ollama",
        chat_client=SimpleNamespace(host=host),
        stream_chat_chunks=_provider,
    )

    assert list(result.chunks) == ["governed reply"]
    assert calls == [host]
    assert receipts.bundle is not None


@pytest.mark.parametrize(
    ("verified_at_commit", "current_commit"),
    (("commit-old", "commit-new"), (None, "commit-current")),
)
def test_authenticated_chat_rejects_stale_or_unverified_project_before_provider(
    verified_at_commit: str | None, current_commit: str | None
) -> None:
    receipts = _ReceiptStore()
    service = _service(
        receipts,
        passport=_passport(verified_at_commit=verified_at_commit),
        current_commit=current_commit,
    )
    calls: list[str] = []

    def _provider(*args: Any, **kwargs: Any):
        calls.append("provider")
        yield "unexpected"

    with pytest.raises(
        AuthenticatedChatRepresentationError, match="stale or unverified"
    ):
        _stream(
            service,
            provider="ollama",
            chat_client=SimpleNamespace(host=_LOOPBACK_OLLAMA_HOST),
            stream_chat_chunks=_provider,
        )

    assert calls == []
    assert receipts.bundle is None


def test_authenticated_chat_formally_excludes_unbound_project_pointer() -> None:
    receipts = _ReceiptStore()
    service = _service(receipts)
    provider_messages: list[list[dict[str, object]]] = []

    def _provider(_client: object, messages: list[dict[str, object]], *, model: str):
        provider_messages.append(messages)
        yield "governed reply"

    result = _stream(
        service,
        provider="ollama",
        chat_client=SimpleNamespace(host=_LOOPBACK_OLLAMA_HOST),
        stream_chat_chunks=_provider,
    )

    assert list(result.chunks) == ["governed reply"]
    assert result.receipt.active_project_revision is None
    assert any(
        exclusion.source == "project_passport"
        and exclusion.field == "active_project"
        and exclusion.reason == "unavailable"
        for exclusion in result.receipt.exclusions
    )
    assert "project:chat-proof" not in str(provider_messages)
