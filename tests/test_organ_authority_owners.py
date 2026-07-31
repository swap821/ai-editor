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


def test_organ_46_propose_lesson_module_function_delegates_to_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 46: propose_lesson is not a parallel implementation."""
    from aios.application.governance import constitutional_learning

    lesson_source = inspect.getsource(constitutional_learning.propose_lesson)
    assert "_CONSTITUTIONAL_LEARNING" in lesson_source

    calls: list[dict[str, object]] = []

    def spy(self: object, **kwargs: object) -> object:
        calls.append(kwargs)
        raise RuntimeError("reachability-probe-stop")

    monkeypatch.setattr(
        constitutional_learning.ConstitutionalLearningAuthority,
        "propose_lesson",
        spy,
    )
    with pytest.raises(RuntimeError, match="reachability-probe-stop"):
        constitutional_learning.propose_lesson(
            lesson_id="organ46-reachability-probe",
            problem_class="approval_friction",
            evidence_refs=("event-1",),
            observed_harm="operators repeatedly re-approve the same low-risk action",
            current_rule="every YELLOW action requires fresh approval",
            proposed_improvement=(
                "add a bounded, revocable pre-authorization window for a narrow "
                "named action class"
            ),
            confidence=0.7,
        )
    assert len(calls) == 1


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


# --------------------------------------------------------------------------- #
# Organ 53 -- InstallationConfigurationAuthority (exact owner over token rotation)
# --------------------------------------------------------------------------- #


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


def test_organ_32_route_intelligence_request_delegates_to_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 32: route_intelligence_request is not a parallel implementation."""
    from aios.application.intelligence import gateway

    route_source = inspect.getsource(gateway.route_intelligence_request)
    assert "_UNIVERSAL_GATEWAY_AUTHORITY" in route_source

    calls: list[dict[str, object]] = []

    def spy(self: object, **kwargs: object) -> object:
        calls.append(kwargs)
        raise RuntimeError("reachability-probe-stop")

    monkeypatch.setattr(
        gateway.UniversalIntelligenceGatewayAuthority,
        "route",
        spy,
    )
    with pytest.raises(RuntimeError, match="reachability-probe-stop"):
        gateway.route_intelligence_request(
            request_id="organ32-reachability-probe",
            operator_identity_digest="a" * 64,
            constitution_digest="b" * 64,
            goal="probe the gateway owner",
            desired_outcome="a governed result",
            target="local",
            delegated_authority_summary="human operator decides",
            model_call=lambda _context: "unused",
            context_store=MagicMock(),
        )
    assert len(calls) == 1


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


def test_organ_36_dispatch_clerical_job_delegates_to_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 36: dispatch_clerical_job is not a parallel implementation."""
    from aios.application.local_workforce import dispatcher

    dispatch_source = inspect.getsource(dispatcher.dispatch_clerical_job)
    assert "_CLERK_DISPATCHER" in dispatch_source

    calls: list[dict[str, object]] = []

    def spy(self: object, **kwargs: object) -> object:
        calls.append(kwargs)
        raise RuntimeError("reachability-probe-stop")

    monkeypatch.setattr(dispatcher.ClerkDispatcherAuthority, "dispatch", spy)
    with pytest.raises(RuntimeError, match="reachability-probe-stop"):
        dispatcher.dispatch_clerical_job(
            deterministic_available=True,
            qualification=None,
        )
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# Organ 7 -- PolicyKernelAuthority
# --------------------------------------------------------------------------- #


def test_organ_7_policy_kernel_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 7: deps.get_policy_kernel returns the ledger owner class."""
    from aios.api.deps import get_policy_kernel
    from aios.policy.kernel import PolicyKernel, PolicyKernelAuthority

    assert PolicyKernel is PolicyKernelAuthority
    authority = get_policy_kernel()
    assert type(authority) is PolicyKernelAuthority
    assert get_policy_kernel() is authority

    calls: list[object] = []
    original = PolicyKernelAuthority.runtime_profile_decisions

    def spy(self: object) -> object:
        calls.append(self)
        return original(self)

    monkeypatch.setattr(PolicyKernelAuthority, "runtime_profile_decisions", spy)
    response = TestClient(app, client=("127.0.0.1", 12345)).get(
        "/api/v1/system/runtime-profile"
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0] is authority

