"""P0-1: CORS credential-widening guard.

With ``allow_credentials=True`` the CORS spec forbids a wildcard origin, and a
``"*"`` or host-less/malformed entry in ``AIOS_CORS_ORIGINS`` would silently widen
credentialed cross-origin access. The app validates origins at import time and
fails closed; these tests pin that contract so it can't regress.
"""
from __future__ import annotations

import pytest
from starlette.middleware.cors import CORSMiddleware

from aios.api.main import _validate_cors_origins, app


def test_rejects_wildcard_origin_while_credentialed():
    with pytest.raises(RuntimeError, match=r"\*"):
        _validate_cors_origins(("*",))


def test_rejects_hostless_or_malformed_origins():
    for bad in (("notanorigin",), ("http://",), ("localhost:5173",), ("",)):
        with pytest.raises(RuntimeError):
            _validate_cors_origins(bad)


def test_accepts_explicit_scheme_host_origins():
    good = ("http://localhost:5173", "https://app.example.com")
    assert _validate_cors_origins(good) == list(good)


def test_live_app_cors_is_credentialed_but_never_wildcard():
    """The mounted middleware must never ship credentials + a wildcard origin/method/header."""
    cors = next((m for m in app.user_middleware if m.cls is CORSMiddleware), None)
    assert cors is not None, "CORS middleware not configured"
    opts = getattr(cors, "kwargs", None) or getattr(cors, "options", {})
    assert opts.get("allow_credentials") is True
    assert "*" not in opts.get("allow_origins", []), "credentials + wildcard origin is forbidden"
    assert opts.get("allow_methods") != ["*"], "wildcard methods not narrowed"
    assert opts.get("allow_headers") != ["*"], "wildcard headers not narrowed"
