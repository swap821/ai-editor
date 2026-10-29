"""The one gateway, by construction: an ungated production call never leaves.

Until 2026-10-29 the model-call ledger only measured (docs/ONE_GATEWAY.md), so
"every model call passes Organ 32" held only as far as a drive reached; real
use found two calls a drive had missed. Now ``model_calls.observe`` -- which
every provider adapter calls before it sends -- refuses a production call
that came through no entrance. Pinned here:

* refused before the transport is touched, and recorded as refused;
* not refused inside an entrance, from a measurement site, or when switched
  off; a measurement tool's own process only when asked;
* the scoreboard fails on a refused call too, named apart;
* only the provider adapters can reach a model at all: every network-capable
  module under ``aios/`` is accounted for, and none but the adapters names a
  model endpoint.
"""

from __future__ import annotations

import ast
import io
import json
import sys
import types
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from aios import config
from aios.core import model_calls

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def ledger(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "GATEWAY_ENFORCE", "")
    monkeypatch.setattr(model_calls, "_WRITE_FAILED", False)
    return tmp_path / "model_calls"


def _records(ledger: Path) -> list[dict[str, Any]]:
    return model_calls.read_ledger(
        ledger.parent, datetime.now(timezone.utc) - timedelta(minutes=5)
    )


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def sent(monkeypatch) -> list[str]:
    """Every request that reached the transport."""
    requests: list[str] = []

    def urlopen(request, timeout=None):
        requests.append(request.full_url)
        return _Response(json.dumps({"response": "ok", "done": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return requests


def _production_call() -> str:
    """A production frame asking a real adapter for a completion with no
    entrance: the unbound worker reasoner, called directly."""
    from aios.core.llm import OllamaClient
    from aios.runtime.intelligence_gateway import LocalOllamaReasoner

    reasoner = LocalOllamaReasoner(OllamaClient("m", host="http://ollama.test"))
    return reasoner.complete("plan something")


SITE = "aios/runtime/intelligence_gateway.py:complete"


def test_an_ungated_production_call_is_refused_before_it_is_sent(ledger, sent) -> None:
    with pytest.raises(model_calls.UngatedModelCall, match="no gateway entrance"):
        _production_call()

    assert sent == []
    (record,) = _records(ledger)
    assert record["site"] == SITE
    assert record["entrance"] is None
    assert record["refused"] is True


def test_inside_an_entrance_the_same_call_is_sent(ledger, sent) -> None:
    with model_calls.gateway_scope("complete_compatibility"):
        assert _production_call() == "ok"

    assert len(sent) == 1
    (record,) = _records(ledger)
    assert record["entrance"] == "complete_compatibility"
    assert "refused" not in record


def test_a_measurement_sites_own_call_is_reported_not_refused(ledger, sent) -> None:
    from aios.core.llm import OllamaClient

    assert OllamaClient("m", host="http://ollama.test").complete("hi") == "ok"
    assert len(sent) == 1
    (record,) = _records(ledger)
    assert record["site"].startswith("tests/")
    assert "refused" not in record


def test_switched_off_it_records_and_sends(ledger, sent, monkeypatch) -> None:
    monkeypatch.setattr(config, "GATEWAY_ENFORCE", "0")
    assert _production_call() == "ok"
    assert len(sent) == 1
    (record,) = _records(ledger)
    assert record["entrance"] is None and "refused" not in record


@pytest.fixture
def tool_process(monkeypatch) -> None:
    """Pretend this process is a measurement tool run as the main program."""
    main = types.ModuleType("__main__")
    main.__file__ = str(REPO / "tools" / "learning_payoff.py")
    monkeypatch.setitem(sys.modules, "__main__", main)


def test_a_measurement_tools_process_is_not_refused_unless_asked(
    ledger, sent, tool_process, monkeypatch
) -> None:
    assert model_calls.measurement_process()
    assert _production_call() == "ok"
    (record,) = _records(ledger)
    # Still recorded and judged: the scoreboard sees it as an ungated call.
    assert record["entrance"] is None and model_calls.judged(record["site"])

    monkeypatch.setattr(config, "GATEWAY_ENFORCE", "1")
    with pytest.raises(model_calls.UngatedModelCall):
        _production_call()
    assert len(sent) == 1


def test_this_test_process_is_not_a_measurement_tool() -> None:
    """The suite runs enforced: a test that drives production code with a
    real adapter outside an entrance fails, which is how such paths are
    found."""
    assert not model_calls.measurement_process()


def test_the_scoreboard_fails_on_a_refused_call_and_names_it(ledger, sent) -> None:
    from tools.production_readiness import FAIL, World, clerk_one_gateway

    with pytest.raises(model_calls.UngatedModelCall):
        _production_call()
    with model_calls.gateway_scope("route"):
        _production_call()

    world = World.__new__(World)
    world.data_dir = ledger.parent
    world.now = datetime.now(timezone.utc) + timedelta(minutes=1)
    gate = clerk_one_gateway(world)

    assert gate.status == FAIL
    assert "refused before they left" in gate.evidence
    assert SITE in gate.evidence


# --------------------------------------------------------------------------- #
# Only the provider adapters can reach a model
# --------------------------------------------------------------------------- #

#: Libraries that can open a connection.
NETWORK = (
    "urllib.request",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "http.client",
    "socket",
    "boto3",
    "botocore",
    "google.genai",
    "google.generativeai",
    "google.auth",
    "openai",
    "anthropic",
    "litellm",
    "ollama",
    "websocket",
    "websockets",
    "grpc",
)

#: The provider adapters: each calls ``model_calls.observe`` before it sends
#: (tests/test_model_calls.py drives every one).
ADAPTERS = {
    "aios/core/llm.py",
    "aios/core/bedrock.py",
    "aios/core/gemini.py",
    "aios/core/openai_compat.py",
    "aios/core/anthropic_direct.py",
    "aios/core/vertex_maas.py",
}

#: Every other module that can open a connection, and what it talks to.
NOT_A_MODEL = {
    "aios/agents/tool_handlers.py": "the browse tool's GET of a web page",
    "aios/application/executor/service.py": "the executor service's own API",
    "aios/application/intelligence/transport_target.py": (
        "resolves a host name to decide local or cloud; sends nothing"
    ),
    "aios/bootstrap.py": "Ollama's /api/tags health probe (GET, no model)",
    "aios/core/websearch.py": "the CRAG web-search provider",
    "aios/probe_session.py": "this backend's own API, for the probe drivers",
}

#: Strings only a model request carries.
MODEL_ENDPOINTS = (
    "/api/chat",
    "chat/completions",
    "/v1/messages",
    "generate_content",
    "converse",
    ":generateContent",
)


def _network_modules() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted((REPO / "aios").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        names: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                # ``from google import genai`` imports google.genai.
                names.add(node.module)
                names.update(f"{node.module}.{alias.name}" for alias in node.names)
        hits = {
            name
            for name in names
            for lib in NETWORK
            if name == lib or name.startswith(lib + ".")
        }
        if hits:
            found[rel] = hits
    return found


def test_every_network_capable_module_is_an_adapter_or_accounted_for() -> None:
    """A new module that can open a connection fails here until someone says
    what it talks to. That is the egress half of the proof: a model request
    can only leave through an adapter, and every adapter records -- and now
    refuses -- before it sends."""
    found = set(_network_modules())
    assert found - ADAPTERS - set(NOT_A_MODEL) == set()
    # And the lists stay true: nothing listed that no longer connects.
    assert set(NOT_A_MODEL) <= found
    assert ADAPTERS <= found


def test_no_module_but_an_adapter_names_a_model_endpoint() -> None:
    for rel in NOT_A_MODEL:
        text = (REPO / rel).read_text(encoding="utf-8")
        named = [marker for marker in MODEL_ENDPOINTS if marker in text]
        assert named == [], f"{rel} names a model endpoint: {named}"
