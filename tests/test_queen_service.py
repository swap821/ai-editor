from __future__ import annotations

import asyncio

import pytest

from aios.council.queen_service import (
    QUEEN_SERVICES,
    QueenService,
    SecurityQueenService,
    register_service,
    unregister_service,
)
from aios.runtime.contracts import MissionContract, QueenVerdict


def _contract(**overrides: object) -> MissionContract:
    data: dict[str, object] = {
        "mission_id": "mission-1",
        "goal": "test goal",
        "worker_type": "frontend",
        "created_by": "tester",
        "workspace_root": "/tmp/workspace",
    }
    data.update(overrides)
    return MissionContract(**data)  # type: ignore[arg-type]


class DummyQueenService(QueenService):
    def __init__(
        self,
        queue_depth: int = 16,
        *,
        verdict: str = "allow",
        risk: str = "GREEN",
        delay: float = 0.0,
    ):
        super().__init__("dummy", queue_depth)
        self._verdict = verdict
        self._risk = risk
        self._delay = delay

    async def _handle(self, contract: MissionContract) -> QueenVerdict:
        if self._delay:
            await asyncio.sleep(self._delay)
        return QueenVerdict(
            queen=self.name, verdict=self._verdict, risk=self._risk, reason="dummy handled"
        )


class ExplodingQueenService(QueenService):
    def __init__(self, queue_depth: int = 16):
        super().__init__("exploding", queue_depth)

    async def _handle(self, contract: MissionContract) -> QueenVerdict:
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    QUEEN_SERVICES.clear()


@pytest.mark.asyncio
async def test_start_stop_lifecycle() -> None:
    service = DummyQueenService()
    assert service.health()["alive"] is False

    await service.start()
    assert service.health()["alive"] is True

    await service.stop()
    assert service.health()["alive"] is False


@pytest.mark.asyncio
async def test_submit_returns_verdict_successfully() -> None:
    service = DummyQueenService(verdict="allow", risk="GREEN")
    await service.start()
    try:
        verdict = await service.submit(_contract())
        assert verdict.queen == "dummy"
        assert verdict.verdict == "allow"
        assert verdict.risk == "GREEN"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_backpressure_returns_defer_when_queue_full() -> None:
    service = DummyQueenService(queue_depth=1)
    # Occupy the only queue slot directly so no drain loop is required to
    # observe QueueFull deterministically.
    placeholder: asyncio.Future[QueenVerdict] = asyncio.get_event_loop().create_future()
    service._inbox.put_nowait((_contract(), placeholder))

    verdict = await service.submit(_contract())

    assert verdict.verdict == "defer"
    assert verdict.risk == "YELLOW"
    assert "backpressure" in verdict.reason
    placeholder.cancel()


@pytest.mark.asyncio
async def test_health_reporting_tracks_processed_and_errors() -> None:
    service = ExplodingQueenService()
    await service.start()
    try:
        verdict = await service.submit(_contract())
        assert verdict.verdict == "deny"
        assert verdict.risk == "RED"

        health = service.health()
        assert health["name"] == "exploding"
        assert health["processed"] == 1
        assert health["errors"] == 1
        assert health["queue_depth"] == 0
    finally:
        await service.stop()


def test_register_and_unregister_service() -> None:
    service = DummyQueenService()
    register_service(service)
    assert QUEEN_SERVICES["dummy"] is service

    unregister_service("dummy")
    assert "dummy" not in QUEEN_SERVICES


@pytest.mark.asyncio
async def test_security_queen_service_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = QueenVerdict(
        queen="security", verdict="allow", risk="GREEN", reason="mocked review"
    )

    from aios.council.queens.security import SecurityQueen

    def _fake_review(self: SecurityQueen, contract: MissionContract) -> QueenVerdict:
        return expected

    monkeypatch.setattr(SecurityQueen, "review", _fake_review)

    service = SecurityQueenService()
    await service.start()
    try:
        verdict = await service.submit(_contract())
        assert verdict is expected
    finally:
        await service.stop()
