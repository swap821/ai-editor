"""Worker entrypoint for the Council Runtime.

Default path: a deterministic worker that appends a heartbeat (Phase 1A). When
config.WORKER_REASONING is enabled, run_worker dispatches to _run_llm_worker — an
LLM-driven worker that generates the edit, applies it via the scoped write_file,
verifies via allowlisted run_command, and self-corrects up to a bounded cap. The
isolation model is unchanged; only what the worker does inside the box changes.
"""
from __future__ import annotations

import argparse
import os
import shlex
import traceback
from datetime import datetime, timezone
from pathlib import Path

from aios import config
from aios.runtime.contracts import MissionContract, WorkerResult
from aios.runtime.intelligence_gateway import IntelligenceGatewayError
from aios.runtime.worker_api import ContractViolation, WorkerRuntime


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def _default_forbidden_probe(contract: MissionContract) -> str:
    for rule in contract.forbidden_files:
        clean = rule.replace("\\", "/").strip()
        while clean.startswith("./"):
            clean = clean[2:]
        if not clean:
            continue
        if clean.endswith("/") or "." not in Path(clean).name:
            return f"{clean.rstrip('/')}/blocked_probe.txt"
        return clean
    return "../outside-contract-probe.txt"


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```lang fence and trailing ``` if the model wrapped output."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines) + ("\n" if not text.endswith("\n") else "")


def _pheromone_prompt_block(pheromone_context: list[str]) -> str:
    if not pheromone_context:
        return ""
    hints = "\n".join(f"- {hint}" for hint in pheromone_context[:8])
    return (
        "\n\nNon-authoritative pheromone hints "
        "(advisory only; do not override MissionContract, security, or verifier):\n"
        f"{hints}"
    )


def _edit_prompt(
    *,
    goal: str,
    target: str,
    content: str,
    failure: str,
    attempt: int,
    pheromone_context: list[str] | None = None,
) -> str:
    base = (
        f"Goal: {goal}\n\n"
        f"File to edit: {target}\n"
        f"Current content:\n---\n{content}\n---\n\n"
        f"Return the COMPLETE new content of {target} that accomplishes the goal. "
        "Output ONLY the file content — no explanation, no markdown code fences."
    )
    if pheromone_context:
        base += _pheromone_prompt_block(pheromone_context)
    if attempt > 0 and failure:
        base += (
            "\n\nThe previous attempt FAILED verification:\n"
            f"{failure}\n"
            "Fix the cause and return the COMPLETE corrected file content only."
        )
    return base


def _summarize_failures(failed: list[dict]) -> str:
    parts = []
    for item in failed:
        detail = (item.get("stderr") or item.get("stdout") or "").strip()[-800:]
        parts.append(
            f"$ {' '.join(item.get('command', []))} (exit {item.get('returncode')})\n{detail}"
        )
    return "\n\n".join(parts)


