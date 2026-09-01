"""Release-time architecture and deployment invariants."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios.domain.workers.worker_contract import WorkerPrincipal
from aios.runtime.cortex_bus import CortexBus
from scripts.security_scan import scan
from tests.cortex_event_helpers import append_event


REPO_ROOT = Path(__file__).resolve().parents[1]
_AUTHORITY_IMPORTS = frozenset(
    {
        "aios.application.capabilities.authority",
        "aios.infrastructure.capabilities.sqlite_store",
        "aios.core.approvals",
    }
)


def _import_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py")) if root.exists() else []


def test_model_and_worker_layers_do_not_import_capability_write_authority() -> None:
    paths = _python_files(REPO_ROOT / "aios" / "agents")
    paths += _python_files(REPO_ROOT / "aios" / "application" / "models")
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(
            _import_names(path) & _AUTHORITY_IMPORTS
        )
        for path in paths
        if _import_names(path) & _AUTHORITY_IMPORTS
    }
    assert not offenders, offenders


def test_queen_layer_does_not_import_executor_implementation() -> None:
    forbidden_fragments = (
        "aios.core.executor",
        "aios.executor_service",
        "aios.infrastructure.executor",
    )
    offenders: list[str] = []
    for path in _python_files(REPO_ROOT / "aios" / "council"):
        imports = _import_names(path)
        if any(
            any(fragment in name for fragment in forbidden_fragments)
            for name in imports
        ):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, offenders


def test_worker_principal_cannot_carry_operator_or_credential_fields() -> None:
    forbidden = {
        "operator_id",
        "password",
        "secret",
        "token",
        "credential",
        "session_cookie",
    }
    assert not forbidden.intersection(WorkerPrincipal.model_fields)


@pytest.mark.parametrize(
    "event_type",
    (
        "approval.decided",
        "grant.issued",
        "skill.promoted",
        "autonomy.granted",
        "verdict.accepted",
        "zone.changed",
    ),
)
def test_authority_event_families_are_blocked_from_cortex(
    tmp_path: Path, event_type: str
) -> None:
    bus = CortexBus(tmp_path / "cortex.db")
    with pytest.raises(ValueError, match="may never ride"):
        append_event(bus, event_type, "entity-1", {})


def test_control_plane_image_has_non_root_default_and_executor_owns_socket() -> None:
    control_dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    executor_dockerfile = (REPO_ROOT / "Dockerfile.executor").read_text(
        encoding="utf-8"
    )
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "USER 65534:65534" in control_dockerfile
    assert "USER 65534:65534" in executor_dockerfile
    control_service = compose.split("\n  executor:", maxsplit=1)[0]
    executor_service = compose.split("\n  executor:", maxsplit=1)[1].split(
        "\n  prometheus:", maxsplit=1
    )[0]
    assert "docker.sock" not in control_service
    assert "docker.sock" in executor_service
    assert "group_add:" in executor_service
    assert "${AIOS_DOCKER_SOCKET_GID:-999}" in executor_service


def test_release_authority_runs_strict_runtime_proof_matrix() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "Run strict GAGOS v1 runtime proof matrix" in workflow
    assert "python -m aios.launcher v1-check --strict --json" in workflow
    assert "AIOS_EXECUTOR_URL=http://executor:8081" in workflow
    assert "AIOS_EXECUTOR_REMOTE_WORKSPACE_ROOT=/workspace/jobs" in workflow
    assert '"$(pwd)/frontend:/app/frontend:ro"' in workflow


def test_ci_builds_the_workload_image_the_runtime_defaults_to() -> None:
    """CI must build whatever image verification jobs actually launch.

    `AIOS_CONTAINER_IMAGE` defaulted to `aios-executor:local` until 2026-08-11.
    CI never built it on purpose -- `docker compose up --build executor` built
    it as a side effect of starting the executor service. Repointing the default
    at `aios-worker:local` therefore broke the release-authority job on master:
    the worker sits behind compose's `build-only` profile, `up executor` skips
    it, and every job died with the image missing. Three isolation proofs failed
    with `status == 'failed'` and no mention of an image anywhere.

    Nothing connected the two facts, because the dependency was accidental. This
    test makes it explicit: whatever image the runtime defaults to, CI has to
    build it by name, so the next repoint fails in review instead of on master.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    from aios import config

    image = config.CONTAINER_IMAGE
    assert f"image: {image}" in compose, (
        f"the runtime launches {image!r} but no compose service declares it, "
        "so nothing in the repo can build it"
    )

    service = next(
        (
            name
            for name in ("worker", "executor")
            if f"  {name}:\n    image: {image}" in compose
        ),
        None,
    )
    assert service is not None, (
        f"{image!r} is declared in docker-compose.yml but not by a service this "
        "test knows how to check -- extend the test rather than dropping the rule"
    )
    assert f"build {service}" in workflow or f"--wait {service}" in workflow, (
        f"CI never builds {image!r} (compose service {service!r}), so every "
        "verification job will fail with the image missing -- exactly the "
        "regression that took the release-authority job down on master"
    )


