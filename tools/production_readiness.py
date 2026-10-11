"""Production readiness, measured on THIS machine. The check is the claim.

    python tools/production_readiness.py            # the scoreboard
    python tools/production_readiness.py --json     # the same, as JSON
    python tools/production_readiness.py --no-v1-check

"Production" here is the operator's own machine running the production profile
24/7, local model first, cloud models optional (docs/PRODUCTION_HARDENING.md).
Each gate is measured, never asserted:

* PASS          measured, and the bar is met;
* FAIL          measured, and it is not -- the evidence says why;
* ERROR         the probe itself broke, so nothing was measured. Never a PASS,
                and never a FAIL the system earned: a dead instrument must not
                fabricate a verdict in either direction;
* NOT_MEASURED  no probe exists yet. Named, with the slice that builds it, so
                an unmeasured property is never read as a met one.

Ready means every gate is PASS. The exit code is 0 only then.

Read-only by construction. Live databases are opened ``mode=ro``: running a
newer tree's code against live data must never migrate it. ``v1-check`` runs
against a throwaway data directory, inheriting THIS environment, because what
it measures is whether this machine's environment (container runtime, keys)
supports the production profile. No secret value is ever read into the output:
key gates report presence, never content.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PASS, FAIL, ERROR, NOT_MEASURED = "PASS", "FAIL", "ERROR", "NOT_MEASURED"
PILLARS = ("cage", "animal", "clerk", "sovereign", "intelligence")

#: The cloud providers production can seat, by the variable that enables each.
CLOUD_KEY_NAMES = (
    "AWS_BEARER_TOKEN_BEDROCK",
    "AIOS_OPENAI_API_KEY",
    "AIOS_ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)
#: Keys the production container needs to verify, promote and sign learning.
PRODUCTION_KEY_NAMES = ("AIOS_VERIFICATION_AUTHORITY_KEY", "AIOS_LEARNING_KEY_LIVE")
_LOOPBACK = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")


@dataclass(frozen=True)
class Gate:
    pillar: str
    key: str
    status: str
    evidence: str
    #: Who must act to move it: "agent" (code) or "operator" (his machine/acts).
    owner: str = "agent"
    next_step: str = ""


@dataclass
class World:
    """Everything a gate reads, injectable so every gate is testable."""

    repo: Path
    data_dir: Path
    env: Mapping[str, str]
    run: Callable[[list[str], Mapping[str, str]], tuple[int, str]]
    http_json: Callable[[str], Optional[Any]]
    http_status: Callable[[str], Optional[int]]
    measure_v1: bool = True
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ro(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _gh_runs(world: World, *args: str) -> Optional[list[dict[str, Any]]]:
    rc, out = world.run(
        ["gh", "run", "list", *args, "--json", "conclusion,status,createdAt"],
        world.env,
    )
    if rc != 0:
        return None
    try:
        runs = json.loads(out)
    except json.JSONDecodeError:
        return None
    return runs if isinstance(runs, list) else None


def _compose_service(world: World, name: str) -> Optional[dict[str, Any]]:
    import yaml

    path = world.repo / "docker-compose.yml"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    service = (data.get("services") or {}).get(name)
    return service if isinstance(service, dict) else None


def _compose_env(service: dict[str, Any]) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, dict):
        return {str(k): "" if v is None else str(v) for k, v in raw.items()}
    env: dict[str, str] = {}
    for item in raw:
        name, _, value = str(item).partition("=")
        env[name] = value
    return env


# --------------------------------------------------------------------------- #
# Cage
# --------------------------------------------------------------------------- #


def cage_v1_check(world: World) -> Gate:
    if not world.measure_v1:
        return Gate("cage", "v1_check", NOT_MEASURED, "skipped (--no-v1-check)")
    with tempfile.TemporaryDirectory(prefix="readiness-v1-") as tmp:
        env = {**world.env, "AIOS_DATA_DIR": tmp}
        rc, out = world.run(
            [sys.executable, "-m", "aios.launcher", "v1-check", "--json"], env
        )
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        return Gate("cage", "v1_check", ERROR, f"v1-check printed no report (rc={rc})")
    if report.get("ready") is True:
        return Gate("cage", "v1_check", PASS, "v1-check: ready, every gate passed")
    failures = list(report.get("failures") or [])
    return Gate(
        "cage",
        "v1_check",
        FAIL,
        f"v1-check not ready; failing: {', '.join(failures) or '?'}",
        owner="operator",
        next_step="container runtime running + production keys in the keystore (H3)",
    )


def cage_organ_ledger(world: World) -> Gate:
    path = world.repo / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
    try:
        organs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Gate("cage", "organ_ledger", ERROR, f"ledger unreadable: {exc}")
    yellow = [o["organ_id"] for o in organs if o.get("status") != "green"]
    if not yellow:
        return Gate("cage", "organ_ledger", PASS, f"{len(organs)}/{len(organs)} green")
    return Gate(
        "cage",
        "organ_ledger",
        FAIL,
        f"{len(organs) - len(yellow)}/{len(organs)} green; not green: {yellow}",
        next_step="each yellow organ's named blockers (H9)",
    )


def _ci_gate(
    world: World, key: str, runs: Optional[list[dict[str, Any]]], need: int
) -> Gate:
    if runs is None:
        return Gate(
            "cage",
            key,
            ERROR,
            "could not read CI runs (is `gh` installed and authenticated?)",
        )
    done = [
        r
        for r in runs
        if r.get("status") == "completed" and r.get("conclusion") != "cancelled"
    ]
    latest = done[:need]
    if len(latest) < need:
        return Gate(
            "cage", key, FAIL, f"only {len(latest)} completed run(s); need {need}"
        )
    bad = [r for r in latest if r.get("conclusion") != "success"]
    shown = ", ".join(
        f"{r.get('createdAt', '?')[:10]}:{r.get('conclusion')}" for r in latest
    )
    return Gate("cage", key, FAIL if bad else PASS, f"last {need}: {shown}")


def cage_nightly(world: World) -> Gate:
    return _ci_gate(
        world,
        "nightly",
        _gh_runs(world, "--workflow", "nightly.yml", "--limit", "6"),
        3,
    )


def cage_master_ci(world: World) -> Gate:
    return _ci_gate(
        world,
        "master_ci",
        _gh_runs(world, "--workflow", "ci.yml", "--branch", "master", "--limit", "6"),
        1,
    )


# --------------------------------------------------------------------------- #
# Sovereign
# --------------------------------------------------------------------------- #


def sovereign_production_started(world: World) -> Gate:
    state = world.data_dir / "launcher-state.json"
    if not state.is_file():
        return Gate(
            "sovereign",
            "production_started",
            FAIL,
            "the production launcher has never run on this machine (no launcher state)",
            owner="operator",
            next_step="`gagos start --profile production` once H3 lands",
        )
    try:
        profile = json.loads(state.read_text(encoding="utf-8")).get("profile")
    except (OSError, json.JSONDecodeError) as exc:
        return Gate(
            "sovereign",
            "production_started",
            ERROR,
            f"launcher state unreadable: {exc}",
        )
    status = PASS if profile == "production" else FAIL
    return Gate(
        "sovereign", "production_started", status, f"launcher profile: {profile}"
    )


def sovereign_backend_ready(world: World) -> Gate:
    port = world.env.get("AIOS_API_PORT", "8000")
    url = f"http://127.0.0.1:{port}/ready"
    code = world.http_status(url)
    if code == 200:
        return Gate("sovereign", "backend_ready", PASS, f"{url} -> 200")
    return Gate(
        "sovereign",
        "backend_ready",
        FAIL,
        f"{url} -> {code if code is not None else 'no answer'}: the backend is not serving",
        owner="operator",
        next_step="production running under its restart policy (H3)",
    )


def sovereign_backups(world: World) -> Gate:
    from aios.operations.doctor import (
        BACKUP_STALE_AFTER_SECONDS,
        newest_backup_age_seconds,
    )

    age = newest_backup_age_seconds(world.data_dir / "backups")
    if age is None:
        return Gate(
            "sovereign",
            "backups",
            FAIL,
            "no restorable backup (a gagos-*.tar.gz archive) exists; ad hoc "
            "database copies are not counted -- recovery cannot restore them",
            next_step="`python -m aios backup create --if-stale` on a schedule + a restore drill (H5)",
        )
    days = age / 86400
    ok = age <= BACKUP_STALE_AFTER_SECONDS
    return Gate(
        "sovereign",
        "backups",
        PASS if ok else FAIL,
        f"newest backup is {days:.1f} days old (stale after "
        f"{BACKUP_STALE_AFTER_SECONDS / 86400:.0f}); nothing schedules them",
        next_step="" if ok else "scheduled backups + a restore drill (H5)",
    )


def sovereign_compose_local_model(world: World) -> Gate:
    service = _compose_service(world, "aios")
    if service is None:
        return Gate(
            "sovereign",
            "compose_local_model",
            ERROR,
            "no aios service in docker-compose.yml",
        )
    host = _compose_env(service).get("OLLAMA_HOST", "")
    if not host:
        return Gate(
            "sovereign",
            "compose_local_model",
            FAIL,
            "the production container sets no OLLAMA_HOST, so it dials 127.0.0.1:11434 -- "
            "itself, not the host's Ollama: production has no local model",
            next_step="point the container at the host's Ollama (H3)",
        )
    if any(lo in host for lo in _LOOPBACK):
        return Gate(
            "sovereign",
            "compose_local_model",
            FAIL,
            f"OLLAMA_HOST={host} is the container's own loopback",
        )
    return Gate("sovereign", "compose_local_model", PASS, f"OLLAMA_HOST={host}")


def sovereign_compose_keys(world: World) -> Gate:
    service = _compose_service(world, "aios")
    if service is None:
        return Gate(
            "sovereign", "compose_keys", ERROR, "no aios service in docker-compose.yml"
        )
    env = _compose_env(service)
    missing = [name for name in PRODUCTION_KEY_NAMES if name not in env]
    if not missing:
        return Gate(
            "sovereign",
            "compose_keys",
            PASS,
            "the production container receives its keys",
        )
    return Gate(
        "sovereign",
        "compose_keys",
        FAIL,
        f"the production container is never given {missing}: verification refuses "
        "and everything it learns is unsigned",
        next_step="keystore -> launcher -> container (H3)",
    )


# --------------------------------------------------------------------------- #
# Clerk
# --------------------------------------------------------------------------- #


def clerk_admitted_model(world: World) -> Gate:
    """Asked exactly as the dispatcher asks: is any model eligible for a job?"""
    from aios.domain.local_workforce.contracts import (
        LocalClerkRuntimeAuthority,
        LocalJobProfile,
        LocalJobRequest,
    )
    from aios.domain.local_workforce.registry import LocalWorkforceRegistry

    db = world.data_dir / "aios_memory.db"
    if not db.is_file():
        return Gate(
            "clerk", "admitted_model", FAIL, "no memory database, so no clerk registry"
        )
    try:
        with _ro(db) as conn:
            rows = conn.execute("SELECT * FROM local_worker_models").fetchall()
    except sqlite3.Error as exc:
        return Gate(
            "clerk", "admitted_model", ERROR, f"clerk registry unreadable: {exc}"
        )
    # The registry's own row conversion; its constructor touches nothing.
    registry = LocalWorkforceRegistry(ollama_client=object())  # type: ignore[arg-type]
    models = [registry._row_to_model(row) for row in rows]
    authority = LocalClerkRuntimeAuthority()
    deadline = world.now + timedelta(seconds=10)
    eligible: dict[str, list[str]] = {}
    for profile in LocalJobProfile:
        request = LocalJobRequest(
            job_id="readiness-probe",
            job_profile=profile,
            input_schema_version="1.0",
            evidence_references=frozenset(),
            redacted_payload="",
            token_budget=1,
            deadline=deadline,
            required_output_schema={},
        )
        for model in authority.eligible_models(request, models):
            eligible.setdefault(model.model_id, []).append(profile.value)
    if eligible:
        return Gate("clerk", "admitted_model", PASS, f"eligible: {eligible}")
    approved = [m.model_id for m in models if m.operator_approved]
    return Gate(
        "clerk",
        "admitted_model",
        FAIL,
        f"0 of {len(models)} local models may take any clerical job; "
        f"operator-approved: {approved or 'none'}",
        owner="operator",
        next_step="approve + qualify a model with the clerk CLI (H4)",
    )


def clerk_real_jobs(world: World) -> Gate:
    db = world.data_dir / "aios_local_workforce_provenance.db"
    if not db.is_file():
        return Gate(
            "clerk",
            "real_jobs",
            FAIL,
            "the clerk's provenance store does not exist: it has never run a job here",
            next_step="a live caller once a model is admitted (H4)",
        )
    try:
        with _ro(db) as conn:
            jobs = conn.execute("SELECT COUNT(*) FROM local_job_requests").fetchone()[0]
    except sqlite3.Error as exc:
        return Gate("clerk", "real_jobs", ERROR, f"clerk provenance unreadable: {exc}")
    return Gate(
        "clerk", "real_jobs", PASS if jobs else FAIL, f"{jobs} recorded clerk job(s)"
    )


#: The window of real use the one-gateway gate judges.
GATEWAY_WINDOW = timedelta(days=7)


def clerk_one_gateway(world: World) -> Gate:
    """Every model call on THIS machine passed a gateway entrance.

    Read from the model-call ledger (``aios/core/model_calls.py``), which each
    provider adapter writes as a request leaves. A call is judged by the code
    that made it: production code (``aios/``) must have come through an
    entrance; a measurement tool's own direct calls (``tools/``, ``tests/``)
    are reported, not judged -- a production path a tool drives is still
    judged, by the production frame that called the model.
    """
    from aios.core.model_calls import read_ledger

    records = read_ledger(world.data_dir, world.now - GATEWAY_WINDOW)
    days = GATEWAY_WINDOW.days
    if not records:
        return Gate(
            "clerk",
            "one_gateway",
            NOT_MEASURED,
            f"no model call recorded on this machine in {days} days",
            next_step="use GAGOS: every model call is recorded as it leaves",
        )
    damaged = [r for r in records if "unreadable" in r]
    if damaged:
        return Gate(
            "clerk",
            "one_gateway",
            ERROR,
            f"{len(damaged)} unreadable ledger line(s): calls that cannot be judged",
        )
    judged = [
        r
        for r in records
        if not str(r.get("site", "")).startswith(("tools/", "tests/"))
    ]
    instruments = len(records) - len(judged)
    ungated: dict[str, int] = {}
    entrances: dict[str, int] = {}
    for record in judged:
        entrance = record.get("entrance")
        if entrance:
            entrances[entrance] = entrances.get(entrance, 0) + 1
        else:
            site = str(record.get("site") or "?")
            ungated[site] = ungated.get(site, 0) + 1
    tail = (
        f"; {instruments} more from measurement tools, reported not judged"
        if instruments
        else ""
    )
    if ungated:
        worst = sorted(ungated.items(), key=lambda kv: -kv[1])[:5]
        return Gate(
            "clerk",
            "one_gateway",
            FAIL,
            f"{sum(ungated.values())} of {len(judged)} model calls in {days} days "
            f"passed no gateway entrance: "
            + ", ".join(f"{site} x{n}" for site, n in worst)
            + tail,
            next_step="route each site through an Organ 32 entrance",
        )
    if not judged:
        return Gate(
            "clerk",
            "one_gateway",
            NOT_MEASURED,
            f"only measurement tools called a model here in {days} days{tail}",
            next_step="use GAGOS: every model call is recorded as it leaves",
        )
    shown = ", ".join(f"{k} {v}" for k, v in sorted(entrances.items()))
    return Gate(
        "clerk",
        "one_gateway",
        PASS,
        f"{len(judged)} model calls in {days} days, every one through a gateway "
        f"entrance ({shown}){tail}",
    )


def _requested_clerk_roles(repo: Path) -> dict[str, list[str]]:
    """The roles production code asks the clerk for: every
    ``job_profile=LocalJobProfile.X`` in ``aios/``, outside the contracts
    themselves and the runtime proofs (fixtures, not callers)."""
    import ast

    found: dict[str, list[str]] = {}
    for path in sorted((repo / "aios").rglob("*.py")):
        rel = path.relative_to(repo).as_posix()
        if rel.endswith("_runtime_proof.py") or "/domain/local_workforce/" in rel:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg == "job_profile"
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "LocalJobProfile"
            ):
                found.setdefault(node.value.attr, []).append(rel)
    return found


def clerk_live_roles_earnable(world: World) -> Gate:
    """A role no qualification test covers can never be granted, so a live
    caller asking for it ALWAYS escalates: the clerk cannot do that job."""
    from aios.application.local_workforce.qualification_evidence import (
        TEST_ID_TO_JOB_PROFILE,
    )
    from aios.domain.local_workforce.contracts import LocalJobProfile

    requested = _requested_clerk_roles(world.repo)
    if not requested:
        return Gate(
            "clerk", "live_roles_earnable", FAIL, "no production code calls the clerk"
        )
    earnable = {profile.name for profile in TEST_ID_TO_JOB_PROFILE.values()}
    never = {
        role: callers for role, callers in requested.items() if role not in earnable
    }
    if not never:
        return Gate(
            "clerk",
            "live_roles_earnable",
            PASS,
            f"every requested role is earnable: {sorted(requested)}",
        )
    shown = "; ".join(
        f"{LocalJobProfile[role].value} (asked by {', '.join(callers)})"
        for role, callers in never.items()
    )
    return Gate(
        "clerk",
        "live_roles_earnable",
        FAIL,
        f"no qualification test covers {shown}: no model can ever earn it, so that "
        f"job always escalates. Earnable today: {sorted(earnable)}",
        next_step="a qualification test for each live role, or live callers for the earnable roles (H4)",
    )


# --------------------------------------------------------------------------- #
# Animal
# --------------------------------------------------------------------------- #


def animal_signing_key(world: World) -> Gate:
    from aios.memory.provenance import KEY_ENV

    name = KEY_ENV["live"]
    present = bool(world.env.get(name, "").strip())
    pinned_file = world.repo / ".aios" / "state" / "LEARNING_PUBLIC_KEYS.json"
    try:
        pinned = (
            json.loads(pinned_file.read_text(encoding="utf-8"))
            .get("keys", {})
            .get("live")
            or []
        )
    except (OSError, json.JSONDecodeError):
        pinned = []
    missing = ([] if present else [f"{name} (the signing key)"]) + (
        [] if pinned else ["a pinned live public key"]
    )
    if not missing:
        return Gate(
            "animal",
            "signing_key",
            PASS,
            f"{name} present; {len(pinned)} live key(s) pinned",
        )
    return Gate(
        "animal",
        "signing_key",
        FAIL,
        f"missing {missing}: everything learned is unsigned and refused at recall",
        owner="operator",
        next_step="generate the key once and store it in the keystore (H3/H8)",
    )


#: Where judging the pre-registered Phase 8 runs records its verdict: Holm over
#: {H1-cloud, H1c-cloud, H1-7B} (docs/learning/PAYOFF_PREREGISTRATION.md, D4).
#: Absent until a judged run exists; the baselines were reported, never judged.
JUDGED_PAYOFF = Path("docs") / "learning" / "payoff_judged_result.json"
#: The census asks as a principal that owns nothing. The recall gate refuses
#: a row "another principal" only after its signature verified, it is not
#: revoked and it names an owner -- exactly a row its OWNER's turn admits --
#: so that count is what reaches a live turn, from the gate's own derivation.
_OWNS_NOTHING = "scoreboard:owns-nothing"
_ADMITTED_TO_OWNER = "another principal"


def animal_usefulness(world: World) -> Gate:
    """Does what the animal learned reach a live turn, and did it help?"""
    from tools.learning_payoff import gate_census

    census = gate_census(
        _OWNS_NOTHING,
        db=world.data_dir / "aios_memory.db",
        library_db=world.data_dir / "aios_operational_state.db",
    )
    candidates = census["candidates"]
    reach = {
        kind: int(census["refused"][kind].get(_ADMITTED_TO_OWNER, 0))
        for kind in ("lessons", "skills")
    }
    if not (reach["lessons"] or reach["skills"]):
        refused = {
            k: v
            for k, v in census["refused"]["lessons"].items()
            if k != _ADMITTED_TO_OWNER
        }
        return Gate(
            "animal",
            "usefulness",
            FAIL,
            f"nothing learned reaches a live turn: 0 of {candidates['lessons']} "
            f"lessons and 0 of {candidates['skills']} active skills pass the "
            f"recall gate for their owner (lessons refused: {refused or 'none'})",
            owner="operator",
            next_step="pin the live learning key, then review and re-admit lessons "
            "(tools/readmit_learning.py --principal)",
        )
    reached = (
        f"{reach['lessons']} of {candidates['lessons']} lessons and "
        f"{reach['skills']} of {candidates['skills']} active skills reach their "
        "owner's turns"
    )
    judged_path = world.repo / JUDGED_PAYOFF
    if not judged_path.is_file():
        return Gate(
            "animal",
            "usefulness",
            NOT_MEASURED,
            f"{reached}; no judged payoff run yet (the baselines were reported, "
            "not judged, and showed no measurable benefit)",
            owner="operator",
            next_step="the pre-registered Phase 8 run "
            "(docs/learning/PAYOFF_PREREGISTRATION.md, D4)",
        )
    judged = json.loads(judged_path.read_text(encoding="utf-8"))
    met = judged.get("h1_met") is True
    return Gate(
        "animal",
        "usefulness",
        PASS if met else FAIL,
        f"{reached}; judged run: {judged.get('summary') or ('met' if met else 'not met')}",
        owner="operator",
    )


def animal_guards_scheduled(world: World) -> Gate:
    import yaml

    path = world.repo / ".github" / "workflows" / "learning-guards.yml"
    if not path.is_file():
        return Gate("animal", "guards_scheduled", FAIL, "no learning-guards workflow")
    workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # YAML 1.1 reads a bare `on:` key as the boolean True.
    triggers = workflow.get("on", workflow.get(True)) or {}
    if isinstance(triggers, dict) and "schedule" in triggers:
        return Gate(
            "animal", "guards_scheduled", PASS, "the reel and probe run on a schedule"
        )
    return Gate(
        "animal",
        "guards_scheduled",
        FAIL,
        "the red-team reel and mutation probe run only when dispatched by hand",
        owner="operator",
        next_step="add the cron line (CI minutes are your call)",
    )


# --------------------------------------------------------------------------- #
# Intelligence
# --------------------------------------------------------------------------- #


def intelligence_local_model(world: World) -> Gate:
    from aios import config

    host = world.env.get("OLLAMA_HOST", config.OLLAMA_HOST).rstrip("/")
    model = world.env.get("AIOS_LLM_MODEL", config.LLM_MODEL)
    tags = world.http_json(f"{host}/api/tags")
    if not isinstance(tags, dict):
        return Gate(
            "intelligence",
            "local_model",
            FAIL,
            f"Ollama at {host} did not answer",
            owner="operator",
        )
    names = {str(m.get("name")) for m in tags.get("models") or []}
    if model in names:
        return Gate("intelligence", "local_model", PASS, f"{model} is served by {host}")
    return Gate(
        "intelligence",
        "local_model",
        FAIL,
        f"{model} is not pulled at {host}",
        owner="operator",
    )


def intelligence_cloud_provider(world: World) -> Gate:
    present = [name for name in CLOUD_KEY_NAMES if world.env.get(name, "").strip()]
    if present:
        return Gate("intelligence", "cloud_provider", PASS, f"configured: {present}")
    return Gate(
        "intelligence",
        "cloud_provider",
        FAIL,
        "no cloud provider is configured for production (keys are only handed to "
        "one-off harness runs)",
        owner="operator",
        next_step="store the provider keys in the keystore (H3)",
    )


# --------------------------------------------------------------------------- #
# Not yet measured -- named, so absence is never read as a pass.
# --------------------------------------------------------------------------- #

NOT_YET = (
    (
        "sovereign",
        "offline_drill",
        "a turn served by the local model with the network cut",
        "H6",
    ),
    (
        "sovereign",
        "privacy_drill",
        "sensitive context kept from a cloud model, live",
        "H6",
    ),
    ("intelligence", "failover_drill", "cloud down -> local, live", "H6"),
)

GATES: tuple[Callable[[World], Gate], ...] = (
    cage_v1_check,
    cage_organ_ledger,
    cage_nightly,
    cage_master_ci,
    animal_signing_key,
    animal_guards_scheduled,
    animal_usefulness,
    clerk_admitted_model,
    clerk_live_roles_earnable,
    clerk_real_jobs,
    clerk_one_gateway,
    sovereign_production_started,
    sovereign_backend_ready,
    sovereign_backups,
    sovereign_compose_local_model,
    sovereign_compose_keys,
    intelligence_local_model,
    intelligence_cloud_provider,
)


def measure(world: World) -> list[Gate]:
    gates: list[Gate] = []
    for probe in GATES:
        try:
            gates.append(probe(world))
        except Exception as exc:  # noqa: BLE001 - a broken probe is ERROR, never a verdict
            pillar, _, key = probe.__name__.partition("_")
            gates.append(
                Gate(pillar, key, ERROR, f"probe raised {type(exc).__name__}: {exc}")
            )
    for pillar, key, what, slice_ in NOT_YET:
        gates.append(
            Gate(
                pillar, key, NOT_MEASURED, f"not measured yet: {what}", next_step=slice_
            )
        )
    return gates


def ready(gates: list[Gate]) -> bool:
    return bool(gates) and all(g.status == PASS for g in gates)


# --------------------------------------------------------------------------- #
# The real world
# --------------------------------------------------------------------------- #


def _run(argv: list[str], env: Mapping[str, str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(REPO_ROOT),
            env=dict(env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout


def _http_json(url: str) -> Optional[Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - local probe
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - "did not answer" is the measurement
        return None


def _http_status(url: str) -> Optional[int]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - local probe
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:  # noqa: BLE001
        return None


def real_world(*, measure_v1: bool) -> World:
    from aios import config

    return World(
        repo=REPO_ROOT,
        data_dir=Path(config.DATA_DIR),
        env=dict(os.environ),
        run=_run,
        http_json=_http_json,
        http_status=_http_status,
        measure_v1=measure_v1,
    )


def render(gates: list[Gate]) -> str:
    lines: list[str] = []
    for pillar in PILLARS:
        rows = [g for g in gates if g.pillar == pillar]
        passed = sum(g.status == PASS for g in rows)
        lines.append(f"\n{pillar.upper()}  {passed}/{len(rows)} pass")
        for g in rows:
            lines.append(f"  {g.status:<13}{g.key}: {g.evidence}")
            if g.status != PASS and g.next_step:
                lines.append(f"  {'':<13}  next ({g.owner}): {g.next_step}")
    total = sum(g.status == PASS for g in gates)
    verdict = "READY" if ready(gates) else "NOT READY"
    lines.append(f"\n{verdict}: {total}/{len(gates)} gates pass")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--no-v1-check", action="store_true", help="skip the slow v1-check gate"
    )
    args = parser.parse_args(argv)
    gates = measure(real_world(measure_v1=not args.no_v1_check))
    if args.json:
        print(
            json.dumps(
                {"ready": ready(gates), "gates": [asdict(g) for g in gates]}, indent=2
            )
        )
    else:
        print(render(gates))
    return 0 if ready(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
