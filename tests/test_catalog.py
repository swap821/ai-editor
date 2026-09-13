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
    assert (
        cloud_capability("us.anthropic.claude-3-5-sonnet-20241022-v2:0") == 360
    )  # top frontier
    assert cloud_capability("gemini-2.5-pro") == 340  # -pro -> frontier
    assert cloud_capability("gemini-2.5-flash") == 300  # flash -> strong
    assert cloud_capability("amazon.nova-lite-v1:0") == 250  # lite -> light
    assert cloud_capability("a-brand-new-model") == 290  # unknown


def test_discovers_models_and_forces_in_the_default() -> None:
    c = FakeCloud(
        [
            {"id": "amazon.nova-pro-v1:0"},
            {"id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0"},
        ]
    )
    ids = catalog_models(c, "bedrock", "amazon.nova-lite-v1:0")
    assert "amazon.nova-lite-v1:0" in ids  # default always present
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

    assert catalog_models(Boom(), "bedrock", "amazon.nova-lite-v1:0") == [
        "amazon.nova-lite-v1:0"
    ]


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
    ids = catalog_models(
        FakeCloud([{"id": "amazon.nova-pro-v1:0"}]), "bedrock", "amazon.nova-lite-v1:0"
    )
    assert "amazon.nova-pro-v1:0" in ids  # the later real discovery won


def test_default_bonus_is_positive() -> None:
    assert DEFAULT_BONUS > 0


# --------------------------------------------------------------------------- #
# Capability scoring against a real 2026 catalog
#
# Measured 2026-09-13 against a live 42-model Bedrock catalog in ap-south-1,
# BEFORE this table was rewritten:
#
#     23 of 42 models scored 290 "unknown" -- glm-5, qwen3-coder-480b,
#        gpt-oss-120b, kimi-k2-thinking, deepseek-v3.2, nemotron-super-120b
#     qwen3-next-80b-a3b scored 250 LIGHT, because the substring "3b" lives
#        inside "a3b"
#     exactly one model scored 360, and it was a 2024 Claude 3 Sonnet
#
# So the router's cold-start pick for a coding task was a two-year-old Sonnet,
# ahead of a 480B coder it had classified as "unknown".
# --------------------------------------------------------------------------- #


def test_a_substring_inside_another_token_no_longer_misfiles_a_model() -> None:
    """THE REGRESSION. An 80B model was scored as a light variant.

    `qwen3-next-80b-a3b` contains "3b" inside "a3b", and `_LIGHT` matched it as
    a substring. This is the same collision class the module's own comment
    documented for "mini" inside "gemini" -- worked around by hand for that
    instance, and missed for this one. Tokenising removes the class.
    """
    assert cloud_capability("qwen.qwen3-next-80b-a3b") == 340

    # The documented instance, still correct.
    assert cloud_capability("gemini-2.5-pro") == 340


def test_a_declared_parameter_count_outranks_a_marketing_word() -> None:
    """`mistral-large-3-675b` scored 300 on the word "large".

    A 675B model plainly out-ranks the tier that word denotes, so a declared
    parameter count is consulted before the keyword tables.
    """
    assert cloud_capability("mistral.mistral-large-3-675b-instruct") == 360
    assert (
        cloud_capability("mistral.mistral-large-2402-v1:0") == 300
    )  # no size declared


def test_mixture_of_experts_ids_are_read_at_their_total_size() -> None:
    """An MoE id names both total and active parameters.

    `qwen3-coder-480b-a35b` is a 480B model with 35B active; total size is the
    better capability signal, so the larger of the two wins.
    """
    assert cloud_capability("qwen.qwen3-coder-480b-a35b-v1:0") == 360
    assert cloud_capability("qwen.qwen3-235b-a22b-2507-v1:0") == 350


def test_current_frontier_families_are_no_longer_unknown() -> None:
    """23 of 42 fell through to the 290 default; these are the worst of them.

    None of these ids declares a parameter count, so without a family table they
    ranked below every keyword match -- including a 2024 Sonnet.
    """
    for model_id in (
        "zai.glm-5",
        "moonshot.kimi-k2-thinking",
        "deepseek.v3.2",
    ):
        assert cloud_capability(model_id) == 340, model_id


def test_a_vendor_named_light_build_stays_light_however_big_it_is() -> None:
    """A vendor calling its own model "nano" is the clearest tier signal there is.

    `nemotron-nano-3-30b` is 30B and still a deliberately small-tier build, so
    the light marker is checked before the size tiers rather than after.
    """
    assert cloud_capability("nvidia.nemotron-nano-3-30b") == 250
    assert cloud_capability("mistral.voxtral-small-24b-2507") == 250


def test_the_band_is_unchanged() -> None:
    """Scores compose with the router's local bias and calibration scale.

    Widening this band would re-weight local-versus-cloud routing -- a policy
    change wearing a heuristic's clothes. This rewrite fixes ordering WITHIN
    cloud candidates and nothing else, so the range must stay where it was.
    """
    sampled = [
        cloud_capability(m)
        for m in (
            "qwen.qwen3-coder-480b-a35b-v1:0",
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "zai.glm-5",
            "gemini-2.5-flash",
            "amazon.nova-lite-v1:0",
            "a-brand-new-model",
            "mistral.ministral-3-3b-instruct",
        )
    ]

    assert min(sampled) >= 250
    assert max(sampled) <= 360


def test_an_unknown_model_still_assumes_broadly_capable() -> None:
    """The default must not become a demotion.

    A model nobody has added to a table is not thereby a weak model; 290 keeps
    it eligible and lets calibration settle it on measured evidence.
    """
    assert cloud_capability("minimax.minimax-m2.5") == 290
    assert cloud_capability("some-vendor.model-nobody-has-seen") == 290
