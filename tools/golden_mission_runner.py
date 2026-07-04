"""Golden mission runner: automated repeatable end-to-end mission sequences.

A "golden mission" is a multi-turn conversation that exercises the full
supervised agent loop — planning, tool use, verification, and memory
recall — as a cohesive workflow. Each mission defines ordered steps with
explicit success criteria; the mission passes only when ALL steps verify.

Usage:
    python tools/golden_mission_runner.py run [--mission NAME] [--repeats N]
    python tools/golden_mission_runner.py list
    python tools/golden_mission_runner.py report

Missions are designed to be idempotent: each run resets sandbox state,
executes the full sequence, and records pass/fail per step + overall.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aios.probe_common import ALLOWED_CMD_RE, ALLOWED_FILE_RE, BASE

try:
    import requests
except ImportError:
    sys.exit("requires: pip install requests")

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / ".aios" / "audit"
LOG_PATH = AUDIT_DIR / "golden-mission-runs.jsonl"

TURN_TIMEOUT_S = 900
MAX_REPLAYS = 10


MISSIONS: dict[str, dict[str, Any]] = {
    "tdd-workflow": {
        "description": "Full TDD cycle: write failing test, implement, verify green",
        "steps": [
            {
                "prompt": "Create training_ground/test_calculator.py with pytest tests for a Calculator class that has add(a,b), subtract(a,b), multiply(a,b), and divide(a,b) methods. divide by zero should raise ZeroDivisionError. Do NOT create the Calculator class yet — only the tests. Then verify that the tests FAIL (they should fail because the module doesn't exist).",
                "files": ["training_ground/test_calculator.py"],
                "expect": "verified_failure",
            },
            {
                "prompt": "Create training_ground/calculator.py with the Calculator class implementing add, subtract, multiply, and divide methods that make all the tests in training_ground/test_calculator.py pass. Then verify that the tests pass.",
                "files": ["training_ground/calculator.py"],
                "expect": "verified_success",
            },
        ],
    },
    "iterative-refinement": {
        "description": "Build, test, find a bug, fix it — the debugging loop",
        "steps": [
            {
                "prompt": "Create training_ground/sorted_insert.py with a function sorted_insert(sorted_list, value) that inserts value into the correct position in an already sorted list (in-place) and returns the list. Then create training_ground/test_sorted_insert.py with pytest tests covering empty list, beginning, middle, end, and duplicates. Then verify that the tests pass.",
                "files": ["training_ground/sorted_insert.py", "training_ground/test_sorted_insert.py"],
                "expect": "verified_success",
            },
            {
                "prompt": "Edit training_ground/test_sorted_insert.py to add a test that verifies sorted_insert works correctly with a list of 1000 elements (generate the sorted list with range(0, 2000, 2) and insert 999). Then verify that the tests pass.",
                "files": [],
                "expect": "verified_success",
            },
        ],
    },
    "multi-module": {
        "description": "Build two cooperating modules with integration test",
        "steps": [
            {
                "prompt": "Create training_ground/validator.py with a function validate_email(email) that returns True if the email contains exactly one @ with non-empty local and domain parts, and the domain contains at least one dot. Then create training_ground/test_validator.py with pytest tests. Then verify that the tests pass.",
                "files": ["training_ground/validator.py", "training_ground/test_validator.py"],
                "expect": "verified_success",
            },
            {
                "prompt": "Create training_ground/user_registry.py that imports validate_email from training_ground.validator and has a UserRegistry class with register(name, email) that raises ValueError for invalid emails, and list_users() that returns registered names. Then create training_ground/test_user_registry.py with pytest tests covering valid registration, invalid email rejection, and listing. Then verify that the tests pass.",
                "files": ["training_ground/user_registry.py", "training_ground/test_user_registry.py"],
                "expect": "verified_success",
            },
        ],
    },
    "error-handling": {
        "description": "Build robust error-handling code with comprehensive tests",
        "steps": [
            {
                "prompt": "Create training_ground/safe_json.py with functions safe_parse(text) that returns (parsed_dict, None) on success or (None, error_string) on failure, and safe_get(data, path) where path is a dot-separated key path that returns the nested value or None if any key is missing. Then create training_ground/test_safe_json.py with pytest tests covering valid JSON, invalid JSON, nested paths, and missing keys. Then verify that the tests pass.",
                "files": ["training_ground/safe_json.py", "training_ground/test_safe_json.py"],
                "expect": "verified_success",
            },
        ],
    },
    "data-pipeline": {
        "description": "Build a data transformation pipeline end-to-end",
        "steps": [
            {
                "prompt": "Create training_ground/pipeline.py with a Pipeline class that has add_step(fn) to register transformation functions and run(data) that passes data through each step in order. Include a built-in step filter_nulls that removes None values from lists. Then create training_ground/test_pipeline.py with pytest tests covering empty pipeline, single step, chained steps, and filter_nulls. Then verify that the tests pass.",
                "files": ["training_ground/pipeline.py", "training_ground/test_pipeline.py"],
                "expect": "verified_success",
            },
            {
                "prompt": "Edit training_ground/pipeline.py to add error handling: if any step raises an exception, Pipeline.run should return a PipelineError(step_index, original_exception) instead of crashing. Edit training_ground/test_pipeline.py to add tests for the error-handling behavior. Then verify that the tests pass.",
                "files": [],
                "expect": "verified_success",
            },
        ],
    },
}


def log_event(record: dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_sse(resp: requests.Response) -> Iterator[tuple[str, dict[str, Any]]]:
    event: str | None = None
    data_lines: list[str] = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            if event is not None:
                payload = json.loads("\n".join(data_lines) or "{}")
                yield event, payload
            event, data_lines = None, []
        elif raw.startswith("event:"):
            event = raw[len("event:"):].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:"):].strip())
    if event is not None and data_lines:
        yield event, json.loads("\n".join(data_lines))


def check_allowlist(payload: dict[str, Any]) -> tuple[bool, str]:
    inp = payload.get("input", {})
    if inp.get("creations"):
        paths = [str(c.get("filepath", "")) for c in inp["creations"]]
        bad = [p for p in paths if not ALLOWED_FILE_RE.match(p)]
        return (not bad, f"create {paths}" if not bad else f"creation outside allowlist: {bad}")
    if inp.get("edits"):
        paths = [str(e.get("filepath", "")) for e in inp["edits"]]
        bad = [p for p in paths if not ALLOWED_FILE_RE.match(p)]
        return (not bad, f"edit {paths}" if not bad else f"edit outside allowlist: {bad}")
    if inp.get("commands"):
        cmds = [str(c) for c in inp["commands"]]
        bad = [c for c in cmds if not ALLOWED_CMD_RE.match(c)]
        return (not bad, f"run {cmds}" if not bad else f"command outside allowlist: {bad}")
    return False, "unrecognized approval payload shape"


def run_prompt(prompt: str, session_id: str, model_id: str = "auto") -> dict[str, Any]:
    tokens: list[str] = []
    approvals_granted: list[str] = []
    evidence: list[str] = []

    for replay in range(MAX_REPLAYS):
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "modelId": model_id,
            "sessionId": session_id,
            "approvalTokens": tokens,
        }
        resp = requests.post(f"{BASE}/api/generate", json=body, stream=True, timeout=TURN_TIMEOUT_S)
        resp.raise_for_status()
        paused: dict[str, Any] | None = None
        finished = False

        for event, data in parse_sse(resp):
            if event == "step":
                output = str(data.get("output", ""))
                if output.startswith(("[VERIFY PASS]", "[VERIFY FAIL]", "[VERIFY SKIPPED]")):
                    evidence.append(output)
            elif event == "human_required":
                paused = data
                break
            elif event == "error":
                return {"outcome": "error", "error": data, "evidence": evidence}
            elif event == "done":
                finished = True

        if finished and paused is None:
            counted = [e for e in evidence if e.startswith(("[VERIFY PASS]", "[VERIFY FAIL]"))]
            if not counted:
                outcome = "unverified"
            elif counted[-1].startswith("[VERIFY PASS]"):
                outcome = "verified_success"
            else:
                outcome = "verified_failure"
            return {"outcome": outcome, "approvals": approvals_granted, "evidence": evidence}

        if paused is None:
            return {"outcome": "truncated", "evidence": evidence}

        ok, why = check_allowlist(paused)
        token = paused.get("input", {}).get("approvalToken")
        if not ok or not token:
            return {"outcome": "rejected", "reason": why, "evidence": evidence}
        approvals_granted.append(why)
        tokens = [token]

    return {"outcome": "max_replays", "evidence": evidence}


def reset_mission_files(mission: dict[str, Any]) -> None:
    for step in mission["steps"]:
        for rel in step.get("files", []):
            if not ALLOWED_FILE_RE.match(rel):
                continue
            target = ROOT / rel
            if target.exists():
                target.unlink()


def run_mission(name: str, mission: dict[str, Any], model_id: str, run_id: str) -> dict[str, Any]:
    reset_mission_files(mission)
    steps_results: list[dict[str, Any]] = []
    mission_passed = True

    for step_idx, step in enumerate(mission["steps"]):
        session_id = f"golden-{name}-s{step_idx}-{run_id}"
        print(f"  step {step_idx + 1}/{len(mission['steps'])}: {step['prompt'][:80]}...")

        result = run_prompt(step["prompt"], session_id, model_id=model_id)
        expected = step["expect"]
        step_passed = result["outcome"] == expected

        steps_results.append({
            "step": step_idx,
            "outcome": result["outcome"],
            "expected": expected,
            "passed": step_passed,
        })
        status = "PASS" if step_passed else "FAIL"
        print(f"    {status}: got={result['outcome']} expected={expected}")

        if not step_passed:
            mission_passed = False
            break

    return {
        "mission": name,
        "run_id": run_id,
        "passed": mission_passed,
        "steps": steps_results,
        "steps_completed": len(steps_results),
        "steps_total": len(mission["steps"]),
    }


def cmd_run(args: argparse.Namespace) -> None:
    if args.mission and args.mission not in MISSIONS:
        sys.exit(f"unknown mission: {args.mission!r}. Use 'list' to see available missions.")

    targets = {args.mission: MISSIONS[args.mission]} if args.mission else MISSIONS
    all_results: list[dict[str, Any]] = []

    for repeat in range(args.repeats):
        print(f"\n{'='*60}")
        print(f"[golden] repeat {repeat + 1}/{args.repeats}")
        print(f"{'='*60}")

        for name, mission in targets.items():
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            print(f"\n[golden] mission={name}: {mission['description']}")
            log_event({"kind": "mission-start", "mission": name, "run_id": run_id, "repeat": repeat})

            t0 = time.monotonic()
            result = run_mission(name, mission, args.model, run_id)
            result["elapsed_s"] = round(time.monotonic() - t0, 1)
            result["repeat"] = repeat

            all_results.append(result)
            status = "PASSED" if result["passed"] else "FAILED"
            print(f"  [{status}] {result['steps_completed']}/{result['steps_total']} steps in {result['elapsed_s']}s")
            log_event({"kind": "mission-complete", **result})

            reset_mission_files(mission)
            time.sleep(2)

    passed = sum(1 for r in all_results if r["passed"])
    total = len(all_results)
    print(f"\n[golden] FINAL: {passed}/{total} mission runs passed ({round(passed/max(total,1)*100)}%)")
    log_event({"kind": "batch-summary", "passed": passed, "total": total,
               "rate": round(passed / max(total, 1), 3)})


def cmd_list(_: argparse.Namespace) -> None:
    print("[golden] available missions:")
    for name, mission in MISSIONS.items():
        steps = len(mission["steps"])
        print(f"  {name} ({steps} steps): {mission['description']}")


def cmd_report(_: argparse.Namespace) -> None:
    if not LOG_PATH.exists():
        print("[golden] no runs recorded yet")
        return
    completions: list[dict[str, Any]] = []
    with LOG_PATH.open() as fh:
        for line in fh:
            record = json.loads(line)
            if record.get("kind") == "mission-complete":
                completions.append(record)

    if not completions:
        print("[golden] no completed missions")
        return

    by_mission: dict[str, list[dict[str, Any]]] = {}
    for c in completions:
        by_mission.setdefault(c["mission"], []).append(c)

    print(f"[golden] {len(completions)} total mission runs:")
    for name, runs in sorted(by_mission.items()):
        passed = sum(1 for r in runs if r["passed"])
        rate = round(passed / len(runs) * 100)
        avg_time = round(sum(r.get("elapsed_s", 0) for r in runs) / len(runs), 1)
        print(f"  {name}: {passed}/{len(runs)} passed ({rate}%) avg={avg_time}s")

    total_passed = sum(1 for r in completions if r["passed"])
    print(f"\n  overall: {total_passed}/{len(completions)} ({round(total_passed/len(completions)*100)}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden mission runner")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run golden missions")
    run_p.add_argument("--mission", type=str, default=None, help="Run a specific mission")
    run_p.add_argument("--repeats", type=int, default=1, help="Repeat all missions N times")
    run_p.add_argument("--model", type=str, default="auto", help="Model ID to use")
    run_p.set_defaults(func=cmd_run)

    list_p = sub.add_parser("list", help="List available missions")
    list_p.set_defaults(func=cmd_list)

    report_p = sub.add_parser("report", help="Show mission run report")
    report_p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
