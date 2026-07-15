from __future__ import annotations

import math
import time
from pathlib import Path

import pytest

from aios.memory.pheromones import Pheromone, PheromoneStore, PheromoneType


def _store(tmp_path: Path, **kwargs) -> PheromoneStore:
    return PheromoneStore(db_path=tmp_path / "pheromones.sqlite3", **kwargs)


def test_deposit_and_query(tmp_path: Path) -> None:
    store = _store(tmp_path)
    pid = store.deposit(
        PheromoneType.SUCCESS_TRAIL,
        "src/foo.py",
        "worker-1",
        strength=0.9,
        payload={"summary": "passed 2 times"},
    )
    assert isinstance(pid, int)
    results = store.query(resource="src/foo.py")
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, Pheromone)
    assert result.resource == "src/foo.py"
    assert result.ptype == PheromoneType.SUCCESS_TRAIL
    assert result.depositor == "worker-1"
    assert result.payload == {"summary": "passed 2 times"}
    assert 0.0 < result.strength <= 0.9


def test_decay_formula(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    pid = store.deposit(PheromoneType.SUCCESS_TRAIL, "src/bar.py", "worker-2", strength=1.0)

    hours_elapsed = 35.0
    monkeypatch.setattr(time, "time", lambda: base_time + hours_elapsed * 3600.0)
    results = store.query(resource="src/bar.py", min_strength=0.0)
    assert len(results) == 1
    expected = 1.0 * math.exp(-0.02 * hours_elapsed)
    assert results[0].strength == pytest.approx(expected, rel=1e-9)
    assert results[0].strength == pytest.approx(0.5, rel=0.02)
    assert results[0].pheromone_id == pid


def test_reinforce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path)
    pid = store.deposit(PheromoneType.SUCCESS_TRAIL, "src/baz.py", "worker-3", strength=0.5)

    monkeypatch.setattr(time, "time", lambda: base_time + 10 * 3600.0)
    before = store.query(resource="src/baz.py", min_strength=0.0)[0]

    store.reinforce(pid, boost=0.3)
    after_reinforce_time = base_time + 10 * 3600.0
    monkeypatch.setattr(time, "time", lambda: after_reinforce_time)
    after = store.query(resource="src/baz.py", min_strength=0.0)[0]

    assert after.strength > before.strength
    assert after.strength == pytest.approx(0.8, rel=1e-9)


def test_query_min_strength_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/old.py", "worker-4", strength=1.0)

    monkeypatch.setattr(time, "time", lambda: base_time + 500 * 3600.0)
    results = store.query(resource="src/old.py", min_strength=0.1)
    assert results == []

    results_low_threshold = store.query(resource="src/old.py", min_strength=0.0)
    assert len(results_low_threshold) == 1


def test_decay_all_prunes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_time = 1_800_000_000.0
    monkeypatch.setattr(time, "time", lambda: base_time)
    store = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    store.deposit(PheromoneType.FAILURE_WARNING, "src/expired.py", "worker-5", strength=0.5)
    store.deposit(PheromoneType.FAILURE_WARNING, "src/fresh.py", "worker-5", strength=1.0)

    monkeypatch.setattr(time, "time", lambda: base_time + 400 * 3600.0)
    pruned = store.decay_all()
    assert pruned == 2

    monkeypatch.setattr(time, "time", lambda: base_time)
    store2 = _store(tmp_path, lambda_decay=0.02, floor=0.01)
    store2.deposit(PheromoneType.FAILURE_WARNING, "src/keep.py", "worker-6", strength=1.0)
    monkeypatch.setattr(time, "time", lambda: base_time + 3600.0)
    pruned2 = store2.decay_all()
    assert pruned2 == 0
    assert len(store2.query(resource="src/keep.py", min_strength=0.0)) == 1


