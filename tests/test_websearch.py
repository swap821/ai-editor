"""CRAG Slice 3b — web-search source.

Vendor-flexible web search behind a configurable JSON endpoint (Tavily-compatible).
Default off + inert until an endpoint + key are set; network I/O is injectable so
tests never hit the wire; the query is secret-scrubbed before it leaves the machine;
all failures are fail-soft. See docs/superpowers/specs/2026-06-29-crag-for-gagos-design.md.
"""
from __future__ import annotations

from aios.core.websearch import web_search


def test_web_search_inert_without_config() -> None:
    assert web_search("q", endpoint="", api_key="") == []
    assert web_search("q", endpoint="https://api.example/search", api_key="") == []
    assert web_search("q", endpoint="", api_key="k") == []


def test_web_search_parses_result_content() -> None:
    def fake_fetch(endpoint, payload, api_key):
        assert endpoint == "https://api.example/search"
        assert payload["query"] == "what is crag"
        return {"results": [{"content": "doc one"}, {"content": "doc two"}]}

    docs = web_search(
        "what is crag", endpoint="https://api.example/search", api_key="k", fetch=fake_fetch
    )
    assert docs == ["doc one", "doc two"]


def test_web_search_falls_back_to_snippet_then_title() -> None:
    def fake_fetch(_e, _p, _k):
        return {"results": [{"snippet": "snip"}, {"title": "ttl"}, {"irrelevant": 1}]}

    docs = web_search("q", endpoint="e", api_key="k", fetch=fake_fetch)
    assert docs == ["snip", "ttl"]


def test_web_search_caps_max_results() -> None:
    def fake_fetch(_e, _p, _k):
        return {"results": [{"content": f"d{i}"} for i in range(10)]}

    docs = web_search("q", endpoint="e", api_key="k", max_results=2, fetch=fake_fetch)
    assert docs == ["d0", "d1"]


def test_web_search_skips_non_dict_results() -> None:
    def fake_fetch(_e, _p, _k):
        return {"results": ["not a dict", {"content": "good doc"}]}

    docs = web_search("q", endpoint="e", api_key="k", fetch=fake_fetch)
    assert docs == ["good doc"]


def test_web_search_failsoft_on_error() -> None:
    def boom(_e, _p, _k):
        raise RuntimeError("network down")

    assert web_search("q", endpoint="e", api_key="k", fetch=boom) == []


def test_default_fetch_builds_request_correctly(monkeypatch) -> None:
    # The real-network path (no injected fetch): mock requests.post and assert the
    # request is built right — api_key in body (Tavily-style) AND bearer header, a
    # BOUNDED timeout, raise_for_status enforced, JSON parsed. Never hits the wire.
    import requests

    captured: dict = {}

    class FakeResp:
        def raise_for_status(self) -> None:
            captured["raised"] = True

        def json(self) -> dict:
            return {"results": [{"content": "net doc"}]}

    def fake_post(url, *, json, headers, timeout, **kwargs):
        captured.update(url=url, json=json, headers=headers, timeout=timeout)
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)

    docs = web_search("hello world", endpoint="https://api.example/search", api_key="sk-key")

    assert docs == ["net doc"]
    assert captured["url"] == "https://api.example/search"
    assert captured["json"]["query"] == "hello world"
    assert captured["json"]["api_key"] == "sk-key"  # key in body
    assert captured["json"]["max_results"] == 3
    assert captured["headers"]["Authorization"] == "Bearer sk-key"  # and bearer header
    assert captured["timeout"] == 10  # bounded — no hang
    assert captured["raised"] is True  # HTTP errors surface


def test_web_search_scrubs_secret_from_query() -> None:
    captured = {}

    def fake_fetch(_e, payload, _k):
        captured["query"] = payload["query"]
        return {"results": [{"content": "ok"}]}

    web_search(
        "look up ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa please",
        endpoint="e",
        api_key="k",
        fetch=fake_fetch,
    )
    assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" not in captured["query"]


def test_web_search_redacts_file_paths_before_egress() -> None:
    """Local file paths must never leave the machine in the outbound query --
    the cloud egress path redacts them (privacy_filter) and the web-search
    egress must apply the same rule (deep-audit thematic finding #5)."""
    sent: dict = {}

    def fake_fetch(_e, payload, _k):
        sent.update(payload)
        return {"results": []}

    web_search(
        r"why does C:\Users\kumar\project\secret_notes.txt fail next to /home/kumar/aios/config.py",
        endpoint="e",
        api_key="k",
        fetch=fake_fetch,
    )
    assert "kumar" not in sent["query"]
    assert "secret_notes" not in sent["query"]
    assert "[PATH REDACTED]" in sent["query"]
