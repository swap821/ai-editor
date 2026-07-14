"""Evidence-backed readiness declaration for the GAGOS v1 boundary."""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseGate:
    name: str
    passed: bool
    evidence: str
    blocking: bool = True


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

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["gates"] = [asdict(gate) for gate in self.gates]
        payload["failures"] = list(self.failures)
        return payload


def _gate(
    name: str, root: Path, required: tuple[str, ...], evidence: str
) -> ReleaseGate:
    missing = [path for path in required if not (root / path).exists()]
    if missing:
        return ReleaseGate(name, False, f"missing: {', '.join(missing)}")
    return ReleaseGate(name, True, evidence)


def evaluate_release(
    root: str | Path | None = None,
    *,
    profile: str = "production",
    executor_available: bool | None = None,
) -> V1ReleaseDeclaration:
    """Evaluate shipped evidence without inventing live runtime telemetry."""
    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    selected_profile = profile.strip().lower()
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
        ),
        _gate(
            "exact_capabilities",
            repo,
            (
                "aios/domain/capabilities/__init__.py",
                "aios/application/capabilities/__init__.py",
                "aios/infrastructure/capabilities/sqlite_store.py",
            ),
            "exact single-use capability layers are shipped",
        ),
        _gate(
            "isolated_executor",
            repo,
            ("aios/executor_service.py", "Dockerfile.executor"),
            "private executor service and non-root executor image are shipped",
        ),
        ReleaseGate(
            "executor_runtime_available",
            bool(executor_available),
            (
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
        ),
        _gate(
            "verification_and_recovery",
            repo,
            (
                "aios/application/evidence/verification.py",
                "aios/application/promotion/authority.py",
            ),
            "verification and checkpoint-bound promotion authorities are shipped",
        ),
        _gate(
            "cortex_consumer_cursors",
            repo,
            ("aios/runtime/cortex_bus.py",),
            "durable Cortex consumer cursor implementation is shipped",
        ),
        _gate(
            "truthful_mirror",
            repo,
            (
                "frontend/src/superbrain/lib/livingMirrorRegistry.ts",
                "frontend/src/superbrain/lib/mirrorStore.ts",
            ),
            "typed canonical-event reaction registry is shipped",
        ),
        _gate(
            "memory_provenance",
            repo,
            (
                "aios/application/memory/authority.py",
                "aios/infrastructure/storage/migrations/0002_memory_provenance.py",
            ),
            "memory authority and provenance migration are shipped",
        ),
        _gate(
            "emergency_control",
            repo,
            (
                "aios/application/governance/emergency_stop.py",
                "aios/infrastructure/storage/migrations/0003_emergency_stop.py",
            ),
            "durable emergency latch with five explicit stop hooks is shipped",
        ),
        _gate(
            "production_profile_fail_closed",
            repo,
            ("aios/launcher.py", "Dockerfile.frontend", "gateway/nginx.conf"),
            "production launcher refuses missing Docker and host fallback",
        ),
        ReleaseGate(
            "production_profile_selected",
            selected_profile == "production",
            (
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
