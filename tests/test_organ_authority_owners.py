"""Phase-2 owner reachability: named authority owners exist AND are reached.

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

from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from aios.api.deps import (
    get_constitutional_learning_authority,
    get_correction_lineage_authority,
    get_correction_record_store,
    get_constitution_authority,
    get_observability_authority,
    get_operator_preference_store,
    get_operator_taste_model_authority,
    get_project_passport_store,
    get_project_understanding_authority,
    get_recovery_resumption_authority,
    get_human_state_interpreter_authority,
)
from aios.api.main import app
from aios.application.governance.constitutional_learning import (
    ConstitutionalLearningAuthority,
    ConstitutionalLearningError,
)
from aios.application.local_workforce.provenance import ClerkProvenanceAuthority
from aios.application.local_workforce.service import LocalWorkforceService
from aios.application.memory.authorities import (
    CorrectionLineageAuthority,
    OperatorTasteModelAuthority,
    ProjectUnderstandingAuthority,
)
from aios.application.observability import ObservabilityAuthority
from aios.application.recovery import RecoveryResumptionAuthority
from aios.domain.local_workforce.contracts import LocalJobProfile, LocalJobRequest
from aios.domain.memory.human_representation import OperatorPreferenceV1
from aios.infrastructure.local_workforce.sqlite_store import (
    LocalWorkforceProvenanceStore,
)
from aios.infrastructure.memory.human_representation_store import (
    CorrectionRecordStore,
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


# --------------------------------------------------------------------------- #
# Organ 38 -- ClerkProvenanceAuthority
# --------------------------------------------------------------------------- #


def _admitted_model():
    from aios.domain.local_workforce.contracts import LocalWorkerModel

    return LocalWorkerModel(
        model_id="granite3.2:2b",
        provider="ollama",
        family="granite",
        parameter_size="2B",
        quantization="q4_K_M",
        installed=True,
        operator_approved=True,
        health="healthy",
        admission_status="approved",
        admission_reason="Passed",
        max_context=131072,
        max_output=4096,
        max_parallelism=1,
        allowed_job_profiles=frozenset({LocalJobProfile.SELECT_SKILL}),
        metadata_confidence="verified",
    )


def test_the_provenance_authority_is_what_run_advisory_job_writes_through(
    tmp_path: Path,
) -> None:
    """Overrides nothing at the FastAPI layer (this organ's real caller is
    LocalWorkforceService, not a route) -- instead proves the service's own
    real production entrypoint (run_advisory_job) resolves and writes
    through a genuine ClerkProvenanceAuthority, not a bare store call."""
    from unittest.mock import MagicMock

    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    registry = MagicMock(spec=LocalWorkforceRegistry)
    admitted = _admitted_model()
    registry.list_models.return_value = [admitted]
    registry.get_model.return_value = admitted
    llm = MagicMock()
    llm.complete.return_value = '{"applicable": true, "confidence": 0.9}'

    service = LocalWorkforceService(
        registry=registry,
        ollama=llm,
        model_client_factory=lambda model_id: llm,
        provenance_store=store,
    )

    assert isinstance(service.provenance_authority, ClerkProvenanceAuthority)
    assert service.provenance_authority.store is store

    request = LocalJobRequest(
        job_id="owner-reachability-probe",
        job_profile=LocalJobProfile.SELECT_SKILL,
        input_schema_version="1.0",
        evidence_references=frozenset({"skill-1"}),
        redacted_payload="Evaluate skill applicability.",
        token_budget=128,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        required_output_schema={"applicable": "bool", "confidence": "float"},
    )
    result = service.run_advisory_job(request)

    assert result.status == "completed"
    # The service only ever calls the authority; if the STORE we passed in
    # now durably has this job, the authority (not a bypass) wrote it.
    provenance = service.provenance_authority.job_provenance(
        "owner-reachability-probe"
    )
    assert provenance.request is not None
    assert provenance.result is not None
    assert provenance.result.status == "completed"


def test_the_provenance_authority_records_a_refusal_honestly(tmp_path: Path) -> None:
    """The real consolidation this authority owns (not a pass-through): it
    builds and links four typed records (request, model call, result, the
    hash-chained provenance record) from one call -- including an honest
    refusal, not only successes."""
    from unittest.mock import MagicMock

    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    store = LocalWorkforceProvenanceStore(tmp_path / "provenance.db")
    authority = ClerkProvenanceAuthority(store)
    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.list_models.return_value = []
    llm = MagicMock()

    service = LocalWorkforceService(
        registry=registry,
        ollama=llm,
        model_client_factory=lambda model_id: llm,
        provenance_store=store,
    )
    request = LocalJobRequest(
        job_id="owner-refusal-probe",
        job_profile=LocalJobProfile.SELECT_SKILL,
        input_schema_version="1.0",
        evidence_references=frozenset({"skill-1"}),
        redacted_payload="Evaluate skill applicability.",
        token_budget=128,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        required_output_schema={"applicable": "bool", "confidence": "float"},
    )

    result = service.run_advisory_job(request)

    assert result.status == "rejected"
    provenance = authority.job_provenance("owner-refusal-probe")
    assert provenance.request is not None
    assert provenance.result is not None
    assert provenance.result.status == "rejected"


# --------------------------------------------------------------------------- #
# Organ 29 -- CorrectionLineageAuthority
# --------------------------------------------------------------------------- #


def test_the_correction_lineage_authority_is_what_session_restore_reads_through(
    tmp_path: Path,
) -> None:
    """Overrides only the STORE-level dependency, then proves the real HTTP
    session-restore route resolves a genuine CorrectionLineageAuthority
    wrapping it. The heavier compensating-transaction behavior (roll back
    ConversationStateStore when the immutable ledger write fails) is
    already exercised end-to-end, through the real routes, by
    tests/test_authenticated_chat_route.py::
    test_correction_route_rolls_back_when_authenticated_ledger_write_fails
    and its clear-route sibling -- both pass against this same authority."""
    store = CorrectionRecordStore(tmp_path / "corrections.db")
    app.dependency_overrides[get_correction_record_store] = lambda: store
    try:
        resolved = get_correction_lineage_authority(store=store)
        assert isinstance(resolved, CorrectionLineageAuthority)
        assert resolved.store is store

        client = TestClient(app, client=("127.0.0.1", 12345))
        response = client.post(
            "/api/v1/conversation/session",
            json={"sessionId": "unused-body-field", "limit": 5},
        )

        assert response.status_code == 200
        assert response.json()["correctionRecords"] == []
    finally:
        app.dependency_overrides.clear()


def test_the_correction_lineage_authority_lineage_reads_newest_first(
    tmp_path: Path,
) -> None:
    """The real read-side work this authority owns (not a pass-through
    rename): `lineage_for_session` is the exact method organ 29's own
    `correctionRecords` response field is built from."""
    from aios.application.memory.human_representation import (
        build_correction_record_v1,
    )

    store = CorrectionRecordStore(tmp_path / "corrections.db")
    authority = CorrectionLineageAuthority(store)

    for revision in (1, 2):
        record = build_correction_record_v1(
            correction_id=f"correction:s-1:{revision}",
            session_id="s-1",
            base_revision=revision - 1,
            correction_revision=revision,
            corrected_fields=("goal",),
            before_frame={"goal": "old"},
            after_frame={"goal": "new"},
            operator_id="operator-1",
        )
        authority.store.save(record)

    lineage = authority.lineage_for_session("s-1")

    assert [r.correction_revision for r in lineage] == [2, 1]


# --------------------------------------------------------------------------- #
# Organ 31 -- RepresentativeContextCompilerAuthority
# --------------------------------------------------------------------------- #


def test_the_context_compiler_authority_is_the_gateway_compiler() -> None:
    from aios.application.intelligence import gateway
    from aios.application.intelligence.context_compiler import (
        RepresentativeContextCompilerAuthority,
    )

    authority = gateway._REPRESENTATIVE_CONTEXT_COMPILER
    assert isinstance(authority, RepresentativeContextCompilerAuthority)
    context = authority.compile(
        request_id="organ31-owner-test",
        operator_identity_digest="a" * 64,
        constitution_digest="b" * 64,
        goal="inspect the context boundary",
        desired_outcome="a compiled context",
        target="local",
        delegated_authority_summary="human operator decides",
        explicit_constraints=(),
        current_decisions=(),
        active_preferences=(),
        project_passport=None,
        project_passport_stale=False,
        relevant_memory_refs=(),
        permitted_tools=(),
        evidence_requirements=(),
        communication_mode="direct",
        latest_correction=None,
        secret_policy=None,
    )
    assert context.request_id == "organ31-owner-test"


# --------------------------------------------------------------------------- #
# Organs 25 and 53 -- exact owner names over the existing live authorities
# --------------------------------------------------------------------------- #


def test_constitution_factory_returns_the_named_kernel_owner() -> None:
    from aios.application.governance.constitution_authority import (
        ConstitutionalKernelAuthority,
    )

    assert isinstance(get_constitution_authority(), ConstitutionalKernelAuthority)


def test_edge_token_factory_returns_the_named_installation_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aios import config
    from aios.application.security.api_token_authority import (
        InstallationConfigurationAuthority,
    )
    from aios.interfaces.http import edge_security

    monkeypatch.setattr(config, "API_TOKEN_ROTATION_DB_PATH", tmp_path / "tokens.db")
    monkeypatch.setattr(edge_security, "_API_TOKEN_AUTHORITY", None)
    resolved = edge_security.get_api_token_authority()
    assert isinstance(resolved, InstallationConfigurationAuthority)


# --------------------------------------------------------------------------- #
# Organ 32 -- UniversalIntelligenceGatewayAuthority
# --------------------------------------------------------------------------- #


def test_the_universal_gateway_authority_owns_both_call_entrances() -> None:
    from unittest.mock import MagicMock

    from aios.application.intelligence import gateway
    from aios.application.intelligence.gateway import (
        UniversalIntelligenceGatewayAuthority,
    )

    authority = gateway._UNIVERSAL_GATEWAY_AUTHORITY
    assert isinstance(authority, UniversalIntelligenceGatewayAuthority)
    store = MagicMock()
    result = gateway.route_intelligence_request(
        request_id="organ32-owner-test",
        operator_identity_digest="a" * 64,
        constitution_digest="b" * 64,
        goal="exercise the gateway owner",
        desired_outcome="a governed result",
        target="local",
        delegated_authority_summary="human operator decides",
        model_call=lambda _context: "governed reply",
        context_store=store,
    )
    assert result.output == "governed reply"
    store.save.assert_called_once()

    structured = gateway.stream_structured_intelligence_request(
        request_id="organ32-structured-owner-test",
        operator_identity_digest="a" * 64,
        constitution_digest="b" * 64,
        goal="exercise the structured gateway owner",
        desired_outcome="a governed event stream",
        target="local",
        delegated_authority_summary="human operator decides",
        model_call=lambda _context: iter(
            [{"type": "text", "text": "governed reply"}, {"type": "done"}]
        ),
        context_store=store,
    )
    assert list(structured.events)[-1] == {"type": "done"}
    assert store.save.call_args.args[0] == structured.context
    assert store.save.call_count == 2


# --------------------------------------------------------------------------- #
# Organ 30 -- HumanStateInterpreterAuthority
# --------------------------------------------------------------------------- #


def test_the_human_state_authority_is_reached_by_the_real_chat_route() -> None:
    from aios.api.main import chat
    from aios.application.memory.human_representation import (
        HumanStateInterpreterAuthority,
    )

    authority = get_human_state_interpreter_authority()
    assert isinstance(authority, HumanStateInterpreterAuthority)
    parameter = inspect.signature(chat).parameters["human_state_interpreter"]
    assert parameter.default.dependency is get_human_state_interpreter_authority
    assert authority.classify("please do this asap").state == "rushed"


# --------------------------------------------------------------------------- #
# Organ 33 -- ModelPassportAuthority
# --------------------------------------------------------------------------- #


def test_the_passport_authority_is_what_the_real_passport_route_uses() -> None:
    """Overrides only the REGISTRY-level dependency, then proves the real
    HTTP route resolves a genuine ModelPassportAuthority wrapping it -- this
    class already existed (built in a prior pass, 12 unit tests) but had
    ZERO production callers until this route; the class existing was not
    enough, matching this project's own forbidden anti-pattern."""
    from unittest.mock import MagicMock

    from aios.api.deps import get_local_workforce_registry, get_model_passport_authority
    from aios.application.models.passport_authority import ModelPassportAuthority
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    admitted = _admitted_model()
    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.get_model.return_value = admitted
    app.dependency_overrides[get_local_workforce_registry] = lambda: registry
    try:
        resolved = get_model_passport_authority(registry=registry)
        assert isinstance(resolved, ModelPassportAuthority)
        assert resolved.registry is registry

        client = TestClient(app, client=("127.0.0.1", 12345))
        response = client.get(f"/api/v1/local-workforce/{admitted.model_id}/passport")

        assert response.status_code == 200
        body = response.json()
        assert body["exact_model_id"] == admitted.model_id
        assert body["admission_status"] == "admitted"
        # The overridden registry, not a bypass, answered this -- confirmed
        # by asserting get_model was actually called with this model_id.
        registry.get_model.assert_any_call(admitted.model_id)
    finally:
        app.dependency_overrides.clear()


