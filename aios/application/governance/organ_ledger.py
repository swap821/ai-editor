"""Organ Truth Ledger: the authoritative catalog of the 54 GAGOS organs.

Slice 25 of the GAGOS Completion Plan (Slices 25-40) establishes this ledger
as the release-conformance baseline.  It intentionally does not re-litigate
work already proven in the Slices 0-24 convergence wave (see
``.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md``); it records which of the 54
organs are green today and lists the 32 organs the remaining 15 slices must
close, each starting from a truthful blocker rather than an optimistic claim.

``validate_ledger`` is the single place allowed to decide whether a ledger is
conformant.  A ``status="green"`` claim is never taken at face value: it must
carry tests, and where ``requires_live_evidence`` is set, live (not fixture)
evidence stamped with the exact commit under evaluation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.domain.governance.contracts import OrganRecord

#: Keyword markers a frontend-facing organ's own tests must demonstrate when
#: `requires_frontend_error_states` is set -- a heuristic presence check
#: (it proves the right test names exist, not that they are well-written),
#: matching the standing rule that a section must never silently present
#: missing/unreachable data as healthy.
_FRONTEND_UNAVAILABLE_MARKERS: tuple[str, ...] = ("unavailable",)
_FRONTEND_ERROR_CLASS_MARKERS: tuple[str, ...] = ("error", "stale", "disconnected")

REQUIRED_ORGAN_COUNT = 54

#: organ_id -> canonical (name, authority_owner). This is the single source
#: of truth for "which 54 organs exist"; a ledger record whose (id, name)
#: pair does not match this registry is an unknown organ.
CANONICAL_ORGANS: Mapping[int, tuple[str, str]] = {
    1: ("Security Gateway", "SecurityGatewayAuthority"),
    2: ("Scope Lock", "ScopeLockAuthority"),
    3: ("Secret Scanner", "SecretScannerAuthority"),
    4: ("Tamper-Evident Audit Logger", "AuditLoggerAuthority"),
    5: ("Prompt Injection Shield", "InjectionShieldAuthority"),
    6: ("Edge Trust Boundary", "EdgeTrustAuthority"),
    7: ("Policy Kernel", "PolicyKernelAuthority"),
    8: ("Action Broker", "ActionBrokerAuthority"),
    9: ("Exact Capability Authority", "CapabilityAuthority"),
    10: ("Mission Authority", "MissionAuthority"),
    11: ("Turn Coordinator", "TurnCoordinatorAuthority"),
    12: ("Worker Foundry", "WorkerFoundryAuthority"),
    13: ("Isolated Executor Service (construction)", "ExecutorServiceAuthority"),
    14: ("Staged Workspace Manager (construction)", "StagedWorkspaceAuthority"),
    15: ("Evidence and Verification Authority (construction)", "VerificationAuthority"),
    16: ("Promotion Authority (construction)", "PromotionAuthority"),
    17: ("Cortex Observation Bus", "CortexBusAuthority"),
    18: ("Memory Authority (construction)", "MemoryAuthority"),
    19: ("Emergency Stop Controller (construction)", "EmergencyStopController"),
    20: ("Living Mirror Reaction Registry (construction)", "LivingMirrorAuthority"),
    21: ("Queen Council Orchestrator", "QueenCouncilAuthority"),
    22: ("V1 Release Declaration (gagos v1-check)", "ReleaseDeclarationAuthority"),
    23: ("Release Conformance Organ", "ReleaseConformanceAuthority"),
    24: ("Human Sovereign Identity", "IdentityAuthority"),
    25: ("Constitutional Kernel", "ConstitutionalKernelAuthority"),
    26: (
        "Emergency Stop Organ (full boundary hard-wiring)",
        "EmergencyStopHardWiringAuthority",
    ),
    27: ("Operator Taste Model", "OperatorTasteModelAuthority"),
    28: ("Project Understanding Organ", "ProjectUnderstandingAuthority"),
    29: ("Correction and Interpretation-Lineage Organ", "CorrectionLineageAuthority"),
    30: ("Communication and Human-State Interpreter", "HumanStateInterpreterAuthority"),
    31: (
        "Human Representative Context Compiler",
        "RepresentativeContextCompilerAuthority",
    ),
    32: ("Universal Intelligence Gateway", "UniversalIntelligenceGatewayAuthority"),
    33: ("Model Registry and Capability Passport", "ModelPassportAuthority"),
    34: ("Cloud Budget and Provider-Health Organ", "ProviderHealthBudgetAuthority"),
    35: ("Local Clerk Runtime", "LocalClerkRuntimeAuthority"),
    36: ("Clerical Job Contract and Dispatcher", "ClerkDispatcherAuthority"),
    37: ("Local Model Qualification and Health", "LocalModelQualificationAuthority"),
    38: (
        "Durable Local-Clerk Provenance and Continuity Organ",
        "ClerkProvenanceAuthority",
    ),
    39: ("Multi-Model Deliberation and Dissent Organ", "DeliberationCouncilAuthority"),
    40: (
        "Isolated Workspace and Executor (live proof)",
        "IsolatedExecutorLiveAuthority",
    ),
    41: (
        "Promotion, Checkpoint and Rollback (live proof)",
        "PromotionRollbackLiveAuthority",
    ),
    42: ("Recovery and Resumption", "RecoveryResumptionAuthority"),
    43: ("Local Skill Reuse, Confidence and Demotion", "SkillLifecycleAuthority"),
    44: ("Golden Mission and Endurance Evaluation", "GoldenMissionEnduranceAuthority"),
    45: ("Constitutional Amendment Authority", "ConstitutionalAmendmentAuthority"),
    46: ("Constitutional Learning Organ", "ConstitutionalLearningAuthority"),
    47: ("Read-Model and Projection Organ", "ReadModelProjectionAuthority"),
    48: ("Truthful Living Mirror (full truthful UI)", "TruthfulMirrorAuthority"),
    49: ("Approval and Decision Surface", "ApprovalDecisionSurfaceAuthority"),
    50: ("Provenance and Explanation Surface", "ProvenanceExplanationSurfaceAuthority"),
    51: (
        "Sovereign Control and Heartbeat Surface",
        "SovereignHeartbeatSurfaceAuthority",
    ),
    52: ("Observability and Health Organ", "ObservabilityAuthority"),
    53: (
        "Installation, Configuration and Key Authority",
        "InstallationConfigurationAuthority",
    ),
    54: ("Backup and Disaster-Recovery Organ", "BackupDisasterRecoveryAuthority"),
}

#: The 32 organs Slices 26-40 must close. Kept separate from CANONICAL_ORGANS
#: so conformance tests can assert this set without re-deriving it from status.
TARGET_ORGAN_IDS: tuple[int, ...] = tuple(range(23, 55))


def _default_ledger_path(root: Path) -> Path:
    return root / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"


def current_commit_sha(root: str | Path) -> str | None:
    """Return the exact commit under evaluation, or None outside a git checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def load_ledger(path: str | Path) -> tuple[OrganRecord, ...]:
    """Load and parse the ledger file. Raises on malformed JSON or schema."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("organ ledger must be a JSON array of organ records")
    return tuple(OrganRecord.model_validate(entry) for entry in raw)


@dataclass(frozen=True, slots=True)
class OrganLedgerReport:
    total_organs: int
    green_count: int
    yellow_count: int
    violations: tuple[str, ...]
    generated_at: str

    @property
    def conformant(self) -> bool:
        return not self.violations

    @property
    def all_green(self) -> bool:
        return self.conformant and self.yellow_count == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "total_organs": self.total_organs,
            "green_count": self.green_count,
            "yellow_count": self.yellow_count,
            "violations": list(self.violations),
            "conformant": self.conformant,
            "all_green": self.all_green,
            "generated_at": self.generated_at,
        }


def _frontend_error_state_coverage(record: OrganRecord, repo_root: Path) -> bool:
    """Best-effort keyword check: do this organ's own test files demonstrate
    both an "unavailable" case and a distinct error/stale/disconnected case?
    Presence of the right test names is not proof the tests are meaningful --
    it is a floor beneath which a claim is definitely not backed by anything,
    not a ceiling on real coverage quality."""
    combined_text = ""
    for rel_path in (*record.focused_tests, *record.integration_tests):
        try:
            combined_text += (repo_root / rel_path).read_text(
                encoding="utf-8", errors="ignore"
            ).lower() + "\n"
        except OSError:
            continue
    has_unavailable = any(m in combined_text for m in _FRONTEND_UNAVAILABLE_MARKERS)
    has_error_class = any(m in combined_text for m in _FRONTEND_ERROR_CLASS_MARKERS)
    return has_unavailable and has_error_class


def validate_ledger(
    records: Sequence[OrganRecord],
    *,
    current_sha: str | None = None,
    repo_root: str | Path | None = None,
    strict_last_verified: bool = False,
) -> tuple[str, ...]:
    """Return a tuple of truthful violation descriptions; empty means conformant.

    ``current_sha`` is the exact commit the ledger is being evaluated against.
    When supplied, live evidence stamped with any other commit is rejected --
    evidence proven at an old tip is not proof for the tip under test.

    ``repo_root``, when supplied, additionally proves every referenced
    ``production_entrypoints``/``focused_tests``/``integration_tests`` path
    actually exists on disk (a claim pointing at a file that was never
    written or was since deleted is exactly as dishonest as no claim at all),
    and checks ``requires_frontend_error_states`` organs for real test-file
    keyword coverage.

    ``strict_last_verified`` is the release-tagging-time gate (Organ 23's
    own job, not every ordinary commit's): when set, every green organ's
    ``last_verified_sha`` must equal ``current_sha`` exactly -- a full
    re-verification pass immediately before a tag, not a rule that should
    fire on every unrelated commit touching organs nobody re-verified today.
    """
    violations: list[str] = []
    root = Path(repo_root) if repo_root is not None else None

    seen_ids: dict[int, OrganRecord] = {}
    for record in records:
        if record.organ_id in seen_ids:
            violations.append(f"duplicate organ_id {record.organ_id}")
        else:
            seen_ids[record.organ_id] = record

    expected_ids = set(range(1, REQUIRED_ORGAN_COUNT + 1))
    present_ids = set(seen_ids)
    for missing_id in sorted(expected_ids - present_ids):
        violations.append(f"missing organ_id {missing_id}")
    for unknown_id in sorted(present_ids - expected_ids):
        violations.append(f"unknown organ_id {unknown_id} (outside 1..54)")

    for organ_id, record in seen_ids.items():
        if organ_id not in CANONICAL_ORGANS:
            continue
        canonical_name, canonical_owner = CANONICAL_ORGANS[organ_id]
        if record.name != canonical_name:
            violations.append(
                f"unknown organ: organ_id {organ_id} has name {record.name!r}, "
                f"expected {canonical_name!r}"
            )
        if record.authority_owner != canonical_owner:
            violations.append(
                f"organ_id {organ_id} has authority_owner "
                f"{record.authority_owner!r}, expected {canonical_owner!r}"
            )

    owners_seen: dict[str, int] = {}
    for record in records:
        if record.authority_owner in owners_seen:
            violations.append(
                f"duplicate authority owner {record.authority_owner!r} "
                f"on organ_id {record.organ_id} and {owners_seen[record.authority_owner]}"
            )
        else:
            owners_seen[record.authority_owner] = record.organ_id

    if root is not None:
        for record in records:
            for field_name in (
                "production_entrypoints",
                "focused_tests",
                "integration_tests",
            ):
                for rel_path in getattr(record, field_name):
                    if not (root / rel_path).exists():
                        violations.append(
                            f"organ_id {record.organ_id} ({record.name}) references "
                            f"{field_name} path {rel_path!r}, which does not exist"
                        )

    for record in records:
        if record.status != "green":
            continue
        if not record.focused_tests:
            violations.append(
                f"organ_id {record.organ_id} ({record.name}) is green without tests"
            )
        if not record.integration_tests:
            violations.append(
                f"organ_id {record.organ_id} ({record.name}) is green without "
                "integration tests"
            )
        if record.known_blockers:
            violations.append(
                f"organ_id {record.organ_id} ({record.name}) is green but still "
                f"lists known_blockers: {list(record.known_blockers)!r}"
            )
        if strict_last_verified and record.last_verified_sha != current_sha:
            violations.append(
                f"organ_id {record.organ_id} ({record.name}) is green but "
                f"last_verified_sha {record.last_verified_sha!r} does not match "
                f"the evaluated commit {current_sha!r}"
            )
        if record.requires_live_evidence:
            if not record.live_evidence:
                violations.append(
                    f"organ_id {record.organ_id} ({record.name}) is green and "
                    "requires live evidence, but none is present"
                )
            for evidence in record.live_evidence:
                if evidence.proof_level != "live":
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) requires live "
                        f"evidence but evidence is labelled {evidence.proof_level!r}"
                    )
                if current_sha is not None and evidence.commit_sha != current_sha:
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) has evidence "
                        f"from commit {evidence.commit_sha!r}, not the evaluated "
                        f"commit {current_sha!r}"
                    )
        if root is not None and record.requires_frontend_error_states:
            if not _frontend_error_state_coverage(record, root):
                violations.append(
                    f"organ_id {record.organ_id} ({record.name}) is a frontend-facing "
                    "green organ but its own test files show no unavailable/error/"
                    "stale-state coverage"
                )

    return tuple(violations)


def evaluate_organs(
    root: str | Path | None = None,
    *,
    ledger_path: str | Path | None = None,
    current_sha: str | None = None,
    strict_last_verified: bool = False,
) -> OrganLedgerReport:
    repo = Path(root or Path(__file__).resolve().parents[3]).resolve()
    path = Path(ledger_path) if ledger_path is not None else _default_ledger_path(repo)
    records = load_ledger(path)
    resolved_sha = current_sha if current_sha is not None else current_commit_sha(repo)
    violations = validate_ledger(
        records,
        current_sha=resolved_sha,
        repo_root=repo,
        strict_last_verified=strict_last_verified,
    )
    green_count = sum(1 for record in records if record.status == "green")
    yellow_count = sum(1 for record in records if record.status == "yellow")
    return OrganLedgerReport(
        total_organs=len(records),
        green_count=green_count,
        yellow_count=yellow_count,
        violations=violations,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def validate_manifest(
    manifest: Mapping[str, object],
    records: Sequence[OrganRecord],
    *,
    repo_root: str | Path,
    current_sha: str | None = None,
) -> tuple[str, ...]:
    """Return a tuple of truthful violation descriptions for a release
    manifest; empty means the manifest is an honest, current hash-pin of
    *records* and the files it claims to cover.

    Every check here is deliberately continuous (true on every commit, not
    only at release-tagging time): a manifest that drifts from the ledger it
    claims to pin, or from the files it claims to hash, is never a valid
    state to ship regardless of which commit produced it.
    """
    violations: list[str] = []
    root = Path(repo_root)

    expected_summary = {
        "total": len(records),
        "green": sum(1 for record in records if record.status == "green"),
        "yellow": sum(1 for record in records if record.status == "yellow"),
    }
    if manifest.get("organ_summary") != expected_summary:
        violations.append(
            f"manifest organ_summary {manifest.get('organ_summary')!r} does not "
            f"match the ledger's actual computed counts {expected_summary!r} -- "
            "organ counts must never be handwritten"
        )

    ledger_rel_path = manifest.get("ledger_path")
    if isinstance(ledger_rel_path, str) and ledger_rel_path:
        ledger_file = root / ledger_rel_path
        if ledger_file.exists():
            actual_ledger_hash = hashlib.sha256(ledger_file.read_bytes()).hexdigest()
            if manifest.get("ledger_sha256") != actual_ledger_hash:
                violations.append(
                    f"manifest ledger_sha256 {manifest.get('ledger_sha256')!r} does "
                    f"not match the actual ledger file hash {actual_ledger_hash!r} "
                    "-- the ledger changed since the manifest was last generated"
                )
        else:
            violations.append(
                f"manifest ledger_path {ledger_rel_path!r} does not exist"
            )
    else:
        violations.append("manifest is missing a non-empty ledger_path")

    if current_sha is not None and manifest.get("source_commit_sha") != current_sha:
        violations.append(
            f"manifest source_commit_sha {manifest.get('source_commit_sha')!r} does "
            f"not match the evaluated commit {current_sha!r} -- the manifest was not "
            "regenerated at this commit"
        )

    files = manifest.get("files")
    if isinstance(files, dict) and files:
        for rel_path, expected_hash in files.items():
            file_path = root / str(rel_path)
            if not file_path.exists():
                violations.append(f"manifest references missing file {rel_path!r}")
                continue
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                violations.append(
                    f"manifest hash for {rel_path!r} is stale: recorded "
                    f"{expected_hash!r}, actual file hash is {actual_hash!r}"
                )
    else:
        violations.append("manifest is missing a non-empty 'files' hash map")

    return tuple(violations)


__all__ = [
    "CANONICAL_ORGANS",
    "TARGET_ORGAN_IDS",
    "REQUIRED_ORGAN_COUNT",
    "OrganLedgerReport",
    "current_commit_sha",
    "load_ledger",
    "validate_ledger",
    "validate_manifest",
    "evaluate_organs",
]
