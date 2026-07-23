import asyncio
import json
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_capability_authority,
    get_development_tracker,
    get_emergency_stop,
    get_identity_service,
    get_privacy_audit_tracker,
    get_private_executor_service,
    get_provider_health,
)
from aios.api.main import app, get_cortex_bus
from aios.application.capabilities.authority import CapabilityAuthority
from aios.application.executor.service import StructuredExecutorClient
from aios.application.models.health import ProviderHealthTracker
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest
from aios.application.models.privacy_audit import PrivacyAuditTracker
from aios.memory.development import DevelopmentTracker
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopHooks,
    EmergencyStopRequest,
)
from aios.application.identity.service import IdentityService
from aios.application.read_models import projection as projection_module
from aios.runtime.cortex_bus import BusEvent, ConsumerReplayGap, CortexBus
from tests.cortex_event_helpers import append_event

client = TestClient(app, client=("127.0.0.1", 12345))


@pytest.fixture
def mock_cortex_bus():
    bus = MagicMock()
    bus.pending_count.return_value = 42

    # Mock subscribe to yield a fake event when called and return unsubscribe
    def mock_subscribe(handler):
        fake_event = BusEvent(
            id=1,
            event_type="plan.created",
            signature="test",
            payload={"schemaVersion": 1, "eventType": "plan.created", "test": "data"},
        )
        handler(fake_event)
        return MagicMock(name="unsubscribe")

    bus.subscribe = mock_subscribe

    # Mock fetch_since
    bus.fetch_since.return_value = [
        BusEvent(
            id=2,
            event_type="worker.started",
            signature="test",
            payload={
                "schemaVersion": 1,
                "eventType": "worker.started",
                "worker": "test",
            },
        )
    ]

    return bus


def test_mirror_snapshot_offline():
    app.dependency_overrides[get_cortex_bus] = lambda: None
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.get("/api/v1/mirror/snapshot")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "offline"
    finally:
        app.dependency_overrides.clear()


def test_mirror_snapshot_online(mock_cortex_bus):
    app.dependency_overrides[get_cortex_bus] = lambda: mock_cortex_bus
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.get("/api/v1/mirror/snapshot")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "online"
            assert data["pending_events"] == 42
    finally:
        app.dependency_overrides.clear()


def test_mirror_snapshot_projects_truthful_state():
    bus = MagicMock()
    bus.pending_count.return_value = 0

    # Simulate a history: turn starts, worker A starts, worker B starts, worker A dissolves.
    # Resulting state should be phase="active", active_castes=["worker_b"]
    bus.fetch_since.return_value = [
        BusEvent(
            id=1,
            event_type="turn.started",
            signature="test",
            payload={"eventType": "turn.started"},
        ),
        BusEvent(
            id=2,
            event_type="worker.started",
            signature="test",
            payload={"eventType": "worker.started", "payload": {"role": "worker_a"}},
        ),
        BusEvent(
            id=3,
            event_type="worker.started",
            signature="test",
            payload={"eventType": "worker.started", "payload": {"role": "worker_b"}},
        ),
        BusEvent(
            id=4,
            event_type="worker.dissolved",
            signature="test",
            payload={"eventType": "worker.dissolved", "payload": {"role": "worker_a"}},
        ),
    ]

    app.dependency_overrides[get_cortex_bus] = lambda: bus
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            response = client.get("/api/v1/mirror/snapshot")
            assert response.status_code == 200
            data = response.json()
            assert data["phase"] == "active"
            assert set(data["active_castes"]) == {"worker_b"}
    finally:
        app.dependency_overrides.clear()


def test_mirror_snapshot_real_bus_distinguishes_castes_workers_and_missions(
    tmp_path: Path,
) -> None:
    """The real production path (a genuine CortexBus, not a MagicMock double)
    must never conflate worker IDs with role/caste names, and must actually
    surface active missions -- the exact bug found while grounding the
    reconciliation-pass frontend review: mirror.py used to return worker IDs
    under the key "active_castes" and never sent mission data at all."""
    bus = CortexBus(tmp_path / "cortex.db")
    append_event(bus, "mission.running", "mission-1", {"missionId": "mission-1"})
    append_event(
        bus,
        "worker.started",
        "worker-1",
        {"workerId": "worker-1", "missionId": "mission-1", "role": "coder"},
    )

    app.dependency_overrides[get_cortex_bus] = lambda: bus
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert data["active_castes"] == ["coder"]
        assert data["active_workers"] == ["worker-1"]
        assert data["active_missions"] == ["mission-1"]
    finally:
        app.dependency_overrides.clear()
        projection_module._PROJECTIONS.clear()


