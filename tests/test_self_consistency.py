from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from aios.core.self_consistency import elect_best, run_self_consistency
from aios.core.verifier import VerificationStrength, VerifierResult


def make_result(passed, passed_count=1, confidence_delta=0.0):
    return VerifierResult(
        passed=passed,
        summary="test",
        confidence_delta=confidence_delta,
        passed_count=passed_count,
        failed_count=0 if passed else 1,
        exit_code=0 if passed else 1,
        status="OK",
        strength=VerificationStrength.MEDIUM,
    )


def make_verifier(results):
    verifier = MagicMock()
    verifier.verify.side_effect = results
    return verifier


def test_all_pass_picks_best():
    results = [
        make_result(True, passed_count=2),
        make_result(True, passed_count=5),
        make_result(True, passed_count=3),
    ]
    verifier = make_verifier(results)
    outcome = run_self_consistency(verifier, ["a", "b", "c"])
    assert outcome.winner_index == 1
    assert outcome.winner_result is results[1]
    assert outcome.pass_count == 3
    assert outcome.fail_count == 0


def test_majority_pass():
    results = [
        make_result(True, passed_count=4),
        make_result(True, passed_count=1),
        make_result(False, confidence_delta=-0.5),
    ]
    verifier = make_verifier(results)
    outcome = run_self_consistency(verifier, ["a", "b", "c"])
    assert outcome.votes == [True, True, False]
    assert outcome.winner_index in (0, 1)
    assert results[outcome.winner_index].passed
    assert outcome.winner_index == 0


def test_majority_fail():
    results = [
        make_result(True, passed_count=1),
        make_result(False, confidence_delta=-0.8),
        make_result(False, confidence_delta=-0.2),
    ]
    verifier = make_verifier(results)
    outcome = run_self_consistency(verifier, ["a", "b", "c"])
    assert outcome.pass_count == 1
    assert outcome.fail_count == 2
    assert not results[outcome.winner_index].passed
    assert outcome.winner_index == 2


def test_all_fail():
    results = [
        make_result(False, confidence_delta=-0.9),
        make_result(False, confidence_delta=-0.3),
        make_result(False, confidence_delta=-0.6),
    ]
    verifier = make_verifier(results)
    outcome = run_self_consistency(verifier, ["a", "b", "c"])
    assert outcome.winner_index == 1
    assert outcome.consensus is True
    assert outcome.pass_count == 0
    assert outcome.fail_count == 3


def test_consensus_flag():
    results = [
        make_result(True, passed_count=1),
        make_result(True, passed_count=2),
        make_result(True, passed_count=3),
    ]
    verifier = make_verifier(results)
    outcome = run_self_consistency(verifier, ["a", "b", "c"])
    assert outcome.consensus is True

    results_split = [
        make_result(True, passed_count=1),
        make_result(True, passed_count=2),
        make_result(False, confidence_delta=-0.1),
    ]
    verifier2 = make_verifier(results_split)
    outcome2 = run_self_consistency(verifier2, ["a", "b", "c"])
    assert outcome2.consensus is True


def test_tiebreak_by_passed_count():
    results = [
        make_result(True, passed_count=2, confidence_delta=0.0),
        make_result(True, passed_count=5, confidence_delta=0.0),
        make_result(True, passed_count=5, confidence_delta=0.0),
    ]
    verifier = make_verifier(results)
    outcome = run_self_consistency(verifier, ["a", "b", "c"])
    assert outcome.winner_index == 1


def test_minimum_candidates():
    verifier = make_verifier([make_result(True), make_result(True)])
    with pytest.raises(ValueError):
        run_self_consistency(verifier, ["a", "b"])


def test_elect_best_shortcut():
    results = [
        make_result(True, passed_count=1),
        make_result(True, passed_count=9),
        make_result(True, passed_count=2),
    ]
    verifier = make_verifier(results)
    winner_index, winner_result = elect_best(verifier, ["a", "b", "c"])
    assert winner_index == 1
    assert winner_result is results[1]
