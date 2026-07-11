import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app, get_cortex_bus
from aios.runtime.cortex_bus import BusEvent

client = TestClient(app, client=("127.0.0.1", 12345))

@pytest.fixture
def mock_cortex_bus():
    bus = MagicMock()
    bus.pending_count.return_value = 42
    
    # Mock subscribe to yield a fake event when called
    def mock_subscribe(handler):
        fake_event = BusEvent(
            id=1,
            event_type="plan.created",
            signature="test",
            payload={"test": "data"}
        )
        handler(fake_event)
        
    bus.subscribe = mock_subscribe
    
    # Mock fetch_since
    bus.fetch_since.return_value = [
        BusEvent(
            id=2,
            event_type="worker.started",
            signature="test",
            payload={"worker": "test"}
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
                        if len(lines) >= 3:
                            break
                    
                    # We expect id, event, and data
                    assert len(lines) >= 3
                    assert any(l.startswith("event: plan.created") for l in lines)
                    assert lines[2] == 'data: {"test": "data"}'
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
                        if len(lines) >= 6:
                            break
                            
                    assert len(lines) >= 6, f"Lines length: {len(lines)}. Lines: {lines}"
                    assert lines[0] == "id: 2"
                    assert lines[1] == "event: worker.started"
                    
                    assert lines[3] == "id: 1"
                    assert lines[4] == "event: plan.created"
    finally:
        app.dependency_overrides.clear()
