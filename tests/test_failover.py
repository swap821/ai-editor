"""Unit tests for aios.core.failover (FailoverChatClient)."""

from unittest.mock import MagicMock
import pytest

from aios.application.models.health import ProviderHealthTracker
from aios.core.failover import FailoverChatClient, _is_cloud_provider, _is_local_provider
from aios.core.llm import LLMError
from aios.core.stream_protocol import StreamFinished


def test_provider_classification():
    assert _is_cloud_provider("bedrock") is True
    assert _is_cloud_provider("gemini") is True
    assert _is_cloud_provider("ollama") is False

    assert _is_local_provider("ollama") is True
    assert _is_local_provider("local") is True
    assert _is_local_provider("bedrock") is False


def test_failover_chat_client_init_empty():
    with pytest.raises(ValueError, match="requires at least one candidate"):
        FailoverChatClient([])


def test_failover_chat_success_first_candidate():
    client1 = MagicMock()
    client1.chat.return_value = {"content": "response 1"}

    client2 = MagicMock()

    candidates = [
        (client1, "model-1", "ollama"),
        (client2, "model-2", "ollama"),
    ]

    fc = FailoverChatClient(candidates)
    assert fc.active_provider == "ollama"
    assert fc.active_model == "model-1"

    result = fc.chat([{"role": "user", "content": "hi"}])
    assert result == {"content": "response 1"}
    client1.chat.assert_called_once()
    client2.chat.assert_not_called()


def test_failover_chat_fallback_on_llm_error():
    client1 = MagicMock()
    client1.chat.side_effect = LLMError("Outage on model 1")

    client2 = MagicMock()
    client2.chat.return_value = {"content": "response 2"}

    hook_calls = []
    def on_failover(failed_p, failed_m, next_p, next_m, exc):
        hook_calls.append((failed_p, failed_m, next_p, next_m, str(exc)))

    candidates = [
        (client1, "model-1", "ollama"),
        (client2, "model-2", "ollama"),
    ]

    fc = FailoverChatClient(candidates, on_failover=on_failover)
    result = fc.chat([{"role": "user", "content": "hello"}])
    assert result == {"content": "response 2"}
    assert fc.active_model == "model-2"
    assert len(hook_calls) == 1
    assert hook_calls[0][0] == "ollama"
    assert hook_calls[0][1] == "model-1"
    assert hook_calls[0][3] == "model-2"


def test_failover_chat_all_fail_raises():
    client1 = MagicMock()
    client1.chat.side_effect = LLMError("Error 1")

    client2 = MagicMock()
    client2.chat.side_effect = LLMError("Error 2")

    candidates = [
        (client1, "m1", "ollama"),
        (client2, "m2", "ollama"),
    ]

    fc = FailoverChatClient(candidates)
    with pytest.raises(LLMError, match="all 2 model candidate\(s\) failed"):
        fc.chat([{"role": "user", "content": "test"}])


def test_failover_stream_chat():
    client1 = MagicMock()
    client1.stream_chat.side_effect = LLMError("Stream failed")

    client2 = MagicMock()
    client2.stream_chat.return_value = iter(["chunk 1", "chunk 2"])

    candidates = [
        (client1, "m1", "ollama"),
        (client2, "m2", "ollama"),
    ]

    fc = FailoverChatClient(candidates)
    chunks = list(fc.stream_chat([{"role": "user", "content": "hi"}]))
    assert chunks == ["chunk 1", "chunk 2"]
    assert fc.active_model == "m2"


# --- Organ 34: the failover client reports real outcomes to a tracker -------
def test_failover_chat_records_success_to_provider_health():
    client1 = MagicMock()
    client1.chat.return_value = {"content": "ok"}
    tracker = ProviderHealthTracker()

    fc = FailoverChatClient([(client1, "m1", "ollama")], provider_health=tracker)
    fc.chat([{"role": "user", "content": "hi"}])

    snapshot = tracker.snapshot("ollama")
    assert snapshot.reachable is True
    assert snapshot.circuit_state == "closed"


