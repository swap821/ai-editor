#!/usr/bin/env python3
"""Phase 4 absolute live-evidence runner (API / real SQLite).

Binding bar: ``.aios/state/PHASE_4_5_6_ABSOLUTE_BAR.md``.

Hostile-reader contract for each claimed organ:
  * production authority path (or TestClient HTTP) against real on-disk state
  * tip SHA recorded
  * JSON artifact under ``release/phase4/`` with command + evidence text
  * process exit 0 only when every claimed organ passed

This deliberately does NOT wrap pytest. Docker is probed and reported; Docker
organs are not claimed when the daemon is absent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "release" / "phase4"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class OrganProof:
    organ_id: int
    name: str
    passed: bool
    command: str
    evidence: str


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def _docker_available() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=REPO_ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker info failed to start: {exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, err[-1] if err else f"docker info exit {proc.returncode}"
    return True, "docker info exit 0"


def _run_wave(scratch: Path) -> list[OrganProof]:
    # Import only after AIOS_DATA_DIR / verification key are set by main().
    from aios.application.governance import runtime_proof as rp
    from aios.application.local_workforce.dispatcher import ClerkDispatcherAuthority
    from aios.application.models.privacy_audit import PrivacyAuditTracker
    from aios.application.observability.authority import ObservabilityAuthority
    from aios.domain.local_workforce.qualifier import QualificationResult
    from fastapi.testclient import TestClient
    from aios.api.main import app

    proofs: list[OrganProof] = []
    failures: list[str] = []

    def claim(
        organ_id: int, name: str, command: str, fn
    ) -> str | None:
        try:
            text = fn()
        except Exception as exc:  # noqa: BLE001 - per-organ isolation
            failures.append(f"organ {organ_id}: {exc}\n{traceback.format_exc()}")
            proofs.append(
                OrganProof(
                    organ_id=organ_id,
                    name=name,
                    passed=False,
                    command=command,
                    evidence=f"FAILED: {exc}",
                )
            )
            return None
        proofs.append(
            OrganProof(
                organ_id=organ_id,
                name=name,
                passed=True,
                command=command,
                evidence=text,
            )
        )
        return text

    # --- organs 9 / 10 / 15 / 16 / 17 / 18 / 19 via production probes ---
    claim(9, "Exact Capability Authority", "rp._probe_capabilities",
          lambda: rp._probe_capabilities(scratch))
    claim(10, "Mission Authority", "rp._probe_mission",
          lambda: rp._probe_mission(scratch))
    staging = claim(
        15,
        "Evidence and Verification Authority (construction)",
        "rp._probe_staging_and_promotion",
        lambda: rp._probe_staging_and_promotion(scratch),
    )
    if staging is not None:
        proofs.append(
            OrganProof(
                organ_id=16,
                name="Promotion Authority (construction)",
                passed=True,
                command="rp._probe_staging_and_promotion (same live run as organ 15)",
                evidence=staging,
            )
        )
    else:
        proofs.append(
            OrganProof(
                organ_id=16,
                name="Promotion Authority (construction)",
                passed=False,
                command="rp._probe_staging_and_promotion (same live run as organ 15)",
                evidence="FAILED: organ 15 staging/promotion probe did not pass",
            )
        )
    claim(17, "Cortex Observation Bus", "rp._probe_cortex",
          lambda: rp._probe_cortex(scratch))
    claim(18, "Memory Authority (construction)", "rp._probe_memory",
          lambda: rp._probe_memory(scratch))
    claim(19, "Emergency Stop Controller (construction)",
          "rp._probe_emergency_stop",
          lambda: rp._probe_emergency_stop(scratch))

    def _organ36() -> str:
        authority = ClerkDispatcherAuthority()
        det = authority.dispatch(deterministic_available=True, qualification=None)
        unqual = authority.dispatch(deterministic_available=False, qualification=None)
        failing = authority.dispatch(
            deterministic_available=False,
            qualification=QualificationResult(
                passed=False,
                schema_validity=0.0,
                identifier_preservation=0.0,
                authority_mutation_attempts=0,
                tool_requests_accepted=0,
                secret_reproduction=0,
                unsupported_claim_rate=1.0,
                timeout_rate=0.0,
            ),
            confidence=0.95,
        )
        if (det, unqual, failing) != (
            "deterministic",
            "frontier_escalation",
            "frontier_escalation",
        ):
            raise RuntimeError(
                f"unexpected dispatcher decisions: {det=}, {unqual=}, {failing=}"
            )
        return f"decisions deterministic={det}, unqual={unqual}, failing={failing}"

    claim(
        36,
        "Clerical Job Contract and Dispatcher",
        "ClerkDispatcherAuthority.dispatch deterministic/unqual/failing",
        _organ36,
    )

    def _organ50() -> str:
        db = scratch / "organ50_privacy_audits.db"
        tracker = PrivacyAuditTracker(database_path=db)
        tracker.record(
            "ollama",
            {
                "model": "phase4-local",
                "redacted_fields": ["api_key"],
                "route": "/api/v1/chat",
            },
        )
        first = list(tracker.recent(limit=5))
        restarted = PrivacyAuditTracker(database_path=db)
        second = list(restarted.recent(limit=5))
        status = restarted.durable_status()
        if not first or not second or not status.get("durable"):
            raise RuntimeError(
                f"privacy audit durability failed: {first=!r} {second=!r} {status=!r}"
            )
        return (
            f"rows_before={len(first)} rows_after_reopen={len(second)} "
            f"durable_status={status} db_bytes={db.stat().st_size}"
        )

    claim(
        50,
        "Provenance and Explanation Surface",
        "PrivacyAuditTracker.record + reopen real SQLite",
        _organ50,
    )

    def _organ52() -> str:
        obs = ObservabilityAuthority(log_dir=scratch / "logs")
        health = obs.health()
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            client.headers["Host"] = "localhost:8000"
            client.headers["Origin"] = "http://localhost:5173"
            response = client.get("/health")
            body = response.json()
            if response.status_code != 200 or body.get("status") != "ok":
                raise RuntimeError(f"/health failed: {response.status_code} {body}")
            stop = client.get("/api/v1/governance/emergency-stop")
            if stop.status_code != 200:
                raise RuntimeError(
                    f"emergency-stop HTTP {stop.status_code}: {stop.text[:200]}"
                )
        # Side-claim HTTP surface for organ 19 in the same live API process.
        proofs.append(
            OrganProof(
                organ_id=19,
                name="Emergency Stop Controller (construction)",
                passed=True,
                command="TestClient GET /api/v1/governance/emergency-stop",
                evidence=f"HTTP 200 body={stop.json()}",
            )
        )
        return (
            f"/health status=ok version={body.get('version')}; "
            f"authority.health={health}; "
            "Docker container log durability NOT claimed (daemon absent on host)"
        )

    claim(
        52,
        "Observability and Health Organ",
        "ObservabilityAuthority.health + TestClient GET /health",
        _organ52,
    )

    if failures:
        # Keep partial proofs so the artifact still names what passed/failed.
        proofs.append(
            OrganProof(
                organ_id=0,
                name="wave-failures",
                passed=False,
                command="scripts/phase4_live_evidence.py",
                evidence=f"{len(failures)} failure(s):\n" + "\n---\n".join(failures),
            )
        )
    return [p for p in proofs if p.organ_id != 0] + (
        [p for p in proofs if p.organ_id == 0]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tip", default=None)
    args = parser.parse_args(argv)
    tip = args.tip or _git_sha()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="phase4-live-", ignore_cleanup_errors=True
    ) as raw:
        scratch = Path(raw)
        data_dir = scratch / "aios-data"
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["AIOS_DATA_DIR"] = str(data_dir)
        os.environ["AIOS_VERIFICATION_AUTHORITY_KEY"] = (
            "phase4-live-evidence-key-32-bytes-min!"
        )
        os.environ["AIOS_PROMOTION_AUTHORITY_KEY"] = (
            "phase4-live-promotion-key-32-bytes-min!"
        )

        errors: list[str] = []
        proofs: list[OrganProof] = []
        try:
            proofs = _run_wave(scratch)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{exc}\n{traceback.format_exc()}")

        docker_ok, docker_msg = _docker_available()
        all_passed = not errors and bool(proofs) and all(p.passed for p in proofs)
        report = {
            "schema": "phase4-live-evidence-v1",
            "generated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "tip_sha": tip,
            "runner": "scripts/phase4_live_evidence.py",
            "command": (
                f"{sys.executable} scripts/phase4_live_evidence.py --tip {tip}"
            ),
            "docker_available": docker_ok,
            "docker_note": docker_msg,
            "proofs": [asdict(p) for p in proofs],
            "errors": errors,
            "all_passed": all_passed,
            "exit_code": 0 if all_passed else 1,
        }
        out_path = OUT_DIR / f"live-evidence-{tip[:12]}.json"
        payload = json.dumps(report, indent=2) + "\n"
        out_path.write_text(payload, encoding="utf-8")
        (OUT_DIR / "live-evidence-latest.json").write_text(payload, encoding="utf-8")
        print(
            json.dumps(
                {
                    "artifact": str(out_path.as_posix()),
                    "tip_sha": tip,
                    "organs_passed": sorted({p.organ_id for p in proofs if p.passed}),
                    "docker_available": docker_ok,
                    "all_passed": all_passed,
                    "exit_code": report["exit_code"],
                },
                indent=2,
            )
        )
        if errors:
            print("\n".join(errors), file=sys.stderr)
        return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