def test_the_thesis_audit_actually_runs_in_ci() -> None:
    """The M1 anti-rot gate must be executed, not merely present in the repo.

    `tools/thesis_audit.py` asserts that config defaults still match the claims
    made in README/AGENTS/PLAN -- it is the machine-checked half of "the system
    is honest AND cannot silently rot". It shipped, passed, and was never wired
    into any workflow, so for weeks it proved nothing about any merge.

    That is the same failure this repo has now hit four times: `golden-cohort-local`
    reporting OK because the image was missing; a ledger-ordering rule believed to
    be CI-enforced that was not; C6/C7 satisfied by a test file merely EXISTING on
    disk. A check nobody runs is a claim.

    Asserted against the workflow text rather than by running the tool, because
    the failure mode being guarded is "it stopped being invoked", which a passing
    local run cannot detect.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "python tools/thesis_audit.py" in workflow, (
        "tools/thesis_audit.py is no longer invoked by ci.yml -- the M1 honesty "
        "gate has been reduced back to a script nobody runs"
    )

    tool = REPO_ROOT / "tools" / "thesis_audit.py"
    assert tool.exists(), (
        "ci.yml invokes tools/thesis_audit.py but the file is gone; the job "
        "would fail, but the rule belongs here where the reason is written down"
    )


def test_container_containment_is_proven_against_a_real_daemon() -> None:
    """The 2026-08-19 containment fix must be EXECUTED, not just constructed.

    `tests/test_executor.py` proves that fix by building the docker argv and
    asserting the string contains `readonly=true`. That is a good unit test of
    argv construction and says nothing about whether Docker honours it. The
    behaviour was verified by hand once, on 2026-08-19, and then nothing pinned
    it -- inventory item 84's core concern, and the reason this step exists.

    An argv assertion cannot catch a Docker version that parses `readonly=true`
    differently, an overlapping-mount ordering change where the writable
    scope-root mounts shadow the read-only parent, or an edit that keeps the
    string and breaks the effect.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "tests/test_container_containment_integration.py" in workflow, (
        "the real-container containment proof is no longer run by CI; the "
        "isolation boundary is back to being asserted only against argv strings"
    )
    assert 'AIOS_EXECUTOR_INTEGRATION: "1"' in workflow, (
        "the containment suite is gated on AIOS_EXECUTOR_INTEGRATION=1 and will "
        "silently ALL-SKIP without it -- a green job proving nothing"
    )

    suite = REPO_ROOT / "tests" / "test_container_containment_integration.py"
    assert suite.exists()
    body = suite.read_text(encoding="utf-8")
    # Both directions, or the forbidden-write test passes trivially on a
    # container that cannot write anything at all.
    assert "can_still_write_its_own_scope_root" in body, (
        "the containment suite no longer proves the sandbox CAN write its own "
        "scope root; read-only-everything is not the fix and would break every "
        "mission while looking like security"
    )


