import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app, get_cortex_bus
from aios.runtime.cortex_bus import BusEvent, ConsumerReplayGap

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
            payload={"schemaVersion": 1, "eventType": "plan.created", "test": "data"}
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
            payload={"schemaVersion": 1, "eventType": "worker.started", "worker": "test"}
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
        BusEvent(id=1, event_type="turn.started", signature="test", payload={"eventType": "turn.started"}),
        BusEvent(id=2, event_type="worker.started", signature="test", payload={"eventType": "worker.started", "payload": {"role": "worker_a"}}),
        BusEvent(id=3, event_type="worker.started", signature="test", payload={"eventType": "worker.started", "payload": {"role": "worker_b"}}),
        BusEvent(id=4, event_type="worker.dissolved", signature="test", payload={"eventType": "worker.dissolved", "payload": {"role": "worker_a"}}),
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
                with client.stream("GET", "/api/v1/mirror/stream", headers={"Last-Event-ID": "1"}) as response:
                    assert response.status_code == 200
                    
                    lines = []
                    for chunk in response.iter_lines():
                        if chunk:
                            lines.append(chunk)
                        if len(lines) >= 4:
                            break
                            
                    assert len(lines) >= 4, f"Lines length: {len(lines)}. Lines: {lines}"
                    assert lines[0] == "id: 2"
                    assert "eventType" in lines[1]
                    assert "worker.started" in lines[1]
                    
                    assert lines[2] == "id: 1"
                    assert "eventType" in lines[3]
                    assert "plan.created" in lines[3]
    finally:
        app.dependency_overrides.clear()


def test_mirror_stream_emits_snapshot_required_on_replay_gap(mock_cortex_bus):
    mock_cortex_bus.fetch_since.side_effect = ConsumerReplayGap(
        "mirror", 1, 7
    )
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
            async def fake_is_disconnected():
                return True # Disconnect immediately
            mock_is_disconnected.side_effect = fake_is_disconnected
            
            with TestClient(app, client=("127.0.0.1", 12345)) as client:
                with client.stream("GET", "/api/v1/mirror/stream") as response:
                    # iterate to force the generator to run and exit
                    for _ in response.iter_lines():
                        pass
                    
            unsubscribe_mock.assert_called_once()
    finally:
        app.dependency_overrides.clear()