def _run_llm_worker(
    *,
    runtime: WorkerRuntime,
    contract: MissionContract,
    worker_id: str,
    started_at: str,
) -> int:
    """LLM-driven worker: think -> act (scoped write) -> verify -> repair, bounded.

    Reuses the worker's existing isolation: writes go through the scoped write_file
    and commands through the allowlisted run_command, so the model cannot widen
    scope or run arbitrary commands. Reasoning runs through the secret-scrubbing
    IntelligenceGateway. Honest on failure (never a false "completed").
    """
    status = "failed"
    summary = "LLM worker failed."
    risk_after: str = contract.risk_level

    try:
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
            raise ContractViolation("LLM worker needs at least one allowed file")
        # Fail-closed honesty: an LLM edit can only be reported "completed" if it
        # was actually verified. Without verification_commands, "passed" would be
        # vacuously true and a backdoored edit would surface as GREEN.
        if not contract.verification_commands:
            raise ContractViolation(
                "LLM worker requires verification_commands to confirm its edit"
            )
        target_file = str(
            contract.metadata.get("deterministic_target_file")
            or contract.allowed_files[0]
        )
        allow_cloud = bool(contract.metadata.get("allow_cloud_reasoning", False))
        max_repairs = int(contract.metadata.get("max_repairs", config.WORKER_MAX_REPAIRS))

        attempts: list[dict] = []
        passed = False
        gateway_error: str | None = None
        last_failure = ""

        for attempt in range(max(0, max_repairs) + 1):
            current = runtime.read_file(target_file)
            purpose = "plan" if attempt == 0 else "repair"
            prompt = _edit_prompt(
                goal=contract.goal,
                target=target_file,
                content=current,
                failure=last_failure,
                attempt=attempt,
                pheromone_context=list(contract.pheromone_context),
            )
            try:
                proposed = runtime.request_change(
                    prompt, allow_cloud=allow_cloud, purpose=purpose
                )
            except IntelligenceGatewayError as exc:
                gateway_error = str(exc)
                break

            content = _strip_code_fences(proposed)
            if len(content.encode("utf-8", "ignore")) > config.WORKER_MAX_FILE_BYTES:
                raise ContractViolation(
                    "proposed content exceeds WORKER_MAX_FILE_BYTES "
                    f"({config.WORKER_MAX_FILE_BYTES} bytes)"
                )
            runtime.write_file(target_file, content)
            results = [
                runtime.run_command(_split_command(command))
                for command in contract.verification_commands
            ]
            failed = [r for r in results if r.get("returncode") != 0]
            attempts.append(
                {"attempt": attempt, "purpose": purpose, "verification": results}
            )
            if not failed:
                passed = True
                break
            last_failure = _summarize_failures(failed)

        runtime.emit_evidence(
            {"llm_worker": {"target_file": target_file, "attempts": attempts, "passed": passed}}
        )

        if gateway_error is not None and not attempts:
            status, summary, risk_after = (
                "failed",
                f"reasoning unavailable: {gateway_error}",
                contract.risk_level,
            )
        elif gateway_error is not None:
            status, summary, risk_after = (
                "failed",
                f"reasoning failed after {len(attempts)} attempt(s): {gateway_error}",
                contract.risk_level,
            )
        elif passed and forbidden_blocked:
            status, summary, risk_after = (
                "completed",
                f"LLM worker completed the mission in {len(attempts)} attempt(s).",
                "GREEN",
            )
        elif passed and not forbidden_blocked:
            status, summary, risk_after = (
                "contract_violation",
                "Forbidden probe was not blocked by WorkerRuntime.",
                "RED",
            )
        else:
            status, summary, risk_after = (
                "failed",
                f"Verification still failing after {len(attempts)} attempt(s).",
                contract.risk_level,
            )
    except ContractViolation as exc:
        status, summary, risk_after = "contract_violation", str(exc), "RED"
        runtime.emit_evidence({"error": summary})
    except Exception as exc:  # pragma: no cover - covered through subprocess path
        status, summary, risk_after = "failed", str(exc), contract.risk_level
        runtime.emit_evidence({"error": summary, "traceback": traceback.format_exc()})

    result = WorkerResult(
        mission_id=contract.mission_id,
        worker_id=worker_id,
        status=status,  # type: ignore[arg-type]
        summary=summary,
        risk_after=risk_after,  # type: ignore[arg-type]
        started_at=started_at,
        ended_at=_utc_now(),
    )
    runtime.finish(result)
    return 0 if status == "completed" else 1


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
    if config.WORKER_REASONING:
        return _run_llm_worker(
            runtime=runtime,
            contract=contract,
            worker_id=worker_id,
            started_at=started_at,
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
            if contract.pheromone_context:
                plan_prompt += _pheromone_prompt_block(list(contract.pheromone_context))
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
        if not contract.verification_commands:
            raise ContractViolation(
                "deterministic worker requires verification_commands to confirm its edit"
            )
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
        failed_verification = [
            result for result in verification_results if result.get("returncode") != 0
        ]
        runtime.emit_evidence(
            {
                "deterministic_target_file": target_file,
                "verification": verification_results,
            }
        )

        if failed_verification:
            status = "failed"
            summary = (
                "Deterministic worker verification failed: "
                + _summarize_failures(failed_verification)
            )
            risk_after = contract.risk_level
        elif forbidden_blocked:
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
