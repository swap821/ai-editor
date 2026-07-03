"""Web-search source for CRAG external corrective retrieval (Slice 3b).

Vendor-flexible: POSTs the query to a configurable JSON search endpoint
(Tavily-compatible by default) and extracts the result text. It is **default off and
inert** until the operator sets ``AIOS_CRAG_SEARCH_ENDPOINT`` + ``AIOS_CRAG_SEARCH_API_KEY``.

Safety: the query is secret-scrubbed before it leaves the machine, network I/O is
injectable (so tests never hit the wire), the timeout is bounded, and every failure
is fail-soft (returns ``[]`` — external search must never break recall).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from aios.logging_config import get_logger
from aios.security.secret_scanner import scan_and_redact

logger = get_logger(__name__)

#: A network call: ``(endpoint, payload, api_key) -> parsed JSON dict``. Injectable.
Fetch = Callable[[str, dict[str, Any], str], dict[str, Any]]


def _validate_endpoint(endpoint: str) -> None:
    """Reject endpoints that could exfiltrate credentials to non-HTTPS or private hosts."""
    import urllib.parse
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https":
        raise ValueError(f"CRAG search endpoint must use HTTPS, got: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("CRAG search endpoint has no hostname")
    hostname = parsed.hostname.lower()
    if hostname in ("localhost", "127.0.0.1", "::1") or hostname.endswith(".local"):
        raise ValueError(f"CRAG search endpoint must not target local host: {hostname}")


def _default_fetch(endpoint: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    import requests

    _validate_endpoint(endpoint)
    resp = requests.post(
        endpoint,
        json={**payload, "api_key": api_key},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
        allow_redirects=False,
    )
    resp.raise_for_status()
    return resp.json()


def web_search(
    query: str,
    *,
    endpoint: str,
    api_key: str,
    max_results: int = 3,
    fetch: Optional[Fetch] = None,
) -> list[str]:
    """Return up to *max_results* result texts for *query*, or ``[]`` when unconfigured.

    The query is secret-scrubbed before transmission. Result text is taken from each
    result's ``content`` / ``snippet`` / ``title`` (first present). Any network or
    parse error degrades to ``[]``.
    """
    if not endpoint or not api_key:
        return []
    safe_query = scan_and_redact(query).scrubbed
    do_fetch = fetch or _default_fetch
    try:
        data = do_fetch(endpoint, {"query": safe_query, "max_results": max_results}, api_key)
    except Exception as exc:  # noqa: BLE001 - external search must never break recall
        logger.warning("CRAG web search failed", exc_info=exc)
        return []
    results = (data or {}).get("results") or []
    docs: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        text = result.get("content") or result.get("snippet") or result.get("title")
        if text and str(text).strip():
            docs.append(str(text))
    return docs[:max_results]
