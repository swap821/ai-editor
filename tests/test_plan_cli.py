"""The operator's own plans at the counter (2026-11-03: "connect codex models to
counter also and C"). Pinned here, without a model or a network:

* Claude goes through ``claude -p`` and GPT through ``codex exec``, each sealed
  as the workshop runs them: no tools of their own, no session, none of his MCP
  servers or plugins, an empty directory;
* what leaves passes the privacy filter first;
* the agent's tools are answered through structured output; a call to a tool
  not offered, or with arguments that are not a JSON object, is dropped;
* a call that gives no answer (a usage limit) is an LLMError, so failover runs;
* the router offers each plan model as a cloud candidate, gated by the
  operator's cloud tasks like any other cloud provider, and ``plan.<model>``
  selects one explicitly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aios.core import model_calls, plan_cli, router, router_wiring
from aios.core.llm import LLMError


@pytest.fixture(autouse=True)
def _through_the_gateway():
    """A counter turn reaches its model through the gateway's entrance."""
    with model_calls.gateway_scope("route"):
        yield


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
        },
    }
]


class FakeRun:
    """Stands in for subprocess.run: records each call and answers like the tool."""

    def __init__(self, *, stdout="", returncode=0, codex_answer=None):
        self.calls: list = []
        self.stdout = stdout
        self.returncode = returncode
        self.codex_answer = codex_answer

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if "-o" in argv and self.codex_answer is not None:
            Path(argv[argv.index("-o") + 1]).write_text(
                self.codex_answer, encoding="utf-8"
            )
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


def _client(run, **kw):
    return plan_cli.PlanCliClient(
        claude_models=("claude-sonnet-5-5",),
        codex_models=("gpt-6.1-terra",),
        run=run,
        claude="claude-bin",
        codex="codex-bin",
        **kw,
    )


def test_claude_is_asked_sealed_and_only_after_the_privacy_filter() -> None:
    run = FakeRun(stdout=json.dumps({"is_error": False, "result": "Hello."}))
    client = _client(run)
    secret = "AKIAIOSFODNN7EXAMPLE"
    answer = client.chat(
        [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": f"my key is {secret}, hi"},
        ]
    )
    assert answer == {"role": "assistant", "content": "Hello."}
    [(argv, kw)] = run.calls
    assert argv[:2] == ["claude-bin", "-p"]
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5"
    assert argv[argv.index("--tools") + 1] == "", "it has no tools of its own"
    assert "--no-session-persistence" in argv and "--strict-mcp-config" in argv
    assert argv[argv.index("--system-prompt") + 1] == "Be brief."
    assert "--json-schema" not in argv, "no tools offered: a plain answer"
    assert secret not in kw["input"], "the privacy filter ran before it left"
    assert "gagos-plan-" in kw["cwd"]


def test_the_agents_tools_come_back_as_tool_calls() -> None:
    structured = {
        "content": "",
        "tool_calls": [
            {"name": "read_file", "arguments_json": '{"path": "a.py"}'},
            {"name": "rm_rf", "arguments_json": "{}"},
            {"name": "read_file", "arguments_json": "not json"},
        ],
    }
    run = FakeRun(
        stdout=json.dumps({"is_error": False, "structured_output": structured})
    )
    answer = _client(run).chat([{"role": "user", "content": "read a.py"}], tools=TOOLS)
    assert answer["tool_calls"] == [
        {
            "id": "plan_0",
            "function": {"name": "read_file", "arguments": {"path": "a.py"}},
        }
    ], "a tool not offered and arguments that are not JSON are dropped"
    [(argv, kw)] = run.calls
    assert json.loads(argv[argv.index("--json-schema") + 1]) == plan_cli.TURN_SCHEMA
    assert "read_file" in kw["input"], "the tools are described to the model"


