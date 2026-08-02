"""Live local-clerk proof (organs 35 and 37), run against a real Ollama.

Organs 35 and 37 have carried the same blocker for the whole campaign -- "no
Ollama — live local clerk runtime evidence needs live Ollama". Every existing
proof for them runs on fixtures: `r15_runtime_proof._probe_local_workforce_
qualification` drives a canned client that returns hand-written JSON, so it
proves the suite's plumbing and nothing about a real model.

This file is the local-clerk twin of `test_executor_integration.py`: skipped
during ordinary runs, executed in CI once a real Ollama is reachable. Keeping
it in the repository makes the local-clerk claims executable rather than
documentation-only.

WHAT COUNTS AS PROOF HERE
-------------------------
Deliberately NOT "a local model passed qualification". A small CI-sized model
may well fail these cases, and demanding a pass would create pressure to pick
a model that flatters the suite, or to loosen the suite until something
passes.

What is proven is that the real machinery ran against a real model and
produced a real, evidence-backed verdict:

* organ 37 -- `LocalModelQualificationAuthority` (the organ's own named
  authority owner) executes its real 16-case suite against a live model and
  returns a `QualificationResult` carrying per-case outcomes.
* organ 35 -- that real result is fed to the real `dispatch_clerical_job`,
  and the routing decision that comes back is the one the evidence justifies.

A model that FAILS qualification and is therefore escalated away from the
local clerk is the safety behaviour working, and is stronger evidence than a
pass would be: it shows the gate refusing on real evidence rather than on a
fixture built to fail.
"""

from __future__ import annotations

import json
import os

import pytest

from aios.core.llm import OllamaClient
from aios.domain.local_workforce.qualifier import (
    QUALIFICATION_SUITE_VERSION,
    LocalModelQualificationAuthority,
)

pytestmark = pytest.mark.skipif(
    os.getenv("AIOS_OLLAMA_INTEGRATION") != "1",
    reason="live local clerk runtime (Ollama) is not enabled",
)

#: Small enough to pull and run on a CPU-only CI runner. The suite's verdict
#: on it is whatever it honestly is -- see the module docstring.
_MODEL = os.getenv("AIOS_OLLAMA_MODEL", "qwen2.5:0.5b")


@pytest.fixture(scope="module")
def live_client() -> OllamaClient:
    client = OllamaClient(model=_MODEL)
    try:
        models = client.list_models()
    except Exception as exc:  # noqa: BLE001 - an unreachable daemon is a real failure here
        pytest.fail(f"live Ollama unreachable at {client.host}: {exc}")
    assert models, f"live Ollama at {client.host} has no models installed"
    return client


def test_the_local_runtime_is_actually_reachable(live_client: OllamaClient) -> None:
    """Organ 35's floor. Everything below is meaningless if this is a fixture."""
    models = live_client.list_models()

    assert models
    assert any(_MODEL.split(":")[0] in str(m) for m in models), (
        f"expected {_MODEL} among live models, got {models}"
    )


def test_a_real_local_model_answers_a_real_prompt(live_client: OllamaClient) -> None:
    """Organ 35: the local clerk runtime genuinely executes work.

    Asserts only that a real, non-empty completion came back from a real
    daemon -- not that the content is correct. Judging a 0.5B model's prose
    would make this test about model quality instead of runtime liveness.
    """
    reply = live_client.complete("Reply with the single word: ready")

    assert isinstance(reply, str)
    assert reply.strip(), "live model returned an empty completion"


def test_the_qualification_suite_runs_against_a_live_model(
    live_client: OllamaClient,
) -> None:
    """Organ 37: the real suite, the real authority, a real model.

    `LocalModelQualificationAuthority` IS organ 37's declared authority_owner,
    so this exercises the named owner rather than a stand-in.
    """
    suite = LocalModelQualificationAuthority(live_client)

    result = suite.run()

    assert result.suite_version == QUALIFICATION_SUITE_VERSION
    assert result.test_results, "qualification produced no per-case results"
    # Every case must have a real recorded outcome. A suite that silently
    # skipped cases would look identical to one that ran them all.
    assert all(case.test_id for case in result.test_results)
    assert all(case.attempts >= 1 for case in result.test_results), (
        "a case with zero attempts never ran against the model"
    )
    assert isinstance(result.passed, bool)


def test_the_dispatcher_honours_the_live_verdict(live_client: OllamaClient) -> None:
    """Organs 35+36: the real routing decision follows the real evidence.

    The chain that matters end to end -- a live model's genuine qualification
    result decides whether the local clerk may be used at all. Asserted in
    both directions so this cannot pass by the dispatcher ignoring evidence
    and always choosing one branch.
    """
    from aios.application.local_workforce.dispatcher import dispatch_clerical_job

    result = LocalModelQualificationAuthority(live_client).run()

    decision = dispatch_clerical_job(
        deterministic_available=False,
        qualification=result,
        confidence=0.9,
    )

    assert decision in {
        "deterministic",
        "local_clerk",
        "frontier_escalation",
        "human_clarification",
    }
    if result.passed:
        assert decision == "local_clerk", (
            f"a qualified live model was not routed to the local clerk: {decision}"
        )
    else:
        # The dispatcher's own rule: an unqualified or failed-qualification
        # model always escalates, regardless of how confident it claims to be.
        assert decision == "frontier_escalation", (
            "an UNQUALIFIED live model was not escalated -- the evidence gate "
            f"did not hold: {decision}"
        )


def test_deterministic_code_still_wins_over_a_live_model(
    live_client: OllamaClient,
) -> None:
    """The local clerk is never consulted when real code can already answer.

    Worth proving against a LIVE model specifically: with a real daemon
    available it becomes tempting to use it, and this is the rule that keeps a
    working parser from being replaced by an LLM guess.
    """
    from aios.application.local_workforce.dispatcher import dispatch_clerical_job

    result = LocalModelQualificationAuthority(live_client).run()

    decision = dispatch_clerical_job(
        deterministic_available=True,
        qualification=result,
        confidence=0.99,
    )

    assert decision == "deterministic", (
        f"deterministic path available but dispatcher chose {decision}"
    )


def test_the_live_verdict_is_recorded_as_evidence(live_client: OllamaClient) -> None:
    """The verdict must be durable and inspectable, not a transient boolean.

    Organ 37's whole purpose is evidence-backed admission; a result that
    cannot be serialised could not be attached to a passport or a ledger row.
    """
    result = LocalModelQualificationAuthority(live_client).run()

    payload = json.loads(result.model_dump_json())

    assert payload["suite_version"] == QUALIFICATION_SUITE_VERSION
    assert payload["test_results"], "serialised result carries no case evidence"