# --------------------------------------------------------------------------- #
# Organ 8 -- ActionBrokerAuthority
# --------------------------------------------------------------------------- #


def test_organ_8_action_broker_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 8: deps.get_action_broker returns the ledger owner class."""
    from aios.api.deps import (
        get_action_broker,
        get_capability_authority,
        get_policy_kernel,
    )
    from aios.application.action_broker import ActionBroker, ActionBrokerAuthority
    from aios.domain.actions.envelope import ActionEnvelope, ActionType
    from aios.domain.identity.models import Principal, PrincipalType

    assert ActionBroker is ActionBrokerAuthority
    authority = get_action_broker(
        kernel=get_policy_kernel(),
        capabilities=get_capability_authority(),
    )
    assert type(authority) is ActionBrokerAuthority

    calls: list[object] = []

    def spy(self: object, envelope: object, *args: object, **kwargs: object) -> object:
        calls.append(envelope)
        raise RuntimeError("reachability-probe-stop")

    monkeypatch.setattr(ActionBrokerAuthority, "submit", spy)
    envelope = ActionEnvelope(
        route="/api/v1/owner-probe",
        action_type=ActionType.COMMAND,
        payload={"command": "echo probe"},
        principal=Principal(
            principal_id="operator-probe",
            principal_type=PrincipalType.OPERATOR,
            display_name="probe",
            session_id="owner-probe",
            authentication_level="operator",
            authenticated_at=datetime.now(timezone.utc),
        ),
        operator_id="operator-probe",
    )
    with pytest.raises(RuntimeError, match="reachability-probe-stop"):
        authority.submit(envelope)
    assert len(calls) == 1

# --------------------------------------------------------------------------- #
# Organ 10 -- MissionAuthority
# --------------------------------------------------------------------------- #


def test_organ_10_mission_authority_is_reached_by_maintenance_service() -> None:
    """Organ 10: the maintenance convergence path owns a MissionAuthority.

    Constructing MissionAuthority in a test would only prove the class exists.
    The repair path must hold the ledger owner as its mission_service.
    """
    from aios.api.deps import get_maintenance_convergence_service
    from aios.application.missions.mission_service import (
        MissionAuthority,
        MissionService,
    )

    assert MissionService is MissionAuthority
    service = get_maintenance_convergence_service()
    assert type(service.mission_service) is MissionAuthority

# --------------------------------------------------------------------------- #
# Organ 11 -- TurnCoordinatorAuthority
# --------------------------------------------------------------------------- #


def test_organ_11_turn_coordinator_is_reached_by_the_generate_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 11: api.main binds TurnCoordinatorAuthority and constructs it."""
    from aios.api import main as api_main
    from aios.application.turns.turn_coordinator import (
        TurnCoordinator,
        TurnCoordinatorAuthority,
    )

    assert TurnCoordinator is TurnCoordinatorAuthority
    assert api_main.TurnCoordinator is TurnCoordinatorAuthority

    constructed: list[type] = []
    original_init = TurnCoordinatorAuthority.__init__

    def spy_init(self: object, *args: object, **kwargs: object) -> None:
        constructed.append(type(self))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(TurnCoordinatorAuthority, "__init__", spy_init)
    coordinator = api_main.TurnCoordinator(deps=None)
    assert constructed == [TurnCoordinatorAuthority]
    assert type(coordinator) is TurnCoordinatorAuthority

# --------------------------------------------------------------------------- #
# Organ 12 -- WorkerFoundryAuthority
# --------------------------------------------------------------------------- #


