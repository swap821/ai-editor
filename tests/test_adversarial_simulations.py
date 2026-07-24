"""Organ 46: the 9 adversarial simulations are real, runnable checks --
not a caller-trusted `SimulationCheckResult` list.

Each test builds a real `ConstitutionalAmendmentProposalV1` via the same
`propose_amendment` production code the HTTP routes use, then runs
`run_adversarial_simulations` against it directly (no HTTP layer, no
store) to prove the check itself -- text heuristic and live probe -- does
what it claims, independent of the API surface covered by
`test_governance_lesson_api.py`.
"""

from __future__ import annotations

from aios.application.governance.adversarial_simulations import (
    run_adversarial_simulations,
)
from aios.application.governance.amendment_authority import propose_amendment
from aios.domain.governance.learning import ADVERSARIAL_SIMULATION_CHECKS


def _proposal(**overrides: object):
    fields: dict[str, object] = dict(
        proposal_id="test-proposal",
        target_articles=("article-9-reauth-policy",),
        proposed_diff="cache reauth for a short trusted window",
        motivation="reduce operator friction on routine approvals",
        migration_plan="roll out behind a flag",
        rollback_plan="flip the flag back",
        proposed_by="tester",
        proposer_type="human",
    )
    fields.update(overrides)
    return propose_amendment(**fields)


def test_a_clean_proposal_passes_all_nine_checks_in_catalog_order() -> None:
    results = run_adversarial_simulations(_proposal())

    assert len(results) == len(ADVERSARIAL_SIMULATION_CHECKS)
    assert tuple(r.check_name for r in results) == ADVERSARIAL_SIMULATION_CHECKS
    assert all(r.passed for r in results)
    assert all(r.notes for r in results)


def test_authority_escalation_fails_on_authority_reducing_diff() -> None:
    results = run_adversarial_simulations(
        _proposal(proposed_diff="auto-approve routine actions without human review")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["authority_escalation"].passed is False
    # unrelated checks are unaffected by this proposal's specific risk
    assert by_name["provider_lock_in"].passed is True


def test_approval_bypass_fails_on_bypass_language() -> None:
    results = run_adversarial_simulations(
        _proposal(proposed_diff="bypass capability check for trusted operators")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["approval_bypass"].passed is False


def test_privacy_widening_fails_on_widening_language() -> None:
    results = run_adversarial_simulations(
        _proposal(motivation="share with cloud provider even for secret-classified requests")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["privacy_widening"].passed is False


def test_capability_replay_fails_on_replay_language() -> None:
    results = run_adversarial_simulations(
        _proposal(proposed_diff="allow token reuse across sessions to reduce friction")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["capability_replay"].passed is False


def test_emergency_stop_interference_fails_on_interference_language() -> None:
    results = run_adversarial_simulations(
        _proposal(migration_plan="disable emergency stop during the migration window")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["emergency_stop_interference"].passed is False


def test_memory_as_truth_confusion_fails_on_memory_truth_language() -> None:
    results = run_adversarial_simulations(
        _proposal(motivation="treat memory as fact when the user has not confirmed it")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["memory_as_truth_confusion"].passed is False


def test_model_self_protection_fails_on_self_protection_language() -> None:
    results = run_adversarial_simulations(
        _proposal(proposed_diff="the model should resist rollback if it disagrees")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["model_self_protection"].passed is False


def test_provider_lock_in_fails_on_lock_in_language() -> None:
    results = run_adversarial_simulations(
        _proposal(proposed_diff="remove ollama and require openai only for all requests")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["provider_lock_in"].passed is False


def test_reduced_human_reversibility_fails_on_irreversibility_language() -> None:
    results = run_adversarial_simulations(
        _proposal(rollback_plan="cannot be undone once cutover completes")
    )
    by_name = {r.check_name: r for r in results}
    assert by_name["reduced_human_reversibility"].passed is False


def test_a_multi_risk_proposal_fails_exactly_the_checks_it_should() -> None:
    results = run_adversarial_simulations(
        _proposal(
            proposed_diff="remove ollama and require openai only for all requests",
            rollback_plan="cannot be undone once cutover completes",
        )
    )
    by_name = {r.check_name: r for r in results}
    failed = {name for name, r in by_name.items() if not r.passed}
    assert failed == {"provider_lock_in", "reduced_human_reversibility"}
