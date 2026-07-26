"""Truthful local/cloud classification for a model call (Organ 32).

The `CompilationTarget` a request compiles under decides whether
`compile_representative_context()` scrubs free text, withholds
`relevant_memory_refs`, and sends only the project passport's digest. Getting
it wrong is not a labelling error -- it is an egress leak. Measured against the
real compiler:

    target="local"  -> raw "AKIA..." kept in the goal, memory refs passed through
    target="cloud"  -> goal scrubbed, memory refs withheld entirely

So the target must be *derived from the transport actually used*, never from a
role assumption ("the King always runs locally") or a provider label
("it says ollama, so it must be local"). An `OllamaClient` can be pointed at
any host, and a remote Ollama is real egress.

This module is the one place that decision is made, so the authenticated-chat
adapter and the Council adapter cannot drift apart on it.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Iterable
from urllib.parse import urlsplit

#: The provider label that *may* be local. Everything else is cloud outright.
_LOCAL_PROVIDER = "ollama"


def hostname_resolves_only_to_loopback(hostname: str) -> bool:
    """Whether every address `hostname` currently resolves to is loopback.

    Fails closed: any resolution error, or a single non-loopback answer, means
    "not provably local". Resolving rather than trusting the name preserves the
    security property -- a `localhost` repointed off-box resolves non-loopback
    and is correctly treated as egress -- while not misclassifying an ordinary
    `OLLAMA_HOST=http://localhost:11434`. Only the system resolver is
    consulted; no outbound request is made.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        try:
            if not ipaddress.ip_address(address).is_loopback:
                return False
        except ValueError:
            return False
    return True


def is_loopback_http_url(raw_host: object) -> bool:
    """Whether an HTTP base URL provably reaches this machine."""
    if not isinstance(raw_host, str) or raw_host != raw_host.strip():
        return False
    try:
        parsed = urlsplit(raw_host)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return False
        # Accessing ``port`` validates malformed and out-of-range ports.
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return False
        hostname = parsed.hostname
    except ValueError:
        return False
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        pass
    return hostname_resolves_only_to_loopback(hostname)


def classify_transport(*, provider: str, clients: Iterable[Any]) -> str:
    """Return ``"local"`` or ``"cloud"`` for the transport actually in use.

    ``clients`` is every client that could serve the call -- a failover chain
    is classified by its weakest link, because any member of it may end up
    being the one that answers.

    Deliberately conservative in one direction only: anything not *provably*
    loopback is cloud. Being wrong that way over-scrubs; being wrong the other
    way leaks.
    """
    if provider.strip().lower() != _LOCAL_PROVIDER:
        return "cloud"
    candidates = list(clients)
    if not candidates:
        return "cloud"
    for client in candidates:
        if not is_loopback_http_url(getattr(client, "host", None)):
            return "cloud"
    return "local"


__all__ = [
    "classify_transport",
    "hostname_resolves_only_to_loopback",
    "is_loopback_http_url",
]
