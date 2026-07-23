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


def test_start_stop_lifecycle() -> None:
    async def _run():
        service = DummyQueenService()
        assert service.health()["alive"] is False
        await service.start()
        assert service.health()["alive"] is True
        await service.stop()
        assert service.health()["alive"] is False

    asyncio.run(_run())


def test_submit_returns_verdict_successfully() -> None:
    async def _run():
        service = DummyQueenService(verdict="allow", risk="GREEN")
        await service.start()
        try:
            verdict = await service.submit(_contract())
            assert verdict.queen == "dummy"
            assert verdict.verdict == "allow"
            assert verdict.risk == "GREEN"
        finally:
            await service.stop()

    asyncio.run(_run())


def test_drain_loop_binds_a_trace_context_derived_from_the_queued_mission_id() -> None:
    """Organ 52: _drain_loop() is started once via asyncio.create_task() and
    outlives any single caller, so nothing propagates a trace context into it
    for free -- it must bind one per dequeued item, derived from that item's
    own mission_id, real proof via get_trace_context() inside _handle()."""
    from aios.operations.tracing import get_trace_context

    seen: dict[str, object] = {}

    class TracingQueenService(QueenService):
        def __init__(self) -> None:
            super().__init__("tracing", 16)

        async def _handle(self, contract: MissionContract) -> QueenVerdict:
            seen["trace"] = get_trace_context()
            return QueenVerdict(
                queen=self.name, verdict="allow", risk="GREEN", reason="traced"
            )

    async def _run():
        service = TracingQueenService()
        await service.start()
        try:
            await service.submit(_contract(mission_id="mission-trace-me"))
        finally:
            await service.stop()

    asyncio.run(_run())
    assert seen["trace"].mission_id == "mission-trace-me"


def test_backpressure_returns_defer_when_queue_full() -> None:
    async def _run():
        service = DummyQueenService(queue_depth=1)
        placeholder: asyncio.Future[QueenVerdict] = asyncio.get_event_loop().create_future()
        service._inbox.put_nowait((_contract(), placeholder))

        verdict = await service.submit(_contract())

        assert verdict.verdict == "defer"
        assert verdict.risk == "YELLOW"
        assert "backpressure" in verdict.reason
        placeholder.cancel()

    asyncio.run(_run())


def test_health_reporting_tracks_processed_and_errors() -> None:
    async def _run():
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

    asyncio.run(_run())


def test_register_and_unregister_service() -> None:
    service = DummyQueenService()
    register_service(service)
    assert QUEEN_SERVICES["dummy"] is service

    unregister_service("dummy")
    assert "dummy" not in QUEEN_SERVICES


def test_security_queen_service_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = QueenVerdict(
        queen="security", verdict="allow", risk="GREEN", reason="mocked review"
    )

    from aios.council.queens.security import SecurityQueen

    def _fake_review(self: SecurityQueen, contract: MissionContract) -> QueenVerdict:
        return expected

    monkeypatch.setattr(SecurityQueen, "review", _fake_review)

    async def _run():
        service = SecurityQueenService()
        await service.start()
        try:
            verdict = await service.submit(_contract())
            assert verdict is expected
        finally:
            await service.stop()

    asyncio.run(_run())
