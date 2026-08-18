"""The local clerk must fit the host it runs on.

`AIOS_LLM_MODEL` is the LOCAL CLERK -- the model the default-on aliveness organs
(CRAG, reflection, narrative self-model, facts extraction) invoke per turn. It is
not the cloud brain, which is chosen per request.

It was llama3.1:8b: 5.6GB resident, pulled once per turn even when every agent
turn is cloud-routed. On a 16GB host that reached 96% memory within a minute and
killed two consecutive 30-minute endurance runs. The harness reported those as
ConnectionResetError -- indistinguishable from a killed backend -- so the first
diagnosis went down the wrong path entirely.

The endurance run that finally completed used qwen2.5:3b (2.2GB): 37 turns over
30.7 minutes, backend memory growth 7.3MB, latency stable.

This test does not forbid a bigger clerk. It exists so that raising it is a
decision someone makes on purpose, with the measurement in front of them.
"""
from __future__ import annotations

from aios import config

#: Rough resident cost in GB of the local models on this host, measured via
#: `ollama ps` on 2026-08-18. Used to catch a default that cannot fit alongside
#: a backend, a browser and a 30-minute measurement on a 16GB machine.
_RESIDENT_GB = {
    "qwen2.5:1.5b": 1.0,
    "granite3.3:2b": 1.5,
    "gemma2:2b": 1.6,
    "qwen2.5:3b": 2.2,
    "granite4.1:3b": 2.1,
    "phi4-mini:3.8b": 2.5,
    "nemotron-mini:4b": 2.7,
    "gemma3:4b": 3.3,
    "qwen2.5:7b": 4.7,
    "qwen2.5-coder:7b": 4.7,
    "llama3.1:8b": 5.6,
}

#: Above this, a 30-minute endurance run on a 16GB host did not survive.
_CLERK_BUDGET_GB = 4.0


def test_the_clerk_default_fits_a_16gb_host() -> None:
    model = config.LLM_MODEL
    cost = _RESIDENT_GB.get(model)

    if cost is None:
        return  # an unmeasured model; nothing to assert against

    assert cost <= _CLERK_BUDGET_GB, (
        f"the local clerk default is {model} at ~{cost}GB resident, above the "
        f"{_CLERK_BUDGET_GB}GB that survived a 30-minute endurance run on a 16GB "
        "host. It is pulled per turn even for cloud-routed turns. Raise "
        "AIOS_LLM_MODEL deliberately per-host instead of shipping it as the "
        "default, or re-measure and move this budget with evidence."
    )


def test_the_clerk_is_operator_overridable() -> None:
    """Per-host tuning must not require editing code."""
    import inspect

    source = inspect.getsource(config)

    assert '_env_str("AIOS_LLM_MODEL"' in source


def test_the_clerk_and_the_cloud_brain_are_separate_settings() -> None:
    """Conflating them is how a cloud model ends up doing clerk work, or worse,
    a local 3B model ends up being asked to run the agent loop."""
    assert config.LLM_MODEL != config.GEMINI_MODEL
    assert hasattr(config, "VERTEX_MAAS_MODEL")