def test_for_contract(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.deposit(
        PheromoneType.SUCCESS_TRAIL,
        "path/to/file.py",
        "worker-7",
        strength=0.85,
        payload={"outcome": "passed", "count": 3},
    )
    contexts = store.for_contract(["path/to/file.py", "path/to/other.py"])
    assert len(contexts) == 1
    assert contexts[0].startswith("[success-trail] path/to/file.py (strength=0.")
    assert "passed 3 times" in contexts[0]


def test_query_by_type(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/mixed.py", "worker-8", strength=0.9)
    store.deposit(PheromoneType.FAILURE_WARNING, "src/mixed.py", "worker-8", strength=0.9)
    store.deposit(PheromoneType.FILE_LOCK, "src/mixed.py", "worker-8", strength=0.9)

    success_only = store.query(resource="src/mixed.py", ptype=PheromoneType.SUCCESS_TRAIL)
    assert len(success_only) == 1
    assert success_only[0].ptype == PheromoneType.SUCCESS_TRAIL

    all_results = store.query(resource="src/mixed.py")
    assert len(all_results) == 3


def test_empty_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.query() == []
    assert store.query(resource="does/not/exist.py") == []
    assert store.for_contract([]) == []
    assert store.for_contract(["does/not/exist.py"]) == []
    assert store.decay_all() == 0


def test_multiple_resources(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/a.py", "worker-9", strength=0.7)
    store.deposit(PheromoneType.SUCCESS_TRAIL, "src/b.py", "worker-9", strength=0.9)

    results_a = store.query(resource="src/a.py")
    results_b = store.query(resource="src/b.py")
    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0].resource == "src/a.py"
    assert results_b[0].resource == "src/b.py"

    all_results = store.query()
    assert len(all_results) == 2


def test_council_loads_pheromone_context_into_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aios import config
    from aios.council.council_orchestrator import CouncilOrchestrator
    from aios.council.queens.planner import CouncilMissionRequest

    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    store = _store(tmp_path)
    store.deposit(
        PheromoneType.SUCCESS_TRAIL,
        "src/foo.py",
        "worker-forager",
        strength=0.9,
        payload={"summary": "similar edit verified twice"},
    )

    run = CouncilOrchestrator(
        runtime_root=tmp_path / "runtime",
        pheromone_store=store,
    ).deliberate(
        CouncilMissionRequest(
            mission_id="mission-pheromone-context",
            goal="edit foo safely",
            workspace_root=tmp_path / "workspace",
            allowed_files=["src/foo.py"],
            allowed_tools=["read_file"],
            verification_commands=[],
        )
    )

    assert any("similar edit verified twice" in item for item in run.contract.pheromone_context)
    assert run.contract.metadata["pheromone_context_non_authoritative"] is True
    memory_verdict = next(v for v in run.verdicts if v.queen == "memory")
    assert any("[success-trail] src/foo.py" in item for item in memory_verdict.constraints)


def test_council_prefers_authority_pheromone_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aios import config
    from aios.council.council_orchestrator import CouncilOrchestrator
    from aios.runtime.contracts import MissionContract

    class Authority:
        def pheromone_for_contract(self, allowed_files: list[str]) -> list[str]:
            assert allowed_files == ["src/foo.py"]
            return ["authority-sourced hint"]

    class ForbiddenStore:
        def for_contract(self, allowed_files: list[str]) -> list[str]:
            raise AssertionError("Council bypassed the authority-owned adapter")

    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    orchestrator = CouncilOrchestrator(
        runtime_root=tmp_path / "runtime-authority",
        memory_authority=Authority(),
        pheromone_store=ForbiddenStore(),
    )
    contract = MissionContract(
        mission_id="mission-authority-pheromone",
        goal="use advisory context",
        worker_type="scout",
        created_by="test",
        workspace_root=str(tmp_path),
        allowed_files=["src/foo.py"],
    )

    enriched = orchestrator._apply_pheromone_context(contract)

    assert enriched.pheromone_context == ["authority-sourced hint"]
    assert enriched.metadata["pheromone_context_source"] == (
        "MemoryAuthority.pheromone_for_contract"
    )


def test_pheromone_context_cannot_override_red_security_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aios import config
    from aios.council.council_orchestrator import CouncilOrchestrator
    from aios.council.queens.planner import CouncilMissionRequest

    monkeypatch.setattr(config, "PHEROMONE_ENABLED", True)
    store = _store(tmp_path)
    store.deposit(
        PheromoneType.SUCCESS_TRAIL,
        "aios/security/gateway.py",
        "worker-builder",
        strength=1.0,
        payload={"summary": "previous protected edit claimed success"},
    )

    run = CouncilOrchestrator(
        runtime_root=tmp_path / "runtime-red",
        pheromone_store=store,
    ).deliberate(
        CouncilMissionRequest(
            mission_id="mission-pheromone-red",
            goal="edit protected gateway",
            workspace_root=tmp_path / "workspace",
            allowed_files=["aios/security/gateway.py"],
            allowed_tools=["read_file"],
            verification_commands=[],
        )
    )

    assert any("previous protected edit claimed success" in item for item in run.contract.pheromone_context)
    security_verdict = next(v for v in run.verdicts if v.queen == "security")
    assert security_verdict.verdict == "deny"
    assert security_verdict.risk == "RED"
    assert run.worker_run is None
    assert run.report.risk == "RED"
