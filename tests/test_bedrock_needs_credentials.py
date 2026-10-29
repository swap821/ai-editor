"""A cloud provider that cannot sign a request is not offered (2026-10-29).

Found on the operator's daily backend: ``.env`` names a Bedrock region and
model, his user-wide environment opts ``coding`` into cloud routing, and the
backend loads no AWS key. Each ``auto`` coding turn's first model call went to
three Bedrock models in turn, every one failing "Unable to locate credentials"
before anything was sent, and only then to the local model. ``get_bedrock_client``
now offers Bedrock only when a request could be signed. Pinned:

* no credential: no client, so nothing to route to, and ``auto`` stays local
  even with ``coding`` opted into the cloud;
* a Bedrock API key, or anything boto3's chain resolves: the client exists and
  ``auto`` routes to it exactly as before (the positive control).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import aios.api.deps as deps
from aios import config
from aios.core import bedrock
from aios.core.failover import FailoverChatClient
from aios.core.router_wiring import _select_chat_client
from tests.test_route_wiring import (  # noqa: F401 - autouse fixtures
    FakeOllama,
    _clear_catalog,
    _reset_runtime_profile,
    _set_cloud_policy,
)

AWS_VARIABLES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
)


class FakeBedrock:
    """Stands in for the boto3-backed client; never sends anything."""

    def __init__(self, **_kwargs) -> None:
        pass


@pytest.fixture()
def no_aws(tmp_path: Path, monkeypatch):
    """A machine with no AWS credential anywhere boto3 looks."""
    for name in AWS_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(config, "BEDROCK_REGION", "us-east-1")
    monkeypatch.setattr(config, "BEDROCK_MODEL", "amazon.nova-pro-v1:0")
    monkeypatch.setattr(deps, "BedrockClient", FakeBedrock)
    monkeypatch.setattr(deps, "_bedrock_client", None)
    yield
    monkeypatch.setattr(deps, "_bedrock_client", None)


def test_no_credential_means_no_bedrock_client(no_aws) -> None:
    assert bedrock.credentials_available("us-east-1") is False
    assert deps.get_bedrock_client() is None


def test_a_bedrock_api_key_is_a_credential(no_aws, monkeypatch) -> None:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "ABSK-test-not-a-real-key")
    assert bedrock.credentials_available("us-east-1") is True
    assert isinstance(deps.get_bedrock_client(), FakeBedrock)


def test_keys_the_default_chain_resolves_are_a_credential(no_aws, monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDTESTNOTREAL")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret-not-real")
    assert bedrock.credentials_available("us-east-1") is True


def _route(bedrock_client):
    return _select_chat_client(
        "auto",
        FakeOllama(["qwen2.5-coder:7b"]),
        bedrock=bedrock_client,
        task="coding",
        llm_picker=False,
    )


def test_auto_stays_local_when_the_cloud_it_may_use_cannot_sign(
    no_aws, monkeypatch
) -> None:
    """The daily backend's case, through the real route selection: coding is
    opted into the cloud, Bedrock is configured, no AWS key is loaded."""
    _set_cloud_policy(monkeypatch, cloud_tasks=("coding",))
    client, model = _route(deps.get_bedrock_client())
    assert model == "qwen2.5-coder:7b"
    assert not isinstance(client, FailoverChatClient) or all(
        provider != "bedrock" for _c, _m, provider in client.candidates
    )


def test_with_a_credential_auto_still_goes_to_the_cloud_it_may_use(
    no_aws, monkeypatch
) -> None:
    """Positive control: the guard removes a provider that cannot sign, and
    nothing else. With a key, the operator's opt-in routes as before."""
    _set_cloud_policy(monkeypatch, cloud_tasks=("coding",))
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "ABSK-test-not-a-real-key")
    client, _model = _route(deps.get_bedrock_client())
    assert isinstance(client, FailoverChatClient)
    assert client.candidates[0][2] == "bedrock"