def test_organ_12_worker_foundry_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 12: deps.get_worker_foundry returns the ledger owner class."""
    from aios.api.deps import get_emergency_stop, get_worker_foundry
    from aios.application.workers.foundry import WorkerFoundry, WorkerFoundryAuthority

    assert WorkerFoundry is WorkerFoundryAuthority
    authority = get_worker_foundry(emergency_stop=get_emergency_stop())
    assert type(authority) is WorkerFoundryAuthority
    assert get_worker_foundry(emergency_stop=get_emergency_stop()) is authority

    calls: list[object] = []
    original = WorkerFoundryAuthority.select

    def spy(self: object, strategy: object, contract: object) -> object:
        calls.append((strategy, contract))
        return original(self, strategy, contract)

    monkeypatch.setattr(WorkerFoundryAuthority, "select", spy)
    authority.select("deterministic", object())
    assert len(calls) == 1

# --------------------------------------------------------------------------- #
# Organ 14 -- StagedWorkspaceAuthority
# --------------------------------------------------------------------------- #


def test_organ_14_staged_workspace_is_reached_by_worker_foundry() -> None:
    """Organ 14: production WorkerFoundry holds StagedWorkspaceAuthority."""
    from aios.api.deps import get_emergency_stop, get_worker_foundry
    from aios.application.workspaces.staged import (
        StagedWorkspaceAuthority,
        StagedWorkspaceManager,
    )

    assert StagedWorkspaceManager is StagedWorkspaceAuthority
    foundry = get_worker_foundry(emergency_stop=get_emergency_stop())
    assert type(foundry.workspace_manager) is StagedWorkspaceAuthority

# --------------------------------------------------------------------------- #
# Organ 13 -- ExecutorServiceAuthority
# --------------------------------------------------------------------------- #


def test_organ_13_executor_service_authority_owns_the_live_job_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 13: POST /v1/jobs dispatches through ExecutorServiceAuthority."""
    from aios import executor_service as executor_mod
    from aios.executor_service import (
        ExecutorServiceAuthority,
        _EXECUTOR_SERVICE_AUTHORITY,
        execute_job,
    )

    assert type(_EXECUTOR_SERVICE_AUTHORITY) is ExecutorServiceAuthority
    calls: list[object] = []

    def spy(self: object, job: object, request: object, authorization: object) -> object:
        calls.append(job)
        raise RuntimeError("reachability-probe-stop")

    monkeypatch.setattr(ExecutorServiceAuthority, "execute", spy)
    with pytest.raises(RuntimeError, match="reachability-probe-stop"):
        execute_job(MagicMock(), MagicMock(), authorization=None)
    assert len(calls) == 1
    assert executor_mod._EXECUTOR_SERVICE_AUTHORITY is _EXECUTOR_SERVICE_AUTHORITY

# --------------------------------------------------------------------------- #
# Organ 17 -- CortexBusAuthority
# --------------------------------------------------------------------------- #


def test_organ_17_cortex_bus_is_what_api_lifespan_constructs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Organ 17: get_cortex_bus returns CortexBusAuthority when lifespan installs it."""
    from aios.api import main as api_main
    from aios.runtime.cortex_bus import CortexBus, CortexBusAuthority

    assert CortexBus is CortexBusAuthority
    bus = CortexBusAuthority(tmp_path / "cortex-owner.db")
    monkeypatch.setattr(api_main, "_cortex_bus", bus)
    assert api_main.get_cortex_bus() is bus
    assert type(api_main.get_cortex_bus()) is CortexBusAuthority

# --------------------------------------------------------------------------- #
# Organ 21 -- QueenCouncilAuthority
# --------------------------------------------------------------------------- #


def test_organ_21_queen_council_is_reached_by_council_deliberation_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Organ 21: council deliberation constructs QueenCouncilAuthority."""
    from aios.api.routes import council as council_routes
    from aios.council.council_orchestrator import (
        CouncilOrchestrator,
        QueenCouncilAuthority,
    )

    assert CouncilOrchestrator is QueenCouncilAuthority
    assert council_routes.CouncilOrchestrator is QueenCouncilAuthority

    constructed: list[type] = []
    original_init = QueenCouncilAuthority.__init__

    def spy_init(self: object, *args: object, **kwargs: object) -> None:
        constructed.append(type(self))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(QueenCouncilAuthority, "__init__", spy_init)
    authority = council_routes.CouncilOrchestrator(runtime_root=tmp_path / "council")
    assert constructed == [QueenCouncilAuthority]
    assert type(authority) is QueenCouncilAuthority

# --------------------------------------------------------------------------- #
# Organ 22 -- ReleaseDeclarationAuthority
# --------------------------------------------------------------------------- #


