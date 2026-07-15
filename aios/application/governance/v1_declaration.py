"""Evidence-backed readiness declaration for the GAGOS v1 boundary."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseGate:
    name: str
    source_present: bool
    runtime_proven: bool
    evidence: str
    blocking: bool = True

    @property
    def passed(self) -> bool:
        """Return whether this gate is safe to count for production readiness.

        Source presence is deliberately insufficient.  A gate becomes passed
        only after its runtime behavior has also been proven.
        """
        return self.source_present and self.runtime_proven

    @property
    def status(self) -> str:
        if self.passed:
            return "VERIFIED"
        if self.source_present:
            return "PARTIAL"
        return "BLOCKED"


@dataclass(frozen=True, slots=True)
class V1ReleaseDeclaration:
    version: str
    profile: str
    ready: bool
    gates: tuple[ReleaseGate, ...]
    generated_at: str

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(
            gate.name for gate in self.gates if gate.blocking and not gate.passed
        )

    @property
    def partials(self) -> tuple[str, ...]:
        return tuple(
            gate.name
            for gate in self.gates
            if gate.blocking and gate.source_present and not gate.runtime_proven
        )

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["gates"] = [
            {**asdict(gate), "passed": gate.passed, "status": gate.status}
            for gate in self.gates
        ]
        payload["failures"] = list(self.failures)
        payload["partials"] = list(self.partials)
        return payload


def _gate(
    name: str,
    root: Path,
    required: tuple[str, ...],
    evidence: str,
    *,
    runtime_proven: bool,
) -> ReleaseGate:
    missing = [path for path in required if not (root / path).exists()]
    if missing:
        return ReleaseGate(
            name=name,
            source_present=False,
            runtime_proven=False,
            evidence=f"source missing: {', '.join(missing)}",
        )
    if runtime_proven:
        return ReleaseGate(
            name=name,
            source_present=True,
            runtime_proven=True,
            evidence=f"{evidence}; runtime proof supplied",
        )
    return ReleaseGate(
        name=name,
        source_present=True,
        runtime_proven=False,
        evidence=f"{evidence}; source present, runtime proof unavailable",
    )


def evaluate_release(
    root: str | Path | None = None,
    *,
    profile: str = "production",
    executor_available: bool | None = None,
    runtime_proofs: Mapping[str, bool] | None = None,
) -> V1ReleaseDeclaration:
    """Evaluate source evidence separately from production runtime proof.

    ``runtime_proofs`` is intentionally explicit and defaults to empty.  A
    file, import, or directory can establish ``source_present`` but can never
    establish ``runtime_proven`` by itself.
    """
    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    selected_profile = profile.strip().lower()
    supplied_runtime_proofs = dict(runtime_proofs or {})
    if executor_available is None:
        executor_available = shutil.which("docker") is not None
    gates = (
        _gate(
            "operator_identity",
            repo,
            (
                "aios/domain/identity/__init__.py",
                "aios/application/identity/__init__.py",
                "aios/infrastructure/identity/__init__.py",
            ),
            "durable Human Sovereign identity layers are shipped",
            runtime_proven=supplied_runtime_proofs.get("operator_identity", False),
        ),
        _gate(
            "exact_capabilities",
            repo,
            (
                "aios/domain/capabilities/__init__.py",
                "aios/domain/capabilities/contracts.py",
                "aios/domain/capabilities/digest.py",
                "aios/application/capabilities/__init__.py",
                "aios/application/capabilities/authority.py",
                "aios/application/capabilities/verifier.py",
                "aios/infrastructure/capabilities/__init__.py",
                "aios/infrastructure/capabilities/sqlite_store.py",
            ),
            "exact single-use capability layers are shipped",
            runtime_proven=supplied_runtime_proofs.get("exact_capabilities", False),
        ),
        _gate(
            "isolated_executor",
            repo,
            ("aios/executor_service.py", "Dockerfile.executor"),
            "private executor service and non-root executor image are shipped",
            runtime_proven=supplied_runtime_proofs.get("isolated_executor", False),
        ),
        ReleaseGate(
            name="executor_runtime_available",
            source_present=True,
            runtime_proven=bool(executor_available),
            evidence=(
                "Docker executable is available"
                if executor_available
                else "Docker executable is unavailable"
            ),
        ),
        _gate(
            "staged_workspaces",
            repo,
            ("aios/application/workspaces/staged.py",),
            "promotion starts from a collision-safe staged workspace",
            runtime_proven=supplied_runtime_proofs.get("staged_workspaces", False),
        ),
        _gate(
            "verification_and_recovery",
            repo,
            (
                "aios/application/evidence/verification.py",
                "aios/application/promotion/authority.py",
            ),
            "verification and checkpoint-bound promotion authorities are shipped",
            runtime_proven=supplied_runtime_proofs.get(
                "verification_and_recovery", False
            ),
        ),
        _gate(
            "promotion_authority",
            repo,
            ("aios/application/promotion/authority.py",),
            "atomic promotion authority is shipped",
            runtime_proven=supplied_runtime_proofs.get("promotion_authority", False),
        ),
        _gate(
            "turn_coordinator",
            repo,
            ("aios/application/turns/turn_coordinator.py",),
            "production turns use the canonical TurnCoordinator",
            runtime_proven=supplied_runtime_proofs.get("turn_coordinator", False),
        ),
        _gate(
            "cortex_consumer_cursors",
            repo,
            ("aios/runtime/cortex_bus.py",),
            "durable Cortex consumer cursor implementation is shipped",
            runtime_proven=supplied_runtime_proofs.get(
                "cortex_consumer_cursors", False
            ),
        ),
        _gate(
            "truthful_mirror",
            repo,
            (
                "frontend/src/superbrain/lib/livingMirrorRegistry.ts",
                "frontend/src/superbrain/lib/mirrorStore.ts",
            ),
            "typed canonical-event reaction registry is shipped",
            runtime_proven=supplied_runtime_proofs.get("truthful_mirror", False),
        ),
        _gate(
            "memory_provenance",
            repo,
            (
                "aios/application/memory/authority.py",
                "aios/infrastructure/storage/migrations/0002_memory_provenance.py",
            ),
            "memory authority and provenance migration are shipped",
            runtime_proven=supplied_runtime_proofs.get("memory_provenance", False),
        ),
        _gate(
            "emergency_stop_controller",
            repo,
            (
                "aios/application/governance/emergency_stop.py",
                "aios/infrastructure/storage/migrations/0003_emergency_stop.py",
            ),
            "durable emergency latch with five explicit stop hooks is shipped",
            runtime_proven=supplied_runtime_proofs.get(
                "emergency_stop_controller", False
            ),
        ),
        _gate(
            "production_profile_fail_closed",
            repo,
            ("aios/launcher.py", "Dockerfile.frontend", "gateway/nginx.conf"),
            "production launcher refuses missing Docker and host fallback",
            runtime_proven=supplied_runtime_proofs.get(
                "production_profile_fail_closed", False
            ),
        ),
        ReleaseGate(
            name="production_profile_selected",
            source_present=True,
            runtime_proven=selected_profile == "production",
            evidence=(
                "production profile selected"
                if selected_profile == "production"
                else f"profile is {selected_profile}"
            ),
        ),
    )
    ready = all(gate.passed for gate in gates if gate.blocking)
    return V1ReleaseDeclaration(
        version="1.0.0-prototype",
        profile=selected_profile,
        ready=ready,
        gates=gates,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


__all__ = ["ReleaseGate", "V1ReleaseDeclaration", "evaluate_release"]