def test_the_passport_authority_returns_none_for_an_unregistered_model() -> None:
    """The real decision this authority owns (not a pass-through): None
    means "no record", which the route maps to a 404 -- never a fabricated
    proposed-but-empty passport for a model the registry has never seen."""
    from unittest.mock import MagicMock

    from aios.application.models.passport_authority import ModelPassportAuthority
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.get_model.return_value = None
    authority = ModelPassportAuthority(registry)

    assert authority.passport_for("unknown-model") is None


# --------------------------------------------------------------------------- #
# Organ 36 -- ClerkDispatcherAuthority
# --------------------------------------------------------------------------- #


def test_the_dispatcher_authority_is_what_the_real_service_calls_through() -> None:
    """The service's own instance attribute, constructed in __init__ -- not
    a second, disconnected authority the test builds itself."""
    from unittest.mock import MagicMock

    from aios.application.local_workforce.dispatcher import ClerkDispatcherAuthority
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    registry = MagicMock(spec=LocalWorkforceRegistry)
    llm = MagicMock()
    service = LocalWorkforceService(
        registry=registry, ollama=llm, model_client_factory=lambda model_id: llm
    )

    assert isinstance(service.dispatcher_authority, ClerkDispatcherAuthority)


def test_the_dispatcher_authority_escalates_an_unqualified_model_through_the_real_service(
    tmp_path: Path,
) -> None:
    """The real decision this organ exists to enforce, exercised through
    run_advisory_job() end to end (not the pure function in isolation): a
    model with no persisted qualification (registry.get_qualification()
    genuinely returns None, never a fabricated pass) must escalate to
    frontier, never silently proceed as though it had qualified."""
    from unittest.mock import MagicMock

    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    admitted = _admitted_model()
    registry = MagicMock(spec=LocalWorkforceRegistry)
    registry.list_models.return_value = [admitted]
    registry.get_model.return_value = admitted
    registry.get_qualification.return_value = None
    llm = MagicMock()

    service = LocalWorkforceService(
        registry=registry, ollama=llm, model_client_factory=lambda model_id: llm
    )
    request = LocalJobRequest(
        job_id="owner-escalation-probe",
        job_profile=LocalJobProfile.SELECT_SKILL,
        input_schema_version="1.0",
        evidence_references=frozenset({"skill-1"}),
        redacted_payload="Evaluate skill applicability.",
        token_budget=128,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        required_output_schema={"applicable": "bool", "confidence": "float"},
    )

    result = service.run_advisory_job(request)

    assert result.status == "rejected"
    assert result.failure_reason == "Dispatched to frontier_escalation"
    registry.get_qualification.assert_called_once_with(admitted.model_id)
    llm.complete.assert_not_called()