def test_failover_chat_records_failure_to_provider_health_on_fallback():
    client1 = MagicMock()
    client1.chat.side_effect = LLMError("outage")
    client2 = MagicMock()
    client2.chat.return_value = {"content": "ok"}
    tracker = ProviderHealthTracker()

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )
    fc.chat([{"role": "user", "content": "hi"}])

    failed = tracker.snapshot("bedrock")
    assert failed.recent_failure_count == 1
    succeeded = tracker.snapshot("ollama")
    assert succeeded.reachable is True


def test_failover_chat_without_a_tracker_behaves_exactly_as_before():
    """`provider_health` is optional -- omitting it must not change behavior
    or raise, matching every pre-existing FailoverChatClient caller."""
    client1 = MagicMock()
    client1.chat.return_value = {"content": "ok"}

    fc = FailoverChatClient([(client1, "m1", "ollama")])
    result = fc.chat([{"role": "user", "content": "hi"}])
    assert result == {"content": "ok"}


def test_failover_stream_chat_records_outcomes_to_provider_health():
    client1 = MagicMock()
    client1.stream_chat.side_effect = LLMError("outage")
    client2 = MagicMock()
    client2.stream_chat.return_value = iter(["chunk"])
    tracker = ProviderHealthTracker()

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )
    list(fc.stream_chat([{"role": "user", "content": "hi"}]))

    assert tracker.snapshot("bedrock").recent_failure_count == 1
    assert tracker.snapshot("ollama").reachable is True


def test_failover_stream_chat_with_tools_records_outcomes_to_provider_health():
    client1 = MagicMock()
    client1.stream_chat_with_tools.return_value = iter(
        ["text", StreamFinished(tool_calls=[], content="text")]
    )
    tracker = ProviderHealthTracker()

    fc = FailoverChatClient([(client1, "m1", "ollama")], provider_health=tracker)
    list(fc.stream_chat_with_tools([{"role": "user", "content": "hi"}]))

    assert tracker.snapshot("ollama").reachable is True


def test_failover_stream_chat_with_tools_records_a_failure():
    client1 = MagicMock()
    client1.stream_chat_with_tools.side_effect = LLMError("outage")
    client2 = MagicMock()
    client2.stream_chat_with_tools.return_value = iter(
        ["text", StreamFinished(tool_calls=[], content="text")]
    )
    tracker = ProviderHealthTracker()

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )
    list(fc.stream_chat_with_tools([{"role": "user", "content": "hi"}]))

    assert tracker.snapshot("bedrock").recent_failure_count == 1
    assert tracker.snapshot("ollama").reachable is True


# --- Organ 34: an open circuit is actually consulted, not just recorded ---
def test_failover_chat_skips_a_candidate_with_an_open_circuit():
    client1 = MagicMock()
    client1.chat.return_value = {"content": "should not be called"}
    client2 = MagicMock()
    client2.chat.return_value = {"content": "ok"}
    tracker = ProviderHealthTracker(failure_threshold=1)
    tracker.record_failure("bedrock")  # opens the circuit after 1 failure

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )
    result = fc.chat([{"role": "user", "content": "hi"}])

    assert result == {"content": "ok"}
    client1.chat.assert_not_called()
    assert fc.active_provider == "ollama"


def test_failover_chat_raises_when_every_candidate_has_an_open_circuit():
    client1 = MagicMock()
    client2 = MagicMock()
    tracker = ProviderHealthTracker(failure_threshold=1)
    tracker.record_failure("bedrock")
    tracker.record_failure("ollama")

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )

    with pytest.raises(LLMError):
        fc.chat([{"role": "user", "content": "hi"}])
    client1.chat.assert_not_called()
    client2.chat.assert_not_called()


def test_failover_stream_chat_skips_a_candidate_with_an_open_circuit():
    client1 = MagicMock()
    client2 = MagicMock()
    client2.stream_chat.return_value = iter(["chunk"])
    tracker = ProviderHealthTracker(failure_threshold=1)
    tracker.record_failure("bedrock")

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )
    chunks = list(fc.stream_chat([{"role": "user", "content": "hi"}]))

    assert chunks == ["chunk"]
    client1.stream_chat.assert_not_called()


