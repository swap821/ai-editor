"""The backend keeps listening when a client drops before its connection is accepted.

2026-11-24: asyncio's Windows proactor closed the backend's listening socket on
WinError 64 (a client that reset mid-accept); the process lived on with :8000
dead, and the operator's envelope signing was refused. 20 such deaths in
data/logs/aios.log since 2026-08-02. Pinned here, both ways: the plain proactor
loses its listener to that error (so the test reaches the defect), the
resilient one keeps serving, and an error that is not a dropped client still
fails as before.
"""

from __future__ import annotations

import asyncio
import socket
import sys

import pytest

from aios.runtime import windows_loop
from aios.runtime.windows_loop import (
    LOOP_FACTORY,
    dropped_client,
    resilient_loop_factory,
)

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="the IOCP proactor is Windows-only"
)


def _oserror(winerror: int) -> OSError:
    exc = OSError(22, "simulated accept failure")
    exc.winerror = winerror  # what the IOCP proactor's overlapped result carries
    return exc


def test_only_a_dropped_client_counts_as_one() -> None:
    for code in (64, 1236, 10053, 10054):
        assert dropped_client(_oserror(code))
    assert not dropped_client(_oserror(5))
    assert not dropped_client(OSError(22, "no winerror"))
    assert not dropped_client(ValueError("not an OSError"))


def test_uvicorn_resolves_the_factory_and_it_runs_a_loop() -> None:
    from uvicorn.importer import import_from_string

    factory = import_from_string(LOOP_FACTORY)
    assert factory is resilient_loop_factory
    with asyncio.Runner(loop_factory=factory) as runner:
        assert runner.run(asyncio.sleep(0, result="ran")) == "ran"


async def _serve_once_after_a_failed_accept() -> tuple[str, list[str]]:
    """A server whose first accept fails as patched; then a normal client."""

    async def handle(reader, writer):
        writer.write(b"ok")
        await writer.drain()
        writer.close()

    loop = asyncio.get_running_loop()
    errors: list[str] = []
    loop.set_exception_handler(
        lambda _loop, ctx: errors.append(str(ctx.get("message")))
    )
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    await asyncio.sleep(0.05)  # let the failed accept's callback run

    def client() -> str:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3) as conn:
                return conn.recv(2).decode() or "empty"
        except OSError:
            return "refused"

    answer = await asyncio.to_thread(client)
    server.close()
    return answer, errors


def _first_accept_fails(monkeypatch, winerror: int) -> None:
    original = asyncio.IocpProactor.accept
    calls = {"n": 0}

    def accept(self, listener):
        calls["n"] += 1
        if calls["n"] == 1:
            future = self._loop.create_future()
            future.set_exception(_oserror(winerror))
            return future
        return original(self, listener)

    monkeypatch.setattr(asyncio.IocpProactor, "accept", accept)


@windows_only
def test_the_plain_proactor_loses_its_listener_to_a_dropped_client(monkeypatch) -> None:
    _first_accept_fails(monkeypatch, 64)
    with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
        answer, errors = runner.run(_serve_once_after_a_failed_accept())
    assert answer == "refused" and "Accept failed on a socket" in errors


@windows_only
def test_the_resilient_loop_keeps_serving_after_a_dropped_client(monkeypatch) -> None:
    _first_accept_fails(monkeypatch, 64)
    with asyncio.Runner(loop_factory=resilient_loop_factory) as runner:
        answer, errors = runner.run(_serve_once_after_a_failed_accept())
    assert answer == "ok" and "Accept failed on a socket" not in errors


@windows_only
def test_any_other_accept_error_still_fails_as_before(monkeypatch) -> None:
    _first_accept_fails(monkeypatch, 5)  # ERROR_ACCESS_DENIED: not a dropped client
    with asyncio.Runner(loop_factory=resilient_loop_factory) as runner:
        answer, errors = runner.run(_serve_once_after_a_failed_accept())
    assert answer == "refused" and "Accept failed on a socket" in errors


@pytest.mark.skipif(sys.platform == "win32", reason="the non-Windows path")
def test_elsewhere_the_factory_is_asyncios_own_loop() -> None:
    loop = resilient_loop_factory()
    try:
        assert type(loop) is type(asyncio.new_event_loop()) or isinstance(
            loop, asyncio.AbstractEventLoop
        )
        assert not hasattr(windows_loop, "ResilientProactor")
    finally:
        loop.close()