def test_mirror_stream_requires_bus():
    app.dependency_overrides[get_cortex_bus] = lambda: None
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            with pytest.raises(ValueError, match="CORTEX_BUS must be enabled"):
                client.get("/api/v1/mirror/stream")
    finally:
        app.dependency_overrides.clear()


def test_mirror_stream_live_events(mock_cortex_bus):
    app.dependency_overrides[get_cortex_bus] = lambda: mock_cortex_bus
    try:
        with patch("fastapi.Request.is_disconnected") as mock_is_disconnected:
            call_count = [0]

            async def fake_is_disconnected():
                call_count[0] += 1
                return call_count[0] > 1

            mock_is_disconnected.side_effect = fake_is_disconnected

            with TestClient(app, client=("127.0.0.1", 12345)) as client:
                with client.stream("GET", "/api/v1/mirror/stream") as response:
                    assert response.status_code == 200

                    lines = []
                    for chunk in response.iter_lines():
                        if chunk:
                            lines.append(chunk)
                        if len(lines) >= 2:
                            break

                    # We expect generic SSE: id and data only
                    assert len(lines) >= 2
                    assert lines[0] == "id: 1"
                    assert "eventType" in lines[1]
                    assert "plan.created" in lines[1]
    finally:
        app.dependency_overrides.clear()


def test_mirror_stream_recovery(mock_cortex_bus):
    app.dependency_overrides[get_cortex_bus] = lambda: mock_cortex_bus
    try:
        with patch("fastapi.Request.is_disconnected") as mock_is_disconnected:
            call_count = [0]

            async def fake_is_disconnected():
                call_count[0] += 1
                return call_count[0] > 2

            mock_is_disconnected.side_effect = fake_is_disconnected

            with TestClient(app, client=("127.0.0.1", 12345)) as client:
                with client.stream(
                    "GET", "/api/v1/mirror/stream", headers={"Last-Event-ID": "1"}
                ) as response:
                    assert response.status_code == 200

                    lines = []
                    for chunk in response.iter_lines():
                        if chunk:
                            lines.append(chunk)
                        if len(lines) >= 4:
                            break

                    assert len(lines) >= 4, (
                        f"Lines length: {len(lines)}. Lines: {lines}"
                    )
                    assert lines[0] == "id: 2"
                    assert "eventType" in lines[1]
                    assert "worker.started" in lines[1]

                    assert lines[2] == "id: 1"
                    assert "eventType" in lines[3]
                    assert "plan.created" in lines[3]
    finally:
        app.dependency_overrides.clear()


def test_mirror_stream_emits_snapshot_required_on_replay_gap(mock_cortex_bus):
    mock_cortex_bus.fetch_since.side_effect = ConsumerReplayGap("mirror", 1, 7)
    app.dependency_overrides[get_cortex_bus] = lambda: mock_cortex_bus
    try:
        with patch("fastapi.Request.is_disconnected") as mock_is_disconnected:

            async def fake_is_disconnected():
                return True

            mock_is_disconnected.side_effect = fake_is_disconnected

            with TestClient(app, client=("127.0.0.1", 12345)) as client:
                with client.stream(
                    "GET", "/api/v1/mirror/stream", headers={"Last-Event-ID": "1"}
                ) as response:
                    lines = [line for line in response.iter_lines() if line]

        assert lines[0] == "event: snapshot_required"
        assert '"reason": "replay_gap"' in lines[1]
        assert '"earliest_event_id": 7' in lines[1]
    finally:
        app.dependency_overrides.clear()


def test_mirror_unsubscribe_called(mock_cortex_bus):
    app.dependency_overrides[get_cortex_bus] = lambda: mock_cortex_bus

    unsubscribe_mock = MagicMock()

    def fake_subscribe(handler):
        return unsubscribe_mock

    mock_cortex_bus.subscribe = fake_subscribe

    try:
        with patch("fastapi.Request.is_disconnected") as mock_is_disconnected:
            call_count = [0]

            async def fake_is_disconnected():
                call_count[0] += 1
                return call_count[0] > 1

            mock_is_disconnected.side_effect = fake_is_disconnected

            with TestClient(app, client=("127.0.0.1", 12345)) as client:
                with client.stream("GET", "/api/v1/mirror/stream") as response:
                    # iterate to force the generator to run and exit
                    for _ in response.iter_lines():
                        pass

            unsubscribe_mock.assert_called_once()
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# /api/v1/mirror/governance -- organs 47/48: the first real route exposing
# the Slice 39 typed projections. Unauthenticated by design, matching
# /snapshot's own convention.
# --------------------------------------------------------------------------- #


