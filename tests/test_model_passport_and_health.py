"""Slice 31: Model Passports, Qualification, Health and Budget."""

from __future__ import annotations

from aios.application.models import (
    ProviderHealthTracker,
    can_drive_tools,
    is_admitted_for_role,
    is_stale_for_version,
)
from aios.domain.models.contracts import CostProfile, ModelPassportV1


def _passport(**overrides: object) -> ModelPassportV1:
    fields: dict[str, object] = dict(
        passport_id="passport-1",
        provider="ollama",
        exact_model_id="granite3.2:2b",
        model_version="2b-v1",
        privacy_class="local",
        qualified_roles=("classify", "triage"),
        disallowed_roles=(),
        tool_protocol_status="unsupported",
        structured_output_status="supported",
        context_limit=4096,
        output_limit=1024,
        cost_profile=CostProfile(),
        admission_status="admitted",
        passport_digest="a" * 64,
    )
    fields.update(overrides)
    return ModelPassportV1(**fields)


# --- ModelPassportV1 admission ----------------------------------------------


def test_unqualified_model_cannot_receive_production_role() -> None:
    passport = _passport(admission_status="proposed")
    assert is_admitted_for_role(passport, "classify") is False


def test_role_not_in_qualified_roles_is_refused() -> None:
    passport = _passport()
    assert is_admitted_for_role(passport, "summarize") is False


def test_explicitly_disallowed_role_is_refused_even_if_qualified_elsewhere() -> None:
    passport = _passport(
        qualified_roles=("classify", "drive_tools"),
        disallowed_roles=("drive_tools",),
    )
    assert is_admitted_for_role(passport, "drive_tools") is False


def test_model_with_failed_tool_qualification_cannot_drive_tools() -> None:
    passport = _passport(tool_protocol_status="unsupported")
    assert can_drive_tools(passport) is False
    verified = _passport(tool_protocol_status="verified")
    assert can_drive_tools(verified) is True


def test_model_version_change_invalidates_stale_qualification() -> None:
    passport = _passport(model_version="2b-v1")
    assert is_stale_for_version(passport, current_model_version="2b-v2") is True
    assert is_stale_for_version(passport, current_model_version="2b-v1") is False


def test_unversioned_qualification_is_conservatively_stale() -> None:
    passport = _passport(model_version=None)
    assert is_stale_for_version(passport, current_model_version="2b-v1") is True
    assert is_stale_for_version(passport, current_model_version=None) is True


def test_unknown_cost_remains_unknown_not_zero() -> None:
    profile = CostProfile()
    assert profile.input_cost_per_1k is None
    assert profile.output_cost_per_1k is None


# --- ProviderHealthTracker circuit breaker ----------------------------------


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_provider_circuit_opens_after_threshold_failures() -> None:
    clock = _FakeClock()
    tracker = ProviderHealthTracker(failure_threshold=3, clock=clock)
    assert tracker.is_call_allowed("bedrock") is True
    tracker.record_failure("bedrock")
    tracker.record_failure("bedrock")
    assert tracker.is_call_allowed("bedrock") is True
    tracker.record_failure("bedrock")
    assert tracker.is_call_allowed("bedrock") is False
    assert tracker.snapshot("bedrock").circuit_state == "open"


def test_health_recovery_requires_a_successful_controlled_probe() -> None:
    clock = _FakeClock()
    tracker = ProviderHealthTracker(
        failure_threshold=1, recovery_after_seconds=60, clock=clock
    )
    tracker.record_failure("gemini")
    assert tracker.snapshot("gemini").circuit_state == "open"
    assert tracker.is_call_allowed("gemini") is False

    clock.now += 60
    assert tracker.is_call_allowed("gemini") is True
    assert tracker.snapshot("gemini").circuit_state == "half_open"

    # A failed recovery probe re-opens the circuit immediately.
    tracker.record_failure("gemini")
    assert tracker.snapshot("gemini").circuit_state == "open"

    clock.now += 60
    assert tracker.is_call_allowed("gemini") is True
    tracker.record_success("gemini", latency_ms=200.0)
    assert tracker.snapshot("gemini").circuit_state == "closed"


def test_credential_invalid_failure_marks_provider_unreachable() -> None:
    tracker = ProviderHealthTracker()
    tracker.record_failure("openai", credential_invalid=True)
    snapshot = tracker.snapshot("openai")
    assert snapshot.credential_valid is False
    assert snapshot.reachable is False


def test_snapshot_budget_remaining_defaults_to_unknown_not_zero() -> None:
    tracker = ProviderHealthTracker()
    tracker.record_success("anthropic")
    snapshot = tracker.snapshot("anthropic")
    assert snapshot.budget_remaining is None


def test_has_observations_is_false_until_a_real_outcome_is_reported() -> None:
    """Organ 47: snapshot() always returns a value (the default closed/
    reachable state) so it never crashes -- but that default must never be
    mistaken for a real measurement of a provider that was never called."""
    tracker = ProviderHealthTracker()
    assert tracker.has_observations("bedrock") is False

    tracker.record_success("bedrock")
    assert tracker.has_observations("bedrock") is True
    assert tracker.has_observations("gemini") is False