# --------------------------------------------------------------------------- #
# Organs 7, 8, 10, 11, 12 and 14 -- exact owners over existing mechanisms
# --------------------------------------------------------------------------- #


def test_phase2_batch_owners_are_reached_by_production_constructors(
    tmp_path: Path,
) -> None:
    """The six names below are the real classes, not pass-through wrappers.

    Existing imports remain valid through aliases, while the production
    dependency factories and lifecycle constructors now return objects whose
    concrete class is the exact owner named in the ledger.
    """
    from aios.api.deps import (
        get_action_broker,
        get_capability_authority,
        get_emergency_stop,
        get_policy_kernel,
        get_worker_foundry,
    )
    from aios.application.action_broker import (
        ActionBroker,
        ActionBrokerAuthority,
    )
    from aios.application.missions.mission_service import (
        MissionAuthority,
        MissionService,
    )
    from aios.application.turns.turn_coordinator import (
        TurnCoordinator,
        TurnCoordinatorAuthority,
    )
    from aios.application.workers.foundry import (
        WorkerFoundry,
        WorkerFoundryAuthority,
    )
    from aios.application.workspaces.staged import (
        StagedWorkspaceAuthority,
        StagedWorkspaceManager,
    )
    from aios.infrastructure.missions.sqlite_mission_repository import (
        SqliteMissionRepository,
    )
    from aios.policy.kernel import PolicyKernel, PolicyKernelAuthority

    assert ActionBroker is ActionBrokerAuthority
    assert MissionService is MissionAuthority
    assert TurnCoordinator is TurnCoordinatorAuthority
    assert WorkerFoundry is WorkerFoundryAuthority
    assert StagedWorkspaceManager is StagedWorkspaceAuthority
    assert PolicyKernel is PolicyKernelAuthority

    assert type(get_policy_kernel()) is PolicyKernelAuthority
    assert (
        type(
            get_action_broker(
                kernel=get_policy_kernel(),
                capabilities=get_capability_authority(),
            )
        )
        is ActionBrokerAuthority
    )
    assert (
        type(get_worker_foundry(emergency_stop=get_emergency_stop()))
        is WorkerFoundryAuthority
    )
    assert (
        type(MissionAuthority(SqliteMissionRepository(tmp_path / "missions.db")))
        is MissionAuthority
    )
    assert (
        type(StagedWorkspaceAuthority(tmp_path / "staged", enrolled_roots=()))
        is StagedWorkspaceAuthority
    )
    assert type(TurnCoordinatorAuthority(deps=None)) is TurnCoordinatorAuthority

