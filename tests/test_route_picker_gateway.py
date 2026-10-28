"""The hybrid route picker's model call passes the gateway (organ 32).

2026-10-28: the operator's model-call ledger (``data/model_calls``) held 163
calls, and 25 came through no gateway entrance. 12 had no repository frame at
all (measurement scripts run on 2026-10-12). The other 13 were production, every
one from ``aios/core/router_wiring.py:picker``: the small local model that
prefers a route on a turn when policy allows two or more candidates. It skipped
the emergency-stop check and output redaction. The one-gateway inventory
(``tools/model_call_inventory.py``) never reached it, because its environment
gave every turn a single candidate.

The picker now runs only through a gate, which the turn routes build on the
local-only compatibility entrance. Without a gate there is no pick.
"""

from __future__ import annotations

import pytest

from aios import config
from aios.application.governance.emergency_stop import EmergencyStopError
from aios.application.intelligence.gateway import (
    complete_compatibility_intelligence_request,
)
from aios.core import model_calls, router
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.core.router_wiring import _maybe_llm_picker
from aios.runtime.secret_policy import SecretPolicy

# A real Bedrock model id that the gateway's redaction cannot tell from a
# secret: it scans as high-entropy.
_480B = "qwen.qwen3-coder-480b-a35b-v1:0"


class _Ollama:
    """Records the gateway entrance each model call ran inside."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.entrances: list[str | None] = []

    def chat(self, messages, *, tools=None, model=None) -> dict:
        self.entrances.append(model_calls.current_entrance())
        return {"content": self.reply}


class _EngagedStop:
    def assert_operational(self) -> None:
        raise EmergencyStopError("emergency stop is engaged; side effects are disabled")


def _gate(stop=UNGOVERNED_FIXTURE):
    """The turn routes' gate, on the real entrance."""

    def gate(pick):
        return complete_compatibility_intelligence_request(
            request_id="test:route-pick",
            target="local",
            model_call=pick,
            emergency_stop=stop,
        )

    return gate


@pytest.fixture
def choice(monkeypatch):
    """Two policy-allowed candidates and a local model to choose with."""
    monkeypatch.setattr(config, "ROUTER_LLM_PICK", True)
    providers = [
        router.Provider(
            name=router.PROVIDER_OLLAMA,
            privacy=router.PRIVACY_LOCAL,
            cost=router.COST_FREE,
            available=True,
            models=("qwen2.5:0.5b", "qwen2.5-coder:7b"),
        )
    ]
    cands = [
        router.Route(
            router.PROVIDER_OLLAMA,
            "qwen2.5-coder:7b",
            router.PRIVACY_LOCAL,
            router.COST_FREE,
            "local",
        ),
        router.Route(
            router.PROVIDER_BEDROCK,
            _480B,
            router.PRIVACY_CLOUD,
            router.COST_LOW,
            "cloud",
        ),
    ]
    return providers, cands


def test_the_pick_runs_inside_a_gateway_entrance(choice) -> None:
    providers, cands = choice
    ollama = _Ollama("ollama.qwen2.5-coder:7b")
    picker = _maybe_llm_picker(ollama, providers, cands, "coding", gate=_gate())
    assert picker is not None
    assert picker(cands) == "ollama.qwen2.5-coder:7b"
    assert ollama.entrances == ["complete_compatibility"], (
        "the route picker called its model outside every gateway entrance"
    )


def test_without_a_gate_no_model_is_asked(choice) -> None:
    providers, cands = choice
    ollama = _Ollama("ollama.qwen2.5-coder:7b")
    assert _maybe_llm_picker(ollama, providers, cands, "coding") is None
    assert ollama.entrances == []


def test_a_pick_redaction_would_mangle_still_lands(choice) -> None:
    """Only the allow-list position leaves the gated call, so a model id that
    redaction rewrites is still chosen."""
    assert SecretPolicy().inspect_text(f"bedrock.{_480B}").scrubbed != (
        f"bedrock.{_480B}"
    ), "precondition: redaction rewrites this id (else this test proves nothing)"
    providers, cands = choice
    ollama = _Ollama(f"bedrock.{_480B}")
    picker = _maybe_llm_picker(ollama, providers, cands, "coding", gate=_gate())
    assert picker(cands) == f"bedrock.{_480B}"
    assert router.pick_from(cands, picker=picker) is cands[1]


def test_an_engaged_stop_refuses_the_pick_before_any_model_call(choice) -> None:
    providers, cands = choice
    ollama = _Ollama("ollama.qwen2.5-coder:7b")
    picker = _maybe_llm_picker(
        ollama, providers, cands, "coding", gate=_gate(_EngagedStop())
    )
    assert picker(cands) is None
    assert ollama.entrances == [], "the model was asked while the stop was engaged"
    # Routing falls back to the deterministic winner; the turn's own model call
    # then meets the same stop at its own entrance.
    assert router.pick_from(cands, picker=picker) is cands[0]


@pytest.mark.parametrize("reply", ["", "not sure", "gemini.gemini-2.5-pro"])
def test_a_reply_naming_no_candidate_leaves_the_deterministic_winner(
    choice, reply
) -> None:
    providers, cands = choice
    ollama = _Ollama(reply)
    picker = _maybe_llm_picker(ollama, providers, cands, "coding", gate=_gate())
    assert picker(cands) is None
    assert router.pick_from(cands, picker=picker) is cands[0]
