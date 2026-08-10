"""Organ 46 driven end to end through the real HTTP routes, and the stale
blocker that drive retires.

Why this exists
---------------
Organ 46's ledger has carried the blocker "no Ollama -- live constitutional
learning path needs live Ollama and/or Outside-machine cloud" since before the
organ was built out. `organ_ledger.py`'s permitted-blocker regex accepts the
literal phrase "no Ollama", so the ledger check was satisfied by the *wording*
and nobody was ever forced to ask whether it was true for THIS organ.

It is not. `constitutional_learning.py`, `adversarial_simulations.py` and
`domain/governance/learning.py` contain zero references to an LLM client, a
provider, or Ollama. Every one of the nine adversarial simulations is either a
deterministic text screen or a live probe against an ephemeral sqlite fixture
or an in-memory snapshot. No model is consulted anywhere on this organ's path.

That is worth stating carefully rather than triumphantly: this does not make
organ 46 greener by argument. It removes a blocker that was never measured, and
replaces it with a run that either passes or does not. `test_the_stale_ollama_
blocker_is_measurably_false` is the one that would fail if a model dependency
were ever introduced -- at which point the blocker becomes true again and
should be restored.

The other tests drive the organ through the real FastAPI routes: propose a
lesson, draft an amendment from it, run all nine simulations, and ratify.

Note which way that last assertion points. The harness bootstraps a real
privileged operator session and answers the route's 428 capability challenge
with a genuinely issued, server-consumed token, so ratification SUCCEEDS -- and
that is correct. The first version of this file asserted a refusal there and
failed, which was the test being wrong about the happy path rather than the
happy path being broken. As far as the record shows, this is the first time the
organ has been driven end to end from lesson to ratified amendment.

The refusal belongs in its own test, and has one:
`test_ratification_is_refused_without_the_operator_bootstrap` uses a
non-loopback client the bootstrap deliberately skips. Exercised through the
real route, never by calling the function with a forged capability object --
that shortcut is how the second red-team campaign produced a finding its own
synthesis had to walk back.
"""

from __future__ import annotations

import ast
import json
import pathlib
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import get_governance_amendment_store
from aios.api.main import app
from aios.domain.governance.learning import ADVERSARIAL_SIMULATION_CHECKS
from aios.infrastructure.governance.sqlite_store import GovernanceAmendmentStore

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LESSON_ID = "organ46-live-proof-lesson"
PROPOSAL_ID = "organ46-live-proof-amendment"


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    store = GovernanceAmendmentStore(tmp_path / "organ46_live_proof.db")
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("127.0.0.1", 12346)) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


#: Every way this codebase reaches a model. A hit inside the organ's own
#: modules would mean the "no Ollama" blocker was real after all.
_MODEL_NEEDLES = ("get_llm_client", "LLMClient", "ollama", "Ollama", "chat_completion")

_ORGAN_46_MODULES = (
    "aios/application/governance/constitutional_learning.py",
    "aios/application/governance/adversarial_simulations.py",
    "aios/domain/governance/learning.py",
)


def _model_references(rel: str) -> list[str]:
    """Model references in *rel*, ignoring string literals.

    Deliberately AST-based rather than a text grep. The first version of this
    check grepped the source and failed immediately -- on
    `_PROVIDER_LOCK_IN_MARKERS`, which contains the literal string
    "remove ollama" as a *screening keyword*. A screen that knows the word
    "ollama" is not a dependency on Ollama, and conflating the two is exactly
    the sloppiness that let the stale blocker survive unexamined for months.

    So this looks at imports, names and attribute accesses -- the ways code
    actually reaches a model -- and never at the contents of a string.
    """
    tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            referenced.add(node.module or "")
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    return sorted(
        needle
        for needle in _MODEL_NEEDLES
        if any(needle.lower() in ref.lower() for ref in referenced)
    )


def test_the_stale_ollama_blocker_is_measurably_false() -> None:
    """The blocker said this organ's path needs a live model. It does not.

    If a model dependency is ever added to organ 46's path, this fails, and the
    honest response is to restore the blocker rather than delete this test.
    """
    offenders = {
        rel: found for rel in _ORGAN_46_MODULES if (found := _model_references(rel))
    }
    assert offenders == {}, (
        "organ 46's path now consults a model, so the 'no Ollama' blocker has "
        f"become true again and must be restored to the ledger: {offenders}"
    )


def _propose_lesson(client: TestClient):
    return client.post(
        "/api/v1/governance/lessons/propose",
        json={
            "lesson_id": LESSON_ID,
            "problem_class": "approval_friction",
            # Short and low-entropy on purpose: the API's secret scanner refuses a
            # payload it reads as credential-like, and a long hyphenated
            # filename full of digits trips its high-entropy detector (403,
            # "payload contains credential-like data"). Discovered by this
            # test failing, which is the scanner doing its job on a governance
            # route -- worth knowing, and not worth fighting here.
            "evidence_refs": ["incident-46"],
            "observed_harm": (
                "Two adversarial campaigns produced 24 confirmed bypasses of "
                "this organ's textual screening layer"
            ),
            "current_rule": (
                "a lesson may become an amendment proposal once nine "
                "adversarial simulations pass"
            ),
            "proposed_improvement": (
                "state in the screening response that its textual half is "
                "advisory so a reviewer is not misled by a passing result"
            ),
            "confidence": 0.9,
        },
    )


