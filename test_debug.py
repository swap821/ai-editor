import pytest
from aios.api.main import app, get_cortex_bus
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

def test_debug():
    mock_cortex_bus = MagicMock()
    app.dependency_overrides[get_cortex_bus] = lambda: mock_cortex_bus
    unsubscribe_mock = MagicMock()
    mock_cortex_bus.subscribe.return_value = unsubscribe_mock

    with patch("fastapi.Request.is_disconnected") as mock_is_disconnected:
        async def fake_is_disconnected():
            print("FAKE DISCONNECTED CALLED")
            return True
        mock_is_disconnected.side_effect = fake_is_disconnected

        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            with client.stream("GET", "/api/v1/mirror/stream") as response:
                print("ITERATING")
                for _ in response.iter_lines():
                    print("GOT LINE", _)
        print(f"CALL COUNT: {unsubscribe_mock.call_count}")

test_debug()