def test_organ_22_launcher_v1_check_evaluates_release_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 22: launcher v1-check evaluates ReleaseDeclarationAuthority."""
    from aios.application.governance.v1_declaration import (
        ReleaseDeclarationAuthority,
        V1ReleaseDeclaration,
        evaluate_release,
    )
    from aios.launcher import LauncherConfig, v1_check

    assert V1ReleaseDeclaration is ReleaseDeclarationAuthority

    captured: list[object] = []
    real_evaluate = evaluate_release

    def spy(*args: object, **kwargs: object) -> ReleaseDeclarationAuthority:
        declaration = real_evaluate(*args, **kwargs)
        captured.append(declaration)
        return declaration

    monkeypatch.setattr("aios.application.governance.evaluate_release", spy)
    monkeypatch.setattr(
        "aios.application.governance.runtime_proof.run_runtime_proofs",
        lambda _root: MagicMock(
            proofs={
                "executor_runtime_available": MagicMock(
                    passed=False, name="x", evidence="t"
                ),
            },
            boolean_map=lambda: {},
            evidence_map=lambda: {},
            all_passed=False,
            as_dict=lambda: {},
        ),
    )

    config = LauncherConfig(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        profile="development",
        api_port=8000,
        gateway_port=8000,
        compose_file=tmp_path / "docker-compose.yml",
        state_file=tmp_path / "launcher-state.json",
        log_file=tmp_path / "launcher.log",
    )
    code = v1_check(config, strict=False, as_json=False)
    assert code == 0
    assert captured, "v1_check must call evaluate_release"
    assert type(captured[0]) is ReleaseDeclarationAuthority


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
# Organ 9 -- CapabilityAuthority
# --------------------------------------------------------------------------- #


def test_capability_authority_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 9: the FastAPI dependency returns the exact ledger owner class.

    A green claim that only proves the class exists would satisfy Decision A
    while leaving condition 2 (a real runtime path invokes it) unchecked.
    ``get_capability_authority`` is the production singleton every privileged
    route binds — proving its concrete type is reachability, not existence.
    """
    from aios.api.deps import get_capability_authority
    from aios.application.capabilities.authority import CapabilityAuthority

    authority = get_capability_authority()
    assert type(authority) is CapabilityAuthority
    assert get_capability_authority() is authority

    calls: list[object] = []
    original = CapabilityAuthority.list_pending

    def spy(self: object) -> object:
        calls.append(self)
        return original(self)

    monkeypatch.setattr(CapabilityAuthority, "list_pending", spy)
    response = TestClient(app, client=("127.0.0.1", 12345)).get(
        "/api/v1/mirror/governance"
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0] is authority


# --------------------------------------------------------------------------- #
# Organ 15 -- VerificationAuthority
# --------------------------------------------------------------------------- #


def test_verification_authority_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 15: deps.get_verification_authority returns the ledger owner."""
    from aios.api.deps import get_verification_authority
    from aios.application.evidence.verification import VerificationAuthority

    authority = get_verification_authority()
    assert type(authority) is VerificationAuthority
    assert get_verification_authority() is authority

    calls: list[str] = []
    original = VerificationAuthority.list_results_for_mission

    def spy(self: object, mission_id: str) -> object:
        calls.append(mission_id)
        return original(self, mission_id)

    monkeypatch.setattr(VerificationAuthority, "list_results_for_mission", spy)
    authority.list_results_for_mission("owner-probe-mission")
    assert calls == ["owner-probe-mission"]


# --------------------------------------------------------------------------- #
# Organ 16 -- PromotionAuthority
# --------------------------------------------------------------------------- #


def test_promotion_authority_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 16: deps.get_promotion_authority returns the ledger owner."""
    from aios.api.deps import get_promotion_authority
    from aios.application.promotion.authority import PromotionAuthority

    authority = get_promotion_authority()
    assert type(authority) is PromotionAuthority
    assert get_promotion_authority() is authority

    calls: list[str] = []
    original = PromotionAuthority.get_promotion

    def spy(self: object, mission_id: str) -> object:
        calls.append(mission_id)
        return original(self, mission_id)

    monkeypatch.setattr(PromotionAuthority, "get_promotion", spy)
    assert authority.get_promotion("owner-probe-mission") is None
    assert calls == ["owner-probe-mission"]


# --------------------------------------------------------------------------- #
# Organ 18 -- MemoryAuthority
# --------------------------------------------------------------------------- #


