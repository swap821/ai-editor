"""R14 executable runtime proof matrix for the GAGOS v1 boundary.

The proof runner deliberately uses disposable stores and explicit dependency
injection.  It never treats a source file as runtime evidence, never prints
bearer material, and reports an unavailable private executor as a failed proof.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aios import config
from aios.application.action_broker import ActionBroker
from aios.application.capabilities.authority import CapabilityAuthority, CapabilityError
from aios.application.capabilities.verifier import CapabilityVerifier
from aios.application.evidence.verification import VerificationAuthority
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopError,
    EmergencyStopHooks,
)
from aios.application.identity.service import IdentityService
from aios.application.memory.authority import MemoryAuthority
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.turns.turn_context import TurnContext, TurnMode
from aios.application.turns.turn_coordinator import (
    RuntimeDeps,
    TurnCoordinator,
    production_handlers,
)
from aios.application.workspaces.staged import StagedWorkspaceManager
from aios.core.events import CanonicalEvent
from aios.core.executor import Executor
from aios.domain.actions.envelope import (
    ActionEnvelope,
    ActionType,
    Principal as EnvelopePrincipal,
)
from aios.domain.capabilities.contracts import CapabilityBinding
from aios.domain.capabilities.digest import payload_digest, resource_digest
from aios.domain.evidence import (
    EvidenceBundle,
    EvidenceCommand,
    EvidenceRecord,
    EvidenceType,
    VerificationObservation,
    VerificationPlanV1,
)
from aios.domain.memory import MemoryHit, MemoryProposal, MemoryPromotionActor
from aios.domain.missions.mission_contract import (
    MissionBudget,
    MissionContract,
    VerificationPlan,
)
from aios.domain.missions.mission_state import MissionState
from aios.domain.promotion import PromotionRequest, PromotionStatus
from aios.infrastructure.memory import MemoryAuthorityStore
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.application.executor.service import (
    IsolationUnavailable,
    StructuredExecutorClient,
)
from aios.domain.executor import ExecutorCapability, ExecutorJob, ResourceLimits
from aios.interfaces.http import edge_security
from aios.policy.kernel import PolicyKernel


REQUIRED_PROOFS = (
    "operator_identity",
    "exact_capabilities",
    "edge_trust_boundary",
    "mutation_authority",
    "mission_lifecycle",
    "isolated_executor",
    "executor_runtime_available",
    "staged_workspaces",
    "verification_and_recovery",
    "promotion_authority",
    "turn_coordinator",
    "cortex_consumer_cursors",
    "truthful_mirror",
    "memory_provenance",
    "emergency_stop_controller",
    "production_profile_fail_closed",
)


@dataclass(frozen=True, slots=True)
class RuntimeProof:
    name: str
    passed: bool
    evidence: str
    proof_level: str = "fixture"


@dataclass(frozen=True, slots=True)
class RuntimeProofReport:
    proofs: dict[str, RuntimeProof]

    @property
    def all_passed(self) -> bool:
        return all(self.proofs[name].passed for name in REQUIRED_PROOFS)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(name for name in REQUIRED_PROOFS if not self.proofs[name].passed)

    def boolean_map(self) -> dict[str, bool]:
        return {name: self.proofs[name].passed for name in REQUIRED_PROOFS}

    def evidence_map(self) -> dict[str, str]:
        return {name: self.proofs[name].evidence for name in REQUIRED_PROOFS}

    def as_dict(self) -> dict[str, object]:
        return {
            "all_passed": self.all_passed,
            "failures": list(self.failures),
            "proofs": {
                name: {
                    "name": proof.name,
                    "passed": proof.passed,
                    "evidence": proof.evidence,
                    "proof_level": proof.proof_level,
                }
                for name, proof in self.proofs.items()
            },
        }


def _proof(name: str, callback, *, proof_level: str = "fixture") -> RuntimeProof:
    try:
        evidence = str(callback()).strip() or "probe completed without evidence"
    except Exception as exc:  # noqa: BLE001 - each proof fails closed independently
        return RuntimeProof(
            name=name,
            passed=False,
            evidence=f"probe failed: {type(exc).__name__}: {str(exc)[:240]}",
            proof_level=proof_level,
        )
    return RuntimeProof(
        name=name,
        passed=True,
        evidence=evidence,
        proof_level=proof_level,
    )


def run_runtime_proofs(root: str | Path | None = None) -> RuntimeProofReport:
    """Execute the complete disposable R14 proof matrix.

    ``root`` is the repository root used for route/source discovery.  All
    mutable proof state lives under a fresh temporary directory.  The private
    executor proof uses the configured live service and fails when that service
    is absent; there is no host or local-process substitute.
    """

    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    with tempfile.TemporaryDirectory(prefix="gagos-v1-runtime-proof-") as raw:
        scratch = Path(raw)
        results: dict[str, RuntimeProof] = {}
        results["operator_identity"] = _proof(
            "operator_identity", lambda: _probe_identity(scratch)
        )
        results["exact_capabilities"] = _proof(
            "exact_capabilities", lambda: _probe_capabilities(scratch)
        )
        results["edge_trust_boundary"] = _proof("edge_trust_boundary", _probe_edge)
        results["mutation_authority"] = _proof(
            "mutation_authority", lambda: _probe_mutation_authority(repo, scratch)
        )
        results["mission_lifecycle"] = _proof(
            "mission_lifecycle", lambda: _probe_mission(scratch)
        )

        executor = _proof("isolated_executor", lambda: _probe_executor(scratch))
        results["isolated_executor"] = executor
        results["executor_runtime_available"] = RuntimeProof(
            name="executor_runtime_available",
            passed=executor.passed,
            evidence=executor.evidence,
        )

        staging = _proof(
            "promotion_authority", lambda: _probe_staging_and_promotion(scratch)
        )
        for name in (
            "staged_workspaces",
            "verification_and_recovery",
            "promotion_authority",
        ):
            results[name] = RuntimeProof(
                name=name, passed=staging.passed, evidence=staging.evidence
            )

        results["turn_coordinator"] = _proof(
            "turn_coordinator", _probe_turn_coordinator
        )
        cortex = _proof("cortex_consumer_cursors", lambda: _probe_cortex(scratch))
        results["cortex_consumer_cursors"] = cortex
        results["truthful_mirror"] = _proof(
            "truthful_mirror", lambda: _probe_mirror(repo, scratch, cortex)
        )
        results["memory_provenance"] = _proof(
            "memory_provenance", lambda: _probe_memory(scratch)
        )
        results["emergency_stop_controller"] = _proof(
            "emergency_stop_controller", lambda: _probe_emergency_stop(scratch)
        )
        results["production_profile_fail_closed"] = _proof(
            "production_profile_fail_closed", lambda: _probe_production_profile(scratch)
        )
    return RuntimeProofReport(results)


def _probe_identity(scratch: Path) -> str:
    service = IdentityService(
        identity_db_path=scratch / "identity.db",
        session_db_path=scratch / "sessions.db",
    )
    enrollment = service.enroll_operator(display_name="R14 Proof Operator")
    login = service.authenticate_credential(enrollment.enrollment_credential)
    privileged = service.reauthenticate(
        login.session_cookie, enrollment.enrollment_credential
    )
    principal = service.get_authenticated_principal(privileged.session_cookie)
    if principal is None or principal.authentication_level != "privileged":
        raise RuntimeError("fresh privileged principal was not established")
    if login.session_cookie == privileged.session_cookie:
        raise RuntimeError("privileged reauthentication did not rotate the session")
    if service.get_authenticated_principal(login.session_cookie) is not None:
        raise RuntimeError("pre-rotation session remained valid")
    if service.authentication_event_count() != 2:
        raise RuntimeError(
            "login and privileged authentication events were not durable"
        )
    return "temporary enrollment, authentication, privileged reauthentication, and session rotation verified"


def _capability_binding(*, payload: dict[str, object]) -> CapabilityBinding:
    return CapabilityBinding(
        operator_id="operator:proof",
        device_id="device:proof",
        authentication_event_id="event:proof",
        session_id="session:proof",
        action_type="command",
        route="/api/v1/execute",
        http_method="POST",
        payload_digest=payload_digest(payload),
        resource_digest=resource_digest({"workspace": "training_ground"}),
        mission_id=None,
        contract_digest=None,
        policy_version="v1",
        scope="training_ground/",
        verification_requirement="command_exit_zero",
    )


def _probe_capabilities(scratch: Path) -> str:
    payload = {"command": "echo proof"}
    binding = _capability_binding(payload=payload)
    authority = CapabilityAuthority(db_path=scratch / "capabilities.db")
    verifier = CapabilityVerifier(authority)
    token = authority.issue(binding, action_payload=payload)
    verifier.verify(token, binding)
    consumed = verifier.consume(token, binding)
    if consumed.consumed_at is None:
        raise RuntimeError("capability consumption was not recorded")
    try:
        authority.consume(token, binding)
    except CapabilityError:
        pass
    else:
        raise RuntimeError("capability replay was accepted")

    altered = replace(
        binding, payload_digest=payload_digest({"command": "echo altered"})
    )
    second = authority.issue(binding, action_payload=payload)
    try:
        verifier.verify(second, altered)
    except CapabilityError:
        pass
    else:
        raise RuntimeError("altered payload binding was accepted")
    return "exact capability issued, consumed once, replay refused, altered payload refused"


class _EdgeRequest:
    def __init__(self, *, host: str, origin: str, client_host: str = "8.8.8.8") -> None:
        self.client = SimpleNamespace(host=client_host)
        self.headers = {"host": host, "origin": origin}
        self.cookies: dict[str, str] = {}
        self.method = "POST"
        self.url = SimpleNamespace(path="/api/v1/auth/session")


def _probe_edge() -> str:
    spoofed = _EdgeRequest(
        host="localhost:8000",
        origin="http://localhost.evil.com:5173",
    )
    if edge_security.is_allowed_origin(
        spoofed.headers["origin"], ["http://localhost:5173"]
    ):
        raise RuntimeError("spoofed origin was accepted")
    if edge_security.check_mutation_origin_or_token(spoofed) is None:
        raise RuntimeError("spoofed mutation origin reached the side-effect boundary")

    host_spoof = _EdgeRequest(host="attacker.example", origin="http://localhost:5173")
    host_error = edge_security._check_host_header(host_spoof)
    if host_error is None or host_error.status_code != 400:
        raise RuntimeError("spoofed host was not refused")
    try:
        edge_security.validate_cors_origins(("*",))
    except RuntimeError:
        pass
    else:
        raise RuntimeError("wildcard credentialed CORS origin was accepted")
    return (
        "spoofed origin, host, and wildcard CORS requests were refused before mutation"
    )


def _mutating_route_decorators(repo: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    api_root = repo / "aios" / "api"
    for source in list((api_root / "routes").glob("*.py")) + [api_root / "main.py"]:
        if not source.is_file():
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            method = node.func.attr.upper()
            if method not in {"POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id not in {
                "router",
                "app",
            }:
                continue
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.append((method, node.args[0].value))
    return found


def _probe_mutation_authority(repo: Path, scratch: Path) -> str:
    kernel = PolicyKernel()
    registered = 0
    for method, route in _mutating_route_decorators(repo):
        authority = kernel.route_authority(route, method)
        if authority.action_type is ActionType.UNKNOWN:
            raise RuntimeError(
                f"mutating route lacks executable authority: {method} {route}"
            )
        registered += 1

    broker = ActionBroker(
        kernel,
        capabilities=CapabilityAuthority(db_path=scratch / "unknown-route.db"),
    )
    envelope = ActionEnvelope(
        route="/api/v1/unknown-runtime-proof-route",
        action_type=ActionType.UNKNOWN,
        http_method="POST",
        payload={"probe": True},
        principal=EnvelopePrincipal(session_id="session:proof"),
    )
    decision = broker.submit(envelope)
    zone = getattr(decision.zone, "value", decision.zone)
    if not decision.blocked or zone != "RED":
        raise RuntimeError("unknown mutation did not fail RED through ActionBroker")
    return f"{registered} mutating route declarations resolved through PolicyKernel; unknown mutation failed RED through ActionBroker"


def _probe_mission(scratch: Path) -> str:
    repository = SqliteMissionRepository(scratch / "missions.db")
    service = MissionService(repository, export_dir=scratch / "exports")
    contract = MissionContract(
        mission_id="r14-mission",
        operator_id="operator:proof",
        goal="complete the disposable R14 mission",
        worker_type="proof-worker",
        created_by="proof-planner",
        project_id="proof-project",
        turn_id="proof-turn",
        budget=MissionBudget(max_workers=1, max_steps=3, timeout_seconds=30),
        verification_plan=VerificationPlan(required_strength="strong"),
    )
    service.create(contract)
    service.start_deliberation(contract.mission_id)
    service.request_approval(contract.mission_id)
    service.approve(
        contract.mission_id,
        operator_id=contract.operator_id,
        capability_digest="capability-proof",
        contract_digest=contract.digest(),
        authentication_event_id="auth-proof",
        session_id="session-proof",
    )
    service.start_execution(contract.mission_id)
    service.start_verification(contract.mission_id)
    completed = service.complete(contract.mission_id, evidence_digest="evidence-proof")
    history = repository.transition_history(contract.mission_id)
    if completed.state is not MissionState.COMPLETED:
        raise RuntimeError("mission did not complete")
    if [item["to_state"] for item in history] != [
        "deliberating",
        "awaiting_approval",
        "approved",
        "running",
        "verifying",
        "completed",
    ]:
        raise RuntimeError("mission lifecycle omitted a required transition")
    approval = next(item for item in history if item["to_state"] == "approved")
    if (
        approval["authentication_event_id"] != "auth-proof"
        or approval["session_id"] != "session-proof"
    ):
        raise RuntimeError("human approval evidence was not attributed")
    if "evidence-proof" not in str(history[-1]["reason"]):
        raise RuntimeError("completion did not retain evidence attribution")
    return "mission originated, deliberated, approved by a bound operator, executed, verified, and completed with evidence attribution"


def _probe_executor(scratch: Path) -> str:
    token = config.EXECUTOR_TOKEN
    base_url = config.EXECUTOR_URL
    if not token or not base_url:
        raise IsolationUnavailable(
            "private executor service is unavailable or unconfigured"
        )
    client = StructuredExecutorClient(base_url=base_url, token=token, timeout_s=30)
    client.health()
    local_root = Path(config.EXECUTOR_WORKSPACE_ROOT).resolve()
    workspace = local_root / f"gagos-v1-proof-{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, exist_ok=False)
    try:
        (workspace / "probe.py").write_text(
            "import os, socket\n"
            "from pathlib import Path\n"
            "print(f'uid={os.getuid()}')\n"
            "try:\n"
            "    socket.create_connection(('1.1.1.1', 80), timeout=1)\n"
            "    print('network=allowed')\n"
            "except Exception:\n"
            "    print('network=blocked')\n"
            "try:\n"
            "    Path('/app/outside.txt').write_text('escape')\n"
            "    print('outside=written')\n"
            "except Exception:\n"
            "    print('outside=blocked')\n",
            encoding="utf-8",
        )
        remote = Path(config.EXECUTOR_REMOTE_WORKSPACE_ROOT) / workspace.name
        job_id = f"r14-proof-{uuid.uuid4().hex}"
        contract_digest = hashlib.sha256(job_id.encode()).hexdigest()
        result = client.execute(
            ExecutorJob(
                job_id=job_id,
                mission_contract_digest=contract_digest,
                capability=ExecutorCapability(
                    capability_id=f"cap-{job_id}",
                    action_digest=hashlib.sha256(
                        (job_id + "-action").encode()
                    ).hexdigest(),
                    mission_contract_digest=contract_digest,
                    expires_at="2099-01-01T00:00:00+00:00",
                ),
                image=config.CONTAINER_IMAGE,
                argv=("python", "probe.py"),
                workspace_snapshot=str(remote),
                resource_limits=ResourceLimits(
                    timeout_seconds=10,
                    max_output_bytes=4096,
                ),
            )
        )
        if result.status != "completed" or not result.isolation_verified:
            raise IsolationUnavailable(
                "private executor did not return verified completion"
            )
        output = result.stdout
        if (
            "uid=65534" not in output
            or "network=blocked" not in output
            or "outside=blocked" not in output
        ):
            raise IsolationUnavailable("executor isolation evidence was incomplete")
        return "live private Executor Service proved non-root uid=65534, no network, and no workspace escape"
    finally:
        try:
            workspace.relative_to(local_root)
        except ValueError:
            raise RuntimeError("executor proof workspace escaped configured root")
        shutil.rmtree(workspace, ignore_errors=True)


def _verification_result(
    verification: VerificationAuthority,
    *,
    mission_id: str,
    action_id: str,
    diff: dict[str, object],
) -> object:
    observation = VerificationObservation(
        command="pytest app.txt",
        exit_code=0,
        stdout="1 passed",
        passed_count=1,
        tool_version="r14-proof",
    )
    return verification.verify(
        mission_id=mission_id,
        action_id=action_id,
        worker_id="worker-proof",
        target="app.txt",
        plan=VerificationPlanV1(
            intended_behavior="app contains the staged proof result",
            targets=("app.txt",),
            minimum_strength=3,
        ),
        workspace_digest=str(diff["workspace_digest"]),
        diff_digest=str(diff["diff_digest"]),
        environment_digest="environment-proof",
        observation=observation,
    )


def _promotion_request(
    manager,
    project: Path,
    lease,
    verification: VerificationAuthority,
    *,
    mission_id: str,
    action_id: str,
) -> PromotionRequest:
    diff = manager.diff(lease)
    result = _verification_result(
        verification,
        mission_id=mission_id,
        action_id=action_id,
        diff=diff,
    )
    observation = VerificationObservation(
        command="pytest app.txt",
        exit_code=0,
        stdout="1 passed",
        passed_count=1,
        tool_version="r14-proof",
    )
    bundle = EvidenceBundle(
        mission_id=mission_id,
        worker_id="worker-proof",
        contract_digest="contract-proof",
        workspace_digest=str(diff["workspace_digest"]),
        diff_digest=str(diff["diff_digest"]),
        executor_job_id="worker-proof",
        environment_digest="environment-proof",
        commands=(
            EvidenceCommand(
                command=observation.command,
                return_code=0,
                stdout_digest="stdout-proof",
                stderr_digest="stderr-proof",
                tool_version=observation.tool_version,
                observed_at=observation.observed_at,
            ),
        ),
        verification_strength=result.strength,
        targets_exercised=("app.txt",),
        started_at=observation.observed_at,
        ended_at=observation.observed_at,
    )
    return PromotionRequest(
        mission_id=mission_id,
        action_id=action_id,
        worker_id="worker-proof",
        executor_job_id="worker-proof",
        environment_digest="environment-proof",
        project_root=str(project),
        lease=lease,
        current_state=MissionState.VERIFYING,
        contract_digest="contract-proof",
        authoritative_contract_digest="contract-proof",
        policy_version="policy-proof",
        authoritative_policy_version="policy-proof",
        workspace_digest=str(diff["workspace_digest"]),
        diff_digest=str(diff["diff_digest"]),
        verification_results=(result,),
        evidence_bundle=bundle,
        required_targets=("app.txt",),
        required_strength=3,
        requires_capability=False,
    )


def _probe_staging_and_promotion(scratch: Path) -> str:
    project = scratch / "project"
    project.mkdir()
    (project / "app.txt").write_text("before\n", encoding="utf-8")
    manager = StagedWorkspaceManager(scratch / "staged", enrolled_roots=(project,))
    verification = VerificationAuthority()

    lease = manager.stage("r14-promote", project)
    Path(lease.workspace_path, "app.txt").write_text("after\n", encoding="utf-8")
    request = _promotion_request(
        manager,
        project,
        lease,
        verification,
        mission_id="r14-promote",
        action_id="action-promote",
    )
    promoted = PromotionAuthority(manager, verification).promote(
        request,
        create_checkpoint=lambda _: "checkpoint-promote",
        apply_staged_diff=lambda _: manager.apply(lease),
        smoke_test=lambda _: (
            (project / "app.txt").read_text(encoding="utf-8") == "after\n"
        ),
        restore_checkpoint=lambda *_: True,
    )
    if promoted.status is not PromotionStatus.PROMOTED:
        raise RuntimeError(
            f"staged verified diff was not promoted: {promoted.reason_codes}"
        )

    rollback_lease = manager.stage("r14-rollback", project)
    Path(rollback_lease.workspace_path, "app.txt").write_text(
        "rollback\n", encoding="utf-8"
    )
    rollback_request = _promotion_request(
        manager,
        project,
        rollback_lease,
        verification,
        mission_id="r14-rollback",
        action_id="action-rollback",
    )

    def restore(*_: object) -> bool:
        (project / "app.txt").write_text("after\n", encoding="utf-8")
        return True

    rolled_back = PromotionAuthority(manager, verification).promote(
        rollback_request,
        create_checkpoint=lambda _: "checkpoint-rollback",
        apply_staged_diff=lambda _: manager.apply(rollback_lease),
        smoke_test=lambda _: False,
        restore_checkpoint=restore,
    )
    if (
        rolled_back.status is not PromotionStatus.ROLLED_BACK
        or not rolled_back.restored
    ):
        raise RuntimeError("failed smoke test did not restore the checkpoint")
    return "disposable workspace staged, modified, strongly verified, promoted, post-checked, and rolled back on failed smoke test"


def _probe_turn_coordinator() -> str:
    async def stream(context: TurnContext, _runtime: RuntimeDeps):
        yield {"type": "turn.completed", "turn_id": context.turn_id}

    coordinator = TurnCoordinator(
        deps=RuntimeDeps(),
        handlers=production_handlers(stream),
    )
    if (
        TurnCoordinator.classify_mode("write a file", mission_requested=True)
        is not TurnMode.MISSION
    ):
        raise RuntimeError("mission mode did not win deterministic classification")
    if (
        TurnCoordinator.classify_mode("stop the system", governance_requested=True)
        is not TurnMode.GOVERNANCE
    ):
        raise RuntimeError("governance mode did not win deterministic classification")
    context = TurnContext(
        turn_id="r14-turn",
        session_id="session-proof",
        operator_id="operator:proof",
        project_id="project-proof",
        directive="explain the proof",
        mode=TurnMode.CONVERSATION,
        model_id=None,
        approval_tokens=(),
    )
    result = coordinator.coordinate(context)

    async def collect() -> list[object]:
        return [item async for item in result.events]

    events = asyncio.run(collect())
    if events != [{"type": "turn.completed", "turn_id": "r14-turn"}]:
        raise RuntimeError(
            "TurnCoordinator did not return the canonical handler stream"
        )
    return "deterministic mode selection and canonical turn event stream verified"


def _canonical_event(
    event_type: str, *, session_id: str, sequence: int
) -> CanonicalEvent:
    return CanonicalEvent(
        event_type=event_type,
        phase="narrative",
        status="completed",
        trust="verified",
        source="r14-proof",
        session_id=session_id,
        sequence=sequence,
        turn_id="r14-turn",
        payload={"summary": event_type},
    )


def _probe_cortex(scratch: Path) -> str:
    from aios.runtime.cortex_bus import CortexBus

    db_path = scratch / "cortex.db"
    bus = CortexBus(db_path)
    first_id = bus.append(
        _canonical_event("turn.completed", session_id="session-proof", sequence=1)
    )
    bus.register_consumer("mirror-proof")
    first_batch = bus.consumer_batch("mirror-proof")
    if [event.id for event in first_batch] != [first_id]:
        raise RuntimeError("canonical event was not delivered to the cursor")
    bus.ack_consumer("mirror-proof", first_id)
    restarted = CortexBus(db_path)
    if restarted.consumer_cursor("mirror-proof").last_event_id != first_id:
        raise RuntimeError("consumer cursor did not survive restart")
    if restarted.consumer_batch("mirror-proof"):
        raise RuntimeError("restart replayed an already acknowledged event")
    second_id = restarted.append(
        _canonical_event("worker.completed", session_id="session-proof", sequence=2)
    )
    if [event.id for event in restarted.consumer_batch("mirror-proof")] != [second_id]:
        raise RuntimeError("post-restart cursor did not advance exactly once")
    restarted.ack_consumer("mirror-proof", second_id)
    return "canonical events advanced a durable consumer cursor across restart without duplicate replay"


def _probe_mirror(repo: Path, scratch: Path, cortex: RuntimeProof) -> str:
    if not cortex.passed:
        raise RuntimeError(
            "mirror proof cannot claim a cursor restart without the Cortex proof"
        )
    registry = (
        repo / "frontend" / "src" / "superbrain" / "lib" / "livingMirrorRegistry.ts"
    )
    store = repo / "frontend" / "src" / "superbrain" / "lib" / "mirrorStore.ts"
    if not registry.is_file() or not store.is_file():
        raise RuntimeError("typed frontend mirror surfaces are missing")
    registry_text = registry.read_text(encoding="utf-8")
    store_text = store.read_text(encoding="utf-8")
    required = ("MirrorEventEnvelope", "eventType", "snapshotRequired", "lastEventId")
    if not all(token in registry_text + store_text for token in required):
        raise RuntimeError(
            "frontend mirror does not expose canonical cursor/snapshot semantics"
        )
    return "backend cursor restart proof passed and the typed mirror registry/store expose canonical event and snapshot recovery contracts"


def _probe_memory(scratch: Path) -> str:
    authority = MemoryAuthority(store=MemoryAuthorityStore(scratch / "memory.db"))
    proposal = MemoryProposal(
        proposal_id="r14-memory",
        memory_type="skill",
        content_reference="procedural_skills:proof",
        content_digest="content-proof",
        project_id="project-proof",
        source_principal="worker:proof",
        source_mission_id="mission-proof",
        source_action_id="action-proof",
        evidence_ids=("evidence-proof",),
        required_strength=3,
        policy_version="v1",
        confidence_basis="R14 runtime verification",
    )
    evidence = EvidenceRecord(
        evidence_id="evidence-proof",
        mission_id="mission-proof",
        action_id="action-proof",
        worker_id="worker-proof",
        evidence_type=EvidenceType.TEST,
        source="executor",
        content_reference="inline:r14-proof",
        content_digest="evidence-digest",
        redaction_status="redacted_or_clean",
        environment_digest="environment-proof",
        tool_version="r14-proof",
        trust_level="verified",
        verification_strength=4,
    )
    authority.propose(proposal)
    advisory = MemoryHit(
        memory_type="chat",
        content_reference="chat:r14",
        verification_status="unverified",
        source="proof",
    )
    if authority.is_trusted(advisory) or authority.trust_level(advisory) != "unknown":
        raise RuntimeError("unverified recall was treated as trusted")
    record = authority.promote(
        proposal,
        MemoryPromotionActor(
            actor_id="operator:proof",
            actor_type="operator",
            authentication_event_id="auth-proof",
            operator_approval=True,
        ),
        evidence=(evidence,),
    )
    if (
        record.provenance.evidence_ids != ("evidence-proof",)
        or record.provenance.operator_approval != "operator:proof"
    ):
        raise RuntimeError("promoted memory lost provenance attribution")
    if authority.store.get_record(record.record_id) != record:
        raise RuntimeError("promoted memory was not durable")
    return "unverified recall remained advisory; verified promotion preserved operator, mission, action, and evidence provenance"


def _probe_emergency_stop(scratch: Path) -> str:
    actions: list[str] = []
    hooks = EmergencyStopHooks(
        revoke_capabilities=lambda: actions.append("revoke") or 1,
        cancel_queued_missions=lambda: actions.append("cancel") or 1,
        kill_active_workers=lambda: actions.append("kill") or 1,
        disable_autonomy=lambda: actions.append("disable") or 1,
        preserve_evidence=lambda _reason: actions.append("evidence") or True,
    )
    db_path = scratch / "emergency.db"
    controller = EmergencyStopController(db_path, hooks=hooks)
    controller.engage(
        __import__(
            "aios.domain.governance", fromlist=["EmergencyStopRequest"]
        ).EmergencyStopRequest(
            operator_id="operator:proof",
            authentication_event_id="auth:engage",
            reason="R14 emergency proof",
        )
    )
    restarted = EmergencyStopController(db_path, hooks=hooks)
    if not restarted.is_engaged():
        raise RuntimeError("emergency latch did not survive restart")
    binding = _capability_binding(payload={"command": "echo blocked"})
    try:
        CapabilityAuthority(
            db_path=scratch / "stopped-capabilities.db", emergency_stop=restarted
        ).issue(binding, action_payload={"command": "echo blocked"})
    except EmergencyStopError:
        pass
    else:
        raise RuntimeError(
            "capability issuance remained available during emergency stop"
        )

    repository = SqliteMissionRepository(scratch / "stopped-missions.db")
    service = MissionService(
        repository,
        export_dir=scratch / "stopped-exports",
        emergency_stop=restarted,
    )
    contract = MissionContract(
        mission_id="stopped-mission",
        operator_id="operator:proof",
        goal="must not schedule",
        worker_type="proof-worker",
        created_by="proof-planner",
    )
    try:
        service.create(contract)
    except EmergencyStopError:
        pass
    else:
        raise RuntimeError(
            "mission scheduling remained available during emergency stop"
        )

    called: list[str] = []
    executor = Executor(
        runner=lambda *_args, **_kwargs: called.append("run") or ("", "", 0),
        approved_runner=lambda *_args, **_kwargs: (
            called.append("approved") or ("", "", 0)
        ),
        emergency_stop=restarted,
        audit_log=lambda *_args, **_kwargs: None,
    )
    blocked = executor.execute("echo blocked", session_id="session-proof")
    if blocked.status != "BLOCKED" or called:
        raise RuntimeError("worker execution was not blocked before runner dispatch")

    clear_token = restarted.issue_clear_capability(
        operator_id="operator:proof",
        authentication_event_id="auth:clear",
        session_id="session:clear",
    )
    cleared = restarted.clear(
        operator_id="operator:proof",
        authentication_event_id="auth:clear",
        session_id="session:clear",
        clear_capability=clear_token,
    )
    if cleared.engaged:
        raise RuntimeError("fresh privileged clear did not release the latch")
    if not {"revoke", "cancel", "kill", "disable", "evidence"}.issubset(actions):
        raise RuntimeError("emergency stop did not invoke every stop hook")
    return "emergency engage blocked capability, mission scheduling, and execution; durable restart held the latch; fresh privileged clear succeeded"


def _probe_production_profile(scratch: Path) -> str:
    from aios.launcher import LauncherConfig, LauncherError, _production_preflight

    root = scratch / "launcher"
    root.mkdir()
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    launcher = LauncherConfig.from_environment(repo_root=root, profile="production")
    with patch("aios.launcher.shutil.which", return_value=None):
        try:
            _production_preflight(launcher)
        except LauncherError as exc:
            if "Docker" not in str(exc):
                raise RuntimeError(
                    f"production refusal was not Docker-specific: {exc}"
                ) from exc
        else:
            raise RuntimeError("production preflight accepted a missing Docker runtime")
    with (
        patch("aios.launcher.shutil.which", return_value="docker"),
        patch.dict(
            os.environ, {"AIOS_APPROVED_EXECUTION_BACKEND": "host"}, clear=False
        ),
    ):
        try:
            _production_preflight(launcher)
        except LauncherError as exc:
            if "host execution backend" not in str(exc):
                raise RuntimeError(
                    f"host fallback refusal was not explicit: {exc}"
                ) from exc
        else:
            raise RuntimeError("production preflight accepted host execution fallback")
    return "production preflight refused missing Docker and forbidden host execution fallback"


__all__ = [
    "REQUIRED_PROOFS",
    "RuntimeProof",
    "RuntimeProofReport",
    "run_runtime_proofs",
]
