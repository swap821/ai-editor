"""Unit tests for the cloud model catalog (aios.core.catalog).

Breadth: routing across the MANY models a provider offers, discovered once and
cached, with a coarse capability heuristic the router ranks + calibration refines.
"""
from __future__ import annotations

import pytest

from aios.core.catalog import (
    DEFAULT_BONUS,
    catalog_models,
    clear_catalog_cache,
    cloud_capability,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_catalog_cache()
    yield
    clear_catalog_cache()


class FakeCloud:
    def __init__(self, models) -> None:
        self._m = models

    def list_models(self):
        return self._m


def test_capability_tiers() -> None:
    assert cloud_capability("us.anthropic.claude-3-5-sonnet-20241022-v2:0") == 360  # top frontier
    assert cloud_capability("gemini-2.5-pro") == 340                                # -pro -> frontier
    assert cloud_capability("gemini-2.5-flash") == 300                              # flash -> strong
    assert cloud_capability("amazon.nova-lite-v1:0") == 250                         # lite -> light
    assert cloud_capability("a-brand-new-model") == 290                             # unknown


def test_discovers_models_and_forces_in_the_default() -> None:
    c = FakeCloud([{"id": "amazon.nova-pro-v1:0"}, {"id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0"}])
    ids = catalog_models(c, "bedrock", "amazon.nova-lite-v1:0")
    assert "amazon.nova-lite-v1:0" in ids                       # default always present
    assert "amazon.nova-pro-v1:0" in ids
    assert "us.anthropic.claude-3-5-sonnet-20241022-v2:0" in ids


def test_default_not_duplicated_when_already_discovered() -> None:
    c = FakeCloud([{"id": "gemini-2.5-flash"}, {"id": "gemini-2.5-pro"}])
    ids = catalog_models(c, "gemini", "gemini-2.5-flash")
    assert ids.count("gemini-2.5-flash") == 1


def test_falls_back_to_default_on_discovery_error() -> None:
    class Boom:
        def list_models(self):
            raise RuntimeError("no control-plane access")

    assert catalog_models(Boom(), "bedrock", "amazon.nova-lite-v1:0") == ["amazon.nova-lite-v1:0"]


def test_multi_model_discovery_is_cached_until_cleared() -> None:
    ids1 = catalog_models(FakeCloud([{"id": "a"}, {"id": "b"}]), "gemini", "a")
    # a later call (even a different client) returns the cached catalog
    ids2 = catalog_models(FakeCloud([{"id": "z"}]), "gemini", "a")
    assert ids1 == ids2 and "z" not in ids2
    clear_catalog_cache()
    ids3 = catalog_models(FakeCloud([{"id": "z"}]), "gemini", "a")
    assert "z" in ids3  # re-discovered after clear


def test_bare_fallback_is_not_cached() -> None:
    # A single-model fallback must not stick — a real discovery should replace it.
    class Boom:
        def list_models(self):
            raise RuntimeError("down")

    catalog_models(Boom(), "bedrock", "amazon.nova-lite-v1:0")  # caches nothing
    ids = catalog_models(FakeCloud([{"id": "amazon.nova-pro-v1:0"}]), "bedrock", "amazon.nova-lite-v1:0")
    assert "amazon.nova-pro-v1:0" in ids  # the later real discovery won


def test_default_bonus_is_positive() -> None:
    assert DEFAULT_BONUS > 0