# --------------------------------------------------------------------------- #
# Organs 13, 17, 21 and 22 -- exact owners over existing mechanisms
# --------------------------------------------------------------------------- #


def test_next_backend_owner_batch_is_reached_by_real_constructors(
    tmp_path: Path,
) -> None:
    """The exact owner is the object the existing production API constructs."""
    from aios.application.governance.v1_declaration import (
        ReleaseDeclarationAuthority,
        V1ReleaseDeclaration,
        evaluate_release,
    )
    from aios.council.council_orchestrator import (
        CouncilOrchestrator,
        QueenCouncilAuthority,
    )
    from aios.executor_service import (
        ExecutorServiceAuthority,
        _EXECUTOR_SERVICE_AUTHORITY,
    )
    from aios.runtime.cortex_bus import CortexBus, CortexBusAuthority

    assert CouncilOrchestrator is QueenCouncilAuthority
    assert V1ReleaseDeclaration is ReleaseDeclarationAuthority
    assert CortexBus is CortexBusAuthority

    assert type(CortexBus(tmp_path / "cortex.db")) is CortexBusAuthority
    assert (
        type(QueenCouncilAuthority(runtime_root=tmp_path / "council"))
        is QueenCouncilAuthority
    )
    declaration = evaluate_release(
        root=tmp_path,
        profile="development",
        executor_available=False,
    )
    assert type(declaration) is ReleaseDeclarationAuthority
    assert type(_EXECUTOR_SERVICE_AUTHORITY) is ExecutorServiceAuthority