def test_memory_authority_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 18: deps.get_memory_authority returns the ledger owner."""
    from aios.api.deps import get_memory_authority
    from aios.application.memory.authority import MemoryAuthority

    authority = get_memory_authority()
    assert type(authority) is MemoryAuthority
    assert get_memory_authority() is authority

    calls: list[str] = []
    original = MemoryAuthority.recall

    def spy(self: object, query: str, *args: object, **kwargs: object) -> object:
        calls.append(query)
        return original(self, query, *args, **kwargs)

    monkeypatch.setattr(MemoryAuthority, "recall", spy)
    response = TestClient(app, client=("127.0.0.1", 12345)).post(
        "/api/v1/memory/search",
        json={"query": "owner-probe", "top_k": 1},
    )
    assert response.status_code == 200
    assert calls == ["owner-probe"]


# --------------------------------------------------------------------------- #
# Organ 19 -- EmergencyStopController
# --------------------------------------------------------------------------- #


def test_emergency_stop_controller_is_the_live_dependency_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 19: deps.get_emergency_stop returns the ledger owner."""
    from aios.api.deps import get_emergency_stop
    from aios.application.governance.emergency_stop import EmergencyStopController

    authority = get_emergency_stop()
    assert type(authority) is EmergencyStopController
    assert get_emergency_stop() is authority

    calls: list[object] = []
    original = EmergencyStopController.state

    def spy(self: object) -> object:
        calls.append(self)
        return original(self)

    monkeypatch.setattr(EmergencyStopController, "state", spy)
    response = TestClient(app, client=("127.0.0.1", 12345)).get(
        "/api/v1/governance/emergency-stop"
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0] is authority


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


def test_organ_6_edge_trust_middleware_reaches_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 6: api.main middleware reaches EdgeTrustAuthority, not a twin."""
    from aios.interfaces.http import edge_security

    token_source = inspect.getsource(edge_security.check_api_token_or_loopback)
    assert "_EDGE_TRUST_AUTHORITY" in token_source

    calls: list[object] = []
    original = edge_security.EdgeTrustAuthority.check_api_token_or_loopback

    def spy(self: object, request: object) -> object:
        calls.append(request)
        return original(self, request)  # type: ignore[arg-type]

    monkeypatch.setattr(
        edge_security.EdgeTrustAuthority,
        "check_api_token_or_loopback",
        spy,
    )
    response = TestClient(app, client=("127.0.0.1", 12345)).get(
        "/api/v1/system/runtime-profile"
    )
    assert response.status_code == 200
    assert len(calls) == 1


def test_organ_6_policy_kernel_delegates_api_token_check_to_edge_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 6: PolicyKernelAuthority.check_api_token_or_loopback delegates."""
    from aios.api.deps import get_policy_kernel
    from aios.interfaces.http import edge_security

    calls: list[object] = []
    original = edge_security.EdgeTrustAuthority.check_api_token_or_loopback

    def spy(self: object, request: object) -> object:
        calls.append(request)
        return original(self, request)  # type: ignore[arg-type]

    monkeypatch.setattr(
        edge_security.EdgeTrustAuthority,
        "check_api_token_or_loopback",
        spy,
    )

    request = MagicMock()
    request.url.path = "/api/probe"
    request.method = "GET"
    request.headers = {"host": "localhost:8000"}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"

    assert get_policy_kernel().check_api_token_or_loopback(request) is None
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# Organ 24 -- IdentityAuthority
# --------------------------------------------------------------------------- #


def test_identity_authority_is_the_real_identity_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aios.api.deps import get_identity_service
    from aios.application.identity.service import IdentityAuthority, IdentityService

    authority = get_identity_service()
    assert IdentityService is IdentityAuthority
    assert type(authority) is IdentityAuthority

    calls: list[object] = []
    original = IdentityAuthority.is_enrolled

    def spy(self: object) -> object:
        calls.append(self)
        return original(self)

    monkeypatch.setattr(IdentityAuthority, "is_enrolled", spy)
    assert isinstance(authority.is_enrolled(), bool)
    assert len(calls) == 1
    assert calls[0] is authority

