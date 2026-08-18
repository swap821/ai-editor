"""Vertex Model-as-a-Service provider: DeepSeek and friends as a cloud brain.

Vertex serves more than Gemini, and which of those a project may actually CALL
is not what the publisher listing says. Verified by invoking each on 2026-08-18:
deepseek-r1 answers, gpt-oss is throttled but reachable, meta/nvidia 404 in every
region tried, and anthropic resolves with zero quota. Reading the listing instead
of probing it cost a golden cohort earlier that day.

These tests are offline. The live two-turn tool round-trip was checked by hand;
what is pinned here is the wiring that would silently rot: token freshness, the
quota-project header, the global-vs-regional host, and reasoning-block stripping.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from aios.core.llm import LLMError
from aios.core.vertex_maas import VertexMaaSClient, maas_base_url, strip_reasoning


# ── reasoning blocks ─────────────────────────────────────────────────────────

def test_a_closed_reasoning_block_is_removed() -> None:
    assert strip_reasoning("<think>chain of thought</think>The answer.") == "The answer."


def test_a_truncated_reasoning_block_is_removed() -> None:
    """The budget can run out mid-thought; the tag then never closes."""
    assert strip_reasoning("The answer.<think>still reasoning") == "The answer."


def test_ordinary_content_is_untouched() -> None:
    assert strip_reasoning("No reasoning here.") == "No reasoning here."
    assert strip_reasoning("") == ""


def test_reasoning_is_stripped_from_chat_content(monkeypatch) -> None:
    """It must not reach the operator's narrative or be replayed as a statement."""
    client = VertexMaaSClient(project="p", credentials=SimpleNamespace(valid=True, token="t"))
    monkeypatch.setattr(
        type(client).__bases__[0], "chat",
        lambda self, m, *, tools=None, model=None: {
            "role": "assistant", "content": "<think>hmm</think>Done.", "tool_calls": [],
        },
    )

    assert client.chat([{"role": "user", "content": "hi"}])["content"] == "Done."


# ── the endpoint ─────────────────────────────────────────────────────────────

def test_global_has_no_region_prefix() -> None:
    """The asymmetry that made every gemini-3.x id look like it did not exist."""
    assert maas_base_url("p", "global").startswith("https://aiplatform.googleapis.com/")


def test_a_region_gets_its_prefix() -> None:
    assert maas_base_url("p", "us-central1").startswith(
        "https://us-central1-aiplatform.googleapis.com/"
    )


def test_the_project_is_in_the_path() -> None:
    assert "/projects/my-proj/" in maas_base_url("my-proj", "us-central1")


# ── auth ─────────────────────────────────────────────────────────────────────

def test_the_token_is_minted_per_request_not_cached_at_construction() -> None:
    """ADC tokens expire. A key captured once dies mid-run.

    That is the "works in the smoke test, fails in the 30-minute measurement"
    shape this repo has already paid for more than once.
    """
    refreshes = []

    class Creds:
        def __init__(self) -> None:
            self.valid = False
            self.token = "tok-1"

        def refresh(self, _request) -> None:
            refreshes.append(1)
            self.valid = True
            self.token = f"tok-{len(refreshes) + 1}"

    # request_factory: the fake ignores the transport, but SOMETHING must be
    # constructed, and google-auth is optional. See the regression test below.
    client = VertexMaaSClient(project="p", credentials=Creds(), request_factory=lambda: None)
    first = client._headers()["Authorization"]
    client._credentials.valid = False  # simulate expiry
    second = client._headers()["Authorization"]

    assert first != second, "the bearer token was reused after expiry"
    assert len(refreshes) == 2


def test_injected_credentials_do_not_need_google_auth() -> None:
    """The `credentials` parameter must work when google-auth is ABSENT.

    google-genai lives in requirements-optional.txt, so CI runners do not have
    it. `_fresh_token` imported google.auth at the top of its try block, before
    the branch that checks whether credentials were already supplied -- so the
    one caller who had done the auth work himself still crashed with
    ModuleNotFoundError, and three tests failed on a runner rather than in the
    code they were testing.

    This blocks the import the way the runner does, and asserts the escape hatch
    actually escapes.
    """
    import builtins

    real_import = builtins.__import__

    def blocked(name: str, *args, **kwargs):
        if name == "google" or name.startswith("google."):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = blocked
    try:
        client = VertexMaaSClient(
            project="p", credentials=SimpleNamespace(valid=True, token="t")
        )
        assert client._headers()["Authorization"] == "Bearer t"
    finally:
        builtins.__import__ = real_import


