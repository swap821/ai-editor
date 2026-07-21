"""P2-5: config robustness — unparseable env-var warnings + startup security banner."""
from __future__ import annotations

import logging
import os

import pytest

from aios.config import (
    PROJECT_ROOT,
    SCOPE_ROOTS,
    _env_bool,
    _env_float,
    _env_int,
    _env_router_tasks,
    startup_banner,
)


class TestScopeRoots:
    """training_ground and lab are both sandbox scope roots (same posture)."""

    def test_training_ground_is_a_scope_root(self):
        assert (PROJECT_ROOT / "training_ground") in SCOPE_ROOTS

    def test_lab_is_a_scope_root(self):
        assert (PROJECT_ROOT / "lab") in SCOPE_ROOTS


def _unique(name: str) -> str:
    """Return a fresh env var name so parallel tests cannot collide."""
    return f"AIOS_TEST_CONFIG_{name}_{os.getpid()}"


class TestUnparseableEnvWarnings:
    """A present-but-unparseable AIOS_* value must warn instead of silently defaulting."""

    def test_int_warns_on_present_non_numeric(self, monkeypatch, caplog):
        name = _unique("INT")
        monkeypatch.setenv(name, "not-a-number")
        with caplog.at_level(logging.WARNING, logger="aios.config"):
            assert _env_int(name, 42) == 42
        assert "Unparseable AIOS env var" in caplog.text
        record = [r for r in caplog.records if "Unparseable" in r.message][-1]
        assert record.var == name
        assert record.value == "not-a-number"
        assert record.default == 42

    def test_int_no_warning_when_unset(self, monkeypatch, caplog):
        name = _unique("INT_UNSET")
        monkeypatch.delenv(name, raising=False)
        with caplog.at_level(logging.WARNING, logger="aios.config"):
            assert _env_int(name, 7) == 7
        assert "Unparseable AIOS env var" not in caplog.text

    def test_int_no_warning_when_blank(self, monkeypatch, caplog):
        name = _unique("INT_BLANK")
        monkeypatch.setenv(name, "")
        with caplog.at_level(logging.WARNING, logger="aios.config"):
            assert _env_int(name, 7) == 7
        assert "Unparseable AIOS env var" not in caplog.text

    def test_float_warns_on_present_non_numeric(self, monkeypatch, caplog):
        name = _unique("FLOAT")
        monkeypatch.setenv(name, "abc")
        with caplog.at_level(logging.WARNING, logger="aios.config"):
            assert _env_float(name, 0.5) == 0.5
        assert "Unparseable AIOS env var" in caplog.text
        record = [r for r in caplog.records if "Unparseable" in r.message][-1]
        assert record.var == name
        assert record.value == "abc"
        assert record.default == 0.5

    def test_bool_warns_on_present_garbage(self, monkeypatch, caplog):
        name = _unique("BOOL")
        monkeypatch.setenv(name, "maybe")
        with caplog.at_level(logging.WARNING, logger="aios.config"):
            # Falls back to the supplied default (True here).
            assert _env_bool(name, True) is True
        assert "Unparseable AIOS env var" in caplog.text
        record = [r for r in caplog.records if "Unparseable" in r.message][-1]
        assert record.var == name
        assert record.value == "maybe"
        assert record.default is True

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", True),
            ("True", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ],
    )
    def test_bool_accepts_valid_literals_without_warning(
        self, monkeypatch, caplog, value, expected
    ):
        name = _unique("BOOL_LIT")
        monkeypatch.setenv(name, value)
        with caplog.at_level(logging.WARNING, logger="aios.config"):
            result = _env_bool(name, not expected)
        assert result is expected
        assert "Unparseable AIOS env var" not in caplog.text

    def test_router_tasks_blank_env_means_local_only(self, monkeypatch):
        name = _unique("ROUTER_TASKS")
        monkeypatch.setenv(name, "")
        assert _env_router_tasks(name, ("reasoning", "coding")) == ()


class TestStartupBanner:
    """The startup banner exposes the resolved security posture, never the secret."""

    def test_banner_contains_security_flags(self, monkeypatch):
        monkeypatch.setattr("aios.config.API_HOST", "127.0.0.1")
        monkeypatch.setattr("aios.config.API_PORT", 8000)
        monkeypatch.setattr("aios.config.API_TOKEN", "")
        monkeypatch.setattr("aios.config.TRUST_PROXY_HEADERS", False)
        monkeypatch.setattr("aios.config.PROBE_BASE", "http://127.0.0.1:8000")
        monkeypatch.setattr("aios.config.ROUTER_CLOUD_TASKS", ("coding",))
        monkeypatch.setattr("aios.config.EARNED_AUTONOMY_ENABLED", False)
        monkeypatch.setattr(
            "aios.config.SCOPE_ROOTS", ("aios/config.py", "training_ground")
        )

        banner = startup_banner()

        assert banner["host"] == "127.0.0.1"
        assert banner["port"] == 8000
        assert banner["token_set"] is False
        assert banner["token_length"] == 0
        assert banner["trust_proxy_headers"] is False
        assert banner["probe_base"] == "http://127.0.0.1:8000"
        assert banner["router_cloud_tasks"] == ["coding"]
        assert banner["earned_autonomy"] is False
        assert banner["scope_roots"] == ["aios/config.py", "training_ground"]

    def test_banner_does_not_leak_token_value(self, monkeypatch):
        secret = "super-secret-token-32-char-long"
        monkeypatch.setattr("aios.config.API_TOKEN", secret)
        banner = startup_banner()
        assert banner["token_set"] is True
        assert banner["token_length"] == len(secret)
        # The raw secret must never appear in the serialised banner.
        serialised = str(banner)
        assert secret not in serialised