def test_codex_is_asked_sealed_and_answers_through_its_file() -> None:
    run = FakeRun(codex_answer=json.dumps({"content": "Done.", "tool_calls": []}))
    answer = _client(run).chat(
        [{"role": "user", "content": "hi"}], tools=TOOLS, model="gpt-6.1-terra"
    )
    assert answer == {"role": "assistant", "content": "Done."}
    [(argv, kw)] = run.calls
    assert argv[:2] == ["codex-bin", "exec"]
    assert argv[argv.index("-s") + 1] == "read-only"
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules"):
        assert flag in argv
    disabled = {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"}
    assert disabled == set(plan_cli.CODEX_ACTING_FEATURES)
    assert argv[argv.index("-m") + 1] == "gpt-6.1-terra"
    assert "model_reasoning_effort=medium" in argv
    assert "--output-schema" in argv and argv[-1] == "-"


def test_a_call_with_no_answer_is_an_error_so_failover_runs() -> None:
    run = FakeRun(
        stdout=json.dumps(
            {"is_error": True, "result": "Claude AI usage limit reached"}
        ),
        returncode=1,
    )
    with pytest.raises(LLMError, match="usage limit"):
        _client(run).chat([{"role": "user", "content": "hi"}])
    with pytest.raises(LLMError, match="no answer"):
        _client(FakeRun(codex_answer="", returncode=1)).chat(
            [{"role": "user", "content": "hi"}], model="gpt-6.1-terra"
        )


def test_only_offered_models_and_installed_tools_serve() -> None:
    client = _client(FakeRun())
    with pytest.raises(LLMError, match="not offered"):
        client.chat([{"role": "user", "content": "hi"}], model="claude-opus-5-5")
    with pytest.raises(LLMError, match="no plan serves"):
        plan_cli.family("mistral.large")
    missing = plan_cli.PlanCliClient(
        claude_models=("claude-sonnet-5-5",), claude="", codex=""
    )
    assert missing.models() == (), "a tool that is not installed offers nothing"


def test_the_router_offers_each_plan_model_as_a_gated_cloud_candidate(
    monkeypatch,
) -> None:
    plan = _client(FakeRun())
    monkeypatch.setattr(router_wiring, "_plan_client", lambda: plan)

    class Ollama:
        def list_models(self):
            return {"models": ["qwen2.5-coder:7b"]}

    providers = router_wiring._build_providers(Ollama(), None, None)
    rows = [p for p in providers if p.name == router.PROVIDER_PLAN]
    assert sorted(m for p in rows for m in p.models) == [
        "claude-sonnet-5-5",
        "gpt-6.1-terra",
    ]
    assert all(p.privacy == router.PRIVACY_CLOUD for p in rows)
    local_only = router.candidates("coding", providers, policy=router.Policy())
    assert {r.provider for r in local_only} == {router.PROVIDER_OLLAMA}, (
        "without his cloud tasks no plan model is a candidate"
    )
    allowed = router.candidates(
        "coding", providers, policy=router.Policy(cloud_tasks=frozenset({"coding"}))
    )
    assert allowed[0].provider == router.PROVIDER_PLAN
    assert allowed[0].model == "claude-sonnet-5-5"
    assert router_wiring._client_for(router.PROVIDER_PLAN, Ollama(), None, None) is plan
    assert router_wiring._provider_name(plan, None, None) == router.PROVIDER_PLAN
    client, model = router_wiring._select_chat_client(
        "plan.gpt-6.1-terra", Ollama(), None
    )
    assert (client, model) == (plan, "gpt-6.1-terra")


def test_a_plan_model_not_offered_is_refused_by_name(monkeypatch) -> None:
    from fastapi import HTTPException

    monkeypatch.setattr(router_wiring, "_plan_client", lambda: None)
    with pytest.raises(HTTPException) as exc:
        router_wiring._select_chat_client("plan.claude-sonnet-5-5", object(), None)
    assert exc.value.status_code == 503


def test_a_plan_call_outside_the_gateway_is_refused_before_it_leaves() -> None:
    """The one-gateway law holds for the plans too (docs/ONE_GATEWAY.md): a
    production caller with no entrance is refused, and nothing is run. The
    caller's frames report a production file, as in tests/test_gateway_enforcement.py."""
    run = FakeRun(stdout=json.dumps({"is_error": False, "result": "Hello."}))
    scope = {"client": _client(run)}
    repo = Path(__file__).resolve().parents[1]
    code = compile(
        "def production():\n"
        "    return client.chat([{'role': 'user', 'content': 'hi'}])\n",
        str(repo / "aios" / "application" / "turns" / "_plan_probe.py"),
        "exec",
    )
    exec(code, scope)
    token = model_calls._ENTRANCE.set(None)
    try:
        with pytest.raises(model_calls.UngatedModelCall):
            scope["production"]()
    finally:
        model_calls._ENTRANCE.reset(token)
    assert run.calls == [], "nothing was run"


def test_a_turn_tries_at_most_one_cloud_the_plans_and_anthropic_included() -> None:
    """Both reviewers of this change: the failover's own cloud list lacked
    ``plan`` (and ``anthropic``), so a turn could try two clouds in a row."""
    from aios.core.failover import FailoverChatClient, _is_cloud_provider

    assert _is_cloud_provider("plan") and _is_cloud_provider("anthropic")

    class Fails:
        def chat(self, messages, **kw):
            raise LLMError("refused")

    class Answers:
        def __init__(self) -> None:
            self.asked = 0

        def chat(self, messages, **kw):
            self.asked += 1
            return {"role": "assistant", "content": "ok"}

    plan, local = Answers(), Answers()
    failover = FailoverChatClient(
        [
            (Fails(), "m", "bedrock"),
            (plan, "claude-sonnet-5-5", "plan"),
            (local, "q", "ollama"),
        ]
    )
    assert failover.chat([{"role": "user", "content": "hi"}])["content"] == "ok"
    assert (plan.asked, local.asked) == (0, 1), "a second cloud is skipped"


def test_the_ledger_names_the_real_caller_not_the_plan_client() -> None:
    run = FakeRun(stdout=json.dumps({"is_error": False, "result": "Hello."}))
    before = model_calls.counts().copy()
    _client(run).chat([{"role": "user", "content": "hi"}])
    new = model_calls.counts() - before
    [(provider, _model, _method, _entrance, site)] = list(new)
    assert provider == "plan" and not site.startswith("aios/core/plan_cli.py")


def test_tool_arguments_that_are_not_a_string_are_dropped_not_fatal() -> None:
    structured = {
        "content": "reading",
        "tool_calls": [{"name": "read_file", "arguments_json": {"path": "a.py"}}],
    }
    run = FakeRun(
        stdout=json.dumps({"is_error": False, "structured_output": structured})
    )
    answer = _client(run).chat([{"role": "user", "content": "read"}], tools=TOOLS)
    assert answer == {"role": "assistant", "content": "reading"}