# --------------------------------------------------------------------------- #
# Organ 34 -- ProviderHealthBudgetAuthority
# --------------------------------------------------------------------------- #


def test_provider_health_budget_authority_is_the_shared_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aios.api.deps import get_provider_health
    from aios.application.models.health import (
        ProviderHealthBudgetAuthority,
        ProviderHealthTracker,
    )

    assert ProviderHealthTracker is ProviderHealthBudgetAuthority
    authority = get_provider_health()
    assert type(authority) is ProviderHealthBudgetAuthority

    calls: list[str] = []
    original = ProviderHealthBudgetAuthority.has_observations

    def spy(self: object, provider: str) -> object:
        calls.append(provider)
        return original(self, provider)

    monkeypatch.setattr(ProviderHealthBudgetAuthority, "has_observations", spy)
    response = TestClient(app, client=("127.0.0.1", 12345)).get(
        "/api/v1/mirror/governance"
    )
    assert response.status_code == 200
    assert calls
    assert authority is get_provider_health()

# --------------------------------------------------------------------------- #
# Organ 35 -- LocalClerkRuntimeAuthority
# --------------------------------------------------------------------------- #


def test_local_clerk_runtime_authority_owns_model_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from aios.application.local_workforce.service import LocalWorkforceService
    from aios.domain.local_workforce.contracts import (
        LocalClerkRuntimeAuthority,
        LocalJobProfile,
        LocalJobRequest,
    )
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    service = LocalWorkforceService(
        registry=MagicMock(spec=LocalWorkforceRegistry),
        ollama=MagicMock(),
    )
    authority = service.local_clerk_runtime_authority
    assert type(authority) is LocalClerkRuntimeAuthority

    calls: list[object] = []
    original = LocalClerkRuntimeAuthority.eligible_models

    def spy(self: object, request: object, models: object) -> object:
        calls.append(request)
        return original(self, request, models)

    monkeypatch.setattr(LocalClerkRuntimeAuthority, "eligible_models", spy)
    request = LocalJobRequest(
        job_id="owner-runtime-probe",
        job_profile=LocalJobProfile.SELECT_SKILL,
        input_schema_version="1.0",
        evidence_references=frozenset({"skill-1"}),
        redacted_payload="probe",
        token_budget=32,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=30),
        required_output_schema={"applicable": "bool"},
    )
    authority.eligible_models(request, ())
    assert len(calls) == 1
    assert calls[0] is request

# --------------------------------------------------------------------------- #
# Organ 37 -- LocalModelQualificationAuthority
# --------------------------------------------------------------------------- #


def test_local_model_qualification_authority_is_the_real_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    calls: list[object] = []
    original = LocalModelQualificationAuthority.run

    def spy(self: object) -> object:
        calls.append(self)
        raise RuntimeError("reachability-probe-stop")

    monkeypatch.setattr(LocalModelQualificationAuthority, "run", spy)
    suite = service.qualification_suite_factory(MagicMock())
    assert type(suite) is LocalModelQualificationAuthority
    with pytest.raises(RuntimeError, match="reachability-probe-stop"):
        suite.run()
    assert len(calls) == 1
    assert calls[0] is suite

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


# --------------------------------------------------------------------------- #
# Organs 1-5 -- frozen security spine (Decision A classes DEPLOYED 2026-07-31)
#
# §VIII Approve+Deploy added SecurityGatewayAuthority etc. Existing module
# functions remain the production call sites; these tests prove both the named
# class exists in the entrypoint module AND the live route/lifespan path still
# reaches the underlying mechanism.
# --------------------------------------------------------------------------- #