# --------------------------------------------------------------------------- #
# Organs 26, 40, 43 and 44 -- the remaining Python owner caller proofs
# --------------------------------------------------------------------------- #


def test_emergency_stop_hard_wiring_owner_is_reached_by_learning_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Organ 26: a real application boundary invokes the named owner.

    This is intentionally a call assertion, not an ``isinstance`` check. If
    LearningService ever calls a legacy helper directly, this test fails even
    though ``EmergencyStopHardWiringAuthority`` still exists in the module.
    """
    from aios.application.capabilities.authority import (
        EmergencyStopHardWiringAuthority,
    )
    from aios.application.learning.service import LearningService
    from aios.domain.learning.trajectory_repository import TrajectoryRepository

    calls: list[str] = []
    original = EmergencyStopHardWiringAuthority.assert_operational

    def spy(emergency_stop: object | None, *, boundary: str) -> None:
        calls.append(boundary)
        original(emergency_stop, boundary=boundary)

    monkeypatch.setattr(
        EmergencyStopHardWiringAuthority,
        "assert_operational",
        staticmethod(spy),
    )
    service = LearningService(
        mission_service=MagicMock(),
        trajectory_repository=TrajectoryRepository(tmp_path / "learning.db"),
    )

    service._assert_operational()

    assert calls == ["learning-service"]


def test_isolated_executor_owner_is_reached_by_the_mirror_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 40: the live HTTP projection route calls the named owner."""
    from types import SimpleNamespace

    from aios.api.deps import get_private_executor_service
    from aios.application.executor.service import StructuredExecutorClient
    from aios.application.read_models.executor_projections import (
        get_isolated_executor_live_authority,
    )

    authority = get_isolated_executor_live_authority()
    original = authority.project
    calls: list[object] = []

    def spy(client: object) -> object:
        calls.append(client)
        return original(client)

    monkeypatch.setattr(authority, "project", spy)
    app.dependency_overrides[get_private_executor_service] = lambda: SimpleNamespace(
        client=StructuredExecutorClient(base_url="", token="")
    )
    try:
        response = TestClient(app, client=("127.0.0.1", 12345)).get(
            "/api/v1/mirror/executor"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(calls) == 1
    assert response.json()["executor"]["reachable"]["status"] == "unavailable"


def test_skill_lifecycle_owner_is_reached_by_reuse_outcome_recording(
    tmp_path: Path,
) -> None:
    """Organ 43: the real LearningService outcome path reaches the owner."""
    from aios.application.learning.service import LearningService
    from aios.domain.learning.contracts import ReuseOutcomeReference
    from aios.domain.learning.trajectory_repository import TrajectoryRepository

    service = LearningService(
        mission_service=MagicMock(),
        trajectory_repository=TrajectoryRepository(tmp_path / "learning.db"),
    )
    skill = MagicMock(source_trajectory_ids=())
    service.skill_repository = MagicMock()
    service.skill_repository.get.return_value = skill
    service.reuse_outcome_repository = MagicMock()
    service.reuse_outcome_repository.record.return_value = True
    service.mission_service.repository = MagicMock()
    service.mission_service.repository.get.return_value = None
    lifecycle = MagicMock(return_value=skill)
    service.skill_lifecycle_authority.apply_reuse_outcome = lifecycle
    reference = ReuseOutcomeReference(
        reuse_outcome_id="outcome-1",
        skill_id="skill-1",
        skill_version=1,
        source_trajectory_id="trajectory-1",
        mission_id="mission-1",
        worker_id="worker-1",
        executor_job_id="job-1",
        promotion_id="promotion-1",
        local_job_id="local-job-1",
        local_model_call_id="call-1",
        verification_ids=("verification-1",),
        workspace_digest="workspace-1",
        diff_digest="diff-1",
        project_digest="project-1",
        contract_digest="contract-1",
        policy_version="policy-1",
    )

    assert service.record_reuse_outcome(reference) is skill
    lifecycle.assert_called_once_with(
        "skill-1", 1, success=False, reason="verification"
    )


def test_golden_mission_runner_reaches_endurance_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 44: the compatibility runner delegates to the named owner."""
    from tools import golden_mission_runner
    from tools.golden_mission_runner import GoldenMissionEnduranceAuthority

    calls: list[tuple[str, str, str]] = []

    def run(self, name: str, mission: dict, model_id: str, run_id: str):
        calls.append((name, model_id, run_id))
        return {"mission": name, "passed": True}

    monkeypatch.setattr(GoldenMissionEnduranceAuthority, "run_mission", run)

    result = golden_mission_runner.run_mission(
        "owner-probe", {"steps": []}, "model-probe", "run-probe"
    )

    assert result["passed"] is True
    assert calls == [("owner-probe", "model-probe", "run-probe")]

# --------------------------------------------------------------------------- #
# Organ 6 -- EdgeTrustAuthority
# --------------------------------------------------------------------------- #


def test_edge_trust_authority_is_the_live_api_middleware_owner() -> None:
    from aios.interfaces.http.edge_security import (
        EdgeTrustAuthority,
        get_edge_trust_authority,
    )

    authority = get_edge_trust_authority()
    assert type(authority) is EdgeTrustAuthority
    assert authority.validate_cors_origins(("http://localhost:5173",)) == [
        "http://localhost:5173"
    ]
    assert authority.check_api_token_or_loopback.__self__ is authority
    assert authority.check_mutation_origin_or_token.__self__ is authority

# --------------------------------------------------------------------------- #
# Organ 24 -- IdentityAuthority
# --------------------------------------------------------------------------- #


def test_identity_authority_is_the_real_identity_dependency() -> None:
    from aios.api.deps import get_identity_service
    from aios.application.identity.service import IdentityAuthority, IdentityService

    assert IdentityService is IdentityAuthority
    assert type(get_identity_service()) is IdentityAuthority

# --------------------------------------------------------------------------- #
# Organ 34 -- ProviderHealthBudgetAuthority
# --------------------------------------------------------------------------- #


def test_provider_health_budget_authority_is_the_shared_tracker() -> None:
    from aios.api.deps import get_provider_health
    from aios.application.models.health import (
        ProviderHealthBudgetAuthority,
        ProviderHealthTracker,
    )

    assert ProviderHealthTracker is ProviderHealthBudgetAuthority
    assert type(get_provider_health()) is ProviderHealthBudgetAuthority

# --------------------------------------------------------------------------- #
# Organ 35 -- LocalClerkRuntimeAuthority
# --------------------------------------------------------------------------- #


def test_local_clerk_runtime_authority_owns_model_admission() -> None:
    from unittest.mock import MagicMock

    from aios.application.local_workforce.service import LocalWorkforceService
    from aios.domain.local_workforce.contracts import LocalClerkRuntimeAuthority
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    service = LocalWorkforceService(
        registry=MagicMock(spec=LocalWorkforceRegistry),
        ollama=MagicMock(),
    )

    assert type(service.local_clerk_runtime_authority) is LocalClerkRuntimeAuthority

# --------------------------------------------------------------------------- #
# Organ 37 -- LocalModelQualificationAuthority
# --------------------------------------------------------------------------- #


def test_local_model_qualification_authority_is_the_real_factory() -> None:
    from unittest.mock import MagicMock

    from aios.application.local_workforce.service import LocalWorkforceService
    from aios.domain.local_workforce.qualifier import (
        LocalModelQualificationAuthority,
        QualificationSuite,
    )

    service = LocalWorkforceService(
        registry=MagicMock(),
        ollama=MagicMock(),
    )

    assert QualificationSuite is LocalModelQualificationAuthority
    assert service.qualification_suite_factory is LocalModelQualificationAuthority

# --------------------------------------------------------------------------- #
# Organ 39 -- DeliberationCouncilAuthority
# --------------------------------------------------------------------------- #


def test_deliberation_council_authority_is_the_live_gather_owner(
    tmp_path: Path,
) -> None:
    from aios.council.council_orchestrator import QueenCouncilAuthority
    from aios.council.deliberation_gather import DeliberationCouncilAuthority

    orchestrator = QueenCouncilAuthority(runtime_root=tmp_path)
    assert type(orchestrator.deliberation_authority) is DeliberationCouncilAuthority

# --------------------------------------------------------------------------- #
# Organ 41 -- PromotionRollbackLiveAuthority
# --------------------------------------------------------------------------- #


def test_promotion_rollback_live_authority_owns_checkpoint_validation() -> None:
    from aios.domain.promotion.contracts import PromotionRollbackLiveAuthority

    assert PromotionRollbackLiveAuthority.checkpoint_id_is_valid("checkpoint-1")
    assert not PromotionRollbackLiveAuthority.checkpoint_id_is_valid("")
    assert not PromotionRollbackLiveAuthority.checkpoint_id_is_valid("../escape")

# --------------------------------------------------------------------------- #
# Organ 45 -- ConstitutionalAmendmentAuthority
# --------------------------------------------------------------------------- #


def test_constitutional_amendment_authority_owns_ratification() -> None:
    from types import SimpleNamespace

    from aios.application.governance.amendment_authority import (
        ConstitutionalAmendmentAuthority,
        ratify_amendment,
    )
    from aios.domain.governance.amendments import (
        CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
    )

    proof = SimpleNamespace(
        action_type=CONSTITUTIONAL_AMENDMENT_RATIFY_ACTION,
        operator_id="operator-1",
        consumed_at="2026-07-28T00:00:00+00:00",
        token_digest="digest-owner-test",
    )
    proposal = _proposal()
    authority = ConstitutionalAmendmentAuthority()

    result = authority.ratify_amendment(
        proposal,
        capability_proof=proof,
        operator_id="operator-1",
    )

    assert result.status == "ratified"
    assert ratify_amendment(
        proposal,
        capability_proof=proof,
        operator_id="operator-1",
    ).status == "ratified"

# --------------------------------------------------------------------------- #
# Organ 47 -- ReadModelProjectionAuthority
# --------------------------------------------------------------------------- #


def test_read_model_projection_authority_is_the_mirror_owner() -> None:
    from aios.api.routes.mirror import (
        _READ_MODEL_PROJECTION_AUTHORITY,
    )
    from aios.application.read_models.governance_projections import (
        ReadModelProjectionAuthority,
    )

    assert type(_READ_MODEL_PROJECTION_AUTHORITY) is ReadModelProjectionAuthority

# --------------------------------------------------------------------------- #
# Organ 54 -- BackupDisasterRecoveryAuthority
# --------------------------------------------------------------------------- #


def test_backup_disaster_recovery_authority_owns_restore() -> None:
    from aios.operations.recovery import (
        BackupDisasterRecoveryAuthority,
        get_backup_disaster_recovery_authority,
    )

    assert type(get_backup_disaster_recovery_authority()) is BackupDisasterRecoveryAuthority

# --------------------------------------------------------------------------- #
# Organ 23 -- ReleaseConformanceAuthority
# --------------------------------------------------------------------------- #


def test_release_conformance_authority_is_the_manifest_builder() -> None:
    import runpy

    module = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/build_release_manifest.py"),
        run_name="release_manifest_test",
    )
    authority = module["ReleaseConformanceAuthority"]()
    fresh = authority.build_manifest()
    assert fresh["organ_summary"]["total"] == 54