def _no_op_hooks() -> EmergencyStopHooks:
    return EmergencyStopHooks(
        revoke_capabilities=lambda: None,
        cancel_queued_missions=lambda: None,
        kill_active_workers=lambda: None,
        disable_autonomy=lambda: None,
        preserve_evidence=lambda reason: None,
    )


def test_governance_projection_is_honestly_unavailable_when_unauthenticated(
    tmp_path: Path,
) -> None:
    """No session cookie -> no fabricated constitution. Emergency stop is
    always real and renderable (a never-engaged latch is still a true,
    non-None state), matching project_emergency_stop's own documented
    always-renderable guarantee."""
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert data["constitution"]["version"]["status"] == "unavailable"
            assert data["constitution"]["version"]["value"] is None
            assert data["emergencyStop"]["engaged"]["status"] == "measured"
            assert data["emergencyStop"]["engaged"]["value"] is False
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_shows_the_real_authenticated_operators_constitution(
    tmp_path: Path,
) -> None:
    """A real Human Sovereign session -> a real, non-fabricated constitution
    snapshot attributed to that exact operator, reusing the same
    build_constitution_snapshot() pattern IdentityService already stamps
    onto every Principal."""
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    enrollment = identity.enroll_operator(display_name="Operator")
    authenticated = identity.authenticate_credential(enrollment.enrollment_credential)
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            test_client.cookies.set("session_id", authenticated.session_cookie)
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert data["constitution"]["version"]["status"] == "measured"
            assert data["constitution"]["version"]["value"] == 1
            assert (
                data["constitution"]["ratified_by_operator_id"]["value"]
                == enrollment.operator_id
            )
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_reflects_a_real_engaged_emergency_stop(
    tmp_path: Path,
) -> None:
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    stop.engage(
        EmergencyStopRequest(
            operator_id="operator:1",
            authentication_event_id="event-1",
            reason="test engagement",
        )
    )
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert data["emergencyStop"]["engaged"]["value"] is True
            assert data["emergencyStop"]["reason"]["value"] == "test engagement"
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_provider_health_reflects_a_real_recorded_outcome(
    tmp_path: Path,
) -> None:
    """A never-observed provider must never appear (no fabricated 'healthy'
    placeholder); a real recorded failure must show up truthfully."""
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    tracker = ProviderHealthTracker()
    tracker.record_failure("bedrock")
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    app.dependency_overrides[get_provider_health] = lambda: tracker
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert [p["provider"] for p in data["providerHealth"]] == ["bedrock"]
            assert data["providerHealth"][0]["recent_failure_count"]["value"] == 1
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_approvals_reflects_a_real_pending_capability(
    tmp_path: Path,
) -> None:
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    authority = CapabilityAuthority(db_path=tmp_path / "capabilities.db")
    authority.issue(
        CapabilityBinding(
            operator_id="operator:1",
            device_id="device:1",
            authentication_event_id="event:1",
            session_id="session:1",
            action_type="rollback",
            route="/api/v1/rollback",
            http_method="POST",
            payload_digest=payload_digest({"snapshot_id": "abc"}),
            resource_digest=payload_digest({"snapshot_id": "abc"}),
            mission_id="mission-xyz",
            contract_digest=None,
            policy_version="policy:v1",
            scope="workspace/",
            verification_requirement="rollback_snapshot_restore",
        )
    )
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    app.dependency_overrides[get_capability_authority] = lambda: authority
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert len(data["approvals"]) == 1
            approval = data["approvals"][0]
            assert approval["requested_action"]["value"] == "rollback"
            assert approval["mission_id"]["value"] == "mission-xyz"
            assert approval["scope"]["value"] == "workspace/"
            assert approval["verification_plan"]["value"] == "rollback_snapshot_restore"
            assert approval["risk"]["status"] == "unavailable"
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_routing_decisions_reflects_a_real_recorded_turn(
    tmp_path: Path,
) -> None:
    """Organ 50 (half): a real routing decision, already durably recorded by
    generate_pipeline.py's route_meta(), must surface truthfully -- newest
    first, and with no fabricated value for a field it never recorded."""
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    tracker = DevelopmentTracker(db_path=tmp_path / "memory.db")
    tracker.record(
        "a real turn",
        "unverified",
        metadata={
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "privacy": "cloud",
            "task": "reasoning",
            "auto": True,
            "turn_id": "turn-1",
        },
    )
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    app.dependency_overrides[get_development_tracker] = lambda: tracker
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert len(data["routingDecisions"]) == 1
            decision = data["routingDecisions"][0]
            assert decision["provider"]["value"] == "gemini"
            assert decision["model"]["value"] == "gemini-2.5-flash"
            assert decision["privacy"]["value"] == "cloud"
            assert decision["task"]["value"] == "reasoning"
            assert decision["turn_id"]["value"] == "turn-1"
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_routing_decisions_empty_when_nothing_recorded(
    tmp_path: Path,
) -> None:
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    tracker = DevelopmentTracker(db_path=tmp_path / "memory.db")
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    app.dependency_overrides[get_development_tracker] = lambda: tracker
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            assert response.json()["routingDecisions"] == []
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_privacy_audits_reflects_a_real_recorded_audit(
    tmp_path: Path,
) -> None:
    """Organ 50 (other half): a real PrivacyFilter audit captured by
    PrivacyAuditTracker must surface truthfully."""
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    tracker = PrivacyAuditTracker()
    tracker.record("gemini", {"redacted_paths": 2, "redacted_credentials": 1})
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    app.dependency_overrides[get_privacy_audit_tracker] = lambda: tracker
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            data = response.json()
            assert len(data["privacyAudits"]) == 1
            audit = data["privacyAudits"][0]
            assert audit["provider"]["value"] == "gemini"
            assert audit["redacted_paths"]["value"] == 2
            assert audit["redacted_credentials"]["value"] == 1
    finally:
        app.dependency_overrides.clear()