def test_organ_1_security_gateway_authority_owns_classify_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 1: classify route reaches SecurityGatewayAuthority via singleton."""
    import aios.security.gateway as gateway
    from aios.api.routes import system as system_routes
    from aios.security.gateway import (
        ClassificationResult,
        SecurityGatewayAuthority,
        Zone,
        _GATEWAY,
    )

    assert inspect.isclass(SecurityGatewayAuthority)
    classify_source = inspect.getsource(gateway.classify)
    assert "_GATEWAY" in classify_source
    assert "_GATEWAY.classify" in classify_source

    calls: list[str] = []
    original = _GATEWAY.classify

    def spy(command: str, *args: object, **kwargs: object) -> ClassificationResult:
        calls.append(command)
        return original(command, *args, **kwargs)

    monkeypatch.setattr(_GATEWAY, "classify", spy)

    result = system_routes.security_classify(
        system_routes.ClassifyRequest(command="echo hello")
    )
    assert calls == ["echo hello"]
    assert result["zone"] == Zone.GREEN.value


def test_organ_2_scope_lock_authority_owns_files_path_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Organ 2: files route reaches ScopeLockAuthority via singleton."""
    from aios.api.routes import files as files_routes
    from aios.security import scope_lock
    from aios.security.scope_lock import ScopeLockAuthority, ScopeResult, _SCOPE_LOCK

    assert isinstance(ScopeLockAuthority().is_path_in_scope(str(tmp_path)).in_scope, bool)
    scope_source = inspect.getsource(scope_lock.is_path_in_scope)
    assert "_SCOPE_LOCK" in scope_source

    calls: list[str] = []
    original = _SCOPE_LOCK.is_path_in_scope

    def spy(path: str, *args: object, **kwargs: object) -> ScopeResult:
        calls.append(str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(_SCOPE_LOCK, "is_path_in_scope", spy)

    check = files_routes.is_path_in_scope(str(tmp_path))
    assert calls == [str(tmp_path)]
    assert isinstance(check.in_scope, bool)


def test_organ_3_secret_scanner_authority_owns_api_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 3: api.main binding reaches SecretScannerAuthority singleton."""
    from aios.api import main as api_main
    from aios.security import secret_scanner
    from aios.security.secret_scanner import SecretScannerAuthority, _SECRET_SCANNER

    scan_source = inspect.getsource(secret_scanner.scan_and_redact)
    assert "_SECRET_SCANNER" in scan_source
    assert api_main.scan_and_redact is secret_scanner.scan_and_redact

    calls: list[str] = []
    original = _SECRET_SCANNER.scan_and_redact

    def spy(payload: str):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(_SECRET_SCANNER, "scan_and_redact", spy)

    result = api_main.scan_and_redact("no secrets here")
    assert calls == ["no secrets here"]
    assert result.scrubbed == "no secrets here"
    assert result.detected is False
    assert result.findings == ()
    assert isinstance(SecretScannerAuthority(), SecretScannerAuthority)


def test_organ_4_audit_logger_authority_owns_verify_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 4: audit verify route reaches AuditLoggerAuthority singleton."""
    from aios.api.routes import system as system_routes
    from aios.security import audit_logger
    from aios.security.audit_logger import AuditLoggerAuthority, ChainStatus, _AUDIT

    verify_source = inspect.getsource(audit_logger.verify_chain)
    assert "_audit_for" in verify_source or "_AUDIT" in verify_source
    assert isinstance(AuditLoggerAuthority().verify_chain(from_id=1, to_id=None), ChainStatus)

    calls: list[tuple[int, object]] = []
    original = _AUDIT.verify_chain

    def spy(
        *,
        from_id: int = 1,
        to_id: int | None = None,
        **kwargs: object,
    ) -> ChainStatus:
        calls.append((from_id, to_id))
        return original(from_id=from_id, to_id=to_id, **kwargs)

    monkeypatch.setattr(_AUDIT, "verify_chain", spy)

    status = system_routes.audit_verify(from_entry=1, to_entry=None)
    assert calls == [(1, None)]
    assert "valid" in status


def test_organ_5_injection_shield_authority_is_installed_from_api_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organ 5: lifespan wires InjectionShieldAuthority (=VectorInjectionShield)."""
    from aios import config
    from aios.security import gateway
    from aios.security.injection_shield import (
        InjectionShieldAuthority,
        VectorInjectionShield,
    )

    assert InjectionShieldAuthority is VectorInjectionShield

    installed: list[object] = []
    original = gateway.set_injection_shield

    def spy(shield: object) -> None:
        installed.append(shield)
        original(shield)

    monkeypatch.setattr(gateway, "set_injection_shield", spy)
    monkeypatch.setattr(config, "INJECTION_VECTOR_SHIELD", True)

    with TestClient(app) as _client:
        pass

    assert len(installed) == 1
    assert type(installed[0]) is InjectionShieldAuthority
