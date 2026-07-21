"""Critique Queen — scrutinizes verification SUFFICIENCY (was the green earned?).

It is a SECOND-ORDER check on the Testing Queen: even a passing verification can be
insufficient (weak strength, or it never exercised the changed files). Deterministic
and STRENGTHEN-ONLY — it can only ADD caution (defer), never relax a block.
"""
from __future__ import annotations

from aios.council.queens.critique import CritiqueQueen
from aios.runtime.contracts import MissionContract, QueenVerdict


def _contract(allowed_files, verification_commands):
    return MissionContract(
        mission_id="m1",
        goal="do the thing",
        worker_type="editor",
        created_by="test",
        workspace_root="/ws",
        allowed_files=list(allowed_files),
        verification_commands=list(verification_commands),
    )


def _testing(verdict="allow", strength="STRONG"):
    return QueenVerdict(
        queen="testing",
        verdict=verdict,
        risk="GREEN" if verdict == "allow" else "YELLOW",
        reason="testing said so",
        confidence=0.9,
        metadata={"verification_strength": strength, "verification": []},
    )


def test_strong_and_covered_is_allowed() -> None:
    v = CritiqueQueen().review(
        contract=_contract(["greet.py"], ["python greet.py"]),
        testing_verdict=_testing(verdict="allow", strength="STRONG"),
    )
    assert v.queen == "critique"
    assert v.verdict == "allow"


def test_weak_strength_on_pass_defers() -> None:
    v = CritiqueQueen().review(
        contract=_contract(["greet.py"], ["python greet.py"]),
        testing_verdict=_testing(verdict="allow", strength="WEAK"),
    )
    assert v.verdict == "defer"
    assert "below" in v.reason.lower() or "weak" in v.reason.lower()


def test_strong_but_uncovered_defers() -> None:
    # STRONG strength, but the verification never references the changed file.
    v = CritiqueQueen().review(
        contract=_contract(["greet.py"], ["echo done"]),
        testing_verdict=_testing(verdict="allow", strength="STRONG"),
    )
    assert v.verdict == "defer"
    assert "greet.py" in v.reason


def test_orchestrator_gates_critique_on_flag(tmp_path, monkeypatch) -> None:
    from aios import config
    from aios.council.council_orchestrator import CouncilOrchestrator

    monkeypatch.setattr(config, "COUNCIL_CRITIQUE", False)
    assert CouncilOrchestrator(runtime_root=tmp_path).critique is None

    monkeypatch.setattr(config, "COUNCIL_CRITIQUE", True)
    assert isinstance(CouncilOrchestrator(runtime_root=tmp_path).critique, CritiqueQueen)


def test_concurs_when_testing_already_blocks() -> None:
    # Testing denied — the gate already blocks; critique must NOT pile on noise,
    # and (strengthen-only) it never flips a block to allow on its own.
    v = CritiqueQueen().review(
        contract=_contract(["greet.py"], ["echo done"]),
        testing_verdict=_testing(verdict="deny", strength="NONE"),
    )
    assert v.verdict == "allow"
    assert v.metadata.get("deferred_to") == "testing"
