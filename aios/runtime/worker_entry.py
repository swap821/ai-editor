"""Deterministic worker entrypoint for Council Runtime Phase 1A."""
from __future__ import annotations

import argparse
import os
import shlex
import traceback
from datetime import datetime, timezone
from pathlib import Path

from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.worker_api import ContractViolation, WorkerRuntime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def _default_forbidden_probe(contract: MissionContract) -> str:
    for rule in contract.forbidden_files:
        clean = rule.replace("\\", "/").strip().lstrip("./")
        if not clean:
            continue
        if clean.endswith("/") or "." not in Path(clean).name:
            return f"{clean.rstrip('/')}/blocked_probe.txt"
        return clean
    return "../outside-contract-probe.txt"


def run_worker(
    *,
    contract_path: Path,
    result_path: Path,
    worker_id: str,
    runtime_root: Path,
) -> int:
    started_at = _utc_now()
    contract = MissionContract.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    runtime = WorkerRuntime(
        contract,
        worker_id=worker_id,
        runtime_root=runtime_root,
        result_path=result_path,
    )
    status = "failed"
    summary = "Deterministic worker failed."
    risk_after = contract.risk_level

    try:
        plan_text = ""
        if "request_plan" in contract.allowed_tools or contract.metadata.get(
            "hybrid_plan_prompt"
        ):
            plan_prompt = str(
                contract.metadata.get("hybrid_plan_prompt")
                or f"Create a plan for this mission: {contract.goal}"
            )
            plan_text = runtime.request_plan(
                plan_prompt,
                allow_cloud=bool(contract.metadata.get("allow_cloud_reasoning", False)),
            )
            runtime.emit_evidence({"plan_text": plan_text})

        forbidden_probe = str(
            contract.metadata.get("deterministic_forbidden_probe")
            or _default_forbidden_probe(contract)
        )
        forbidden_blocked = False
        try:
            runtime.read_file(forbidden_probe)
        except ContractViolation as exc:
            forbidden_blocked = True
            runtime.emit_evidence(
                {
                    "forbidden_probe": forbidden_probe,
                    "forbidden_access_blocked": True,
                    "forbidden_block_reason": str(exc),
                }
            )

        if not contract.allowed_files:
            raise ContractViolation("deterministic worker needs one allowed file")
        target_file = str(
            contract.metadata.get("deterministic_target_file")
            or contract.allowed_files[0]
        )
        original = runtime.read_file(target_file)
        comment = str(
            contract.metadata.get(
                "deterministic_append_comment",
                "// Council Runtime deterministic worker heartbeat",
            )
        )
        if plan_text and contract.metadata.get("include_plan_in_comment", False):
            first_line = plan_text.splitlines()[0][:120]
            comment = f"{comment} | plan: {first_line}"
        separator = "" if original.endswith("\n") else "\n"
        runtime.write_file(target_file, f"{original}{separator}{comment}\n")

        verification_results = []
        for command in contract.verification_commands:
            verification_results.append(runtime.run_command(_split_command(command)))
        runtime.emit_evidence(
            {
                "deterministic_target_file": target_file,
                "verification": verification_results,
            }
        )

        if forbidden_blocked:
            status = "completed"
            summary = "Deterministic worker completed under MissionContract."
            risk_after = "GREEN"
        else:
            status = "contract_violation"
            summary = "Forbidden probe was not blocked by WorkerRuntime."
            risk_after = "RED"
    except ContractViolation as exc:
        status = "contract_violation"
        summary = str(exc)
        risk_after = "RED"
        runtime.emit_evidence({"error": summary})
    except Exception as exc:  # pragma: no cover - covered through subprocess path
        status = "failed"
        summary = str(exc)
        risk_after = contract.risk_level
        runtime.emit_evidence(
            {
                "error": summary,
                "traceback": traceback.format_exc(),
            }
        )

    result = WorkerResult(
        mission_id=contract.mission_id,
        worker_id=worker_id,
        status=status,
        summary=summary,
        risk_after=risk_after,
        started_at=started_at,
        ended_at=_utc_now(),
    )
    runtime.finish(result)
    return 0 if status == "completed" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--runtime-root", required=True)
    args = parser.parse_args(argv)
    return run_worker(
        contract_path=Path(args.contract),
        result_path=Path(args.result),
        worker_id=args.worker_id,
        runtime_root=Path(args.runtime_root),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