def test_governance_projection_privacy_audits_empty_when_nothing_recorded(
    tmp_path: Path,
) -> None:
    identity = IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )
    stop = EmergencyStopController(tmp_path / "stop.db", hooks=_no_op_hooks())
    tracker = PrivacyAuditTracker()
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_emergency_stop] = lambda: stop
    app.dependency_overrides[get_privacy_audit_tracker] = lambda: tracker
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/governance")
            assert response.status_code == 200
            assert response.json()["privacyAudits"] == []
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# /api/v1/mirror/executor -- organ 40: the frontend-facing surface for the
# isolated private executor service. Unauthenticated by design, matching
# /snapshot and /governance's own convention.
# --------------------------------------------------------------------------- #


class _HealthResponse:
    """Same fake transport shape used in tests/test_executor_client.py."""

    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self) -> "_HealthResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_executor_status_is_honestly_unconfigured_with_no_base_url_or_token() -> None:
    client = StructuredExecutorClient(base_url="", token="")
    app.dependency_overrides[get_private_executor_service] = lambda: types.SimpleNamespace(
        client=client
    )
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/executor")
            assert response.status_code == 200
            data = response.json()["executor"]
            assert data["configured"]["value"] is False
            assert data["reachable"]["status"] == "unavailable"
            assert data["reason"]["value"] == "private executor service is not configured"
    finally:
        app.dependency_overrides.clear()


def test_executor_status_reflects_a_real_reachable_service() -> None:
    transport = lambda request, timeout: _HealthResponse(
        {"status": "ok", "service": "executor", "runtime": "docker", "token_configured": True}
    )
    client = StructuredExecutorClient(
        base_url="http://executor:8081", token="private-token", transport=transport
    )
    app.dependency_overrides[get_private_executor_service] = lambda: types.SimpleNamespace(
        client=client
    )
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/executor")
            assert response.status_code == 200
            data = response.json()["executor"]
            assert data["configured"]["value"] is True
            assert data["reachable"]["value"] is True
            assert data["runtime"]["value"] == "docker"
            assert data["reason"]["status"] == "unavailable"
    finally:
        app.dependency_overrides.clear()


def test_executor_status_reports_an_honest_reason_when_configured_but_unreachable() -> None:
    def transport(request, timeout):
        raise TimeoutError()

    client = StructuredExecutorClient(
        base_url="http://executor:8081", token="private-token", transport=transport
    )
    app.dependency_overrides[get_private_executor_service] = lambda: types.SimpleNamespace(
        client=client
    )
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
            response = test_client.get("/api/v1/mirror/executor")
            assert response.status_code == 200
            data = response.json()["executor"]
            assert data["configured"]["value"] is True
            assert data["reachable"]["value"] is False
            assert data["runtime"]["status"] == "unavailable"
            assert "timed out" in data["reason"]["value"]
    finally:
        app.dependency_overrides.clear()
