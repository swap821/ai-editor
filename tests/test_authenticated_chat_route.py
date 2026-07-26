"""End-to-end acceptance proof for PR2 authenticated representative chat."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from aios.api import main as api_main
from aios.api.deps import (
    get_conversation_state_store,
    get_correction_record_store,
    get_human_state_hypothesis_store,
    get_identity_service,
    get_operator_preference_store,
    get_project_passport_store,
    get_representative_context_store,
)
from aios.core.alignment import UnderstandingFrame
from aios.infrastructure.identity.sqlite_store import credential_digest
from aios.infrastructure.intelligence.representative_context_store import (
    RepresentativeContextStore,
)
from aios.infrastructure.memory.human_representation_store import (
    CorrectionRecordStore,
    HumanStateHypothesisStore,
    OperatorPreferenceStore,
    ProjectPassportStore,
)
from aios.memory.conversation import ConversationStateStore
from aios.memory.facts import SemanticFacts


class ReceiptCheckingOllama:
    """Local streaming fake that refuses to run before the receipt exists."""

    def __init__(self, receipts: RepresentativeContextStore) -> None:
        self.receipts = receipts
        self.host = "http://127.0.0.1:11434"
        self.messages: list[list[dict[str, Any]]] = []
        self.receipt_was_persisted_before_provider = False

    def stream_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[Any] | None = None,
        model: str | None = None,
    ):
        assert tools is None
        contexts = self.receipts.list_recent()
        assert contexts, "the provider must not run before representative context persists"
        assert self.receipts.get_bundle(contexts[0].request_id) is not None
        self.receipt_was_persisted_before_provider = True
        self.messages.append(messages)
        yield "governed reply"


def _event_data(body: str, event_name: str) -> dict[str, Any]:
    lines = body.replace("\r\n", "\n").split("\n")
    for index, line in enumerate(lines):
        if line != f"event: {event_name}":
            continue
        for candidate in lines[index + 1 :]:
            if candidate.startswith("event: "):
                break
            if candidate.startswith("data: "):
                return json.loads(candidate[len("data: ") :])
    raise AssertionError(f"missing SSE event {event_name!r}")


def _preference_payload(*, scope: str, value: str) -> dict[str, object]:
    return {
        "domain": "communication",
        "key": "style",
        "value": value,
        "scope": scope,
        "confidence": 1.0,
    }


def test_authenticated_chat_uses_real_durable_sources_and_receipt_before_provider(
    tmp_path: Path,
) -> None:
    preferences_path = tmp_path / "preferences.db"
    passports_path = tmp_path / "passports.db"
    corrections_path = tmp_path / "corrections.db"
    conversation_path = tmp_path / "conversation.db"
    human_state_path = tmp_path / "human-state.db"
    contexts_path = tmp_path / "contexts.db"

    facts = SemanticFacts(preferences_path)
    preferences = OperatorPreferenceStore(preferences_path, facts=facts)
    passports = ProjectPassportStore(passports_path)
    corrections = CorrectionRecordStore(corrections_path)
    conversation = ConversationStateStore(conversation_path)
    human_states = HumanStateHypothesisStore(human_state_path)
    receipts = RepresentativeContextStore(contexts_path)
    provider = ReceiptCheckingOllama(receipts)

    api_main.app.dependency_overrides[api_main.get_ollama_client] = lambda: provider
    api_main.app.dependency_overrides[api_main.get_bedrock_client] = lambda: None
    api_main.app.dependency_overrides[api_main.get_gemini_client] = lambda: None
    api_main.app.dependency_overrides[api_main.get_openai_client] = lambda: None
    api_main.app.dependency_overrides[api_main.get_anthropic_client] = lambda: None
    api_main.app.dependency_overrides[api_main.get_semantic_facts] = lambda: facts
    api_main.app.dependency_overrides[api_main.get_semantic_indexer] = lambda: None
    api_main.app.dependency_overrides[get_operator_preference_store] = lambda: preferences
    api_main.app.dependency_overrides[get_project_passport_store] = lambda: passports
    api_main.app.dependency_overrides[get_correction_record_store] = lambda: corrections
    api_main.app.dependency_overrides[get_conversation_state_store] = lambda: conversation
    api_main.app.dependency_overrides[get_human_state_hypothesis_store] = lambda: human_states
    api_main.app.dependency_overrides[get_representative_context_store] = lambda: receipts

    try:
        with TestClient(api_main.app, client=("127.0.0.1", 12345)) as client:
            principal = get_identity_service().get_authenticated_principal(
                client.cookies.get("session_id")
            )
            assert principal is not None
            assert principal.authentication_event_id
            owner_digest = credential_digest(principal.principal_id)

            # An intentionally raw legacy fact acts as a leak sentinel: it is
            # allowed in the legacy store but must never reach the provider.
            sentinel = "RAW_OPERATOR_FACT_MUST_NOT_REACH_PROVIDER"
            assert facts.add_fact("operator", "prefers", json.dumps(sentinel)).committed

            scan = client.post(
                "/api/v1/projects/passport/scan",
                json={"root": ".", "maxFiles": 20},
            )
            assert scan.status_code == 200, scan.text
            project_id = scan.json()["projectId"]
            assert isinstance(project_id, str) and project_id

            status = client.get("/api/v1/projects/passport/status")
            assert status.status_code == 200, status.text
            assert status.json()["projectId"] == project_id
            current_passport = passports.get_current_with_revision(project_id)
            assert current_passport is not None
            revision, _ = current_passport
            assert revision == 1

            global_pref = client.post(
                "/api/v1/preferences",
                json=_preference_payload(scope="global", value="verbose-global"),
            )
            project_pref = client.post(
                "/api/v1/preferences",
                json=_preference_payload(
                    scope=f"project:{project_id}", value="concise-project"
                ),
            )
            assert global_pref.status_code == 200
            assert project_pref.status_code == 200
            global_preference_id = global_pref.json()["preferenceId"]
            project_preference_id = project_pref.json()["preferenceId"]

            conversation.save(
                principal.session_id,
                UnderstandingFrame.fallback(
                    "Review the authenticated chat boundary.", has_context=True
                ).as_dict(),
            )
            correction = client.post(
                "/api/v1/conversation/correction",
                json={
                    "sessionId": "attacker-controlled-body-session",
                    "corrections": {"goal": "Review only the public API"},
                    "reason": "The authenticated operator narrowed the scope.",
                },
            )
            assert correction.status_code == 200
            correction_event_id = correction.json()["authenticatedCorrectionEvent"][
                "event_id"
            ]

            response = client.post(
                "/api/v1/chat",
                json={
                    "transcript": "ugh, this is still broken; keep it concise",
                    "sessionId": "attacker-controlled-body-session",
                },
            )

        assert response.status_code == 200
        assert provider.receipt_was_persisted_before_provider is True
        assert "event: representative_context" in response.text
        assert response.text.index("event: human_state") < response.text.index(
            "event: representative_context"
        ) < response.text.index("event: route")
        assert "governed reply" in response.text

        provider_payload = json.dumps(provider.messages, sort_keys=True)
        assert sentinel not in provider_payload
        assert "concise-project" in provider_payload
        assert "verbose-global" not in provider_payload
        assert "Review only the public API" in provider_payload

        context_event = _event_data(response.text, "representative_context")
        persisted_context = receipts.list_recent(limit=1)[0]
        bundle = receipts.get_bundle(persisted_context.request_id)
        assert bundle is not None
        context, receipt = bundle
        assert context.context_digest == context_event["context_digest"]
        assert receipt.receipt_digest == context_event["receipt_digest"]
        assert receipt.operator_identity_digest == owner_digest
        assert receipt.constitution_digest == principal.constitution_digest
        assert receipt.target == "local"
        assert receipt.consent_status == "not_required_local"
        assert receipt.included_preference_ids == (project_preference_id,)
        assert receipt.included_correction_ids == (correction_event_id,)
        assert receipt.active_project_revision == revision
        assert receipt.human_state_hypothesis_id is not None
        assert receipt.human_state_disposition == "included"
        assert any(
            exclusion.source == "operator_preference"
            and exclusion.reason == "superseded"
            and exclusion.source_id == global_preference_id
            for exclusion in receipt.exclusions
        )

        # Re-open every durable source: the selection proof must survive a
        # process restart, not merely live in one injected Python object.
        restarted_preferences = OperatorPreferenceStore(
            preferences_path, facts=SemanticFacts(preferences_path)
        )
        restarted_passports = ProjectPassportStore(passports_path)
        restarted_corrections = CorrectionRecordStore(corrections_path)
        restarted_conversation = ConversationStateStore(conversation_path)
        restarted_human_states = HumanStateHypothesisStore(human_state_path)
        restarted_receipts = RepresentativeContextStore(contexts_path)

        assert restarted_preferences.list_active_for_operator_scope(
            owner_digest, f"project:{project_id}"
        )[0].preference_id == project_preference_id
        assert restarted_passports.get_active_for_operator(owner_digest)[0] == project_id
        assert restarted_receipts.get_bundle(context.request_id) is not None
        assert restarted_human_states.get_history(principal.session_id)
        assert restarted_corrections.verified_active_projection(
            session_id=principal.session_id,
            operator_id=principal.principal_id,
            operator_identity_digest=owner_digest,
            authentication_event_id=principal.authentication_event_id,
            active_revision=restarted_conversation.active_correction_revision(
                principal.session_id
            ),
        ) is not None
    finally:
        api_main.app.dependency_overrides.clear()

class FailingCorrectionLedger:
    """Forces the route's compensating state transition in a real request."""

    def append_authenticated(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("immutable correction ledger unavailable")

    def append_authenticated_clear(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("immutable correction ledger unavailable")


def test_correction_route_rolls_back_when_authenticated_ledger_write_fails(
    tmp_path: Path,
) -> None:
    conversation = ConversationStateStore(tmp_path / "conversation.db")
    api_main.app.dependency_overrides[get_conversation_state_store] = lambda: conversation
    api_main.app.dependency_overrides[get_correction_record_store] = (
        lambda: FailingCorrectionLedger()
    )
    try:
        with TestClient(api_main.app, client=("127.0.0.1", 12345)) as client:
            principal = get_identity_service().get_authenticated_principal(
                client.cookies.get("session_id")
            )
            assert principal is not None
            base = UnderstandingFrame.fallback(
                "Review the rollback path.", has_context=True
            ).as_dict()
            conversation.save(principal.session_id, base)

            response = client.post(
                "/api/v1/conversation/correction",
                json={
                    "sessionId": principal.session_id,
                    "corrections": {"goal": "This must not remain active"},
                    "reason": "exercise the unavailable-ledger path",
                },
            )

        assert response.status_code == 503, response.text
        assert conversation.active_correction_revision(principal.session_id) is None
        restored = conversation.get(principal.session_id)
        assert restored is not None
        assert restored["goal"] == base["goal"]
        assert not restored.get("correction", {}).get("active", False)
        history = conversation.correction_history(principal.session_id)
        assert history[0]["status"] == "superseded"
        assert history[0]["ledger_rejected_at"] is not None
    finally:
        api_main.app.dependency_overrides.clear()

def test_clear_route_rolls_back_when_authenticated_ledger_write_fails(
    tmp_path: Path,
) -> None:
    conversation = ConversationStateStore(tmp_path / "conversation.db")
    api_main.app.dependency_overrides[get_conversation_state_store] = lambda: conversation
    api_main.app.dependency_overrides[get_correction_record_store] = (
        lambda: FailingCorrectionLedger()
    )
    try:
        with TestClient(api_main.app, client=("127.0.0.1", 12345)) as client:
            principal = get_identity_service().get_authenticated_principal(
                client.cookies.get("session_id")
            )
            assert principal is not None
            base = UnderstandingFrame.fallback(
                "Review the clear rollback path.", has_context=True
            ).as_dict()
            active_revision, persisted = conversation.record_correction(
                principal.session_id,
                before_frame=base,
                after_frame={
                    **base,
                    "goal": "Previously authenticated correction",
                    "correction": {"active": True},
                },
                corrections={"goal": "Previously authenticated correction"},
                corrected_fields=["goal"],
            )

            response = client.post(
                "/api/v1/conversation/correction/clear",
                json={"sessionId": principal.session_id},
            )

        assert response.status_code == 503, response.text
        assert conversation.active_correction_revision(principal.session_id) == active_revision
        restored = conversation.get(principal.session_id)
        assert restored is not None
        assert restored["goal"] == persisted["goal"]
        history = conversation.correction_history(principal.session_id)
        assert history[0]["status"] == "superseded"
        assert history[0]["ledger_rejected_at"] is not None
    finally:
        api_main.app.dependency_overrides.clear()