def test_the_quota_project_header_is_sent() -> None:
    """Without it ADC gets 403 'requires a quota project' -- which reads as a
    permissions failure and is not one."""
    client = VertexMaaSClient(project="my-proj", credentials=SimpleNamespace(valid=True, token="t"))

    assert client._headers()["x-goog-user-project"] == "my-proj"


def test_the_static_api_key_path_is_not_used() -> None:
    """Inherited api_key must stay empty so the parent cannot send a stale key."""
    client = VertexMaaSClient(project="p", credentials=SimpleNamespace(valid=True, token="t"))

    assert client.api_key == ""
    assert client._headers()["Authorization"] == "Bearer t"


def test_a_missing_project_fails_loudly() -> None:
    """Silently defaulting a GCP project is how a run bills someone else."""
    with pytest.raises(LLMError, match="project"):
        VertexMaaSClient(project="")


# ── routing ──────────────────────────────────────────────────────────────────

class _FakeVertex:
    model = "deepseek-ai/deepseek-r1-0528-maas"


def test_an_explicit_vertexmaas_id_reaches_the_provider() -> None:
    """Without its own branch the id falls through to the Bedrock catch-all.

    The dispatch chain ends "any other explicit id routes to Bedrock", so a
    `vertexmaas.` id would have produced a 503 naming the WRONG provider -- the
    same class of misleading refusal as the `Host header is not configured`
    message that hid a port mismatch for an hour.
    """
    from aios.core.router_wiring import _select_chat_client

    client, model = _select_chat_client(
        "vertexmaas.deepseek-ai/deepseek-r1-0528-maas",
        None, None, vertex_maas=_FakeVertex(),
    )

    assert isinstance(client, _FakeVertex)
    assert model == "deepseek-ai/deepseek-r1-0528-maas", "the prefix was not stripped"


def test_a_slash_in_the_model_name_survives() -> None:
    """Vertex MaaS ids are `<publisher>/<model>` -- the only provider here whose
    model name contains a separator."""
    from aios.core.router_wiring import _select_chat_client

    _client, model = _select_chat_client(
        "vertexmaas.openai/gpt-oss-120b-maas", None, None, vertex_maas=_FakeVertex()
    )

    assert model == "openai/gpt-oss-120b-maas"


def test_selecting_it_unconfigured_names_the_right_provider() -> None:
    from fastapi import HTTPException

    from aios.core.router_wiring import _select_chat_client

    with pytest.raises(HTTPException) as exc:
        _select_chat_client("vertexmaas.x", None, None, vertex_maas=None)

    assert exc.value.status_code == 503
    assert "Vertex MaaS" in str(exc.value.detail)


def test_it_is_registered_as_cloud_not_local() -> None:
    """The single most consequential line in this change.

    Mislabelled PRIVACY_LOCAL, it would bypass the policy gate entirely and be
    eligible for every task -- turning "a new provider is available" into "a new
    egress is open".
    """
    from aios.core import router
    from aios.core.router_wiring import _build_providers

    providers = _build_providers(None, None, None, vertex_maas=_FakeVertex())
    vm = [p for p in providers if p.name == router.PROVIDER_VERTEX_MAAS]

    assert vm, "the provider was not registered at all"
    assert vm[0].privacy == router.PRIVACY_CLOUD


def test_it_cannot_be_routed_to_when_no_task_is_cloud_eligible() -> None:
    """cloud_tasks defaults to empty; a cloud provider must then be ineligible."""
    from aios.core import router
    from aios.core.router_wiring import _build_providers

    providers = _build_providers(None, None, None, vertex_maas=_FakeVertex())
    vm = [p for p in providers if p.name == router.PROVIDER_VERTEX_MAAS][0]

    assert not router.policy_allows(router.Policy(cloud_tasks=frozenset()), "coding", vm)
