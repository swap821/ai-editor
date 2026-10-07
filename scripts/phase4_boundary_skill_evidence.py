"""Narrow real-SQLite evidence refresh for organs 26 and 43 only.

No backend edits, historical artifact rewrites, arbitrary --tip, model/network
calls, release declaration, or human review claim. See PHASE_4_5_6_ABSOLUTE_BAR.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def backend_tip(root: Path) -> str:
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "aios"],
        cwd=root,
        text=True,
    ).strip()
    if dirty:
        raise RuntimeError("backend differs from HEAD; cannot attribute a live proof")
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def probe_boundary(scratch: Path) -> str:
    from aios.application.capabilities.authority import EmergencyStopHardWiringAuthority
    from aios.application.governance.emergency_stop import (
        EmergencyStopController,
        EmergencyStopHooks,
    )

    def noop(*_args, **_kwargs):
        return None

    controller = EmergencyStopController(
        scratch / "estop26.db",
        hooks=EmergencyStopHooks(
            revoke_capabilities=noop,
            cancel_queued_missions=noop,
            kill_active_workers=noop,
            disable_autonomy=noop,
            preserve_evidence=noop,
        ),
    )
    EmergencyStopHardWiringAuthority.assert_operational(
        controller, boundary="phase4-live"
    )
    try:
        EmergencyStopHardWiringAuthority.assert_operational(
            object(), boundary="phase4-live-bad"
        )
    except TypeError:
        pass
    else:
        raise RuntimeError("non-checkable emergency_stop was accepted")
    return "real SQLite controller accepted; non-checkable dependency refused; no worker/hook termination claimed"


def probe_skill(scratch: Path) -> str:
    from aios.application.learning.skill_lifecycle import SkillLifecycleAuthority
    from aios.domain.learning.repository import SkillRecord, SkillRepository

    db = scratch / "skills43.db"
    repo = SkillRepository(db)
    now = datetime.now(timezone.utc).isoformat()
    skill = SkillRecord(
        skill_id="skill-p4",
        version=1,
        problem_signature="sig",
        applicability_conditions={},
        known_exclusions=[],
        required_inputs=[],
        required_project_state={},
        procedure="do X",
        allowed_tools=[],
        allowed_scope_pattern="*",
        expected_observations=[],
        verification_plan=None,
        escalation_conditions=[],
        source_trajectory_ids=[],
        confidence=0.5,
        success_count=0,
        failure_count=0,
        last_validated_versions=[],
        state="active",
        created_at=now,
        updated_at=now,
    )
    try:
        repo.save(skill)
    except ValueError:
        pass
    else:
        raise RuntimeError("store accepted a skill saved straight into active")
    repo.save(skill.model_copy(update={"state": "candidate"}))
    repo.transition_state("skill-p4", 1, "human_reviewed")
    repo.transition_state("skill-p4", 1, "active")
    updated = SkillLifecycleAuthority(repo).apply_reuse_outcome(
        "skill-p4", 1, success=True
    )
    got = SkillLifecycleAuthority(SkillRepository(db)).repository.get("skill-p4", 1)
    if (
        got is None
        or got.success_count != 1
        or got.state != "active"
        or got.confidence != updated.confidence
    ):
        raise RuntimeError(f"skill outcome not durable: {got}")
    return (
        "direct active birth refused; candidate→human_reviewed→active (synthetic probe transition, "
        f"NOT operator approval); reopen SQLite success_count={got.success_count} confidence={got.confidence} state={got.state}"
    )


def main() -> int:
    tip = backend_tip(REPO_ROOT)
    out = (
        REPO_ROOT
        / "release"
        / "phase4"
        / f"live-evidence-boundary-skill-{tip[:12]}.json"
    )
    if out.exists():
        raise RuntimeError(f"preserve existing evidence: {out}; re-run at a new commit")
    runner_path = Path(__file__)
    runner_hash = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    command = f'"{sys.executable}" scripts/phase4_boundary_skill_evidence.py'
    proofs = []
    errors = []
    prior_data_dir = os.environ.get("AIOS_DATA_DIR")
    with tempfile.TemporaryDirectory(
        prefix="phase4-boundary-skill-", ignore_cleanup_errors=True
    ) as raw:
        scratch = Path(raw)
        os.environ["AIOS_DATA_DIR"] = str(scratch / "data")
        try:
            for organ_id, name, probe in (
                (
                    26,
                    "Emergency Stop Organ (full boundary hard-wiring)",
                    probe_boundary,
                ),
                (43, "Local Skill Reuse, Confidence and Demotion", probe_skill),
            ):
                try:
                    evidence = probe(scratch)
                    passed = True
                except Exception as exc:  # noqa: BLE001 - preserve failure, never a passed proof
                    evidence = f"{type(exc).__name__}: {exc}"
                    passed = False
                proofs.append(
                    dict(
                        organ_id=organ_id,
                        name=name,
                        passed=passed,
                        command=command,
                        evidence=evidence,
                    )
                )
            if backend_tip(REPO_ROOT) != tip:
                errors.append("backend HEAD changed during measurement")
            if hashlib.sha256(runner_path.read_bytes()).hexdigest() != runner_hash:
                errors.append("runner changed during measurement")
        finally:
            if prior_data_dir is None:
                os.environ.pop("AIOS_DATA_DIR", None)
            else:
                os.environ["AIOS_DATA_DIR"] = prior_data_dir

    passed = not errors and all(p["passed"] for p in proofs)
    report = {
        "schema": "phase4-live-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tip_sha": tip,
        "runner": "scripts/phase4_boundary_skill_evidence.py",
        "runner_sha256": runner_hash,
        "command": command,
        "scope": "Only organs26/43 production authorities + real temporary SQLite. Backend clean at HEAD before/after; unrelated UI edits allowed. No models/network/Docker, human approval, worker termination, or release readiness claimed.",
        "proofs": proofs,
        "errors": errors,
        "all_passed": passed,
        "exit_code": 0 if passed else 1,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    # A new artifact only; never overwrite historical or live-evidence-latest.
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "artifact": str(out),
                "tip_sha": tip,
                "proofs": proofs,
                "errors": errors,
                "exit_code": report["exit_code"],
            },
            indent=2,
        )
    )
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
