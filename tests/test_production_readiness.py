"""The production scoreboard measures; it never asserts.

Pinned, both directions for every gate: the bar met reads PASS, the bar missed
reads FAIL. Beyond that, the properties that make it an honest instrument:

* a probe that raises is ERROR -- never PASS, never a FAIL the system earned;
* an unmeasured property (NOT_MEASURED) keeps the machine NOT READY;
* live databases are opened read-only, and a key's value never reaches output;
* v1-check runs against a throwaway data directory, in this environment.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tools import production_readiness as pr


def _world(tmp_path: Path, **over: Any) -> pr.World:
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / ".aios" / "state").mkdir(parents=True, exist_ok=True)
    (repo / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    data.mkdir(exist_ok=True)
    fields: dict[str, Any] = {
        "repo": repo,
        "data_dir": data,
        "env": {},
        "run": lambda argv, env: (1, ""),
        "http_json": lambda url: None,
        "http_status": lambda url: None,
        "now": datetime(2026, 10, 11, tzinfo=timezone.utc),
    }
    fields.update(over)
    return pr.World(**fields)


def _compose(world: pr.World, environment: list[str]) -> None:
    import yaml

    (world.repo / "docker-compose.yml").write_text(
        yaml.safe_dump({"services": {"aios": {"environment": environment}}}),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# The instrument's own honesty
# --------------------------------------------------------------------------- #


def test_a_probe_that_raises_is_an_error_never_a_verdict(tmp_path, monkeypatch) -> None:
    def broken(world):
        raise RuntimeError("probe died")

    monkeypatch.setattr(pr, "GATES", (broken,))
    gates = pr.measure(_world(tmp_path))
    assert gates[0].status == pr.ERROR and "probe died" in gates[0].evidence
    assert not pr.ready(gates)


def test_unmeasured_properties_keep_the_machine_not_ready(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(pr, "GATES", (lambda w: pr.Gate("cage", "x", pr.PASS, "ok"),))
    gates = pr.measure(_world(tmp_path))
    assert any(g.status == pr.NOT_MEASURED for g in gates)
    assert not pr.ready(gates)
    monkeypatch.setattr(pr, "NOT_YET", ())
    assert pr.ready(pr.measure(_world(tmp_path))), "the control: all PASS is ready"


def test_nothing_is_ready_with_no_gates() -> None:
    assert not pr.ready([])


def test_the_exit_code_is_zero_only_when_ready(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pr, "real_world", lambda measure_v1: _world(tmp_path))
    monkeypatch.setattr(pr, "NOT_YET", ())
    monkeypatch.setattr(pr, "GATES", (lambda w: pr.Gate("cage", "x", pr.FAIL, "no"),))
    assert pr.main([]) == 1
    monkeypatch.setattr(pr, "GATES", (lambda w: pr.Gate("cage", "x", pr.PASS, "ok"),))
    assert pr.main([]) == 0


# --------------------------------------------------------------------------- #
# Cage
# --------------------------------------------------------------------------- #


def test_v1_check_runs_in_a_throwaway_data_dir_with_this_environment(tmp_path) -> None:
    seen: dict[str, Any] = {}

    def run(argv, env):
        seen.update(argv=argv, env=dict(env))
        return 0, json.dumps({"ready": True})

    world = _world(tmp_path, run=run, env={"AIOS_VERIFICATION_AUTHORITY_KEY": "k"})
    assert pr.cage_v1_check(world).status == pr.PASS
    assert seen["argv"][-2:] == ["v1-check", "--json"]
    assert Path(seen["env"]["AIOS_DATA_DIR"]) != world.data_dir
    assert seen["env"]["AIOS_VERIFICATION_AUTHORITY_KEY"] == "k", (
        "env must be inherited"
    )


def test_v1_check_failures_and_a_silent_v1_check(tmp_path) -> None:
    report = {"ready": False, "failures": ["isolated_executor"]}
    world = _world(tmp_path, run=lambda a, e: (1, json.dumps(report)))
    gate = pr.cage_v1_check(world)
    assert gate.status == pr.FAIL and "isolated_executor" in gate.evidence
    silent = _world(tmp_path, run=lambda a, e: (1, "Traceback ..."))
    assert pr.cage_v1_check(silent).status == pr.ERROR
    assert (
        pr.cage_v1_check(_world(tmp_path, measure_v1=False)).status == pr.NOT_MEASURED
    )


def test_the_organ_ledger_gate(tmp_path) -> None:
    world = _world(tmp_path)
    ledger = world.repo / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
    ledger.write_text(
        json.dumps([{"organ_id": 1, "status": "green"}]), encoding="utf-8"
    )
    assert pr.cage_organ_ledger(world).status == pr.PASS
    ledger.write_text(
        json.dumps(
            [{"organ_id": 1, "status": "green"}, {"organ_id": 2, "status": "yellow"}]
        ),
        encoding="utf-8",
    )
    gate = pr.cage_organ_ledger(world)
    assert gate.status == pr.FAIL and "[2]" in gate.evidence


def _runs(*conclusions: str) -> str:
    return json.dumps(
        [
            {"status": "completed", "conclusion": c, "createdAt": "2026-10-1%dT00" % i}
            for i, c in enumerate(conclusions)
        ]
    )


def test_the_nightly_gate_needs_three_green_nights(tmp_path) -> None:
    ok = _world(tmp_path, run=lambda a, e: (0, _runs("success", "success", "success")))
    assert pr.cage_nightly(ok).status == pr.PASS
    red = _world(tmp_path, run=lambda a, e: (0, _runs("success", "failure", "success")))
    assert pr.cage_nightly(red).status == pr.FAIL
    short = _world(tmp_path, run=lambda a, e: (0, _runs("success")))
    assert pr.cage_nightly(short).status == pr.FAIL, "one green night is not three"
    no_gh = _world(tmp_path, run=lambda a, e: (127, "gh: not found"))
    assert pr.cage_nightly(no_gh).status == pr.ERROR


def test_cancelled_runs_are_not_counted(tmp_path) -> None:
    world = _world(tmp_path, run=lambda a, e: (0, _runs("cancelled", "success")))
    assert pr.cage_master_ci(world).status == pr.PASS


# --------------------------------------------------------------------------- #
# Sovereign
# --------------------------------------------------------------------------- #


def test_production_started_reads_the_launchers_own_state(tmp_path) -> None:
    world = _world(tmp_path)
    assert pr.sovereign_production_started(world).status == pr.FAIL
    (world.data_dir / "launcher-state.json").write_text(
        json.dumps({"profile": "development"})
    )
    assert pr.sovereign_production_started(world).status == pr.FAIL
    (world.data_dir / "launcher-state.json").write_text(
        json.dumps({"profile": "production"})
    )
    assert pr.sovereign_production_started(world).status == pr.PASS


def test_backend_ready_is_the_readiness_probe(tmp_path) -> None:
    urls: list[str] = []

    def status(url):
        urls.append(url)
        return 200

    assert (
        pr.sovereign_backend_ready(_world(tmp_path, http_status=status)).status
        == pr.PASS
    )
    assert urls == ["http://127.0.0.1:8000/ready"]
    assert (
        pr.sovereign_backend_ready(_world(tmp_path, http_status=lambda u: 503)).status
        == pr.FAIL
    )


def test_backups_count_only_restorable_archives(tmp_path) -> None:
    world = _world(tmp_path)
    backups = world.data_dir / "backups"
    backups.mkdir()
    (backups / "aios_memory.adhoc.db").write_bytes(b"x")
    assert pr.sovereign_backups(world).status == pr.FAIL, (
        "an ad hoc copy is not a backup"
    )
    (backups / "gagos-20261011.tar.gz").write_bytes(b"x")
    assert pr.sovereign_backups(world).status == pr.PASS


@pytest.mark.parametrize(
    "environment, status",
    [
        (["AIOS_PROFILE=production"], pr.FAIL),
        (["OLLAMA_HOST=http://127.0.0.1:11434"], pr.FAIL),
        (["OLLAMA_HOST=http://localhost:11434"], pr.FAIL),
        (["OLLAMA_HOST=http://host.docker.internal:11434"], pr.PASS),
    ],
)
def test_the_production_container_must_reach_the_hosts_model(
    tmp_path, environment, status
) -> None:
    world = _world(tmp_path)
    _compose(world, environment)
    assert pr.sovereign_compose_local_model(world).status == status


def test_the_production_container_must_receive_its_keys(tmp_path) -> None:
    world = _world(tmp_path)
    _compose(
        world, ["AIOS_VERIFICATION_AUTHORITY_KEY=${AIOS_VERIFICATION_AUTHORITY_KEY:-}"]
    )
    gate = pr.sovereign_compose_keys(world)
    assert gate.status == pr.FAIL and "AIOS_LEARNING_KEY_LIVE" in gate.evidence
    _compose(
        world,
        [
            "AIOS_VERIFICATION_AUTHORITY_KEY=${AIOS_VERIFICATION_AUTHORITY_KEY:-}",
            "AIOS_LEARNING_KEY_LIVE=${AIOS_LEARNING_KEY_LIVE:-}",
        ],
    )
    assert pr.sovereign_compose_keys(world).status == pr.PASS


# --------------------------------------------------------------------------- #
# Clerk
# --------------------------------------------------------------------------- #


def _registry(world: pr.World, **row: Any) -> Path:
    from aios.memory.db import init_memory_db

    db = world.data_dir / "aios_memory.db"
    init_memory_db(db)
    values = {
        "model_id": "qwen2.5:3b",
        "provider": "ollama",
        "family": "qwen2",
        "parameter_size": "3B",
        "quantization": "Q4_K_M",
        "installed": 1,
        "operator_approved": 1,
        "health": "healthy",
        "admission_status": "approved",
        "max_context": 8192,
        "max_output": 2048,
        "max_parallelism": 1,
        "allowed_job_profiles_json": json.dumps(["select_skill"]),
        "metadata_confidence": "verified",
    }
    values.update(row)
    with sqlite3.connect(db) as conn:
        conn.execute(
            f"INSERT INTO local_worker_models ({', '.join(values)}) "  # noqa: S608 - test fixture
            f"VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )
    return db


def test_an_admitted_clerk_model_passes(tmp_path) -> None:
    world = _world(tmp_path)
    _registry(world)
    gate = pr.clerk_admitted_model(world)
    assert gate.status == pr.PASS and "qwen2.5:3b" in gate.evidence


@pytest.mark.parametrize(
    "row",
    [
        {"admission_status": "rejected"},
        {"operator_approved": 0},
        {"health": "degraded"},
        {"installed": 0},
        {"allowed_job_profiles_json": "[]"},
    ],
)
def test_the_dispatchers_own_rule_decides_admission(tmp_path, row) -> None:
    world = _world(tmp_path)
    _registry(world, **row)
    assert pr.clerk_admitted_model(world).status == pr.FAIL


def test_the_clerk_registry_is_read_never_written(tmp_path) -> None:
    world = _world(tmp_path)
    db = _registry(world)
    before = db.read_bytes()
    pr.clerk_admitted_model(world)
    assert db.read_bytes() == before
    with pytest.raises(sqlite3.OperationalError):
        with pr._ro(db) as conn:
            conn.execute("DELETE FROM local_worker_models")


def test_clerk_jobs_are_counted_from_its_own_store(tmp_path) -> None:
    world = _world(tmp_path)
    assert pr.clerk_real_jobs(world).status == pr.FAIL
    from aios.infrastructure.local_workforce.sqlite_store import (
        LocalWorkforceProvenanceStore,
    )

    store = world.data_dir / "aios_local_workforce_provenance.db"
    LocalWorkforceProvenanceStore(store)
    assert pr.clerk_real_jobs(world).status == pr.FAIL, "an empty store is no job"
    with sqlite3.connect(store) as conn:
        conn.execute(
            "INSERT INTO local_job_requests (job_id, job_profile, input_schema_version, "
            "qualification_suite_version, model_allowlist_json, requested_model, "
            "evidence_references_json, redacted_input_digest, token_budget, deadline, "
            "created_at, record_digest) VALUES "
            "('j1', 'select_skill', '1.0', 'r15-v2', '[]', 'm', '[]', 'd', 1, 't', 't', 'r')"
        )
    gate = pr.clerk_real_jobs(world)
    assert gate.status == pr.PASS and "1 recorded" in gate.evidence


# --------------------------------------------------------------------------- #
# Animal
# --------------------------------------------------------------------------- #


def test_the_signing_key_is_reported_by_presence_never_value(tmp_path) -> None:
    world = _world(tmp_path, env={"AIOS_LEARNING_KEY_LIVE": "deadbeef" * 8})
    pins = world.repo / ".aios" / "state" / "LEARNING_PUBLIC_KEYS.json"
    assert pr.animal_signing_key(world).status == pr.FAIL, "no pinned key"
    pins.write_text(json.dumps({"keys": {"live": ["ab" * 32]}}), encoding="utf-8")
    gate = pr.animal_signing_key(world)
    assert gate.status == pr.PASS
    assert "deadbeef" not in json.dumps(gate.__dict__)
    assert pr.animal_signing_key(_world(tmp_path)).status == pr.FAIL


def test_the_guards_must_run_on_a_schedule(tmp_path) -> None:
    world = _world(tmp_path)
    flow = world.repo / ".github" / "workflows" / "learning-guards.yml"
    flow.write_text("on:\n  workflow_dispatch: {}\njobs: {}\n", encoding="utf-8")
    assert pr.animal_guards_scheduled(world).status == pr.FAIL
    flow.write_text(
        "on:\n  workflow_dispatch: {}\n  schedule:\n    - cron: '0 3 * * *'\njobs: {}\n",
        encoding="utf-8",
    )
    assert pr.animal_guards_scheduled(world).status == pr.PASS


# --------------------------------------------------------------------------- #
# Intelligence
# --------------------------------------------------------------------------- #


def test_the_local_model_must_be_served(tmp_path) -> None:
    tags = {"models": [{"name": "qwen2.5:3b"}]}
    env = {"AIOS_LLM_MODEL": "qwen2.5:3b", "OLLAMA_HOST": "http://h:1"}
    world = _world(tmp_path, env=env, http_json=lambda u: tags)
    assert pr.intelligence_local_model(world).status == pr.PASS
    other = _world(
        tmp_path, env={**env, "AIOS_LLM_MODEL": "llama3:8b"}, http_json=lambda u: tags
    )
    assert pr.intelligence_local_model(other).status == pr.FAIL
    down = _world(tmp_path, env=env, http_json=lambda u: None)
    assert pr.intelligence_local_model(down).status == pr.FAIL


def test_a_cloud_provider_is_reported_by_name_only(tmp_path) -> None:
    assert pr.intelligence_cloud_provider(_world(tmp_path)).status == pr.FAIL
    world = _world(tmp_path, env={"AWS_BEARER_TOKEN_BEDROCK": "secret-value"})
    gate = pr.intelligence_cloud_provider(world)
    assert gate.status == pr.PASS and "secret-value" not in gate.evidence


def _caller(world: pr.World, rel: str, role: str) -> None:
    path = world.repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"def ask():\n    return make(job_profile=LocalJobProfile.{role})\n",
        encoding="utf-8",
    )


def test_a_live_role_no_test_covers_can_never_be_earned(tmp_path) -> None:
    world = _world(tmp_path)
    assert pr.clerk_live_roles_earnable(world).status == pr.FAIL, "no caller at all"
    _caller(world, "aios/application/x/service.py", "SUMMARISE")
    assert pr.clerk_live_roles_earnable(world).status == pr.PASS
    _caller(world, "aios/application/y/service.py", "SELECT_SKILL")
    gate = pr.clerk_live_roles_earnable(world)
    assert gate.status == pr.FAIL and "select_skill" in gate.evidence
    assert "aios/application/y/service.py" in gate.evidence


def test_runtime_proofs_are_fixtures_not_callers(tmp_path) -> None:
    world = _world(tmp_path)
    _caller(world, "aios/application/x/service.py", "SUMMARISE")
    _caller(world, "aios/application/governance/r15_runtime_proof.py", "SELECT_SKILL")
    assert pr.clerk_live_roles_earnable(world).status == pr.PASS