def test_release_source_scan_is_clean() -> None:
    assert scan() == ()


def test_emergency_governance_routes_are_registered_and_separate_from_council() -> None:
    from aios.api.main import app

    def application_paths(routes) -> set[str]:
        paths: set[str] = set()
        for route in routes:
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                paths.update(application_paths(original_router.routes))
            elif hasattr(route, "path"):
                paths.add(route.path)
        return paths

    paths = application_paths(app.routes)
    assert "/api/v1/governance/emergency-stop" in paths
    assert "/api/v1/governance/emergency-stop/engage" in paths
    assert "/api/v1/governance/emergency-stop/clear" in paths


def test_r3_migrated_routes_do_not_issue_legacy_approval_tokens() -> None:
    for relative in (
        "aios/api/main.py",
        "aios/api/routes/actions.py",
        "aios/api/routes/council.py",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "approvals.issue(" not in source, relative
        assert "approval_store.issue(" not in source, relative
        assert "LegacyApprovalAdapter" not in source, relative
        assert "approvals.redeem(" not in source, relative
        assert "approvals.consume(" not in source, relative


def test_action_broker_uses_exact_capability_authority_in_production() -> None:
    source = (REPO_ROOT / "aios" / "application" / "action_broker.py").read_text(
        encoding="utf-8"
    )
    assert "CapabilityAuthority" in source
    assert "capabilities.issue" in source
    assert "capabilities.consume" in source
    assert "legacy test adapter" in source
    assert "from aios.core.approvals" not in source


def test_convergence_ledger_uses_truthful_status_taxonomy() -> None:
    ledger = (
        REPO_ROOT / ".aios" / "state" / "PRODUCTION_CONVERGENCE_LEDGER.md"
    ).read_text(encoding="utf-8")

    assert "**DONE**" not in ledger
    for status in ("VERIFIED", "PARTIAL", "DORMANT", "BLOCKED"):
        assert status in ledger
    assert "Human Sovereign identity | **VERIFIED**" in ledger
    assert "Exact capabilities | **VERIFIED**" in ledger
    assert "TurnCoordinator | **VERIFIED**" in ledger
    assert "PromotionAuthority | **VERIFIED**" in ledger
    assert "EmergencyStopController | **VERIFIED**" in ledger
    assert "Isolated Executor Service | **VERIFIED**" in ledger


def test_restart_resilience_step_proves_a_restart_not_a_cold_start() -> None:
    """This step used to be `docker compose restart executor` followed by
    `docker compose up -d --wait executor`, with a comment asserting that
    exporting AIOS_DOCKER_SOCKET_GID kept the resolved config identical so `up`
    would only wait. It did not. Runs 29989936411, 30751967500 and 30756711677
    all log `Recreate` / `Recreated` right after the restart, and then report
    `CREATED 16 seconds ago` for a container that was ~110s old -- so the
    post-restart suite exercised a brand-new container and a cold start was
    being reported as restart resilience for over a week.

    Pin the shape that makes that impossible rather than trusting the comment.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    step = workflow.split('- name: "Restart private Executor Service', maxsplit=1)[
        1
    ].split(
        "- name: Prove private Executor Service isolation survives a restart",
        maxsplit=1,
    )[0]

    assert "docker compose restart executor" in step
    # The whole defect: anything that re-runs `up` here can silently recreate
    # the container and downgrade this proof back into a cold start.
    assert "docker compose up" not in step
    # The container must be the SAME one on the other side of the restart.
    assert "State.Health.Status" in step
    assert "REPLACED, not restarted" in step


def test_every_job_that_runs_a_golden_mission_builds_the_workload_image() -> None:
    """The image rule has to hold PER JOB, not per file.

    `test_ci_builds_the_workload_image_the_runtime_defaults_to` asserts the
    string "build worker" appears in ci.yml. It does, in release-authority --
    so the rule stayed green while `golden-cohort-local`, added later, launched
    the same containers and never built the image.

    On 2026-08-19 that job executed for the first time and scored 0/1: every
    verify step died with "Unable to find image 'aios-worker:local'" (exit 125,
    the docker daemon refusing to start a container) and the integrity gate
    still reported OK. A whole cohort run proved nothing, and said it was fine.

    A file-scoped assertion cannot see a second job. This one iterates jobs, so
    the next job that drives the runner has to build what it launches.
    """
    import yaml

    from aios import config

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    image = config.CONTAINER_IMAGE

    offenders = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        runs = " ".join(str(step.get("run", "")) for step in (job.get("steps") or []))
        if "golden_mission_runner.py" not in runs:
            continue
        # Either build the image by name, or declare it is not using the
        # container backend at all -- both are honest, silence is not.
        builds = "build worker" in runs or f"image inspect {image}" in runs
        opts_out = "AIOS_APPROVED_EXECUTION_BACKEND" in yaml.dump(job)
        if not (builds or opts_out):
            offenders.append(job_name)

    assert not offenders, (
        f"job(s) {offenders} drive golden_mission_runner.py but never build "
        f"{image!r}, which AIOS_APPROVED_EXECUTION_BACKEND='container' makes "
        "every verify step depend on. The mission will score 0 for a reason "
        "that has nothing to do with the model."
    )


def test_every_job_that_runs_docker_compose_supplies_its_required_variables() -> None:
    """`docker compose` interpolates the WHOLE file before building anything.

    `golden-cohort-local` builds only the `worker` service, but compose still
    resolves grafana's and the executor's variables first, so a job that omits
    them dies with "required variable ... is missing a value" and never reaches
    the image. That is exactly how the first attempt at building the workload
    image failed: the job was fixed, the build step was added, and the build
    itself could not start.

    Derived from docker-compose.yml rather than hard-coded, so adding a new
    `${VAR:?...}` to compose fails here instead of in a job nobody watches.
    """
    import re

    import yaml

    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{([A-Z_]+):\?", compose_text))
    assert required, "expected compose to declare at least one required variable"

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )

    offenders = {}
    for job_name, job in (workflow.get("jobs") or {}).items():
        job_env = set((job.get("env") or {}).keys())
        for step in job.get("steps") or []:
            if "docker compose" not in str(step.get("run", "")):
                continue
            supplied = job_env | set((step.get("env") or {}).keys())
            missing = required - supplied
            if missing:
                offenders.setdefault(job_name, set()).update(missing)

    assert not offenders, (
        "job(s) run `docker compose` without the variables compose requires: "
        f"{ {k: sorted(v) for k, v in offenders.items()} }. compose resolves the "
        "entire file before building, so the build fails before it starts."
    )


def test_the_strict_release_gate_still_blocks_on_a_release_tag() -> None:
    """`continue-on-error` on the strict gate must stay conditional.

    The gate was made ADVISORY on manual dispatch because it is structurally red
    there: --strict-release requires every green organ's last_verified_sha to
    EQUAL HEAD, and outside a release cut all of them differ, necessarily, since
    every merge moves HEAD. A permanently-red gate teaches people to ignore it,
    and it made every dispatch run conclude `failure` -- which made the cohort
    evidence inside that run uncitable under C10, whose verifier requires a
    cited run to have SUCCEEDED.

    The danger is the obvious next edit: `continue-on-error: true`, which would
    silently defang the gate at release time, exactly where tip equality IS the
    claim. This asserts the expression stays keyed to workflow_dispatch.
    """
    import yaml

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["release-strict-gate"]
    coe = job.get("continue-on-error")

    assert coe is not True, (
        "release-strict-gate is unconditionally advisory -- it would no longer "
        "block a gagos-release-* tag, which is the only place it has teeth"
    )
    assert isinstance(coe, str) and "workflow_dispatch" in coe, (
        "release-strict-gate's continue-on-error must stay keyed to "
        f"workflow_dispatch so release tags still block; found {coe!r}"
    )
    assert "gagos-release-" in str(job.get("if", "")), (
        "release-strict-gate must still run on release tags"
    )
