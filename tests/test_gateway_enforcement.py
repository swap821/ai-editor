"""The one gateway, by construction: an ungated production call never leaves.

Until 2026-10-29 the model-call ledger only measured (docs/ONE_GATEWAY.md), so
"every model call passes Organ 32" held only as far as a drive reached; real
use found two calls a drive had missed. Now ``model_calls.observe`` -- which
every provider adapter calls before it sends -- refuses a production call
that came through no entrance. Pinned here:

* refused before the transport is touched, and recorded as refused;
* not refused inside an entrance, from a measurement site, or when switched
  off; an exempt program's own process only when asked;
* a call is production if ANY frame on its stack is, so it cannot be laundered
  through a tool's helper;
* the scoreboard fails on a refused call too, named apart;
* only the gateway can name an entrance, so none can be faked;
* only the provider adapters can reach a model at all: every network-capable
  module under ``aios/`` is accounted for, none but the adapters names a model
  endpoint, and nothing else calls a provider SDK's inference method.
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
    monkeypatch.setattr(config, "GATEWAY_ENFORCE", None)
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
    assert record["judged"] is True
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
    assert record["judged"] is False
    assert "refused" not in record


def _frame_in(rel: str, name: str, body: str, scope: dict[str, Any]) -> Any:
    """A function whose frames report *rel* as their file, as code living
    there would."""
    code = compile(body, str(REPO / rel), "exec")
    exec(code, scope)
    return scope[name]


def test_a_call_cannot_be_laundered_through_a_tools_helper(ledger, sent) -> None:
    """Production code that reaches a model through a ``tools/`` helper is
    still production. Judged by the innermost frame alone, the call would
    have been a tool's own, so neither refused nor counted (found by the
    adversarial re-read, 2026-10-29; no live path did this)."""
    from aios.core.llm import OllamaClient

    scope: dict[str, Any] = {"OllamaClient": OllamaClient}
    _frame_in(
        "tools/_laundering_probe.py",
        "helper",
        "def helper():\n"
        "    return OllamaClient('m', host='http://ollama.test').complete('hi')\n",
        scope,
    )
    production = _frame_in(
        "aios/_laundering_probe.py",
        "production",
        "def production():\n    return helper()\n",
        scope,
    )

    with pytest.raises(model_calls.UngatedModelCall):
        production()
    assert sent == []
    (record,) = _records(ledger)
    assert record["site"] == "tools/_laundering_probe.py:helper"
    assert record["judged"] is True and record["refused"] is True


def test_switched_off_it_records_and_sends(ledger, sent, monkeypatch) -> None:
    monkeypatch.setattr(config, "GATEWAY_ENFORCE", False)
    assert _production_call() == "ok"
    assert len(sent) == 1
    (record,) = _records(ledger)
    assert record["entrance"] is None and "refused" not in record


def test_the_switch_and_its_exemptions_are_defined_behind_the_freeze() -> None:
    from aios.security import limits

    assert config.GATEWAY_ENFORCE is limits.GATEWAY_ENFORCE
    assert config.GATEWAY_UNJUDGED_SITES is limits.GATEWAY_UNJUDGED_SITES
    assert config.GATEWAY_EXEMPT_PROGRAMS is limits.GATEWAY_EXEMPT_PROGRAMS


@pytest.fixture
def tool_process(monkeypatch) -> None:
    """Pretend this process is a measurement tool run as the main program."""
    main = types.ModuleType("__main__")
    main.__file__ = str(REPO / "tools" / "learning_payoff.py")
    monkeypatch.setitem(sys.modules, "__main__", main)


def test_an_exempt_programs_process_is_not_refused_unless_asked(
    ledger, sent, tool_process, monkeypatch
) -> None:
    assert model_calls.measurement_process()
    assert _production_call() == "ok"
    (record,) = _records(ledger)
    # Still recorded and judged: the scoreboard sees it as an ungated call.
    assert record["entrance"] is None and record["judged"] is True

    monkeypatch.setattr(config, "GATEWAY_ENFORCE", True)
    with pytest.raises(model_calls.UngatedModelCall):
        _production_call()
    assert len(sent) == 1


def test_this_test_process_is_not_an_exempt_program() -> None:
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
# Only the gateway can name an entrance
# --------------------------------------------------------------------------- #

#: Where an entrance may be opened: the gateway, and the ledger that defines it.
ENTRANCE_OWNERS = {
    "aios/application/intelligence/gateway.py",
    "aios/core/model_calls.py",
}


def test_only_the_gateway_opens_an_entrance() -> None:
    """``gateway_scope`` and ``scoped_iter`` mark a call as having passed an
    entrance. Production code that opened one itself would skip the stop
    check, context record and redaction while the ledger said "gated", and
    enforcement would let it through. So nothing else may name them."""
    names = {"gateway_scope", "scoped_iter", "_ENTRANCE"}
    offenders = []
    for path in sorted((REPO / "aios").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in ENTRANCE_OWNERS:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            named = (
                node.attr
                if isinstance(node, ast.Attribute)
                else node.id
                if isinstance(node, ast.Name)
                else node.name
                if isinstance(node, ast.alias)
                else None
            )
            if named in names:
                offenders.append(f"{rel}:{getattr(node, 'lineno', '?')} {named}")
    assert offenders == []


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
    "aios/operations/github_app.py": (
        "GAGOS's own GitHub App: GitHub's REST API (an installation token, a "
        "pull request); no model"
    ),
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

#: Provider SDK methods that run a model.
SDK_INFERENCE = frozenset(
    {
        "converse",
        "converse_stream",
        "invoke_model",
        "invoke_model_with_response_stream",
        "generate_content",
        "generate_content_stream",
    }
)

#: Not adapters, but the adapters' own retry plumbing (aios/core/model_calls.py
#: _PLUMBING): it runs a call an adapter has already recorded.
ADAPTER_PLUMBING = {"aios/core/failover.py", "aios/core/provider_retry.py"}


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


def test_nothing_but_an_adapter_runs_a_provider_sdk_or_names_an_endpoint() -> None:
    """A module needs no network import to reach a model: it could call an
    adapter's private SDK client (``bedrock._client.converse(...)``) or hand
    an inference URL to someone else's transport. Read as code, not text, so
    a docstring that mentions one is not a call."""
    offenders = []
    for path in sorted((REPO / "aios").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in ADAPTERS or rel in ADAPTER_PLUMBING:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in SDK_INFERENCE:
                offenders.append(f"{rel}:{node.lineno} .{node.attr}")
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and any(marker in node.value for marker in MODEL_ENDPOINTS[:3])
            ):
                offenders.append(f"{rel}:{node.lineno} {node.value[:60]!r}")
    assert offenders == []


# --------------------------------------------------------------------------- #
# A virtualenv inside the repository (review, 2026-10-29)
# --------------------------------------------------------------------------- #


def test_installed_code_inside_the_repository_is_not_repository_code(
    monkeypatch,
) -> None:
    """The README's install puts ``.venv`` inside the repository. Its files
    are the interpreter's, never the repository's own."""
    from aios.core import model_calls as mc

    root = mc._REPO_ROOT
    venv = (root / ".venv").resolve()
    installed = venv / "Lib" / "site-packages" / "_pytest" / "python.py"
    monkeypatch.setattr(mc, "_INSTALL_ROOTS", (venv,))
    assert mc._relative(str(installed)) is None
    # Any site-packages below the repository, whatever its virtualenv is called.
    monkeypatch.setattr(mc, "_INSTALL_ROOTS", ())
    assert mc._relative(str(installed)) is None
    # Positive control: the repository's own code is still its own.
    assert mc._relative(str(root / "aios" / "core" / "llm.py")) == "aios/core/llm.py"
    assert mc._relative(str(root / "tests" / "test_x.py")) == "tests/test_x.py"


def test_a_test_call_through_an_in_repo_virtualenv_is_not_production(
    monkeypatch,
) -> None:
    """The shape that failed: a call a test makes, with pytest's installed
    frames on the stack, judged by the real ``calling_stack``. Before the fix
    the installed frame was kept as repository code outside ``tests/``, so the
    call was judged production and refused."""
    from aios.core import model_calls as mc

    venv = (mc._REPO_ROOT / ".venv").resolve()
    monkeypatch.setattr(mc, "_INSTALL_ROOTS", (venv,))
    runner = venv / "Lib" / "site-packages" / "_pytest" / "fake_runner.py"
    namespace: dict = {}
    exec(  # noqa: S102 - a fixed two-line function, compiled under an installed path
        compile("def run(callback):\n    return callback()\n", str(runner), "exec"),
        namespace,
    )
    stack = namespace["run"](mc.calling_stack)
    assert stack, "the test's own frame is kept"
    assert all(frame.startswith("tests/") for frame in stack), stack
    assert mc.judged_stack(stack) is False
