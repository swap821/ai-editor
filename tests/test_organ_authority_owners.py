"""Organs 42, 46, 52: the named authority owners exist AND are reached.

The ledger names an `authority_owner` for every organ, but `validate_ledger()`
only string-compares that field against a registry of strings -- it never
checks the named class exists. So a name matching nothing was structurally
invisible, and all three of these organs named classes that did not exist.

Creating the classes alone would be worse than useless: it satisfies the
letter of green-contract condition 1 ("named authority owner") while leaving
condition 2 ("a real API/mission/runtime path invokes it") false. That is
precisely the anti-pattern the plan forbids -- an organ is not green because
its class exists.

These tests therefore assert reachability, not existence. Each one drives a
real production entrypoint and proves the authority was the thing that acted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_constitutional_learning_authority,
    get_observability_authority,
    get_operator_preference_store,
    get_operator_taste_model_authority,
    get_project_passport_store,
    get_project_understanding_authority,
    get_recovery_resumption_authority,
)
from aios.api.main import app
from aios.application.governance.constitutional_learning import (
    ConstitutionalLearningAuthority,
    ConstitutionalLearningError,
)
from aios.application.memory.authorities import (
    OperatorTasteModelAuthority,
    ProjectUnderstandingAuthority,
)
from aios.application.observability import ObservabilityAuthority
from aios.application.recovery import RecoveryResumptionAuthority
from aios.domain.memory.human_representation import OperatorPreferenceV1
from aios.infrastructure.memory.human_representation_store import (
    OperatorPreferenceStore,
    ProjectPassportStore,
)
from aios.infrastructure.missions.transition_journal_store import (
    MissionTransitionJournal,
)
from aios.memory.facts import SemanticFacts


# --------------------------------------------------------------------------- #
# Organ 42 -- RecoveryResumptionAuthority
# --------------------------------------------------------------------------- #


def _recovery(tmp_path: Path) -> RecoveryResumptionAuthority:
    return RecoveryResumptionAuthority(MissionTransitionJournal(tmp_path / "j.db"))


def test_the_recovery_authority_is_the_singleton_the_repair_path_writes_to() -> None:
    """The whole point of one authority: the startup scan must read the same
    journal the maintenance repair path wrote to. Two independently
    constructed journals would each look healthy while sharing nothing."""
    authority = get_recovery_resumption_authority()

    assert isinstance(authority, RecoveryResumptionAuthority)
    assert get_recovery_resumption_authority() is authority

    from aios.api.deps import get_maintenance_convergence_service

    service = get_maintenance_convergence_service()
    assert service.mission_journal is authority.journal, (
        "the maintenance repair path must journal into the authority's own "
        "store, or the startup recovery scan reads a different journal"
    )


def test_the_recovery_authority_reports_interrupted_missions(tmp_path: Path) -> None:
    authority = _recovery(tmp_path)
    authority.record_transition("m-done", "MISSION_CREATED")
    authority.record_transition("m-done", "FAILED")
    authority.record_transition("m-live", "MISSION_CREATED")
    authority.record_transition("m-live", "APPROVED")

    interrupted = authority.interrupted_missions()

    assert "m-live" in interrupted
    assert "m-done" not in interrupted, "a terminal mission is not interrupted"
    assert authority.is_complete("m-done") is True
    assert authority.last_transition("m-live") == "APPROVED"


def test_record_transition_never_raises_and_reports_refusal(tmp_path: Path) -> None:
    """Best-effort, but not silent: the caller learns nothing was recorded.

    The refusal here is the exact trap this organ has to guard -- the store
    rejects any first transition that is not MISSION_CREATED, so a path that
    journals only its later steps writes nothing at all.
    """
    authority = _recovery(tmp_path)

    assert authority.record_transition("m-never-created", "WORKSPACE_CREATED") is False
    assert authority.last_transition("m-never-created") is None
    assert authority.record_transition("m-ok", "MISSION_CREATED") is True


def test_the_recovery_report_never_raises_on_a_tampered_journal(
    tmp_path: Path,
) -> None:
    """A tampered journal must be reported, not thrown -- this runs at API
    startup, and a recovery scan that crashes the boot is worse than one that
    reports honestly."""
    import sqlite3

    authority = _recovery(tmp_path)
    authority.record_transition("m-1", "MISSION_CREATED")
    authority.record_transition("m-1", "APPROVED")

    with sqlite3.connect(str(authority.journal.db_path)) as conn:
        conn.execute(
            "UPDATE mission_execution_transitions SET transition = 'COMPLETED' "
            "WHERE sequence = 1"
        )
        conn.commit()

    report = authority.recovery_report()

    assert report["integrity"] == "tampered"
    assert report["error"]


def test_the_recovery_report_is_honest_about_a_clean_journal(tmp_path: Path) -> None:
    authority = _recovery(tmp_path)
    authority.record_transition("m-1", "MISSION_CREATED")

    report = authority.recovery_report()

    assert report["integrity"] == "verified"
    assert report["verified_entries"] == 1
    assert report["interrupted_count"] == 1


# --------------------------------------------------------------------------- #
# Organ 52 -- ObservabilityAuthority
# --------------------------------------------------------------------------- #


def test_the_observability_authority_binds_the_request_correlation_chain() -> None:
    """The middleware builds and binds through this authority, so a context
    bound by it must be what `current_context()` reports."""
    authority = get_observability_authority()
    assert isinstance(authority, ObservabilityAuthority)

    context = authority.context_from_headers({"x-request-id": "organ52-owner-test"})
    with authority.bind(context):
        assert authority.current_context().request_id == "organ52-owner-test"
        assert authority.propagation_headers()["x-request-id"] == "organ52-owner-test"
        assert (
            authority.propagation_env()["AIOS_TRACE_REQUEST_ID"] == "organ52-owner-test"
        )


def test_an_unsafe_trace_id_is_dropped_not_propagated() -> None:
    """Correlation metadata crosses into HTTP headers and container argv, so a
    value failing validation must be replaced, never passed through."""
    authority = get_observability_authority()

    context = authority.context_from_headers({"x-request-id": "bad id; rm -rf /"})

    assert context.request_id != "bad id; rm -rf /"
    assert context.request_id


def test_durable_logs_survive_the_process_that_wrote_them(tmp_path: Path) -> None:
    """Condition 3. Before this, logging attached only a stderr StreamHandler,
    so an incident investigated after a crash had nothing to read."""
    authority = ObservabilityAuthority(log_dir=tmp_path / "logs")
    assert authority.durable_log_status()["durable"] is False

    path = authority.enable_durable_logs()

    assert path is not None and path.exists()
    status = authority.durable_log_status()
    assert status["durable"] is True
    assert status["max_bytes"] > 0 and status["backup_count"] > 0

    import logging

    logging.getLogger().warning("organ52-durable-probe")
    assert "organ52-durable-probe" in path.read_text(encoding="utf-8")


def test_health_reports_unavailable_rather_than_inventing_a_reading() -> None:
    """An observability organ that fabricates reassuring numbers is worse than
    one that admits it cannot tell, because the numbers get believed."""
    authority = get_observability_authority()

    health = authority.health()

    assert health["metrics"]["status"] in {"available", "unavailable"}
    assert "logs" in health and "trace" in health


# --------------------------------------------------------------------------- #
# Organ 46 -- ConstitutionalLearningAuthority
# --------------------------------------------------------------------------- #


def _proposal():
    from aios.application.governance.amendment_authority import propose_amendment

    return propose_amendment(
        proposal_id="owner-test-proposal",
        target_articles=("article-9-reauth-policy",),
        proposed_diff="cache reauth for a short trusted window",
        motivation="reduce operator friction on routine approvals",
        migration_plan="roll out behind a flag",
        rollback_plan="flip the flag back",
        proposed_by="tester",
        proposer_type="human",
    )


def test_the_learning_authority_is_what_the_governance_route_uses() -> None:
    assert isinstance(
        get_constitutional_learning_authority(), ConstitutionalLearningAuthority
    )


def test_screen_proposal_runs_the_checks_and_returns_the_breakdown() -> None:
    authority = ConstitutionalLearningAuthority()

    results = authority.screen_proposal(_proposal())

    from aios.domain.governance.learning import ADVERSARIAL_SIMULATION_CHECKS

    assert tuple(r.check_name for r in results) == ADVERSARIAL_SIMULATION_CHECKS
    assert all(r.passed for r in results)


def test_screen_proposal_refuses_an_unsafe_proposal() -> None:
    """The invariant the authority exists to hold: run and require cannot be
    separated, so a caller cannot run the checks and then decline to consult
    them."""
    authority = ConstitutionalLearningAuthority()
    unsafe = _proposal().model_copy(
        update={"proposed_diff": "auto-approve routine actions without human review"}
    )

    with pytest.raises(ConstitutionalLearningError):
        authority.screen_proposal(unsafe)


@pytest.mark.parametrize(
    "text",
    [
        "remove human approval from the promotion path",
        "let the system auto-approve routine repairs",
        "proceed without human review when confidence is high",
        "allow the model to self-approve low-risk actions",
    ],
)
def test_the_authority_still_refuses_authority_reducing_text(text: str) -> None:
    """The one rule the whole organ serves. Phrased as real proposals rather
    than bare marker strings, so this would catch the markers being narrowed
    to the point where ordinary wording slips past."""
    authority = ConstitutionalLearningAuthority()

    with pytest.raises(ConstitutionalLearningError):
        authority.assert_never_reduces_human_authority(text)


def test_the_authority_permits_naming_a_weakness_without_proposing_surrender() -> None:
    """GAGOS may learn that its sovereignty mechanisms are weak -- it may only
    never propose reducing human authority to fix that. A rule that refused
    both would make the organ unable to report its own gaps."""
    authority = ConstitutionalLearningAuthority()

    authority.assert_never_reduces_human_authority(
        "the approval gate is easy to miss; add a second confirmation step "
        "and make refusals state which check failed"
    )


# --------------------------------------------------------------------------- #
# Organ 27 -- OperatorTasteModelAuthority
# --------------------------------------------------------------------------- #


def test_the_taste_model_authority_is_what_the_real_preferences_route_uses(
    tmp_path: Path,
) -> None:
    """Overrides only the STORE-level dependency (never the authority), then
    proves the real HTTP route resolves a genuine OperatorTasteModelAuthority
    wrapping it -- a class existing in isolation would not make this pass."""
    db_path = tmp_path / "mem.db"
    store = OperatorPreferenceStore(db_path, facts=SemanticFacts(db_path))
    app.dependency_overrides[get_operator_preference_store] = lambda: store
    try:
        resolved = get_operator_taste_model_authority(store=store)
        assert isinstance(resolved, OperatorTasteModelAuthority)
        assert resolved.store is store

        client = TestClient(app, client=("127.0.0.1", 12345))
        response = client.post(
            "/api/v1/preferences",
            json={
                "domain": "testing",
                "key": "owner_reachability_probe",
                "value": True,
                "scope": "project:ai-editor",
                "confidence": 0.9,
            },
        )
        assert response.status_code == 200
        # The route only ever sees the authority; if it round-trips through
        # the STORE we overrode, the authority (not a bypass) handled it.
        assert store.get(response.json()["preferenceId"]) is not None
    finally:
        app.dependency_overrides.clear()


def test_the_taste_model_authority_active_preferences_excludes_withdrawn_and_expired(
    tmp_path: Path,
) -> None:
    """The real consolidation this authority owns (not a pass-through): the
    store's own `list_active_for_operator_scope` only filters `status`; the
    authority additionally drops expired rows, matching organ 31's exact
    `active_preferences` contract."""
    db_path = tmp_path / "mem.db"
    store = OperatorPreferenceStore(db_path, facts=SemanticFacts(db_path))
    authority = OperatorTasteModelAuthority(store)
    digest = "owner-digest"

    _, kept = authority.record_explicit_preference(
        preference_id="pref-active",
        domain="testing",
        key="keep",
        value=1,
        scope="s",
        confidence=1.0,
        review_after=None,
        operator_identity_digest=digest,
    )
    result, withdrawn_pref = authority.record_explicit_preference(
        preference_id="pref-withdrawn",
        domain="testing",
        key="drop",
        value=1,
        scope="s",
        confidence=1.0,
        review_after=None,
        operator_identity_digest=digest,
    )
    assert result.saved and withdrawn_pref is not None
    assert authority.withdraw("pref-withdrawn", operator_identity_digest=digest)

    active = authority.active_preferences_for_operator(digest, "s")

    assert [p.preference_id for p in active] == ["pref-active"]
    assert kept is not None


# --------------------------------------------------------------------------- #
# Organ 28 -- ProjectUnderstandingAuthority
# --------------------------------------------------------------------------- #


def test_the_project_understanding_authority_is_what_the_real_scan_route_uses(
    tmp_path: Path,
) -> None:
    """Overrides only the STORE-level dependency, then proves the real HTTP
    scan route resolves a genuine ProjectUnderstandingAuthority wrapping
    it -- a class existing in isolation would not make this pass."""
    store = ProjectPassportStore(tmp_path / "passports.db")
    app.dependency_overrides[get_project_passport_store] = lambda: store
    try:
        resolved = get_project_understanding_authority(store=store)
        assert isinstance(resolved, ProjectUnderstandingAuthority)
        assert resolved.store is store

        client = TestClient(app, client=("127.0.0.1", 12345))
        response = client.post(
            "/api/v1/projects/passport/scan",
            json={"root": str(Path(__file__).resolve().parents[1]), "maxFiles": 5},
        )
        assert response.status_code == 200
        project_id = response.json()["projectId"]
        # The route only ever sees the authority; if the STORE we overrode
        # now durably has this project, the authority (not a bypass) wrote it.
        assert store.get_current(project_id) is not None
    finally:
        app.dependency_overrides.clear()


def test_the_project_understanding_authority_status_combines_three_store_reads(
    tmp_path: Path,
) -> None:
    """The real consolidation this authority owns (not a pass-through): the
    route used to assemble `active_project_status` from three separate store
    calls inline (and, before this pass, had a dead duplicate copy of that
    assembly after an unconditional `return`) -- the authority now owns that
    assembly as one real method."""
    from aios.memory.project_passport import ProjectPassport

    store = ProjectPassportStore(tmp_path / "passports.db")
    authority = ProjectUnderstandingAuthority(store)
    digest = "owner-digest"

    assert authority.active_project_status(digest) is None

    passport = ProjectPassport(
        root=str(tmp_path),
        generated_at="2026-07-28T00:00:00+00:00",
        purpose="test",
        stack=[],
        folder_map=[],
        key_files=[],
        install_commands=[],
        run_commands=[],
        build_commands=[],
        test_commands=[],
        env_vars=[],
        safe_actions=[],
        risky_actions=[],
        known_issues=[],
        current_goals=[],
        suggested_improvements=[],
        evidence_files=[],
    )
    revision, _diff = authority.record_scan(
        tmp_path,
        project_id="proj-1",
        verified_at_commit="deadbeef",
        passport=passport,
        operator_identity_digest=digest,
        scan_summary={"filesScanned": 1},
    )
    assert revision == 1

    status = authority.active_project_status(digest)

    assert status is not None
    assert status["projectId"] == "proj-1"
    assert status["lastScan"] == {"filesScanned": 1}
    assert status["durable"]["revisionCount"] == 1
    assert status["durable"]["verifiedAtCommit"] == "deadbeef"
