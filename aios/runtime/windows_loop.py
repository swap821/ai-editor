"""The backend keeps listening when a client drops before its connection is accepted.

2026-11-24: the operator's standing-envelope signing was refused because nothing
listened on :8000, though the backend process was alive. asyncio's
``ProactorEventLoop`` (Windows) closes a server's listening socket on ANY
``OSError`` an accept raises (``BaseProactorEventLoop._start_serving``: "Accept
failed on a socket", then ``sock.close()``), including
``ERROR_NETNAME_DELETED`` (WinError 64): one client that reset its connection
before the accept completed. The process lives on and the port is dead until
the watchdog's next pass. ``data/logs/aios.log`` holds 20 such deaths from
2026-08-02 to 2026-11-24, seven of them in the last four days. Python 3.12.10
and 3.14.5 both do it.

This loop's proactor treats the errors that mean only "that one client went
away" as such: it starts the next accept instead of failing the server's.
Anything else still fails as before. Elsewhere than Windows the factory is
asyncio's own loop.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

#: Accept errors that mean only that one client went away before its
#: connection was accepted: ERROR_NETNAME_DELETED, ERROR_CONNECTION_ABORTED,
#: WSAECONNABORTED, WSAECONNRESET.
DROPPED_CLIENT_ERRORS = frozenset({64, 1236, 10053, 10054})


def dropped_client(exc: BaseException) -> bool:
    return (
        isinstance(exc, OSError)
        and getattr(exc, "winerror", None) in DROPPED_CLIENT_ERRORS
    )


if sys.platform == "win32":

    class ResilientProactor(asyncio.IocpProactor):
        """An IOCP proactor whose accept outlives a client that dropped mid-accept."""

        def accept(self, listener: Any) -> asyncio.Future[Any]:
            loop = self._loop  # type: ignore[attr-defined]  # set by set_loop()
            outer: asyncio.Future[Any] = loop.create_future()
            pending: list[asyncio.Future[Any]] = []

            def attempt() -> None:
                inner = super(ResilientProactor, self).accept(listener)
                pending[:] = [inner]
                inner.add_done_callback(finished)

            def finished(inner: asyncio.Future[Any]) -> None:
                if outer.done():
                    return
                if inner.cancelled():
                    outer.cancel()
                    return
                exc = inner.exception()
                if exc is None:
                    outer.set_result(inner.result())
                    return
                if dropped_client(exc) and listener.fileno() != -1:
                    logger.info(
                        "a client dropped before its connection was accepted "
                        "(WinError %s); still listening",
                        getattr(exc, "winerror", None),
                    )
                    try:
                        attempt()
                    except OSError as again:
                        outer.set_exception(again)
                    return
                outer.set_exception(exc)

            def on_outer_done(fut: asyncio.Future[Any]) -> None:
                if fut.cancelled() and pending:
                    pending[0].cancel()

            outer.add_done_callback(on_outer_done)
            attempt()
            return outer

    class ResilientProactorEventLoop(asyncio.ProactorEventLoop):
        def __init__(self) -> None:
            super().__init__(proactor=ResilientProactor())


def resilient_loop_factory() -> asyncio.AbstractEventLoop:
    """uvicorn's ``loop=`` factory for the backend: the resilient proactor on
    Windows, asyncio's own loop elsewhere."""
    if sys.platform == "win32":
        return ResilientProactorEventLoop()
    return asyncio.new_event_loop()


#: The import path uvicorn's ``loop=`` takes.
LOOP_FACTORY = "aios.runtime.windows_loop:resilient_loop_factory"

__all__ = [
    "DROPPED_CLIENT_ERRORS",
    "LOOP_FACTORY",
    "dropped_client",
    "resilient_loop_factory",
]
