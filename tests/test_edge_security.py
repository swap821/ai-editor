"""Tests for aios.interfaces.http.edge_security."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from aios.interfaces.http import edge_security
from aios import config


def test_is_private_ip_rejects_public_and_empty():
    assert edge_security.is_private_ip("8.8.8.8") is False
    assert edge_security.is_private_ip("1.1.1.1") is False
    assert edge_security.is_private_ip("") is True
    assert edge_security.is_private_ip("not-an-ip") is True


def test_is_private_ip_accepts_loopback_and_rfc1918():
    assert edge_security.is_private_ip("127.0.0.1") is True
    assert edge_security.is_private_ip("::1") is True
    assert edge_security.is_private_ip("192.168.1.5") is True
    assert edge_security.is_private_ip("10.0.0.1") is True
    assert edge_security.is_private_ip("fd00::1") is True


def _request(client_host="8.8.8.8", headers=None, method="GET", path="/api/test"):
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = client_host
    request.headers = headers or {}
    request.method = method
    request.url.path = path
    return request


def test_real_client_ip_without_proxy():
    request = _request(client_host="8.8.8.8")
    assert edge_security.real_client_ip(request) == "8.8.8.8"


def test_real_client_ip_with_private_proxy_chain():
    orig = config.TRUST_PROXY_HEADERS
    try:
        config.TRUST_PROXY_HEADERS = True
        request = _request(headers={
            "x-forwarded-for": "10.0.0.1, 192.168.1.1, 8.8.8.8"
        }, client_host="10.0.0.2")
        assert edge_security.real_client_ip(request) == "8.8.8.8"
    finally:
        config.TRUST_PROXY_HEADERS = orig


def test_real_client_ip_picks_first_untrusted_chain_link():
    orig = config.TRUST_PROXY_HEADERS
    try:
        config.TRUST_PROXY_HEADERS = True
        request = _request(headers={
            "x-forwarded-for": "8.8.8.8, 192.168.1.1, 10.0.0.1"
        }, client_host="10.0.0.2")
        assert edge_security.real_client_ip(request) == "8.8.8.8"
    finally:
        config.TRUST_PROXY_HEADERS = orig


def test_real_client_ip_ignores_untrusted_proxy_headers():
    orig = config.TRUST_PROXY_HEADERS
    try:
        config.TRUST_PROXY_HEADERS = False
        request = _request(headers={"x-forwarded-for": "8.8.8.8"}, client_host="192.168.1.5")
        assert edge_security.real_client_ip(request) == "192.168.1.5"
    finally:
        config.TRUST_PROXY_HEADERS = orig


def test_validate_cors_origins_parses_and_deduplicates():
    orig = config.API_CORS_ORIGINS
    try:
        config.API_CORS_ORIGINS = ("http://localhost:5173", "https://app.example.com")
        assert set(edge_security.validate_cors_origins(config.API_CORS_ORIGINS)) == {"http://localhost:5173", "https://app.example.com"}
    finally:
        config.API_CORS_ORIGINS = orig


def test_is_allowed_origin_accepts_configured_and_private():
    orig = config.API_CORS_ORIGINS
    try:
        config.API_CORS_ORIGINS = ("http://localhost:5173",)
        assert edge_security.is_allowed_origin("http://localhost:5173") is True
        assert edge_security.is_allowed_origin("http://127.0.0.1:5173") is True
        assert edge_security.is_allowed_origin("http://192.168.1.5:5173") is True
        assert edge_security.is_allowed_origin("http://evil.com") is False
        assert edge_security.is_allowed_origin("http://8.8.8.8") is False
    finally:
        config.API_CORS_ORIGINS = orig


def test_is_allowed_origin_rejects_origin_spoof_attempts():
    assert edge_security.is_allowed_origin("null") is False
    assert edge_security.is_allowed_origin("") is False
    assert edge_security.is_allowed_origin("http://localhost.evil.com") is False


def test_check_host_header_blocks_crlf_injection():
    request = _request(headers={"host": "good.com\r\nX-Injected: bad"})
    resp = edge_security._check_host_header(request)
    assert resp is not None
    assert resp.status_code == 400


def test_check_host_header_allows_loopback_host():
    request = _request(headers={"host": "127.0.0.1:8000"})
    assert edge_security._check_host_header(request) is None


def test_check_bearer_token_is_case_insensitive():
    class FakeConfig:
        API_TOKEN = "super-secret"
    orig = edge_security.config
    edge_security.config = FakeConfig()
    try:
        request = _request(headers={"authorization": "bearer super-secret"})
        assert edge_security.check_bearer_token(request) is True
        request = _request(headers={"authorization": "Bearing super-secret"})
        assert edge_security.check_bearer_token(request) is False
    finally:
        edge_security.config = orig


def test_check_api_token_or_loopback_accepts_loopback_without_token():
    request = _request(client_host="127.0.0.1", path="/api/v1/status")
    assert edge_security.check_api_token_or_loopback(request) is None


def test_check_api_token_or_loopback_rejects_remote_without_token():
    request = _request(client_host="8.8.8.8", path="/api/v1/status")
    resp = edge_security.check_api_token_or_loopback(request)
    assert resp is not None
    assert resp.status_code == 403


def test_check_api_token_or_loopback_accepts_valid_token():
    orig = config.API_TOKEN
    try:
        config.API_TOKEN = "secret"
        request = _request(client_host="8.8.8.8", path="/api/v1/status", headers={"authorization": "bearer secret"})
        assert edge_security.check_api_token_or_loopback(request) is None
    finally:
        config.API_TOKEN = orig


def test_check_mutation_origin_or_token_accepts_browser_origin():
    request = _request(method="POST", headers={"origin": "http://localhost:5173"})
    assert edge_security.check_mutation_origin_or_token(request) is None


def test_check_mutation_origin_or_token_accepts_sec_fetch_site_same_origin():
    request = _request(method="POST", headers={"sec-fetch-site": "same-origin"})
    assert edge_security.check_mutation_origin_or_token(request) is None


def test_check_mutation_origin_or_token_rejects_untrusted_origin():
    request = _request(method="POST", headers={"origin": "http://evil.com"})
    resp = edge_security.check_mutation_origin_or_token(request)
    assert resp is not None
    assert resp.status_code == 403


def test_check_mutation_origin_or_token_accepts_token():
    orig = config.API_TOKEN
    try:
        config.API_TOKEN = "secret"
        request = _request(method="POST", headers={"authorization": "bearer secret"})
        assert edge_security.check_mutation_origin_or_token(request) is None
    finally:
        config.API_TOKEN = orig


def test_cors_origin_list_rejects_crlf_injection():
    with pytest.raises(RuntimeError):
        edge_security.validate_cors_origins(("http://good.com\r\nX-Injected: bad",))


def test_extract_session_id_prefers_cookie():
    async def _inner():
        request = MagicMock(spec=Request)
        request.cookies = {"session_id": "cookie-hash"}
        request.method = "POST"
        request.headers = {"content-type": "application/json"}
        fake_session = MagicMock()
        fake_session.session_hash = "hashed-session"
        sm = MagicMock()
        sm.validate_session.return_value = fake_session
        orig_manager = edge_security.get_session_manager
        edge_security.get_session_manager = lambda: sm
        try:
            sid = await edge_security.extract_session_id(request, allow_body_fallback=True)
            assert sid == "hashed-session"
        finally:
            edge_security.get_session_manager = orig_manager
    asyncio.run(_inner())


def test_extract_session_id_body_fallback_allowed():
    async def _inner():
        request = MagicMock(spec=Request)
        request.cookies = {}
        request.method = "POST"
        request.headers = {"content-type": "application/json"}
        request.body = AsyncMock(return_value=b"{\"sessionId\": \"body-session\"}")
        sid = await edge_security.extract_session_id(request, allow_body_fallback=True)
        assert sid == "body-session"
    asyncio.run(_inner())


def test_extract_session_id_body_fallback_blocked_by_default():
    async def _inner():
        request = MagicMock(spec=Request)
        request.cookies = {}
        request.method = "POST"
        request.headers = {"content-type": "application/json"}
        request.body = AsyncMock(return_value=b"{\"sessionId\": \"body-session\"}")
        sid = await edge_security.extract_session_id(request)
        assert sid is None
    asyncio.run(_inner())


def test_extract_session_id_body_fallback_blocked_for_get():
    async def _inner():
        request = MagicMock(spec=Request)
        request.cookies = {}
        request.method = "GET"
        request.headers = {"content-type": "application/json"}
        request.body = AsyncMock(return_value=b"{\"sessionId\": \"body-session\"}")
        sid = await edge_security.extract_session_id(request, allow_body_fallback=True)
        assert sid is None
    asyncio.run(_inner())