def test_failover_stream_chat_with_tools_skips_a_candidate_with_an_open_circuit():
    client1 = MagicMock()
    client2 = MagicMock()
    client2.stream_chat_with_tools.return_value = iter(
        ["text", StreamFinished(tool_calls=[], content="text")]
    )
    tracker = ProviderHealthTracker(failure_threshold=1)
    tracker.record_failure("bedrock")

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock"), (client2, "m2", "ollama")],
        provider_health=tracker,
    )
    list(fc.stream_chat_with_tools([{"role": "user", "content": "hi"}]))

    client1.stream_chat_with_tools.assert_not_called()


def test_failover_chat_recovers_after_a_half_open_success():
    """A circuit that has entered recovery (half_open) must still allow
    exactly the recovery probe through -- gating must not permanently lock
    out a provider once its cooldown has elapsed."""
    now = [0.0]
    client1 = MagicMock()
    client1.chat.return_value = {"content": "recovered"}
    tracker = ProviderHealthTracker(
        failure_threshold=1, recovery_after_seconds=10.0, clock=lambda: now[0]
    )
    tracker.record_failure("bedrock")
    now[0] = 11.0  # past recovery_after_seconds -> half_open

    fc = FailoverChatClient([(client1, "m1", "bedrock")], provider_health=tracker)
    result = fc.chat([{"role": "user", "content": "hi"}])

    assert result == {"content": "recovered"}
    client1.chat.assert_called_once()


def test_failover_chat_records_the_real_privacy_audit_when_a_tracker_is_supplied():
    """Organ 50 (second half): the real per-call redaction audit computed
    once before any cloud attempt -- not just logged -- must reach an
    injected PrivacyAuditTracker, labelled with the provider that will
    actually be attempted first."""
    from aios.application.models.privacy_audit import PrivacyAuditTracker

    raw_path = r"C:\Users\kumar\ai-editor\secrets.txt"
    client1 = MagicMock()
    client1.chat.return_value = {"content": "ok"}
    audit_tracker = PrivacyAuditTracker()

    fc = FailoverChatClient(
        [(client1, "m1", "bedrock")], privacy_audit_tracker=audit_tracker
    )
    fc.chat([{"role": "user", "content": f"read {raw_path}"}])

    records = audit_tracker.recent()
    assert len(records) == 1
    assert records[0].provider == "bedrock"
    assert records[0].audit["redacted_paths"] >= 1


def test_failover_chat_never_raises_when_no_privacy_audit_tracker_is_supplied():
    client1 = MagicMock()
    client1.chat.return_value = {"content": "ok"}
    fc = FailoverChatClient([(client1, "m1", "bedrock")])
    result = fc.chat([{"role": "user", "content": "hi"}])
    assert result == {"content": "ok"}


def test_failover_chat_privacy_audit_tracker_untouched_for_local_only_candidates():
    """No cloud candidate means the privacy pre-filter never runs at all --
    confirms the tracker isn't touched for a purely local turn."""
    from aios.application.models.privacy_audit import PrivacyAuditTracker

    client1 = MagicMock()
    client1.chat.return_value = {"content": "ok"}
    audit_tracker = PrivacyAuditTracker()

    fc = FailoverChatClient(
        [(client1, "m1", "ollama")], privacy_audit_tracker=audit_tracker
    )
    fc.chat([{"role": "user", "content": "hi"}])

    assert audit_tracker.recent() == []


def test_failover_stream_chat_with_tools():
    client1 = MagicMock()
    client1.stream_chat_with_tools.return_value = iter([
        "text",
        StreamFinished(tool_calls=[], content="text")
    ])

    candidates = [
        (client1, "m1", "ollama")
    ]

    fc = FailoverChatClient(candidates)
    items = list(fc.stream_chat_with_tools([{"role": "user", "content": "hi"}]))
    assert len(items) == 2
    assert items[0] == "text"
    assert isinstance(items[1], StreamFinished)
