"""Organ Truth Ledger: the authoritative catalog of the 55 GAGOS organs.

Slice 25 of the GAGOS Completion Plan (Slices 25-40) establishes this ledger
as the release-conformance baseline.  It intentionally does not re-litigate
work already proven in the Slices 0-24 convergence wave (see
``.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md``); it records which of the 54
organs are green today and lists the 32 organs the remaining 15 slices must
close, each starting from a truthful blocker rather than an optimistic claim.

``validate_ledger`` is the single place allowed to decide whether a ledger is
conformant.  A ``status="green"`` claim is never taken at face value: it must
carry tests, and where ``requires_live_evidence`` is set, live (not fixture)
evidence stamped at the commit the organ claims verification at
(``last_verified_sha``), which the tip gate separately requires to be an
ancestor of HEAD.  Evidence from earlier commits is kept as record and proves
nothing on its own.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aios.application.governance import spine_release
from aios.domain.governance.contracts import OrganRecord

#: Keyword markers a frontend-facing organ's own tests must demonstrate when
#: `requires_frontend_error_states` is set -- a heuristic presence check
#: (it proves the right test names exist, not that they are well-written),
#: matching the standing rule that a section must never silently present
#: missing/unreachable data as healthy.
_FRONTEND_UNAVAILABLE_MARKERS: tuple[str, ...] = ("unavailable",)
_FRONTEND_ERROR_CLASS_MARKERS: tuple[str, ...] = ("error", "stale", "disconnected")

#: Phase 4 absolute (2026-07-31): live evidence must be re-checkable, and
#: organs without live evidence must name one precise Outside/Docker/Ollama/
#: Phase-6/frozen/browser residual — never silence.
_LIVE_COMMIT_SHA = re.compile(r"\A[0-9a-f]{40}\Z")
_LIVE_RECHECKABLE = re.compile(
    r"release/phase4/|TestClient|rp\._probe|https?://|command=`|"
    r"scripts/phase4_live_evidence\.py|actions/runs/\d+|CI run \d+|"
    r"docker-compose|test_executor_integration",
    re.IGNORECASE,
)
_PHASE4_NAMED_REASON = re.compile(
    r"frozen spine|Phase 6 gate|no Ollama|Outside-machine|browser-session|"
    r"Phase 4 absolute residual|no Docker",
    re.IGNORECASE,
)

REQUIRED_ORGAN_COUNT = 55

#: The 12-condition green contract (artifactplan.md Phase 5). Written
#: per-organ verdicts must use these keys (C1..C12). Mechanical checks
#: cover an enforceable subset; prose covers the rest.
GREEN_CONTRACT_CONDITIONS: Mapping[str, str] = {
    "C1": "Named authority owner is a real class in production_entrypoints (Decision A)",
    "C2": "A real API/mission/runtime path invokes the owner (not construct-in-test alone)",
    "C3": "Durable state survives process restart (or N/A-BY-DESIGN with cite)",
    "C4": "Tamper-evidence / integrity chain (or N/A-BY-DESIGN with cite)",
    "C5": "Fail-safe reporting: unavailable rather than a plausible zero",
    "C6": "Focused tests exist and referenced paths resolve on disk",
    "C7": "Integration tests exist and referenced paths resolve on disk",
    "C8": "Frontend error/unavailable/stale coverage when requires_frontend_error_states",
    "C9": "No residual known_blockers when claiming green",
    "C10": "Live evidence stamped at a verified commit, or named Outside residual when yellow",
    "C11": "last_verified_sha records the exact tested commit",
    "C12": "CI verifies that commit (ancestor of HEAD on ordinary CI; exact tip at release)",
}
REQUIRED_CONDITION_VERDICT_KEYS: tuple[str, ...] = tuple(f"C{i}" for i in range(1, 13))

#: organ_id -> canonical (name, authority_owner). This is the single source
#: of truth for "which 55 organs exist"; a ledger record whose (id, name)
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
    55: (
        "Governance Conformance Evaluation (Refusal Reel)",
        "GovernanceConformanceAuthority",
    ),
}

#: The 32 organs Slices 26-40 must close. Kept separate from CANONICAL_ORGANS
#: so conformance tests can assert this set without re-deriving it from status.
TARGET_ORGAN_IDS: tuple[int, ...] = tuple(range(23, 55))

#: The security spine is RED/frozen by the repository contract. Its five
#: production entrypoint modules cannot be edited merely to satisfy Decision A;
#: they must remain yellow until the controlled self-modification process has
#: been completed by an authorized human.
FROZEN_SECURITY_ORGAN_IDS: frozenset[int] = frozenset(range(1, 6))


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


def _git_ok(root: Path, *args: str) -> bool:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def sha_is_ancestor_of_head(root: str | Path, sha: str) -> bool | None:
    """Return True/False when git can answer; None when ancestry is unknowable.

    Shallow checkouts (or missing objects) make ancestry unknowable — callers
    must not treat that as a pass or a failure of the ledger itself.
    """
    repo = Path(root)
    if not _LIVE_COMMIT_SHA.fullmatch(sha):
        return False
    if not _git_ok(repo, "rev-parse", "--is-inside-work-tree"):
        return None
    if not _git_ok(repo, "cat-file", "-e", f"{sha}^{{commit}}"):
        return None
    return _git_ok(repo, "merge-base", "--is-ancestor", sha, "HEAD")


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


def _authority_owner_is_class_reference(record: OrganRecord, repo_root: Path) -> bool:
    """Decision A (2026-07-27, see docs/architecture/GAGOS_54_ORGANS.md): a
    non-frozen organ's `authority_owner` must name a real class defined
    somewhere in that
    organ's own `production_entrypoints` -- not merely a string that happens to
    match `CANONICAL_ORGANS`. Matches both Python (`class Foo`) and TypeScript/
    JS (`export class Foo`) class-definition syntax; a name that only appears in
    a comment or string is a false positive this heuristic accepts, the same
    tradeoff already made by `_frontend_error_state_coverage` below."""
    pattern = re.compile(rf"\bclass\s+{re.escape(record.authority_owner)}\b")
    for rel_path in record.production_entrypoints:
        try:
            text = (repo_root / rel_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            return True
    return False


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
    require_sha_ancestry: bool = False,
    enforce_owner_attestation: bool = False,
    enforce_phase4_honesty: bool = False,
    enforce_condition_verdicts: bool = False,
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

    ``require_sha_ancestry`` is the ordinary-CI tip-SHA gate (Phase 1): every
    green organ must record a well-formed ``last_verified_sha`` that is an
    ancestor of HEAD when git can answer. Exact tip equality remains
    ``strict_last_verified`` / ``--strict-release`` (chicken-egg: a commit
    cannot truthfully self-stamp its own SHA; see
    ``release/phase6/STRICT_RELEASE_PROCEDURE.md``).

    ``enforce_owner_attestation`` is the Phase 2 CI/launcher boundary. When
    enabled with ``repo_root``, every organ must define its named owner class
    in its own production entrypoints, regardless of whether the row is
    currently yellow or green. Frozen organs 1--5 still cannot claim green
    here (security-spine RED), but after the 2026-07-31 §VIII Deploy their
    Decision A owner classes are attested like every other organ.

    ``enforce_phase4_honesty`` is the Phase 4 absolute boundary: every
    ``proof_level="live"`` row must carry a full 40-char commit SHA and a
    re-checkable description, and every organ without live evidence must
    name one precise Outside/Docker/Ollama/Phase-6/frozen/browser reason.

    ``enforce_condition_verdicts`` is the Phase 3 boundary: every organ must
    carry written C1..C12 verdicts so greens can keep ``known_blockers``
    empty without wiping the durable per-condition attestations.
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

    if enforce_condition_verdicts:
        for record in records:
            verdicts = record.condition_verdicts or {}
            missing_keys = [
                key
                for key in REQUIRED_CONDITION_VERDICT_KEYS
                if key not in verdicts or not str(verdicts.get(key) or "").strip()
            ]
            if missing_keys:
                violations.append(
                    f"organ_id {record.organ_id} ({record.name}) is missing "
                    f"written condition_verdicts for {missing_keys} "
                    "(Phase 3 requires C1..C12 for every organ)"
                )
            else:
                for key in REQUIRED_CONDITION_VERDICT_KEYS:
                    text = str(verdicts[key]).strip()
                    if len(text) < 8:
                        violations.append(
                            f"organ_id {record.organ_id} ({record.name}) "
                            f"condition_verdicts[{key!r}] is too short to be a "
                            "real written verdict"
                        )

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

    if root is not None and enforce_owner_attestation:
        # §VIII approval channel. Until 2026-08-04 this check forbade a frozen
        # organ from being green UNCONDITIONALLY -- no evidence, approval or
        # artifact could satisfy it, which is why the operator's own §VIII
        # Approve+Deploy on 2026-07-31 left organs 1-5 yellow: the human act
        # happened and the code had no way to receive it.
        #
        # The gate is not weakened here, it is given an input only a human can
        # produce. spine_release.approved_organ_ids() returns a non-empty set
        # ONLY for a committed public key plus an artifact whose Ed25519
        # signature covers {organ_ids, commit_sha, evidence_digest} for the
        # evidence present right now, at an ancestor commit. It fails closed on
        # every other path. An agent can write all of this code and still not
        # satisfy it, because the private key never exists in the repository.
        spine_approved = spine_release.approved_organ_ids(
            root,
            records,
            current_sha=current_sha,
            is_ancestor=lambda sha: _git_ok(
                root, "merge-base", "--is-ancestor", sha, "HEAD"
            ),
        )
        for record in records:
            if record.organ_id in FROZEN_SECURITY_ORGAN_IDS:
                if record.status == "green" and record.organ_id not in spine_approved:
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) is frozen "
                        "security-spine RED and cannot claim green before controlled "
                        "self-modification approval"
                    )
                # Operator §VIII Approve+Deploy (2026-07-31): owner classes now
                # exist in aios/security/*. Still forbid green, but require the
                # same Decision A class attestation as every other organ.
            if not _authority_owner_is_class_reference(record, root):
                violations.append(
                    f"organ_id {record.organ_id} ({record.name}) has no Phase 2 "
                    f"owner attestation: authority_owner "
                    f"{record.authority_owner!r} is not defined as a class in its "
                    "own production_entrypoints"
                )

    if enforce_phase4_honesty:
        for record in records:
            live_rows = [
                evidence
                for evidence in record.live_evidence
                if evidence.proof_level == "live"
            ]
            for evidence in live_rows:
                if not _LIVE_COMMIT_SHA.fullmatch(evidence.commit_sha):
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) has "
                        f"proof_level='live' evidence with non-40-char commit_sha "
                        f"{evidence.commit_sha!r}"
                    )
                if not _LIVE_RECHECKABLE.search(evidence.description):
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) has "
                        "proof_level='live' evidence that is not re-checkable "
                        "(missing artifact path, TestClient/probe command, or CI URL)"
                    )
            if not live_rows:
                blocker_text = " ".join(record.known_blockers)
                if not _PHASE4_NAMED_REASON.search(blocker_text):
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) has no live "
                        "evidence and no precise named Phase 4 reason "
                        "(Outside-machine / no Docker / no Ollama / Phase 6 gate / "
                        "frozen spine / browser-session / Phase 4 absolute residual)"
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
        if (
            root is not None
            and not enforce_owner_attestation
            and not _authority_owner_is_class_reference(record, root)
        ):
            # Preserve the direct-call diagnostic used by existing fixture
            # consumers. The Phase 2 release boundary uses the stronger
            # all-status gate above and emits its own explicit message.
            violations.append(
                f"organ_id {record.organ_id} ({record.name}) is green but its "
                f"authority_owner {record.authority_owner!r} is not defined as a "
                "class anywhere in its own production_entrypoints -- a label, "
                "not a class reference (Decision A)"
            )
        if require_sha_ancestry:
            sha = record.last_verified_sha
            if not sha or not _LIVE_COMMIT_SHA.fullmatch(sha):
                violations.append(
                    f"organ_id {record.organ_id} ({record.name}) is green without "
                    "a well-formed last_verified_sha (Phase 1 ordinary-CI tip gate)"
                )
            elif root is not None:
                ancestry = sha_is_ancestor_of_head(root, sha)
                if ancestry is False:
                    violations.append(
                        f"organ_id {record.organ_id} ({record.name}) is green but "
                        f"last_verified_sha {sha!r} is not an ancestor of HEAD "
                        "(Phase 1 ordinary-CI tip gate)"
                    )
                # ancestry is None → shallow/missing object: do not fail closed
                # on unknowable history (same posture as test_ledger_verification_sha).
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
            # Currency, anchored to the organ's own verification claim.
            #
            # This replaces a rule that required EVERY row to carry the
            # evaluated commit's sha. That rule could never pass, and was never
            # exercised: no organ carried `requires_live_evidence` until the
            # 2026-09-01 recount, and the one that does (44) stayed yellow, so
            # the branch was never reached. It fails two ways.
            #
            # It is self-referential. Recording evidence creates a commit whose
            # sha the evidence could not have contained, so stamping the tip and
            # committing merely moves the tip. Demonstrated on 2026-09-02:
            # evidence stamped af268809, committed, gate then demanded 82b5c431.
            #
            # It is history-hostile. Applying to every row, it forces deleting
            # older evidence -- including runs that scored badly. Organ 44's own
            # C10 calls that laundering: "an organ whose evidence trail shows
            # only its best day is not an evidence trail". Squash-merging makes
            # it worse: 3 of organ 44's 5 historical shas are not ancestors of
            # HEAD at all, because their branches were squashed away.
            #
            # What currency actually requires is that the organ's verification
            # CLAIM is backed by a live run: at least one row stamped at
            # `last_verified_sha`. That sha is separately required above to be
            # well-formed and an ancestor of HEAD (Phase 1 tip gate), and at
            # release-tagging time `strict_last_verified` pins it to the
            # evaluated commit.
            #
            # This does NOT loosen what the flag exists to stop: fixture-labelled
            # evidence still cannot satisfy it (above), and an organ whose
            # evidence is all older than its own verification claim is refused.
            if record.live_evidence and not any(
                evidence.commit_sha == record.last_verified_sha
                for evidence in record.live_evidence
            ):
                violations.append(
                    f"organ_id {record.organ_id} ({record.name}) is green and "
                    "requires live evidence, but no live evidence is stamped at "
                    f"its last_verified_sha {record.last_verified_sha!r} -- every "
                    "row is older than the commit it claims verification at"
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
    require_sha_ancestry: bool = False,
    enforce_owner_attestation: bool = True,
    enforce_phase4_honesty: bool = False,
    enforce_condition_verdicts: bool = True,
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
        require_sha_ancestry=require_sha_ancestry,
        enforce_owner_attestation=enforce_owner_attestation,
        enforce_phase4_honesty=enforce_phase4_honesty,
        enforce_condition_verdicts=enforce_condition_verdicts,
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
    strict_source_commit: bool = False,
) -> tuple[str, ...]:
    """Return a tuple of truthful violation descriptions for a release
    manifest; empty means the manifest is an honest hash-pin of *records*
    and the files it claims to cover.

    The hash/summary checks below are genuinely continuous (true on every
    commit, not only at release-tagging time): a manifest whose recorded
    hashes drift from the actual file content it claims to cover is never a
    valid state to ship, regardless of which commit produced it.

    `source_commit_sha` is different, deliberately not held to the same
    continuous exact-match bar: a commit's SHA is a hash of its own final
    tree, so a file committed *as part of* that commit can only ever record
    its parent's SHA, never its own -- requiring exact equality to whatever
    HEAD happens to be on every ordinary commit is unsatisfiable by
    construction, not a real drift signal. This function only requires
    `source_commit_sha` to be present and well-formed continuously; exact
    equality to `current_sha` is opt-in via `strict_source_commit` for the
    Organ 23 / release-tagging gate, where the manifest is regenerated and
    verified as the last step before a tag is cut against that same commit.
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

    source_commit_sha = manifest.get("source_commit_sha")
    if not isinstance(source_commit_sha, str) or not re.fullmatch(
        r"[0-9a-f]{7,64}", source_commit_sha
    ):
        violations.append(
            f"manifest source_commit_sha {source_commit_sha!r} is missing or "
            "does not look like a real commit sha"
        )
    elif (
        strict_source_commit
        and current_sha is not None
        and source_commit_sha != current_sha
    ):
        violations.append(
            f"manifest source_commit_sha {source_commit_sha!r} does not match "
            f"the evaluated commit {current_sha!r} -- the manifest was not "
            "regenerated at this exact commit (release-tagging gate)"
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
    "GREEN_CONTRACT_CONDITIONS",
    "REQUIRED_CONDITION_VERDICT_KEYS",
    "TARGET_ORGAN_IDS",
    "FROZEN_SECURITY_ORGAN_IDS",
    "REQUIRED_ORGAN_COUNT",
    "OrganLedgerReport",
    "current_commit_sha",
    "sha_is_ancestor_of_head",
    "load_ledger",
    "validate_ledger",
    "validate_manifest",
    "evaluate_organs",
]