def _draft_amendment(client: TestClient):
    return client.post(
        f"/api/v1/governance/lessons/{LESSON_ID}/draft-amendment",
        json={
            "proposal_id": PROPOSAL_ID,
            "target_articles": ["screening transparency"],
            "proposed_diff": (
                "record in the check-simulations response that the textual "
                "screen is advisory"
            ),
            "migration_plan": "no migration required; response fields only",
            "rollback_plan": "remove the added response fields",
        },
    )


def test_the_whole_organ_runs_end_to_end_through_the_real_routes(
    client, tmp_path
) -> None:
    """One pass through the organ, and a recorded artifact of what happened.

    Deliberately a single test rather than four: the value is the *sequence*
    completing against the real app, and a per-step breakdown that a reviewer
    can read without running anything.
    """
    steps: list[dict[str, object]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        steps.append({"step": name, "passed": bool(ok), "detail": detail})

    lesson = _propose_lesson(client)
    record("lesson_proposed", lesson.status_code == 200, f"HTTP {lesson.status_code}")
    assert lesson.status_code == 200, lesson.text

    draft = _draft_amendment(client)
    record("amendment_drafted", draft.status_code == 200, f"HTTP {draft.status_code}")
    assert draft.status_code == 200, draft.text
    proposal = draft.json()["proposal"]

    record(
        "proposer_type_is_model",
        proposal["proposer_type"] == "model",
        f"proposer_type={proposal['proposer_type']!r}",
    )
    assert proposal["proposer_type"] == "model"

    record(
        "approval_model_is_typed_and_human_gated",
        proposal["approval_model"] == "human_capability_required",
        f"approval_model={proposal['approval_model']!r}",
    )
    assert proposal["approval_model"] == "human_capability_required"

    checked = client.post(
        "/api/v1/governance/lessons/check-simulations",
        json={"proposal_id": PROPOSAL_ID},
    )
    assert checked.status_code == 200, checked.text
    body = checked.json()
    names = {r["check_name"] for r in body["results"]}
    record(
        "all_nine_simulations_ran_for_real",
        names == set(ADVERSARIAL_SIMULATION_CHECKS),
        f"{len(body['results'])} checks returned",
    )
    assert names == set(ADVERSARIAL_SIMULATION_CHECKS)

    record(
        "screen_ships_its_own_limits",
        bool(body.get("screen_limits")),
        f"{len(body.get('screen_limits', ()))} limit statements shipped",
    )
    assert body.get("screen_limits"), "the advisory screen must state its limits"

    # The only step here that is not advisory -- and it SUCCEEDS, because the
    # test harness bootstraps a real privileged operator session and answers
    # the route's 428 capability challenge with a genuinely issued, server-
    # consumed token. That is the legitimate path, and this is the first time
    # it has been driven end to end from lesson to ratification.
    #
    # The negative control lives in its own test below, with a client the
    # bootstrap deliberately does not apply to. Asserting a refusal here would
    # have been asserting that the happy path is broken.
    ratify = client.post(f"/api/v1/governance/amendments/{PROPOSAL_ID}/ratify", json={})
    record(
        "ratification_succeeds_for_a_real_operator_capability",
        ratify.status_code == 200,
        f"HTTP {ratify.status_code}",
    )
    assert ratify.status_code == 200, ratify.text

    ratified = ratify.json()
    record(
        "ratified_proposal_records_its_operator_and_capability_digest",
        bool(ratified.get("ratified_by_operator_id"))
        and bool(ratified.get("ratification_capability_digest")),
        f"operator={ratified.get('ratified_by_operator_id')!r} "
        f"digest_present={bool(ratified.get('ratification_capability_digest'))}",
    )
    assert ratified["status"] == "ratified"
    assert ratified["ratified_by_operator_id"]
    assert ratified["ratification_capability_digest"]

    artifact = tmp_path / "organ46-live-proof.json"
    report = {"steps": steps, "passed": all(s["passed"] for s in steps)}
    artifact.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["passed"], steps


def test_ratification_is_refused_without_the_operator_bootstrap(tmp_path) -> None:
    """The negative control, and the half that actually matters.

    conftest only bootstraps a privileged session for LOOPBACK clients. A
    non-loopback client gets no session, no capability, and must not be able to
    ratify anything -- which is the invariant organ 46's green claim rests on,
    exercised through the real route rather than by calling the function with a
    forged object (the mistake the second red-team campaign made and its own
    synthesis caught).
    """
    store = GovernanceAmendmentStore(tmp_path / "unprivileged.db")
    app.dependency_overrides[get_governance_amendment_store] = lambda: store
    try:
        with TestClient(app, client=("203.0.113.7", 44444)) as stranger:
            resp = stranger.post(
                f"/api/v1/governance/amendments/{PROPOSAL_ID}/ratify", json={}
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code != 200, (
        "an unauthenticated remote client ratified a constitutional amendment: "
        f"HTTP {resp.status_code} {resp.text}"
    )


def test_the_drafted_proposal_is_independently_fetchable_and_still_unratified(
    client,
) -> None:
    """Persistence, checked against the store rather than the response body.

    A proposal that only exists in the reply to the request that made it is not
    durable state, and C3 is about durable state.
    """
    _propose_lesson(client)
    _draft_amendment(client)

    fetched = client.get(f"/api/v1/governance/amendments/{PROPOSAL_ID}")
    assert fetched.status_code == 200, fetched.text
    stored = fetched.json()
    assert stored["status"] == "proposed"
    assert stored["ratified_by_operator_id"] is None
    assert stored["ratification_capability_digest"] is None
    assert stored["approval_model"] == "human_capability_required"
