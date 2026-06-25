"""Regression tests for P0-4: token-auth proxy-header policy.

The production allowlist must never contain Starlette's ``testclient`` host, and
the unauthenticated loopback exemption must be disabled whenever the operator
configures the API to run behind a trusted reverse proxy.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from aios import config
from aios.api.main import app


_API_TOKEN = "a" * 32
_AUTH_HEADER = {"Authorization": f"Bearer {_API_TOKEN}"}
_LOOPBACK_CLIENT = ("127.0.0.1", 12345)
_REMOTE_CLIENT = ("203.0.113.10", 50000)


def _client(app_instance, client_addr=None, headers=None):
    kwargs = {}
    if client_addr is not None:
        kwargs["client"] = client_addr
    if headers is not None:
        kwargs["headers"] = headers
    return TestClient(app_instance, **kwargs)


@pytest.fixture
def no_token_app(monkeypatch):
    """App config with no API token and no trusted proxy headers."""
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", False)
    return app


@pytest.fixture
def token_app(monkeypatch):
    """App config with a strong API token and no trusted proxy headers."""
    monkeypatch.setattr(config, "API_TOKEN", _API_TOKEN)
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", False)
    return app


@pytest.fixture
def proxy_app_no_token(monkeypatch):
    """App config with proxy headers trusted but no API token."""
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", True)
    return app


def test_loopback_allowed_without_token(no_token_app):
    """Direct loopback connections may use the API without a token."""
    with _client(no_token_app, client_addr=_LOOPBACK_CLIENT) as client:
        resp = client.get("/api/v1/audit/verify")
    assert resp.status_code == 200


def test_testclient_rejected_without_token(no_token_app):
    """Starlette's default 'testclient' host is not in the production allowlist."""
    with _client(no_token_app) as client:
        resp = client.get("/api/v1/audit/verify")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "unauthenticated API access is loopback-only"


def test_remote_rejected_without_token(no_token_app):
    """Non-loopback clients must present a token."""
    with _client(no_token_app, client_addr=_REMOTE_CLIENT) as client:
        resp = client.get("/api/v1/audit/verify")
    assert resp.status_code == 403


def test_token_required_regardless_of_host(token_app):
    """When a token is configured, every host must present it."""
    with _client(token_app, client_addr=_REMOTE_CLIENT) as client:
        denied = client.get("/api/v1/audit/verify")
    assert denied.status_code == 401

    with _client(token_app, client_addr=_REMOTE_CLIENT, headers=_AUTH_HEADER) as client:
        allowed = client.get("/api/v1/audit/verify")
    assert allowed.status_code == 200


def test_proxy_headers_trusted_requires_token_at_startup(monkeypatch):
    """A proxy-configured server refuses to start without a token."""
    monkeypatch.setattr(config, "API_TOKEN", "")
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", True)
    with pytest.raises(RuntimeError, match="AIOS_API_TOKEN is required"):
        with TestClient(app):
            pass  # pragma: no cover


def test_proxy_headers_trusted_loopback_must_present_token(token_app):
    """With a trusted proxy, even loopback clients must present the token."""
    with _client(token_app, client_addr=_LOOPBACK_CLIENT) as client:
        denied = client.get("/api/v1/audit/verify")
    assert denied.status_code == 401

    with _client(token_app, client_addr=_LOOPBACK_CLIENT, headers=_AUTH_HEADER) as client:
        allowed = client.get("/api/v1/audit/verify")
    assert allowed.status_code == 200


def test_startup_banner_reports_proxy_header_trust(monkeypatch):
    """The startup banner exposes the proxy-header trust flag."""
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", True)
    banner = config.startup_banner()
    assert banner["trust_proxy_headers"] is True
